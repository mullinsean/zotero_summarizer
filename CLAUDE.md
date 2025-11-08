# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Zotero Summarizer** is a Python tool suite for working with Zotero libraries via the Zotero API.

The primary tool is **ZoteroResearcher** (`zresearcher.py`), a sophisticated research assistant that analyzes sources based on a research brief, ranks them by relevance, and generates targeted summaries with key quotes and statistics. It uses a two-phase workflow with project-based organization:

- **Phase 1 (Build)**: Generate project-aware summaries with metadata and tags for all sources
- **Phase 2 (Query)**: Evaluate relevance against a research brief and generate targeted summaries

The tool supports a **Zotero-native workflow** where all configuration and outputs are stored in Zotero (recommended).

**Legacy tools** (now deprecated, moved to `/old/`):
- `extract_html.py` - Simple HTML-to-Markdown extraction (superseded by ZoteroResearcher)
- `summarize_sources.py` - Basic source summarization (superseded by ZoteroResearcher)

## Package Manager

**This project uses `uv` for Python package management.** All commands should be run with `uv run` to ensure proper dependency resolution.

## Common Commands

### Development Setup
```bash
# Create and activate virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt
```

### Running the Application

**ZoteroResearcher - Primary Tool**
```bash
# Step 0: List collections
uv run python -m src.zresearcher --list-collections

# Step 1: Initialize a project in a collection (creates template notes in Zotero)
uv run python -m src.zresearcher --init-collection \
    --collection COLLECTION_KEY --project "My Research Project"

# Step 2: List existing projects in a collection
uv run python -m src.zresearcher --list-projects --collection COLLECTION_KEY

# Step 3: (Optional) Organize sources to ensure all items have acceptable attachments
uv run python -m src.zresearcher --organize-sources --collection COLLECTION_KEY

# Step 4: Edit the template notes in Zotero (in the 【ZResearcher: PROJECT】 subcollection):
#   - 【Project Overview: PROJECT】 (describe your research project)
#   - 【Research Tags: PROJECT】 (one tag per line)
#   - 【Research Brief: PROJECT】 (your research question)
#   - 【Project Config: PROJECT】 (optional: tune performance & LLM settings)

# Step 5: Build general summaries (Phase 1 - loads config from Zotero)
uv run python -m src.zresearcher --build-summaries \
    --collection COLLECTION_KEY --project "My Research Project"

# Rebuild existing summaries (force mode)
uv run python -m src.zresearcher --build-summaries \
    --collection COLLECTION_KEY --project "My Research Project" --force

# Step 6: Run query (Phase 2 - loads brief from Zotero, stores report as note)
uv run python -m src.zresearcher --query-summary \
    --collection COLLECTION_KEY --project "My Research Project"

# Verbose mode for detailed logging
uv run python -m src.zresearcher --query-summary \
    --collection COLLECTION_KEY --project "My Research Project" --verbose
```

**ZoteroResearcher - File Search (Google Gemini RAG)**
```bash
# Step 1: Edit the Query Request note in Zotero (in the 【ZResearcher: PROJECT】 subcollection):
#   - 【Query Request】 (your File Search query)

# Step 2: Run File Search query (auto-uploads files if needed, then queries)
uv run python -m src.zresearcher --file-search \
    --collection COLLECTION_KEY --project "My Research Project"

# Verbose mode for detailed logging
uv run python -m src.zresearcher --file-search \
    --collection COLLECTION_KEY --project "My Research Project" --verbose

# Force re-upload of all files (clears existing corpus and re-uploads)
uv run python -m src.zresearcher --file-search \
    --collection COLLECTION_KEY --project "My Research Project" --force
```

**ZoteroResearcher - Cleanup**
```bash
# Preview cleanup for a specific project (dry-run mode - no changes made)
uv run python -m src.zresearcher --cleanup-project \
    --collection COLLECTION_KEY --project "My Research Project" --dry-run

# Clean up a specific project (deletes subcollection and all summary notes)
uv run python -m src.zresearcher --cleanup-project \
    --collection COLLECTION_KEY --project "My Research Project"

# Skip confirmation prompt (useful for scripts)
uv run python -m src.zresearcher --cleanup-project \
    --collection COLLECTION_KEY --project "My Research Project" --yes

# Preview cleanup for ALL projects in a collection (dry-run mode)
uv run python -m src.zresearcher --cleanup-collection \
    --collection COLLECTION_KEY --dry-run

# Clean up ALL projects in a collection (use with caution!)
uv run python -m src.zresearcher --cleanup-collection \
    --collection COLLECTION_KEY --yes

# Verbose mode shows detailed error messages
uv run python -m src.zresearcher --cleanup-project \
    --collection COLLECTION_KEY --project "My Research Project" --verbose
```

