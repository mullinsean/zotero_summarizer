#!/usr/bin/env python3
"""
ZoteroResearcher Query Module

Handles Phase 2: Querying sources with research briefs and generating reports.
"""

import os
import time
import markdown
from typing import Optional, Dict, List
from datetime import datetime

# Handle both relative and absolute imports
try:
    from .zr_common import ZoteroResearcherBase
    from . import zr_prompts
except ImportError:
    from zr_common import ZoteroResearcherBase
    import zr_prompts


class ZoteroResearcherQuerier(ZoteroResearcherBase):
    """Handles querying sources and generating research reports."""

    def load_research_brief_from_zotero(self, collection_key: str) -> str:
        """
        Load research brief from project-specific subcollection note.

        Args:
            collection_key: Parent collection key

        Returns:
            Research brief text

        Raises:
            FileNotFoundError: If subcollection or note not found
            ValueError: If note still contains template placeholder
        """
        return self.load_note_from_subcollection(
            collection_key,
            self._get_research_brief_note_title(),
            check_todo=True,
            remove_title_line=True,
            remove_footer=True,
            operation_name="running query"
        )

    def parse_general_summary_note(self, note_content: str) -> Optional[Dict]:
        """
        Parse a structured general summary note.

        Args:
            note_content: The note content (HTML or plain text)

        Returns:
            Dict with 'metadata', 'tags', and 'summary' keys, or None if parsing fails
        """
        try:
            # Strip HTML if present
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(note_content, 'html.parser')
            text = soup.get_text()

            # Initialize result
            result = {
                'metadata': {},
                'tags': [],
                'summary': ''
            }

            # After HTML->text conversion, markdown "## Heading" becomes just "Heading"
            # Try both formats for compatibility
            metadata_marker = 'Metadata' if 'Metadata' in text and '## Metadata' not in text else '## Metadata'
            tags_marker = 'Tags' if 'Tags' in text and '## Tags' not in text else '## Tags'
            summary_marker = 'Summary' if 'Summary' in text and '## Summary' not in text else '## Summary'

            # Parse metadata section
            if metadata_marker in text:
                parts = text.split(metadata_marker)
                if len(parts) > 1:
                    # Find next section marker
                    metadata_section = parts[1]
                    if tags_marker in metadata_section:
                        metadata_section = metadata_section.split(tags_marker)[0]

                    import re
                    # Look for both markdown bold (**) and plain text patterns
                    result['metadata']['title'] = re.search(r'(?:\*\*)?Title(?:\*\*)?:?\s*(.+?)(?:\n|$)', metadata_section)
                    result['metadata']['title'] = result['metadata']['title'].group(1).strip() if result['metadata']['title'] else ''

                    result['metadata']['authors'] = re.search(r'(?:\*\*)?Authors(?:\*\*)?:?\s*(.+?)(?:\n|$)', metadata_section)
                    result['metadata']['authors'] = result['metadata']['authors'].group(1).strip() if result['metadata']['authors'] else ''

                    result['metadata']['date'] = re.search(r'(?:\*\*)?Date(?:\*\*)?:?\s*(.+?)(?:\n|$)', metadata_section)
                    result['metadata']['date'] = result['metadata']['date'].group(1).strip() if result['metadata']['date'] else ''

                    result['metadata']['publication'] = re.search(r'(?:\*\*)?Publication(?:\*\*)?:?\s*(.+?)(?:\n|$)', metadata_section)
                    result['metadata']['publication'] = result['metadata']['publication'].group(1).strip() if result['metadata']['publication'] else ''

                    result['metadata']['type'] = re.search(r'(?:\*\*)?Type(?:\*\*)?:?\s*(.+?)(?:\n|$)', metadata_section)
                    result['metadata']['type'] = result['metadata']['type'].group(1).strip() if result['metadata']['type'] else ''

                    result['metadata']['url'] = re.search(r'(?:\*\*)?URL(?:\*\*)?:?\s*(.+?)(?:\n|$)', metadata_section)
                    result['metadata']['url'] = result['metadata']['url'].group(1).strip() if result['metadata']['url'] else ''

            # Parse tags section
            if tags_marker in text:
                parts = text.split(tags_marker)
                if len(parts) > 1:
                    tags_section = parts[1]
                    if summary_marker in tags_section:
                        tags_section = tags_section.split(summary_marker)[0]

                    tags_line = tags_section.strip()
                    if tags_line and tags_line.lower() != 'none' and tags_line != 'N/A':
                        result['tags'] = [tag.strip() for tag in tags_line.split(',') if tag.strip()]

            # Parse summary section
            if summary_marker in text:
                parts = text.split(summary_marker)
                if len(parts) > 1:
                    summary_section = parts[1]
                    if '---' in summary_section:
                        summary_section = summary_section.split('---')[0]
                    result['summary'] = summary_section.strip()

            return result

        except Exception as e:
            print(f"  ⚠️  Error parsing general summary note: {e}")
            import traceback
            traceback.print_exc()
            return None

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
            operation_name="running query"
        )

    def generate_synthesis(
        self,
        collection_key: str,
        report_title: str,
        report_content: str,
        report_note_key: Optional[str] = None,
        num_sources: int = 0,
        report_timestamp: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate a research synthesis from the research report.

        Loads project overview and research brief, then calls Claude Sonnet
        to create a meta-analysis synthesis of the research findings.

        Args:
            collection_key: The Zotero collection key
            report_title: Title of the research report
            report_content: Full HTML content of the research report
            report_note_key: Optional Zotero note key for internal link
            num_sources: Number of sources in the research report
            report_timestamp: Optional timestamp string for report creation

        Returns:
            Note key if synthesis created, None if generation fails or is disabled
        """
        if not self.synthesis_enabled:
            if self.verbose:
                print(f"  ℹ️  Research synthesis disabled (generate_synthesis=false in config)")
            return None

        print(f"\n{'='*80}")
        print(f"Generating Research Synthesis")
        print(f"{'='*80}\n")

        # Load project overview
        print(f"  Loading project overview...")
        try:
            project_overview = self.load_project_overview_from_zotero(collection_key)
            print(f"  ✅ Loaded project overview ({len(project_overview)} characters)")
        except (FileNotFoundError, ValueError) as e:
            print(f"  ⚠️  Could not load project overview: {e}")
            print(f"  ℹ️  Skipping synthesis generation")
            return None

        # Generate synthesis using Sonnet
        print(f"  Generating synthesis with Claude Sonnet...")
        print(f"  (This may take a minute for large reports)")

        try:
            # Build Zotero link if report_note_key is provided
            zotero_link = None
            if report_note_key:
                library_type = 'groups' if self.zot.library_type == 'group' else 'library'
                zotero_link = f"zotero://select/{library_type}/{self.zot.library_id}/items/{report_note_key}"

            prompt = zr_prompts.research_synthesis_prompt(
                project_overview=project_overview,
                research_brief=self.research_brief,
                research_report=report_content,
                report_title=report_title,
                num_sources=num_sources,
                report_timestamp=report_timestamp,
                zotero_link=zotero_link
            )

            # Use Sonnet (not Haiku) for high-quality synthesis
            synthesis_text = self.llm_client.call(
                prompt=prompt,
                max_tokens=16000,  # Allow for comprehensive synthesis
                model=self.sonnet_model,  # Always use Sonnet for synthesis
                temperature=0.3
            )

            if not synthesis_text:
                print(f"  ❌ Failed to generate synthesis (empty response)")
                return None

            print(f"  ✅ Synthesis generated ({len(synthesis_text)} characters)")

        except Exception as e:
            print(f"  ❌ Error generating synthesis: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return None

        # Save synthesis as note in project subcollection
        print(f"  Saving synthesis to Zotero...")

        subcollection_key = self.get_subcollection(collection_key, self._get_subcollection_name())
        if not subcollection_key:
            print(f"  ❌ {self._get_subcollection_name()} subcollection not found")
            return None

        try:
            synthesis_note_key = self.create_standalone_note(
                subcollection_key,
                synthesis_text,
                f"Research Synthesis: {report_title}",
                convert_markdown=True
            )

            if synthesis_note_key:
                print(f"  ✅ Synthesis note created in {self._get_subcollection_name()}")
                return synthesis_note_key
            else:
                print(f"  ❌ Failed to create synthesis note")
                return None

        except Exception as e:
            print(f"  ❌ Error saving synthesis note: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return None

    def generate_report_title(self, research_brief: str) -> str:
        """
        Generate an appropriate title for the research report based on the research brief.

        Args:
            research_brief: The research question/brief to generate a title for

        Returns:
            Generated title string, or fallback title if generation fails
        """
        try:
            # Truncate brief if too long (keep first 2000 chars)
            brief_for_prompt = research_brief[:2000] if len(research_brief) > 2000 else research_brief

            prompt = f"""Based on the following research brief, generate a concise, professional title for a research report (max 10 words).

Research Brief:
{brief_for_prompt}

Respond with ONLY the title, nothing else. No quotes, no punctuation at the end."""

            # Use Haiku for fast, cost-efficient title generation
            title = self.llm_client.call(
                prompt=prompt,
                max_tokens=50,
                model=self.haiku_model,
                temperature=0.5
            )

            if title:
                # Clean up the title - remove quotes if present
                title = title.strip().strip('"\'')
                # Limit length
                if len(title) > 100:
                    title = title[:97] + "..."
                return title
            else:
                # Fallback to simple extraction from brief
                brief_lines = research_brief.strip().split('\n')
                fallback = brief_lines[0] if brief_lines else "Research Report"
                if len(fallback) > 100:
                    fallback = fallback[:97] + "..."
                return fallback

        except Exception as e:
            if self.verbose:
                print(f"  ⚠️  Error generating title: {e}")
            # Fallback to simple extraction from brief
            brief_lines = research_brief.strip().split('\n')
            fallback = brief_lines[0] if brief_lines else "Research Report"
            if len(fallback) > 100:
                fallback = fallback[:97] + "..."
            return fallback

    def rank_sources(self, sources_with_scores: List[Dict]) -> List[Dict]:
        """
        Sort sources by relevance score (descending).

        Args:
            sources_with_scores: List of dicts with 'item', 'score', and 'content' keys

        Returns:
            Sorted list (highest relevance first)
        """
        return sorted(sources_with_scores, key=lambda x: x['score'], reverse=True)

    def run_query_summary(
        self,
        collection_key: str,
        subcollections: Optional[str] = None,
        include_main: bool = False
    ) -> Optional[str]:
        """
        Phase 2: Query sources based on research brief from Zotero notes.

        Loads project configuration and research brief from Zotero subcollection,
        runs query, and stores report as a Zotero note (or HTML file if >1MB).

        Args:
            collection_key: The Zotero collection key to analyze
            subcollections: Optional filter to specific subcollections (comma-separated names or "all")
            include_main: Include items from main collection when using subcollection filtering

        Returns:
            Note key if report stored as note, or file path if stored as HTML file
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

        print(f"\n{'='*80}")
        print(f"Research Query Summary")
        print(f"{'='*80}\n")

        # Load research brief from Zotero
        print(f"Loading research brief from {self._get_subcollection_name()} subcollection...")
        try:
            self.research_brief = self.load_research_brief_from_zotero(collection_key)
            print(f"✅ Loaded research brief ({len(self.research_brief)} characters)")
            brief_preview = self.research_brief[:200].replace('\n', ' ')
            print(f"   Preview: {brief_preview}...\n")
        except (FileNotFoundError, ValueError) as e:
            print(f"❌ Error loading research brief from Zotero: {e}")
            print(f"\nOptions:")
            print(f"   1. Run --init-collection --project \"{self.project_name}\" first")
            print(f"   2. Edit the {self._get_research_brief_note_title()} note in {self._get_subcollection_name()}\n")
            return None

        # Run the query using existing logic
        print(f"\n{'='*80}")
        print(f"Research Query Starting")
        print(f"{'='*80}")
        print(f"Collection: {collection_key}")
        print(f"Relevance Threshold: {self.relevance_threshold}/10")
        print(f"Max Sources: {self.max_sources}")
        print(f"Summary Model: {self.summary_model} ({'Sonnet - High Quality' if self.use_sonnet else 'Haiku - Cost Efficient'})")
        print(f"{'='*80}\n")

        # Get items to process (with optional subcollection filtering)
        items = self.get_items_to_process(collection_key, subcollections, include_main)
        if not items:
            print("❌ No items found in collection")
            return None

        # Limit sources if needed
        if len(items) > self.max_sources:
            print(f"⚠️  Collection has {len(items)} items, limiting to {self.max_sources}")
            items = items[:self.max_sources]

        # Phase 1: Parse summaries and evaluate relevance
        print(f"\n{'='*80}")
        print(f"Phase 1: Loading Summaries & Evaluating Relevance")
        print(f"{'='*80}\n")

        # Step 1.1: Load and parse all summaries
        print(f"Step 1.1: Loading general summaries...")

        items_with_summaries = []
        missing_summaries = 0

        for idx, item in enumerate(items, 1):
            item_type = item['data'].get('itemType')
            if item_type in ['attachment', 'note']:
                continue

            item_title = item['data'].get('title', 'Untitled')
            item_key = item['key']

            # Check for general summary
            if not self.has_note_with_prefix(
                item_key, self._get_summary_note_prefix(), collection_key
            ):
                print(f"[{idx}/{len(items)}] ⚠️  {item_title} - no summary (run --build-summaries first)")
                missing_summaries += 1
                continue

            # Parse general summary note
            summary_note = self.get_note_with_prefix(
                item_key, self._get_summary_note_prefix(), collection_key
            )
            if not summary_note:
                print(f"[{idx}/{len(items)}] ⚠️  {item_title} - could not load summary")
                missing_summaries += 1
                continue

            parsed_summary = self.parse_general_summary_note(summary_note)
            if not parsed_summary:
                print(f"[{idx}/{len(items)}] ⚠️  {item_title} - could not parse summary")
                missing_summaries += 1
                continue

            metadata = parsed_summary['metadata']
            tags = parsed_summary['tags']
            summary = parsed_summary['summary']

            tags_display = ', '.join(tags[:3]) if tags else 'None'
            if len(tags) > 3:
                tags_display += f", +{len(tags)-3} more"

            # Get full content for detailed summary generation later
            content, content_type = self.get_source_content(item)

            print(f"[{idx}/{len(items)}] ✅ {item_title} - {metadata.get('type', 'Unknown')} | Tags: {tags_display}")

            items_with_summaries.append({
                'item': item,
                'item_key': item_key,
                'item_title': item_title,
                'metadata': metadata,
                'tags': tags,
                'summary': summary,
                'content': content if content else summary,
                'content_type': content_type if content else metadata.get('type', 'Unknown')
            })

        # Step 1.2: Build batch requests for relevance evaluation
        print(f"\nStep 1.2: Building {len(items_with_summaries)} relevance evaluation requests...")

        batch_requests = []
        for item_data in items_with_summaries:
            tags_str = ', '.join(item_data['tags']) if item_data['tags'] else 'None'

            prompt = zr_prompts.relevance_evaluation_prompt(
                research_brief=self.research_brief,
                title=item_data['metadata'].get('title', 'Untitled'),
                authors=item_data['metadata'].get('authors', 'Unknown'),
                date=item_data['metadata'].get('date', 'Unknown'),
                doc_type=item_data['metadata'].get('type', 'Unknown'),
                tags=tags_str,
                summary=item_data['summary'][:10000]
            )

            batch_requests.append({
                'id': item_data['item_key'],
                'prompt': prompt,
                'max_tokens': 10,
                'model': self.haiku_model
            })

        # Step 1.3: Evaluate relevance in parallel
        print(f"Step 1.3: Evaluating relevance in parallel ({self.max_workers} workers)...")
        print(f"Progress: ", end='', flush=True)

        def progress_callback(completed, total):
            print(f"{completed}/{total}...", end=' ', flush=True)

        # Parse relevance score from response
        def parse_relevance_score(response_text: str) -> Optional[int]:
            """Extract relevance score 0-10 from response."""
            try:
                import re
                match = re.search(r'^(\d+)', response_text.strip())
                if not match:
                    match = re.search(r'\b(\d+)\b', response_text)
                if match:
                    score = int(match.group(1))
                    return max(0, min(10, score))
                return None
            except Exception:
                return None

        relevance_results = self.llm_client.call_batch_with_parsing(
            requests=batch_requests,
            parser=parse_relevance_score,
            max_workers=self.max_workers,
            rate_limit_delay=self.rate_limit_delay,
            progress_callback=progress_callback
        )

        print("\n")

        # Step 1.4: Combine scores with source data
        print(f"Step 1.4: Processing results...")

        sources_with_scores = []
        evaluated = 0

        for item_data in items_with_summaries:
            item_key = item_data['item_key']
            score = relevance_results.get(item_key)

            if score is not None:
                print(f"  ✅ {item_data['item_title']} - Score: {score}/10")
                sources_with_scores.append({
                    'item': item_data['item'],
                    'score': score,
                    'content': item_data['content'],
                    'content_type': item_data['content_type'],
                    'metadata': item_data['metadata'],
                    'tags': item_data['tags']
                })
                evaluated += 1
            else:
                print(f"  ⚠️  {item_data['item_title']} - Could not evaluate relevance")

        # Filter and rank sources
        print(f"\n{'='*80}")
        print(f"Phase 2: Ranking & Filtering")
        print(f"{'='*80}\n")

        relevant_sources = [s for s in sources_with_scores if s['score'] >= self.relevance_threshold]
        relevant_sources = self.rank_sources(relevant_sources)

        print(f"  Sources meeting threshold ({self.relevance_threshold}/10): {len(relevant_sources)}")

        if not relevant_sources:
            print(f"\n⚠️  No sources meet the relevance threshold of {self.relevance_threshold}/10")
            if missing_summaries > 0:
                print(f"  Note: {missing_summaries} sources were missing summaries. Run --build-summaries first.")
            print(f"  Try lowering the threshold or refining your research brief")
            return None

        # Phase 3: Generate detailed summaries
        print(f"\n{'='*80}")
        print(f"Phase 3: Detailed Research Summaries")
        print(f"{'='*80}\n")

        # Step 3.1: Build batch requests for targeted summaries
        print(f"Step 3.1: Building {len(relevant_sources)} targeted summary requests...\n")

        batch_requests = []
        for idx, source_data in enumerate(relevant_sources, 1):
            item = source_data['item']
            item_title = item['data'].get('title', 'Untitled')
            item_key = item['key']
            content = source_data['content']
            content_type = source_data['content_type']
            content_len = len(content)
            truncated = content_len > self.TARGETED_SUMMARY_CHAR_LIMIT

            if truncated:
                print(f"  [{idx}/{len(relevant_sources)}] {item_title} ({content_len:,} chars) - will truncate to {self.TARGETED_SUMMARY_CHAR_LIMIT:,}")
            else:
                print(f"  [{idx}/{len(relevant_sources)}] {item_title} ({content_len:,} chars)")

            prompt = zr_prompts.targeted_summary_prompt(
                research_brief=self.research_brief,
                title=item_title,
                content_type=content_type,
                content=content[:self.TARGETED_SUMMARY_CHAR_LIMIT],
                truncated=truncated,
                char_limit=self.TARGETED_SUMMARY_CHAR_LIMIT
            )

            batch_requests.append({
                'id': item_key,
                'prompt': prompt,
                'max_tokens': 4096,
                'model': self.summary_model
            })

        # Step 3.2: Generate targeted summaries in parallel
        model_name = "Sonnet" if self.use_sonnet else "Haiku"
        print(f"\nStep 3.2: Generating summaries in parallel ({model_name}, {self.max_workers} workers)...")
        print(f"Progress: ", end='', flush=True)

        def progress_callback(completed, total):
            print(f"{completed}/{total}...", end=' ', flush=True)

        summary_results = self.llm_client.call_batch(
            requests=batch_requests,
            max_workers=self.max_workers,
            rate_limit_delay=self.rate_limit_delay,
            progress_callback=progress_callback
        )

        print("\n")

        # Step 3.3: Attach results to sources
        print(f"Step 3.3: Processing results...")

        for source_data in relevant_sources:
            item_key = source_data['item']['key']
            item_title = source_data['item']['data'].get('title', 'Untitled')
            summary_text = summary_results.get(item_key)

            if summary_text:
                source_data['summary_data'] = {
                    'summary': summary_text,
                    'full_text': summary_text
                }
                print(f"  ✅ {item_title}")
            else:
                source_data['summary_data'] = {'full_text': 'Summary generation failed'}
                print(f"  ⚠️  {item_title} - Failed to generate summary")

        # Phase 4: Generate HTML report
        print(f"\n{'='*80}")
        print(f"Phase 4: Generating Research Report")
        print(f"{'='*80}\n")

        elapsed_time = time.time() - start_time
        stats = {
            'total': len(items),
            'evaluated': evaluated,
            'relevant': len(relevant_sources),
            'missing_summaries': missing_summaries,
            'time': f"{elapsed_time:.1f} seconds"
        }

        # Generate timestamp for report creation
        report_timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")

        # Generate title from research brief using LLM
        print(f"  Generating report title...")
        report_title = self.generate_report_title(self.research_brief)

        # Generate HTML content (but don't save to file yet)
        html_content = self._compile_research_html_string(collection_key, relevant_sources, stats, report_title)

        # Check HTML size (1MB = 1,048,576 bytes)
        html_size_bytes = len(html_content.encode('utf-8'))
        html_size_mb = html_size_bytes / 1_048_576

        print(f"  Report size: {html_size_mb:.2f} MB")

        # Get project-specific subcollection
        subcollection_key = self.get_subcollection(collection_key, self._get_subcollection_name())
        if not subcollection_key:
            print(f"❌ {self._get_subcollection_name()} subcollection not found")
            print(f"   Run --init-collection --project \"{self.project_name}\" first")
            return None

        # If report >1MB, save as file and create stub note
        if html_size_bytes > 1_048_576:
            print(f"  ⚠️  Report exceeds 1MB limit for Zotero notes")
            print(f"  Saving as HTML file instead...")

            # Save HTML file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"research_report_{collection_key}_{timestamp}.html"

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)

            print(f"  ✅ HTML file saved: {output_file}")

            # Create stub note
            stub_content = f"""This research report exceeded the 1MB limit for Zotero notes.

The full report has been saved to:
{os.path.abspath(output_file)}

Report Statistics:
- Total sources: {stats['total']}
- Evaluated: {stats['evaluated']}
- Relevant sources: {stats['relevant']}
- Processing time: {stats['time']}

Generated: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}
"""

            note_key = self.create_standalone_note(
                subcollection_key,
                stub_content,
                f"Research Report: {report_title} (See File)",
                convert_markdown=True
            )

            if note_key:
                print(f"  ✅ Stub note created in {self._get_subcollection_name()}")
            else:
                print(f"  ⚠️  Failed to create stub note")

            # Generate research synthesis
            synthesis_key = self.generate_synthesis(
                collection_key,
                report_title,
                html_content,
                report_note_key=None,  # No note key for file-based reports
                num_sources=stats['relevant'],
                report_timestamp=report_timestamp
            )

            # Final summary
            print(f"\n{'='*80}")
            print(f"✅ Query Complete")
            print(f"{'='*80}")
            print(f"Total sources: {stats['total']}")
            print(f"Evaluated: {stats['evaluated']}")
            print(f"Missing summaries: {stats['missing_summaries']}")
            print(f"Relevant: {stats['relevant']}")
            print(f"Processing time: {stats['time']}")
            print(f"Report: {output_file} (with stub note in Zotero)")
            if synthesis_key:
                print(f"Synthesis: Created in {self._get_subcollection_name()}")
            print(f"{'='*80}\n")

            return output_file

        # If report <1MB, create full note in Zotero
        else:
            print(f"  Creating note in {self._get_subcollection_name()}...")

            # Create note with HTML content directly (no markdown conversion)
            note_key = self.create_standalone_note(
                subcollection_key,
                html_content,
                f"Research Report: {report_title}",
                convert_markdown=False  # Already HTML
            )

            if note_key:
                print(f"  ✅ Report note created in {self._get_subcollection_name()}")
            else:
                print(f"  ❌ Failed to create report note")
                return None

            # Generate research synthesis
            synthesis_key = self.generate_synthesis(
                collection_key,
                report_title,
                html_content,
                report_note_key=note_key,  # Include Zotero link for note-based reports
                num_sources=stats['relevant'],
                report_timestamp=report_timestamp
            )

            # Final summary
            print(f"\n{'='*80}")
            print(f"✅ Query Complete")
            print(f"{'='*80}")
            print(f"Total sources: {stats['total']}")
            print(f"Evaluated: {stats['evaluated']}")
            print(f"Missing summaries: {stats['missing_summaries']}")
            print(f"Relevant: {stats['relevant']}")
            print(f"Processing time: {stats['time']}")
            print(f"Report: Stored as note in {self._get_subcollection_name()}")
            if synthesis_key:
                print(f"Synthesis: Created in {self._get_subcollection_name()}")
            print(f"{'='*80}\n")

            return note_key

    def compile_research_html(
        self,
        collection_key: str,
        relevant_sources: List[Dict],
        stats: Dict,
        report_title: str = "Research Report"
    ) -> str:
        """
        Compile all research results into an HTML document with linked TOC.
        Saves to file (legacy file-based workflow).

        Args:
            collection_key: The collection key
            relevant_sources: List of dicts with source data and summaries
            stats: Statistics dict with processing info
            report_title: Title for the research report (optional, defaults to "Research Report")

        Returns:
            Filename of the generated HTML file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"research_report_{collection_key}_{timestamp}.html"

        html_content = self._compile_research_html_string(collection_key, relevant_sources, stats, report_title)

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"\n  ✅ Research report saved to: {filename}")
            return filename
        except Exception as e:
            print(f"\n  ❌ Error saving research report: {e}")
            return ""

    def _compile_research_html_string(self, collection_key: str, relevant_sources: List[Dict], stats: Dict, report_title: str = "Research Report") -> str:
        """
        Internal method: Generate HTML report as string (doesn't save to file).

        Args:
            collection_key: Collection key
            relevant_sources: List of relevant sources with summaries
            stats: Statistics dict
            report_title: Title for the research report (optional, defaults to "Research Report")

        Returns:
            HTML content as string
        """
        html_parts = []

        # HTML header with styles
        html_parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Research Report</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 30px;
            background-color: #f5f7fa;
            color: #2c3e50;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            border-radius: 10px;
            margin-bottom: 40px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .header h1 {
            margin: 0 0 15px 0;
            font-size: 2.5em;
        }
        .meta {
            font-size: 0.95em;
            opacity: 0.95;
            line-height: 1.8;
        }
        .research-brief {
            background: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border-left: 5px solid #3498db;
        }
        .research-brief h2 {
            margin-top: 0;
            color: #2c3e50;
        }
        .brief-text {
            white-space: pre-wrap;
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            line-height: 1.8;
        }
        .toc {
            background: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .toc h2 {
            margin-top: 0;
            color: #2c3e50;
        }
        .toc ol {
            line-height: 2;
        }
        .toc a {
            color: #3498db;
            text-decoration: none;
        }
        .toc a:hover {
            text-decoration: underline;
        }
        .relevance-score {
            float: right;
            background: #ecf0f1;
            padding: 3px 12px;
            border-radius: 15px;
            font-size: 0.85em;
            font-weight: 600;
            color: #7f8c8d;
        }
        .relevance-score.high {
            background: #2ecc71;
            color: white;
        }
        .relevance-score.medium {
            background: #f39c12;
            color: white;
        }
        .source {
            background: white;
            padding: 35px;
            margin-bottom: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .source h3 {
            margin-top: 0;
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 15px;
        }
        .metadata {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            line-height: 1.9;
        }
        .metadata strong {
            color: #34495e;
        }
        .content-section {
            margin-top: 25px;
            line-height: 1.8;
        }
        .content-section h4 {
            color: #2c3e50;
            margin-top: 25px;
            border-left: 4px solid #3498db;
            padding-left: 15px;
        }
        .tag-badge {
            display: inline-block;
            background: #e8f4fd;
            color: #2980b9;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            margin-right: 6px;
            margin-bottom: 6px;
            font-weight: 500;
        }
        .back-to-top {
            display: inline-block;
            margin-top: 25px;
            color: #3498db;
            text-decoration: none;
            font-size: 14px;
            font-weight: 500;
        }
        .back-to-top:hover {
            text-decoration: underline;
        }
        .stats {
            background: linear-gradient(135deg, #27ae60 0%, #2ecc71 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-top: 40px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .stats h2 {
            margin-top: 0;
        }
        .stats ul {
            list-style: none;
            padding: 0;
            line-height: 2;
        }
        .stats li:before {
            content: "✓ ";
            margin-right: 10px;
        }
    </style>
</head>
<body>
""")

        # Header
        html_parts.append(f"""
    <div class="header">
        <h1>{report_title}</h1>
        <div class="meta">
            Generated: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}<br>
            Collection: {collection_key}<br>
            Relevant Sources Found: {len(relevant_sources)}<br>
            Relevance Threshold: {self.relevance_threshold}/10
        </div>
    </div>
""")

        # Research Brief Section
        html_parts.append(f"""
    <div class="research-brief">
        <h2>Research Brief</h2>
        <div class="brief-text">{self.research_brief}</div>
    </div>
""")

        # Table of Contents
        html_parts.append("""
    <div class="toc">
        <h2>Table of Contents</h2>
        <ol>
""")

        for idx, source_data in enumerate(relevant_sources, 1):
            item_title = source_data['item']['data'].get('title', 'Untitled')
            score = source_data['score']
            anchor = f"source-{idx}"

            score_class = "high" if score >= 8 else ("medium" if score >= 6 else "")

            html_parts.append(
                f'            <li><a href="#{anchor}">{item_title}</a>&nbsp;'
                f'<span class="relevance-score {score_class}">{score}/10</span></li>\n'
            )

        html_parts.append("""        </ol>
    </div>
""")

        # Individual source summaries
        for idx, source_data in enumerate(relevant_sources, 1):
            item = source_data['item']
            item_title = item['data'].get('title', 'Untitled')
            item_key = item['key']
            score = source_data['score']
            content_type = source_data.get('content_type', 'Unknown')
            summary_data = source_data.get('summary_data', {})
            metadata = source_data.get('metadata', {})
            tags = source_data.get('tags', [])

            anchor = f"source-{idx}"

            # Build Zotero link
            library_type = 'groups' if self.zot.library_type == 'group' else 'library'
            zotero_link = f"zotero://select/{library_type}/{self.zot.library_id}/items/{item_key}"

            # Convert markdown to HTML
            summary_markdown = summary_data.get('full_text', 'Summary not available')
            summary_html = markdown.markdown(summary_markdown, extensions=['extra', 'nl2br'])

            # Format tags as badges
            tags_html = ''
            if tags:
                tags_badges = [f'<span class="tag-badge">{tag}</span>' for tag in tags]
                tags_html = f"<br><strong>Tags:</strong> {' '.join(tags_badges)}"

            # Format metadata
            authors_display = metadata.get('authors', 'Unknown')
            date_display = metadata.get('date', 'Unknown')
            publication_display = metadata.get('publication', 'N/A')
            doc_type_display = metadata.get('type', content_type)
            url_display = metadata.get('url', '')
            url_html = f'<br><strong>URL:</strong> <a href="{url_display}" target="_blank">{url_display}</a>' if url_display else ''

            html_parts.append(f"""
    <div class="source" id="{anchor}">
        <h3>{idx}. {item_title}</h3>
        <div class="metadata">
            <strong>Authors:</strong> {authors_display}<br>
            <strong>Date:</strong> {date_display}<br>
            <strong>Publication:</strong> {publication_display}<br>
            <strong>Type:</strong> {doc_type_display}<br>
            <strong>Relevance Score:</strong> {score}/10{tags_html}{url_html}<br>
            <strong>Zotero Link:</strong> <a href="{zotero_link}" target="_blank">Open in Zotero</a>
        </div>
        <div class="content-section">
{summary_html}
        </div>
        <a href="#" class="back-to-top">↑ Back to top</a>
    </div>
""")

        # Statistics Section
        html_parts.append(f"""
    <div class="stats">
        <h2>Research Statistics</h2>
        <ul>
            <li>Total sources in collection: {stats.get('total', 0)}</li>
            <li>Sources evaluated: {stats.get('evaluated', 0)}</li>
            <li>Missing summaries: {stats.get('missing_summaries', 0)}</li>
            <li>Relevant sources (≥ {self.relevance_threshold}/10): {stats.get('relevant', 0)}</li>
            <li>Processing time: {stats.get('time', 'N/A')}</li>
        </ul>
    </div>
""")

        # HTML footer
        html_parts.append("""
</body>
</html>
""")

        return ''.join(html_parts)
