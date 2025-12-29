"""
ZoteroResearcher Cache Manager

Provides local caching of Zotero collections to minimize API bottleneck
and enable offline operation.

Architecture:
- SQLite database for metadata, relationships, and sync state
- Filesystem storage for attachment files and extracted content
- Version tracking for incremental sync
"""

import os
import json
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
import shutil

from .zr_common import ZoteroResearcherBase


class ZoteroCacheManager(ZoteroResearcherBase):
    """Manages local cache of Zotero collection data"""

    CACHE_VERSION = 1
    DEFAULT_CACHE_DIR = ".zotero_cache"

    def __init__(self, library_id: str, library_type: str, api_key: str,
                 cache_dir: Optional[str] = None, verbose: bool = False):
        """
        Initialize cache manager

        Args:
            library_id: Zotero library ID
            library_type: 'user' or 'group'
            api_key: Zotero API key
            cache_dir: Directory for cache storage (default: .zotero_cache)
            verbose: Enable verbose logging
        """
        # Initialize with empty anthropic_api_key since cache operations don't need LLM
        super().__init__(
            library_id=library_id,
            library_type=library_type,
            api_key=api_key,
            anthropic_api_key="",  # Not used for cache operations
            project_name="cache",  # Dummy project name
            force_rebuild=False,
            verbose=verbose
        )

        # Set up cache directory
        self.cache_dir = Path(cache_dir) if cache_dir else Path(self.DEFAULT_CACHE_DIR)
        self.cache_dir.mkdir(exist_ok=True)

        # Set up subdirectories
        self.files_dir = self.cache_dir / "files"
        self.files_dir.mkdir(exist_ok=True)

        # Database path
        self.db_path = self.cache_dir / "store.db"

        # Initialize database
        self._init_database()

        # Load config
        self.config_path = self.cache_dir / "config.json"
        self.config = self._load_config()

    def _init_database(self):
        """Initialize SQLite database with schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys = ON")

        # Schema version tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Collections table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS collections (
                collection_key TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                parent_key TEXT,
                version INTEGER NOT NULL,
                last_synced TIMESTAMP,
                FOREIGN KEY (parent_key) REFERENCES collections(collection_key)
            )
        """)

        # Items table (stores item metadata)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                item_key TEXT PRIMARY KEY,
                item_type TEXT NOT NULL,
                title TEXT,
                date TEXT,
                url TEXT,
                metadata TEXT,
                version INTEGER NOT NULL,
                last_synced TIMESTAMP
            )
        """)

        # Collection memberships (many-to-many)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS collection_items (
                collection_key TEXT NOT NULL,
                item_key TEXT NOT NULL,
                PRIMARY KEY (collection_key, item_key),
                FOREIGN KEY (collection_key) REFERENCES collections(collection_key) ON DELETE CASCADE,
                FOREIGN KEY (item_key) REFERENCES items(item_key) ON DELETE CASCADE
            )
        """)

        # Attachments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attachments (
                attachment_key TEXT PRIMARY KEY,
                parent_item_key TEXT NOT NULL,
                filename TEXT NOT NULL,
                content_type TEXT,
                local_path TEXT,
                file_hash TEXT,
                version INTEGER NOT NULL,
                last_synced TIMESTAMP,
                FOREIGN KEY (parent_item_key) REFERENCES items(item_key) ON DELETE CASCADE
            )
        """)

        # Notes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                note_key TEXT PRIMARY KEY,
                parent_item_key TEXT,
                collection_key TEXT,
                title TEXT,
                content_html TEXT,
                version INTEGER NOT NULL,
                last_synced TIMESTAMP,
                FOREIGN KEY (parent_item_key) REFERENCES items(item_key) ON DELETE CASCADE,
                FOREIGN KEY (collection_key) REFERENCES collections(collection_key) ON DELETE CASCADE
            )
        """)

        # Extracted content table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extracted_content (
                item_key TEXT PRIMARY KEY,
                extraction_method TEXT NOT NULL,
                extracted_text TEXT,
                extraction_date TIMESTAMP,
                FOREIGN KEY (item_key) REFERENCES items(item_key) ON DELETE CASCADE
            )
        """)

        # Sync state table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_state (
                collection_key TEXT PRIMARY KEY,
                last_sync_version INTEGER NOT NULL DEFAULT 0,
                last_sync_time TIMESTAMP,
                full_sync_completed BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (collection_key) REFERENCES collections(collection_key) ON DELETE CASCADE
            )
        """)

        # Create indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_items_type ON items(item_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_attachments_parent ON attachments(parent_item_key)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_notes_parent ON notes(parent_item_key)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_notes_collection ON notes(collection_key)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_collection_items_collection ON collection_items(collection_key)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_collection_items_item ON collection_items(item_key)
        """)

        # Record schema version
        cursor.execute("SELECT version FROM schema_version WHERE version = ?", (self.CACHE_VERSION,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (self.CACHE_VERSION,))

        conn.commit()
        conn.close()

        if self.verbose:
            print(f"✓ Database initialized: {self.db_path}")

    def _load_config(self) -> Dict[str, Any]:
        """Load cache configuration"""
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                return json.load(f)
        return {
            'version': self.CACHE_VERSION,
            'created_at': datetime.now().isoformat()
        }

    def _save_config(self):
        """Save cache configuration"""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

    def get_connection(self) -> sqlite3.Connection:
        """Get database connection with Row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _get_item_storage_dir(self, item_key: str) -> Path:
        """Get storage directory for an item"""
        item_dir = self.files_dir / item_key
        item_dir.mkdir(exist_ok=True)
        return item_dir

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    def init_cache(self, collection_key: str) -> bool:
        """
        Initialize cache for a collection (create sync state entry)

        Args:
            collection_key: Zotero collection key

        Returns:
            True if successful
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Check if already initialized
            cursor.execute("""
                SELECT collection_key FROM sync_state WHERE collection_key = ?
            """, (collection_key,))

            if cursor.fetchone():
                print(f"Cache already initialized for collection {collection_key}")
                conn.close()
                return True

            # Get collection info from API
            collection_data = self.zot.collection(collection_key)

            # Insert collection (set parent_key to NULL for now - will be set during sync)
            # Use INSERT OR IGNORE to avoid CASCADE DELETE of sync_state
            cursor.execute("""
                INSERT OR IGNORE INTO collections (collection_key, name, parent_key, version, last_synced)
                VALUES (?, ?, NULL, ?, ?)
            """, (
                collection_key,
                collection_data['data']['name'],
                collection_data['version'],
                datetime.now().isoformat()
            ))

            # Update if already exists
            cursor.execute("""
                UPDATE collections
                SET name = ?, version = ?, last_synced = ?
                WHERE collection_key = ?
            """, (
                collection_data['data']['name'],
                collection_data['version'],
                datetime.now().isoformat(),
                collection_key
            ))

            # Initialize sync state
            cursor.execute("""
                INSERT INTO sync_state (collection_key, last_sync_version, last_sync_time, full_sync_completed)
                VALUES (?, 0, NULL, FALSE)
            """, (collection_key,))

            conn.commit()
            conn.close()

            print(f"✓ Cache initialized for collection: {collection_data['data']['name']}")
            return True

        except Exception as e:
            print(f"✗ Failed to initialize cache: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return False

    def sync_collection(self, collection_key: str, include_subcollections: bool = True,
                       force_full: bool = False) -> Dict[str, int]:
        """
        Sync collection from Zotero to local cache

        Args:
            collection_key: Zotero collection key
            include_subcollections: Include subcollections in sync
            force_full: Force full sync (ignore version tracking)

        Returns:
            Dictionary with sync statistics
        """
        print(f"\n{'='*60}")
        print(f"Syncing collection to cache...")
        print(f"{'='*60}\n")

        stats = {
            'collections_synced': 0,
            'items_synced': 0,
            'attachments_downloaded': 0,
            'content_extracted': 0,
            'notes_synced': 0,
            'errors': 0
        }

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Get sync state (create if doesn't exist due to CASCADE DELETE)
            cursor.execute("""
                SELECT last_sync_version, full_sync_completed
                FROM sync_state
                WHERE collection_key = ?
            """, (collection_key,))

            sync_state = cursor.fetchone()
            if not sync_state:
                # Check if collection exists in collections table
                cursor.execute("""
                    SELECT collection_key FROM collections WHERE collection_key = ?
                """, (collection_key,))

                if not cursor.fetchone():
                    print("✗ Collection not initialized. Run --init-cache first.")
                    conn.close()
                    return stats

                # Collection exists but sync_state was deleted (CASCADE DELETE issue)
                # Recreate sync_state entry
                cursor.execute("""
                    INSERT INTO sync_state (collection_key, last_sync_version, last_sync_time, full_sync_completed)
                    VALUES (?, 0, NULL, FALSE)
                """, (collection_key,))
                conn.commit()

                # Re-fetch sync state
                cursor.execute("""
                    SELECT last_sync_version, full_sync_completed
                    FROM sync_state
                    WHERE collection_key = ?
                """, (collection_key,))
                sync_state = cursor.fetchone()

            last_version = sync_state['last_sync_version']
            full_sync_done = sync_state['full_sync_completed']

            # Determine sync mode
            if force_full or not full_sync_done:
                print("→ Running FULL SYNC (this may take a while)...")
                since_version = None
            else:
                print(f"→ Running INCREMENTAL SYNC (since version {last_version})...")
                since_version = last_version

            # Sync collection metadata
            # Two-pass approach to avoid foreign key constraint failures:
            # Pass 1: Insert all collections without parent relationships
            # Pass 2: Update parent relationships after all collections exist

            collection_data = self.zot.collection(collection_key)
            collections_to_sync = [(collection_key, collection_data)]

            # Get subcollections if requested
            collection_keys = [collection_key]
            if include_subcollections:
                subcollections = self.zot.collections_sub(collection_key)
                for subcol in subcollections:
                    collections_to_sync.append((subcol['key'], subcol))
                    collection_keys.append(subcol['key'])

            # Pass 1: Insert all collections with NULL parent_key (avoid CASCADE DELETE issues)
            for col_key, col_data in collections_to_sync:
                # Use INSERT OR IGNORE to avoid deleting existing row (which would CASCADE DELETE sync_state)
                cursor.execute("""
                    INSERT OR IGNORE INTO collections (collection_key, name, parent_key, version, last_synced)
                    VALUES (?, ?, NULL, ?, ?)
                """, (
                    col_key,
                    col_data['data']['name'],
                    col_data['version'],
                    datetime.now().isoformat()
                ))

                # Update existing row if it already exists
                cursor.execute("""
                    UPDATE collections
                    SET name = ?, version = ?, last_synced = ?
                    WHERE collection_key = ?
                """, (
                    col_data['data']['name'],
                    col_data['version'],
                    datetime.now().isoformat(),
                    col_key
                ))
                stats['collections_synced'] += 1

            # Pass 2: Update parent_key values
            for col_key, col_data in collections_to_sync:
                parent_key = col_data['data'].get('parentCollection')
                if parent_key:
                    cursor.execute("""
                        UPDATE collections SET parent_key = ? WHERE collection_key = ?
                    """, (parent_key, col_key))

            conn.commit()
            print(f"✓ Synced {stats['collections_synced']} collection(s)")

            # Sync items for each collection
            for col_key in collection_keys:
                col_name = cursor.execute("SELECT name FROM collections WHERE collection_key = ?",
                                         (col_key,)).fetchone()['name']
                print(f"\n→ Syncing items in: {col_name}")

                # Get items (with version filtering if incremental)
                # Use everything() to get all items across all pages
                items = self.zot.everything(self.zot.collection_items(col_key))

                for item in items:
                    try:
                        item_key = item['key']
                        item_type = item['data']['itemType']

                        # Skip notes and attachments (handled separately)
                        if item_type in ['note', 'attachment']:
                            continue

                        # Store item metadata (INSERT OR IGNORE to avoid CASCADE DELETE on attachments)
                        cursor.execute("""
                            INSERT OR IGNORE INTO items (
                                item_key, item_type, title, date, url, metadata, version, last_synced
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            item_key,
                            item_type,
                            item['data'].get('title', ''),
                            item['data'].get('date', ''),
                            item['data'].get('url', ''),
                            json.dumps(item['data']),
                            item['version'],
                            datetime.now().isoformat()
                        ))

                        # Update metadata if already exists
                        cursor.execute("""
                            UPDATE items
                            SET item_type = ?, title = ?, date = ?, url = ?, metadata = ?, version = ?, last_synced = ?
                            WHERE item_key = ?
                        """, (
                            item_type,
                            item['data'].get('title', ''),
                            item['data'].get('date', ''),
                            item['data'].get('url', ''),
                            json.dumps(item['data']),
                            item['version'],
                            datetime.now().isoformat(),
                            item_key
                        ))

                        # Add to collection_items
                        cursor.execute("""
                            INSERT OR IGNORE INTO collection_items (collection_key, item_key)
                            VALUES (?, ?)
                        """, (col_key, item_key))

                        stats['items_synced'] += 1

                        # Sync children (attachments and notes)
                        children = self.zot.children(item_key)
                        for child in children:
                            child_key = child['key']
                            child_type = child['data']['itemType']

                            if child_type == 'attachment':
                                # Store attachment metadata (INSERT OR IGNORE to preserve local_path)
                                cursor.execute("""
                                    INSERT OR IGNORE INTO attachments (
                                        attachment_key, parent_item_key, filename,
                                        content_type, local_path, version, last_synced
                                    ) VALUES (?, ?, ?, ?, NULL, ?, ?)
                                """, (
                                    child_key,
                                    item_key,
                                    child['data'].get('filename', ''),
                                    child['data'].get('contentType', ''),
                                    child['version'],
                                    datetime.now().isoformat()
                                ))

                                # Update metadata if already exists (preserve local_path if set)
                                cursor.execute("""
                                    UPDATE attachments
                                    SET filename = ?, content_type = ?, version = ?, last_synced = ?
                                    WHERE attachment_key = ?
                                """, (
                                    child['data'].get('filename', ''),
                                    child['data'].get('contentType', ''),
                                    child['version'],
                                    datetime.now().isoformat(),
                                    child_key
                                ))

                                # Download attachment file
                                if self._download_attachment_to_cache(cursor, item_key, child_key, child):
                                    stats['attachments_downloaded'] += 1

                            elif child_type == 'note':
                                # Store note
                                note_html = child['data'].get('note', '')
                                note_title = self.get_note_title_from_html(note_html)

                                cursor.execute("""
                                    INSERT OR REPLACE INTO notes (
                                        note_key, parent_item_key, title,
                                        content_html, version, last_synced
                                    ) VALUES (?, ?, ?, ?, ?, ?)
                                """, (
                                    child_key,
                                    item_key,
                                    note_title,
                                    note_html,
                                    child['version'],
                                    datetime.now().isoformat()
                                ))
                                stats['notes_synced'] += 1

                        # Extract content from attachments
                        if self._extract_content_to_cache(cursor, item_key):
                            stats['content_extracted'] += 1

                        # Progress indicator
                        if stats['items_synced'] % 10 == 0:
                            print(f"  • Synced {stats['items_synced']} items...", end='\r')

                    except Exception as e:
                        print(f"\n  ✗ Error syncing item {item.get('key', 'unknown')}: {e}")
                        if self.verbose:
                            import traceback
                            traceback.print_exc()
                        stats['errors'] += 1
                        continue

                print(f"  ✓ Synced {stats['items_synced']} items from {col_name}")

                # Commit after each collection to save progress and release locks
                conn.commit()

            # Sync standalone notes from all collections (main + subcollections)
            for col_key in collection_keys:
                try:
                    standalone_notes = self.zot.everything(self.zot.collection_items(col_key, itemType='note'))
                    if standalone_notes:
                        print(f"  → Syncing {len(standalone_notes)} standalone notes from collection {col_key}...")

                    for note in standalone_notes:
                        try:
                            note_key = note['key']
                            note_html = note['data'].get('note', '')
                            note_title = self.get_note_title_from_html(note_html)

                            cursor.execute("""
                                INSERT OR REPLACE INTO notes (
                                    note_key, parent_item_key, collection_key, title,
                                    content_html, version, last_synced
                                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                note_key,
                                None,
                                col_key,
                                note_title,
                                note_html,
                                note['version'],
                                datetime.now().isoformat()
                            ))

                            # Add to collection_items mapping
                            cursor.execute("""
                                INSERT OR IGNORE INTO collection_items (collection_key, item_key)
                                VALUES (?, ?)
                            """, (col_key, note_key))

                            stats['notes_synced'] += 1

                        except Exception as e:
                            print(f"  ✗ Error syncing note {note.get('key', 'unknown')}: {e}")
                            stats['errors'] += 1

                except Exception as e:
                    print(f"  ✗ Error getting notes from collection {col_key}: {e}")
                    if self.verbose:
                        import traceback
                        traceback.print_exc()
                    stats['errors'] += 1

            # Update sync state
            cursor.execute("""
                UPDATE sync_state
                SET last_sync_version = ?,
                    last_sync_time = ?,
                    full_sync_completed = TRUE
                WHERE collection_key = ?
            """, (
                collection_data['version'],
                datetime.now().isoformat(),
                collection_key
            ))

            conn.commit()
            conn.close()

            # Print summary
            print(f"\n{'='*60}")
            print("Sync completed!")
            print(f"{'='*60}")
            print(f"Collections synced: {stats['collections_synced']}")
            print(f"Items synced: {stats['items_synced']}")
            print(f"Attachments downloaded: {stats['attachments_downloaded']}")
            print(f"Content extracted: {stats['content_extracted']}")
            print(f"Notes synced: {stats['notes_synced']}")
            if stats['errors'] > 0:
                print(f"Errors: {stats['errors']}")
            print(f"{'='*60}\n")

            return stats

        except Exception as e:
            print(f"\n✗ Sync failed: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            stats['errors'] += 1
            return stats

    def _download_attachment_to_cache(self, cursor: sqlite3.Cursor, item_key: str,
                                     attachment_key: str, attachment_data: Dict) -> bool:
        """
        Download attachment file to cache

        Args:
            cursor: Database cursor to use (to avoid database locking)
            item_key: Parent item key
            attachment_key: Attachment key
            attachment_data: Attachment metadata from API

        Returns:
            True if successful
        """
        try:
            # Check if attachment already exists in cache
            cursor.execute("""
                SELECT local_path, file_hash FROM attachments
                WHERE attachment_key = ? AND local_path IS NOT NULL
            """, (attachment_key,))

            existing = cursor.fetchone()
            if existing and Path(existing['local_path']).exists():
                if self.verbose:
                    filename = Path(existing['local_path']).name
                    print(f"    ↻ Already cached: {filename}")
                return True  # Already downloaded and file exists

            # Get storage directory for item
            item_dir = self._get_item_storage_dir(item_key)

            # Download file
            content = self.download_attachment(attachment_key)
            if not content:
                return False

            # Save file
            filename = attachment_data['data'].get('filename', f'{attachment_key}.dat')
            file_path = item_dir / filename

            with open(file_path, 'wb') as f:
                f.write(content)

            # Compute hash
            file_hash = self._compute_file_hash(file_path)

            # Update database with local path and hash (using provided cursor)
            cursor.execute("""
                UPDATE attachments
                SET local_path = ?, file_hash = ?
                WHERE attachment_key = ?
            """, (str(file_path), file_hash, attachment_key))

            if self.verbose:
                print(f"    ✓ Downloaded: {filename}")

            return True

        except Exception as e:
            if self.verbose:
                print(f"    ✗ Failed to download attachment {attachment_key}: {e}")
            return False

    def _extract_content_to_cache(self, cursor: sqlite3.Cursor, item_key: str) -> bool:
        """
        Extract text content from item attachments and cache it

        Args:
            cursor: Database cursor to use (to avoid database locking)
            item_key: Item key

        Returns:
            True if content was extracted
        """
        try:
            # Check if already extracted
            cursor.execute("""
                SELECT item_key FROM extracted_content WHERE item_key = ?
            """, (item_key,))
            if cursor.fetchone():
                return False

            # Get attachments
            cursor.execute("""
                SELECT attachment_key, local_path, content_type, filename
                FROM attachments
                WHERE parent_item_key = ? AND local_path IS NOT NULL
            """, (item_key,))

            attachments = cursor.fetchall()
            if not attachments:
                return False

            # Try to extract from first suitable attachment
            for att in attachments:
                local_path = Path(att['local_path'])
                content_type = att['content_type'] or ''

                extracted_text = None
                method = None

                # Try HTML extraction
                if 'html' in content_type.lower() or local_path.suffix.lower() == '.html':
                    try:
                        with open(local_path, 'r', encoding='utf-8', errors='ignore') as f:
                            html_content = f.read()
                        extracted_text = self.extract_text_from_html(html_content)
                        method = 'trafilatura'
                    except Exception as e:
                        if self.verbose:
                            print(f"    ✗ HTML extraction failed: {e}")

                # Try PDF extraction
                elif 'pdf' in content_type.lower() or local_path.suffix.lower() == '.pdf':
                    try:
                        with open(local_path, 'rb') as f:
                            pdf_content = f.read()
                        extracted_text = self.extract_text_from_pdf(pdf_content)
                        method = 'pymupdf'
                    except Exception as e:
                        if self.verbose:
                            print(f"    ❌ Error extracting PDF text: {e}")

                # Try plain text
                elif 'text' in content_type.lower() or local_path.suffix.lower() == '.txt':
                    try:
                        with open(local_path, 'r', encoding='utf-8', errors='ignore') as f:
                            extracted_text = f.read()
                        method = 'plaintext'
                    except Exception as e:
                        if self.verbose:
                            print(f"    ✗ Text extraction failed: {e}")

                # Save extracted content
                if extracted_text and extracted_text.strip():
                    cursor.execute("""
                        INSERT INTO extracted_content (
                            item_key, extraction_method, extracted_text, extraction_date
                        ) VALUES (?, ?, ?, ?)
                    """, (
                        item_key,
                        method,
                        extracted_text,
                        datetime.now().isoformat()
                    ))

                    if self.verbose:
                        print(f"    ✓ Extracted content ({method}): {len(extracted_text)} chars")

                    return True

            return False

        except Exception as e:
            if self.verbose:
                print(f"    ✗ Content extraction failed for {item_key}: {e}")
            return False

    def get_cache_info(self, collection_key: str) -> Dict[str, Any]:
        """
        Get cache statistics for a collection

        Args:
            collection_key: Zotero collection key

        Returns:
            Dictionary with cache statistics
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Get sync state
            cursor.execute("""
                SELECT last_sync_version, last_sync_time, full_sync_completed
                FROM sync_state
                WHERE collection_key = ?
            """, (collection_key,))

            sync_state = cursor.fetchone()
            if not sync_state:
                return {'error': 'Collection not cached'}

            # Get collection name
            cursor.execute("""
                SELECT name FROM collections WHERE collection_key = ?
            """, (collection_key,))
            col = cursor.fetchone()
            collection_name = col['name'] if col else 'Unknown'

            # Count items
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM collection_items
                WHERE collection_key = ?
            """, (collection_key,))
            item_count = cursor.fetchone()['count']

            # Count attachments
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM attachments a
                JOIN collection_items ci ON a.parent_item_key = ci.item_key
                WHERE ci.collection_key = ?
            """, (collection_key,))
            attachment_count = cursor.fetchone()['count']

            # Count extracted content
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM extracted_content ec
                JOIN collection_items ci ON ec.item_key = ci.item_key
                WHERE ci.collection_key = ?
            """, (collection_key,))
            extracted_count = cursor.fetchone()['count']

            # Count notes
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM notes
                WHERE collection_key = ? OR parent_item_key IN (
                    SELECT item_key FROM collection_items WHERE collection_key = ?
                )
            """, (collection_key, collection_key))
            note_count = cursor.fetchone()['count']

            # Calculate storage size
            total_size = 0
            for item_dir in self.files_dir.iterdir():
                if item_dir.is_dir():
                    for file in item_dir.rglob('*'):
                        if file.is_file():
                            total_size += file.stat().st_size

            conn.close()

            return {
                'collection_name': collection_name,
                'collection_key': collection_key,
                'last_sync_time': sync_state['last_sync_time'],
                'last_sync_version': sync_state['last_sync_version'],
                'full_sync_completed': bool(sync_state['full_sync_completed']),
                'item_count': item_count,
                'attachment_count': attachment_count,
                'extracted_count': extracted_count,
                'note_count': note_count,
                'storage_size_mb': round(total_size / (1024 * 1024), 2),
                'cache_dir': str(self.cache_dir)
            }

        except Exception as e:
            return {'error': str(e)}

    def get_cached_items(self, collection_key: str,
                        subcollections: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Get all items from cache for a collection

        Args:
            collection_key: Collection key
            subcollections: Optional list of subcollection names to filter

        Returns:
            List of item dictionaries with metadata
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Build query based on subcollection filter
            if subcollections:
                # Get subcollection keys
                placeholders = ','.join('?' * len(subcollections))
                cursor.execute(f"""
                    SELECT collection_key FROM collections
                    WHERE parent_key = ? AND name IN ({placeholders})
                """, [collection_key] + subcollections)
                subcol_keys = [row['collection_key'] for row in cursor.fetchall()]

                if not subcol_keys:
                    conn.close()
                    return []

                # Query items from subcollections
                placeholders = ','.join('?' * len(subcol_keys))
                cursor.execute(f"""
                    SELECT DISTINCT i.*, ci.collection_key
                    FROM items i
                    JOIN collection_items ci ON i.item_key = ci.item_key
                    WHERE ci.collection_key IN ({placeholders})
                """, subcol_keys)
            else:
                # Query items from main collection
                cursor.execute("""
                    SELECT i.*, ci.collection_key
                    FROM items i
                    JOIN collection_items ci ON i.item_key = ci.item_key
                    WHERE ci.collection_key = ?
                """, (collection_key,))

            items = []
            for row in cursor.fetchall():
                item = dict(row)
                # Parse metadata JSON
                if item['metadata']:
                    item['data'] = json.loads(item['metadata'])
                items.append(item)

            conn.close()
            return items

        except Exception as e:
            print(f"✗ Error getting cached items: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return []

    def get_cached_content(self, item_key: str) -> Optional[str]:
        """
        Get cached extracted content for an item

        Args:
            item_key: Item key

        Returns:
            Extracted text content or None
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT extracted_text FROM extracted_content WHERE item_key = ?
            """, (item_key,))

            row = cursor.fetchone()
            conn.close()

            return row['extracted_text'] if row else None

        except Exception as e:
            if self.verbose:
                print(f"✗ Error getting cached content: {e}")
            return None

    def get_cached_attachments(self, item_key: str) -> List[Dict[str, Any]]:
        """
        Get all attachments for an item from cache

        Args:
            item_key: Parent item key

        Returns:
            List of attachment dictionaries with metadata
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM attachments WHERE parent_key = ?
            """, (item_key,))

            attachments = [dict(row) for row in cursor.fetchall()]
            conn.close()

            return attachments

        except Exception as e:
            if self.verbose:
                print(f"✗ Error getting cached attachments: {e}")
            return []

    def get_cached_notes_for_item(self, item_key: str, title_prefix: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get child notes for an item from cache

        Args:
            item_key: Parent item key
            title_prefix: Optional title prefix to filter notes (e.g., "【ZResearcher Summary:")

        Returns:
            List of note dictionaries with content
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            if title_prefix:
                # Filter by title prefix
                cursor.execute("""
                    SELECT * FROM notes
                    WHERE parent_item_key = ? AND title LIKE ?
                    ORDER BY last_synced DESC
                """, (item_key, f"{title_prefix}%"))
            else:
                # Get all child notes
                cursor.execute("""
                    SELECT * FROM notes WHERE parent_item_key = ?
                    ORDER BY last_synced DESC
                """, (item_key,))

            notes = [dict(row) for row in cursor.fetchall()]
            conn.close()

            return notes

        except Exception as e:
            if self.verbose:
                print(f"✗ Error getting cached notes: {e}")
            return []

    def get_cached_attachment_content(self, attachment_key: str) -> Optional[str]:
        """
        Read attachment file content from cache

        Args:
            attachment_key: Attachment key

        Returns:
            File path to cached attachment, or None if not found
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT local_path, parent_key FROM attachments WHERE attachment_key = ?
            """, (attachment_key,))

            row = cursor.fetchone()
            conn.close()

            if row and row['local_path']:
                file_path = self.cache_dir / row['local_path']
                if file_path.exists():
                    return str(file_path)

            return None

        except Exception as e:
            if self.verbose:
                print(f"✗ Error getting cached attachment content: {e}")
            return None

    def get_item_metadata(self, item_key: str) -> Optional[Dict[str, Any]]:
        """
        Get full item metadata from cache

        Args:
            item_key: Item key

        Returns:
            Item dictionary with metadata, or None if not found
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM items WHERE item_key = ?
            """, (item_key,))

            row = cursor.fetchone()
            conn.close()

            if row:
                item = dict(row)
                # Parse metadata JSON
                if item['metadata']:
                    item['data'] = json.loads(item['metadata'])
                return item

            return None

        except Exception as e:
            if self.verbose:
                print(f"✗ Error getting item metadata: {e}")
            return None

    def get_standalone_notes(self, collection_key: str, title_prefix: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get standalone notes in a collection from cache

        Args:
            collection_key: Collection key
            title_prefix: Optional title prefix to filter notes

        Returns:
            List of note dictionaries
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            if title_prefix:
                # Filter by title prefix and collection
                cursor.execute("""
                    SELECT n.* FROM notes n
                    JOIN collection_items ci ON n.note_key = ci.item_key
                    WHERE ci.collection_key = ? AND n.parent_item_key IS NULL AND n.title LIKE ?
                    ORDER BY n.last_synced DESC
                """, (collection_key, f"{title_prefix}%"))
            else:
                # Get all standalone notes in collection
                cursor.execute("""
                    SELECT n.* FROM notes n
                    JOIN collection_items ci ON n.note_key = ci.item_key
                    WHERE ci.collection_key = ? AND n.parent_item_key IS NULL
                    ORDER BY n.last_synced DESC
                """, (collection_key,))

            notes = [dict(row) for row in cursor.fetchall()]
            conn.close()

            return notes

        except Exception as e:
            if self.verbose:
                print(f"✗ Error getting standalone notes: {e}")
            return []
