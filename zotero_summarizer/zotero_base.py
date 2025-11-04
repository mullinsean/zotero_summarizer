#!/usr/bin/env python3
"""
Zotero Base Processor

Base class providing shared functionality for processing Zotero collections,
including attachment detection, note creation, and verbose output.
"""

import markdown
from pyzotero import zotero
from typing import Optional, Dict, List


class ZoteroBaseProcessor:
    """Base class for processing Zotero collections with shared functionality."""

    def __init__(
        self,
        library_id: str,
        library_type: str,
        api_key: str,
        verbose: bool = False
    ):
        """
        Initialize the Zotero base processor.

        Args:
            library_id: Your Zotero user ID or group ID
            library_type: 'user' or 'group'
            api_key: Your Zotero API key
            verbose: If True, show detailed information about all child items
        """
        self.zot = zotero.Zotero(library_id, library_type, api_key)
        self.verbose = verbose

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
        Get all top-level items in a specific collection (excluding child items).

        Args:
            collection_key: The key of the collection to process

        Returns:
            List of top-level items in the collection (no attachments/notes)
        """
        print(f"Fetching top-level items from collection {collection_key}...")
        try:
            # Use collection_items_top to only get parent items, not child attachments/notes
            items = self.zot.collection_items_top(collection_key)
            print(f"Found {len(items)} top-level items in collection")
            return items
        except Exception as e:
            print(f"Error fetching collection items: {e}")
            print("\nThis could mean:")
            print("  1. The collection key is incorrect")
            print("  2. You're using a user library ID for a group collection (or vice versa)")
            print("  3. The API key doesn't have access to this collection")
            print("\nTip: Run with --list-collections to see available collections")
            return []

    def get_item_children(self, item_key: str) -> List[Dict]:
        """
        Get all child items for a specific parent item.

        Args:
            item_key: The key of the parent item

        Returns:
            List of all child items (attachments and notes)
        """
        return self.zot.children(item_key)

    def get_item_attachments(self, item_key: str) -> List[Dict]:
        """
        Get all attachments for a specific item (excludes notes).

        Args:
            item_key: The key of the parent item

        Returns:
            List of attachment items (only actual file attachments, not notes)
        """
        children = self.get_item_children(item_key)
        # Filter to only attachment items (excludes notes and other child types)
        attachments = [
            child for child in children
            if child['data'].get('itemType') == 'attachment'
        ]
        return attachments

    def print_child_items(self, item_key: str):
        """
        Print detailed information about all child items (verbose mode).

        Args:
            item_key: The key of the parent item
        """
        if not self.verbose:
            return

        children = self.get_item_children(item_key)
        print(f"  📋 All child items ({len(children)} total):")
        for idx, child in enumerate(children, 1):
            child_type = child['data'].get('itemType', 'unknown')
            child_title = child['data'].get('title', 'Untitled')

            if child_type == 'note':
                note_preview = child['data'].get('note', '')[:80].replace('\n', ' ')
                print(f"    {idx}. 📝 NOTE: {note_preview}...")
            elif child_type == 'attachment':
                content_type = child['data'].get('contentType', 'unknown')
                filename = child['data'].get('filename', 'no filename')
                link_mode = child['data'].get('linkMode', 'unknown')
                url = child['data'].get('url', 'no url')
                print(f"    {idx}. 📎 ATTACHMENT: {child_title}")
                print(f"        - Filename: {filename}")
                print(f"        - Content Type: {content_type}")
                print(f"        - Link Mode: {link_mode}")
                print(f"        - URL: {url}")
            else:
                print(f"    {idx}. ❓ {child_type.upper()}: {child_title}")

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

    def is_pdf_attachment(self, attachment: Dict) -> bool:
        """
        Check if an attachment is a PDF file.

        Args:
            attachment: The attachment item data

        Returns:
            True if the attachment is PDF
        """
        content_type = attachment['data'].get('contentType', '')
        filename = attachment['data'].get('filename', '')

        return (content_type == 'application/pdf' or
                filename.lower().endswith('.pdf'))

    def download_attachment(self, attachment_key: str) -> Optional[bytes]:
        """
        Download an attachment file from Zotero.

        Args:
            attachment_key: The key of the attachment

        Returns:
            File content as bytes, or None if download fails
        """
        try:
            if self.verbose:
                print(f"  📥 Downloading attachment from Zotero...")
            file_content = self.zot.file(attachment_key)
            return file_content
        except Exception as e:
            print(f"  ❌ Error downloading attachment: {e}")
            return None

    def has_note_with_prefix(self, item_key: str, prefix: str) -> bool:
        """
        Check if an item already has a note starting with a specific prefix.

        Since notes are stored as HTML, we check for the HTML version of the prefix.
        For markdown headings like "# AI Summary:", we check for "<h1>AI Summary:"

        Args:
            item_key: The key of the parent item
            prefix: The prefix to search for (e.g., "AI Summary:", "Markdown Extract:")

        Returns:
            True if the item has a note with that prefix
        """
        children = self.get_item_children(item_key)
        notes = [child for child in children if child['data'].get('itemType') == 'note']

        for note in notes:
            note_content = note['data'].get('note', '')
            # Notes are stored as HTML, so check for HTML heading
            # The markdown "# Title" becomes "<h1>Title</h1>" in HTML
            html_prefix = f"<h1>{prefix}"
            if html_prefix in note_content[:200]:  # Check first 200 chars for the heading
                return True

        return False

    def markdown_to_html(self, markdown_content: str) -> str:
        """
        Convert markdown content to HTML for Zotero notes.

        Args:
            markdown_content: Markdown content

        Returns:
            HTML formatted content
        """
        try:
            # Convert markdown to HTML with extensions
            html_content = markdown.markdown(
                markdown_content,
                extensions=['extra', 'nl2br', 'sane_lists']
            )
            return html_content
        except Exception as e:
            print(f"  ⚠️  Warning: Markdown conversion failed: {e}")
            # Fall back to simple newline-to-br replacement
            return markdown_content.replace('\n', '<br>')

    def create_note(
        self,
        parent_key: str,
        content: str,
        title: str,
        convert_markdown: bool = True
    ) -> bool:
        """
        Create a note in Zotero attached to a parent item.

        Args:
            parent_key: The key of the parent item
            content: The content for the note (markdown or HTML)
            title: Title to prepend to the note
            convert_markdown: If True, convert markdown to HTML

        Returns:
            True if note was created successfully
        """
        try:
            # Prepend title
            full_content = f"# {title}\n\n{content}"

            # Convert markdown to HTML for proper Zotero rendering
            if convert_markdown:
                html_content = self.markdown_to_html(full_content)
            else:
                html_content = full_content

            note_template = self.zot.item_template('note')
            note_template['note'] = html_content
            note_template['parentItem'] = parent_key

            result = self.zot.create_items([note_template])

            if result['success']:
                print(f"  ✅ Note created successfully")
                return True
            else:
                print(f"  ❌ Failed to create note: {result}")
                return False
        except Exception as e:
            print(f"  ❌ Error creating note: {e}")
            return False
