# Zotero Summarizer

A Python tool suite for sophisticated research workflows with Zotero libraries using AI-powered summarization and analysis.

## Primary Tool: ZoteroResearcher

**ZoteroResearcher** is an advanced research assistant that analyzes sources based on a research brief, ranks them by relevance, and generates targeted summaries with key quotes and statistics. It uses a **three-phase, project-based workflow** with all configuration and outputs stored in Zotero:

- **Phase 1 (Build)**: Generate project-aware summaries with metadata and tags for all sources
- **Phase 2 (Query)**: Evaluate relevance against a research brief and generate targeted summaries
- **Phase 3 (Synthesis)**: Automatically generate a meta-analysis synthesis of the research findings

### Key Features

- **Project-based organization** - Multiple research projects per collection
- **Zotero-native workflow** - All config and outputs stored in Zotero (no external files)
- **Parallel LLM processing** - Fast batch processing with configurable worker counts
- **Smart storage** - Reports <1MB saved as notes, >1MB as files with stub notes
- **Context-aware summaries** - Informed by your project overview and research goals
- **Tag-based categorization** - User-defined taxonomy for organizing findings
- **Rich metadata extraction** - Authors, dates, publications, document types, URLs
- **File Search (RAG)** - Google Gemini-powered semantic search across your collection
- **Research synthesis** - Automated meta-analysis with Claude Sonnet
- **Cleanup tools** - Delete projects and summaries with dry-run preview

### LLM Model Strategy

- **Claude Haiku 4.5** - Phase 1 general summaries, relevance evaluation, and targeted summaries (cost-efficient, default)
- **Claude Sonnet 4.5** - Available for targeted summaries via Project Config override (production quality)
- **Claude Sonnet 4.5** - Always used for Phase 3 research synthesis (high-quality meta-analysis)
- **Google Gemini** - File Search (RAG) for semantic search across collections

## Quick Start

### 1. Setup

```bash
# Create and activate virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file in the project root:

```bash
# Zotero Configuration
ZOTERO_LIBRARY_ID=your_library_id
ZOTERO_LIBRARY_TYPE=user              # or 'group' for group libraries
ZOTERO_API_KEY=your_zotero_api_key

# LLM Configuration
ANTHROPIC_API_KEY=your_anthropic_key  # Required for most features
GEMINI_API_KEY=your_gemini_key        # Required for --file-search only
```

**Important:** Do not use quotes around values in `.env` files.

### 3. Basic Workflow

```bash
# Step 1: List available collections
uv run python -m src.zresearcher --list-collections

# Step 2: Initialize a project (creates template notes in Zotero)
uv run python -m src.zresearcher --init-collection \
    --collection COLLECTION_KEY --project "My Research Project"

# Step 3: Edit the template notes in Zotero
# Navigate to the 【ZResearcher: My Research Project】 subcollection
# Edit these four notes:
#   - 【Project Overview: My Research Project】
#   - 【Research Tags: My Research Project】
#   - 【Research Brief: My Research Project】
#   - 【Project Config: My Research Project】 (optional)

# Step 4: (Optional) Organize sources to ensure all items have attachments
uv run python -m src.zresearcher --organize-sources \
    --collection COLLECTION_KEY

# Step 5: Build general summaries (Phase 1)
uv run python -m src.zresearcher --build-summaries \
    --collection COLLECTION_KEY --project "My Research Project"

# Step 6: Run query and generate report (Phase 2 + 3)
uv run python -m src.zresearcher --query-summary \
    --collection COLLECTION_KEY --project "My Research Project"
```

The tool will:
- Load your research brief from Zotero
- Evaluate source relevance using metadata, tags, and summaries
- Generate detailed targeted summaries for relevant sources
- Create an HTML research report (saved as note or file based on size)
- Automatically generate a research synthesis (meta-analysis)

## Advanced Features

### File Search (Gemini RAG)

Semantic search across your entire collection using Google Gemini File Search:

```bash
# Step 1: Upload files to Gemini (one-time setup per project)
uv run python -m src.zresearcher --upload-files \
    --collection COLLECTION_KEY --project "My Research Project"

