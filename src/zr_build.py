#!/usr/bin/env python3
"""
ZoteroResearcher Build Module

Handles Phase 1: Building general summaries with metadata and tags.
"""

import re
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

    def has_general_summary(self, item_key: str, collection_key: str = None) -> bool:
        """
        Check if an item has a cached general summary note for this project.

        Args:
            item_key: The key of the item
            collection_key: Optional collection key for cache lookup

        Returns:
            True if a general summary exists for this project
        """
        return self.has_note_with_prefix(
            item_key, self._get_summary_note_prefix(), collection_key
        )

    def format_general_summary_note(
        self,
        metadata: Dict,
        tags: List[str],
        summary: str,
        document_type: str,
        research_type: str = "unknown",
        project_role: str = "supporting",
        temporal_status: str = "current",
        temporal_context: str = "",
        peer_reviewed: str = "unclear",
        evidence_strength: str = "moderate",
        limitations: str = "Not stated",
        biases: str = "None identified",
        relevant_sections: str = "",
        skip_sections: str = "",
        key_claims: List[Dict] = None,
        model_used: str = "unknown"
    ) -> str:
        """
        Format an enhanced structured general summary note.

        Args:
            metadata: Metadata dict (title, authors, date, publication, url)
            tags: List of assigned tags
            summary: Summary text
            document_type: Document type (determined by LLM)
            research_type: Type of research (empirical, theoretical, review, etc.)
            project_role: Role in project (background, core_evidence, etc.)
            temporal_status: Temporal fit (current, dated, foundational)
            temporal_context: Explanation of temporal relevance
            peer_reviewed: Whether peer reviewed (yes, no, unclear)
            evidence_strength: Strength of evidence (strong, moderate, weak)
            limitations: Key limitations noted
            biases: Potential biases identified
            relevant_sections: Sections worth deep reading
            skip_sections: Sections that can be skipped
            key_claims: List of dicts with 'claim' and 'questions' keys
            model_used: Model used for generation

        Returns:
            Formatted note content as plain text
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Format tags as comma-separated list
        tags_str = ', '.join(tags) if tags else 'None'

        # Format temporal status with context
        temporal_display = temporal_status
        if temporal_context:
            temporal_display = f"{temporal_status} ({temporal_context})"

        # Format key claims
        if key_claims:
            claims_lines = []
            for i, claim_data in enumerate(key_claims, 1):
                claim_text = claim_data.get('claim', '')
                questions = claim_data.get('questions', [])
                if questions:
                    q_links = ', '.join([f"Q{q}" for q in questions])
                    claims_lines.append(f"{i}. [{q_links}] {claim_text}")
                else:
                    claims_lines.append(f"{i}. {claim_text}")
            key_claims_str = '\n'.join(claims_lines)
        else:
            key_claims_str = "None extracted"

        # Note: The title will be added by create_note() as an H1 heading
        note_content = f"""## Metadata
- **Title**: {metadata.get('title', 'Untitled')}
- **Authors**: {metadata.get('authors', 'Unknown')}
- **Date**: {metadata.get('date', 'Unknown')}
- **Publication**: {metadata.get('publication', 'N/A')}
- **Type**: {document_type}
- **URL**: {metadata.get('url', 'N/A')}

## Classification
- **Research Type**: {research_type}
- **Project Role**: {project_role}
- **Temporal Status**: {temporal_display}

## Quality Assessment
- **Peer Reviewed**: {peer_reviewed}
- **Evidence Strength**: {evidence_strength}
- **Limitations**: {limitations}
- **Potential Biases**: {biases}

## Tags
{tags_str}

## Summary
{summary}

## Structural Guidance
**Most Relevant Sections**: {relevant_sections if relevant_sections else 'Not specified'}
**Sections to Skip**: {skip_sections if skip_sections else 'None'}

## Key Claims
{key_claims_str}

