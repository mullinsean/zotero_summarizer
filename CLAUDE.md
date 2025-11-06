# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Zotero Summarizer** is a Python tool that automates the extraction of HTML content from Zotero library items (web snapshots) and converts them to Markdown notes. It accesses both user and group Zotero libraries via the Zotero API, identifies HTML attachments, converts them to readable Markdown format, and creates notes attached to the original items.

The tool includes a **Research Assistant** feature that analyzes sources based on a research brief, ranks them by relevance, and generates targeted summaries with key quotes and statistics. The Research Assistant supports two workflows:

- **Zotero-native workflow**: All configuration and outputs stored in Zotero (recommended for end-users)
- **File-based workflow**: Configuration in text files, outputs as HTML files (useful for debugging)

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
```bash
# Run main entry point
uv run python main.py

# List available collections without processing
uv run python extract_html.py --list-collections

# Force re-extraction (even if markdown notes exist)
uv run python extract_html.py --force

# Use LLM polish (applies Claude polish to Trafilatura output)
uv run python extract_html.py --use-llm

# Use LLM polish without fallback (fail if LLM polish fails)
uv run python extract_html.py --use-llm --no-fallback

# Enable verbose mode to see all child items
uv run python extract_html.py --verbose

# Run diagnostic utility for troubleshooting
uv run python zotero_diagnose.py --user
uv run python zotero_diagnose.py --group GROUP_ID

# Summarize sources in a collection
uv run python summarize_sources.py --collection COLLECTION_KEY
uv run python summarize_sources.py --verbose

# Research Assistant - Zotero-native workflow (RECOMMENDED)
# All configuration and reports stored in Zotero

# Step 0: List collections
uv run python researcher.py --list-collections

# Step 1: Initialize collection (creates template notes in Zotero)
uv run python researcher.py --init-collection --collection COLLECTION_KEY

# Step 2: Edit the three template notes in Zotero:
#   - Project Overview (describe your research project)
#   - Research Tags (one tag per line)
#   - Research Brief (your research question)

# Step 3: Build general summaries (loads config from Zotero)
uv run python researcher.py --build-summaries --collection COLLECTION_KEY
uv run python researcher.py --build-summaries --collection COLLECTION_KEY --force  # Rebuild existing

# Step 4: Run query (loads brief from Zotero, stores report as note)
uv run python researcher.py --query-summary --collection COLLECTION_KEY
uv run python researcher.py --query-summary --collection COLLECTION_KEY --threshold 7
uv run python researcher.py --query-summary --collection COLLECTION_KEY --use-sonnet  # High quality mode

# Research Assistant - File-based workflow (for debugging)
# Configuration from files, reports as HTML files

# Phase 1: Build general summaries (provide files)
uv run python researcher.py --build-summaries --collection COLLECTION_KEY \
    --project-overview project_overview.txt --tags tags.txt
uv run python researcher.py --build-summaries --collection COLLECTION_KEY \
    --project-overview project_overview.txt --tags tags.txt --force  # Rebuild existing

# Phase 2: Query with research briefs (provide brief file, output HTML)
uv run python researcher.py --query --collection COLLECTION_KEY --brief research_brief.txt
uv run python researcher.py --query --collection COLLECTION_KEY --brief research_brief.txt --threshold 7
uv run python researcher.py --query --collection COLLECTION_KEY --brief research_brief.txt --max-sources 100
uv run python researcher.py --query --collection COLLECTION_KEY --brief research_brief.txt --use-sonnet
```

### Linting & Code Quality
No linting tools currently configured. Future setup should include tools like `black`, `ruff`, or `pylint`.

### Testing
No test framework currently configured. Tests should be added in `/tests/` directory using `pytest` or `unittest`.

## Code Architecture

### Core Module: `zotero_summarizer/extract_html.py`

The `ZoteroHTMLExtractor` class is the central component orchestrating all functionality:

**API Interaction Methods:**
- `__init__()` - Initializes with Zotero credentials, configures HTML-to-Markdown converter, and optionally initializes LLM extractor
- `list_collections()` - Retrieves available collections
- `get_collection_items()` - Fetches items from a specific collection
- `get_item_attachments()` - Gets child attachments for an item
- `create_note()` - Creates markdown notes in Zotero

**HTML Processing Methods:**
- `is_html_attachment()` - Identifies HTML files
- `is_webpage_item()` - Checks if parent item is a webpage type with a URL
- `has_pdf_attachment()` - Checks if any attachment is a PDF file
- `has_markdown_extract_note()` - Checks if item already has extracted markdown
- `download_attachment()` - Retrieves attachment from Zotero storage
- `fetch_url_content()` - Fetches HTML from a URL (fallback)
- `trafilatura_extract()` - **DEFAULT** - Extracts main article content using Trafilatura
- `extract_text_from_html()` - Parses and cleans HTML using BeautifulSoup (fallback)
- `html_to_markdown()` - Converts HTML to Markdown format (BeautifulSoup fallback method)
- `extract_content()` - Unified extraction method: Trafilatura → optional LLM polish → fallback to BeautifulSoup

