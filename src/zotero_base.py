#!/usr/bin/env python3
"""
Zotero Base Processor

Base class providing shared functionality for processing Zotero collections,
including attachment detection, note creation, and verbose output.

Supports optional local caching for offline operation and reduced API calls.
"""

import markdown
from pyzotero import zotero
from typing import Optional, Dict, List

from .zotero_cache import ZoteroCache


class ZoteroBaseProcessor:
    """Base class for processing Zotero collections with shared functionality."""

    def __init__(
        self,
        library_id: str,
        library_type: str,
        api_key: str,
        verbose: bool = False,
        enable_cache: bool = False,
        cache_dir: Optional[str] = None,
        offline: bool = False
    ):
        """
        Initialize the Zotero base processor.

        Args:
            library_id: Your Zotero user ID or group ID
            library_type: 'user' or 'group'
            api_key: Your Zotero API key
            verbose: If True, show detailed information about all child items
            enable_cache: If True, enable local caching
            cache_dir: Custom cache directory (default: ~/.zotero_summarizer/cache)
            offline: If True, only use cached data (no API calls)
        """
        self.library_id = library_id
        self.zot = zotero.Zotero(library_id, library_type, api_key)
        self.verbose = verbose

        # Cache configuration
        self.enable_cache = enable_cache
        self.cache_dir = cache_dir
        self.offline = offline
        self._caches: Dict[str, ZoteroCache] = {}  # Per-collection caches

    # =========================================================================
    # Cache Management
    # =========================================================================

    def _get_cache(self, collection_key: str) -> Optional[ZoteroCache]:
        """Get or create cache for a collection."""
        if not self.enable_cache:
            return None

        if collection_key not in self._caches:
            self._caches[collection_key] = ZoteroCache(
                library_id=self.library_id,
                collection_key=collection_key,
                cache_dir=self.cache_dir,
                verbose=self.verbose
            )
        return self._caches[collection_key]

    def _log_cache(self, message: str):
        """Log cache-related message if verbose."""
        if self.verbose:
            print(f"[Cache] {message}")

    def get_library_version(self) -> Optional[int]:
        """Get current library version from Zotero API."""
        if self.offline:
            return None
        try:
            # Fetch a minimal request to get the library version
            # The version is in the response headers
            self.zot.collections(limit=1)
            return self.zot.request.headers.get('Last-Modified-Version')
        except Exception as e:
            if self.verbose:
                print(f"[Cache] Error getting library version: {e}")
            return None

    def sync_collection(
        self,
        collection_key: str,
        force: bool = False,
        sync_attachments: bool = True,
        progress_callback=None
    ) -> bool:
        """
        Sync a collection and all its subcollections to local cache.

        Args:
            collection_key: Collection to sync
            force: If True, do full sync ignoring cache state
            sync_attachments: If True, download all attachments (eager caching)
            progress_callback: Optional callback for progress updates

        Returns:
            True if sync was successful
        """
        if self.offline:
            print("Cannot sync in offline mode")
            return False

        cache = self._get_cache(collection_key)
        if not cache:
            print("Cache not enabled")
            return False

        print(f"\n=== Syncing Collection {collection_key} ===")

        try:
            # Check if delta sync is possible
            if not force and cache.is_synced():
                cached_version = cache.get_library_version()
                print(f"Cache version: {cached_version}")
                print("Checking for updates...")
                # For now, always do full sync on explicit --sync
                # Delta sync will be used for auto-sync on workflow start

            # Step 1: Sync the parent collection metadata
            print("\n1. Syncing collection metadata...")
            collections = self.zot.collections()
            parent_coll = None
            for coll in collections:
                if coll['key'] == collection_key:
                    parent_coll = coll
                    cache.store_collection(coll)
                    break

            if not parent_coll:
                print(f"Collection {collection_key} not found!")
                return False

            print(f"   Parent: {parent_coll['data']['name']}")

            # Step 2: Sync all subcollections
            print("\n2. Syncing subcollections...")
            subcollections = self.zot.collections_sub(collection_key)
            for subcoll in subcollections:
                cache.store_collection(subcoll)
            print(f"   Found {len(subcollections)} subcollections")

            # Step 3: Sync all items in collection (top-level)
            print("\n3. Syncing items...")
            items = list(self.zot.everything(self.zot.collection_items_top(collection_key)))
            cache.store_items(items, collection_key)
            print(f"   Found {len(items)} items in parent collection")

            # Also sync items in subcollections
            for subcoll in subcollections:
                subcoll_key = subcoll['key']
                subcoll_items = list(self.zot.everything(
                    self.zot.collection_items_top(subcoll_key)
                ))
                cache.store_items(subcoll_items, subcoll_key)
                if subcoll_items:
                    print(f"   Found {len(subcoll_items)} items in {subcoll['data']['name']}")

            # Step 4: Sync all children (notes + attachments) for each item
            print("\n4. Syncing item children (notes & attachments)...")
            all_items = list(items)  # Start with parent items
            for subcoll in subcollections:
                subcoll_key = subcoll['key']
                subcoll_items = list(self.zot.everything(
                    self.zot.collection_items_top(subcoll_key)
                ))
                all_items.extend(subcoll_items)

            # Deduplicate items (same item can be in multiple collections)
            seen_keys = set()
            unique_items = []
            for item in all_items:
                if item['key'] not in seen_keys:
                    seen_keys.add(item['key'])
                    unique_items.append(item)

            total_children = 0
            for i, item in enumerate(unique_items):
                item_key = item['key']
                children = self.zot.children(item_key)
                if children:
                    cache.store_children(children, item_key)
                    # Remove orphaned children (deleted from Zotero)
                    valid_child_keys = {c['key'] for c in children}
                    cache.remove_orphaned_children(item_key, valid_child_keys)
                    total_children += len(children)
                else:
                    # No children from API - remove any cached children
                    cache.remove_orphaned_children(item_key, set())

                if progress_callback:
                    progress_callback(i + 1, len(unique_items), "children")

            print(f"   Synced {total_children} children for {len(unique_items)} items")

            # Step 4b: Remove orphaned items (deleted from Zotero)
            removed_count = cache.remove_orphaned_items(seen_keys)
            if removed_count > 0:
                print(f"   Removed {removed_count} deleted items from cache")

            # Step 5: Download attachments (if eager caching enabled)
            if sync_attachments:
                print("\n5. Downloading attachments...")
                attachment_count = 0
                skipped_count = 0

                for i, item in enumerate(unique_items):
                    item_key = item['key']
                    children = cache.get_item_children(item_key) or []
                    attachments = [
                        c for c in children
                        if c['data'].get('itemType') == 'attachment'
                    ]

                    for att in attachments:
                        att_key = att['key']
                        if cache.has_attachment_file(att_key):
                            skipped_count += 1
                            continue

                        try:
                            content = self.zot.file(att_key)
                            cache.store_attachment_file(att_key, content, att['data'])
                            attachment_count += 1
                        except Exception as e:
                            if self.verbose:
                                print(f"   Warning: Could not download {att_key}: {e}")

                    if progress_callback:
                        progress_callback(i + 1, len(unique_items), "attachments")

                print(f"   Downloaded {attachment_count} attachments ({skipped_count} already cached)")

            # Update sync state
            cache.set_last_sync_time()
            # Try to get library version for delta sync
            try:
                self.zot.collections(limit=1)
                version = self.zot.request.headers.get('Last-Modified-Version')
                if version:
                    cache.set_library_version(int(version))
            except Exception:
                pass

            print("\n=== Sync Complete ===")
            cache.print_stats()
            return True

        except Exception as e:
            print(f"\nSync failed: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return False

    def delta_sync_collection(self, collection_key: str) -> bool:
        """
        Perform delta sync - only fetch changes since last sync.

        This is called automatically on workflow start when cache is enabled.

        Args:
            collection_key: Collection to sync

        Returns:
            True if sync was successful or no sync needed
        """
        if self.offline:
            self._log_cache("Offline mode - skipping delta sync")
            return True

        cache = self._get_cache(collection_key)
        if not cache:
            return True  # No cache, nothing to sync

        if not cache.is_synced():
            self._log_cache(f"Collection {collection_key} not synced yet")
            return False

        # Check if sync is needed
        try:
            self.zot.collections(limit=1)
            current_version = self.zot.request.headers.get('Last-Modified-Version')
            if current_version:
                current_version = int(current_version)
                if not cache.needs_sync(current_version):
                    self._log_cache("Cache is up to date")
                    return True

                self._log_cache(f"Library changed (cached: {cache.get_library_version()}, "
                               f"current: {current_version})")
                # For now, just note that sync is needed
                # Full delta sync implementation would fetch only changed items
                # using ?since=VERSION parameter
                self._log_cache("Delta sync: fetching changes...")

                # Simple approach: re-sync the collection
                # A more sophisticated approach would use the Zotero sync API
                return self.sync_collection(collection_key, force=False, sync_attachments=False)

        except Exception as e:
            self._log_cache(f"Delta sync check failed: {e}")
            return True  # Continue with cached data

        return True

    def get_cache_status(self, collection_key: str) -> Optional[Dict]:
        """Get cache status for a collection."""
        cache = self._get_cache(collection_key)
        if not cache:
            return None
        return cache.get_stats()

    def clear_cache(self, collection_key: str):
        """Clear cache for a collection."""
        cache = self._get_cache(collection_key)
        if cache:
            cache.clear_all()
            print(f"Cache cleared for collection {collection_key}")

    def list_collections(self) -> List[Dict]:
        """
        List all collections in the library.

        Returns:
            List of all collections
        """
        try:
            collections = self.zot.collections()
            return collections
        except Exception as e:
            print(f"Error listing collections: {e}")
            return []

    def print_collections(self):
        """Print all available collections with their keys."""
        collections = self.list_collections()
        if not collections:
            print("No collections found or error accessing library")
            return

        print(f"\n{'='*60}")
        print(f"Available Collections ({len(collections)} total)")
        print(f"{'='*60}")

        for col in collections:
            name = col['data'].get('name', 'Unnamed')
            key = col['key']
            parent = col['data'].get('parentCollection', 'Top-level')
            num_items = col['meta'].get('numItems', 0)
            print(f"  📁 {name}")
            print(f"     Key: {key}")
            print(f"     Items: {num_items}")
            if parent != 'Top-level':
                print(f"     Parent: {parent}")
            print()
        print(f"{'='*60}\n")

    def get_collection_items(self, collection_key: str) -> List[Dict]:
        """
        Get all top-level items in a specific collection (excluding child items).

        Args:
            collection_key: The key of the collection to process

        Returns:
            List of top-level items in the collection (no attachments/notes)
        """
        # Check cache first
        cache = self._get_cache(collection_key)
        if cache:
            cached_items = cache.get_collection_items(collection_key)
            if cached_items is not None:
                self._log_cache(f"Cache hit: {len(cached_items)} items from collection {collection_key}")
                return cached_items
            elif self.offline:
                print(f"Error: Collection {collection_key} not in cache (offline mode)")
                return []

        if self.offline:
            print(f"Error: Cache not available for collection {collection_key} (offline mode)")
            return []

        print(f"Fetching top-level items from collection {collection_key}...")
        try:
            # Use collection_items_top to only get parent items, not child attachments/notes
            # Use everything() to handle pagination and fetch all items (no 100-item limit)
            items = list(self.zot.everything(self.zot.collection_items_top(collection_key)))
            print(f"Found {len(items)} top-level items in collection")

            # Store in cache
            if cache:
                cache.store_items(items, collection_key)

            return items
        except Exception as e:
            print(f"Error fetching collection items: {e}")
            print("\nThis could mean:")
            print("  1. The collection key is incorrect")
            print("  2. You're using a user library ID for a group collection (or vice versa)")
            print("  3. The API key doesn't have access to this collection")
            print("\nTip: Run with --list-collections to see available collections")
            return []

    def get_item_children(self, item_key: str, collection_key: Optional[str] = None) -> List[Dict]:
        """
        Get all child items for a specific parent item.

        Args:
            item_key: The key of the parent item
            collection_key: Optional collection key for cache lookup

        Returns:
            List of all child items (attachments and notes)
        """
        # Check cache first (need collection_key to get the right cache)
        # Try all active caches if collection_key not provided
        caches_to_check = []
        if collection_key:
            cache = self._get_cache(collection_key)
            if cache:
                caches_to_check = [cache]
        else:
            caches_to_check = list(self._caches.values())

        for cache in caches_to_check:
            cached_children = cache.get_item_children(item_key)
            if cached_children is not None:
                self._log_cache(f"Cache hit: {len(cached_children)} children for item {item_key}")
                return cached_children

        if self.offline:
            self._log_cache(f"Cache miss for item {item_key} children (offline mode)")
            return []

        # Fetch from API
        children = self.zot.children(item_key)

        # Store in cache if we have a collection context
        if collection_key:
            cache = self._get_cache(collection_key)
            if cache:
                cache.store_children(children, item_key)

        return children

    def get_item_attachments(self, item_key: str) -> List[Dict]:
        """
        Get all attachments for a specific item (excludes notes).

        Args:
            item_key: The key of the parent item

        Returns:
            List of attachment items (only actual file attachments, not notes)
        """
        children = self.get_item_children(item_key)
        # Filter to only attachment items (excludes notes and other child types)
        attachments = [
            child for child in children
            if child['data'].get('itemType') == 'attachment'
        ]
        return attachments

    def print_child_items(self, item_key: str):
        """
        Print detailed information about all child items (verbose mode).

        Args:
            item_key: The key of the parent item
        """
        if not self.verbose:
            return

        children = self.get_item_children(item_key)
        print(f"  📋 All child items ({len(children)} total):")
        for idx, child in enumerate(children, 1):
            child_type = child['data'].get('itemType', 'unknown')
            child_title = child['data'].get('title', 'Untitled')

            if child_type == 'note':
                note_preview = child['data'].get('note', '')[:80].replace('\n', ' ')
                print(f"    {idx}. 📝 NOTE: {note_preview}...")
            elif child_type == 'attachment':
                content_type = child['data'].get('contentType', 'unknown')
                filename = child['data'].get('filename', 'no filename')
                link_mode = child['data'].get('linkMode', 'unknown')
                url = child['data'].get('url', 'no url')
                print(f"    {idx}. 📎 ATTACHMENT: {child_title}")
                print(f"        - Filename: {filename}")
                print(f"        - Content Type: {content_type}")
                print(f"        - Link Mode: {link_mode}")
                print(f"        - URL: {url}")
            else:
                print(f"    {idx}. ❓ {child_type.upper()}: {child_title}")

    def is_html_attachment(self, attachment: Dict) -> bool:
        """
        Check if an attachment is an HTML file.

        Args:
            attachment: The attachment item data

        Returns:
            True if the attachment is HTML
        """
        content_type = attachment['data'].get('contentType', '')
        filename = attachment['data'].get('filename', '')

        return (content_type in ['text/html', 'application/xhtml+xml'] or
                filename.lower().endswith(('.html', '.htm')))

    def is_pdf_attachment(self, attachment: Dict) -> bool:
        """
        Check if an attachment is a PDF file.

        Args:
            attachment: The attachment item data

        Returns:
            True if the attachment is PDF
        """
        content_type = attachment['data'].get('contentType', '')
        filename = attachment['data'].get('filename', '')

        return (content_type == 'application/pdf' or
                filename.lower().endswith('.pdf'))

    def is_txt_attachment(self, attachment: Dict) -> bool:
        """
        Check if an attachment is a text file.

        Args:
            attachment: The attachment item data

        Returns:
            True if the attachment is a text file
        """
        content_type = attachment['data'].get('contentType', '')
        filename = attachment['data'].get('filename', '')

        return (content_type == 'text/plain' or
                filename.lower().endswith('.txt'))

    def is_docx_attachment(self, attachment: Dict) -> bool:
        """
        Check if an attachment is a DOCX file.

        Args:
            attachment: The attachment item data

        Returns:
            True if the attachment is DOCX
        """
        content_type = attachment['data'].get('contentType', '')
        filename = attachment['data'].get('filename', '')

        # Support both modern .docx and legacy .doc formats
        # Note: python-docx only supports .docx, not legacy .doc
        return (content_type in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                                 'application/msword'] or
                filename.lower().endswith(('.docx', '.doc')))

    def download_attachment(
        self,
        attachment_key: str,
        collection_key: Optional[str] = None,
        attachment_data: Optional[Dict] = None
    ) -> Optional[bytes]:
        """
        Download an attachment file from Zotero (or cache).

        Args:
            attachment_key: The key of the attachment
            collection_key: Optional collection key for cache lookup
            attachment_data: Optional attachment metadata for caching

        Returns:
            File content as bytes, or None if download fails
        """
        # Check cache first
        caches_to_check = []
        if collection_key:
            cache = self._get_cache(collection_key)
            if cache:
                caches_to_check = [cache]
        else:
            caches_to_check = list(self._caches.values())

        for cache in caches_to_check:
            cached_content = cache.get_attachment_file(attachment_key)
            if cached_content is not None:
                self._log_cache(f"Cache hit: attachment {attachment_key}")
                return cached_content

        if self.offline:
            self._log_cache(f"Cache miss for attachment {attachment_key} (offline mode)")
            return None

        # Fetch from API
        try:
            if self.verbose:
                print(f"  📥 Downloading attachment from Zotero...")
            file_content = self.zot.file(attachment_key)

            # Store in cache
            if collection_key and attachment_data:
                cache = self._get_cache(collection_key)
                if cache:
                    cache.store_attachment_file(attachment_key, file_content, attachment_data)

            return file_content
        except Exception as e:
            print(f"  ❌ Error downloading attachment: {e}")
            return None

    def has_note_with_prefix(self, item_key: str, prefix: str) -> bool:
        """
        Check if an item already has a note starting with a specific prefix.

        Since notes are stored as HTML, we check for the HTML version of the prefix.
        For markdown headings like "# AI Summary:", we check for "<h1>AI Summary:"

        Args:
            item_key: The key of the parent item
            prefix: The prefix to search for (e.g., "AI Summary:", "Markdown Extract:")

        Returns:
            True if the item has a note with that prefix
        """
        children = self.get_item_children(item_key)
        notes = [child for child in children if child['data'].get('itemType') == 'note']

        for note in notes:
            note_content = note['data'].get('note', '')
            # Notes are stored as HTML, so check for HTML heading
            # The markdown "# Title" becomes "<h1>Title</h1>" in HTML
            html_prefix = f"<h1>{prefix}"
            if html_prefix in note_content[:200]:  # Check first 200 chars for the heading
                return True

        return False

    def get_note_with_prefix(self, item_key: str, prefix: str) -> Optional[str]:
        """
        Get the content of a note starting with a specific prefix.

        Args:
            item_key: The key of the parent item
            prefix: The prefix to search for (e.g., "AI Summary:", "Markdown Extract:")

        Returns:
            The HTML content of the note, or None if not found
        """
        children = self.get_item_children(item_key)
        notes = [child for child in children if child['data'].get('itemType') == 'note']

        for note in notes:
            note_content = note['data'].get('note', '')
            # Notes are stored as HTML, so check for HTML heading
            html_prefix = f"<h1>{prefix}"
            if html_prefix in note_content[:200]:  # Check first 200 chars for the heading
                return note_content

        return None

    def delete_note_with_prefix(
        self,
        item_key: str,
        prefix: str,
        collection_key: Optional[str] = None
    ) -> bool:
        """
        Delete a note starting with a specific prefix.

        Args:
            item_key: The key of the parent item
            prefix: The prefix to search for (e.g., "AI Summary:", "Markdown Extract:")
            collection_key: Optional collection key for cache invalidation

        Returns:
            True if note was found and deleted
        """
        if self.offline:
            print("  ❌ Cannot delete note in offline mode")
            return False

        children = self.get_item_children(item_key, collection_key)
        notes = [child for child in children if child['data'].get('itemType') == 'note']

        for note in notes:
            note_content = note['data'].get('note', '')
            # Notes are stored as HTML, so check for HTML heading
            html_prefix = f"<h1>{prefix}"
            if html_prefix in note_content[:200]:  # Check first 200 chars for the heading
                try:
                    self.zot.delete_item(note)

                    # Invalidate cache
                    if collection_key:
                        cache = self._get_cache(collection_key)
                        if cache:
                            cache.invalidate_child(note['key'])

                    return True
                except Exception as e:
                    if self.verbose:
                        print(f"  ⚠️  Error deleting note: {e}")
                    return False

        return False

    def markdown_to_html(self, markdown_content: str) -> str:
        """
        Convert markdown content to HTML for Zotero notes.

        Args:
            markdown_content: Markdown content

        Returns:
            HTML formatted content
        """
        try:
            # Convert markdown to HTML with extensions
            html_content = markdown.markdown(
                markdown_content,
                extensions=['extra', 'nl2br', 'sane_lists']
            )
            return html_content
        except Exception as e:
            print(f"  ⚠️  Warning: Markdown conversion failed: {e}")
            # Fall back to simple newline-to-br replacement
            return markdown_content.replace('\n', '<br>')

    def create_note(
        self,
        parent_key: str,
        content: str,
        title: str,
        convert_markdown: bool = True,
        collection_key: Optional[str] = None
    ) -> bool:
        """
        Create a note in Zotero attached to a parent item.

        Args:
            parent_key: The key of the parent item
            content: The content for the note (markdown or HTML)
            title: Title to prepend to the note
            convert_markdown: If True, convert markdown to HTML
            collection_key: Optional collection key for cache invalidation

        Returns:
            True if note was created successfully
        """
        if self.offline:
            print("  ❌ Cannot create note in offline mode")
            return False

        try:
            # Prepend title
            full_content = f"# {title}\n\n{content}"

            # Convert markdown to HTML for proper Zotero rendering
            if convert_markdown:
                html_content = self.markdown_to_html(full_content)
            else:
                html_content = full_content

            note_template = self.zot.item_template('note')
            note_template['note'] = html_content
            note_template['parentItem'] = parent_key

            result = self.zot.create_items([note_template])

            if result['success']:
                print(f"  ✅ Note created successfully")

                # Invalidate cache for parent's children and store new note
                if collection_key:
                    cache = self._get_cache(collection_key)
                    if cache:
                        # Invalidate children cache so next read gets fresh data
                        cache.invalidate_children_for_parent(parent_key)

                return True
            else:
                print(f"  ❌ Failed to create note: {result}")
                return False
        except Exception as e:
            print(f"  ❌ Error creating note: {e}")
            return False

    def get_subcollection(self, parent_collection_key: str, subcollection_name: str) -> Optional[str]:
        """
        Get a subcollection key by name within a parent collection.

        Args:
            parent_collection_key: Key of parent collection
            subcollection_name: Name of subcollection to find

        Returns:
            Subcollection key or None if not found
        """
        # Check cache first
        cache = self._get_cache(parent_collection_key)
        if cache:
            subcollections = cache.get_subcollections(parent_collection_key)
            for coll in subcollections:
                if coll['data']['name'] == subcollection_name:
                    self._log_cache(f"Cache hit: subcollection {subcollection_name}")
                    return coll['key']
            # If cache exists but subcollection not found, might be not synced
            # Fall through to API if not offline
            if self.offline:
                return None

        if self.offline:
            return None

        try:
            collections = self.zot.collections_sub(parent_collection_key)
            for coll in collections:
                if coll['data']['name'] == subcollection_name:
                    # Store in cache
                    if cache:
                        cache.store_collection(coll)
                    return coll['key']
            return None
        except Exception as e:
            print(f"  ❌ Error getting subcollection: {e}")
            return None

    def create_subcollection(self, parent_collection_key: str, subcollection_name: str) -> Optional[str]:
        """
        Create a subcollection inside a parent collection.

        Args:
            parent_collection_key: Key of parent collection
            subcollection_name: Name for new subcollection

        Returns:
            Key of created subcollection or None if creation fails
        """
        if self.offline:
            print("  ❌ Cannot create subcollection in offline mode")
            return None

        try:
            # Check if already exists
            existing_key = self.get_subcollection(parent_collection_key, subcollection_name)
            if existing_key:
                return existing_key

            # Create new subcollection manually (no template method for collections)
            collection_data = {
                'name': subcollection_name,
                'parentCollection': parent_collection_key
            }

            result = self.zot.create_collections([collection_data])

            if result['successful']:
                new_key = result['successful']['0']['key']

                # Store in cache
                cache = self._get_cache(parent_collection_key)
                if cache:
                    # Construct collection object to store
                    new_collection = {
                        'key': new_key,
                        'data': {
                            'name': subcollection_name,
                            'parentCollection': parent_collection_key
                        },
                        'version': result['successful']['0'].get('version')
                    }
                    cache.store_collection(new_collection)

                return new_key
            else:
                print(f"  ❌ Failed to create subcollection: {result}")
                return None
        except Exception as e:
            print(f"  ❌ Error creating subcollection: {e}")
            return None

    def create_standalone_note(
        self,
        collection_key: str,
        content: str,
        title: str,
        convert_markdown: bool = True,
        tags: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Create a standalone note (not attached to an item) in a collection.

        Args:
            collection_key: Collection to add note to
            content: Note content (markdown or HTML)
            title: Note title (will be first heading in HTML)
            convert_markdown: If True, convert markdown to HTML
            tags: Optional list of Zotero tags

        Returns:
            Item key of created note or None if creation fails
        """
        if self.offline:
            print("  ❌ Cannot create standalone note in offline mode")
            return None

        try:
            # Prepend title
            full_content = f"# {title}\n\n{content}"

            # Convert markdown to HTML for proper Zotero rendering
            if convert_markdown:
                html_content = self.markdown_to_html(full_content)
            else:
                html_content = full_content

            # Create note item manually to ensure correct structure
            note_item = {
                'itemType': 'note',
                'note': html_content,
                'collections': [collection_key],
                'tags': [{'tag': tag} for tag in tags] if tags else []
            }

            result = self.zot.create_items([note_item])

            if result['successful']:
                note_key = result['successful']['0']['key']
                print(f"  ✅ Standalone note created successfully")
                return note_key
            else:
                print(f"  ❌ Failed to create standalone note: {result}")
                return None
        except Exception as e:
            print(f"  ❌ Error creating standalone note: {e}")
            return None

    def get_collection_notes(self, collection_key: str) -> List[Dict]:
        """
        Get all standalone notes in a collection (not attached to items).

        Args:
            collection_key: Collection key

        Returns:
            List of note items
        """
        try:
            # Use everything() to handle pagination and fetch all items (no 100-item limit)
            items = self.zot.everything(self.zot.collection_items(collection_key))
            notes = [item for item in items if item['data']['itemType'] == 'note']
            return notes
        except Exception as e:
            print(f"  ❌ Error getting collection notes: {e}")
            return []

    def get_note_title_from_html(self, note_html: str) -> str:
        """
        Extract title from note HTML (first h1 or first line).

        Args:
            note_html: HTML content of note

        Returns:
            Note title
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(note_html, 'html.parser')

        # Try to find h1
        h1 = soup.find('h1')
        if h1:
            return h1.get_text().strip()

        # Fall back to first non-empty line
        text = soup.get_text().strip()
        first_line = text.split('\n')[0] if text else 'Untitled'
        return first_line.strip()

    def extract_text_from_note_html(self, note_html: str) -> str:
        """
        Extract plain text from note HTML.

        Args:
            note_html: HTML content of note

        Returns:
            Plain text content
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(note_html, 'html.parser')
        return soup.get_text().strip()
