#!/usr/bin/env python3
"""
Zotero HTML to Markdown Extractor

This script accesses a Zotero collection, identifies items with HTML attachments,
extracts the text content, converts it to Markdown, and saves it as a note in the collection.
"""

import os
import requests
from pyzotero import zotero
from bs4 import BeautifulSoup
import html2text
from typing import Optional, Dict, List
import time


class ZoteroHTMLExtractor:
    """Extract HTML content from Zotero items and convert to Markdown notes."""
    
    def __init__(self, library_id: str, library_type: str, api_key: str):
        """
        Initialize the Zotero client.
        
        Args:
            library_id: Your Zotero user ID or group ID
            library_type: 'user' or 'group'
            api_key: Your Zotero API key
        """
        self.zot = zotero.Zotero(library_id, library_type, api_key)
        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = False
        self.html_converter.ignore_images = False
        self.html_converter.body_width = 0  # Don't wrap lines
        
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
        Get all items in a specific collection.
        
        Args:
            collection_key: The key of the collection to process
            
        Returns:
            List of items in the collection
        """
        print(f"Fetching items from collection {collection_key}...")
        try:
            items = self.zot.collection_items(collection_key)
            print(f"Found {len(items)} items in collection")
            return items
        except Exception as e:
            print(f"Error fetching collection items: {e}")
            print("\nThis could mean:")
            print("  1. The collection key is incorrect")
            print("  2. You're using a user library ID for a group collection (or vice versa)")
            print("  3. The API key doesn't have access to this collection")
            print("\nTip: Run with --list-collections to see available collections")
            return []
    
    def get_item_attachments(self, item_key: str) -> List[Dict]:
        """
        Get all attachments for a specific item.
        
        Args:
            item_key: The key of the parent item
            
        Returns:
            List of attachment items
        """
        children = self.zot.children(item_key)
        attachments = [child for child in children if child['data'].get('itemType') == 'attachment']
        return attachments
    
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
    
    def download_attachment(self, attachment_key: str) -> Optional[bytes]:
        """
        Download an attachment file from Zotero.
        
        Args:
            attachment_key: The key of the attachment
            
        Returns:
            File content as bytes, or None if download fails
        """
        try:
            print(f"  Downloading attachment from Zotero...")
            file_content = self.zot.file(attachment_key)
            return file_content
        except Exception as e:
            print(f"  Error downloading attachment: {e}")
            return None
    
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
        Convert HTML content to Markdown.
        
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
    
    def create_note(self, parent_key: str, markdown_content: str, title: str) -> bool:
        """
        Create a note in Zotero attached to a parent item.
        
        Args:
            parent_key: The key of the parent item
            markdown_content: The Markdown content for the note
            title: Title for the note
            
        Returns:
            True if note was created successfully
        """
        try:
            note_template = self.zot.item_template('note')
            note_template['note'] = f"<h2>{title}</h2>\n<pre>{markdown_content}</pre>"
            note_template['parentItem'] = parent_key
            
            result = self.zot.create_items([note_template])
            
            if result['success']:
                print(f"  ✓ Note created successfully")
                return True
            else:
                print(f"  ✗ Failed to create note: {result}")
                return False
        except Exception as e:
            print(f"  ✗ Error creating note: {e}")
            return False
    
    def process_collection(self, collection_key: str):
        """
        Process all items in a collection, extracting HTML content and creating notes.
        
        Args:
            collection_key: The key of the collection to process
        """
        items = self.get_collection_items(collection_key)
        
        processed = 0
        skipped = 0
        errors = 0
        
        for item in items:
            item_key = item['key']
            item_title = item['data'].get('title', 'Untitled')
            
            print(f"\nProcessing: {item_title}")
            
            # Skip if item is already a note or attachment
            if item['data']['itemType'] in ['note', 'attachment']:
                print(f"  Skipping (is a {item['data']['itemType']})")
                skipped += 1
                continue
            
            # Get attachments for this item
            attachments = self.get_item_attachments(item_key)
            
            if not attachments:
                print("  No attachments found")
                skipped += 1
                continue
            
            # Process HTML attachments
            html_found = False
            for attachment in attachments:
                if not self.is_html_attachment(attachment):
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
                    # Convert to Markdown
                    markdown = self.html_to_markdown(html_content)
                    
                    # Create note
                    note_title = f"Markdown Extract: {attachment_title}"
                    success = self.create_note(item_key, markdown, note_title)
                    
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
        print(f"Processed: {processed}")
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
    extractor = ZoteroHTMLExtractor(LIBRARY_ID, LIBRARY_TYPE, API_KEY)
    
    # Check for command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == '--list-collections':
        print(f"\nLibrary Type: {LIBRARY_TYPE}")
        print(f"Library ID: {LIBRARY_ID}")
        extractor.print_collections()
        return
    
    # Validate collection key
    if 'YOUR' in COLLECTION_KEY:
        print("Error: Please specify a collection key")
        print("\nTip: Run with --list-collections to see available collections:")
        print(f"  python {sys.argv[0]} --list-collections")
        return
    
    # Process collection
    print(f"\nLibrary Type: {LIBRARY_TYPE}")
    print(f"Library ID: {LIBRARY_ID}")
    print(f"Collection Key: {COLLECTION_KEY}\n")
    extractor.process_collection(COLLECTION_KEY)


if __name__ == '__main__':
    main()