**Diagnostic Utility**
```bash
# Run diagnostic utility for troubleshooting
uv run python -m src.zotero_diagnose --user
uv run python -m src.zotero_diagnose --group GROUP_ID
```

**Legacy Tools** (deprecated, see `/old/` directory):
```bash
# extract_html.py and summarize_sources.py have been superseded by zresearcher.py
# These files are preserved in /old/ for reference only
```

### Linting & Code Quality
No linting tools currently configured. Future setup should include tools like `black`, `ruff`, or `pylint`.

### Testing
No test framework currently configured. Tests should be added in `/tests/` directory using `pytest` or `unittest`.

## Code Architecture

### ZoteroResearcher Modular Architecture

**As of the major refactoring**, `zresearcher.py` has been split into a modular architecture for better maintainability:

**File Structure:**
```
src/
├── zresearcher.py (~380 lines)         # CLI entry point & routing
├── zr_common.py (~760 lines)           # Base class & shared utilities
├── zr_init.py (~290 lines)             # Collection initialization workflow
├── zr_organize_sources.py (~350 lines) # Source organization workflow
├── zr_build.py (~440 lines)            # Phase 1: Build summaries workflow
├── zr_query.py (~990 lines)            # Phase 2: Query & report generation workflow
├── zr_file_search.py (~450 lines)      # File Search: Gemini RAG integration
├── zr_cleanup.py (~530 lines)          # Cleanup: Delete projects & summary notes
├── zr_llm_client.py                    # Centralized LLM API client
├── zr_prompts.py                       # Prompt templates
└── zotero_base.py                      # Base Zotero API functionality
```

**Module Responsibilities:**

**`zresearcher.py`** - CLI Entry Point (91.5% reduction from original 2970 lines)
- Command-line argument parsing
- Environment variable loading and validation
- Routes to appropriate workflow classes
- No business logic - pure orchestration

**`zr_common.py`** - Base Class & Shared Utilities
- `ZoteroResearcherBase` class (inherits from `ZoteroBaseProcessor`)
  - Initialization & configuration management
  - `extract_metadata()` - Extract metadata from Zotero API
  - `get_source_content()` - Unified content retrieval (HTML/PDF/URL priority)
  - `extract_text_from_html()` - Trafilatura-based HTML extraction
  - `extract_text_from_pdf()` - PyMuPDF-based PDF extraction
  - `load_project_config_from_zotero()` - Load config from Zotero notes
  - `apply_project_config()` - Apply and validate configuration
  - All `_get_*_note_title()` helper methods
- `validate_project_name()` - Utility function for name validation

**`zr_init.py`** - Collection Initialization
- `ZoteroResearcherInit` class (inherits from `ZoteroResearcherBase`)
  - `init_collection()` - Create project subcollection & template notes
  - `list_projects()` - List existing projects in a collection

**`zr_organize_sources.py`** - Source Organization (Optional Workflow)
- `ZoteroResearcherOrganizer` class (inherits from `ZoteroResearcherBase`)
  - `organize_sources()` - Ensure all items have acceptable attachments (HTML/PDF/TXT)
  - `is_txt_attachment()` - Check if attachment is a text file
  - `has_acceptable_attachment()` - Verify item has processable attachment
  - `promote_attachment_to_parent()` - Convert standalone attachments to proper items
  - `save_webpage_snapshot()` - Fetch and save webpage HTML snapshots
  - Run after `init_collection` but before `build_summaries`

**`zr_build.py`** - Phase 1 Workflow
- `ZoteroResearcherBuilder` class (inherits from `ZoteroResearcherBase`)
  - `build_general_summaries()` - Main Phase 1 orchestration with parallel LLM processing
  - `load_project_overview_from_zotero()` - Load project context
  - `load_tags_from_zotero()` - Load tag taxonomy
  - `has_general_summary()` - Check for existing summaries
  - `format_general_summary_note()` - Create structured note format