# Step 2: Edit the Query Request note in Zotero
# Navigate to: 【ZResearcher: My Research Project】/【Query Request】
# Write your search query

# Step 3: Run File Search
uv run python -m src.zresearcher --file-search \
    --collection COLLECTION_KEY --project "My Research Project"
```

**Features:**
- Supports PDF, HTML, and TXT attachments
- Incremental uploads (only new files uploaded on subsequent runs)
- Automatically extracts grounding sources from results
- LLM-generated report titles based on your query
- Free storage and embedding; low cost for indexing ($0.15 per 1M tokens)

**Force rebuild:**
```bash
# Delete existing file search store and re-upload all files
uv run python -m src.zresearcher --upload-files \
    --collection COLLECTION_KEY --project "My Research Project" --force
```

### Cleanup Projects

Remove projects and summaries with dry-run preview:

```bash
# Preview what will be deleted (safe, no changes made)
uv run python -m src.zresearcher --cleanup-project \
    --collection COLLECTION_KEY --project "My Research Project" --dry-run

# Delete a specific project (includes subcollection, notes, and Gemini files)
uv run python -m src.zresearcher --cleanup-project \
    --collection COLLECTION_KEY --project "My Research Project"

# Skip confirmation prompt (useful for scripts)
uv run python -m src.zresearcher --cleanup-project \
    --collection COLLECTION_KEY --project "My Research Project" --yes

# Clean up ALL projects in a collection (use with caution!)
uv run python -m src.zresearcher --cleanup-collection \
    --collection COLLECTION_KEY --dry-run
```

### List Projects

View all existing projects in a collection:

```bash
uv run python -m src.zresearcher --list-projects \
    --collection COLLECTION_KEY
```

### Rebuild Summaries

Force rebuild existing summaries:

```bash
uv run python -m src.zresearcher --build-summaries \
    --collection COLLECTION_KEY --project "My Research Project" --force
```

### Verbose Logging

Enable detailed logging for troubleshooting:

```bash
uv run python -m src.zresearcher --query-summary \
    --collection COLLECTION_KEY --project "My Research Project" --verbose
```

## Template Notes Structure

When you run `--init-collection`, four template notes are created in the project subcollection:

### 1. Project Overview
Describes your research project and goals. This context informs the general summaries created for each source.

```markdown
Describe your research project, goals, and key areas of interest.

Example:
This project examines the impact of artificial intelligence on
software development practices. Key areas include: code generation
tools, automated testing, productivity metrics, and ethical
considerations.
```

### 2. Research Tags
Tag taxonomy (one per line) for categorizing sources:

```markdown
artificial-intelligence
software-development
code-generation
automated-testing
productivity-metrics
ethics
```

### 3. Research Brief
Your specific research question or brief:

```markdown
What are the current challenges and best practices for integrating
AI-powered code generation tools into enterprise software development
workflows? Focus on adoption barriers, productivity impacts, and
quality assurance approaches.
```

### 4. Project Config (Optional)
Performance tuning and LLM settings:

```yaml
# Worker configuration for parallel processing
max_workers=10              # Number of parallel LLM requests (default: 10)

# LLM model selection
use_sonnet=true             # Use Claude Sonnet for targeted summaries (default: false, uses Haiku)

# Synthesis configuration
generate_synthesis=true     # Auto-generate research synthesis after query (default: true)

