# Researcher Feature - Implementation Plan

## Overview

Add a sophisticated research assistant feature that analyzes a Zotero collection based on a user-defined research brief, ranks sources by relevance, and generates targeted summaries with key quotes and statistics.

**Key Implementation Advantage:** This feature can leverage substantial existing code from `summarize_sources.py`, `analyze_pdfs.py`, and `zotero_base.py`. No new dependencies are required - all PDF extraction, HTML processing, LLM integration, and HTML compilation functionality already exists in the codebase!

## User Workflow

1. User creates a research brief file (e.g., `research_brief.txt`) describing their paper topic or research question
2. User runs: `uv run python zresearcher.py --collection COLLECTION_KEY --brief research_brief.txt`
3. System processes sources in the collection (up to configurable limit)
4. System outputs a compiled HTML research report with:
   - Linked Table of Contents with relevance scores (clickable)
   - Detailed summaries of relevant sources (ranked by relevance)
   - Key quotes and statistics for each source
   - Relevance explanations
   - Processing statistics
5. User opens HTML file in browser to review and use for research

## Architecture

### New Module: `zotero_summarizer/zresearcher.py`

**Class: `ZoteroResearcher`**

Inherits from `ZoteroBaseProcessor` (like `ZoteroSourceSummarizer` does) to reuse collection/item retrieval logic.

**Core Methods:**
- `__init__()` - Initialize with Zotero credentials and LLM client
- `load_research_brief()` - Load research brief from plain text file
- `get_source_content()` - Retrieve content from markdown/HTML/PDF/URL (priority order)
- `extract_text_from_html()` - **REUSE from `summarize_sources.py`** (Trafilatura-based)
- `extract_text_from_pdf()` - **REUSE from `summarize_sources.py`** (PyMuPDF/fitz-based)
- `evaluate_source_relevance()` - LLM call to score source relevance (0-10 scale)
- `rank_sources()` - Sort sources by relevance score (descending)
- `generate_targeted_summary()` - Create detailed summary with quotes for relevant sources
- `compile_html_document()` - Build final HTML document (leverage pattern from `build_compiled_html()`)
- `run_research()` - Main orchestration method

### New Module: `zotero_summarizer/source_summarizer.py` (Optional)

**Class: `SourceSummarizer`**

Handles creation and caching of source summaries for efficiency.

**Core Methods:**
- `get_or_create_summary()` - Check for existing summary note, create if needed
- `create_summary_note()` - Generate and store a general summary in Zotero
- `has_summary_note()` - Check if source already has a cached summary

## Detailed Workflow

### Phase 1: Collection Loading
1. Retrieve all items from specified collection
2. Filter for items with extractable content (HTML snapshots, PDFs, or URLs)
3. Skip items that are notes or attachments themselves

### Phase 2: Relevance Evaluation

**Two-Stage Approach for Efficiency:**

**Stage 1: Quick Relevance Check (using cached summaries)**
- For each source:
  - Check if a "General Summary" note exists in Zotero
  - If not, create one using LLM (store for future reuse)
  - Use the summary to evaluate relevance with prompt:
    ```
    Research Brief: {brief}

    Source Summary: {summary}

    Rate the relevance of this source to the research brief on a scale of 0-10.
    Provide only a number.
    ```
  - Store relevance score with source metadata

**Stage 2: Filtering**
- Rank sources by relevance score (highest to lowest)
- Apply threshold (e.g., only process sources with score >= 6)
- This reduces expensive detailed summarization to only relevant sources

### Phase 3: Detailed Summarization
For each relevant source (relevance >= threshold):
- Retrieve full content (markdown extract or generate from HTML/PDF)
- Make LLM call with enhanced prompt:
  ```
  Research Brief: {brief}

  Source Content: {full_content}

  Please provide:
  1. A concise summary of this source (2-3 paragraphs)
  2. An explanation of why this source is relevant to the research brief (1 paragraph)
  3. Key passages, quotes, and statistics from the source that are relevant to the brief.
     Format each as:
     - Quote/Stat: "[exact text]"
     - Context: [brief explanation]
     - Page/Section: [if available]
  ```

