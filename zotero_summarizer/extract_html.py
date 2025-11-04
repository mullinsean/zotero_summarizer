#!/usr/bin/env python3
"""
Zotero HTML to Markdown Extractor

This script accesses a Zotero collection, identifies items with HTML attachments,
extracts the text content, converts it to Markdown, and saves it as a note in the collection.
"""

import os
import requests
from bs4 import BeautifulSoup
import html2text
from typing import Optional, Dict, List
import time
import trafilatura

# Handle both relative and absolute imports
try:
    from .llm_extractor import LLMExtractor
    from .zotero_base import ZoteroBaseProcessor
except ImportError:
    from llm_extractor import LLMExtractor
    from zotero_base import ZoteroBaseProcessor


class ZoteroHTMLExtractor(ZoteroBaseProcessor):
    """Extract HTML content from Zotero items and convert to Markdown notes."""
    
    def __init__(
        self,
        library_id: str,
        library_type: str,
        api_key: str,
        force_reextract: bool = False,
        anthropic_api_key: Optional[str] = None,
        use_llm: bool = False,
        llm_fallback: bool = True,
        verbose: bool = False
    ):
        """
        Initialize the Zotero HTML extractor.

        Args:
            library_id: Your Zotero user ID or group ID
            library_type: 'user' or 'group'
            api_key: Your Zotero API key
            force_reextract: If True, re-extract even if markdown note already exists
            anthropic_api_key: Anthropic API key for LLM extraction (optional)
            use_llm: If True, use LLM extraction instead of BeautifulSoup
            llm_fallback: If True, fall back to BeautifulSoup if LLM extraction fails
            verbose: If True, show detailed information about all child items
        """
        # Initialize base class
        super().__init__(library_id, library_type, api_key, verbose)

        # HTML-specific configuration
        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = False
        self.html_converter.ignore_images = True  # Ignore images including data URIs
        self.html_converter.body_width = 0  # Don't wrap lines
        self.force_reextract = force_reextract
        self.use_llm = use_llm
        self.llm_fallback = llm_fallback

        # Initialize LLM extractor if API key provided
        self.llm_extractor = None
        if anthropic_api_key:
            self.llm_extractor = LLMExtractor(anthropic_api_key)
        elif use_llm:
            print("Warning: --use-llm flag set but no ANTHROPIC_API_KEY found. Falling back to BeautifulSoup.")
            self.use_llm = False

    def has_markdown_extract_note(self, item_key: str) -> bool:
        """
        Check if an item already has a markdown extract note.

        Args:
            item_key: The key of the parent item

        Returns:
            True if the item already has a markdown extract note
        """
        return self.has_note_with_prefix(item_key, 'Markdown Extract:')

    def fetch_url_content(self, url: str) -> Optional[str]:
        """
        Fetch HTML content from a URL.
        
        Args:
            url: The URL to fetch
            
        Returns:
            HTML content as string, or None if fetch fails
        """
        try:
            print(f"  Fetching content from URL: {url}")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"  Error fetching URL: {e}")
            return None
    
    def extract_text_from_html(self, html_content: str) -> str:
        """
        Extract and clean text from HTML content.
        
        Args:
            html_content: Raw HTML content
            
        Returns:
            Cleaned text content
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(['script', 'style', 'nav', 'footer', 'header']):
            script.decompose()
        
        return str(soup)
    
    def html_to_markdown(self, html_content: str) -> str:
        """
        Convert HTML content to Markdown using BeautifulSoup + html2text.

        Args:
            html_content: HTML content

        Returns:
            Markdown formatted text
        """
        # Clean the HTML first
        cleaned_html = self.extract_text_from_html(html_content)

        # Convert to Markdown
        markdown = self.html_converter.handle(cleaned_html)

        return markdown.strip()

    def trafilatura_extract(self, html_content: str) -> Optional[str]:
        """
        Extract article content using Trafilatura.

        Trafilatura is purpose-built for extracting main content from web pages
        and handles large documents much better than BeautifulSoup.

        Args:
            html_content: Raw HTML content

        Returns:
            Extracted markdown content, or None if extraction fails
        """
        try:
            # Extract main content with Trafilatura
            # output_format='markdown' gives us markdown output directly
            # include_links=True preserves hyperlinks
            # include_images=False skips images (consistent with our config)
            markdown = trafilatura.extract(
                html_content,
                output_format='markdown',
                include_links=True,
                include_images=False,
                include_tables=True
            )

            if markdown:
                return markdown.strip()
            else:
                print("  ⚠ Trafilatura returned no content")
                return None

        except Exception as e:
            print(f"  ✗ Trafilatura extraction error: {e}")
            return None

    def extract_content(self, html_content: str, title: str = "") -> Optional[str]:
        """
        Extract article content from HTML using configured method.

        Default: Trafilatura extraction
        With --use-llm: Trafilatura extraction → LLM polish

        Args:
            html_content: Raw HTML content
            title: Optional title for context

        Returns:
            Markdown content, or None if extraction fails
        """
        # Step 1: Extract content with Trafilatura (default method)
        print("  Using Trafilatura extraction...")
        markdown = self.trafilatura_extract(html_content)

        if not markdown:
            # Trafilatura failed, try BeautifulSoup fallback if enabled
            if self.llm_fallback:
                print("  ⚠ Trafilatura failed, falling back to BeautifulSoup...")
                markdown = self.html_to_markdown(html_content)
            else:
                print("  ✗ Trafilatura extraction failed, no fallback enabled")
                return None

        if not markdown:
            return None

        # Step 2: Optional LLM polish if enabled
        if self.use_llm and self.llm_extractor:
            print("  Applying LLM polish to extracted content...")
            polished = self.llm_extractor.polish_markdown(markdown, title)

            if polished:
                print("  ✓ LLM polish successful")
                return polished
            elif not self.llm_fallback:
                print("  ✗ LLM polish failed, no fallback enabled")
                return None
            else:
                print("  ⚠ LLM polish failed, using unpolished Trafilatura output")
                return markdown

        return markdown

    def process_collection(self, collection_key: str):
        """
        Process all items in a collection, extracting HTML content and creating notes.
        
        Args:
            collection_key: The key of the collection to process
        """
        items = self.get_collection_items(collection_key)
        
        processed = 0
        skipped = 0
        already_extracted = 0
        errors = 0
        
        for item in items:
            # Items from collection_items_top should only be parent items,
            # but double-check to be safe
            item_type = item['data'].get('itemType')
            if item_type in ['attachment', 'note']:
                print(f"  ⚠️  Skipping {item_type} (should not appear in top-level items)")
                skipped += 1
                continue

            item_key = item['key']
            item_title = item['data'].get('title', 'Untitled')

            print(f"\nProcessing: {item_title}")

            # Check if already has markdown extract (unless force flag is set)
            if not self.force_reextract and self.has_markdown_extract_note(item_key):
                print(f"  ⏭️  Already has markdown extract, skipping")
                already_extracted += 1
                continue

            # Print child items in verbose mode
            self.print_child_items(item_key)

            # Get attachments for this item
            attachments = self.get_item_attachments(item_key)

            if not attachments:
                print("  ⚠️  No attachments found")
                skipped += 1
                continue
            
            # Process HTML attachments
            html_found = False
            for attachment in attachments:
                # Verify this is actually an attachment (not a note)
                if attachment['data'].get('itemType') != 'attachment':
                    continue

                # Check if it's an HTML attachment
                if not self.is_html_attachment(attachment):
                    if self.verbose:
                        att_title = attachment['data'].get('title', 'Untitled')
                        att_content = attachment['data'].get('contentType', 'unknown')
                        print(f"  ⏭️  Skipping non-HTML attachment: {att_title} ({att_content})")
                    continue

                html_found = True
                attachment_key = attachment['key']
                attachment_title = attachment['data'].get('title', 'HTML Snapshot')
                
                print(f"  Found HTML attachment: {attachment_title}")
                
                html_content = None
                
                # Try to download from Zotero first (snapshot)
                if attachment['data'].get('linkMode') in ['imported_file', 'imported_url']:
                    file_content = self.download_attachment(attachment_key)
                    if file_content:
                        html_content = file_content.decode('utf-8', errors='ignore')
                
                # Fall back to URL if available and no snapshot found
                if not html_content:
                    url = attachment['data'].get('url')
                    if url and url.startswith('http'):
                        html_content = self.fetch_url_content(url)
                
                if html_content:
                    # Extract content using configured method (LLM or BeautifulSoup)
                    markdown = self.extract_content(html_content, item_title)

                    if not markdown:
                        print("  ✗ Content extraction failed")
                        errors += 1
                        continue

                    # Create note
                    note_title = f"Markdown Extract: {attachment_title}"
                    success = self.create_note(item_key, markdown, note_title, convert_markdown=True)
                    
                    if success:
                        processed += 1
                    else:
                        errors += 1
                    
                    # Rate limiting - be nice to Zotero API
                    time.sleep(1)
                    break  # Process only the first HTML attachment
                else:
                    print("  ✗ Could not retrieve HTML content")
                    errors += 1
            
            if not html_found:
                print("  No HTML attachments found")
                skipped += 1
        
        print("\n" + "="*60)
        print("Processing complete!")
        print(f"Newly processed: {processed}")
        print(f"Already extracted: {already_extracted}")
        print(f"Skipped: {skipped}")
        print(f"Errors: {errors}")
        print("="*60)


def main():
    """Main execution function."""
    import sys

    # Configuration - Replace with your actual values
    LIBRARY_ID = os.environ.get('ZOTERO_LIBRARY_ID', 'YOUR_LIBRARY_ID')
    LIBRARY_TYPE = os.environ.get('ZOTERO_LIBRARY_TYPE', 'group')  # 'user' or 'group'
    API_KEY = os.environ.get('ZOTERO_API_KEY', 'YOUR_API_KEY')
    COLLECTION_KEY = os.environ.get('ZOTERO_COLLECTION_KEY', '3YNCRQHJ')

    # LLM Configuration
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', None)

    # Check for flags
    force_reextract = '--force' in sys.argv
    list_collections = '--list-collections' in sys.argv
    use_llm = '--use-llm' in sys.argv
    llm_fallback = '--no-fallback' not in sys.argv  # Default to True, disable with --no-fallback
    verbose = '--verbose' in sys.argv or '-v' in sys.argv


    # Validate configuration
    if 'YOUR' in LIBRARY_ID or 'YOUR' in API_KEY:
        print("Error: Please configure your Zotero credentials")
        print("\nYou can either:")
        print("1. Set environment variables:")
        print("   For USER library:")
        print("     export ZOTERO_LIBRARY_ID='your_user_id'")
        print("     export ZOTERO_LIBRARY_TYPE='user'")
        print("     export ZOTERO_API_KEY='your_api_key'")
        print("     export ZOTERO_COLLECTION_KEY='your_collection_key'")
        print("\n   For GROUP library:")
        print("     export ZOTERO_LIBRARY_ID='group_id'  # NOT your user ID!")
        print("     export ZOTERO_LIBRARY_TYPE='group'")
        print("     export ZOTERO_API_KEY='your_api_key'")
        print("     export ZOTERO_COLLECTION_KEY='collection_key_from_group'")
        print("\n2. Or edit this script and replace the placeholder values")
        print("\nTo get your credentials:")
        print("- User ID: Your user ID from https://www.zotero.org/settings/keys")
        print("- Group ID: From group URL: https://www.zotero.org/groups/GROUP_ID/...")
        print("- API Key: Create one at https://www.zotero.org/settings/keys")
        print("  (Make sure to enable access to the group if using group library!)")
        print("- Collection Key: Right-click collection > 'Copy Collection Link' > use last part of URL")
        return
    
    # Create extractor
    extractor = ZoteroHTMLExtractor(
        LIBRARY_ID,
        LIBRARY_TYPE,
        API_KEY,
        force_reextract=force_reextract,
        anthropic_api_key=ANTHROPIC_API_KEY,
        use_llm=use_llm,
        llm_fallback=llm_fallback,
        verbose=verbose
    )
    
    # Check for command line arguments
    if list_collections:
        print(f"\nLibrary Type: {LIBRARY_TYPE}")
        print(f"Library ID: {LIBRARY_ID}")
        extractor.print_collections()
        return
    
    # Validate collection key
    if 'YOUR' in COLLECTION_KEY:
        print("Error: Please specify a collection key")
        print("\nTip: Run with --list-collections to see available collections:")
        print(f"  python {sys.argv[0]} --list-collections")
        print("\nAvailable flags:")
        print("  --list-collections  : List all collections")
        print("  --force            : Re-extract items with existing notes")
        print("  --use-llm          : Use LLM polish on extracted content")
        print("  --no-fallback      : Disable BeautifulSoup fallback")
        print("  --verbose or -v    : Show detailed info about all child items")
        return
    
    # Process collection
    print(f"\nLibrary Type: {LIBRARY_TYPE}")
    print(f"Library ID: {LIBRARY_ID}")
    print(f"Collection Key: {COLLECTION_KEY}")

    # Display mode information
    if force_reextract:
        print("Mode: FORCE RE-EXTRACT (will recreate existing markdown notes)")
    else:
        print("Mode: Skip items with existing markdown notes")

    # Display extraction method
    if use_llm and ANTHROPIC_API_KEY:
        print(f"Extraction: Trafilatura + LLM Polish (Claude API)")
    else:
        print("Extraction: Trafilatura (default)")
    print(f"Fallback: {'Enabled (BeautifulSoup)' if llm_fallback else 'Disabled'}")

    if verbose:
        print("Verbose mode: ON (showing all child items)")

    print()
    extractor.process_collection(COLLECTION_KEY)


if __name__ == '__main__':
    main()