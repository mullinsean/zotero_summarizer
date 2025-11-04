#!/usr/bin/env python3
"""
Zotero PDF Analyzer

This script accesses a Zotero collection, identifies PDF attachments,
and determines whether they are digital (selectable text) or scanned (OCR).
"""

import os
from pyzotero import zotero
from pypdf import PdfReader
from typing import Optional, Dict, List
import io


class ZoteroPDFAnalyzer:
    """Analyze PDF attachments in Zotero collections."""

    def __init__(
        self,
        library_id: str,
        library_type: str,
        api_key: str
    ):
        """
        Initialize the Zotero client.

        Args:
            library_id: Your Zotero user ID or group ID
            library_type: 'user' or 'group'
            api_key: Your Zotero API key
        """
        self.zot = zotero.Zotero(library_id, library_type, api_key)

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
            attachment_key: The key of the attachment to download

        Returns:
            The file content as bytes, or None if download failed
        """
        try:
            content = self.zot.file(attachment_key)
            return content
        except Exception as e:
            print(f"  ❌ Error downloading attachment: {e}")
            return None

    def analyze_pdf_type(self, pdf_content: bytes) -> Dict[str, any]:
        """
        Analyze PDF to determine if it's digital or scanned.

        Uses heuristics:
        - Digital PDFs: Have substantial extractable text (>100 chars per page on average)
        - Scanned PDFs: Have little or no extractable text

        Args:
            pdf_content: The PDF file content as bytes

        Returns:
            Dict with analysis results: {
                'type': 'digital' or 'scanned',
                'total_pages': int,
                'total_chars': int,
                'avg_chars_per_page': float,
                'confidence': 'high' or 'medium' or 'low'
            }
        """
        try:
            pdf_file = io.BytesIO(pdf_content)
            reader = PdfReader(pdf_file)

            total_pages = len(reader.pages)
            total_chars = 0

            # Extract text from all pages
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    total_chars += len(text.strip())

            # Calculate average characters per page
            avg_chars_per_page = total_chars / total_pages if total_pages > 0 else 0

            # Heuristic thresholds
            # Digital PDFs typically have >100 chars per page
            # Scanned PDFs with OCR might have some text but usually less
            # Pure scanned PDFs have virtually no text

            if avg_chars_per_page > 500:
                pdf_type = 'digital'
                confidence = 'high'
            elif avg_chars_per_page > 100:
                pdf_type = 'digital'
                confidence = 'medium'
            elif avg_chars_per_page > 20:
                pdf_type = 'scanned'
                confidence = 'medium'
            else:
                pdf_type = 'scanned'
                confidence = 'high'

            return {
                'type': pdf_type,
                'total_pages': total_pages,
                'total_chars': total_chars,
                'avg_chars_per_page': round(avg_chars_per_page, 2),
                'confidence': confidence
            }

        except Exception as e:
            print(f"  ❌ Error analyzing PDF: {e}")
            return {
                'type': 'error',
                'error': str(e)
            }

    def analyze_collection(self, collection_key: str):
        """
        Analyze all PDF attachments in a collection.

        Args:
            collection_key: The key of the collection to analyze
        """
        items = self.get_collection_items(collection_key)

        if not items:
            print("No items found in collection")
            return

        print(f"\n{'='*80}")
        print(f"PDF Analysis Report")
        print(f"{'='*80}\n")

        pdf_count = 0
        digital_count = 0
        scanned_count = 0
        error_count = 0

        for item in items:
            # Skip if the item itself is an attachment or note
            if item['data'].get('itemType') in ['attachment', 'note']:
                continue

            item_data = item['data']
            item_title = item_data.get('title', 'Untitled')
            item_key = item['key']

            # Get attachments for this item
            attachments = self.get_item_attachments(item_key)

            # Filter for PDF attachments
            pdf_attachments = [att for att in attachments if self.is_pdf_attachment(att)]

            if not pdf_attachments:
                continue

            # Process each PDF attachment
            for attachment in pdf_attachments:
                pdf_count += 1
                attachment_title = attachment['data'].get('title', 'Untitled PDF')
                attachment_key = attachment['key']

                print(f"📄 {item_title}")
                print(f"   Attachment: {attachment_title}")

                # Download and analyze the PDF
                pdf_content = self.download_attachment(attachment_key)

                if pdf_content is None:
                    print(f"   ⚠️  Could not download PDF")
                    error_count += 1
                    print()
                    continue

                # Analyze the PDF
                analysis = self.analyze_pdf_type(pdf_content)

                if analysis['type'] == 'error':
                    print(f"   ⚠️  Error: {analysis['error']}")
                    error_count += 1
                else:
                    pdf_type = analysis['type'].upper()
                    confidence = analysis['confidence'].upper()
                    pages = analysis['total_pages']
                    avg_chars = analysis['avg_chars_per_page']

                    # Use emoji indicators
                    type_emoji = '📝' if analysis['type'] == 'digital' else '🖼️'

                    print(f"   {type_emoji} Type: {pdf_type} (confidence: {confidence})")
                    print(f"   📊 Pages: {pages} | Avg chars/page: {avg_chars}")

                    if analysis['type'] == 'digital':
                        digital_count += 1
                    else:
                        scanned_count += 1

                print()

        # Print summary
        print(f"{'='*80}")
        print(f"Summary")
        print(f"{'='*80}")
        print(f"Total PDFs analyzed: {pdf_count}")
        print(f"  📝 Digital PDFs: {digital_count}")
        print(f"  🖼️  Scanned PDFs: {scanned_count}")
        if error_count > 0:
            print(f"  ⚠️  Errors: {error_count}")
        print()


def main():
    """Main entry point."""
    import argparse
    from dotenv import load_dotenv

    # Load environment variables
    load_dotenv()

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Analyze PDF attachments in a Zotero collection'
    )
    parser.add_argument(
        '--list-collections',
        action='store_true',
        help='List all available collections and exit'
    )
    parser.add_argument(
        '--collection',
        type=str,
        help='Collection key to analyze (overrides ZOTERO_COLLECTION_KEY env var)'
    )

    args = parser.parse_args()

    # Get configuration from environment
    library_id = os.getenv('ZOTERO_LIBRARY_ID')
    library_type = os.getenv('ZOTERO_LIBRARY_TYPE', 'user')
    api_key = os.getenv('ZOTERO_API_KEY')
    collection_key = args.collection or os.getenv('ZOTERO_COLLECTION_KEY')

    # Validate required configuration
    if not library_id or not api_key:
        print("Error: Missing required environment variables")
        print("Please set ZOTERO_LIBRARY_ID and ZOTERO_API_KEY in your .env file")
        return

    # Initialize analyzer
    analyzer = ZoteroPDFAnalyzer(library_id, library_type, api_key)

    # Handle --list-collections flag
    if args.list_collections:
        analyzer.print_collections()
        return

    # Validate collection key
    if not collection_key:
        print("Error: No collection specified")
        print("Either:")
        print("  1. Set ZOTERO_COLLECTION_KEY in your .env file, or")
        print("  2. Use --collection COLLECTION_KEY argument")
        print("\nTip: Run with --list-collections to see available collections")
        return

    # Analyze the collection
    print(f"Analyzing PDFs in collection: {collection_key}")
    analyzer.analyze_collection(collection_key)


if __name__ == '__main__':
    main()
