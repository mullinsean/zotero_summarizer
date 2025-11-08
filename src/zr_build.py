#!/usr/bin/env python3
"""
ZoteroResearcher Build Module

Handles Phase 1: Building general summaries with metadata and tags.
"""

import time
from typing import Optional, Dict, List
from datetime import datetime

# Handle both relative and absolute imports
try:
    from .zr_common import ZoteroResearcherBase
    from . import zr_prompts
except ImportError:
    from zr_common import ZoteroResearcherBase
    import zr_prompts


class ZoteroResearcherBuilder(ZoteroResearcherBase):
    """Handles building general summaries for sources in a collection."""

    def load_project_overview_from_zotero(self, collection_key: str) -> str:
        """
        Load project overview from project-specific subcollection note.

        Args:
            collection_key: Parent collection key

        Returns:
            Project overview text

        Raises:
            FileNotFoundError: If subcollection or note not found
            ValueError: If note still contains template placeholder
        """
        return self.load_note_from_subcollection(
            collection_key,
            self._get_project_overview_note_title(),
            check_todo=True,
            remove_title_line=True,
            remove_footer=True,
            operation_name="building summaries"
        )

    def load_tags_from_zotero(self, collection_key: str) -> List[str]:
        """
        Load research tags from project-specific subcollection note.

        Args:
            collection_key: Parent collection key

        Returns:
            List of tags (one per line from note)

        Raises:
            FileNotFoundError: If subcollection or note not found
            ValueError: If note still contains template placeholder or is empty
        """
        note_title = self._get_research_tags_note_title()

        # Load note content using generic method
        content = self.load_note_from_subcollection(
            collection_key,
            note_title,
            check_todo=True,
            remove_title_line=True,
            remove_footer=True,
            operation_name="building summaries"
        )

        # Parse tags (one per line), filter empty lines
        lines = content.split('\n')
        tags = [line.strip() for line in lines if line.strip() and not line.startswith('Example')]

        if not tags:
            raise ValueError(f"{note_title} is empty. Please add tags.")

        return tags

    def has_general_summary(self, item_key: str) -> bool:
        """
        Check if an item has a cached general summary note for this project.

        Args:
            item_key: The key of the item

        Returns:
            True if a general summary exists for this project
        """
        return self.has_note_with_prefix(item_key, self._get_summary_note_prefix())

    def format_general_summary_note(
        self,
        metadata: Dict,
        tags: List[str],
        summary: str,
        document_type: str
    ) -> str:
        """
        Format a structured general summary note.

        Args:
            metadata: Metadata dict (title, authors, date, publication, url)
            tags: List of assigned tags
            summary: Summary text
            document_type: Document type (determined by LLM)

        Returns:
            Formatted note content as plain text
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Format tags as comma-separated list
        tags_str = ', '.join(tags) if tags else 'None'

        # Note: The title will be added by create_note() as an H1 heading
        note_content = f"""## Metadata
- **Title**: {metadata.get('title', 'Untitled')}
- **Authors**: {metadata.get('authors', 'Unknown')}
- **Date**: {metadata.get('date', 'Unknown')}
- **Publication**: {metadata.get('publication', 'N/A')}
- **Type**: {document_type}
- **URL**: {metadata.get('url', 'N/A')}

## Tags
{tags_str}

## Summary
{summary}