**`zr_query.py`** - Phase 2 Workflow
- `ZoteroResearcherQuerier` class (inherits from `ZoteroResearcherBase`)
  - `run_query_summary()` - Main Phase 2 orchestration with parallel processing
  - `load_research_brief_from_zotero()` - Load research question
  - `parse_general_summary_note()` - Parse structured summaries
  - `rank_sources()` - Sort by relevance score
  - `generate_report_title()` - LLM-generated report titles
  - `_compile_research_html_string()` - HTML report generation
  - Smart storage: Notes <1MB, files >1MB with stub notes

**`zr_file_search.py`** - File Search Workflow (Google Gemini RAG)
- `ZoteroFileSearcher` class (inherits from `ZoteroResearcherBase`)
  - `run_file_search()` - Query Gemini File Search (auto-uploads if needed) and save results
  - `upload_files_to_gemini()` - Upload collection files to Gemini corpus
  - `load_query_request_from_zotero()` - Load query from Zotero note
  - `_load_gemini_state_from_config()` - Load upload state from Project Config
  - `_save_gemini_state_to_config()` - Save upload state to Project Config
  - Supports PDF, HTML, and TXT attachments
  - Creates numbered Research Report notes in Zotero
  - Free storage and embedding; $0.15 per 1M tokens for indexing
  - Smart upload: Only uploads on first run or with --force flag

**`zr_cleanup.py`** - Cleanup Workflow (Delete Projects & Summary Notes)
- `ZoteroResearcherCleaner` class (inherits from `ZoteroResearcherBase`)
  - `cleanup_project()` - Delete specific project subcollection and summary notes
  - `cleanup_all_projects()` - Delete ALL ZResearcher data in collection
  - `is_general_summary_note()` - Identify general summary notes (with optional project filter)
  - `find_general_summary_notes_for_project()` - Find summaries for specific project (both standalone and child notes)
  - `find_all_general_summary_notes()` - Find all summary notes in collection (both standalone and child notes)
  - `find_all_project_subcollections()` - Find all ZResearcher subcollections
  - `delete_gemini_files_for_project()` - Delete uploaded Gemini files for project
  - `count_items_in_collection()` - Count items by type (notes/files/items)
  - `preview_cleanup()` - Display preview of what will be deleted
  - `confirm_cleanup()` - Ask user for confirmation
  - `delete_collection_recursive()` - Delete collection and all contents
  - Supports dry-run mode (--dry-run) for safe previewing
  - Supports skip-confirmation mode (--yes) for scripting
  - Continues cleanup even if individual deletions fail
  - Reports detailed summary of deleted items and errors
  - Deletes child summary notes attached to items (created by --build-summaries)
  - Deletes Gemini files uploaded to Google File API

### Legacy Modules (Deprecated - see `/old/`)

**`old/extract_html.py`** - Simple HTML-to-Markdown extraction (superseded by ZoteroResearcher)

**`old/summarize_sources.py`** - Basic source summarization (superseded by ZoteroResearcher)

### LLM Module: `src/llm_extractor.py`

The `LLMExtractor` class provides AI-powered content polishing:

**Methods:**
- `__init__()` - Initializes Anthropic client with API key and model selection
- `polish_markdown()` - **PRIMARY** - Polishes Trafilatura-extracted markdown for better formatting
- `extract_article_markdown()` - Legacy method for direct HTML extraction (kept for compatibility)
- `preprocess_html()` - Removes scripts, styles, and non-content elements before sending to LLM
- `set_model()` - Change the Claude model (e.g., claude-haiku-4-5, claude-3-5-sonnet)

**Key Features:**
- Polishes Trafilatura output for improved formatting and readability
- Fixes markdown inconsistencies and structural issues
- Preserves all content and links from original extraction
- Uses Claude Haiku 4.5 by default for cost efficiency
- Handles content of any size (works with already-extracted markdown)

### Utility Module: `src/zotero_diagnose.py`

Diagnostic tool for troubleshooting Zotero connections and library access. Provides CLI for testing API connectivity and group membership.

### Research Module: ZoteroResearcher (Modular Architecture)

**See "ZoteroResearcher Modular Architecture" section above for detailed module breakdown.**

The ZoteroResearcher tool uses a **two-phase workflow** with **project-based organization**:

**Phase 1 - Build Summaries (`--build-summaries`):**
- Pre-process all sources with project-aware summaries
- Extract metadata (authors, date, publication, type, URL)
- Generate context-aware summaries informed by project overview
- Assign relevant tags from user-provided list
- Create structured "General Summary" notes in Zotero
- Run once per project, reuse across multiple queries
- Uses parallel LLM processing for efficiency