### Phase 4: Document Compilation
Generate final HTML document with linked table of contents:
```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Research Report: {brief title}</title>
  <style>
    body { font-family: Georgia, serif; max-width: 900px; margin: 40px auto; padding: 0 20px; line-height: 1.6; }
    h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }
    h2 { color: #34495e; margin-top: 40px; }
    h3 { color: #7f8c8d; }
    .toc { background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 30px 0; }
    .toc ol { line-height: 2; }
    .source { border-left: 4px solid #3498db; padding-left: 20px; margin: 40px 0; }
    .metadata { color: #7f8c8d; font-size: 0.9em; }
    .quote { background: #f0f8ff; border-left: 3px solid #3498db; padding: 15px; margin: 15px 0; font-style: italic; }
    .stats { background: #e8f5e9; padding: 20px; border-radius: 8px; margin-top: 40px; }
  </style>
</head>
<body>
  <h1>Research Report: {brief title}</h1>

  <div class="section">
    <h2>Research Brief</h2>
    <p>{full brief text}</p>
  </div>

  <div class="toc">
    <h2>Table of Contents</h2>
    <ol>
      <li><a href="#source-1">Source Title 1</a> - Relevance: 9/10</li>
      <li><a href="#source-2">Source Title 2</a> - Relevance: 8/10</li>
      ...
    </ol>
  </div>

  <h2>Sources</h2>

  <div id="source-1" class="source">
    <h3>1. Source Title 1</h3>
    <div class="metadata">
      <strong>Relevance Score:</strong> 9/10<br>
      <strong>Zotero Link:</strong> <a href="zotero://select/...">Open in Zotero</a>
    </div>

    <h4>Summary</h4>
    <p>{summary}</p>

    <h4>Relevance Explanation</h4>
    <p>{why relevant}</p>

    <h4>Key Passages & Quotes</h4>
    <div class="quote">
      <strong>Quote:</strong> "..."<br>
      <strong>Context:</strong> ...<br>
      <strong>Location:</strong> Page 45
    </div>
  </div>

  <!-- Repeat for each source -->

  <div class="stats">
    <h2>Statistics</h2>
    <ul>
      <li>Total sources in collection: X</li>
      <li>Sources evaluated: Y</li>
      <li>Relevant sources (>= threshold): Z</li>
      <li>Processing time: M minutes</li>
    </ul>
  </div>
</body>
</html>
```

## Configuration

### Command-Line Arguments
```bash
uv run python zresearcher.py \
  --collection COLLECTION_KEY \           # Required: Zotero collection to analyze
  --brief research_brief.txt \            # Required: Path to research brief file (plain text)
  --threshold 6 \                         # Optional: Relevance threshold (default: 6)
  --output research_report.html \         # Optional: Output file (default: research_report_{timestamp}.html)
  --max-sources 50 \                      # Optional: Limit number of sources to process (default: 50)
  --cache-summaries \                     # Optional: Enable summary caching (default: True)
  --no-cache-summaries \                  # Optional: Disable summary caching
  --model claude-sonnet-4-5-20250929      # Optional: Override LLM model
```

### Environment Variables
Reuse existing:
- `ZOTERO_LIBRARY_ID`
- `ZOTERO_LIBRARY_TYPE`
- `ZOTERO_API_KEY`
- `ANTHROPIC_API_KEY` (required for this feature)

### Zotero Note Types
Create standardized note titles for organization:
- **"General Summary"** - Cached summary for quick relevance checks (reusable)
- **"Research Summary: {brief_title}"** - Targeted summary for specific research brief (specific)

## Implementation Phases

### Phase 1: Basic Researcher (MVP)
- Load research brief from plain text file
- Retrieve collection items
- Support multiple content types: HTML snapshots, PDFs, and URLs
- Extract content from PDFs using pypdf or pdfplumber
- Evaluate relevance using existing markdown extracts (no caching yet)
- Rank sources by relevance score (0-10 scale, threshold default: 6)
- Generate simple summaries without detailed quotes
- Output HTML document with linked table of contents
- Configurable source limit (default: 50)

### Phase 2: Summary Caching
- Add SourceSummarizer class
- Check for existing "General Summary" notes
- Generate and store summaries when missing
- Use cached summaries for relevance evaluation

### Phase 3: Enhanced Summarization
- Add structured quote extraction with page numbers
- Improve prompt engineering for better relevance explanations
- Add citation formatting (APA, MLA, Chicago styles)
- Better handling of tables and figures from PDFs
- Extract and format bibliographic metadata

### Phase 4: Advanced Features
- Parallel processing for multiple LLM calls
- Progress indicators and status updates
- **Cost estimation and control:**
  - Display estimated cost before processing
  - Add `--dry-run` flag to preview without execution
  - Token counting and cost tracking
- Support for multiple research briefs in batch mode
- Additional export formats (PDF, DOCX)
- Incremental updates (only process new sources)

