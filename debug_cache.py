#!/usr/bin/env python3
"""Debug script to test cache detection"""

import sqlite3
from pathlib import Path

def check_cache_exists(collection_key: str, cache_dir: str = None) -> bool:
    """Check if a valid cache exists for the given collection."""
    cache_path = Path(cache_dir) if cache_dir else Path(".zotero_cache")
    db_path = cache_path / "store.db"

    print(f"Checking cache at: {cache_path.absolute()}")
    print(f"Database path: {db_path.absolute()}")
    print(f"Database exists: {db_path.exists()}")

    # Check if database exists
    if not db_path.exists():
        print("❌ Database file not found")
        return False

    # Check if collection has been synced
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check all collections in sync_state
        cursor.execute("SELECT collection_key, last_synced FROM sync_state")
        all_syncs = cursor.fetchall()
        print(f"\nAll synced collections in database:")
        for row in all_syncs:
            print(f"  - {row[0]}: {row[1]}")

        # Check for specific collection
        cursor.execute("""
            SELECT last_synced FROM sync_state
            WHERE collection_key = ?
        """, (collection_key,))
        result = cursor.fetchone()
        conn.close()

        print(f"\nLooking for collection: {collection_key}")
        print(f"Found: {result}")

        # Cache exists and has been synced at least once
        if result is not None and result[0] is not None:
            print("✅ Cache is valid and synced")
            return True
        else:
            print("❌ Collection not found in sync_state")
            return False

    except Exception as e:
        print(f"❌ Error checking cache: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import sys
    collection_key = sys.argv[1] if len(sys.argv) > 1 else "C9UYUHY7"
    cache_dir = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"Testing cache detection for collection: {collection_key}")
    print(f"Current working directory: {Path.cwd()}")
    print("=" * 60)

    result = check_cache_exists(collection_key, cache_dir)

    print("=" * 60)
    print(f"Result: {'CACHE DETECTED' if result else 'NO CACHE'}")
