#!/usr/bin/env python3
"""
Zotero Source Summarizer

This script processes sources in a Zotero collection, extracts content from
HTML and PDF attachments, and generates AI summaries using a custom prompt.
The summaries are saved as notes attached to the original sources.
"""

import os
import io
import time
from pyzotero import zotero
from pypdf import PdfReader
import fitz  # PyMuPDF
import trafilatura
import requests
from bs4 import BeautifulSoup
from typing import Optional, Dict, List
from anthropic import Anthropic

# Handle both relative and absolute imports
try:
    from .llm_extractor import LLMExtractor
except ImportError:
    from llm_extractor import LLMExtractor


class ZoteroSourceSummarizer:
    """Summarize sources in Zotero collections using LLM."""

    def __init__(
        self,
        library_id: str,
        library_type: str,
        api_key: str,
        anthropic_api_key: str,
        custom_prompt: str,
        force_resummary: bool = False,
        model: str = "claude-haiku-4-5-20251001"
    ):
        """
        Initialize the Zotero summarizer.

        Args:
            library_id: Your Zotero user ID or group ID
            library_type: 'user' or 'group'
            api_key: Your Zotero API key
            anthropic_api_key: Anthropic API key for Claude
            custom_prompt: Custom prompt template for summarization
            force_resummary: If True, re-summarize even if summary note already exists
            model: Claude model to use (default: claude-haiku-4-5 for cost efficiency)
        """
        self.zot = zotero.Zotero(library_id, library_type, api_key)
        self.anthropic_client = Anthropic(api_key=anthropic_api_key)
        self.custom_prompt = custom_prompt
        self.force_resummary = force_resummary
        self.model = model

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

    def has_summary_note(self, item_key: str) -> bool:
        """
        Check if an item already has a summary note.

        Args:
            item_key: The key of the parent item

        Returns:
            True if the item already has a summary note
        """
        children = self.zot.children(item_key)
        notes = [child for child in children if child['data'].get('itemType') == 'note']

        for note in notes:
            note_content = note['data'].get('note', '')
            # Check if note starts with our summary title pattern
            if note_content.startswith('# AI Summary:'):
                return True

        return False

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
            file_content = self.zot.file(attachment_key)
            return file_content
        except Exception as e:
            print(f"  ❌ Error downloading attachment: {e}")
            return None

    def extract_text_from_html(self, html_content: bytes, attachment_url: Optional[str] = None) -> Optional[str]:
        """
        Extract text from HTML content using Trafilatura.

        Args:
            html_content: HTML content as bytes
            attachment_url: Optional URL to fetch from if bytes fail

        Returns:
            Extracted text, or None if extraction fails
        """
        try:
            # Try to decode bytes to string
            html_string = html_content.decode('utf-8', errors='ignore')

            # Use Trafilatura for extraction
            markdown = trafilatura.extract(
                html_string,
                output_format='markdown',
                include_links=True,
                include_images=False,
                include_tables=True
            )

            if markdown:
                return markdown.strip()

            # If Trafilatura fails and we have a URL, try fetching directly
            if attachment_url and not markdown:
                print("  ⚠️  Trying to fetch from URL...")
                response = requests.get(attachment_url, timeout=30)
                response.raise_for_status()
                markdown = trafilatura.extract(
                    response.text,
                    output_format='markdown',
                    include_links=True,
                    include_images=False,
                    include_tables=True
                )
                if markdown:
                    return markdown.strip()

            return None

        except Exception as e:
            print(f"  ❌ Error extracting HTML: {e}")
            return None

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
            total_pages = len(pdf_document)

            # Extract text from each page
            for page_num in range(total_pages):
                page = pdf_document[page_num]
                text = page.get_text()
                if text.strip():
                    extracted_text.append(text)

            pdf_document.close()

            full_text = "\n\n".join(extracted_text) if extracted_text else None

            # Check if PDF is likely scanned (very little text)
            if full_text and total_pages > 0:
                avg_chars_per_page = len(full_text) / total_pages
                if avg_chars_per_page < 100:
                    print(f"  ⚠️  Warning: PDF appears to be scanned (low text density)")

            return full_text

        except Exception as e:
            print(f"  ❌ Error extracting PDF text: {e}")
            return None

    def summarize_with_llm(self, content: str, source_title: str) -> Optional[str]:
        """
        Generate a summary using Claude with the custom prompt.

        Args:
            content: The extracted content to summarize
            source_title: Title of the source for context

        Returns:
            Generated summary, or None if summarization fails
        """
        try:
            # Construct the user prompt with the extracted content
            user_prompt = self.custom_prompt.format(
                title=source_title,
                content=content
            )

            # Call Claude API
            response = self.anthropic_client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )

            # Extract the summary from the response
            if response.content and len(response.content) > 0:
                summary = response.content[0].text
                return summary.strip()
            else:
                print("  ❌ LLM returned empty response")
                return None

        except Exception as e:
            print(f"  ❌ Error calling LLM: {e}")
            return None

    def create_summary_note(self, parent_key: str, summary: str, source_title: str) -> bool:
        """
        Create a summary note in Zotero attached to a parent item.

        Args:
            parent_key: The key of the parent item
            summary: The summary content
            source_title: Title of the source

        Returns:
            True if note was created successfully
        """
        try:
            note_template = self.zot.item_template('note')
            note_template['note'] = f"# AI Summary: {source_title}\n\n{summary}"
            note_template['parentItem'] = parent_key

            result = self.zot.create_items([note_template])

            if result['success']:
                print(f"  ✅ Summary note created successfully")
                return True
            else:
                print(f"  ❌ Failed to create note: {result}")
                return False
        except Exception as e:
            print(f"  ❌ Error creating note: {e}")
            return False

    def process_collection(self, collection_key: str):
        """
        Process all items in a collection and generate summaries.

        Args:
            collection_key: The key of the collection to process
        """
        items = self.get_collection_items(collection_key)

        if not items:
            print("No items found in collection")
            return

        print(f"\n{'='*80}")
        print(f"Source Summarization Report")
        print(f"{'='*80}\n")

        processed = 0
        skipped = 0
        already_summarized = 0
        errors = 0

        for item in items:
            # Skip if the item itself is an attachment or note
            if item['data'].get('itemType') in ['attachment', 'note']:
                continue

            item_data = item['data']
            item_title = item_data.get('title', 'Untitled')
            item_key = item['key']

            print(f"\n📚 Processing: {item_title}")

            # Check if already summarized (unless force flag is set)
            if not self.force_resummary and self.has_summary_note(item_key):
                print(f"  ⏭️  Already has summary note, skipping...")
                already_summarized += 1
                continue

            # Get attachments for this item
            attachments = self.get_item_attachments(item_key)

            if not attachments:
                print(f"  ⚠️  No attachments found")
                skipped += 1
                continue

            # Try to extract content from attachments
            extracted_content = None
            content_type = None

            for attachment in attachments:
                attachment_title = attachment['data'].get('title', 'Untitled')
                attachment_key = attachment['key']
                attachment_url = attachment['data'].get('url')

                # Try HTML extraction
                if self.is_html_attachment(attachment):
                    print(f"  📄 Found HTML attachment: {attachment_title}")
                    print(f"  📥 Downloading and extracting...")

                    html_content = self.download_attachment(attachment_key)
                    if html_content:
                        extracted_content = self.extract_text_from_html(html_content, attachment_url)
                        if extracted_content:
                            content_type = "HTML"
                            break

                # Try PDF extraction
                elif self.is_pdf_attachment(attachment):
                    print(f"  📄 Found PDF attachment: {attachment_title}")
                    print(f"  📥 Downloading and extracting...")

                    pdf_content = self.download_attachment(attachment_key)
                    if pdf_content:
                        extracted_content = self.extract_text_from_pdf(pdf_content)
                        if extracted_content:
                            content_type = "PDF"
                            break

            if not extracted_content:
                print(f"  ❌ Could not extract content from any attachment")
                errors += 1
                continue

            print(f"  ✅ Extracted {len(extracted_content)} characters from {content_type}")

            # Generate summary with LLM
            print(f"  🤖 Generating summary with {self.model}...")
            summary = self.summarize_with_llm(extracted_content, item_title)

            if not summary:
                print(f"  ❌ Failed to generate summary")
                errors += 1
                continue

            print(f"  ✅ Summary generated ({len(summary)} characters)")

            # Create note in Zotero
            print(f"  💾 Saving summary to Zotero...")
            if self.create_summary_note(item_key, summary, item_title):
                processed += 1
            else:
                errors += 1

            # Rate limiting - be nice to the APIs
            print(f"  ⏳ Rate limiting (1 second)...")
            time.sleep(1)

        # Print summary
        print(f"\n{'='*80}")
        print(f"Summary")
        print(f"{'='*80}")
        print(f"Total items processed: {len(items)}")
        print(f"  ✅ Successfully summarized: {processed}")
        print(f"  ⏭️  Already had summaries: {already_summarized}")
        print(f"  ⚠️  Skipped (no attachments): {skipped}")
        print(f"  ❌ Errors: {errors}")
        print()


