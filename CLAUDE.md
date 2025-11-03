# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Zotero Summarizer** is a Python tool that automates the extraction of HTML content from Zotero library items (web snapshots) and converts them to Markdown notes. It accesses both user and group Zotero libraries via the Zotero API, identifies HTML attachments, converts them to readable Markdown format, and creates notes attached to the original items.

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
python main.py

# List available collections without processing
python extract_html.py --list-collections

# Force re-extraction (even if markdown notes exist)
python extract_html.py --force

# Use LLM (Claude API) for extraction instead of BeautifulSoup
python extract_html.py --use-llm

# Use LLM without fallback to BeautifulSoup (fail if LLM fails)
python extract_html.py --use-llm --no-fallback

# Run diagnostic utility for troubleshooting
python zotero_diagnose.py --user
python zotero_diagnose.py --group GROUP_ID
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
- `has_markdown_extract_note()` - Checks if item already has extracted markdown
- `download_attachment()` - Retrieves attachment from Zotero storage
- `fetch_url_content()` - Fetches HTML from a URL (fallback)
- `extract_text_from_html()` - Parses and cleans HTML using BeautifulSoup
- `html_to_markdown()` - Converts HTML to Markdown format (BeautifulSoup method)
- `extract_content()` - **NEW** - Unified extraction method supporting both LLM and BeautifulSoup with configurable fallback

**Main Processing:**
- `process_collection()` - Orchestrates the extraction workflow

### LLM Module: `zotero_summarizer/llm_extractor.py`

The `LLMExtractor` class provides AI-powered content extraction:

**Methods:**
- `__init__()` - Initializes Anthropic client with API key and model selection
- `extract_article_markdown()` - Uses Claude API to intelligently extract article content from HTML
- `set_model()` - Change the Claude model (e.g., claude-3-5-haiku, claude-3-5-sonnet)

**Key Features:**
- Intelligently identifies main article content
- Removes navigation, ads, sidebars, and other non-content elements
- Preserves article structure, headings, links, and formatting
- Direct conversion to clean Markdown
- More accurate than BeautifulSoup for complex web pages

### Utility Module: `zotero_summarizer/zotero_diagnose.py`

Diagnostic tool for troubleshooting Zotero connections and library access. Provides CLI for testing API connectivity and group membership.

### Data Flow

1. Load Zotero credentials and optional LLM API key from environment variables
2. Query Zotero API for collections (if `--list-collections` flag)
3. For each item in the target collection:
   - Skip if already a note/attachment
   - Check if markdown extract note already exists (skip unless `--force`)
   - Retrieve HTML attachments
   - For each HTML file:
     - Try downloading from Zotero snapshot first
     - Fall back to fetching from URL
     - **Extract content using selected method:**
       - **If `--use-llm` flag:** Use Claude API for intelligent extraction
       - **If LLM fails and fallback enabled:** Fall back to BeautifulSoup
       - **Default:** Use BeautifulSoup method
     - Create note via Zotero API
     - Rate limit (1-second delay between API calls)

### Content Retrieval Priority
1. Zotero snapshot (local file in library)
2. Direct URL fetch (HTTP request to attachment URL)

### Extraction Methods

**LLM Extraction (--use-llm):**
- Uses Claude API to intelligently identify article content
- Removes ads, navigation, and other non-content elements automatically
- Better quality for complex web pages
- Requires `ANTHROPIC_API_KEY` environment variable
- Supports fallback to BeautifulSoup (default) or fail-fast with `--no-fallback`

**BeautifulSoup Extraction (default):**
- Rule-based HTML cleaning
- Removes script, style, nav, footer, header tags
- Converts to Markdown using html2text
- Free and fast but less accurate for complex layouts

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
- **beautifulsoup4** - HTML parsing and cleaning
- **html2text** - HTML to Markdown conversion
- **requests** - HTTP library for URL fetching
- **python-dotenv** - Environment variable management
- **anthropic** - Anthropic Claude API client (optional, for LLM extraction)

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

### HTML Processing Pipelines

**LLM Pipeline (--use-llm):**
1. Send raw HTML to Claude API with extraction prompt
2. Claude intelligently identifies main article content
3. Claude removes non-content elements (ads, navigation, etc.)
4. Claude converts directly to clean Markdown
5. Fallback to BeautifulSoup pipeline if enabled and LLM fails

**BeautifulSoup Pipeline (default):**
1. Parse HTML with BeautifulSoup
2. Remove script, style, nav, footer, and header tags
3. Extract text content
4. Convert to Markdown using html2text
5. Preserve links; ignore images and data URIs

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
