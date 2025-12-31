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
    from .zotero_base import ZoteroBaseProcessor
    from .zr_common import validate_project_name
    from .zr_init import ZoteroResearcherInit
    from .zr_build import ZoteroResearcherBuilder
    from .zr_query import ZoteroResearcherQuerier
    from .zr_organize_sources import ZoteroResearcherOrganizer
    from .zr_file_search import ZoteroFileSearcher
    from .zr_cleanup import ZoteroResearcherCleaner
    from .zr_export import ZoteroNotebookLMExporter
    from .zr_vector_db import ZoteroVectorSearcher
except ImportError:
    from zotero_base import ZoteroBaseProcessor
    from zr_common import validate_project_name
    from zr_init import ZoteroResearcherInit
    from zr_build import ZoteroResearcherBuilder
    from zr_query import ZoteroResearcherQuerier
    from zr_organize_sources import ZoteroResearcherOrganizer
    from zr_file_search import ZoteroFileSearcher
    from zr_cleanup import ZoteroResearcherCleaner
    from zr_export import ZoteroNotebookLMExporter
    from zr_vector_db import ZoteroVectorSearcher


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

  # File Search Stage 1: Upload files to Gemini file search store
  python zresearcher.py --upload-files --collection KEY --project "AI Productivity"

  # File Search Stage 2: Run Gemini RAG query (requires files to be uploaded first)
  python zresearcher.py --file-search --collection KEY --project "AI Productivity"

  # Force re-upload all files (deletes and recreates file search store)
  python zresearcher.py --upload-files --collection KEY --project "AI Productivity" --force

  # Cleanup: Remove a specific project (preview with --dry-run)
  python zresearcher.py --cleanup-project --collection KEY --project "AI Productivity" --dry-run
  python zresearcher.py --cleanup-project --collection KEY --project "AI Productivity"

  # Cleanup: Remove ALL projects from a collection (use with caution!)
  python zresearcher.py --cleanup-collection --collection KEY --dry-run
  python zresearcher.py --cleanup-collection --collection KEY --yes

  # Export: Export collection to NotebookLM format (PDFs, TXT, HTML→Markdown)
  python zresearcher.py --export-to-notebooklm --collection KEY --output-dir ./notebooklm_export

  # Export: Export all ZResearcher summary notes (consolidated file or separate files)
  python zresearcher.py --export-summaries --collection KEY --project "AI Productivity"
  python zresearcher.py --export-summaries --collection KEY --project "AI Productivity" --output-file ./my_summaries.md
  python zresearcher.py --export-summaries --collection KEY --project "AI Productivity" --separate-files
  python zresearcher.py --export-summaries --collection KEY --project "AI Productivity" --separate-files --output-file ./summaries_dir

  # Cache: Sync collection to local cache (required before offline use)
  python zresearcher.py --sync --collection KEY

  # Cache: Force full re-sync (ignore existing cache)
  python zresearcher.py --sync --collection KEY --force

  # Cache: Check cache status
  python zresearcher.py --cache-status --collection KEY

  # Cache: Clear cache for a collection
  python zresearcher.py --clear-cache --collection KEY

  # Cache: Run query offline using cached data
  python zresearcher.py --query-summary --collection KEY --project "AI Productivity" --offline --enable-cache
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
        '--upload-files',
        action='store_true',
        help='Google Gemini File Search: upload collection files to file search store (requires GEMINI_API_KEY)'
    )
    mode_group.add_argument(
        '--file-search',
        action='store_true',
        help='Google Gemini File Search: query sources using RAG (requires files to be uploaded first, requires GEMINI_API_KEY)'
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
    mode_group.add_argument(
        '--export-to-notebooklm',
        action='store_true',
        help='Export collection to NotebookLM format: extract PDFs, TXT files, and convert HTML to Markdown'
    )
    mode_group.add_argument(
        '--export-summaries',
        action='store_true',
        help='Export all ZResearcher summary notes for a project to a single markdown file'
    )

    # Cache management commands
    mode_group.add_argument(
        '--sync',
        action='store_true',
        help='Sync collection to local cache (downloads items, children, and attachments)'
    )
    mode_group.add_argument(
        '--cache-status',
        action='store_true',
        help='Show cache status for a collection'
    )
    mode_group.add_argument(
        '--clear-cache',
        action='store_true',
        help='Clear local cache for a collection'
    )

    # Vector database commands
    mode_group.add_argument(
        '--index-vectors',
        action='store_true',
        help='Index collection documents to local vector database for semantic search'
    )
    mode_group.add_argument(
        '--vector-search',
        action='store_true',
        help='Query collection using local vector RAG (requires --index-vectors first)'
    )
    mode_group.add_argument(
        '--discover-sources',
        action='store_true',
        help='Find top N most relevant documents for a query (requires --index-vectors first)'
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

    # Subcollection filtering arguments
    parser.add_argument(
        '--subcollections',
        type=str,
        help='Filter to specific subcollections (comma-separated names, or "all" for all subcollections). Example: --subcollections "Research Papers,Reports"'
    )
    parser.add_argument(
        '--include-main',
        action='store_true',
        help='Include items from main collection when using --subcollections (by default only subcollection items are processed)'
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

    # Export arguments
    parser.add_argument(
        '--output-dir',
        type=str,
        default='./notebooklm_export',
        help='[Export] Output directory for exported files (default: ./notebooklm_export)'
    )
    parser.add_argument(
        '--output-file',
        type=str,
        help='[Export Summaries] Output file path (consolidated) or directory path (separate files). Default: ./zresearcher_summaries_{project}.md or ./zresearcher_summaries_{project}/'
    )
    parser.add_argument(
        '--separate-files',
        action='store_true',
        help='[Export Summaries] Export each summary as a separate .md file instead of one consolidated file'
    )

    # Cache arguments
    parser.add_argument(
        '--enable-cache',
        action='store_true',
        help='Enable local caching for faster operations (reduces API calls)'
    )
    parser.add_argument(
        '--offline',
        action='store_true',
        help='Work offline using only cached data (requires prior --sync)'
    )

    # Vector search arguments
    parser.add_argument(
        '--item-types',
        type=str,
        help='[Vector] Filter by Zotero itemType (comma-separated, e.g., "journalArticle,report")'
    )
    parser.add_argument(
        '--doc-types',
        type=str,
        help='[Vector] Filter by document type (comma-separated, e.g., "primary source,report")'
    )
    parser.add_argument(
        '--top-n',
        type=int,
        default=10,
        help='[Vector] Number of sources to return for --discover-sources (default: 10)'
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

    if (args.file_search or args.upload_files) and not gemini_api_key:
        print("Error: Missing required GEMINI_API_KEY for File Search operations")
        print("Please set GEMINI_API_KEY in your .env file")
        return

    # Validate project name is provided for operations that require it
    operations_requiring_project = [
        args.init_collection,
        args.build_summaries,
        args.query_summary,
        args.upload_files,
        args.file_search,
        args.cleanup_project,
        args.export_summaries
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

    # Handle --sync flag (sync collection to local cache)
    if args.sync:
        if not collection_key:
            print("Error: --collection required for --sync")
            print("Example: python zresearcher.py --sync --collection ABC123")
            return

        processor = ZoteroBaseProcessor(
            library_id,
            library_type,
            zotero_api_key,
            verbose=args.verbose,
            enable_cache=True
        )
        success = processor.sync_collection(collection_key, force=args.force)
        if success:
            print("\nSync completed successfully!")
        else:
            print("\nSync failed. Check the errors above.")
        return

    # Handle --cache-status flag
    if args.cache_status:
        if not collection_key:
            print("Error: --collection required for --cache-status")
            print("Example: python zresearcher.py --cache-status --collection ABC123")
            return

        processor = ZoteroBaseProcessor(
            library_id,
            library_type,
            zotero_api_key,
            verbose=args.verbose,
            enable_cache=True
        )
        stats = processor.get_cache_status(collection_key)
        if stats:
            cache = processor._get_cache(collection_key)
            if cache:
                cache.print_stats()
        else:
            print(f"No cache found for collection {collection_key}")
            print("Run --sync first to create the cache.")
        return

    # Handle --clear-cache flag
    if args.clear_cache:
        if not collection_key:
            print("Error: --collection required for --clear-cache")
            print("Example: python zresearcher.py --clear-cache --collection ABC123")
            return

        processor = ZoteroBaseProcessor(
            library_id,
            library_type,
            zotero_api_key,
            verbose=args.verbose,
            enable_cache=True
        )
        processor.clear_cache(collection_key)
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
            verbose=args.verbose,
            enable_cache=args.enable_cache,
            offline=args.offline
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
            verbose=args.verbose,
            enable_cache=args.enable_cache,
            offline=args.offline
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
            verbose=args.verbose,
            enable_cache=args.enable_cache,
            offline=args.offline
        )
        stats = organizer.organize_sources(
            collection_key,
            subcollections=args.subcollections,
            include_main=args.include_main
        )
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
            verbose=args.verbose,
            enable_cache=args.enable_cache,
            offline=args.offline
        )
        researcher.build_general_summaries(
            collection_key,
            subcollections=args.subcollections,
            include_main=args.include_main
        )
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
            verbose=args.verbose,
            enable_cache=args.enable_cache,
            offline=args.offline
        )
        result = researcher.run_query_summary(
            collection_key,
            subcollections=args.subcollections,
            include_main=args.include_main
        )

        if result:
            if result.endswith('.html'):
                print(f"Note: Large report saved as file (with stub note in Zotero)")
            else:
                print(f"Note: Report saved as note in project subcollection")
        return

    # Handle --upload-files mode
    if args.upload_files:
        searcher = ZoteroFileSearcher(
            library_id,
            library_type,
            zotero_api_key,
            anthropic_api_key or "",  # Optional for file upload
            gemini_api_key,
            project_name=project_name,
            force_rebuild=args.force,
            verbose=args.verbose,
            enable_cache=args.enable_cache,
            offline=args.offline
        )

        # Upload files to Gemini file search store
        result = searcher.upload_files_to_gemini(
            collection_key,
            subcollections=args.subcollections,
            include_main=args.include_main
        )
        if result:
            print(f"✅ File upload completed successfully")
        else:
            print(f"❌ File upload failed")
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
            verbose=args.verbose,
            enable_cache=args.enable_cache,
            offline=args.offline
        )

        # Run file search (requires files to be uploaded first)
        result = searcher.run_file_search(
            collection_key,
            subcollections=args.subcollections,
            include_main=args.include_main
        )
        if result:
            print(f"✅ File search query completed successfully")
        else:
            print(f"❌ File search query failed")
        return

    # Handle --index-vectors mode
    if args.index_vectors:
        searcher = ZoteroVectorSearcher(
            library_id,
            library_type,
            zotero_api_key,
            anthropic_api_key or "",
            project_name=project_name,
            force_rebuild=args.force,
            verbose=args.verbose,
            enable_cache=True,  # Cache required for vector operations
            offline=args.offline
        )
        stats = searcher.index_collection(
            collection_key,
            subcollections=args.subcollections,
            include_main=args.include_main
        )
        if stats['indexed'] > 0 or stats['skipped'] > 0:
            print(f"✅ Vector indexing completed successfully")
        else:
            print(f"❌ No items were indexed")
        return

    # Handle --vector-search mode
    if args.vector_search:
        # Parse filtering options
        item_types = args.item_types.split(',') if args.item_types else None
        doc_types = args.doc_types.split(',') if args.doc_types else None

        searcher = ZoteroVectorSearcher(
            library_id,
            library_type,
            zotero_api_key,
            anthropic_api_key,
            project_name=project_name,
            force_rebuild=False,
            verbose=args.verbose,
            enable_cache=True,  # Cache required for vector operations
            offline=args.offline
        )
        result = searcher.run_vector_query(
            collection_key,
            subcollections=args.subcollections,
            include_main=args.include_main,
            item_types=item_types,
            doc_types=doc_types
        )
        if result:
            print(f"✅ Vector search completed successfully")
        else:
            print(f"❌ Vector search failed")
        return

    # Handle --discover-sources mode
    if args.discover_sources:
        # Parse filtering options
        item_types = args.item_types.split(',') if args.item_types else None
        doc_types = args.doc_types.split(',') if args.doc_types else None

        searcher = ZoteroVectorSearcher(
            library_id,
            library_type,
            zotero_api_key,
            anthropic_api_key,
            project_name=project_name,
            force_rebuild=False,
            verbose=args.verbose,
            enable_cache=True,  # Cache required for vector operations
            offline=args.offline
        )
        matches = searcher.discover_sources(
            collection_key,
            top_n=args.top_n,
            subcollections=args.subcollections,
            include_main=args.include_main,
            item_types=item_types,
            doc_types=doc_types
        )
        if matches:
            print(f"✅ Found {len(matches)} relevant sources")
        else:
            print(f"❌ No relevant sources found")
        return

    # Handle --cleanup-project mode
    if args.cleanup_project:
        cleaner = ZoteroResearcherCleaner(
            library_id,
            library_type,
            zotero_api_key,
            anthropic_api_key or "",  # Not used in cleanup, but required by base class
            project_name=project_name,
            verbose=args.verbose,
            enable_cache=args.enable_cache,
            offline=args.offline
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
            verbose=args.verbose,
            enable_cache=args.enable_cache,
            offline=args.offline
        )
        cleaner.cleanup_all_projects(
            collection_key,
            dry_run=args.dry_run,
            skip_confirm=args.yes
        )
        return

    # Handle --export-to-notebooklm mode
    if args.export_to_notebooklm:
        exporter = ZoteroNotebookLMExporter(
            library_id,
            library_type,
            zotero_api_key,
            anthropic_api_key or "",  # Not used in export, but required by base class
            verbose=args.verbose,
            enable_cache=args.enable_cache,
            offline=args.offline
        )
        stats = exporter.export_to_notebooklm(
            collection_key,
            output_dir=args.output_dir,
            subcollections=args.subcollections,
            include_main=args.include_main
        )
        return

    # Handle --export-summaries mode
    if args.export_summaries:
        # Determine output path (file or directory depending on mode)
        if args.output_file:
            output_path = args.output_file
        else:
            # Default: use project name in filename/dirname
            safe_project_name = project_name.replace(' ', '_').replace('/', '_')
            if args.separate_files:
                # Separate files mode: default to directory
                output_path = f"./zresearcher_summaries_{safe_project_name}"
            else:
                # Consolidated mode: default to single file
                output_path = f"./zresearcher_summaries_{safe_project_name}.md"

        exporter = ZoteroNotebookLMExporter(
            library_id,
            library_type,
            zotero_api_key,
            anthropic_api_key or "",  # Not used in export, but required by base class
            verbose=args.verbose,
            enable_cache=args.enable_cache,
            offline=args.offline
        )
        stats = exporter.export_summaries_to_markdown(
            collection_key,
            project_name=project_name,
            output_path=output_path,
            subcollections=args.subcollections,
            include_main=args.include_main,
            separate_files=args.separate_files
        )
        return


if __name__ == '__main__':
    main()
