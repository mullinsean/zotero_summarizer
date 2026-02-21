# Source Module Architecture

Detailed module responsibilities and APIs for the ZoteroResearcher codebase.

## File Structure

```
src/
├── zresearcher.py          # CLI entry point & routing
├── zr_common.py            # Base class & shared utilities
├── zr_init.py              # Collection initialization workflow
├── zr_organize_sources.py  # Source organization workflow
├── zr_verify_metadata.py   # Metadata verification & APA field audit
├── zr_build.py             # Phase 1: Build summaries workflow
├── zr_query.py             # Phase 2: Query & report generation workflow
├── zr_file_search.py       # File Search: Gemini RAG integration
├── zr_vector_db.py         # Vector Search: Local semantic search
├── zr_vector_embeddings.py # Embedding model wrapper (sentence-transformers)
├── zr_vector_chunker.py    # Document chunking with page/section tracking
├── zr_cleanup.py           # Cleanup: Delete projects & summary notes
├── zr_export.py            # Export: NotebookLM format & summary export
├── zr_llm_client.py        # Centralized LLM API client
├── zr_prompts.py           # Prompt templates
├── zotero_base.py          # Base Zotero API functionality
├── zotero_cache.py         # Local SQLite cache layer + vector storage
├── llm_extractor.py        # LLM-powered content polishing
└── zotero_diagnose.py      # Diagnostic utility
```

---

## Module Responsibilities

### `zresearcher.py` - CLI Entry Point

- Command-line argument parsing
- Environment variable loading and validation
- Routes to appropriate workflow classes
- No business logic - pure orchestration

### `zr_common.py` - Base Class & Shared Utilities

`ZoteroResearcherBase` class (inherits from `ZoteroBaseProcessor`):
- Initialization & configuration management
- `extract_metadata()` - Extract metadata from Zotero API
- `get_source_content()` - Unified content retrieval (HTML/PDF/URL priority)
- `extract_text_from_html()` - Trafilatura-based HTML extraction
- `extract_text_from_pdf()` - PyMuPDF-based PDF extraction
- `load_project_config_from_zotero()` - Load config from Zotero notes
- `apply_project_config()` - Apply and validate configuration
- All `_get_*_note_title()` helper methods

Utility function:
- `validate_project_name()` - Utility function for name validation

### `zr_init.py` - Collection Initialization

`ZoteroResearcherInit` class (inherits from `ZoteroResearcherBase`):
- `init_collection()` - Create project subcollection & template notes
- `list_projects()` - List existing projects in a collection

### `zr_organize_sources.py` - Source Organization

`ZoteroResearcherOrganizer` class (inherits from `ZoteroResearcherBase`):
- `organize_sources()` - Ensure all items have acceptable attachments (HTML/PDF/TXT)
- `is_txt_attachment()` - Check if attachment is a text file
- `has_acceptable_attachment()` - Verify item has processable attachment
- `promote_attachment_to_parent()` - Convert standalone attachments to proper items
- `save_webpage_snapshot()` - Fetch and save webpage HTML snapshots

Run after `init_collection` but before `build_summaries`.

### `zr_verify_metadata.py` - Metadata Verification

`ZoteroMetadataVerifier` class (inherits from `ZoteroResearcherBase`):
- `verify_metadata()` - Main entry point: four-phase audit & fix workflow
  - Phase A: Audit fields against APA requirements (no LLM)
  - Phase B: LLM verification of missing/suspicious fields via batch calls
  - Phase C: Compute safe updates (conservative by default, aggressive with `--force`)
  - Phase D: Apply changes to Zotero or display dry-run report
- `_audit_item()` - Check item fields against `APA_FIELD_REQUIREMENTS`
- `_parse_verification_response()` - Parse LLM structured output
- `_compute_field_updates()` / `_compute_type_change()` - Determine safe changes
- `_apply_updates()` - Write field changes and type changes to Zotero API
- `_add_verified_tag()` - Tag items with `_metadata_verified` to skip on re-runs

Uses `_metadata_verified` tag for idempotency. Supports `--dry-run`, `--force`, `--yes`.

### `zr_build.py` - Phase 1 Workflow

`ZoteroResearcherBuilder` class (inherits from `ZoteroResearcherBase`):
- `build_general_summaries()` - Main Phase 1 orchestration with parallel LLM processing
- `load_project_overview_from_zotero()` - Load project context
- `load_tags_from_zotero()` - Load tag taxonomy
- `has_general_summary()` - Check for existing summaries
- `format_general_summary_note()` - Create structured note format

### `zr_query.py` - Phase 2 Workflow