def load_custom_prompt(prompt_file: str = "summarize_prompt.txt") -> str:
    """
    Load custom prompt from file, or return default prompt.

    Args:
        prompt_file: Path to the prompt file

    Returns:
        Custom prompt template string
    """
    if os.path.exists(prompt_file):
        print(f"Loading custom prompt from: {prompt_file}")
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    else:
        print(f"No custom prompt file found at {prompt_file}, using default prompt")
        return """Please provide a comprehensive summary of the following source.

Title: {title}

Content:
{content}

Instructions:
- Provide a clear, concise summary of the main points
- Highlight key findings, arguments, or insights
- Include any important data, statistics, or evidence
- Note any methodologies or approaches used
- Identify the target audience and purpose
- Use markdown formatting for better readability
- Structure with headings and bullet points where appropriate

Please provide your summary below:"""


def main():
    """Main entry point."""
    import argparse
    from dotenv import load_dotenv

    # Load environment variables
    load_dotenv()

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Generate AI summaries for sources in a Zotero collection'
    )
    parser.add_argument(
        '--list-collections',
        action='store_true',
        help='List all available collections and exit'
    )
    parser.add_argument(
        '--collection',
        type=str,
        help='Collection key to process (overrides ZOTERO_COLLECTION_KEY env var)'
    )
    parser.add_argument(
        '--prompt-file',
        type=str,
        default='summarize_prompt.txt',
        help='Path to custom prompt file (default: summarize_prompt.txt)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Re-summarize items even if summary note already exists'
    )
    parser.add_argument(
        '--model',
        type=str,
        default='claude-haiku-4-5-20251001',
        help='Claude model to use (default: claude-haiku-4-5-20251001)'
    )

    args = parser.parse_args()

    # Get configuration from environment
    library_id = os.getenv('ZOTERO_LIBRARY_ID')
    library_type = os.getenv('ZOTERO_LIBRARY_TYPE', 'user')
    zotero_api_key = os.getenv('ZOTERO_API_KEY')
    anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
    collection_key = args.collection or os.getenv('ZOTERO_COLLECTION_KEY')

    # Validate required configuration
    if not library_id or not zotero_api_key:
        print("Error: Missing required Zotero environment variables")
        print("Please set ZOTERO_LIBRARY_ID and ZOTERO_API_KEY in your .env file")
        return

    if not anthropic_api_key:
        print("Error: Missing required ANTHROPIC_API_KEY")
        print("Please set ANTHROPIC_API_KEY in your .env file")
        return

    # Initialize summarizer
    summarizer = ZoteroSourceSummarizer(
        library_id,
        library_type,
        zotero_api_key,
        anthropic_api_key,
        custom_prompt="",  # Will be loaded below
        force_resummary=args.force,
        model=args.model
    )

    # Handle --list-collections flag
    if args.list_collections:
        summarizer.print_collections()
        return

    # Validate collection key
    if not collection_key:
        print("Error: No collection specified")
        print("Either:")
        print("  1. Set ZOTERO_COLLECTION_KEY in your .env file, or")
        print("  2. Use --collection COLLECTION_KEY argument")
        print("\nTip: Run with --list-collections to see available collections")
        return

    # Load custom prompt
    custom_prompt = load_custom_prompt(args.prompt_file)
    summarizer.custom_prompt = custom_prompt

    # Process the collection
    print(f"Processing collection: {collection_key}")
    print(f"Using model: {args.model}")
    print()
    summarizer.process_collection(collection_key)


if __name__ == '__main__':
    main()
