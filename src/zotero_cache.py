"""
Local SQLite-based cache for Zotero data.

Provides transparent caching layer between ZoteroBaseProcessor and the Zotero API.
Supports offline operation, delta sync, and prepares for future vector DB integration.
"""

import json
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import os


class ZoteroCache:
    """
    Local SQLite-based cache for Zotero data.

    Features:
    - Persistent storage in SQLite
    - Attachment files stored on filesystem
    - Version tracking for delta sync
    - Write-through cache (API writes update cache on success)
    """

    # Default cache directory in user home
    DEFAULT_CACHE_DIR = os.path.expanduser("~/.zotero_summarizer/cache")

    def __init__(
        self,
        library_id: str,
        collection_key: str,
        cache_dir: Optional[str] = None,
        verbose: bool = False
    ):
        """
        Initialize cache for a specific library and collection.

        Args:
            library_id: Zotero library ID
            collection_key: Collection key to cache
            cache_dir: Optional custom cache directory
            verbose: Enable verbose logging
        """
        self.library_id = library_id
        self.collection_key = collection_key
        self.verbose = verbose

        # Set up cache directory
        self.cache_dir = Path(cache_dir or self.DEFAULT_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Attachments stored in shared directory
        self.attachments_dir = self.cache_dir / "attachments"
        self.attachments_dir.mkdir(parents=True, exist_ok=True)

        # SQLite database per library+collection
        self.db_path = self.cache_dir / f"{library_id}_{collection_key}.db"

        # Initialize database
        self._init_db()

        # In-memory session cache (L1)
        self._session_cache: Dict[str, Any] = {}

    def _init_db(self):
        """Initialize SQLite database with schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                -- Sync state tracking
                CREATE TABLE IF NOT EXISTS sync_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Collections cache (parent + subcollections)
                CREATE TABLE IF NOT EXISTS collections (
                    key TEXT PRIMARY KEY,
                    parent_key TEXT,
                    name TEXT,
                    data_json TEXT NOT NULL,
                    version INTEGER,
                    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Items cache (top-level items only)
                CREATE TABLE IF NOT EXISTS items (
                    key TEXT PRIMARY KEY,
                    item_type TEXT,
                    data_json TEXT NOT NULL,
                    version INTEGER,
                    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Item-collection membership (M:N relationship)
                CREATE TABLE IF NOT EXISTS item_collections (
                    item_key TEXT NOT NULL,
                    collection_key TEXT NOT NULL,
                    PRIMARY KEY (item_key, collection_key),
                    FOREIGN KEY (item_key) REFERENCES items(key),
                    FOREIGN KEY (collection_key) REFERENCES collections(key)
                );

                -- Children cache (notes + attachments)
                CREATE TABLE IF NOT EXISTS children (
                    key TEXT PRIMARY KEY,
                    parent_key TEXT NOT NULL,
                    item_type TEXT,
                    data_json TEXT NOT NULL,
                    version INTEGER,
                    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Attachment content metadata (files stored on filesystem)
                CREATE TABLE IF NOT EXISTS attachment_files (
                    attachment_key TEXT PRIMARY KEY,
                    filename TEXT,
                    content_type TEXT,
                    file_path TEXT NOT NULL,
                    file_size INTEGER,
                    content_hash TEXT,
                    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (attachment_key) REFERENCES children(key)
                );

                -- Future: Vector embeddings table
                CREATE TABLE IF NOT EXISTS embeddings (
                    item_key TEXT PRIMARY KEY,
                    embedding BLOB,
                    content_hash TEXT,
                    model_version TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (item_key) REFERENCES items(key)
                );

                -- Create indexes for common queries
                CREATE INDEX IF NOT EXISTS idx_children_parent ON children(parent_key);
                CREATE INDEX IF NOT EXISTS idx_item_collections_collection ON item_collections(collection_key);
                CREATE INDEX IF NOT EXISTS idx_items_type ON items(item_type);
            """)
            conn.commit()

    def _log(self, message: str):
        """Log message if verbose mode enabled."""
        if self.verbose:
            print(f"[Cache] {message}")

    # =========================================================================
    # Sync State Management
    # =========================================================================

    def get_sync_state(self, key: str) -> Optional[str]:
        """Get a sync state value."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT value FROM sync_state WHERE key = ?",
                (key,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def set_sync_state(self, key: str, value: str):
        """Set a sync state value."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO sync_state (key, value, updated_at)
                   VALUES (?, ?, ?)""",
                (key, value, datetime.now().isoformat())
            )
            conn.commit()

    def get_library_version(self) -> Optional[int]:
        """Get cached library version."""
        version = self.get_sync_state("library_version")
        return int(version) if version else None

    def set_library_version(self, version: int):
        """Set library version after sync."""
        self.set_sync_state("library_version", str(version))

    def get_last_sync_time(self) -> Optional[str]:
        """Get timestamp of last sync."""
        return self.get_sync_state("last_sync_time")

    def set_last_sync_time(self):
        """Set last sync time to now."""
        self.set_sync_state("last_sync_time", datetime.now().isoformat())

    def is_synced(self) -> bool:
        """Check if this collection has ever been synced."""
        return self.get_library_version() is not None

    def needs_sync(self, current_version: int) -> bool:
        """Check if cache needs sync based on version."""
        cached_version = self.get_library_version()
        if cached_version is None:
            return True
        return current_version > cached_version

    # =========================================================================
    # Collection Operations
    # =========================================================================

    def get_collections(self) -> Optional[List[Dict]]:
        """Get all cached collections (parent + subcollections)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT data_json FROM collections")
            rows = cursor.fetchall()
            if not rows:
                return None
            return [json.loads(row[0]) for row in rows]

    def get_collection(self, collection_key: str) -> Optional[Dict]:
        """Get a specific collection by key."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT data_json FROM collections WHERE key = ?",
                (collection_key,)
            )
            row = cursor.fetchone()
            return json.loads(row[0]) if row else None

    def get_subcollections(self, parent_key: str) -> List[Dict]:
        """Get subcollections of a parent collection."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT data_json FROM collections WHERE parent_key = ?",
                (parent_key,)
            )
            return [json.loads(row[0]) for row in cursor.fetchall()]

    def store_collection(self, collection: Dict):
        """Store a single collection."""
        key = collection['key']
        data = collection.get('data', {})
        parent_key = data.get('parentCollection')
        name = data.get('name', '')
        version = collection.get('version')

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO collections
                   (key, parent_key, name, data_json, version, synced_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (key, parent_key, name, json.dumps(collection), version,
                 datetime.now().isoformat())
            )
            conn.commit()
        self._log(f"Stored collection: {name} ({key})")

    def store_collections(self, collections: List[Dict]):
        """Store multiple collections."""
        for collection in collections:
            self.store_collection(collection)

    # =========================================================================
    # Item Operations
    # =========================================================================

    def get_collection_items(self, collection_key: str) -> Optional[List[Dict]]:
        """Get all items in a collection from cache."""
        # Check session cache first
        cache_key = f"items_{collection_key}"
        if cache_key in self._session_cache:
            self._log(f"Session cache hit: {cache_key}")
            return self._session_cache[cache_key]

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT i.data_json FROM items i
                   JOIN item_collections ic ON i.key = ic.item_key
                   WHERE ic.collection_key = ?""",
                (collection_key,)
            )
            rows = cursor.fetchall()
            if not rows:
                return None

            items = [json.loads(row[0]) for row in rows]
            self._session_cache[cache_key] = items
            self._log(f"Loaded {len(items)} items from DB for collection {collection_key}")
            return items

    def get_item(self, item_key: str) -> Optional[Dict]:
        """Get a specific item by key."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT data_json FROM items WHERE key = ?",
                (item_key,)
            )
            row = cursor.fetchone()
            return json.loads(row[0]) if row else None

    def store_item(self, item: Dict, collection_keys: List[str]):
        """Store a single item with collection memberships."""
        key = item['key']
        data = item.get('data', {})
        item_type = data.get('itemType', '')
        version = item.get('version')

        with sqlite3.connect(self.db_path) as conn:
            # Store item
            conn.execute(
                """INSERT OR REPLACE INTO items
                   (key, item_type, data_json, version, synced_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (key, item_type, json.dumps(item), version,
                 datetime.now().isoformat())
            )

            # Store collection memberships
            for coll_key in collection_keys:
                conn.execute(
                    """INSERT OR IGNORE INTO item_collections (item_key, collection_key)
                       VALUES (?, ?)""",
                    (key, coll_key)
                )

            conn.commit()

        # Invalidate session cache for affected collections
        for coll_key in collection_keys:
            cache_key = f"items_{coll_key}"
            self._session_cache.pop(cache_key, None)

    def store_items(self, items: List[Dict], collection_key: str):
        """Store multiple items for a collection."""
        for item in items:
            # Get collection memberships from item data
            data = item.get('data', {})
            collection_keys = data.get('collections', [])
            if collection_key not in collection_keys:
                collection_keys.append(collection_key)
            self.store_item(item, collection_keys)
        self._log(f"Stored {len(items)} items for collection {collection_key}")

    # =========================================================================
    # Children (Notes + Attachments) Operations
    # =========================================================================

    def get_item_children(self, item_key: str) -> Optional[List[Dict]]:
        """Get all children (notes + attachments) for an item."""
        # Check session cache first
        cache_key = f"children_{item_key}"
        if cache_key in self._session_cache:
            self._log(f"Session cache hit: {cache_key}")
            return self._session_cache[cache_key]

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT data_json FROM children WHERE parent_key = ?",
                (item_key,)
            )
            rows = cursor.fetchall()
            if not rows:
                return None

            children = [json.loads(row[0]) for row in rows]
            self._session_cache[cache_key] = children
            self._log(f"Loaded {len(children)} children for item {item_key}")
            return children

    def get_child(self, child_key: str) -> Optional[Dict]:
        """Get a specific child by key."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT data_json FROM children WHERE key = ?",
                (child_key,)
            )
            row = cursor.fetchone()
            return json.loads(row[0]) if row else None

    def store_child(self, child: Dict):
        """Store a single child (note or attachment)."""
        key = child['key']
        data = child.get('data', {})
        parent_key = data.get('parentItem', '')
        item_type = data.get('itemType', '')
        version = child.get('version')

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO children
                   (key, parent_key, item_type, data_json, version, synced_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (key, parent_key, item_type, json.dumps(child), version,
                 datetime.now().isoformat())
            )
            conn.commit()

        # Invalidate session cache
        cache_key = f"children_{parent_key}"
        self._session_cache.pop(cache_key, None)

    def store_children(self, children: List[Dict], parent_key: str):
        """Store multiple children for an item."""
        for child in children:
            self.store_child(child)
        self._log(f"Stored {len(children)} children for item {parent_key}")

    # =========================================================================
    # Attachment File Operations
    # =========================================================================

    def has_attachment_file(self, attachment_key: str) -> bool:
        """Check if attachment file is cached."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT file_path FROM attachment_files WHERE attachment_key = ?",
                (attachment_key,)
            )
            row = cursor.fetchone()
            if not row:
                return False
            # Verify file still exists
            return Path(row[0]).exists()

    def get_attachment_file(self, attachment_key: str) -> Optional[bytes]:
        """Get attachment file content from cache."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT file_path FROM attachment_files WHERE attachment_key = ?",
                (attachment_key,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            file_path = Path(row[0])
            if not file_path.exists():
                self._log(f"Attachment file missing: {file_path}")
                return None

            self._log(f"Loading attachment from cache: {attachment_key}")
            return file_path.read_bytes()

    def store_attachment_file(
        self,
        attachment_key: str,
        content: bytes,
        attachment_data: Dict
    ):
        """
        Store attachment file on filesystem and metadata in DB.

        Args:
            attachment_key: Attachment item key
            content: File content bytes
            attachment_data: Attachment metadata from Zotero API
        """
        # Determine file extension from metadata
        filename = attachment_data.get('filename', '')
        content_type = attachment_data.get('contentType', '')

        if filename:
            ext = Path(filename).suffix
        elif 'pdf' in content_type:
            ext = '.pdf'
        elif 'html' in content_type:
            ext = '.html'
        elif 'text' in content_type:
            ext = '.txt'
        else:
            ext = '.bin'

        # Store file
        file_path = self.attachments_dir / f"{attachment_key}{ext}"
        file_path.write_bytes(content)

        # Calculate hash for change detection
        content_hash = hashlib.sha256(content).hexdigest()

        # Store metadata
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO attachment_files
                   (attachment_key, filename, content_type, file_path,
                    file_size, content_hash, downloaded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (attachment_key, filename, content_type, str(file_path),
                 len(content), content_hash, datetime.now().isoformat())
            )
            conn.commit()

        self._log(f"Stored attachment: {filename or attachment_key} ({len(content)} bytes)")

    def get_attachment_metadata(self, attachment_key: str) -> Optional[Dict]:
        """Get attachment file metadata."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT filename, content_type, file_path, file_size,
                          content_hash, downloaded_at
                   FROM attachment_files WHERE attachment_key = ?""",
                (attachment_key,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                'attachment_key': attachment_key,
                'filename': row[0],
                'content_type': row[1],
                'file_path': row[2],
                'file_size': row[3],
                'content_hash': row[4],
                'downloaded_at': row[5]
            }

    # =========================================================================
    # Cache Invalidation
    # =========================================================================

    def invalidate_item(self, item_key: str):
        """Invalidate cache for a specific item and its children."""
        with sqlite3.connect(self.db_path) as conn:
            # Delete children
            conn.execute("DELETE FROM children WHERE parent_key = ?", (item_key,))
            # Delete item-collection memberships
            conn.execute("DELETE FROM item_collections WHERE item_key = ?", (item_key,))
            # Delete item
            conn.execute("DELETE FROM items WHERE key = ?", (item_key,))
            conn.commit()

        # Clear session cache
        self._session_cache.pop(f"children_{item_key}", None)
        # Clear all collection item caches (item might be in multiple)
        keys_to_remove = [k for k in self._session_cache if k.startswith("items_")]
        for k in keys_to_remove:
            self._session_cache.pop(k, None)

        self._log(f"Invalidated item: {item_key}")

    def invalidate_child(self, child_key: str):
        """Invalidate cache for a specific child."""
        with sqlite3.connect(self.db_path) as conn:
            # Get parent key first
            cursor = conn.execute(
                "SELECT parent_key FROM children WHERE key = ?",
                (child_key,)
            )
            row = cursor.fetchone()
            parent_key = row[0] if row else None

            # Delete child
            conn.execute("DELETE FROM children WHERE key = ?", (child_key,))
            conn.commit()

        # Clear session cache for parent
        if parent_key:
            self._session_cache.pop(f"children_{parent_key}", None)

        self._log(f"Invalidated child: {child_key}")

    def invalidate_children_for_parent(self, parent_key: str):
        """Invalidate all cached children for a parent item."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM children WHERE parent_key = ?", (parent_key,))
            conn.commit()

        # Clear session cache
        self._session_cache.pop(f"children_{parent_key}", None)
        self._log(f"Invalidated children for parent: {parent_key}")

    def invalidate_collection(self, collection_key: str):
        """Invalidate cache for a collection (not items, just membership)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM item_collections WHERE collection_key = ?",
                (collection_key,)
            )
            conn.execute(
                "DELETE FROM collections WHERE key = ?",
                (collection_key,)
            )
            conn.commit()

        self._session_cache.pop(f"items_{collection_key}", None)
        self._log(f"Invalidated collection: {collection_key}")

    def clear_session_cache(self):
        """Clear in-memory session cache."""
        self._session_cache.clear()
        self._log("Cleared session cache")

    def clear_all(self):
        """Clear all cached data for this collection."""
        # Delete database file
        if self.db_path.exists():
            self.db_path.unlink()

        # Note: We don't delete attachments as they might be shared
        # between collections. A separate cleanup command can handle that.

        # Re-initialize empty database
        self._init_db()
        self._session_cache.clear()

        self._log(f"Cleared all cache data")

    def remove_orphaned_items(self, valid_item_keys: set, collection_key: str = None) -> int:
        """
        Remove items from cache that are no longer in the API response.

        This handles the case where items are deleted from Zotero but still
        exist in the local cache.

        Args:
            valid_item_keys: Set of item keys that should remain in cache
            collection_key: If provided, only remove orphaned items from this collection

        Returns:
            Number of items removed
        """
        removed_count = 0

        with sqlite3.connect(self.db_path) as conn:
            if collection_key:
                # Get items that are in this collection but not in valid_item_keys
                cursor = conn.execute(
                    """
                    SELECT DISTINCT item_key FROM item_collections
                    WHERE collection_key = ?
                    """,
                    (collection_key,)
                )
            else:
                # Get all items in cache
                cursor = conn.execute("SELECT key FROM items")

            cached_keys = {row[0] for row in cursor.fetchall()}
            orphaned_keys = cached_keys - valid_item_keys

            for item_key in orphaned_keys:
                # Delete children first
                conn.execute("DELETE FROM children WHERE parent_key = ?", (item_key,))
                # Delete item-collection memberships
                conn.execute("DELETE FROM item_collections WHERE item_key = ?", (item_key,))
                # Delete item
                conn.execute("DELETE FROM items WHERE key = ?", (item_key,))
                removed_count += 1

                # Clear session cache
                self._session_cache.pop(f"children_{item_key}", None)

            conn.commit()

        # Clear collection item caches
        keys_to_remove = [k for k in self._session_cache if k.startswith("items_")]
        for k in keys_to_remove:
            self._session_cache.pop(k, None)

        if removed_count > 0:
            self._log(f"Removed {removed_count} orphaned items from cache")

        return removed_count

    def remove_orphaned_children(self, parent_key: str, valid_child_keys: set) -> int:
        """
        Remove children from cache that are no longer in the API response.

        Args:
            parent_key: Parent item key
            valid_child_keys: Set of child keys that should remain in cache

        Returns:
            Number of children removed
        """
        removed_count = 0

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT key FROM children WHERE parent_key = ?",
                (parent_key,)
            )
            cached_keys = {row[0] for row in cursor.fetchall()}
            orphaned_keys = cached_keys - valid_child_keys

            for child_key in orphaned_keys:
                conn.execute("DELETE FROM children WHERE key = ?", (child_key,))
                removed_count += 1

            conn.commit()

        # Clear session cache
        self._session_cache.pop(f"children_{parent_key}", None)

        if removed_count > 0:
            self._log(f"Removed {removed_count} orphaned children for {parent_key}")

        return removed_count

    # =========================================================================
    # Statistics / Status
    # =========================================================================

    def get_stats(self) -> Dict:
        """Get cache statistics."""
        with sqlite3.connect(self.db_path) as conn:
            stats = {
                'library_id': self.library_id,
                'collection_key': self.collection_key,
                'db_path': str(self.db_path),
                'db_size_mb': self.db_path.stat().st_size / (1024 * 1024) if self.db_path.exists() else 0,
                'is_synced': self.is_synced(),
                'library_version': self.get_library_version(),
                'last_sync_time': self.get_last_sync_time(),
            }

            # Count records
            for table in ['collections', 'items', 'children', 'attachment_files']:
                cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                stats[f'{table}_count'] = cursor.fetchone()[0]

            # Calculate attachment storage size
            attachment_size = sum(
                f.stat().st_size for f in self.attachments_dir.iterdir()
                if f.is_file()
            )
            stats['attachments_size_mb'] = attachment_size / (1024 * 1024)

            return stats

    def print_stats(self):
        """Print cache statistics."""
        stats = self.get_stats()
        print(f"\n=== Cache Status ===")
        print(f"Library ID: {stats['library_id']}")
        print(f"Collection: {stats['collection_key']}")
        print(f"Database: {stats['db_path']}")
        print(f"Database size: {stats['db_size_mb']:.2f} MB")
        print(f"Synced: {stats['is_synced']}")
        if stats['is_synced']:
            print(f"Library version: {stats['library_version']}")
            print(f"Last sync: {stats['last_sync_time']}")
        print(f"\nCached records:")
        print(f"  Collections: {stats['collections_count']}")
        print(f"  Items: {stats['items_count']}")
        print(f"  Children: {stats['children_count']}")
        print(f"  Attachments: {stats['attachment_files_count']}")
        print(f"  Attachment storage: {stats['attachments_size_mb']:.2f} MB")
