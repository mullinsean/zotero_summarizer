# Implementation Details

Edge cases, rate limiting, and important implementation details for ZoteroResearcher.

## API Rate Limiting

The code includes 1-second delays between API calls to respect Zotero's rate limits. This is implemented in the collection processing loop.

## Duplicate Prevention

The `--force` flag controls whether to re-extract markdown notes. The code checks for existing "Markdown Extract" notes to avoid duplicates. This prevents the same content from being extracted multiple times.

## Library Type Support

Supports both user libraries and group libraries. The `ZOTERO_LIBRARY_TYPE` environment variable determines which type is used.

**Important:** Do not use quotes around values in `.env` files:
- Correct: `ZOTERO_LIBRARY_TYPE=group`
- Wrong: `ZOTERO_LIBRARY_TYPE='group'` (quotes will be included in the value)

## PDF Attachment Handling

Items with PDF attachments are automatically skipped for HTML extraction. This prevents unnecessary webpage fetching when a PDF version already exists. The logic checks all child attachments for PDF files (by content type or file extension) before attempting any HTML extraction.

## Webpage Without Snapshot Handling

The tool can extract content from webpage items even without HTML snapshots:

- If an item has **no child items** and is a `webpage` type with a URL, content is fetched directly from the URL
- If an item has **child items but no HTML attachments** (e.g., only text files) and is a `webpage` type, content is fetched from the parent item's URL
- This enables extraction from webpages added to Zotero without saving snapshots
- PDF attachments take priority - if a PDF exists, webpage extraction is skipped

## Smart Storage for Large Reports

Reports are stored differently based on size:

- **Reports < 1MB**: Stored as full Zotero notes in the project subcollection
- **Reports >= 1MB**: Saved as HTML files with a stub note pointing to the file location

This prevents issues with Zotero's note size limits.

## Template Validation

When loading project configuration from Zotero notes:

- The tool checks for `[TODO:` markers in template notes
- If markers are found, it will refuse to run and prompt you to edit the notes
- This ensures you don't accidentally run with placeholder templates

## Cleanup Behavior

The cleanup workflow (`--cleanup-project`, `--cleanup-collection`):

- Supports dry-run mode (`--dry-run`) for safe previewing
- Supports skip-confirmation mode (`--yes`) for scripting
- Continues cleanup even if individual deletions fail
- Reports detailed summary of deleted items and errors
- Deletes child summary notes attached to items
- Deletes Gemini file search stores (and all files in store)

## Cache Invalidation

When using the local cache (`--enable-cache`):

- Write operations update both API and cache (write-through)
- Delta sync checks for changes and syncs incrementally
- Cache can be cleared per-collection with `--clear-cache`
- Offline mode (`--offline`) uses only cached data

## Subcollection Filtering

When using `--subcollections`:

- The ZResearcher project subcollection is always excluded from filtering
- Subcollection names are case-sensitive and must match exactly
- Error is shown if a specified subcollection name doesn't exist
