#!/usr/bin/env python3
"""
Utility script to list and delete Google Gemini File Search Stores.

This helps free up your 1GB free tier storage quota by removing old stores.

File Search stores do NOT auto-expire - they persist until you delete them.
Uses force=true to delete non-empty stores (removes all documents inside).

Usage:
    # List all stores
    python cleanup_gemini_stores.py --list

    # Delete all stores (force deletes non-empty stores)
    python cleanup_gemini_stores.py --delete-all

    # Delete specific store
    python cleanup_gemini_stores.py --delete STORE_NAME
"""

import os
import sys
import argparse
from dotenv import load_dotenv

def list_stores(client):
    """List all file search stores for this API key."""
    try:
        print("\n" + "="*80)
        print("File Search Stores")
        print("="*80 + "\n")

        stores = client.file_search_stores.list()

        if not stores:
            print("No file search stores found.\n")
            return []

        store_list = []
        for idx, store in enumerate(stores, 1):
            print(f"{idx}. {store.name}")
            if hasattr(store, 'display_name') and store.display_name:
                print(f"   Display Name: {store.display_name}")
            print()
            store_list.append(store)

        print(f"Total: {len(store_list)} store(s)")
        print("="*80 + "\n")

        return store_list

    except Exception as e:
        print(f"❌ Error listing stores: {e}")
        return []

def delete_store(client, store_name):
    """Delete a specific file search store.

    Args:
        client: Gemini client
        store_name: Name of the store to delete
    """
    try:
        print(f"Deleting store: {store_name}...")

        # Delete using config={'force': True} to handle non-empty stores
        client.file_search_stores.delete(name=store_name, config={'force': True})
        print(f"✅ Deleted successfully\n")
        return True

    except Exception as e:
        print(f"❌ Error deleting store: {e}\n")
        return False

def delete_all_stores(client):
    """Delete all file search stores."""
    stores = list_stores(client)

    if not stores:
        return

    # Confirm deletion
    response = input(f"⚠️  Delete ALL {len(stores)} store(s)? This cannot be undone! (yes/no): ")
    if response.lower() != 'yes':
        print("Cancelled.")
        return

    print()
    deleted = 0
    failed = 0

    for store in stores:
        if delete_store(client, store.name):
            deleted += 1
        else:
            failed += 1

    print("="*80)
    print(f"Cleanup Summary")
    print("="*80)
    print(f"  Deleted: {deleted}")
    print(f"  Failed: {failed}")
    print("="*80 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Manage Google Gemini File Search Stores")
    parser.add_argument('--list', action='store_true', help='List all file search stores')
    parser.add_argument('--delete-all', action='store_true', help='Delete all file search stores')
    parser.add_argument('--delete', metavar='STORE_NAME', help='Delete specific store by name')

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()
    gemini_api_key = os.getenv('GEMINI_API_KEY')

    if not gemini_api_key:
        print("❌ GEMINI_API_KEY not found in environment variables")
        print("   Make sure your .env file contains: GEMINI_API_KEY=your_key_here")
        sys.exit(1)

    # Initialize Gemini client
    try:
        from google import genai
        client = genai.Client(api_key=gemini_api_key)
    except ImportError:
        print("❌ google-genai package not found")
        print("   Install it with: uv pip install google-genai")
        sys.exit(1)

    # Execute command
    if args.list:
        list_stores(client)
    elif args.delete_all:
        delete_all_stores(client)
    elif args.delete:
        delete_store(client, args.delete)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
