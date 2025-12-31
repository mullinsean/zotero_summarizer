# Content Extraction

Documentation for content extraction methods used across all ZoteroResearcher tools.

## Content Retrieval Priority

When retrieving content from sources, ZoteroResearcher uses this priority order:

1. **Existing "Markdown Extract" note** (from legacy tools)
2. **HTML snapshot** (Zotero stored snapshot)
3. **PDF attachment** (PyMuPDF extraction)
4. **URL fetch** (for webpage items without snapshots)

---

## Extraction Methods

### Trafilatura Extraction (Default)

The primary extraction method for all web content.

**Characteristics:**
- Purpose-built for extracting main article content from web pages
- Intelligently identifies and extracts article content
- Handles documents of any size
- Outputs clean markdown directly
- Free, fast, and accurate for most web pages
- **Default method for all extractions**

### LLM Polish (`--use-llm`)

Optional enhancement that applies Claude API to improve extraction quality.

**Characteristics:**
- Applies Claude API to polish Trafilatura output
- Improves markdown formatting and structure
- Fixes inconsistencies and artifacts
- Enhances readability
- Requires `ANTHROPIC_API_KEY` environment variable
- Works with content of any size (since it polishes extracted markdown, not raw HTML)

### BeautifulSoup Extraction (Fallback Only)

Used only when Trafilatura fails.

**Characteristics:**
- Rule-based HTML cleaning
- Removes script, style, nav, footer, header tags
- Converts to Markdown using html2text
- Used only as fallback when Trafilatura fails
- Can be disabled with `--no-fallback`

---

## HTML Processing Pipelines

### Trafilatura Pipeline (Default)

1. Trafilatura analyzes HTML structure
2. Identifies main content area using heuristics
3. Extracts article content (text, headings, links, tables)
4. Removes ads, navigation, footers, and other non-content
5. Outputs clean Markdown directly
6. Handles documents of any size

### Trafilatura + LLM Polish Pipeline (`--use-llm`)

1. Trafilatura extracts main content to Markdown
2. Send extracted Markdown to Claude API
3. Claude polishes formatting and structure
4. Claude fixes any extraction artifacts
5. Returns enhanced Markdown
6. Fallback to unpolished Trafilatura output if LLM fails

### BeautifulSoup Pipeline (Fallback Only)

1. Parse HTML with BeautifulSoup
2. Remove script, style, nav, footer, and header tags
3. Extract text content
4. Convert to Markdown using html2text
5. Used only when Trafilatura fails

---

## PDF Extraction

PDF content is extracted using PyMuPDF (fitz):

- Extracts text content from all pages
- Preserves basic structure where possible
- Handled in `zr_common.py` via `extract_text_from_pdf()`

---

## LLM Extractor Module (`src/llm_extractor.py`)

The `LLMExtractor` class provides AI-powered content polishing:

### Methods

- `__init__()` - Initializes Anthropic client with API key and model selection
- `polish_markdown()` - **PRIMARY** - Polishes Trafilatura-extracted markdown for better formatting
- `extract_article_markdown()` - Legacy method for direct HTML extraction (kept for compatibility)
- `preprocess_html()` - Removes scripts, styles, and non-content elements before sending to LLM
- `set_model()` - Change the Claude model (e.g., claude-haiku-4-5, claude-3-5-sonnet)

### Key Features

- Polishes Trafilatura output for improved formatting and readability
- Fixes markdown inconsistencies and structural issues
- Preserves all content and links from original extraction
- Uses Claude Haiku 4.5 by default for cost efficiency
- Handles content of any size (works with already-extracted markdown)