# Relevance threshold
min_relevance_score=6       # Minimum score for inclusion in report (1-10, default: 6)
```

## Three-Phase Workflow Explained

### Phase 1: Build Summaries (`--build-summaries`)

Pre-processes all sources with project-aware summaries:

1. Loads project overview, tags, and config from Zotero
2. For each source:
   - Extracts metadata (authors, date, publication, URL)
   - Gets content (HTML/PDF/URL priority)
   - Generates context-aware summary using project overview
   - Assigns relevant tags from your taxonomy
   - Identifies document type (article, report, book, etc.)
3. Creates structured "General Summary" notes in Zotero
4. Uses parallel processing for efficiency

**Run once per project, reuse across multiple queries**

### Phase 2: Query Summary (`--query-summary`)

Evaluates relevance and generates targeted summaries:

1. Loads research brief from Zotero
2. Parses existing general summaries
3. Evaluates relevance using metadata + tags + summary (parallel processing)
4. Ranks sources by relevance score
5. Generates detailed targeted summaries for relevant sources (parallel processing)
6. Creates professional HTML report with LLM-generated title
7. Smart storage: <1MB as note, >1MB as file with stub note

**Run multiple times with different research briefs**

### Phase 3: Research Synthesis (Automatic)

Generates comprehensive meta-analysis after Phase 2:

1. Automatically triggered after creating research report (enabled by default)
2. Loads project overview and research brief
3. Analyzes the full research report
4. Uses Claude Sonnet for high-quality synthesis
5. Generates comprehensive analysis including:
   - Executive Summary
   - Main Themes and Patterns
   - Key Findings (with source citations)
   - Implications and Insights
   - Recommendations
   - Research Gaps and Future Directions
6. Saves as "Research Synthesis: {title}" note

**Can be disabled** by setting `generate_synthesis=false` in Project Config

## Benefits of Project-Based Approach

- **Efficiency**: Build summaries once, query many times
- **Context-Aware**: Summaries informed by project overview
- **Better Relevance**: Tags help LLM evaluate topical alignment
- **Metadata Rich**: Display source provenance and authority
- **Flexibility**: Run multiple queries against same summary set
- **Cost Optimization**: ~90% cost reduction by separating phases
- **Multiple Projects**: Organize different research initiatives in the same collection

## Content Extraction

### Priority Order

1. Existing "Markdown Extract" note (from legacy tools)
2. HTML snapshot (Zotero stored snapshot)
3. PDF attachment (PyMuPDF extraction)
4. URL fetch (for webpage items without snapshots)

### Extraction Methods

- **Trafilatura**: Purpose-built for web content extraction (primary method)
- **PyMuPDF**: PDF text extraction with layout preservation
- **BeautifulSoup**: HTML fallback when Trafilatura fails
- **LLM Polish**: Optional Claude-powered markdown enhancement

## Project Structure

```
src/
├── zresearcher.py              # CLI entry point & routing
├── zr_common.py                # Base class & shared utilities
├── zr_init.py                  # Collection initialization workflow
├── zr_organize_sources.py      # Source organization workflow
├── zr_build.py                 # Phase 1: Build summaries workflow
├── zr_query.py                 # Phase 2: Query & report generation workflow
├── zr_file_search.py           # File Search: Gemini RAG integration
├── zr_cleanup.py               # Cleanup: Delete projects & summary notes
├── zr_llm_client.py            # Centralized LLM API client
├── zr_prompts.py               # Prompt templates
├── zotero_base.py              # Base Zotero API functionality
├── llm_extractor.py            # LLM-powered content extraction
└── zotero_diagnose.py          # Diagnostic utility
```

## Requirements

- **Python 3.12+**
- **Zotero library** (user or group)
- **Anthropic API key** (for Claude - required for most features)
- **Google Gemini API key** (optional, only for File Search)

### Key Dependencies

- **pyzotero** - Zotero API client
- **trafilatura** - Web content extraction
- **anthropic** - Claude API client
- **google-genai** - Gemini API client (v1.x)
- **PyMuPDF** - PDF text extraction
- **beautifulsoup4** - HTML parsing (fallback)
- **requests** - HTTP library

## Legacy Tools

The following tools have been deprecated and moved to `/old/`:

- `extract_html.py` - Simple HTML-to-Markdown extraction
- `summarize_sources.py` - Basic source summarization

These are superseded by the more powerful ZoteroResearcher tool.

## Documentation

See **[CLAUDE.md](CLAUDE.md)** for comprehensive documentation including:
- Detailed command reference
- Code architecture (modular design)
- Configuration options
- Implementation details
- API rate limiting
- Testing guidelines

## Diagnostic Tool

Troubleshoot Zotero connections:

```bash
# Test user library
uv run python -m src.zotero_diagnose --user

# Test group library
uv run python -m src.zotero_diagnose --group GROUP_ID
```

## Contributing

This project uses **`uv`** for Python package management. All commands should be run with `uv run` to ensure proper dependency resolution.

## License

[Add your license information here]
