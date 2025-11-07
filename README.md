# Zotero Summarizer

A Python tool suite for sophisticated research workflows with Zotero libraries using AI-powered summarization and analysis.

## Primary Tool: ZoteroResearcher

**ZoteroResearcher** is a research assistant that analyzes sources based on a research brief, ranks them by relevance, and generates targeted summaries with key quotes and statistics. It uses a two-phase, project-based workflow:

- **Phase 1 (Build)**: Generate project-aware summaries with metadata and tags for all sources
- **Phase 2 (Query)**: Evaluate relevance against a research brief and generate targeted summaries

All configuration and outputs are stored in Zotero (no external files required).

## Quick Start

1. **Setup:**
   ```bash
   uv venv
   source .venv/bin/activate
   uv pip install -r requirements.txt
   ```

2. **Configure** (create `.env` file):
   ```
   ZOTERO_LIBRARY_ID=your_library_id
   ZOTERO_LIBRARY_TYPE=user
   ZOTERO_API_KEY=your_api_key
   ANTHROPIC_API_KEY=your_anthropic_key
   ```

3. **Initialize a project:**
   ```bash
   uv run python -m src.zresearcher --init-collection \
       --collection COLLECTION_KEY --project "My Research Project"
   ```

4. **Edit template notes in Zotero** (in the 【ZResearcher: PROJECT】 subcollection)

5. **Build summaries** (Phase 1):
   ```bash
   uv run python -m src.zresearcher --build-summaries \
       --collection COLLECTION_KEY --project "My Research Project"
   ```

6. **Run query** (Phase 2):
   ```bash
   uv run python -m src.zresearcher --query-summary \
       --collection COLLECTION_KEY --project "My Research Project"
   ```

## Documentation

See **[CLAUDE.md](CLAUDE.md)** for comprehensive documentation including:
- Detailed command reference
- Code architecture (modular design)
- Configuration options
- Project-based workflow guide

## Legacy Tools

The following tools have been deprecated and moved to `/old/`:
- `extract_html.py` - Simple HTML-to-Markdown extraction
- `summarize_sources.py` - Basic source summarization

These are superseded by the more powerful ZoteroResearcher tool.

## Project Structure

```
src/
├── zresearcher.py        # CLI entry point
├── zr_common.py          # Base class & shared utilities
├── zr_init.py            # Collection initialization
├── zr_build.py           # Phase 1: Build summaries
├── zr_query.py           # Phase 2: Query & report generation
├── zr_llm_client.py      # LLM API client
├── zr_prompts.py         # Prompt templates
└── zotero_base.py        # Base Zotero API functionality
```

## Requirements

- Python 3.12+
- Zotero library (user or group)
- Anthropic API key (for Claude)
