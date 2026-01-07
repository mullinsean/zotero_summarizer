#!/usr/bin/env python3
"""
ZoteroResearcher Export Module

Handles exporting collections to various formats:
- NotebookLM format (PDFs, TXT, and Markdown)
- Source directory tables for report-system
- Vault exports with YAML frontmatter
- Claude Code multi-agent exports with batching
"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Set, Any

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
        verbose: bool = False,
        enable_cache: bool = False,
        offline: bool = False
    ):
        """
        Initialize the NotebookLM exporter.

        Args:
            library_id: Your Zotero user ID or group ID
            library_type: 'user' or 'group'
            api_key: Your Zotero API key
            anthropic_api_key: Anthropic API key (required by base class, not used for export)
            verbose: If True, show detailed information
            enable_cache: If True, enable local caching
            offline: If True, use cached data only (requires enable_cache)
        """
        # Initialize base class without project name
        super().__init__(
            library_id=library_id,
            library_type=library_type,
            api_key=api_key,
            anthropic_api_key=anthropic_api_key,
            project_name=None,
            force_rebuild=False,
            verbose=verbose,
            enable_cache=enable_cache,
            offline=offline
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
        output_path: str,
        subcollections: Optional[List[str]] = None,
        include_main: bool = False,
        separate_files: bool = False
    ) -> Dict[str, int]:
        """
        Export all ZResearcher summary notes to markdown file(s).

        Args:
            collection_key: Zotero collection key
            project_name: Name of the project to export summaries for
            output_path: Path to output markdown file (consolidated) or directory (separate files)
            subcollections: Optional list of subcollection names to filter
            include_main: If True, include main collection items when filtering subcollections
            separate_files: If True, export each summary as a separate file in output_path directory

        Returns:
            Dict with export statistics (exported, skipped counts)
        """
        print(f"\n{'='*80}")
        print(f"EXPORTING ZRESEARCHER SUMMARIES TO MARKDOWN")
        print(f"{'='*80}\n")
        print(f"Project: {project_name}")
        if separate_files:
            print(f"Mode: Separate files")
            print(f"Output directory: {output_path}\n")
        else:
            print(f"Mode: Single consolidated file")
            print(f"Output file: {output_path}\n")

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

        # Collect all summaries with item titles
        all_summaries = []  # List of tuples: (item_title, summary_text)

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

                            # Store tuple of (item_title, summary_text)
                            all_summaries.append((item_title, summary_entry))
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

        # Write all summaries to file(s)
        if all_summaries:
            if separate_files:
                # Separate files mode: create directory and write individual files
                print(f"\n📝 Writing {len(all_summaries)} summaries as separate files...")

                # Create output directory
                output_dir = Path(output_path)
                output_dir.mkdir(parents=True, exist_ok=True)

                # Write each summary to a separate file
                for idx, (item_title, summary_text) in enumerate(all_summaries, 1):
                    # Sanitize filename
                    safe_title = self._sanitize_filename(item_title)
                    filename = f"{idx:03d}_{safe_title}.md"
                    filepath = output_dir / filename

                    # Write individual file
                    with open(filepath, 'w', encoding='utf-8') as f:
                        # The summary_text already has the title header and content
                        f.write(summary_text)

                    if self.verbose:
                        print(f"  ✓ Wrote {filename}")

                print(f"✅ Successfully wrote {len(all_summaries)} summaries to: {output_dir}")

            else:
                # Consolidated mode: write single file
                print(f"\n📝 Writing {len(all_summaries)} summaries to consolidated file...")

                # Create output directory if needed
                output_file_path = Path(output_path)
                output_file_path.parent.mkdir(parents=True, exist_ok=True)

                # Write the combined markdown file
                with open(output_path, 'w', encoding='utf-8') as f:
                    # Write a header
                    f.write(f"# ZResearcher Summaries: {project_name}\n\n")
                    f.write(f"Total summaries: {len(all_summaries)}\n\n")
                    f.write("="*80 + "\n\n")

                    # Write all summaries
                    for item_title, summary_text in all_summaries:
                        f.write(summary_text)

                print(f"✅ Successfully wrote summaries to: {output_path}")
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
            if separate_files:
                print(f"\n📁 Files saved to: {output_path}/")
            else:
                print(f"\n📁 File saved to: {output_path}")

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

    def _format_authors_for_table(self, item: Dict) -> str:
        """Format authors for table display (shortened form)."""
        item_data = item['data']
        creators = item_data.get('creators', [])
        if not creators:
            return 'Unknown'

        # Get first author
        first = creators[0]
        if 'lastName' in first:
            name = first['lastName']
        elif 'name' in first:
            name = first['name'].split()[-1] if first['name'] else 'Unknown'
        else:
            name = 'Unknown'

        # Add "et al." if multiple authors
        if len(creators) > 1:
            return f"{name} et al."
        return name

    def _format_authors_list(self, item: Dict) -> List[str]:
        """Format authors as a list for YAML frontmatter."""
        item_data = item['data']
        creators = item_data.get('creators', [])
        authors = []
        for creator in creators:
            if 'lastName' in creator:
                if 'firstName' in creator:
                    authors.append(f"{creator['lastName']}, {creator['firstName']}")
                else:
                    authors.append(creator['lastName'])
            elif 'name' in creator:
                authors.append(creator['name'])
        return authors if authors else ['Unknown']

    def _extract_year(self, item: Dict) -> str:
        """Extract year from item date."""
        date = item['data'].get('date', '')
        if date:
            # Try to extract 4-digit year
            match = re.search(r'\b(\d{4})\b', date)
            if match:
                return match.group(1)
        return 'n.d.'

    def _generate_citekey(self, item: Dict) -> str:
        """Generate a citation key (author + year format)."""
        author = self._format_authors_for_table(item).replace(' et al.', '').lower()
        # Remove special characters
        author = re.sub(r'[^a-z]', '', author)
        year = self._extract_year(item)
        return f"{author}{year}"

    def _parse_summary_note_for_export(self, summary_content: str) -> Dict:
        """
        Parse enhanced summary note content to extract structured fields for export.

        Args:
            summary_content: The summary note content as markdown text

        Returns:
            Dict with extracted fields (with defaults for missing/old format notes)
        """
        result = {
            # Classification
            'research_type': 'unknown',
            'project_role': 'supporting',
            # Temporal fit
            'temporal_status': 'current',
            'temporal_context': '',
            # Quality indicators
            'peer_reviewed': 'unclear',
            'evidence_strength': 'moderate',
            'limitations': '',
            'biases': '',
            # Structural guidance
            'relevant_sections': [],
            'skip_sections': [],
            # Key claims
            'key_claims': []
        }

        # Parse Classification section
        research_match = re.search(r'\*\*Research Type\*\*:\s*(\w+)', summary_content)
        if research_match:
            result['research_type'] = research_match.group(1).lower()

        role_match = re.search(r'\*\*Project Role\*\*:\s*(\w+)', summary_content)
        if role_match:
            result['project_role'] = role_match.group(1).lower()

        # Parse Temporal Status (format: "status (context)" or just "status")
        temporal_match = re.search(r'\*\*Temporal Status\*\*:\s*(\w+)(?:\s*\(([^)]+)\))?', summary_content)
        if temporal_match:
            result['temporal_status'] = temporal_match.group(1).lower()
            if temporal_match.group(2):
                result['temporal_context'] = temporal_match.group(2).strip()

        # Parse Quality Assessment
        peer_match = re.search(r'\*\*Peer Reviewed\*\*:\s*(\w+)', summary_content)
        if peer_match:
            result['peer_reviewed'] = peer_match.group(1).lower()

        strength_match = re.search(r'\*\*Evidence Strength\*\*:\s*(\w+)', summary_content)
        if strength_match:
            result['evidence_strength'] = strength_match.group(1).lower()

        limitations_match = re.search(r'\*\*Limitations\*\*:\s*(.+?)(?=\n\*\*|\n##|\Z)', summary_content, re.DOTALL)
        if limitations_match:
            result['limitations'] = limitations_match.group(1).strip()

        biases_match = re.search(r'\*\*Potential Biases\*\*:\s*(.+?)(?=\n##|\Z)', summary_content, re.DOTALL)
        if biases_match:
            result['biases'] = biases_match.group(1).strip()

        # Parse Structural Guidance
        relevant_match = re.search(r'\*\*Most Relevant Sections\*\*:\s*(.+?)(?=\n\*\*|\n##|\Z)', summary_content, re.DOTALL)
        if relevant_match:
            sections_str = relevant_match.group(1).strip()
            if sections_str and sections_str.lower() != 'not specified':
                result['relevant_sections'] = [s.strip() for s in sections_str.split(',') if s.strip()]

        skip_match = re.search(r'\*\*Sections to Skip\*\*:\s*(.+?)(?=\n##|\Z)', summary_content, re.DOTALL)
        if skip_match:
            sections_str = skip_match.group(1).strip()
            if sections_str and sections_str.lower() != 'none':
                result['skip_sections'] = [s.strip() for s in sections_str.split(',') if s.strip()]

        # Parse Key Claims section
        claims_match = re.search(r'## Key Claims\n(.+?)(?=\n---|\Z)', summary_content, re.DOTALL)
        if claims_match:
            claims_text = claims_match.group(1).strip()
            if claims_text.lower() != 'none extracted':
                # Parse numbered claims with optional [Qn] notation
                claim_pattern = re.compile(r'^\s*\d+\.\s*(?:\[([^\]]+)\])?\s*(.+?)(?=\n\d+\.|\Z)', re.MULTILINE | re.DOTALL)
                for match in claim_pattern.finditer(claims_text):
                    q_links_str = match.group(1)
                    claim_text = match.group(2).strip()
                    questions = []
                    if q_links_str:
                        q_numbers = re.findall(r'Q(\d+)', q_links_str)
                        questions = [int(q) for q in q_numbers]
                    if claim_text:
                        result['key_claims'].append({
                            'claim': claim_text,
                            'linked_questions': questions
                        })

        return result

    def export_source_directory(
        self,
        collection_key: str,
        output_path: str,
        project_name: Optional[str] = None,
        subcollections: Optional[List[str]] = None,
        include_main: bool = False,
        append: bool = False
    ) -> Dict[str, int]:
        """
        Export source directory table for report-system vault.

        Args:
            collection_key: Zotero collection key
            output_path: Output markdown file path
            project_name: Optional project name filter
            subcollections: Optional list of subcollection names to filter
            include_main: If True, include main collection items when filtering subcollections
            append: If True, append to existing file

        Returns:
            Dict with export statistics
        """
        print(f"\n{'='*80}")
        print(f"EXPORTING SOURCE DIRECTORY")
        print(f"{'='*80}\n")
        print(f"Output: {output_path}")
        if project_name:
            print(f"Project filter: {project_name}")

        # Get items from collection
        items = self.get_items_to_process(
            collection_key,
            subcollections=subcollections,
            include_main=include_main
        )

        if not items:
            print("⚠️  No items found in collection")
            return {'exported': 0, 'skipped': 0}

        # Filter out notes and attachments
        items = [i for i in items if i['data'].get('itemType') not in ['note', 'attachment']]
        print(f"Found {len(items)} items to export\n")

        stats = {'exported': 0, 'skipped': 0}

        # Get collection name
        try:
            collection = self.zot.collection(collection_key)
            collection_name = collection['data'].get('name', collection_key)
        except Exception:
            collection_name = collection_key

        # Build table rows
        rows = []
        for item in items:
            item_data = item['data']

            # Skip if filtering by project and item doesn't have summary for this project
            if project_name:
                summary_note_prefix = f"【ZResearcher Summary: {project_name}】"
                children = self.zot.children(item['key'])
                has_summary = any(
                    child['data'].get('itemType') == 'note' and
                    summary_note_prefix in self.get_note_title_from_html(child['data'].get('note', ''))
                    for child in children
                )
                if not has_summary:
                    stats['skipped'] += 1
                    continue

            citekey = self._generate_citekey(item)
            author = self._format_authors_for_table(item)
            year = self._extract_year(item)
            title = item_data.get('title', 'Untitled')
            item_type = item_data.get('itemType', 'unknown')

            rows.append(f"| {citekey} | {author} | {year} | {title} | {item_type} |")
            stats['exported'] += 1

        # Create output directory if needed
        output_file_path = Path(output_path)
        output_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate content
        today = datetime.now().strftime('%Y-%m-%d')
        content = f"""---
