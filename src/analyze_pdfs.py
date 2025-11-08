#!/usr/bin/env python3
"""
Zotero PDF Analyzer

This script accesses a Zotero collection, identifies PDF attachments,
and determines whether they are digital (selectable text) or scanned (OCR).
"""

import os
import re
from pyzotero import zotero
from pypdf import PdfReader
from typing import Optional, Dict, List
import io
import fitz  # PyMuPDF


class ZoteroPDFAnalyzer:
    """Analyze PDF attachments in Zotero collections."""

    def __init__(
        self,
        library_id: str,
        library_type: str,
        api_key: str,
        output_dir: str = 'pdf_extracts',
        extract_text: bool = False
    ):
        """
        Initialize the Zotero client.

        Args:
            library_id: Your Zotero user ID or group ID
            library_type: 'user' or 'group'
            api_key: Your Zotero API key
            output_dir: Directory to save extracted text files (default: 'pdf_extracts')
            extract_text: If True, extract text from digital PDFs
        """
        self.zot = zotero.Zotero(library_id, library_type, api_key)
        self.output_dir = output_dir
        self.extract_text = extract_text

        # Create output directory if text extraction is enabled
        if self.extract_text and not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            print(f"Created output directory: {self.output_dir}")

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

    def extract_text_from_pdf(self, pdf_content: bytes) -> Optional[str]:
        """
        Extract text from a PDF using PyMuPDF.

        Args:
            pdf_content: The PDF file content as bytes

        Returns:
            Extracted text as string, or None if extraction failed
        """
        try:
            # Open PDF from bytes
            pdf_document = fitz.open(stream=pdf_content, filetype="pdf")

            extracted_text = []

            # Extract text from each page
            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                text = page.get_text()
                if text.strip():
                    extracted_text.append(f"--- Page {page_num + 1} ---\n")
                    extracted_text.append(text)
                    extracted_text.append("\n\n")

            pdf_document.close()

            return "".join(extracted_text) if extracted_text else None

        except Exception as e:
            print(f"  ❌ Error extracting text: {e}")
            return None

    def sanitize_filename(self, filename: str) -> str:
        """
        Convert a string to a safe filename.

        Args:
            filename: The original filename/title

        Returns:
            Sanitized filename safe for filesystem
        """
        # Remove or replace problematic characters
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # Replace spaces with underscores
        filename = filename.replace(' ', '_')
        # Limit length
        if len(filename) > 200:
            filename = filename[:200]
        # Remove leading/trailing dots and spaces
        filename = filename.strip('. ')
        return filename if filename else 'untitled'

    def save_text_to_file(self, text: str, item_title: str, attachment_title: str, attachment_key: str) -> Optional[str]:
        """
        Save extracted text to a file.

        Args:
            text: The extracted text to save
            item_title: Title of the parent item
            attachment_title: Title of the attachment
            attachment_key: Key of the attachment (used for uniqueness)

        Returns:
            Path to the saved file, or None if save failed
        """
        try:
            # Create a safe filename
            safe_item = self.sanitize_filename(item_title)
            safe_attachment = self.sanitize_filename(attachment_title)

            # Use attachment key to ensure uniqueness
            filename = f"{safe_item}_{safe_attachment}_{attachment_key}.txt"
            filepath = os.path.join(self.output_dir, filename)

            # Write the text to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Source: {item_title}\n")
                f.write(f"Attachment: {attachment_title}\n")
                f.write(f"Attachment Key: {attachment_key}\n")
                f.write(f"{'='*80}\n\n")
                f.write(text)

            return filepath

        except Exception as e:
            print(f"  ❌ Error saving text to file: {e}")
            return None

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

                        # Extract and save text if enabled and PDF is digital
                        if self.extract_text:
                            print(f"   💾 Extracting text...")
                            extracted_text = self.extract_text_from_pdf(pdf_content)

                            if extracted_text:
                                saved_path = self.save_text_to_file(
                                    extracted_text,
                                    item_title,
                                    attachment_title,
                                    attachment_key
                                )
                                if saved_path:
                                    print(f"   ✅ Saved to: {saved_path}")
                            else:
                                print(f"   ⚠️  No text could be extracted")
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
    parser.add_argument(
        '--extract-text',
        action='store_true',
        help='Extract text from digital PDFs and save to files'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='pdf_extracts',
        help='Directory to save extracted text files (default: pdf_extracts)'
    )

    args = parser.parse_args()

    # Get configuration from environment
    library_id = os.getenv('ZOTERO_LIBRARY_ID')
    library_type_raw = os.getenv('ZOTERO_LIBRARY_TYPE', 'user')
    api_key = os.getenv('ZOTERO_API_KEY')
    collection_key = args.collection or os.getenv('ZOTERO_COLLECTION_KEY')

    # Sanitize library_type: strip quotes and whitespace
    library_type = library_type_raw.strip().strip("'\"") if library_type_raw else 'user'

    # Validate library_type
    if library_type not in ['user', 'group']:
        print(f"Error: Invalid ZOTERO_LIBRARY_TYPE: '{library_type_raw}'")
        print("Must be either 'user' or 'group' (without quotes in .env file)")
        print(f"Example .env entry: ZOTERO_LIBRARY_TYPE=group")
        return

    # Validate required configuration
    if not library_id or not api_key:
        print("Error: Missing required environment variables")
        print("Please set ZOTERO_LIBRARY_ID and ZOTERO_API_KEY in your .env file")
        return

    # Initialize analyzer
    analyzer = ZoteroPDFAnalyzer(
        library_id,
        library_type,
        api_key,
        output_dir=args.output_dir,
        extract_text=args.extract_text
    )

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
