#!/usr/bin/env python3
"""
ZoteroResearcher Cleanup Module

Handles cleanup of ZResearcher projects and summary notes.
"""

import sys
from typing import Dict, List, Optional

# Handle both relative and absolute imports
try:
    from .zr_common import ZoteroResearcherBase
except ImportError:
    from zr_common import ZoteroResearcherBase


class ZoteroResearcherCleaner(ZoteroResearcherBase):
    """Handles cleanup of ZResearcher projects and notes"""

    def __init__(
        self,
        library_id: str,
        library_type: str,
        api_key: str,
        anthropic_api_key: str,
        project_name: str = None,
        verbose: bool = False
    ):
        """
        Initialize the cleanup handler.

        Args:
            library_id: Your Zotero user ID or group ID
            library_type: 'user' or 'group'
            api_key: Your Zotero API key
            anthropic_api_key: Anthropic API key (required for base class, not used in cleanup)
            project_name: Name of the project to clean up (optional for collection-wide cleanup)
            verbose: If True, show detailed information
        """
        super().__init__(
            library_id=library_id,
            library_type=library_type,
            api_key=api_key,
            anthropic_api_key=anthropic_api_key,
            project_name=project_name,
            verbose=verbose
        )

    def is_general_summary_note(self, note_html: str, project_name: str = None) -> bool:
        """
        Check if a note is a General Summary note (optionally for a specific project).

        Args:
            note_html: HTML content of the note
            project_name: Optional project name to filter by

        Returns:
            True if note is a general summary (for the specified project if provided)
        """
        # Check structure: should start with the summary heading
        title = self.get_note_title_from_html(note_html)

        # Modern format: 【ZResearcher Summary: PROJECT_NAME】
        if project_name:
            expected_title = f"【ZResearcher Summary: {project_name}】"
            if expected_title not in title:
                return False
        else:
            # Check if it matches the pattern for any project
            if not ('【ZResearcher Summary:' in title and '】' in title):
                return False

        # Verify it has the expected structure
        text = self.extract_text_from_note_html(note_html)
        required_sections = ['## Metadata', '## Tags', '## Summary']

        return all(section in text for section in required_sections)

    def find_general_summary_notes_for_project(
        self,
        collection_key: str,
        project_name: str
    ) -> List[Dict]:
        """
        Find all general summary notes for a specific project in a collection.

        Searches both:
        - Standalone notes in the collection
        - Child notes attached to items (created by --build-summaries)

        Args:
            collection_key: The collection key
            project_name: The project name to filter by

        Returns:
            List of note items that are general summaries for this project
        """
        items = self.get_collection_items(collection_key)
        summary_notes = []

        if self.verbose:
            print(f"  Scanning {len(items)} items for summary notes...")

        for item in items:
            item_data = item['data']
            item_type = item_data.get('itemType')

            # Check if this item itself is a standalone note
            if item_type == 'note':
                note_html = item_data.get('note', '')
                if self.is_general_summary_note(note_html, project_name):
                    summary_notes.append(item)

            # Also check child notes attached to this item
            elif item_type not in ['note', 'attachment']:
                # Get child items (notes and attachments)
                item_key = item['key']
                try:
                    children = self.zot.children(item_key)
                    for child in children:
                        child_data = child['data']
                        if child_data.get('itemType') == 'note':
                            note_html = child_data.get('note', '')
                            if self.is_general_summary_note(note_html, project_name):
                                summary_notes.append(child)
                except Exception as e:
                    if self.verbose:
                        print(f"  ⚠️  Error checking children for {item_key}: {e}")

        return summary_notes

    def find_all_general_summary_notes(self, collection_key: str) -> List[Dict]:
        """
        Find all general summary notes in a collection (for any project).

        Searches both:
        - Standalone notes in the collection
        - Child notes attached to items (created by --build-summaries)

        Args:
            collection_key: The collection key

        Returns:
            List of note items that are general summaries
        """
        items = self.get_collection_items(collection_key)
        summary_notes = []

        if self.verbose:
            print(f"  Scanning {len(items)} items for summary notes...")

        for item in items:
            item_data = item['data']
            item_type = item_data.get('itemType')

            # Check if this item itself is a standalone note
            if item_type == 'note':
                note_html = item_data.get('note', '')
                if self.is_general_summary_note(note_html):
                    summary_notes.append(item)

            # Also check child notes attached to this item
            elif item_type not in ['note', 'attachment']:
                # Get child items (notes and attachments)
                item_key = item['key']
                try:
                    children = self.zot.children(item_key)
                    for child in children:
                        child_data = child['data']
                        if child_data.get('itemType') == 'note':
                            note_html = child_data.get('note', '')
                            if self.is_general_summary_note(note_html):
                                summary_notes.append(child)
                except Exception as e:
                    if self.verbose:
                        print(f"  ⚠️  Error checking children for {item_key}: {e}")

        return summary_notes

    def find_all_project_subcollections(self, parent_collection_key: str) -> List[Dict]:
        """
        Find all ZResearcher project subcollections.

        Args:
            parent_collection_key: The parent collection key

        Returns:
            List of dicts with keys: 'key', 'name', 'project_name'
        """
        collections = self.zot.collections_sub(parent_collection_key)

        project_subcollections = []
        for coll in collections:
            name = coll['data']['name']
            # Match pattern: 【ZResearcher: *】
            if name.startswith('【ZResearcher: ') and name.endswith('】'):
                project_name = name[len('【ZResearcher: '):-1]
                project_subcollections.append({
                    'key': coll['key'],
                    'name': name,
                    'project_name': project_name
                })

        return project_subcollections

    def count_items_in_collection(self, collection_key: str) -> Dict[str, int]:
        """
        Count items in a collection by type.

        Args:
            collection_key: The collection key

        Returns:
            Dict with counts: {'notes': N, 'files': N, 'items': N, 'total': N}
        """
        try:
            items = self.zot.everything(self.zot.collection_items(collection_key))

            counts = {'notes': 0, 'files': 0, 'items': 0, 'total': 0}

            for item in items:
                item_type = item['data'].get('itemType', 'unknown')
                if item_type == 'note':
                    counts['notes'] += 1
                elif item_type == 'attachment':
                    counts['files'] += 1
                else:
                    counts['items'] += 1
                counts['total'] += 1

            return counts
        except Exception as e:
            if self.verbose:
                print(f"  ⚠️  Error counting items: {e}")
            return {'notes': 0, 'files': 0, 'items': 0, 'total': 0}

    def preview_cleanup(
        self,
        subcollections: List[Dict],
        summary_notes: List[Dict],
        collection_name: str = "this collection"
    ) -> None:
        """
        Display a preview of what will be deleted.

        Args:
            subcollections: List of project subcollections to delete
            summary_notes: List of general summary notes to delete
            collection_name: Name of the collection for display
        """
        print()
        print(f"Scanning collection '{collection_name}'...\n")

        # Show subcollections and their contents
        for subcoll in subcollections:
            print(f"Found project: {subcoll['name']}")
            counts = self.count_items_in_collection(subcoll['key'])
            print(f"  ├─ {counts['notes']} notes")
            print(f"  ├─ {counts['files']} file attachments")
            print(f"  └─ {counts['items']} other items")
            print()

        # Show summary notes count
        if summary_notes:
            print(f"Found {len(summary_notes)} general summary notes in parent collection\n")

        # Calculate totals
        total_subcollections = len(subcollections)
        total_subcollection_items = sum(
            self.count_items_in_collection(sc['key'])['total']
            for sc in subcollections
        )
        total_summary_notes = len(summary_notes)

        # Display deletion summary
        print("┌─────────────────────────────────────────────┐")
        print("│ THIS WILL PERMANENTLY DELETE:                │")
        if total_subcollections > 0:
            print(f"│  • {total_subcollections} subcollection(s)                       │")
            print(f"│  • {total_subcollection_items} item(s) in subcollections          │")
        if total_summary_notes > 0:
            print(f"│  • {total_summary_notes} general summary note(s)          │")
        print("└─────────────────────────────────────────────┘")
        print()

    def confirm_cleanup(self) -> bool:
        """
        Ask user for confirmation before deleting.

        Returns:
            True if user confirms, False otherwise
        """
        try:
            response = input("Are you sure? (y/N): ").strip().lower()
            return response in ['y', 'yes']
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return False

    def delete_gemini_files_for_project(self, collection_key: str, gemini_api_key: str = None) -> Dict[str, any]:
        """
        Delete Gemini file search store for this project.

        Args:
            collection_key: Parent collection key
            gemini_api_key: Google Gemini API key (optional, will try to load from env)

        Returns:
            Dict with deletion results: {'deleted': N, 'errors': [...]}
        """
        result = {'deleted': 0, 'errors': []}

        # Get Gemini API key
        if not gemini_api_key:
            import os
            gemini_api_key = os.getenv('GEMINI_API_KEY')

        if not gemini_api_key:
            if self.verbose:
                print("  ℹ️  No GEMINI_API_KEY found, skipping Gemini cleanup")
            return result

        try:
            # Initialize Gemini client
            try:
                from google import genai
                genai_client = genai.Client(api_key=gemini_api_key)
            except ImportError:
                if self.verbose:
                    print("  ⚠️  google-genai package not found, skipping Gemini cleanup")
                return result

            # Load project config to get file search store
            try:
                config = self.load_project_config_from_zotero(collection_key)
            except (FileNotFoundError, ValueError):
                # No config found, nothing to delete
                if self.verbose:
                    print("  ℹ️  No project config found, no Gemini store to delete")
                return result

            # Get file search store name
            store_name = config.get('gemini_file_search_store', '')
            if not store_name:
                if self.verbose:
                    print("  ℹ️  No Gemini file search store found in project config")
                return result

            # Delete the file search store (this deletes all files in it)
            print(f"  🗑️  Deleting Gemini file search store...")
            try:
                genai_client.file_search_stores.delete(name=store_name)
                result['deleted'] = 1
                if self.verbose:
                    print(f"    ✅ Deleted store: {store_name}")
            except Exception as e:
                error_msg = f"Failed to delete Gemini file search store {store_name}: {e}"
                result['errors'].append(error_msg)
                if self.verbose:
                    print(f"    ⚠️  {error_msg}")

        except Exception as e:
            error_msg = f"Error during Gemini cleanup: {e}"
            result['errors'].append(error_msg)
            if self.verbose:
                print(f"  ⚠️  {error_msg}")

        return result

    def delete_collection_recursive(self, collection_key: str) -> Dict[str, any]:
        """
        Delete a collection and all its contents recursively.

        Args:
            collection_key: The collection key to delete

        Returns:
            Dict with deletion results: {'notes': N, 'files': N, 'items': N, 'errors': [...]}
        """
        deleted = {'notes': 0, 'files': 0, 'items': 0, 'errors': []}

        try:
            # Get all items in collection (including children)
            items = self.zot.everything(self.zot.collection_items(collection_key))

            # Delete each item
            for item in items:
                try:
                    item_key = item['key']
                    item_type = item['data'].get('itemType', 'unknown')

                    self.zot.delete_item(item)

                    if item_type == 'note':
                        deleted['notes'] += 1
                    elif item_type == 'attachment':
                        deleted['files'] += 1
                    else:
                        deleted['items'] += 1

                except Exception as e:
                    error_msg = f"Failed to delete item {item.get('key', 'unknown')}: {e}"
                    deleted['errors'].append(error_msg)
                    if self.verbose:
                        print(f"  ⚠️  {error_msg}")

            # Delete the collection itself
            try:
                # Retrieve collection object (pyzotero requires the full object, not just the key)
                collection = self.zot.collection(collection_key)
                self.zot.delete_collection(collection)
            except Exception as e:
                error_msg = f"Failed to delete collection {collection_key}: {e}"
                deleted['errors'].append(error_msg)
                if self.verbose:
                    print(f"  ⚠️  {error_msg}")

        except Exception as e:
            error_msg = f"Failed to retrieve collection items: {e}"
            deleted['errors'].append(error_msg)
            if self.verbose:
                print(f"  ⚠️  {error_msg}")

        return deleted

    def cleanup_project(
        self,
        collection_key: str,
        project_name: str,
        dry_run: bool = False,
        skip_confirm: bool = False
    ) -> None:
        """
        Clean up a specific project (delete subcollection and summary notes).

        Args:
            collection_key: Parent collection key
            project_name: Name of project to clean up
            dry_run: If True, show preview without deleting
            skip_confirm: If True, skip confirmation prompt
        """
        print(f"\n🧹 Cleanup Project: {project_name}")
        print("=" * 60)

        # Find project subcollection
        self.project_name = project_name
        subcollection_name = self._get_subcollection_name()
        subcollection_key = self.get_subcollection(collection_key, subcollection_name)

        subcollections = []
        if subcollection_key:
            subcollections = [{
                'key': subcollection_key,
                'name': subcollection_name,
                'project_name': project_name
            }]
        else:
            print(f"⚠️  Warning: {subcollection_name} not found")

        # Find general summary notes for this project
        summary_notes = self.find_general_summary_notes_for_project(
            collection_key,
            project_name
        )

        # Check if anything to delete
        if not subcollections and not summary_notes:
            print(f"\n✅ No ZResearcher data found for project '{project_name}'")
            return

        # Get collection name for display
        try:
            collection = self.zot.collection(collection_key)
            collection_name = collection['data']['name']
        except:
            collection_name = collection_key

        # Show preview
        self.preview_cleanup(subcollections, summary_notes, collection_name)

        if dry_run:
            print("🔍 DRY RUN: No changes made")
            return

        # Confirm deletion
        if not skip_confirm:
            if not self.confirm_cleanup():
                print("❌ Cleanup cancelled")
                return

        # Perform deletion
        print("\n🗑️  Deleting items...")
        total_deleted = {'notes': 0, 'files': 0, 'items': 0, 'gemini_files': 0, 'errors': []}

        # Delete Gemini files first (if any)
        if subcollections:
            gemini_result = self.delete_gemini_files_for_project(collection_key)
            total_deleted['gemini_files'] += gemini_result['deleted']
            total_deleted['errors'].extend(gemini_result['errors'])

        # Delete subcollection and contents
        for subcoll in subcollections:
            print(f"\n  Deleting {subcoll['name']}...")
            result = self.delete_collection_recursive(subcoll['key'])
            total_deleted['notes'] += result['notes']
            total_deleted['files'] += result['files']
            total_deleted['items'] += result['items']
            total_deleted['errors'].extend(result['errors'])

        # Delete general summary notes
        if summary_notes:
            print(f"\n  Deleting {len(summary_notes)} general summary notes...")
            for note in summary_notes:
                try:
                    self.zot.delete_item(note)
                    total_deleted['notes'] += 1
                except Exception as e:
                    error_msg = f"Failed to delete note {note.get('key', 'unknown')}: {e}"
                    total_deleted['errors'].append(error_msg)
                    if self.verbose:
                        print(f"  ⚠️  {error_msg}")

        # Report results
        print("\n" + "=" * 60)
        print("✅ Cleanup Complete\n")
        print(f"Deleted:")
        if total_deleted['gemini_files'] > 0:
            print(f"  • {total_deleted['gemini_files']} Gemini files")
        print(f"  • {total_deleted['notes']} notes")
        print(f"  • {total_deleted['files']} file attachments")
        print(f"  • {total_deleted['items']} other items")

        if total_deleted['errors']:
            print(f"\n⚠️  {len(total_deleted['errors'])} errors occurred:")
            for error in total_deleted['errors'][:5]:  # Show first 5 errors
                print(f"  • {error}")
            if len(total_deleted['errors']) > 5:
                print(f"  ... and {len(total_deleted['errors']) - 5} more errors")
        print()

    def cleanup_all_projects(
        self,
        collection_key: str,
        dry_run: bool = False,
        skip_confirm: bool = False
    ) -> None:
        """
        Clean up ALL projects in a collection (delete all ZResearcher data).

        Args:
            collection_key: Parent collection key
            dry_run: If True, show preview without deleting
            skip_confirm: If True, skip confirmation prompt
        """
        print("\n🧹 Cleanup ALL Projects in Collection")
        print("=" * 60)

        # Find all project subcollections
        subcollections = self.find_all_project_subcollections(collection_key)

        # Find all general summary notes
        summary_notes = self.find_all_general_summary_notes(collection_key)

        # Check if anything to delete
        if not subcollections and not summary_notes:
            print("\n✅ No ZResearcher data found in this collection")
            return

        # Get collection name for display
        try:
            collection = self.zot.collection(collection_key)
            collection_name = collection['data']['name']
        except:
            collection_name = collection_key

        # Show preview
        self.preview_cleanup(subcollections, summary_notes, collection_name)

        if dry_run:
            print("🔍 DRY RUN: No changes made")
            return

        # Confirm deletion
        if not skip_confirm:
            print("⚠️  WARNING: This will delete ALL ZResearcher projects in this collection!")
            if not self.confirm_cleanup():
                print("❌ Cleanup cancelled")
                return

        # Perform deletion
        print("\n🗑️  Deleting items...")
        total_deleted = {'notes': 0, 'files': 0, 'items': 0, 'gemini_files': 0, 'errors': []}

        # Delete Gemini files for each project
        for subcoll in subcollections:
            # Set project name for this iteration
            self.project_name = subcoll['project_name']
            print(f"\n  Checking Gemini files for {subcoll['name']}...")
            gemini_result = self.delete_gemini_files_for_project(collection_key)
            total_deleted['gemini_files'] += gemini_result['deleted']
            total_deleted['errors'].extend(gemini_result['errors'])

        # Delete all subcollections
        for subcoll in subcollections:
            print(f"\n  Deleting {subcoll['name']}...")
            result = self.delete_collection_recursive(subcoll['key'])
            total_deleted['notes'] += result['notes']
            total_deleted['files'] += result['files']
            total_deleted['items'] += result['items']
            total_deleted['errors'].extend(result['errors'])

        # Delete all general summary notes
        if summary_notes:
            print(f"\n  Deleting {len(summary_notes)} general summary notes...")
            for note in summary_notes:
                try:
                    self.zot.delete_item(note)
                    total_deleted['notes'] += 1
                except Exception as e:
                    error_msg = f"Failed to delete note {note.get('key', 'unknown')}: {e}"
                    total_deleted['errors'].append(error_msg)
                    if self.verbose:
                        print(f"  ⚠️  {error_msg}")

        # Report results
        print("\n" + "=" * 60)
        print("✅ Cleanup Complete\n")
        print(f"Deleted:")
        if total_deleted['gemini_files'] > 0:
            print(f"  • {total_deleted['gemini_files']} Gemini files")
        print(f"  • {len(subcollections)} project subcollections")
        print(f"  • {total_deleted['notes']} notes")
        print(f"  • {total_deleted['files']} file attachments")
        print(f"  • {total_deleted['items']} other items")

        if total_deleted['errors']:
            print(f"\n⚠️  {len(total_deleted['errors'])} errors occurred:")
            for error in total_deleted['errors'][:5]:  # Show first 5 errors
                print(f"  • {error}")
            if len(total_deleted['errors']) > 5:
                print(f"  ... and {len(total_deleted['errors']) - 5} more errors")
        print()