title: Source Directory
last_updated: {today}
collection: {collection_name}
---

# Source Directory

## Zotero Sources

| Key | Author | Year | Title | Type |
|-----|--------|------|-------|------|
"""
        content += '\n'.join(rows) + '\n'

        # Write to file
        mode = 'a' if append else 'w'
        with open(output_path, mode, encoding='utf-8') as f:
            f.write(content)

        print(f"\n✅ Exported {stats['exported']} sources to {output_path}")
        if stats['skipped'] > 0:
            print(f"⚠️  Skipped {stats['skipped']} items (no matching project summary)")

        return stats

    def export_to_vault(
        self,
        collection_key: str,
        output_dir: str,
        project_name: Optional[str] = None,
        subcollections: Optional[List[str]] = None,
        include_main: bool = False
    ) -> Dict[str, int]:
        """
        Export individual source files with YAML frontmatter for vault integration.

        Args:
            collection_key: Zotero collection key
            output_dir: Output directory path
            project_name: Optional project name to include Phase 1 summaries
            subcollections: Optional list of subcollection names to filter
            include_main: If True, include main collection items when filtering subcollections

        Returns:
            Dict with export statistics
        """
        print(f"\n{'='*80}")
        print(f"EXPORTING TO VAULT")
        print(f"{'='*80}\n")
        print(f"Output directory: {output_dir}")
        if project_name:
            print(f"Including summaries for project: {project_name}")

        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Get items from collection
        items = self.get_items_to_process(
            collection_key,
            subcollections=subcollections,
            include_main=include_main
        )

        if not items:
            print("⚠️  No items found in collection")
            return {'exported': 0, 'skipped': 0, 'with_summary': 0}

        # Filter out notes and attachments
        items = [i for i in items if i['data'].get('itemType') not in ['note', 'attachment']]
        print(f"Found {len(items)} items to export\n")

        stats = {'exported': 0, 'skipped': 0, 'with_summary': 0}

        for idx, item in enumerate(items, 1):
            item_data = item['data']
            item_key = item['key']
            item_title = item_data.get('title', 'Untitled')

            print(f"[{idx}/{len(items)}] {item_title[:60]}")

            try:
                # Build YAML frontmatter
                citekey = self._generate_citekey(item)
                authors = self._format_authors_list(item)
                year = self._extract_year(item)

                frontmatter = {
                    'key': item_key,
                    'citekey': citekey,
                    'authors': authors,
                    'year': year,
                    'title': item_title,
                    'type': item_data.get('itemType', 'unknown'),
                    'publication': item_data.get('publicationTitle', item_data.get('bookTitle', '')),
                    'doi': item_data.get('DOI', ''),
                    'url': item_data.get('url', ''),
                    'abstract': item_data.get('abstractNote', ''),
                    'tags': [tag['tag'] for tag in item_data.get('tags', [])],
                    'has_summary': False
                }

                # Get children (notes and attachments)
                children = self.zot.children(item_key)

                # Look for Phase 1 summary if project specified
                summary_content = None
                if project_name:
                    summary_note_prefix = f"【ZResearcher Summary: {project_name}】"
                    for child in children:
                        if child['data'].get('itemType') == 'note':
                            note_html = child['data'].get('note', '')
                            note_title = self.get_note_title_from_html(note_html)
                            if summary_note_prefix in note_title:
                                summary_content = self.extract_text_from_note_html(note_html)
                                frontmatter['has_summary'] = True
                                stats['with_summary'] += 1
                                break

                # Collect Zotero notes (non-summary notes)
                zotero_notes = []
                for child in children:
                    if child['data'].get('itemType') == 'note':
                        note_html = child['data'].get('note', '')
                        note_title = self.get_note_title_from_html(note_html)
                        # Skip ZResearcher notes
                        if '【' not in note_title:
                            note_text = self.extract_text_from_note_html(note_html)
                            if note_text.strip():
                                zotero_notes.append(note_text)

                # Build markdown content
                yaml_content = "---\n"
                for key, value in frontmatter.items():
                    if isinstance(value, list):
                        if value:
                            yaml_content += f"{key}:\n"
                            for v in value:
                                yaml_content += f"  - {v}\n"
                        else:
                            yaml_content += f"{key}: []\n"
                    elif isinstance(value, bool):
                        yaml_content += f"{key}: {str(value).lower()}\n"
                    elif isinstance(value, str) and ('"' in value or '\n' in value or ':' in value):
                        # Quote strings with special characters
                        escaped = value.replace('"', '\\"').replace('\n', '\\n')
                        yaml_content += f'{key}: "{escaped}"\n'
                    elif value:
                        yaml_content += f"{key}: {value}\n"
                    else:
                        yaml_content += f"{key}:\n"
                yaml_content += "---\n\n"

                md_content = yaml_content
                md_content += f"# {item_title}\n\n"

                if frontmatter['abstract']:
                    md_content += "## Abstract\n\n"
                    md_content += f"{frontmatter['abstract']}\n\n"

                if zotero_notes:
                    md_content += "## Zotero Notes\n\n"
                    for note in zotero_notes:
                        md_content += f"{note}\n\n"

                if summary_content:
                    md_content += "## Phase 1 Summary\n\n"
                    md_content += f"{summary_content}\n\n"

                # Generate filename
                safe_title = self._sanitize_filename(item_title)
                filename = f"{citekey}_{safe_title}.md"
                filepath = output_path / filename

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(md_content)

                stats['exported'] += 1
                print(f"  ✓ Exported: {filename}")

            except Exception as e:
                print(f"  ⚠️  Error: {e}")
                if self.verbose:
                    import traceback
                    traceback.print_exc()
                stats['skipped'] += 1

            # Rate limiting
            if idx < len(items):
                time.sleep(0.1)

        # Print summary
        print(f"\n{'='*80}")
        print(f"EXPORT COMPLETE")
        print(f"{'='*80}")
        print(f"📊 Summary:")
        print(f"  • Sources exported: {stats['exported']}")
        print(f"  • With Phase 1 summary: {stats['with_summary']}")
        print(f"  • Skipped (errors): {stats['skipped']}")
        print(f"\n📁 Files saved to: {output_path.absolute()}")

        return stats

    def export_for_claude(
        self,
        collection_key: str,
        output_dir: str,
        project_name: str,
        include_full_content: bool = False,
        batch_tokens: int = 60000,
        subcollections: Optional[List[str]] = None,
        include_main: bool = False
    ) -> Dict[str, Any]:
        """
        Export collection data optimized for Claude Code skill consumption.

        Prerequisites: All sources must have Phase 1 summaries for the specified project.

        Args:
            collection_key: Zotero collection key
            output_dir: Output directory path
            project_name: Project name (required - summaries must exist)
            include_full_content: If True, also export full document content
            batch_tokens: Target tokens per batch (default: 60000)
            subcollections: Optional list of subcollection names to filter
            include_main: If True, include main collection items when filtering subcollections

        Returns:
            Manifest dict on success

        Raises:
            ValueError: If summaries are missing for any source
        """
        print(f"\n{'='*80}")
        print(f"EXPORTING FOR CLAUDE CODE")
        print(f"{'='*80}\n")
        print(f"Project: {project_name}")
        print(f"Output directory: {output_dir}")
        print(f"Include full content: {include_full_content}")
        print(f"Target tokens per batch: {batch_tokens}")

        # Create output directories
        output_path = Path(output_dir)
        summaries_path = output_path / "summaries"
        summaries_path.mkdir(parents=True, exist_ok=True)

        if include_full_content:
            content_path = output_path / "full_content"
            content_path.mkdir(parents=True, exist_ok=True)

        # Get items from collection
        items = self.get_items_to_process(
            collection_key,
            subcollections=subcollections,
            include_main=include_main
        )

        if not items:
            raise ValueError("No items found in collection")

        # Filter out notes and attachments
        items = [i for i in items if i['data'].get('itemType') not in ['note', 'attachment']]
        print(f"\nFound {len(items)} items to process")

        # Get collection name
        try:
            collection = self.zot.collection(collection_key)
            collection_name = collection['data'].get('name', collection_key)
        except Exception:
            collection_name = collection_key

        # Load project overview (project brief) if available
        project_brief = ""
        try:
            self.project_name = project_name
            subcollection_key = self.get_subcollection(collection_key, self._get_subcollection_name())
            if subcollection_key:
                notes = self.get_collection_notes(subcollection_key)
                project_overview_title = self._get_project_overview_note_title()
                for note in notes:
                    note_html = note['data'].get('note', '')
                    note_title = self.get_note_title_from_html(note_html)
                    if project_overview_title in note_title:
                        project_brief = self.extract_text_from_note_html(note_html)
                        break
        except Exception:
            pass

        # Process each item
        summary_note_prefix = f"【ZResearcher Summary: {project_name}】"
        citation_index = {}
        sources_with_summaries = []
        skipped_sources = []

        print(f"\nPhase 1: Collecting summaries...")
        for idx, item in enumerate(items, 1):
            item_data = item['data']
            item_key = item['key']
            item_title = item_data.get('title', 'Untitled')

            # Get children
            children = self.zot.children(item_key)

            # Look for summary note
            summary_content = None
            for child in children:
                if child['data'].get('itemType') == 'note':
                    note_html = child['data'].get('note', '')
                    note_title = self.get_note_title_from_html(note_html)
                    if summary_note_prefix in note_title:
                        summary_content = self.extract_text_from_note_html(note_html)
                        break

            if not summary_content:
                skipped_sources.append(item_title)
                continue

            # Extract metadata
            metadata = self.extract_metadata(item)
            citekey = self._generate_citekey(item)
            authors = self._format_authors_list(item)
            year = self._extract_year(item)

            # Estimate tokens (rough: words * 1.3)
            token_estimate = int(len(summary_content.split()) * 1.3)

            # Parse enhanced fields from summary (with defaults for old format)
            parsed_summary = self._parse_summary_note_for_export(summary_content)

            sources_with_summaries.append({
                'item_key': item_key,
                'citekey': citekey,
                'title': item_title,
                'summary': summary_content,
                'token_estimate': token_estimate,
                'metadata': metadata,
                'authors': authors,
                'year': year,
                'item': item,
                'parsed': parsed_summary  # Include parsed fields
            })

            # Build citation index entry with enhanced fields
            citation_index[item_key] = {
                'title': item_title,
                'authors': authors,
                'date': year,
                'publication': item_data.get('publicationTitle', item_data.get('bookTitle', '')),
                'url': item_data.get('url', ''),
                'zotero_link': f"zotero://select/items/{item_key}",
                'item_type': item_data.get('itemType', 'unknown'),
                'tags': [tag['tag'] for tag in item_data.get('tags', [])],
                'summary_file': None,  # Will be filled in
                'content_file': None,  # Will be filled in if include_full_content

                # Enhanced classification fields
                'research_type': parsed_summary['research_type'],
                'project_role': parsed_summary['project_role'],
                'temporal_fit': {
                    'status': parsed_summary['temporal_status'],
                    'context': parsed_summary['temporal_context']
                },
                'quality': {
                    'peer_reviewed': parsed_summary['peer_reviewed'],
                    'evidence_strength': parsed_summary['evidence_strength'],
                    'limitations': parsed_summary['limitations'],
                    'biases': parsed_summary['biases']
                },
                'structural_guidance': {
                    'relevant_sections': parsed_summary['relevant_sections'],
                    'skip_sections': parsed_summary['skip_sections']
                },
                'key_claims': parsed_summary['key_claims']
            }

        # Report skipped sources
        if skipped_sources:
            print(f"\n⚠️  Skipping {len(skipped_sources)} items without Phase 1 summaries:")
            for title in skipped_sources[:5]:
                print(f"   - {title[:60]}")
            if len(skipped_sources) > 5:
                print(f"   ... and {len(skipped_sources) - 5} more")
            print(f"   (Run --build-summaries to generate summaries for these sources)")

        if not sources_with_summaries:
            raise ValueError("No sources with Phase 1 summaries found. Run --build-summaries first.")

        print(f"\n✅ Found {len(sources_with_summaries)} sources with summaries")

        # Phase 2: Export summary files
        print(f"\nPhase 2: Exporting summary files...")
        for idx, source in enumerate(sources_with_summaries, 1):
            safe_title = self._sanitize_filename(source['title'])
            filename = f"{idx:03d}_{safe_title}.md"
            filepath = summaries_path / filename

            # Write summary file with header
            content = f"# {source['title']}\n\n"
            content += f"**Key**: {source['item_key']}\n"
            content += f"**Authors**: {', '.join(source['authors'])}\n"
            content += f"**Year**: {source['year']}\n"
            content += f"**Type**: {source['metadata'].get('itemType', 'unknown')}\n\n"
            content += "---\n\n"
            content += source['summary']

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            citation_index[source['item_key']]['summary_file'] = f"summaries/{filename}"

        # Phase 3: Export full content (optional)
        if include_full_content:
            print(f"\nPhase 3: Exporting full content...")
            for idx, source in enumerate(sources_with_summaries, 1):
                print(f"  [{idx}/{len(sources_with_summaries)}] {source['title'][:50]}")

                content, content_type = self.get_source_content(source['item'])
                if content:
                    filename = f"{source['item_key']}.md"
                    filepath = content_path / filename

                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(f"# {source['title']}\n\n")
                        f.write(f"Source type: {content_type}\n\n")
                        f.write("---\n\n")
                        f.write(content)

                    citation_index[source['item_key']]['content_file'] = f"full_content/{filename}"

        # Phase 4: Create batches
        print(f"\nPhase 4: Creating batches...")

        # Sort by token estimate (descending) for better packing
        sources_sorted = sorted(sources_with_summaries, key=lambda x: x['token_estimate'], reverse=True)

        batches = []
        current_batch = {'sources': [], 'token_estimate': 0}

        for source in sources_sorted:
            if current_batch['token_estimate'] + source['token_estimate'] > batch_tokens:
                if current_batch['sources']:
                    batches.append(current_batch)
                current_batch = {'sources': [], 'token_estimate': 0}

            current_batch['sources'].append(source['item_key'])
            current_batch['token_estimate'] += source['token_estimate']

        if current_batch['sources']:
            batches.append(current_batch)

        print(f"  Created {len(batches)} batches")

        # Create batch manifest
        batch_manifest = []
        for idx, batch in enumerate(batches, 1):
            batch_manifest.append({
                'batch_id': idx,
                'sources': batch['sources'],
                'token_estimate': batch['token_estimate']
            })

        # Phase 5: Write manifest and citation index
        print(f"\nPhase 5: Writing manifest files...")

        manifest = {
            'collection_key': collection_key,
            'collection_name': collection_name,
            'project_name': project_name,
            'project_brief': project_brief,
            'total_sources': len(sources_with_summaries),
            'skipped_sources': len(skipped_sources),
            'export_date': datetime.now().isoformat(),
            'zresearcher_version': '1.0.0',
            'batches': batch_manifest,
            'batch_config': {
                'target_tokens_per_batch': batch_tokens,
                'model_context_limit': 200000
            }
        }

        manifest_path = output_path / 'manifest.json'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)

        index_path = output_path / 'citation_index.json'
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(citation_index, f, indent=2)

        # Print summary
        print(f"\n{'='*80}")
        print(f"EXPORT COMPLETE")
        print(f"{'='*80}")
        print(f"📊 Summary:")
        print(f"  • Sources exported: {len(sources_with_summaries)}")
        if skipped_sources:
            print(f"  • Sources skipped (no summary): {len(skipped_sources)}")
        print(f"  • Batches created: {len(batches)}")
        print(f"  • Full content exported: {include_full_content}")
        print(f"\n📁 Output structure:")
        print(f"  {output_path}/")
        print(f"  ├── manifest.json")
        print(f"  ├── citation_index.json")
        print(f"  ├── summaries/")
        print(f"  │   └── {len(sources_with_summaries)} files")
        if include_full_content:
            print(f"  └── full_content/")
            print(f"      └── {len(sources_with_summaries)} files")

        return manifest