---
Created: {timestamp}
Project: {self.project_name}
"""
        return note_content

    def build_general_summaries(self, collection_key: str) -> None:
        """
        Phase 1: Build general summaries for all sources in a collection.

        Loads project configuration, project overview, and tags from Zotero subcollection.

        Args:
            collection_key: The Zotero collection key to process
        """
        start_time = time.time()

        # Load project configuration from Zotero
        try:
            config = self.load_project_config_from_zotero(collection_key)
            self.apply_project_config(config)
            if self.verbose:
                print(f"✅ Loaded project configuration from Zotero")
        except FileNotFoundError as e:
            if self.verbose:
                print(f"⚠️  Project config not found, using defaults: {e}")
        except Exception as e:
            print(f"⚠️  Error loading project config, using defaults: {e}")

        # Load project overview and tags from Zotero
        print(f"\n📋 Loading project data from {self._get_subcollection_name()} subcollection...\n")

        try:
            self.project_overview = self.load_project_overview_from_zotero(collection_key)
            print(f"✅ Loaded project overview from Zotero ({len(self.project_overview)} characters)")

            self.tags = self.load_tags_from_zotero(collection_key)
            print(f"✅ Loaded {len(self.tags)} tags from Zotero")
            print(f"   Tags: {', '.join(self.tags[:5])}{', ...' if len(self.tags) > 5 else ''}\n")

        except (FileNotFoundError, ValueError) as e:
            print(f"❌ Error loading project data from Zotero: {e}")
            print(f"\nRun --init-collection first to create project configuration and templates.\n")
            return

        print(f"\n{'='*80}")
        print(f"📚 Building General Summaries")
        print(f"{'='*80}")
        print(f"Collection: {collection_key}")
        print(f"Max Sources: {self.max_sources}")
        print(f"Force Rebuild: {self.force_rebuild}")
        print(f"Project: {self.project_overview.split(chr(10))[0] if self.project_overview else 'N/A'}")
        print(f"Tags: {len(self.tags)} available")
        print(f"{'='*80}\n")

        # Get collection items
        items = self.get_collection_items(collection_key)
        if not items:
            print("❌ No items found in collection")
            return

        # Limit sources if needed
        if len(items) > self.max_sources:
            print(f"⚠️  Collection has {len(items)} items, limiting to {self.max_sources}\n")
            items = items[:self.max_sources]

        # Step 1: Filter and prepare items for processing
        print(f"Step 1: Preparing items for batch processing...\n")

        items_to_process = []
        skipped = 0

        for idx, item in enumerate(items, 1):
            item_type = item['data'].get('itemType')
            if item_type in ['attachment', 'note']:
                continue

            item_key = item['key']
            item_title = item['data'].get('title', 'Untitled')

            # Check if general summary already exists
            has_existing_summary = self.has_general_summary(item_key)

            if has_existing_summary and not self.force_rebuild:
                print(f"[{idx}/{len(items)}] ✓ {item_title} - already has summary, skipping")
                skipped += 1
                continue

            if self.force_rebuild and has_existing_summary:
                print(f"[{idx}/{len(items)}] 🔄 {item_title} - force rebuild enabled")
            else:
                print(f"[{idx}/{len(items)}] 📚 {item_title}")

            # Extract metadata and content
            metadata = self.extract_metadata(item)
            content, content_type = self.get_source_content(item)

            if not content:
                print(f"  ⚠️  Could not extract content, skipping")
                continue

            content_len = len(content)
            if content_len > self.GENERAL_SUMMARY_CHAR_LIMIT:
                print(f"  ✅ Ready for processing ({content_len:,} chars, {content_type}) - will truncate to {self.GENERAL_SUMMARY_CHAR_LIMIT:,}")
            else:
                print(f"  ✅ Ready for processing ({content_len:,} chars, {content_type})")

            items_to_process.append({
                'item': item,
                'item_key': item_key,
                'item_title': item_title,
                'metadata': metadata,
                'content': content,
                'content_type': content_type,
                'index': idx,
                'has_existing_summary': has_existing_summary
            })

        if not items_to_process:
            print(f"\n⚠️  No items to process (all skipped or errors)")
            return

        # Step 2: Build batch requests for LLM
        print(f"\nStep 2: Building {len(items_to_process)} batch requests...")

        tags_list = '\n'.join([f"- {tag}" for tag in self.tags])
        batch_requests = []

        for item_data in items_to_process:
            content = item_data['content']
            truncated = len(content) > self.GENERAL_SUMMARY_CHAR_LIMIT

            prompt = zr_prompts.general_summary_prompt(
                project_overview=self.project_overview,
                tags_list=tags_list,
                title=item_data['metadata'].get('title', 'Untitled'),
                authors=item_data['metadata'].get('authors', 'Unknown'),
                date=item_data['metadata'].get('date', 'Unknown'),
                content=content[:self.GENERAL_SUMMARY_CHAR_LIMIT],
                truncated=truncated,
                char_limit=self.GENERAL_SUMMARY_CHAR_LIMIT
            )

            batch_requests.append({
                'id': item_data['item_key'],
                'prompt': prompt,
                'max_tokens': 2048,
                'model': self.haiku_model
            })

        # Step 3: Process batch with parallel LLM calls
        print(f"Step 3: Generating summaries in parallel ({self.max_workers} workers)...")
        print(f"Progress: ", end='', flush=True)

        def progress_callback(completed, total):
            print(f"{completed}/{total}...", end=' ', flush=True)

        # Parse response function for batch processing
        def parse_summary_response(response_text: str) -> Optional[Dict]:
            """Parse SUMMARY/TAGS/DOCUMENT_TYPE format."""
            try:
                import re
                result = {}

                summary_match = re.search(r'SUMMARY:\s*(.+?)(?=TAGS:)', response_text, re.DOTALL)
                result['summary'] = summary_match.group(1).strip() if summary_match else ''

                tags_match = re.search(r'TAGS:\s*(.+?)(?=DOCUMENT_TYPE:)', response_text, re.DOTALL)
                tags_str = tags_match.group(1).strip() if tags_match else ''
                result['tags'] = [tag.strip() for tag in tags_str.split(',') if tag.strip()]

                type_match = re.search(r'DOCUMENT_TYPE:\s*(.+?)(?:\n|$)', response_text, re.DOTALL)
                result['document_type'] = type_match.group(1).strip() if type_match else 'Unknown'

                return result if result['summary'] else None
            except Exception:
                return None

        batch_results = self.llm_client.call_batch_with_parsing(
            requests=batch_requests,
            parser=parse_summary_response,
            max_workers=self.max_workers,
            rate_limit_delay=self.rate_limit_delay,
            progress_callback=progress_callback
        )

        print("\n")

        # Step 4: Create notes for successful results
        print(f"Step 4: Creating notes in Zotero...")

        created = 0
        errors = 0

        for item_data in items_to_process:
            item_key = item_data['item_key']
            item_title = item_data['item_title']
            metadata = item_data['metadata']

            summary_data = batch_results.get(item_key)

            if summary_data and summary_data.get('summary'):
                # If force rebuild and item had existing summary, delete it first
                if self.force_rebuild and item_data.get('has_existing_summary'):
                    if self.verbose:
                        print(f"  🗑️  Deleting existing summary...")
                    self.delete_note_with_prefix(item_key, self._get_summary_note_prefix())

                # Format and create note
                note_content = self.format_general_summary_note(
                    metadata=metadata,
                    tags=summary_data['tags'],
                    summary=summary_data['summary'],
                    document_type=summary_data['document_type']
                )

                success = self.create_note(
                    parent_key=item_key,
                    content=note_content,
                    title=self._get_summary_note_prefix(),
                    convert_markdown=True
                )

                if success:
                    tags_str = ', '.join(summary_data['tags'][:3]) if summary_data['tags'] else 'None'
                    if len(summary_data['tags']) > 3:
                        tags_str += f", +{len(summary_data['tags'])-3} more"
                    print(f"  ✅ {item_title}")
                    print(f"     Type: {summary_data['document_type']} | Tags: {tags_str}")
                    created += 1
                else:
                    print(f"  ❌ {item_title} - failed to create note")
                    errors += 1
            else:
                print(f"  ❌ {item_title} - failed to generate summary")
                errors += 1

        processed = created + errors

        # Final summary
        elapsed_time = time.time() - start_time
        print(f"\n{'='*80}")
        print(f"✅ Build Complete")
        print(f"{'='*80}")
        print(f"Total items: {len(items)}")
        print(f"Processed: {processed}")
        print(f"Created: {created}")
        print(f"Skipped (existing): {skipped}")
        print(f"Errors: {errors}")
        print(f"Processing time: {elapsed_time:.1f} seconds")
        print(f"{'='*80}\n")
