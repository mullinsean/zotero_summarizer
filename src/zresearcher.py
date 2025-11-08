#!/usr/bin/env python3
"""
Zotero Researcher - CLI Entry Point

This script provides a command-line interface for the ZoteroResearcher tool.
It routes commands to the appropriate workflow modules:
- zr_init: Collection initialization
- zr_build: Building general summaries (Phase 1)
- zr_query: Querying with research briefs (Phase 2)
"""

import os
import argparse
from dotenv import load_dotenv

# Handle both relative and absolute imports
try:
    from .zr_common import validate_project_name
    from .zr_init import ZoteroResearcherInit
    from .zr_build import ZoteroResearcherBuilder
    from .zr_query import ZoteroResearcherQuerier
    from .zr_organize_sources import ZoteroResearcherOrganizer
    from .zr_file_search import ZoteroFileSearcher
    from .zr_cleanup import ZoteroResearcherCleaner
except ImportError:
    from zr_common import validate_project_name
    from zr_init import ZoteroResearcherInit
    from zr_build import ZoteroResearcherBuilder
    from zr_query import ZoteroResearcherQuerier
    from zr_organize_sources import ZoteroResearcherOrganizer
    from zr_file_search import ZoteroFileSearcher
    from zr_cleanup import ZoteroResearcherCleaner