**Phase 2 - Query (`--query-summary`):**
- Load research brief from Zotero notes
- Parse pre-built summaries with metadata and tags
- Evaluate relevance using metadata + tags + summary content (parallel processing)
- Rank sources by relevance score
- Generate detailed targeted summaries for relevant sources (parallel processing)
- Output professional HTML report
- Smart storage: reports <1MB as notes, >1MB as files with stub notes

**Key Features:**
- Project-based organization (multiple projects per collection)
- Two-phase workflow: build once, query multiple times
- Context-aware summaries informed by project overview
- Tag-based categorization from user-defined taxonomy
- Rich metadata extraction from Zotero API
- Relevance evaluation using metadata + tags + summary
- Professional HTML reports with metadata and tag badges
- Parallel LLM processing for speed and efficiency
- Cost-efficient: expensive summarization separate from cheap relevance checks

**LLM Model Strategy:**
- **Claude Haiku 4.5** for Phase 1 general summaries (cost-efficient)
- **Claude Haiku 4.5** for relevance evaluation (fast, cheap)
- **Claude Haiku 4.5** for detailed targeted summaries by default (cost-efficient)
- **Claude Sonnet 4.5** for detailed targeted summaries with Project Config override (production quality)

**Structured Note Format:**
```
General Summary

## Metadata
- **Title**: <title>
- **Authors**: <authors>
- **Date**: <date>
- **Publication**: <publication>
- **Type**: <document type determined by LLM>
- **URL**: <url>

## Tags
<comma-separated tags>

## Summary
<summary text>

---
Created: <timestamp>
Project: <project name>
```

**Zotero-Native Workflow (Project-Based):**

*Initialization (run once per project):*
1. Run `--init-collection --collection KEY --project "PROJECT_NAME"`
2. Creates project-specific subcollection: `【ZResearcher: PROJECT_NAME】`
3. Creates four template notes in the subcollection:
   - **【Project Overview: PROJECT_NAME】**: Describe research project and goals
   - **【Research Tags: PROJECT_NAME】**: Tag list (one per line)
   - **【Research Brief: PROJECT_NAME】**: Research question/brief
   - **【Project Config: PROJECT_NAME】**: Optional performance & LLM tuning