## Key Design Questions

### 1. Summary Caching Strategy
**Question:** Where should we store cached general summaries?

**Options:**
- **A) Zotero Notes** (recommended)
  - Pros: Portable, visible in Zotero UI, backed up with library
  - Cons: API calls to create, rate limiting

- **B) Local SQLite Database**
  - Pros: Faster access, no API calls
  - Cons: Not portable, separate from Zotero

- **C) JSON File**
  - Pros: Simple, human-readable
  - Cons: Not scalable, potential corruption

**Recommendation:** Start with Zotero Notes (Option A) for consistency with existing approach.

### 2. Relevance Scoring Approach
**Question:** How should we evaluate relevance?

**Options:**
- **A) 0-10 Numeric Scale** (recommended)
  - Simple to rank and threshold

- **B) Categories (High/Medium/Low/Not Relevant)**
  - More interpretable but harder to rank

- **C) Percentage (0-100%)**
  - More granular but potentially over-precise

**Recommendation:** 0-10 scale with threshold parameter.

### 3. Content Source Priority
**Decision:** Use the following priority order for content extraction:

**Priority Order:**
1. Existing "Markdown Extract" notes (already processed, fastest)
2. Generate from HTML snapshot (using existing Trafilatura pipeline)
3. Generate from PDF attachment (using pypdf, new in MVP)
4. Fetch from URL (fallback for webpage items without snapshots)

**For Cached Summaries:**
Use same content source as relevance evaluation to ensure consistency. Cache the extracted content type in the summary note metadata for transparency.

### 4. LLM Model Selection
**Question:** Which Claude model for different tasks?

**Recommendations:**
- **Relevance Evaluation:** Claude Haiku 4.5 (fast, cheap, simple task)
- **General Summaries:** Claude Haiku 4.5 (straightforward summarization)
- **Detailed Research Summaries:** Claude 3.5 Sonnet (better at nuanced analysis, quote extraction)

Allow override via `--model` flag.

### 5. Rate Limiting & Cost Control
**Question:** How to manage API costs?

**Strategies:**
- Display estimated cost before processing (token estimation)
- Add `--dry-run` flag to see what would be processed
- Add `--max-sources` limit
- Use summary caching aggressively (reduces repeated LLM calls)
- Batch similar API calls where possible
- Rate limit to respect both Zotero and Anthropic API limits

### 6. Error Handling
**Question:** What happens when a source fails to process?

**Approach:**
- Log errors but continue processing other sources
- Include failed sources in final report with error explanation
- Add `--strict` flag to fail fast on errors
- Track success/failure statistics in final report

## Testing Strategy

### Unit Tests
- Test research brief parsing
- Test relevance scoring logic
- Test document compilation
- Mock LLM responses for deterministic testing

### Integration Tests
- Test with mock Zotero collection
- Test with sample research briefs
- Validate output document structure

### Manual Testing Scenarios
1. Empty collection
2. Collection with no relevant sources
3. Collection with mix of relevant and irrelevant sources
4. Very large collection (100+ items)
5. Sources without extractable content
6. Multiple research briefs on same collection

## Documentation Updates

### CLAUDE.md Additions
- Add Researcher module section
- Document new commands
- Explain caching strategy
- Update data flow diagram

### README.md Updates
- Add Researcher feature section
- Include example workflows
- Show sample output
- Add troubleshooting guide

## Dependencies

### No New Dependencies Required!

All necessary dependencies are already installed:
- **`pymupdf` (fitz)** - PDF text extraction (already used in `analyze_pdfs.py` and `summarize_sources.py`)
- **`pypdf`** - PDF analysis (already installed, used in `analyze_pdfs.py`)
- **`anthropic`** - LLM features (already used in `summarize_sources.py`)
- **`pyzotero`** - Zotero API (used throughout project)
- **`trafilatura`** - HTML extraction (already used in `summarize_sources.py`)
- **`beautifulsoup4`** - HTML parsing (already installed)
- **`requests`** - URL fetching (already used)
- **`markdown`** - Markdown to HTML conversion (already used in `zotero_base.py`)

### Existing Code to Reuse

**From `summarize_sources.py` (ZoteroSourceSummarizer):**
- `extract_text_from_html()` - Trafilatura-based HTML extraction (lines 78-124)
- `extract_text_from_pdf()` - PyMuPDF-based PDF extraction (lines 126-164)
- `summarize_with_llm()` - Anthropic API calling pattern (lines 166-203)
- `build_compiled_html()` - HTML report generation with TOC (lines 366-520)
- Inherits from `ZoteroBaseProcessor` for collection handling