`ZoteroResearcherQuerier` class (inherits from `ZoteroResearcherBase`):
- `run_query_summary()` - Main Phase 2 orchestration with parallel processing
- `load_research_brief_from_zotero()` - Load research question
- `parse_general_summary_note()` - Parse structured summaries
- `rank_sources()` - Sort by relevance score
- `generate_report_title()` - LLM-generated report titles
- `_compile_research_html_string()` - HTML report generation
- Smart storage: Notes <1MB, files >1MB with stub notes

### `zr_vector_db.py` - Vector Search Workflow (Local RAG)

`ZoteroVectorSearcher` class (inherits from `ZoteroResearcherBase`):

**Indexing (`index_collection()`):**
- Extract content from collection items (PDF/HTML/TXT)
- Chunk documents with page/section tracking
- Generate embeddings using sentence-transformers
- Store chunks and embeddings in SQLite cache
- Track indexing state for incremental updates

**RAG Query (`run_vector_query()`):**
- Load query from Query Request note
- Embed query and search vector database
- Group results by source with page references
- Generate LLM response with inline citations [N, p.X]
- Save Vector Search Report to Zotero

**Document Discovery (`discover_sources()`):**
- Load query from Query Request note
- Embed query and search vector database
- Aggregate chunk scores by source document
- Generate brief justifications for top N sources
- Save Discovery Report to Zotero

**Helper Methods:**
- `_group_chunks_by_source()` - Group search results by item
- `_generate_rag_response()` - Generate cited response via LLM
- `_generate_discovery_justification()` - Generate relevance justifications
- `_format_vector_report()` / `_format_discovery_report()` - Report formatting

### `zr_vector_embeddings.py` - Embedding Model Wrapper

`VectorEmbeddingModel` class:
- Wraps sentence-transformers for local embeddings
- Default model: all-MiniLM-L6-v2 (384 dimensions)
- `embed_documents(texts)` - Batch embed documents
- `embed_query(query)` - Embed single query
- `serialize_embedding()` / `deserialize_embedding()` - Binary serialization for SQLite

Supported models: all-MiniLM-L6-v2, all-mpnet-base-v2, bge-small-en-v1.5, bge-base-en-v1.5

### `zr_vector_chunker.py` - Document Chunker

`ChunkData` dataclass:
- `text`, `chunk_index`, `page_number`, `section_id`, `char_start`, `char_end`

`DocumentChunker` class:
- Configurable chunk_size (default 512), chunk_overlap (default 50)
- `chunk_pdf(pdf_bytes)` - Chunk PDF with page tracking
- `chunk_html(html_bytes)` - Chunk HTML with section tracking
- `chunk_markdown(markdown_text)` - Chunk markdown with heading tracking
- `chunk_text(text)` - Basic text chunking
- Smart split detection: paragraph breaks → sentence endings → punctuation → words

### `zr_file_search.py` - File Search Workflow (Gemini RAG)

`ZoteroFileSearcher` class (inherits from `ZoteroResearcherBase`):

**Stage 1: Upload Files (`upload_files_to_gemini()`)**
- Upload collection files to Gemini file search store
- Create or reuse existing file search store
- Support incremental uploads (only new files uploaded)
- Track uploaded files in Project Config note
- Support force rebuild (delete and recreate store)

**Stage 2: Query (`run_file_search()`)**
- Verify files have been uploaded (error if not)
- Warn about new files not yet uploaded
- Query Gemini File Search and save results
- Generate LLM-based report title from query request
- Create File Search Report notes with grounding sources

**Helper Methods:**
- `load_query_request_from_zotero()` - Load query from Zotero note
- `generate_report_title()` - Generate LLM-based title from query request
- `_load_gemini_state_from_config()` - Load store name and upload state
- `_save_gemini_state_to_config()` - Save store name and upload state

Uses Google Gemini File Search Stores (genai.Client API). Files uploaded to dedicated store, used as tool (not in context window).

### `zr_cleanup.py` - Cleanup Workflow

`ZoteroResearcherCleaner` class (inherits from `ZoteroResearcherBase`):
- `cleanup_project()` - Delete specific project subcollection and summary notes
- `cleanup_all_projects()` - Delete ALL ZResearcher data in collection
- `is_general_summary_note()` - Identify general summary notes (with optional project filter)
- `find_general_summary_notes_for_project()` - Find summaries for specific project
- `find_all_general_summary_notes()` - Find all summary notes in collection
- `find_all_project_subcollections()` - Find all ZResearcher subcollections
- `delete_gemini_files_for_project()` - Delete Gemini file search store for project
- `count_items_in_collection()` - Count items by type (notes/files/items)
- `preview_cleanup()` - Display preview of what will be deleted
- `confirm_cleanup()` - Ask user for confirmation
- `delete_collection_recursive()` - Delete collection and all contents

### `zr_export.py` - Export Workflow

`ZoteroNotebookLMExporter` class (inherits from `ZoteroResearcherBase`):