**Main Processing:**
- `process_collection()` - Orchestrates the extraction workflow

### LLM Module: `zotero_summarizer/llm_extractor.py`

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

### Utility Module: `zotero_summarizer/zotero_diagnose.py`

Diagnostic tool for troubleshooting Zotero connections and library access. Provides CLI for testing API connectivity and group membership.

### Research Module: `zotero_summarizer/researcher.py`

The `ZoteroResearcher` class performs sophisticated research analysis on Zotero collections using a **two-phase workflow** with **dual-mode support**:

**Architecture: Dual-Mode Support**

The tool supports two workflows:

1. **Zotero-native workflow** (RECOMMENDED):
   - All configuration stored as notes in a "ZoteroResearcher" subcollection
   - Research reports stored as Zotero notes (or HTML file if >1MB)
   - No external files required
   - Best for end-users working entirely within Zotero

2. **File-based workflow**:
   - Configuration from text files (project_overview.txt, tags.txt, research_brief.txt)
   - Reports saved as HTML files
   - Useful for debugging and batch processing

**Architecture: Two-Phase Workflow**

**Phase 1 - Build Summaries (`--build-summaries`):**
- Pre-process all sources with project-aware summaries
- Extract metadata (authors, date, publication, type, URL)
- Generate context-aware summaries informed by project overview
- Assign relevant tags from user-provided list
- Create structured "General Summary" notes in Zotero
- Run once per collection, reuse across multiple queries
- **Supports both modes**: loads config from Zotero notes OR from files

**Phase 2 - Query:**
- **Zotero-native** (`--query-summary`): Loads brief from Zotero, stores report as note
- **File-based** (`--query`): Loads brief from file, outputs HTML file
- Answer specific research questions using pre-built summaries
- Parse structured summaries with metadata and tags
- Evaluate relevance using metadata, tags, and summary content
- Rank sources by relevance score
- Generate detailed targeted summaries for relevant sources
- Output professional HTML report (as note or file depending on mode)

**Key Features:**
- Two-phase workflow: build once, query multiple times
- Dual-mode: Zotero-native (no files) or file-based (debugging)
- Context-aware summaries informed by project overview
- Tag-based categorization from user-defined list
- Rich metadata extraction from Zotero API
- Relevance evaluation using metadata + tags + summary
- Professional HTML reports with metadata and tag badges
- Smart storage: reports <1MB as notes, >1MB as files with stub notes
- Cost-efficient: expensive summarization separate from cheap relevance checks

**Core Methods:**

*Initialization & Configuration:*
- `init_collection()` - Initialize collection with ZoteroResearcher subcollection and template notes

*Loaders & Extraction:*
- `load_research_brief()` - Loads research brief/question from file (file-based mode)
- `load_research_brief_from_zotero()` - Loads research brief from Zotero notes (Zotero-native mode)
- `load_project_overview()` - Loads project overview from file (file-based mode)
- `load_project_overview_from_zotero()` - Loads project overview from Zotero notes (Zotero-native mode)
- `load_tags()` - Loads tag list from file (file-based mode)
- `load_tags_from_zotero()` - Loads tags from Zotero notes (Zotero-native mode)
- `extract_metadata()` - Extracts metadata from Zotero API
- `get_source_content()` - Retrieves content with priority: Markdown Extract → HTML → PDF → URL
- `extract_text_from_html()` - Trafilatura-based HTML extraction
- `extract_text_from_pdf()` - PyMuPDF-based PDF extraction

*Phase 1 - Build:*
- `build_general_summaries()` - Main orchestration for Phase 1 (auto-detects mode)
- `create_general_summary_with_tags()` - Generates summary with tags and document type
- `format_general_summary_note()` - Creates structured note format
- `has_general_summary()` - Checks for existing summary

*Phase 2 - Query:*
- `run_query()` - Main orchestration for Phase 2 (file-based mode, outputs HTML file)
- `run_query_summary()` - Main orchestration for Phase 2 (Zotero-native mode, outputs note)
- `parse_general_summary_note()` - Parses structured note into metadata/tags/summary
- `evaluate_source_relevance()` - LLM-based relevance scoring with metadata + tags
- `rank_sources()` - Sorts sources by relevance score (descending)
- `generate_targeted_summary()` - Creates detailed research summary with quotes
- `compile_research_html()` - Builds HTML report and saves to file (file-based mode)
- `_compile_research_html_string()` - Internal method to generate HTML string without saving

