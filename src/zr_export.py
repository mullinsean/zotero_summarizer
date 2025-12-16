#!/usr/bin/env python3
"""
ZoteroResearcher Export Module

Handles exporting collections to NotebookLM format (PDFs, TXT, and Markdown).
"""

import os
import re
import time
from pathlib import Path
from typing import Optional, Dict, List, Set

# Handle both relative and absolute imports
try:
    from .zr_common import ZoteroResearcherBase
except ImportError:
    from zr_common import ZoteroResearcherBase


class ZoteroNotebookLMExporter(ZoteroResearcherBase):
    """Handles exporting Zotero collections to NotebookLM format."""

    def __init__(
        self,
        library_id: str,
        library_type: str,
        api_key: str,
        anthropic_api_key: str,
        verbose: bool = False
    ):
        """
        Initialize the NotebookLM exporter.

        Args:
            library_id: Your Zotero user ID or group ID
            library_type: 'user' or 'group'
            api_key: Your Zotero API key
            anthropic_api_key: Anthropic API key (required by base class, not used for export)
            verbose: If True, show detailed information
        """
        # Initialize base class without project name
        super().__init__(
            library_id=library_id,
            library_type=library_type,
            api_key=api_key,
            anthropic_api_key=anthropic_api_key,
            project_name=None,
            force_rebuild=False,
            verbose=verbose
        )

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename to be filesystem-safe.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename safe for filesystem
        """
        # Remove or replace problematic characters
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # Remove control characters
        sanitized = re.sub(r'[\x00-\x1f\x7f]', '', sanitized)
        # Collapse multiple spaces/underscores
        sanitized = re.sub(r'[\s_]+', '_', sanitized)
        # Remove leading/trailing spaces and dots
        sanitized = sanitized.strip(' .')
        # Limit length (leave room for extension)
        max_length = 200
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
        # Ensure not empty
        if not sanitized:
            sanitized = 'untitled'
        return sanitized

    def _get_export_filename(self, item: Dict, attachment: Dict, extension: str) -> str:
        """
        Generate a unique filename for export.

        Args:
            item: The parent item
            attachment: The attachment item
            extension: File extension (e.g., 'pdf', 'txt', 'md')

        Returns:
            Sanitized filename with extension
        """
        item_data = item['data']
        attachment_data = attachment['data']

        # Try to get a meaningful name from item title or attachment filename
        item_title = item_data.get('title', '')
        attachment_filename = attachment_data.get('filename', attachment_data.get('title', ''))

        # Prefer item title if available
        if item_title:
            base_name = self._sanitize_filename(item_title)
        elif attachment_filename:
            # Remove extension from attachment filename
            base_name = self._sanitize_filename(os.path.splitext(attachment_filename)[0])
        else:
            # Fallback to item key
            base_name = f"item_{item['key']}"

        # Add attachment key to ensure uniqueness
        attachment_key = attachment['key']
        filename = f"{base_name}_{attachment_key}.{extension}"

        return filename

    def _export_pdf_attachment(
        self,
        attachment: Dict,
        item: Dict,
        output_dir: Path
    ) -> Optional[str]:
        """
        Export PDF attachment to output directory.

        Args:
            attachment: The attachment item
            item: The parent item
            output_dir: Output directory path

        Returns:
            Filename of exported file, or None if export failed
        """
        try:
            attachment_key = attachment['key']

            # Download PDF content
            content = self.download_attachment(attachment_key)
            if not content:
                print(f"    ⚠️  Could not download PDF attachment")
                return None

            # Generate filename
            filename = self._get_export_filename(item, attachment, 'pdf')
            filepath = output_dir / filename

            # Write to file
            with open(filepath, 'wb') as f:
                f.write(content)

            print(f"    ✓ Exported PDF: {filename}")
            return filename

        except Exception as e:
            print(f"    ⚠️  Error exporting PDF: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return None

    def _export_txt_attachment(
        self,
        attachment: Dict,
        item: Dict,
        output_dir: Path
    ) -> Optional[str]:
        """
        Export text attachment to output directory.

        Args:
            attachment: The attachment item
            item: The parent item
            output_dir: Output directory path

        Returns:
            Filename of exported file, or None if export failed
        """
        try:
            attachment_key = attachment['key']

            # Download text content
            content = self.download_attachment(attachment_key)
            if not content:
                print(f"    ⚠️  Could not download text attachment")
                return None

            # Generate filename
            filename = self._get_export_filename(item, attachment, 'txt')
            filepath = output_dir / filename

            # Write to file
            with open(filepath, 'wb') as f:
                f.write(content)

            print(f"    ✓ Exported text file: {filename}")
            return filename

        except Exception as e:
            print(f"    ⚠️  Error exporting text file: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return None

    def _export_html_attachment(
        self,
        attachment: Dict,
        item: Dict,
        output_dir: Path
    ) -> Optional[str]:
        """
        Export HTML attachment as Markdown to output directory.

        Args:
            attachment: The attachment item
            item: The parent item
            output_dir: Output directory path

        Returns:
            Filename of exported file, or None if export failed
        """
        try:
            attachment_key = attachment['key']

            # Download HTML content
            raw_content = self.download_attachment(attachment_key)
            if not raw_content:
                print(f"    ⚠️  Could not download HTML attachment")
                return None

            # Extract and convert to markdown using Trafilatura
            markdown_content = self.extract_text_from_html(raw_content)
            if not markdown_content:
                print(f"    ⚠️  Could not extract markdown from HTML")
                return None

            # Generate filename with .md extension
            filename = self._get_export_filename(item, attachment, 'md')
            filepath = output_dir / filename

            # Write markdown to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(markdown_content)

            print(f"    ✓ Exported HTML as Markdown: {filename}")
            return filename

        except Exception as e:
            print(f"    ⚠️  Error exporting HTML as Markdown: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return None

    def export_summaries_to_markdown(
        self,
        collection_key: str,
        project_name: str,
        output_file: str,
        subcollections: Optional[List[str]] = None,
        include_main: bool = False
    ) -> Dict[str, int]:
        """
        Export all ZResearcher summary notes to a single markdown file.

        Args:
            collection_key: Zotero collection key
            project_name: Name of the project to export summaries for
            output_file: Path to output markdown file
            subcollections: Optional list of subcollection names to filter
            include_main: If True, include main collection items when filtering subcollections

        Returns:
            Dict with export statistics (exported, skipped counts)
        """
        print(f"\n{'='*80}")
        print(f"EXPORTING ZRESEARCHER SUMMARIES TO MARKDOWN")
        print(f"{'='*80}\n")
        print(f"Project: {project_name}")
        print(f"Output file: {output_file}\n")

        # Get items from collection (with optional subcollection filtering)
        items = self.get_items_to_process(
            collection_key,
            subcollections=subcollections,
            include_main=include_main
        )

        if not items:
            print("⚠️  No items found in collection")
            return {'exported': 0, 'skipped': 0}

        print(f"Found {len(items)} items to process\n")

        # Statistics
        stats = {'exported': 0, 'skipped': 0}

        # Build the expected summary note prefix for this project
        summary_note_prefix = f"【ZResearcher Summary: {project_name}】"

        # Collect all summaries
        all_summaries = []

        # Process each item
        for idx, item in enumerate(items, 1):
            item_data = item['data']
            item_title = item_data.get('title', 'Untitled')
            item_key = item['key']

            # Skip notes and attachments (we only want parent items)
            item_type = item_data.get('itemType')
            if item_type in ['note', 'attachment']:
                continue

            print(f"[{idx}/{len(items)}] {item_title[:60]}")

            # Get child items (notes and attachments)
            try:
                children = self.zot.children(item_key)
                summary_found = False

                for child in children:
                    child_data = child['data']
                    if child_data.get('itemType') == 'note':
                        note_html = child_data.get('note', '')
                        # Check if this is the summary note for our project
                        note_title = self.get_note_title_from_html(note_html)
                        if summary_note_prefix in note_title:
                            # Extract the text content (markdown format)
                            note_text = self.extract_text_from_note_html(note_html)

                            # Add to our collection with a header
                            summary_entry = f"# {item_title}\n\n"
                            summary_entry += note_text
                            summary_entry += "\n\n" + "="*80 + "\n\n"

                            all_summaries.append(summary_entry)
                            stats['exported'] += 1
                            summary_found = True
                            print(f"  ✓ Found summary note")
                            break

                if not summary_found:
                    print(f"  ⚠️  No summary note found")
                    stats['skipped'] += 1

            except Exception as e:
                print(f"  ⚠️  Error processing item: {e}")
                if self.verbose:
                    import traceback
                    traceback.print_exc()
                stats['skipped'] += 1

        # Write all summaries to file
        if all_summaries:
            print(f"\n📝 Writing {len(all_summaries)} summaries to file...")

            # Create output directory if needed
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write the combined markdown file
            with open(output_file, 'w', encoding='utf-8') as f:
                # Write a header
                f.write(f"# ZResearcher Summaries: {project_name}\n\n")
                f.write(f"Total summaries: {len(all_summaries)}\n\n")
                f.write("="*80 + "\n\n")

                # Write all summaries
                for summary in all_summaries:
                    f.write(summary)

            print(f"✅ Successfully wrote summaries to: {output_file}")
        else:
            print(f"⚠️  No summaries found for project '{project_name}'")

        # Print summary
        print(f"\n{'='*80}")
        print(f"EXPORT COMPLETE")
        print(f"{'='*80}")
        print(f"📊 Summary:")
        print(f"  • Summaries exported: {stats['exported']}")
        print(f"  • Items skipped (no summary): {stats['skipped']}")
        if all_summaries:
            print(f"\n📁 File saved to: {output_file}")

        return stats

    def export_to_notebooklm(
        self,
        collection_key: str,
        output_dir: str,
        subcollections: Optional[List[str]] = None,
        include_main: bool = False
    ) -> Dict[str, int]:
        """
        Export collection to NotebookLM format.

        Args:
            collection_key: Zotero collection key
            output_dir: Output directory path
            subcollections: Optional list of subcollection names to filter
            include_main: If True, include main collection items when filtering subcollections

        Returns:
            Dict with export statistics (exported, skipped, failed counts by type)
        """
        print(f"\n{'='*80}")
        print(f"EXPORTING COLLECTION TO NOTEBOOKLM")
        print(f"{'='*80}\n")

        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        print(f"📁 Output directory: {output_path.absolute()}\n")

        # Get items from collection (with optional subcollection filtering)
        items = self.get_items_to_process(
            collection_key,
            subcollections=subcollections,
            include_main=include_main
        )

        if not items:
            print("⚠️  No items found in collection")
            return {
                'pdf_exported': 0, 'txt_exported': 0, 'html_exported': 0,
                'skipped': 0, 'failed': 0
            }

        print(f"Found {len(items)} items to process\n")

        # Statistics
        stats = {
            'pdf_exported': 0,
            'txt_exported': 0,
            'html_exported': 0,
            'skipped': 0,
            'failed': 0
        }

        # Track exported files to avoid duplicates
        exported_files: Set[str] = set()

        # Process each item
        for idx, item in enumerate(items, 1):
            item_data = item['data']
            item_title = item_data.get('title', 'Untitled')
            item_key = item['key']

            print(f"[{idx}/{len(items)}] {item_title[:60]}")

            # Get attachments
            attachments = self.get_item_attachments(item_key)

            if not attachments:
                print(f"  ⚠️  No attachments found")
                stats['skipped'] += 1
                continue

            # Process each attachment
            exported_count = 0
            for attachment in attachments:
                attachment_key = attachment['key']

                # Skip if already exported
                if attachment_key in exported_files:
                    continue

                # Export based on type
                filename = None
                if self.is_pdf_attachment(attachment):
                    filename = self._export_pdf_attachment(attachment, item, output_path)
                    if filename:
                        stats['pdf_exported'] += 1
                        exported_count += 1
                        exported_files.add(attachment_key)
                    else:
                        stats['failed'] += 1

                elif self.is_txt_attachment(attachment):
                    filename = self._export_txt_attachment(attachment, item, output_path)
                    if filename:
                        stats['txt_exported'] += 1
                        exported_count += 1
                        exported_files.add(attachment_key)
                    else:
                        stats['failed'] += 1

                elif self.is_html_attachment(attachment):
                    filename = self._export_html_attachment(attachment, item, output_path)
                    if filename:
                        stats['html_exported'] += 1
                        exported_count += 1
                        exported_files.add(attachment_key)
                    else:
                        stats['failed'] += 1
                else:
                    # Skip unsupported attachment types
                    if self.verbose:
                        attachment_data = attachment['data']
                        content_type = attachment_data.get('contentType', 'unknown')
                        print(f"    → Skipping unsupported attachment type: {content_type}")

            if exported_count == 0:
                stats['skipped'] += 1

            # Rate limiting
            if idx < len(items):
                time.sleep(0.5)

        # Print summary
        print(f"\n{'='*80}")
        print(f"EXPORT COMPLETE")
        print(f"{'='*80}")
        print(f"📊 Summary:")
        print(f"  • PDF files exported: {stats['pdf_exported']}")
        print(f"  • Text files exported: {stats['txt_exported']}")
        print(f"  • HTML→Markdown exported: {stats['html_exported']}")
        print(f"  • Items skipped (no attachments): {stats['skipped']}")
        print(f"  • Failed exports: {stats['failed']}")
        print(f"\n📁 Files saved to: {output_path.absolute()}")

        return stats