---
Created: {timestamp}
Project: {self.project_name}
Model: {model_used}
"""
        return note_content

    def _extract_key_questions(self, project_overview: str) -> str:
        """
        Extract numbered key questions from project overview for prompt inclusion.

        Looks for numbered list patterns (e.g., "1. How does X affect Y?")
        in the project overview and extracts them.

        Args:
            project_overview: The project overview text

        Returns:
            Formatted string of numbered questions, or empty string if none found
        """
        # Look for numbered list patterns (supports various formats)
        # Matches: "1. Question" or "1) Question" or "1: Question"
        questions = re.findall(
            r'^\s*(\d+)[.):]\s*(.+?)(?:\n|$)',
            project_overview,
            re.MULTILINE
        )

        if questions:
            return "\n".join([f"{num}. {q.strip()}" for num, q in questions])
        return ""

    def build_general_summaries(
        self,
        collection_key: str,
        subcollections: Optional[str] = None,
        include_main: bool = False
    ) -> None:
        """
        Phase 1: Build general summaries for all sources in a collection.

        Loads project configuration, project overview, and tags from Zotero subcollection.

        Args:
            collection_key: The Zotero collection key to process
            subcollections: Optional filter to specific subcollections (comma-separated names or "all")
            include_main: Include items from main collection when using subcollection filtering
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

        # Get items to process (with optional subcollection filtering)
        items = self.get_items_to_process(collection_key, subcollections, include_main)
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
            has_existing_summary = self.has_general_summary(item_key, collection_key)

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
        print(f"Using model: {self.summary_model}")

        tags_list = '\n'.join([f"- {tag}" for tag in self.tags])
        key_questions = self._extract_key_questions(self.project_overview)
        if key_questions:
            print(f"Extracted {len(key_questions.split(chr(10)))} key questions from project overview")

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
                char_limit=self.GENERAL_SUMMARY_CHAR_LIMIT,
                key_questions=key_questions
            )

            batch_requests.append({
                'id': item_data['item_key'],
                'prompt': prompt,
                'max_tokens': 4096,  # Increased for enhanced output
                'model': self.summary_model
            })

        # Step 3: Process batch with parallel LLM calls
        print(f"Step 3: Generating summaries in parallel ({self.max_workers} workers)...")
        print(f"Progress: ", end='', flush=True)

        def progress_callback(completed, total):
            print(f"{completed}/{total}...", end=' ', flush=True)

        # Enhanced parse response function for batch processing
        def parse_enhanced_summary_response(response_text: str) -> Optional[Dict]:
            """Parse enhanced SUMMARY/TAGS/DOCUMENT_TYPE/... format with all new fields."""
            try:
                # Valid values for controlled vocabularies
                VALID_RESEARCH_TYPES = ['empirical', 'theoretical', 'review', 'primary_source', 'commentary']
                VALID_PROJECT_ROLES = ['background', 'core_evidence', 'methodology', 'counterargument', 'supporting']
                VALID_PEER_REVIEWED = ['yes', 'no', 'unclear']
                VALID_EVIDENCE_STRENGTH = ['strong', 'moderate', 'weak']
                VALID_TEMPORAL_STATUS = ['current', 'dated', 'foundational']

                result = {
                    # Existing fields
                    'summary': '',
                    'tags': [],
                    'document_type': 'Unknown',

                    # New classification fields
                    'research_type': 'unknown',
                    'project_role': 'supporting',

                    # Structural guidance
                    'relevant_sections': '',
                    'skip_sections': '',

                    # Quality indicators
                    'peer_reviewed': 'unclear',
                    'evidence_strength': 'moderate',
                    'limitations': 'Not stated',
                    'biases': 'None identified',

                    # Temporal fit
                    'temporal_status': 'current',
                    'temporal_context': '',

                    # Key claims
                    'key_claims': []
                }

                # Parse SUMMARY (everything up to TAGS:)
                summary_match = re.search(r'SUMMARY:\s*(.+?)(?=\nTAGS:)', response_text, re.DOTALL)
                result['summary'] = summary_match.group(1).strip() if summary_match else ''

                # Parse TAGS (up to DOCUMENT_TYPE:)
                tags_match = re.search(r'TAGS:\s*(.+?)(?=\nDOCUMENT_TYPE:)', response_text, re.DOTALL)
                if tags_match:
                    tags_str = tags_match.group(1).strip()
                    result['tags'] = [tag.strip() for tag in tags_str.split(',') if tag.strip()]

                # Parse DOCUMENT_TYPE (up to RESEARCH_TYPE:)
                type_match = re.search(r'DOCUMENT_TYPE:\s*(.+?)(?=\nRESEARCH_TYPE:)', response_text, re.DOTALL)
                result['document_type'] = type_match.group(1).strip() if type_match else 'Unknown'

                # Parse RESEARCH_TYPE (up to PROJECT_ROLE:)
                research_match = re.search(r'RESEARCH_TYPE:\s*(\w+)', response_text)
                if research_match:
                    val = research_match.group(1).strip().lower()
                    result['research_type'] = val if val in VALID_RESEARCH_TYPES else 'unknown'

                # Parse PROJECT_ROLE (up to STRUCTURAL_GUIDANCE:)
                role_match = re.search(r'PROJECT_ROLE:\s*(\w+)', response_text)
                if role_match:
                    val = role_match.group(1).strip().lower()
                    result['project_role'] = val if val in VALID_PROJECT_ROLES else 'supporting'

                # Parse STRUCTURAL_GUIDANCE
                struct_match = re.search(
                    r'STRUCTURAL_GUIDANCE:\s*\n?Most Relevant Sections:\s*(.+?)\n\s*Sections to Skip:\s*(.+?)(?=\n\n|\nQUALITY_INDICATORS:)',
                    response_text, re.DOTALL
                )
                if struct_match:
                    result['relevant_sections'] = struct_match.group(1).strip()
                    result['skip_sections'] = struct_match.group(2).strip()

                # Parse QUALITY_INDICATORS
                quality_match = re.search(
                    r'QUALITY_INDICATORS:\s*\n?Peer Reviewed:\s*(\w+)\s*\n?\s*Evidence Strength:\s*(\w+)\s*\n?\s*Limitations:\s*(.+?)\n\s*Potential Biases:\s*(.+?)(?=\n\n|\nTEMPORAL_FIT:)',
                    response_text, re.DOTALL
                )
                if quality_match:
                    peer_val = quality_match.group(1).strip().lower()
                    result['peer_reviewed'] = peer_val if peer_val in VALID_PEER_REVIEWED else 'unclear'

                    strength_val = quality_match.group(2).strip().lower()
                    result['evidence_strength'] = strength_val if strength_val in VALID_EVIDENCE_STRENGTH else 'moderate'

                    result['limitations'] = quality_match.group(3).strip()
                    result['biases'] = quality_match.group(4).strip()

                # Parse TEMPORAL_FIT
                temporal_match = re.search(
                    r'TEMPORAL_FIT:\s*\n?Status:\s*(\w+).*?\n\s*Context:\s*(.+?)(?=\n\n|\nKEY_CLAIMS:)',
                    response_text, re.DOTALL
                )
                if temporal_match:
                    status_val = temporal_match.group(1).strip().lower()
                    result['temporal_status'] = status_val if status_val in VALID_TEMPORAL_STATUS else 'current'
                    result['temporal_context'] = temporal_match.group(2).strip()

                # Parse KEY_CLAIMS
                claims_match = re.search(r'KEY_CLAIMS:\s*\n(.+?)(?:\n---|\Z)', response_text, re.DOTALL)
                if claims_match:
                    claims_text = claims_match.group(1).strip()
                    # Parse numbered claims with optional [Qn] notation
                    claim_pattern = re.compile(r'^\s*\d+\.\s*(?:\[([^\]]+)\])?\s*(.+?)(?=\n\s*\d+\.|\Z)', re.MULTILINE | re.DOTALL)
                    for match in claim_pattern.finditer(claims_text):
                        q_links_str = match.group(1)
                        claim_text = match.group(2).strip()
                        questions = []
                        if q_links_str:
                            # Parse "Q1, Q2" or "Q1" format
                            q_numbers = re.findall(r'Q(\d+)', q_links_str)
                            questions = [int(q) for q in q_numbers]
                        if claim_text:
                            result['key_claims'].append({
                                'claim': claim_text,
                                'questions': questions
                            })

                return result if result['summary'] else None
            except Exception as e:
                if self.verbose:
                    print(f"  ⚠️  Parse error: {e}")
                return None

        batch_results = self.llm_client.call_batch_with_parsing(
            requests=batch_requests,
            parser=parse_enhanced_summary_response,
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
                    self.delete_note_with_prefix(
                        item_key, self._get_summary_note_prefix(), collection_key
                    )

                # Format and create note with all enhanced fields
                note_content = self.format_general_summary_note(
                    metadata=metadata,
                    tags=summary_data['tags'],
                    summary=summary_data['summary'],
                    document_type=summary_data['document_type'],
                    research_type=summary_data.get('research_type', 'unknown'),
                    project_role=summary_data.get('project_role', 'supporting'),
                    temporal_status=summary_data.get('temporal_status', 'current'),
                    temporal_context=summary_data.get('temporal_context', ''),
                    peer_reviewed=summary_data.get('peer_reviewed', 'unclear'),
                    evidence_strength=summary_data.get('evidence_strength', 'moderate'),
                    limitations=summary_data.get('limitations', 'Not stated'),
                    biases=summary_data.get('biases', 'None identified'),
                    relevant_sections=summary_data.get('relevant_sections', ''),
                    skip_sections=summary_data.get('skip_sections', ''),
                    key_claims=summary_data.get('key_claims', []),
                    model_used=self.summary_model
                )

                success = self.create_note(
                    parent_key=item_key,
                    content=note_content,
                    title=self._get_summary_note_prefix(),
                    convert_markdown=True,
                    collection_key=collection_key
                )

                if success:
                    tags_str = ', '.join(summary_data['tags'][:3]) if summary_data['tags'] else 'None'
                    if len(summary_data['tags']) > 3:
                        tags_str += f", +{len(summary_data['tags'])-3} more"
                    role = summary_data.get('project_role', 'supporting')
                    print(f"  ✅ {item_title}")
                    print(f"     Type: {summary_data['document_type']} | Role: {role} | Tags: {tags_str}")
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
