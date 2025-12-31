# CLI Commands Reference

Full command reference for ZoteroResearcher. For quick start, see the root [CLAUDE.md](../../CLAUDE.md).

## ZoteroResearcher - Primary Tool

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

## File Search (Google Gemini RAG)

```bash
# Step 1: Upload files to Gemini file search store
uv run python -m src.zresearcher --upload-files \
    --collection COLLECTION_KEY --project "My Research Project"

# Force re-upload of all files (deletes existing file search store and re-uploads)
uv run python -m src.zresearcher --upload-files \
    --collection COLLECTION_KEY --project "My Research Project" --force

# Step 2: Edit the Query Request note in Zotero (in the 【ZResearcher: PROJECT】 subcollection):
#   - 【Query Request】 (your File Search query)

# Step 3: Run File Search query (requires files to be uploaded first)
uv run python -m src.zresearcher --file-search \
    --collection COLLECTION_KEY --project "My Research Project"

# Verbose mode for detailed logging
uv run python -m src.zresearcher --file-search \
    --collection COLLECTION_KEY --project "My Research Project" --verbose
```

### File Search Implementation Details

- Uses Google Gemini File Search Stores for efficient RAG querying
- Two-stage workflow: upload files first (--upload-files), then run queries (--file-search)
- Files are uploaded to a dedicated file search store (not passed in context)
- Store is used as a tool during generation, avoiding context window limits
- Supports large collections (tested with 70+ files)
- Incremental uploads: only new files are uploaded on subsequent --upload-files runs
- Automatically detects and warns about new files not yet uploaded
- Automatically extracts and displays grounding sources
- LLM-generated report titles based on query request (format: "File Search Report: {title}")
- Store name and upload state tracked in Project Config note

## Vector Search (Local RAG)

Local vector search provides semantic search over your collection without external API dependencies:

```bash
# Step 1: Index collection documents (creates embeddings)
uv run python -m src.zresearcher --index-vectors \
    --collection COLLECTION_KEY --project "My Research Project"

# Step 2: Edit the Query Request note in Zotero (same as File Search)

# Step 3: Run Vector Search query
uv run python -m src.zresearcher --vector-search \
    --collection COLLECTION_KEY --project "My Research Project"

# Filter by Zotero item types (comma-separated)
uv run python -m src.zresearcher --vector-search \
    --collection COLLECTION_KEY --project "My Research Project" \
    --item-types "journalArticle,report"

# Filter by document types (from Phase 1 summaries)
uv run python -m src.zresearcher --vector-search \
    --collection COLLECTION_KEY --project "My Research Project" \
    --doc-types "primary_source,technical_report"
```

### Document Discovery

Find the most relevant documents for a topic without generating a full report:

```bash
# Discover top 10 relevant sources (default)
uv run python -m src.zresearcher --discover-sources \
    --collection COLLECTION_KEY --project "My Research Project"

# Discover top N sources
uv run python -m src.zresearcher --discover-sources \
    --collection COLLECTION_KEY --project "My Research Project" --top-n 15

# With filtering
uv run python -m src.zresearcher --discover-sources \
    --collection COLLECTION_KEY --project "My Research Project" \
    --item-types "journalArticle" --top-n 5
```

### Vector Search Implementation Details

- **Local processing**: All embedding and search happens locally using sentence-transformers
- **Default model**: all-MiniLM-L6-v2 (384 dimensions, fast and efficient)
- **Storage**: Vectors stored in SQLite cache (same as local cache feature)
- **Chunking**: Documents split into 512-character chunks with 50-character overlap
- **Page tracking**: Citations include page numbers for PDFs, section IDs for HTML
- **Incremental indexing**: Only new/changed documents are re-indexed
- **Filtering**: Filter by Zotero itemType or Phase 1 document type
- **Citations**: RAG responses include [source_num, p.X] style citations
- **Discovery justifications**: LLM-generated explanations for why each source is relevant

### Configuration (Project Config note)