def main():
    """Main entry point."""

    # Load environment variables
    load_dotenv()

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Two-phase research assistant for Zotero collections',
        epilog="""
Examples:
  # List collections
  python zresearcher.py --list-collections

  # List projects in a collection
  python zresearcher.py --list-projects --collection KEY

  # Initialize collection for a new project
  python zresearcher.py --init-collection --collection KEY --project "AI Productivity"

  # Organize sources (optional, run after init-collection)
  python zresearcher.py --organize-sources --collection KEY

  # Phase 1: Build general summaries
  python zresearcher.py --build-summaries --collection KEY --project "AI Productivity"

  # Phase 2: Query with research brief
  python zresearcher.py --query-summary --collection KEY --project "AI Productivity"

  # Rebuild all summaries for a project
  python zresearcher.py --build-summaries --collection KEY --project "AI Productivity" --force

  # File Search: Run Gemini RAG query (auto-uploads if needed)
  python zresearcher.py --file-search --collection KEY --project "AI Productivity"

  # Cleanup: Remove a specific project (preview with --dry-run)
  python zresearcher.py --cleanup-project --collection KEY --project "AI Productivity" --dry-run
  python zresearcher.py --cleanup-project --collection KEY --project "AI Productivity"

  # Cleanup: Remove ALL projects from a collection (use with caution!)
  python zresearcher.py --cleanup-collection --collection KEY --dry-run
  python zresearcher.py --cleanup-collection --collection KEY --yes
        """
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--list-collections',
        action='store_true',
        help='List all available collections and exit'
    )
    mode_group.add_argument(
        '--list-projects',
        action='store_true',
        help='List all ZResearcher projects in a collection'
    )
    mode_group.add_argument(
        '--init-collection',
        action='store_true',
        help='Initialize collection with project-specific 【ZResearcher: PROJECT】 subcollection and templates'
    )
    mode_group.add_argument(
        '--organize-sources',
        action='store_true',
        help='Organize sources: ensure all items have acceptable attachments (HTML/PDF/TXT). Optional, run after init-collection.'
    )
    mode_group.add_argument(
        '--build-summaries',
        action='store_true',
        help='Phase 1: Build general summaries with metadata and tags'
    )
    mode_group.add_argument(
        '--query-summary',
        action='store_true',
        help='Phase 2: Query sources using research brief from Zotero notes'
    )
    mode_group.add_argument(
        '--file-search',
        action='store_true',
        help='Google Gemini File Search: query sources using RAG (auto-uploads if needed, requires GEMINI_API_KEY)'
    )
    mode_group.add_argument(
        '--cleanup-project',
        action='store_true',
        help='Clean up a specific project: delete subcollection and all summary notes for this project'
    )
    mode_group.add_argument(
        '--cleanup-collection',
        action='store_true',
        help='Clean up ALL projects in a collection: delete all ZResearcher data (use with caution!)'
    )

    # Common arguments
    parser.add_argument(
        '--collection',
        type=str,
        help='Collection key to process (overrides ZOTERO_COLLECTION_KEY env var)'
    )
    parser.add_argument(
        '--project',
        type=str,
        required=False,
        help='Project name for organizing research (required for most operations). Each project has its own subcollection and configuration.'
    )
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Show detailed information about all child items'
    )

    # Phase 1 (build) arguments
    parser.add_argument(
        '--force',
        action='store_true',
        help='[Build] Force rebuild of existing summaries'
    )

    # Cleanup arguments
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='[Cleanup] Preview what would be deleted without actually deleting'
    )
    parser.add_argument(
        '--yes',
        action='store_true',
        help='[Cleanup] Skip confirmation prompt (useful for scripts)'
    )

    args = parser.parse_args()

    # Get configuration from environment
    library_id = os.getenv('ZOTERO_LIBRARY_ID')
    library_type_raw = os.getenv('ZOTERO_LIBRARY_TYPE', 'user')
    zotero_api_key = os.getenv('ZOTERO_API_KEY')
    anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
    gemini_api_key = os.getenv('GEMINI_API_KEY')
    collection_key = args.collection or os.getenv('ZOTERO_COLLECTION_KEY')

    # Sanitize library_type: strip quotes and whitespace
    # (users sometimes add quotes in .env files like ZOTERO_LIBRARY_TYPE='group')
    library_type = library_type_raw.strip().strip("'\"") if library_type_raw else 'user'

    # Validate library_type
    if library_type not in ['user', 'group']:
        print(f"Error: Invalid ZOTERO_LIBRARY_TYPE: '{library_type_raw}'")
        print("Must be either 'user' or 'group' (without quotes in .env file)")
        print(f"Example .env entry: ZOTERO_LIBRARY_TYPE=group")
        return

    # Validate required configuration
    if not library_id or not zotero_api_key:
        print("Error: Missing required Zotero environment variables")
        print("Please set ZOTERO_LIBRARY_ID and ZOTERO_API_KEY in your .env file")
        return

    if not anthropic_api_key and not args.file_search:
        print("Error: Missing required ANTHROPIC_API_KEY")
        print("Please set ANTHROPIC_API_KEY in your .env file")
        return

    if args.file_search and not gemini_api_key:
        print("Error: Missing required GEMINI_API_KEY for File Search")
        print("Please set GEMINI_API_KEY in your .env file")
        return

    # Validate project name is provided for operations that require it
    operations_requiring_project = [
        args.init_collection,
        args.build_summaries,
        args.query_summary,
        args.file_search,
        args.cleanup_project
    ]
    if any(operations_requiring_project) and not args.project:
        print("Error: --project is required for this operation")
        print("Example: python zresearcher.py --init-collection --collection KEY --project \"AI Productivity\"")
        return

    # Validate project name format if provided
    project_name = None
    if args.project:
        try:
            project_name = validate_project_name(args.project)
        except ValueError as e:
            print(f"Error: Invalid project name: {e}")
            return

    # Handle --list-collections flag (uses Init class for convenience)
    if args.list_collections:
        # We can use any of the classes for this, since it's inherited from base
        temp_researcher = ZoteroResearcherInit(
            library_id,
            library_type,
            zotero_api_key,
            anthropic_api_key,
            project_name="temp",  # Dummy project name
            force_rebuild=False,
            verbose=args.verbose
        )
        temp_researcher.print_collections()
        return

    # Handle --list-projects flag
    if args.list_projects:
        if not collection_key:
            print("Error: --collection required for --list-projects")
            print("Example: python zresearcher.py --list-projects --collection ABC123")
            return

        # Initialize with a temporary project name for listing
        temp_researcher = ZoteroResearcherInit(
            library_id,
            library_type,
            zotero_api_key,
            anthropic_api_key,
            project_name="temp",  # Dummy project name
            force_rebuild=False,
            verbose=args.verbose
        )
        temp_researcher.list_projects(collection_key)
        return

    # Handle --init-collection flag
    if args.init_collection:
        if not collection_key:
            print("Error: --collection required for --init-collection")
            print("Example: python zresearcher.py --init-collection --collection ABC123 --project \"AI Productivity\"")
            return

        researcher = ZoteroResearcherInit(
            library_id,
            library_type,
            zotero_api_key,
            anthropic_api_key,
            project_name=project_name,
            force_rebuild=args.force,
            verbose=args.verbose
        )
        researcher.init_collection(collection_key, force=args.force)
        return

    # Validate collection key for remaining operations
    if not collection_key:
        print("Error: No collection specified")
        print("Either:")
        print("  1. Set ZOTERO_COLLECTION_KEY in your .env file, or")
        print("  2. Use --collection COLLECTION_KEY argument")
        print("\nTip: Run with --list-collections to see available collections")
        return

    # Handle --organize-sources mode
    if args.organize_sources:
        organizer = ZoteroResearcherOrganizer(
            library_id,
            library_type,
            zotero_api_key,
            anthropic_api_key,
            project_name=project_name if project_name else "temp",  # Optional for organize
            force_rebuild=False,
            verbose=args.verbose
        )
        stats = organizer.organize_sources(collection_key)
        return

    # Handle --build-summaries mode
    if args.build_summaries:
        researcher = ZoteroResearcherBuilder(
            library_id,
            library_type,
            zotero_api_key,
            anthropic_api_key,
            project_name=project_name,
            force_rebuild=args.force,
            verbose=args.verbose
        )
        researcher.build_general_summaries(collection_key)
        return

    # Handle --query-summary mode
    if args.query_summary:
        researcher = ZoteroResearcherQuerier(
            library_id,
            library_type,
            zotero_api_key,
            anthropic_api_key,
            project_name=project_name,
            force_rebuild=False,  # Not used in query mode
            verbose=args.verbose
        )
        result = researcher.run_query_summary(collection_key)

        if result:
            if result.endswith('.html'):
                print(f"Note: Large report saved as file (with stub note in Zotero)")
            else:
                print(f"Note: Report saved as note in project subcollection")
        return

    # Handle --file-search mode
    if args.file_search:
        searcher = ZoteroFileSearcher(
            library_id,
            library_type,
            zotero_api_key,
            anthropic_api_key or "",  # Optional for file search
            gemini_api_key,
            project_name=project_name,
            force_rebuild=args.force,
            verbose=args.verbose
        )

        # Run file search (auto-uploads if needed)
        result = searcher.run_file_search(collection_key)
        if result:
            print(f"✅ File search query completed successfully")
        else:
            print(f"❌ File search query failed")
        return

    # Handle --cleanup-project mode
    if args.cleanup_project:
        cleaner = ZoteroResearcherCleaner(
            library_id,
            library_type,
            zotero_api_key,
            anthropic_api_key or "",  # Not used in cleanup, but required by base class
            project_name=project_name,
            verbose=args.verbose
        )
        cleaner.cleanup_project(
            collection_key,
            project_name,
            dry_run=args.dry_run,
            skip_confirm=args.yes
        )
        return

    # Handle --cleanup-collection mode
    if args.cleanup_collection:
        cleaner = ZoteroResearcherCleaner(
            library_id,
            library_type,
            zotero_api_key,
            anthropic_api_key or "",  # Not used in cleanup, but required by base class
            project_name="temp",  # Not used for collection-wide cleanup
            verbose=args.verbose
        )
        cleaner.cleanup_all_projects(
            collection_key,
            dry_run=args.dry_run,
            skip_confirm=args.yes
        )
        return


if __name__ == '__main__':
    main()