def main():
    """Standalone test/example usage"""
    import os
    from dotenv import load_dotenv

    # Load environment variables
    load_dotenv()

    # Get required credentials
    library_id = os.getenv('ZOTERO_LIBRARY_ID')
    library_type_raw = os.getenv('ZOTERO_LIBRARY_TYPE', 'user')
    api_key = os.getenv('ZOTERO_API_KEY')
    anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')

    # Sanitize library_type: strip quotes and whitespace
    library_type = library_type_raw.strip().strip("'\"") if library_type_raw else 'user'

    # Validate library_type
    if library_type not in ['user', 'group']:
        print(f"Error: Invalid ZOTERO_LIBRARY_TYPE: '{library_type_raw}'")
        print("Must be either 'user' or 'group' (without quotes)")
        sys.exit(1)

    if not all([library_id, api_key, anthropic_api_key]):
        print("Error: Missing required environment variables")
        sys.exit(1)

    # Example usage
    cleaner = ZoteroResearcherCleaner(
        library_id=library_id,
        library_type=library_type,
        api_key=api_key,
        anthropic_api_key=anthropic_api_key,
        verbose=True
    )

    # Dry run example
    collection_key = "YOUR_COLLECTION_KEY"
    project_name = "Test Project"

    cleaner.cleanup_project(
        collection_key=collection_key,
        project_name=project_name,
        dry_run=True
    )


if __name__ == '__main__':
    main()
