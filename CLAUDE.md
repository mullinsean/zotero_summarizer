# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Zotero Summarizer** is a Python tool suite for working with Zotero libraries via the Zotero API.

The primary tool is **ZoteroResearcher** (`zresearcher.py`), a research assistant that analyzes sources based on a research brief, ranks them by relevance, and generates targeted summaries. It uses a three-phase workflow:

- **Phase 1 (Build)**: Generate project-aware summaries with metadata and tags
- **Phase 2 (Query)**: Evaluate relevance and generate targeted summaries with HTML reports
- **Phase 3 (Synthesis)**: Auto-generate meta-analysis synthesis (optional, enabled by default)

The tool supports a **Zotero-native workflow** where configuration and outputs are stored in Zotero.

## Detailed Documentation

| Document | Description |
|----------|-------------|
| [CLI Commands](docs/claude/commands.md) | Full command reference with examples |
| [Workflows](docs/claude/workflows.md) | Phase 1/2/3 details, data flow, Zotero-native workflow |
| [Content Extraction](docs/claude/content-extraction.md) | Trafilatura, PDF, URL extraction pipelines |
| [Implementation Details](docs/claude/implementation-details.md) | Edge cases, rate limiting, gotchas |
| [Module Architecture](src/CLAUDE.md) | Detailed module responsibilities and APIs |

## Package Manager

**This project uses `uv` for Python package management.** All commands should be run with `uv run`.

## Development Setup

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

## Quick Start Commands

```bash
# List collections
uv run python -m src.zresearcher --list-collections

# Initialize a project
uv run python -m src.zresearcher --init-collection \
    --collection COLLECTION_KEY --project "My Project"

# Build summaries (Phase 1)
uv run python -m src.zresearcher --build-summaries \
    --collection COLLECTION_KEY --project "My Project"

# Run query (Phase 2 + Phase 3)
uv run python -m src.zresearcher --query-summary \
    --collection COLLECTION_KEY --project "My Project"

# Vector search: Index collection
uv run python -m src.zresearcher --index-vectors \
    --collection COLLECTION_KEY --project "My Project"

# Vector search: RAG query (requires indexing first)
uv run python -m src.zresearcher --vector-search \
    --collection COLLECTION_KEY --project "My Project"

# Vector search: Find top N relevant sources
uv run python -m src.zresearcher --discover-sources \
    --collection COLLECTION_KEY --project "My Project" --top-n 10
```

For full command reference, see [docs/claude/commands.md](docs/claude/commands.md).

## File Structure

```
src/
├── zresearcher.py          # CLI entry point & routing
├── zr_common.py            # Base class & shared utilities
├── zr_init.py              # Collection initialization
├── zr_organize_sources.py  # Source organization
├── zr_build.py             # Phase 1: Build summaries
├── zr_query.py             # Phase 2: Query & reports
├── zr_file_search.py       # Gemini RAG integration
├── zr_vector_db.py         # Local vector search (index, query, discover)
├── zr_vector_embeddings.py # Embedding model wrapper
├── zr_vector_chunker.py    # Document chunking with page tracking
├── zr_cleanup.py           # Project cleanup
├── zr_export.py            # Export workflows
├── zr_llm_client.py        # LLM API client
├── zr_prompts.py           # Prompt templates
├── zotero_base.py          # Base Zotero API
├── zotero_cache.py         # Local SQLite cache + vector storage
├── llm_extractor.py        # Content polishing
└── zotero_diagnose.py      # Diagnostic utility
```

For detailed module documentation, see [src/CLAUDE.md](src/CLAUDE.md).

## Environment Variables

```bash
# Zotero Configuration
ZOTERO_LIBRARY_ID=<library_id>      # User or group ID
ZOTERO_LIBRARY_TYPE=user|group      # Type of library (no quotes!)
ZOTERO_API_KEY=<api_key>            # Zotero API key
ZOTERO_COLLECTION_KEY=<collection>  # Collection to process

# LLM Configuration
ANTHROPIC_API_KEY=<api_key>         # Claude API key (required)
GEMINI_API_KEY=<api_key>            # Gemini API key (for --file-search)
```

**Important:** Do not use quotes around values in `.env` files.

## Key Dependencies

- **pyzotero** - Zotero API client
- **trafilatura** - Web content extraction (primary method)
- **beautifulsoup4** / **html2text** - HTML processing (fallback)
- **anthropic** - Claude API client
- **google-genai** - Gemini API client (for file search)
- **sentence-transformers** - Local embedding models (for vector search)
- **sqlite-vec** - Vector search extension for SQLite
- **python-dotenv** - Environment management

## Python Version

**Required:** Python 3.12+

## LLM Model Strategy

- **Claude Haiku 4.5**: Phase 1 summaries, relevance evaluation, targeted summaries (default)
- **Claude Sonnet 4.5**: Targeted summaries (with config override), research synthesis (always)

## Content Extraction Priority

1. Existing "Markdown Extract" note
2. HTML snapshot (Trafilatura extraction)
3. PDF attachment (PyMuPDF extraction)
4. URL fetch (for webpages without snapshots)

## Linting & Code Quality

No linting tools currently configured. Future setup should include `black`, `ruff`, or `pylint`.

## Testing

No test framework currently configured. Tests should be added in `/tests/` using `pytest`.

When adding tests:
- Mock Zotero API responses using pyzotero fixtures
- Test HTML extraction with various document structures
- Validate Markdown conversion accuracy
- Test environment variable handling
- Test edge cases: missing attachments, invalid URLs, malformed HTML

## Known Limitations

- No linting or code formatting tools configured
- No automated test suite
- Documentation is minimal (only basic README)
- No CI/CD pipeline configured

## Legacy Tools

Deprecated tools moved to `/old/`:
- `extract_html.py` - Simple HTML-to-Markdown (superseded)
- `summarize_sources.py` - Basic summarization (superseded)