**LLM Model Strategy:**
- **Claude Haiku 4.5** for Phase 1 general summaries (cost-efficient)
- **Claude Haiku 4.5** for relevance evaluation (fast, cheap)
- **Claude Haiku 4.5** for detailed targeted summaries by default (cost-efficient)
- **Claude Sonnet 4.5** for detailed targeted summaries with `--use-sonnet` flag (production quality)

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

**Zotero-Native Workflow (RECOMMENDED):**

*Initialization (run once per collection):*
1. Run `--init-collection` to create ZoteroResearcher subcollection
2. Creates three template notes:
   - **Project Overview**: Describe research project and goals
   - **Research Tags**: Tag list (one per line)
   - **Research Brief**: Research question/brief
3. Edit template notes in Zotero (remove [TODO: markers)

*Phase 1 - Build Summaries:*
1. Run `--build-summaries` (without file arguments)
2. Load project overview and tags from Zotero notes
3. For each source in collection:
   - Extract metadata from Zotero API
   - Get source content (HTML/PDF/URL)
   - Generate context-aware summary with LLM
   - Assign relevant tags from provided list
   - Identify document type (LLM)
   - Create structured "General Summary" note in Zotero
4. Skip existing summaries unless `--force` flag used

*Phase 2 - Query Summary:*
1. Run `--query-summary`
2. Load research brief from Zotero notes
3. For each source in collection:
   - Load and parse "General Summary" note
   - Extract metadata, tags, and summary
   - Evaluate relevance using metadata + tags + summary
   - If score ≥ threshold: add to relevant sources list
4. Rank relevant sources by score
5. Generate detailed targeted summaries with quotes
6. Generate HTML report
7. **Smart storage:**
   - If report <1MB: Create full note in ZoteroResearcher subcollection
   - If report >1MB: Save as HTML file + create stub note with file location

**File-Based Workflow (for debugging):**

*Phase 1 - Build Summaries:*
1. Run `--build-summaries` with `--project-overview` and `--tags` files
2. Load project overview and tags from files
3. Process sources same as Zotero-native mode
4. Create "General Summary" notes in Zotero

*Phase 2 - Query:*
1. Run `--query` with `--brief` file
2. Load research brief from file
3. Process sources same as Zotero-native mode
4. Save HTML report to file (always, regardless of size)

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

### Base Module: `zotero_summarizer/zotero_base.py`

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
- `ZoteroSourceSummarizer` (summarize_sources.py)
- `ZoteroResearcher` (researcher.py)

### Data Flow

1. Load Zotero credentials and optional LLM API key from environment variables
2. Query Zotero API for collections (if `--list-collections` flag)
3. For each item in the target collection:
   - Skip if already a note/attachment
   - Check if markdown extract note already exists (skip unless `--force`)
   - Retrieve child attachments
   - **If no child items found:**
     - Check if parent item is a webpage type with a URL
     - If yes, fetch HTML content directly from the parent item's URL
     - Process the fetched content using the extraction pipeline
     - Create note via Zotero API
     - Rate limit (1-second delay between API calls)
   - **If child items exist:**
     - **Check for PDF attachments first - if found, skip item entirely**
     - For each HTML attachment:
       - Try downloading from Zotero snapshot first
       - Fall back to fetching from URL
       - **Extract content using Trafilatura (default):**
         - Trafilatura extracts main article content
         - **If `--use-llm` flag:** Apply Claude polish to improve formatting
         - **If Trafilatura fails and fallback enabled:** Fall back to BeautifulSoup
       - Create note via Zotero API
       - Rate limit (1-second delay between API calls)
     - **If no HTML attachments found but child items exist:**
       - Check if parent item is a webpage type with a URL
       - If yes, fetch HTML content directly from the parent item's URL
       - Process the fetched content using the same extraction pipeline
       - Create note via Zotero API

### Content Retrieval Priority
1. Zotero snapshot (local file in library)
2. Direct URL fetch (HTTP request to attachment URL)
3. Parent item URL fetch (for webpage items without snapshots)

### Extraction Methods

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

# LLM Configuration (optional - for --use-llm feature)
ANTHROPIC_API_KEY=<api_key>         # Anthropic API key for Claude
```

### Key Dependencies
- **pyzotero** - Zotero API client
- **trafilatura** - Main content extraction from web pages (primary extraction method)
- **beautifulsoup4** - HTML parsing and cleaning (fallback only)
- **html2text** - HTML to Markdown conversion (fallback only)
- **requests** - HTTP library for URL fetching
- **python-dotenv** - Environment variable management
- **anthropic** - Anthropic Claude API client (optional, for LLM polish)

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
