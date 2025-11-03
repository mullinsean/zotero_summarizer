#!/usr/bin/env python3
"""
Zotero Library Diagnostic Tool

This script helps diagnose connection issues and shows you what's available
in your Zotero library (user or group).
"""

import os
import sys
from pyzotero import zotero


def diagnose_library(library_id, library_type, api_key):
    """Run diagnostic checks on a Zotero library."""
    
    print("="*70)
    print("ZOTERO LIBRARY DIAGNOSTIC")
    print("="*70)
    print(f"\nConfiguration:")
    print(f"  Library ID: {library_id}")
    print(f"  Library Type: {library_type}")
    print(f"  API Key: {'*' * (len(api_key) - 4) + api_key[-4:]}")
    print()
    
    try:
        # Initialize Zotero client
        print("Connecting to Zotero API...")
        zot = zotero.Zotero(library_id, library_type, api_key)
        print("✓ Connection successful\n")
        
        # Test 1: Get library info
        print("-" * 70)
        print("TEST 1: Library Access")
        print("-" * 70)
        try:
            # Try to get some items to verify access
            items = zot.items(limit=5)
            print(f"✓ Can access library")
            print(f"  Sample items retrieved: {len(items)}")
        except Exception as e:
            print(f"✗ Cannot access library: {e}")
            return
        
        # Test 2: List collections
        print("\n" + "-" * 70)
        print("TEST 2: Collections")
        print("-" * 70)
        try:
            collections = zot.collections()
            print(f"✓ Found {len(collections)} collection(s)")
            
            if collections:
                print("\nAvailable Collections:")
                print()
                for col in collections:
                    name = col['data'].get('name', 'Unnamed')
                    key = col['key']
                    parent = col['data'].get('parentCollection', None)
                    num_items = col['meta'].get('numItems', 0)
                    
                    indent = "  "
                    if parent:
                        indent = "    "  # Indent sub-collections
                    
                    print(f"{indent}📁 {name}")
                    print(f"{indent}   Key: {key}")
                    print(f"{indent}   Items: {num_items}")
                    if parent:
                        print(f"{indent}   (Sub-collection)")
                    print()
            else:
                print("  No collections found in this library")
        except Exception as e:
            print(f"✗ Cannot access collections: {e}")
        
        # Test 3: List groups (only relevant for user libraries)
        if library_type == 'user':
            print("-" * 70)
            print("TEST 3: Group Memberships")
            print("-" * 70)
            try:
                groups = zot.groups()
                if groups:
                    print(f"✓ You are a member of {len(groups)} group(s):")
                    print()
                    for group in groups:
                        group_id = group['id']
                        group_name = group['data'].get('name', 'Unnamed Group')
                        group_type = group['data'].get('type', 'Unknown')
                        
                        print(f"  👥 {group_name}")
                        print(f"     Group ID: {group_id}")
                        print(f"     Type: {group_type}")
                        print(f"     URL: https://www.zotero.org/groups/{group_id}")
                        print()
                        print(f"     To access this group's collections, use:")
                        print(f"       export ZOTERO_LIBRARY_ID='{group_id}'")
                        print(f"       export ZOTERO_LIBRARY_TYPE='group'")
                        print()
                else:
                    print("  You are not a member of any groups")
            except Exception as e:
                print(f"  Cannot retrieve groups: {e}")
        
        print("="*70)
        print("Diagnostic complete!")
        print("="*70)
        
    except Exception as e:
        print(f"\n✗ Error connecting to Zotero: {e}")
        print("\nPossible issues:")
        print("  1. Invalid API key")
        print("  2. Wrong library ID for the library type")
        print("  3. API key doesn't have proper permissions")
        print("  4. Network connection issue")


def main():
    """Main execution function."""
    
    print("\n" + "="*70)
    print("ZOTERO DIAGNOSTIC TOOL")
    print("="*70)
    print("\nThis tool will help you:")
    print("  1. Test your Zotero API connection")
    print("  2. List available collections")
    print("  3. Find your group IDs (if any)")
    print()
    
    # Get configuration
    LIBRARY_ID = os.environ.get('ZOTERO_LIBRARY_ID')
    LIBRARY_TYPE = os.environ.get('ZOTERO_LIBRARY_TYPE', 'user')
    API_KEY = os.environ.get('ZOTERO_API_KEY')
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == '--help':
            print("\nUsage:")
            print("  python zotero_diagnose.py [--user | --group GROUP_ID]")
            print("\nExamples:")
            print("  # Diagnose user library")
            print("  export ZOTERO_API_KEY='your_api_key'")
            print("  export ZOTERO_LIBRARY_ID='your_user_id'")
            print("  python zotero_diagnose.py --user")
            print()
            print("  # Diagnose group library")
            print("  export ZOTERO_API_KEY='your_api_key'")
            print("  python zotero_diagnose.py --group 12345")
            return
        
        if sys.argv[1] == '--user':
            LIBRARY_TYPE = 'user'
            if not LIBRARY_ID:
                print("Error: Please set ZOTERO_LIBRARY_ID to your user ID")
                print("Find it at: https://www.zotero.org/settings/keys")
                return
        elif sys.argv[1] == '--group':
            LIBRARY_TYPE = 'group'
            if len(sys.argv) < 3:
                print("Error: Please provide the group ID")
                print("Usage: python zotero_diagnose.py --group GROUP_ID")
                return
            LIBRARY_ID = sys.argv[2]
    
    # Validate we have credentials
    if not API_KEY:
        print("Error: ZOTERO_API_KEY not set")
        print("\nPlease set your API key:")
        print("  export ZOTERO_API_KEY='your_api_key'")
        print("\nGet your API key from: https://www.zotero.org/settings/keys")
        return
    
    if not LIBRARY_ID:
        print("Error: ZOTERO_LIBRARY_ID not set")
        print("\nFor user library:")
        print("  export ZOTERO_LIBRARY_ID='your_user_id'")
        print("  export ZOTERO_LIBRARY_TYPE='user'")
        print("\nFor group library:")
        print("  export ZOTERO_LIBRARY_ID='group_id'")
        print("  export ZOTERO_LIBRARY_TYPE='group'")
        print("\nOr use: python zotero_diagnose.py --user")
        print("        python zotero_diagnose.py --group GROUP_ID")
        return
    
    # Run diagnostics
    diagnose_library(LIBRARY_ID, LIBRARY_TYPE, API_KEY)


if __name__ == '__main__':
    main()