**NotebookLM Export:**
- `export_to_notebooklm()` - Main export orchestration with progress tracking
- `_sanitize_filename()` - Clean filenames for filesystem safety
- `_get_export_filename()` - Generate unique filenames
- `_export_pdf_attachment()` - Copy PDF files to output directory
- `_export_txt_attachment()` - Copy text files to output directory
- `_export_html_attachment()` - Convert HTML to Markdown and save

**Summary Export:**
- `export_summaries_to_markdown()` - Export all summary notes (consolidated or separate)

---

## Base Modules

### `zotero_base.py` - Base Zotero API

`ZoteroBaseProcessor` class provides shared functionality:

**Collection & Item Management:**
- `list_collections()` / `print_collections()` - Collection management
- `get_collection_items()` - Retrieves top-level items from collection
- `get_item_attachments()` - Fetches child attachments
- `get_subcollection()` - Get subcollection by name within parent
- `create_subcollection()` - Create subcollection inside parent

**Attachment & Content:**
- `is_html_attachment()` / `is_pdf_attachment()` - Content type detection
- `download_attachment()` - Downloads attachment content from Zotero

**Note Management:**
- `create_note()` - Creates child note attached to item (with markdown conversion)
- `create_standalone_note()` - Creates standalone note in collection
- `get_collection_notes()` - Get all standalone notes in collection
- `has_note_with_prefix()` / `get_note_with_prefix()` - Note checking and retrieval
- `get_note_title_from_html()` - Extract title from note HTML
- `extract_text_from_note_html()` - Extract plain text from note HTML
- `markdown_to_html()` - Convert markdown to HTML for Zotero notes

### `zotero_cache.py` - Local SQLite Cache

`ZoteroCache` class provides local caching:

**Storage:**
- SQLite database per library+collection: `{library_id}_{collection_key}.db`
- Attachment files in: `~/.zotero_summarizer/cache/attachments/`
- In-memory session cache for frequently accessed data

**Read Operations (cache-first):**
- `get_collections()` / `get_collection()` / `get_subcollections()`
- `get_collection_items()` - Items in a collection
- `get_item_children()` - Notes and attachments for an item
- `get_attachment_file()` - Attachment file content

**Write Operations (store after API success):**
- `store_collection()` / `store_collections()`
- `store_item()` / `store_items()` - Cache items with collection membership
- `store_child()` / `store_children()` - Cache notes and attachments
- `store_attachment_file()` - Cache attachment file content

**Sync State:**
- `get_library_version()` / `set_library_version()`
- `is_synced()` / `needs_sync()`
- `get_last_sync_time()` / `set_last_sync_time()`

**Invalidation:**
- `invalidate_item()` - Remove item and its children
- `invalidate_child()` - Remove specific child
- `invalidate_children_for_parent()` - Remove all children for a parent
- `clear_all()` - Clear entire cache

**Statistics:**
- `get_stats()` - Get cache statistics
- `print_stats()` - Print formatted cache status

**Vector Storage:**
- `store_chunks()` - Store document chunks with embeddings
- `search_vectors()` - Cosine similarity search with optional filtering
- `get_index_state()` / `is_item_indexed()` - Check indexing status
- `get_indexed_items()` - List all indexed items
- `delete_item_vectors()` / `delete_all_vectors()` - Remove vector data
- `get_vector_stats()` / `print_vector_stats()` - Vector statistics

---

## Utility Modules

### `zotero_diagnose.py`

Diagnostic tool for troubleshooting Zotero connections and library access. Provides CLI for testing API connectivity and group membership.

### `llm_extractor.py`

See [content-extraction.md](../docs/claude/content-extraction.md) for details.

---

## Legacy Modules (Deprecated)

Located in `/old/` directory:

- **`old/extract_html.py`** - Simple HTML-to-Markdown extraction (superseded by ZoteroResearcher)
- **`old/summarize_sources.py`** - Basic source summarization (superseded by ZoteroResearcher)

---

## Class Hierarchy

```
ZoteroBaseProcessor (zotero_base.py)
└── ZoteroResearcherBase (zr_common.py)
    ├── ZoteroResearcherInit (zr_init.py)
    ├── ZoteroResearcherOrganizer (zr_organize_sources.py)
    ├── ZoteroMetadataVerifier (zr_verify_metadata.py)
    ├── ZoteroResearcherBuilder (zr_build.py)
    ├── ZoteroResearcherQuerier (zr_query.py)
    ├── ZoteroFileSearcher (zr_file_search.py)
    ├── ZoteroVectorSearcher (zr_vector_db.py)
    ├── ZoteroResearcherCleaner (zr_cleanup.py)
    └── ZoteroNotebookLMExporter (zr_export.py)
```