4. Edit template notes in Zotero (remove [TODO: markers)

*Phase 1 - Build Summaries:*
1. Run `--build-summaries --collection KEY --project "PROJECT_NAME"`
2. Load project overview, tags, and config from Zotero notes
3. For each source in collection:
   - Extract metadata from Zotero API
   - Get source content (HTML/PDF/URL)
   - Generate context-aware summary with LLM (parallel processing)
   - Assign relevant tags from provided list
   - Identify document type (LLM)
   - Create structured "General Summary" note in Zotero
4. Skip existing summaries unless `--force` flag used

*Phase 2 - Query Summary:*
1. Run `--query-summary --collection KEY --project "PROJECT_NAME"`
2. Load research brief and config from Zotero notes
3. For each source in collection:
   - Load and parse "General Summary" note
   - Extract metadata, tags, and summary
   - Evaluate relevance using metadata + tags + summary (parallel processing)
   - If score ≥ threshold: add to relevant sources list
4. Rank relevant sources by score
5. Generate detailed targeted summaries with quotes (parallel processing)
6. Generate HTML report with LLM-generated title
7. **Smart storage:**
   - If report <1MB: Create full note in project subcollection
   - If report >1MB: Save as HTML file + create stub note with file location

**Benefits of Two-Phase Approach:**
- **Efficiency**: Build summaries once, query many times
- **Context-Aware**: Summaries informed by project overview
- **Better Relevance**: Tags help LLM evaluate topical alignment
- **Metadata Rich**: Display source provenance and authority
- **Flexibility**: Run multiple queries against same summary set
- **Cost Optimization**: ~90% cost reduction by separating phases

**Zotero-Native Configuration (Template Notes):**

The `--init-collection` command creates a "ZoteroResearcher" subcollection with three template notes:

1. **Project Overview** - Template structure:
```
[TODO: Replace this template with your project description]

Describe your research project, goals, and key areas of interest.
This context will inform the general summaries created for each source.

Example:
This project examines the impact of artificial intelligence on
software development practices. Key areas include: code generation
tools, automated testing, productivity metrics, and ethical
considerations. The research will inform a technical report for
software engineering managers.

---
Template created by ZoteroResearcher
Edit this note before running --build-summaries
```

2. **Research Tags** - Template structure:
```
[TODO: Replace with your research tags, one per line]

Example tags:
artificial-intelligence
software-development
code-generation
automated-testing
productivity-metrics
ethics

---
Template created by ZoteroResearcher
Edit this note before running --build-summaries
```

3. **Research Brief** - Template structure:
```
[TODO: Replace this template with your research question]

Describe the specific research question or brief you want to answer.
This will be used to evaluate relevance of sources and generate targeted summaries.

Example:
What are the current challenges and best practices for integrating
AI-powered code generation tools into enterprise software development
workflows? Focus on adoption barriers, productivity impacts, and
quality assurance approaches.

---
Template created by ZoteroResearcher
Edit this note before running --query-summary
```

**Template Validation:**
- The tool checks for `[TODO:` markers when loading configuration
- If markers are found, it will refuse to run and prompt you to edit the notes
- This ensures you don't accidentally run with placeholder templates

**Inherits from:** `ZoteroBaseProcessor` (shares collection/attachment/note handling with other modules)

### Base Module: `src/zotero_base.py`

The `ZoteroBaseProcessor` class provides shared functionality for all processors:

**Collection & Item Management:**
- `list_collections()` / `print_collections()` - Collection management
- `get_collection_items()` - Retrieves top-level items from collection
- `get_item_attachments()` - Fetches child attachments
- `get_subcollection()` - Get subcollection by name within parent collection
- `create_subcollection()` - Create subcollection inside parent collection

**Attachment & Content:**
- `is_html_attachment()` / `is_pdf_attachment()` - Content type detection
- `download_attachment()` - Downloads attachment content from Zotero

**Note Management:**
- `create_note()` - Creates child note attached to item (with markdown conversion)
- `create_standalone_note()` - Creates standalone note in collection (with markdown conversion)
- `get_collection_notes()` - Get all standalone notes in collection
- `has_note_with_prefix()` / `get_note_with_prefix()` - Note checking and retrieval
- `get_note_title_from_html()` - Extract title from note HTML (first h1 or first line)
- `extract_text_from_note_html()` - Extract plain text from note HTML
- `markdown_to_html()` - Convert markdown to HTML for Zotero notes

**Used by:**
- `ZoteroResearcherBase` (zr_common.py) - Base class for all ZoteroResearcher modules
- `ZoteroSourceSummarizer` (old/summarize_sources.py) - Legacy, deprecated

### Data Flow (ZoteroResearcher)

**Initialization:**
1. Load Zotero credentials and LLM API key from environment variables
2. Validate project name and collection key
3. Route to appropriate workflow module (Init/Build/Query)

**Phase 1 - Build Summaries:**
1. Load project overview, tags, and config from Zotero subcollection notes
2. For each item in collection:
   - Skip if already a note/attachment
   - Check for existing project-specific summary (skip unless `--force`)
   - Extract metadata from Zotero API
   - Get source content using priority: Markdown Extract → HTML → PDF → URL
   - Build batch of LLM requests
3. Process batch in parallel with configured worker count
4. Create structured "General Summary" notes in Zotero with metadata, tags, and summary

**Phase 2 - Query Summary:**
1. Load research brief and config from Zotero subcollection notes
2. For each item in collection:
   - Load and parse existing "General Summary" note
   - Extract metadata, tags, and summary
   - Build batch of relevance evaluation requests
3. Process relevance evaluations in parallel
4. Filter sources by relevance threshold
5. Rank sources by relevance score
6. Build batch of targeted summary requests for relevant sources
7. Process targeted summaries in parallel
8. Generate HTML report with LLM-generated title
9. Smart storage: Save as note if <1MB, otherwise save as file with stub note

### Content Retrieval Priority (ZoteroResearcher)
1. Existing "Markdown Extract" note (from legacy tools)
2. HTML snapshot (Zotero stored snapshot)
3. PDF attachment (PyMuPDF extraction)
4. URL fetch (for webpage items without snapshots)

### Content Extraction Methods (Shared across all tools)

**Trafilatura Extraction (default):**
- Purpose-built for extracting main article content from web pages
- Intelligently identifies and extracts article content
- Handles documents of any size
- Outputs clean markdown directly
- Free, fast, and accurate for most web pages
- **Default method for all extractions**

**LLM Polish (--use-llm):**
- Applies Claude API to polish Trafilatura output
- Improves markdown formatting and structure
- Fixes inconsistencies and artifacts
- Enhances readability
- Requires `ANTHROPIC_API_KEY` environment variable
- Works with content of any size (since it polishes extracted markdown, not raw HTML)

**BeautifulSoup Extraction (fallback only):**
- Rule-based HTML cleaning
- Removes script, style, nav, footer, header tags
- Converts to Markdown using html2text
- Used only as fallback when Trafilatura fails
- Can be disabled with `--no-fallback`

## Configuration & Environment

### Environment Variables (`.env`)
```
# Zotero Configuration
ZOTERO_LIBRARY_ID=<library_id>      # User or group ID
ZOTERO_LIBRARY_TYPE=user|group      # Type of library
ZOTERO_API_KEY=<api_key>            # Zotero API authentication key
ZOTERO_COLLECTION_KEY=<collection>  # Collection to process

# LLM Configuration
ANTHROPIC_API_KEY=<api_key>         # Anthropic API key for Claude (required for most features)
GEMINI_API_KEY=<api_key>            # Google Gemini API key (required for --file-search)
```

### Key Dependencies
- **pyzotero** - Zotero API client
- **trafilatura** - Main content extraction from web pages (primary extraction method)
- **beautifulsoup4** - HTML parsing and cleaning (fallback only)
- **html2text** - HTML to Markdown conversion (fallback only)
- **requests** - HTTP library for URL fetching
- **python-dotenv** - Environment variable management
- **anthropic** - Anthropic Claude API client (required for most features)
- **google-genai** - Google Gemini API client v1.x (required for --file-search)

### Python Version
- **Required:** Python 3.12+
- Use `.python-version` file for version management

## Important Implementation Details

### API Rate Limiting
The code includes 1-second delays between API calls to respect Zotero's rate limits. This is implemented in the collection processing loop.

### Duplicate Prevention
The `--force` flag controls whether to re-extract markdown notes. The code checks for existing "Markdown Extract" notes to avoid duplicates. This prevents the same content from being extracted multiple times (commit 137431e).

### Library Type Support
Supports both user libraries and group libraries. The `ZOTERO_LIBRARY_TYPE` environment variable determines which type is used (commit b1cdc8d added group support).

### PDF Attachment Handling
Items with PDF attachments are automatically skipped for HTML extraction. This prevents unnecessary webpage fetching when a PDF version already exists. The logic checks all child attachments for PDF files (by content type or file extension) before attempting any HTML extraction.

### Webpage Without Snapshot Handling
The tool can extract content from webpage items even without HTML snapshots:
- If an item has **no child items** and is a `webpage` type with a URL, content is fetched directly from the URL
- If an item has **child items but no HTML attachments** (e.g., only text files) and is a `webpage` type, content is fetched from the parent item's URL
- This enables extraction from webpages added to Zotero without saving snapshots
- PDF attachments take priority - if a PDF exists, webpage extraction is skipped

### HTML Processing Pipelines

**Trafilatura Pipeline (default):**
1. Trafilatura analyzes HTML structure
2. Identifies main content area using heuristics
3. Extracts article content (text, headings, links, tables)
4. Removes ads, navigation, footers, and other non-content
5. Outputs clean Markdown directly
6. Handles documents of any size

**Trafilatura + LLM Polish Pipeline (--use-llm):**
1. Trafilatura extracts main content to Markdown
2. Send extracted Markdown to Claude API
3. Claude polishes formatting and structure
4. Claude fixes any extraction artifacts
5. Returns enhanced Markdown
6. Fallback to unpolished Trafilatura output if LLM fails

**BeautifulSoup Pipeline (fallback only):**
1. Parse HTML with BeautifulSoup
2. Remove script, style, nav, footer, and header tags
3. Extract text content
4. Convert to Markdown using html2text
5. Used only when Trafilatura fails

## Testing & Validation

Currently no tests are implemented. When adding tests:
- Mock Zotero API responses using pyzotero fixtures
- Test HTML extraction with various document structures
- Validate Markdown conversion accuracy
- Test environment variable handling and credential validation
- Test edge cases: missing attachments, invalid URLs, malformed HTML

## Known Limitations & Future Work

- No linting or code formatting tools configured
- No automated test suite
- Documentation is minimal (only basic README)
- No CI/CD pipeline configured
- Group collection support was added recently (commit b1cdc8d) - validate thoroughly