**From `analyze_pdfs.py` (ZoteroPDFAnalyzer):**
- `is_pdf_attachment()` - PDF detection logic (lines 123-137)
- `download_attachment()` - Attachment downloading (lines 139-154)

**From `zotero_base.py` (ZoteroBaseProcessor):**
- `get_collection_items()` - Collection retrieval
- `get_item_attachments()` - Attachment fetching
- `is_html_attachment()` / `is_pdf_attachment()` - Content type detection
- `create_note()` - Note creation in Zotero
- `has_note_with_prefix()` / `get_note_with_prefix()` - Note checking for caching

### Potential Future Dependencies (Phase 4)
- `tqdm` - Progress bars for long-running operations
- `python-docx` - DOCX export format
- `weasyprint` or `pdfkit` - PDF export format

## Migration & Backward Compatibility

- No breaking changes to existing functionality
- Researcher is a new standalone module
- Existing extract_html.py and summarize_sources.py remain unchanged
- Can be adopted gradually

## Success Metrics

### Functionality
- [ ] Successfully evaluates relevance of sources
- [ ] Generates useful targeted summaries
- [ ] Produces well-formatted research documents
- [ ] Caching reduces redundant LLM calls by >80%

### Performance
- [ ] Processes 50-source collection in <5 minutes
- [ ] Rate limiting respects API constraints
- [ ] Cost per source is reasonable (<$0.10)

### User Experience
- [ ] Clear progress indicators
- [ ] Useful error messages
- [ ] Output is immediately useful for research

## Design Decisions (Agreed)

### Core Decisions
1. **Relevance Threshold:** Default to 6/10, configurable via `--threshold` flag ✓
2. **Brief Format:** Plain text input files, HTML output with linked table of contents ✓
3. **Source Limits:** Default maximum of 50 sources, configurable via `--max-sources` flag ✓
4. **PDF Support:** Include in MVP (Phase 1) using `pypdf` library ✓
5. **Cost Control:** Defer to Phase 4 (future work) ✓

### Design Choices
6. **Output Format:** HTML with embedded CSS for professional, clickable reports ✓
7. **Summary Caching:** Store in Zotero as "General Summary" notes (portable, backed up) ✓
8. **Relevance Scoring:** 0-10 numeric scale for easy ranking and thresholding ✓
9. **LLM Models:**
   - Haiku 4.5 for relevance checks and general summaries (fast, cheap)
   - Sonnet 4.5 for detailed research summaries (better analysis)

### Open Questions (Future Consideration)
- **Quote Extraction Format:** Markdown in HTML or structured JSON mode?
- **Multi-Brief Workflow:** Batch processing multiple research questions?
- **Incremental Updates:** Re-run only on new sources since last research?
- **Additional Exports:** PDF and DOCX generation priority?

## Next Steps

1. ~~Review this plan and discuss open questions~~ ✓
2. ~~Agree on MVP scope~~ ✓ (Phase 1 + Phase 2)
3. ~~Check for existing code to reuse~~ ✓ (Found extensive reusable code!)
4. Create implementation tasks and begin development:
   - **Create `ZoteroResearcher` class** inheriting from `ZoteroBaseProcessor`
   - **Reuse extraction methods** from `summarize_sources.py`:
     - Copy `extract_text_from_html()` (Trafilatura-based)
     - Copy `extract_text_from_pdf()` (PyMuPDF-based)
   - **Implement research-specific features:**
     - `load_research_brief()` - Read plain text brief file
     - `get_source_content()` - Unified content retrieval with priority order
     - `evaluate_source_relevance()` - LLM-based relevance scoring
     - `rank_sources()` - Sort by relevance score
   - **Implement summary caching (Phase 2):**
     - Check for "General Summary" notes (reuse base class methods)
     - Generate and cache summaries for reuse
   - **Implement detailed summarization:**
     - `generate_targeted_summary()` - Contextual summaries with quotes
     - Enhanced prompts for research-specific output
   - **Adapt HTML compilation:**
     - Leverage pattern from `build_compiled_html()` in `summarize_sources.py`
     - Add linked table of contents with relevance scores
     - Add research brief section
5. Test with real Zotero collection
6. Iterate based on real-world usage and feedback

---

**Created:** 2025-11-05
**Updated:** 2025-11-05
**Status:** Approved - Ready for Implementation