```
vector_chunk_size=512
vector_chunk_overlap=50
vector_top_k=20
vector_embedding_model=all-MiniLM-L6-v2
```

## Subcollection Filtering

All workflows support optional subcollection filtering to process only items in specific subcollections:

```bash
# Process only items in specific subcollections (comma-separated names)
uv run python -m src.zresearcher --organize-sources \
    --collection COLLECTION_KEY --subcollections "Research Papers,Reports"

uv run python -m src.zresearcher --build-summaries \
    --collection COLLECTION_KEY --project "My Project" \
    --subcollections "Research Papers,Reports"

uv run python -m src.zresearcher --query-summary \
    --collection COLLECTION_KEY --project "My Project" \
    --subcollections "Research Papers"

# Process all subcollections (excludes main collection items)
uv run python -m src.zresearcher --build-summaries \
    --collection COLLECTION_KEY --project "My Project" \
    --subcollections all

# Include main collection items along with subcollections
uv run python -m src.zresearcher --build-summaries \
    --collection COLLECTION_KEY --project "My Project" \
    --subcollections "Research Papers" --include-main

# File Search with subcollection filtering
uv run python -m src.zresearcher --upload-files \
    --collection COLLECTION_KEY --project "My Project" \
    --subcollections "Research Papers,Reports"

uv run python -m src.zresearcher --file-search \
    --collection COLLECTION_KEY --project "My Project" \
    --subcollections "Research Papers,Reports"
```

### Subcollection Filtering Behavior

- **No flags**: Process all items in the main collection (default behavior)
- **`--subcollections "Name1,Name2"`**: Process only items in specified subcollections
- **`--subcollections all`**: Process items in all subcollections (excluding the ZResearcher project subcollection)
- **`--include-main`**: Also include items from the main collection when using `--subcollections`
- The ZResearcher project subcollection (e.g., `【ZResearcher: My Project】`) is always excluded from filtering
- Subcollection names are case-sensitive and must match exactly
- Error is shown if a specified subcollection name doesn't exist, with a list of available subcollections

## Cleanup

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

## Export to NotebookLM

Export collection to NotebookLM format by extracting PDFs, text files, and converting HTML to Markdown:

```bash
# Export entire collection to NotebookLM format
uv run python -m src.zresearcher --export-to-notebooklm \
    --collection COLLECTION_KEY --output-dir ./notebooklm_export

# Export with custom output directory
uv run python -m src.zresearcher --export-to-notebooklm \
    --collection COLLECTION_KEY --output-dir ~/Documents/NotebookLM

# Export only specific subcollections
uv run python -m src.zresearcher --export-to-notebooklm \
    --collection COLLECTION_KEY --subcollections "Research Papers,Reports" \
    --output-dir ./notebooklm_export

# Verbose mode for detailed logging
uv run python -m src.zresearcher --export-to-notebooklm \
    --collection COLLECTION_KEY --verbose
```

### Export Behavior

- **PDFs**: Copied as-is to output directory
- **Text files (.txt)**: Copied as-is to output directory
- **HTML snapshots**: Converted to Markdown using Trafilatura and saved as .md files
- Filenames are sanitized and made unique using item titles and attachment keys
- Supports subcollection filtering (same as other workflows)
- No project name required (standalone operation)
- Default output directory: `./notebooklm_export`

### Use Cases

- Prepare sources for NotebookLM analysis without summarization
- Quick export of all source documents in NotebookLM-compatible format
- Export specific subcollections for focused analysis
- Backup source documents in a portable format

## Export Summaries to Markdown

Export all ZResearcher summary notes for a project as either a single consolidated file or separate files:

```bash
# Export all summary notes to single consolidated file (default: ./zresearcher_summaries_{project}.md)
uv run python -m src.zresearcher --export-summaries \
    --collection COLLECTION_KEY --project "My Research Project"

# Export with custom output file path
uv run python -m src.zresearcher --export-summaries \
    --collection COLLECTION_KEY --project "My Research Project" \
    --output-file ./my_summaries.md

# Export as separate .md files in a directory (default: ./zresearcher_summaries_{project}/)
uv run python -m src.zresearcher --export-summaries \
    --collection COLLECTION_KEY --project "My Research Project" \
    --separate-files

# Export as separate files with custom directory path
uv run python -m src.zresearcher --export-summaries \
    --collection COLLECTION_KEY --project "My Research Project" \
    --separate-files --output-file ./summaries_directory

# Export only summaries from specific subcollections
uv run python -m src.zresearcher --export-summaries \
    --collection COLLECTION_KEY --project "My Research Project" \
    --subcollections "Research Papers,Reports"

# Verbose mode for detailed logging
uv run python -m src.zresearcher --export-summaries \
    --collection COLLECTION_KEY --project "My Research Project" --verbose
```

### Export Behavior

- Finds all items in the collection with "【ZResearcher Summary: PROJECT】" notes (created by --build-summaries)
- Extracts the content from each summary note (Metadata, Tags, Summary sections)
- **Consolidated mode (default)**: Appends all summaries into a single markdown file with headers for each item
- **Separate files mode (--separate-files)**: Creates individual .md files for each summary in a directory
  - Filenames: `001_Item_Title.md`, `002_Item_Title.md`, etc.
  - Files are numbered and include sanitized item titles
- Supports subcollection filtering (same as other workflows)
- Requires project name to identify which summaries to export
- Default output:
  - Consolidated: `./zresearcher_summaries_{project}.md`
  - Separate files: `./zresearcher_summaries_{project}/`

### Use Cases

- **Consolidated file**: Create a single reference document, share with collaborators, archive summaries
- **Separate files**: Individual review/editing, version control friendly, focused analysis per source
- Create input for further analysis or LLM processing
- Generate documents for reading or printing

## Local Cache (Experimental)

Local caching reduces API calls and enables offline operation. Cache is stored in `~/.zotero_summarizer/cache/`.

```bash
# Sync collection to local cache (downloads items, children, attachments)
uv run python -m src.zresearcher --sync --collection COLLECTION_KEY

# Force full re-sync (ignore existing cache)
uv run python -m src.zresearcher --sync --collection COLLECTION_KEY --force

# Check cache status for a collection
uv run python -m src.zresearcher --cache-status --collection COLLECTION_KEY

# Clear cache for a collection
uv run python -m src.zresearcher --clear-cache --collection COLLECTION_KEY

# Run workflow offline using cached data (requires prior --sync)
uv run python -m src.zresearcher --query-summary \
    --collection COLLECTION_KEY --project "My Project" \
    --enable-cache --offline
```

### Cache Features

- **SQLite-based storage**: Metadata, items, children stored in SQLite database per collection
- **Attachment caching**: PDF, HTML, TXT files downloaded during sync
- **Subcollection support**: Syncing parent collection includes all subcollections
- **Delta sync**: On workflow start, checks for changes and syncs incrementally
- **Offline mode**: `--offline` flag uses only cached data (no API calls)
- **Write-through**: Write operations update both API and cache

### Cache Location

```
~/.zotero_summarizer/
└── cache/
    ├── {library_id}_{collection_key}.db    # SQLite database
    └── attachments/
        ├── {attachment_key}.pdf            # Cached files
        └── {attachment_key}.html
```

### Use Cases

- Reduce API calls for frequently-accessed collections
- Work offline (e.g., on airplane, poor connectivity)
- Speed up repetitive operations (eliminates redundant API calls)
- Future: Vector database integration for RAG queries

## Diagnostic Utility

```bash
# Run diagnostic utility for troubleshooting
uv run python -m src.zotero_diagnose --user
uv run python -m src.zotero_diagnose --group GROUP_ID
```

## Legacy Tools

Legacy tools have been deprecated and moved to `/old/` directory:

```bash
# extract_html.py and summarize_sources.py have been superseded by zresearcher.py
# These files are preserved in /old/ for reference only
```
