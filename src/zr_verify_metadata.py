#!/usr/bin/env python3
"""
ZoteroResearcher Metadata Verification Module

Audits and fixes bibliographic metadata on Zotero items using LLM-based
content analysis. Designed for APA 7th edition citation requirements.
"""

import csv
import re
from typing import Optional, Dict, List, Any

# Handle both relative and absolute imports
try:
    from .zr_common import ZoteroResearcherBase
    from .zr_prompts import metadata_verification_prompt
except ImportError:
    from zr_common import ZoteroResearcherBase
    from zr_prompts import metadata_verification_prompt


# Tag added to items after successful verification
VERIFIED_TAG = "_metadata_verified"

# Content limit for verification prompts (chars)
VERIFICATION_CONTENT_LIMIT = 15000

# Values considered suspicious/placeholder
SUSPICIOUS_VALUES = {
    "unknown", "untitled", "n/a", "na", "none", "tbd",
    "no author", "no date", "no title", "anonymous",
    "[no author]", "[no date]", "[no title]",
}

# APA 7th edition field requirements by item type
APA_FIELD_REQUIREMENTS = {
    'journalArticle': {
        'required': ['title', 'creators', 'date', 'publicationTitle'],
        'recommended': ['volume', 'issue', 'pages', 'DOI'],
    },
    'book': {
        'required': ['title', 'creators', 'date', 'publisher'],
        'recommended': ['ISBN', 'DOI', 'edition', 'place'],
    },
    'bookSection': {
        'required': ['title', 'creators', 'date', 'bookTitle', 'publisher'],
        'recommended': ['pages', 'ISBN', 'edition'],
    },
    'webpage': {
        'required': ['title', 'creators', 'date', 'websiteTitle', 'url'],
        'recommended': ['accessDate'],
    },
    'report': {
        'required': ['title', 'creators', 'date', 'institution'],
        'recommended': ['reportNumber', 'url'],
    },
    'conferencePaper': {
        'required': ['title', 'creators', 'date', 'conferenceName'],
        'recommended': ['pages', 'DOI', 'publisher'],
    },
    'thesis': {
        'required': ['title', 'creators', 'date', 'university'],
        'recommended': ['thesisType', 'url'],
    },
    'blogPost': {
        'required': ['title', 'creators', 'date', 'blogTitle', 'url'],
        'recommended': [],
    },
    'newspaperArticle': {
        'required': ['title', 'creators', 'date', 'publicationTitle'],
        'recommended': ['pages', 'url'],
    },
    'magazineArticle': {
        'required': ['title', 'creators', 'date', 'publicationTitle'],
        'recommended': ['volume', 'issue', 'pages'],
    },
    'document': {
        'required': ['title', 'creators', 'date'],
        'recommended': ['publisher', 'url'],
    },
    'preprint': {
        'required': ['title', 'creators', 'date', 'repository'],
        'recommended': ['DOI', 'url'],
    },
    '_default': {
        'required': ['title', 'creators', 'date'],
        'recommended': ['url'],
    },
}


class ZoteroMetadataVerifier(ZoteroResearcherBase):
    """Audits and fixes bibliographic metadata on Zotero items."""

    def verify_metadata(
        self,
        collection_key: str,
        dry_run: bool = False,
        skip_confirm: bool = False,
        subcollections: Optional[str] = None,
        include_main: bool = False,
        report_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Main entry point: audit and fix metadata for items in a collection.

        Four phases:
          A. Audit — check fields against APA requirements (no LLM)
          B. LLM Verification — extract/verify missing fields from content
          C. Compute Updates — determine safe changes
          D. Apply or Report — write to Zotero or show dry-run report

        Args:
            collection_key: Zotero collection key
            dry_run: If True, show what would change without writing
            skip_confirm: If True, skip confirmation prompt
            subcollections: Optional subcollection filter
            include_main: Include main collection items when filtering
            report_path: If set, write CSV report of audit results to this path

        Returns:
            Stats dict with counts of actions taken
        """
        stats = {
            'total_items': 0,
            'skipped_verified': 0,
            'skipped_notes': 0,
            'skipped_attachments': 0,
            'audited': 0,
            'needs_verification': 0,
            'already_complete': 0,
            'llm_verified': 0,
            'items_updated': 0,
            'fields_updated': 0,
            'items_retyped': 0,
            'errors': 0,
        }
        report_rows = []

        print("=" * 80)
        print("METADATA VERIFICATION")
        print("=" * 80)
        if dry_run:
            print("MODE: Dry run (no changes will be made)\n")
        else:
            print()

        # ── Phase A: Audit ──────────────────────────────────────────────
        print("Phase A: Auditing metadata fields...\n")

        items = self.get_items_to_process(
            collection_key,
            subcollections=subcollections,
            include_main=include_main
        )
        stats['total_items'] = len(items)
        print(f"Found {len(items)} items in collection\n")

        if not items:
            print("No items to process.")
            if report_path:
                self._generate_csv_report(report_rows, report_path)
            return stats

        # Filter out notes and standalone attachments (only process regular items)
        processable_items = []
        for item in items:
            item_type = item['data'].get('itemType', '')
            if item_type == 'note':
                stats['skipped_notes'] += 1
                continue
            if item_type == 'attachment':
                stats['skipped_attachments'] += 1
                continue
            processable_items.append(item)

        if stats['skipped_attachments'] > 0:
            print(f"Found {stats['skipped_attachments']} standalone attachments (no parent item) — these will be skipped.")
            print(f"  Run --organize-sources first to convert them to proper items.\n")

        if not processable_items:
            print("No processable items found (all items are notes/attachments).")
            if report_path:
                self._generate_csv_report(report_rows, report_path)
            return stats

        # Check for already-verified items
        items_to_audit = []
        for item in processable_items:
            if not self.force_rebuild and self._has_verified_tag(item):
                stats['skipped_verified'] += 1
                report_rows.append(self._build_report_row(item, 'verified'))
                continue
            items_to_audit.append(item)

        if stats['skipped_verified'] > 0:
            print(f"Skipped {stats['skipped_verified']} previously verified items (use --force to re-verify)")

        if not items_to_audit:
            print("\nAll items already verified. Use --force to re-verify.")
            if report_path:
                self._generate_csv_report(report_rows, report_path)
            return stats

        # Audit each item's fields
        items_needing_llm = []  # (item, audit_result) pairs
        for item in items_to_audit:
            audit = self._audit_item(item)
            stats['audited'] += 1

            if audit['needs_verification']:
                items_needing_llm.append((item, audit))
                stats['needs_verification'] += 1
            else:
                stats['already_complete'] += 1
                report_rows.append(self._build_report_row(item, 'complete'))

        print(f"\nAudit complete:")
        print(f"  {stats['audited']} items audited")
        print(f"  {stats['already_complete']} items have complete metadata")
        print(f"  {stats['needs_verification']} items need LLM verification")

        if not items_needing_llm:
            # Tag complete items if not dry run
            if not dry_run:
                self._tag_complete_items(items_to_audit, items_needing_llm)
            print("\nNo items need LLM verification.")
            if report_path:
                self._generate_csv_report(report_rows, report_path)
            return stats

        # ── Phase B: LLM Verification ──────────────────────────────────
        print(f"\nPhase B: Verifying {len(items_needing_llm)} items with LLM...\n")

        # Build batch requests
        batch_requests = []
        item_map = {}  # request_id -> (item, audit)
        no_content_count = 0
        no_content_titles = []

        for item, audit in items_needing_llm:
            item_key = item['key']
            item_title = item['data'].get('title', 'Untitled')

            # Get source content
            content, content_type = self.get_source_content(item)
            if not content:
                no_content_count += 1
                no_content_titles.append(item_title)
                report_rows.append(self._build_report_row(
                    item, 'incomplete', missing_fields=audit['missing_fields']))
                stats['errors'] += 1
                continue

            # Truncate content
            content_truncated = content[:VERIFICATION_CONTENT_LIMIT]

            # Build prompt
            prompt = metadata_verification_prompt(
                item_type=audit['item_type'],
                current_metadata=audit['current_metadata'],
                missing_fields=audit['missing_fields'],
                suspicious_fields=audit['suspicious_fields'],
                content=content_truncated
            )

            batch_requests.append({
                'id': item_key,
                'prompt': prompt,
                'max_tokens': 2000,
                'model': self.haiku_model,
                'temperature': 0.2,
            })
            item_map[item_key] = (item, audit)

        if no_content_count > 0:
            print(f"\n  Skipped {no_content_count}/{len(items_needing_llm)} items: no extractable content (no attachments or URL fetch failed)")
            if self.verbose:
                for title in no_content_titles:
                    print(f"    - {title}")
            print(f"  Tip: Run --organize-sources first to save webpage snapshots and create parent items\n")

        if not batch_requests:
            print("No items had extractable content for verification.")
            if report_path:
                self._generate_csv_report(report_rows, report_path)
            return stats

        # Progress callback
        def progress_cb(completed, total):
            print(f"\r  LLM progress: {completed}/{total} items verified", end="", flush=True)

        # Execute batch
        parsed_results = self.llm_client.call_batch_with_parsing(
            requests=batch_requests,
            parser=self._parse_verification_response,
            max_workers=self.max_workers,
            rate_limit_delay=self.rate_limit_delay,
            progress_callback=progress_cb,
        )
        print()  # newline after progress

        stats['llm_verified'] = sum(1 for v in parsed_results.values() if v is not None)
        print(f"  {stats['llm_verified']}/{len(batch_requests)} items successfully verified")

        # ── Phase C: Compute Updates ────────────────────────────────────
        print(f"\nPhase C: Computing updates...\n")

        update_plans = []  # list of (item, changes_dict, type_change_dict_or_None)

        for request_id, parsed in parsed_results.items():
            if parsed is None:
                continue

            item, audit = item_map[request_id]
            item_title = item['data'].get('title', 'Untitled')

            changes = self._compute_field_updates(item, audit, parsed)
            type_change = self._compute_type_change(item, parsed)

            if changes or type_change:
                update_plans.append((item, changes, type_change))

        # Build report rows for LLM-processed items
        updated_keys = {item['key'] for item, _, _ in update_plans}
        for request_id, (item, audit) in item_map.items():
            parsed = parsed_results.get(request_id)
            if parsed is None:
                report_rows.append(self._build_report_row(
                    item, 'incomplete', missing_fields=audit['missing_fields']))
            elif request_id in updated_keys:
                fields_updated_list = []
                type_override = None
                for uitem, uchanges, utype_change in update_plans:
                    if uitem['key'] == request_id:
                        fields_updated_list = list(uchanges.keys())
                        type_override = utype_change['to'] if utype_change else None
                        break
                remaining_missing = [f for f in audit['missing_fields']
                                     if f not in fields_updated_list]
                report_rows.append(self._build_report_row(
                    item, 'updated', missing_fields=remaining_missing,
                    fields_updated=fields_updated_list,
                    item_type_override=type_override))
            else:
                report_rows.append(self._build_report_row(
                    item, 'complete', missing_fields=audit['missing_fields']))

        # ── Phase D: Apply or Report ────────────────────────────────────
        print(f"Phase D: {'Reporting changes (dry run)' if dry_run else 'Applying updates'}...\n")

        if not update_plans:
            print("No metadata updates needed.")
            # Tag all verified items (even if no changes needed)
            if not dry_run:
                self._tag_verified_items(
                    [item for item, _ in items_needing_llm],
                    parsed_results
                )
            if report_path:
                self._generate_csv_report(report_rows, report_path)
            return stats

        # Display proposed changes
        for item, changes, type_change in update_plans:
            item_title = item['data'].get('title', 'Untitled')[:60]
            item_key = item['key']
            print(f"  [{item_key}] {item_title}")

            if type_change:
                print(f"    Type: {type_change['from']} -> {type_change['to']} ({type_change['confidence']})")

            for field, change in changes.items():
                old_val = change.get('old', '(empty)')
                new_val = change['new']
                action = change['action']
                conf = change['confidence']
                print(f"    {field}: {old_val!r} -> {new_val!r} [{action}, {conf}]")

            print()

        print(f"Summary: {len(update_plans)} items with proposed changes")

        if dry_run:
            print("\nDry run complete. No changes were made.")
            if report_path:
                self._generate_csv_report(report_rows, report_path)
            return stats

        # Confirm unless --yes
        if not skip_confirm:
            response = input(f"\nApply changes to {len(update_plans)} items? [y/N] ").strip().lower()
            if response not in ('y', 'yes'):
                print("Aborted.")
                if report_path:
                    self._generate_csv_report(report_rows, report_path)
                return stats

        # Apply updates
        for item, changes, type_change in update_plans:
            item_title = item['data'].get('title', 'Untitled')[:60]
            try:
                updated = self._apply_updates(item, changes, type_change)
                if updated:
                    stats['items_updated'] += 1
                    stats['fields_updated'] += len(changes)
                    if type_change:
                        stats['items_retyped'] += 1
                    print(f"  Updated: {item_title}")
                else:
                    stats['errors'] += 1
                    print(f"  Failed: {item_title}")
            except Exception as e:
                stats['errors'] += 1
                print(f"  Error updating {item_title}: {e}")

        # Tag all successfully verified items
        self._tag_verified_items(
            [item for item, _ in items_needing_llm],
            parsed_results
        )

        # Final summary
        print(f"\n{'='*80}")
        print(f"VERIFICATION COMPLETE")
        print(f"{'='*80}")
        print(f"  Items in collection: {stats['total_items']}")
        print(f"  Previously verified: {stats['skipped_verified']}")
        print(f"  Audited:             {stats['audited']}")
        print(f"  Already complete:    {stats['already_complete']}")
        print(f"  LLM verified:        {stats['llm_verified']}")
        print(f"  Items updated:       {stats['items_updated']}")
        print(f"  Fields updated:      {stats['fields_updated']}")
        print(f"  Items retyped:       {stats['items_retyped']}")
        print(f"  Errors:              {stats['errors']}")

        if report_path:
            self._generate_csv_report(report_rows, report_path)
        return stats

    # ── Audit helpers ───────────────────────────────────────────────────

    def _has_verified_tag(self, item: Dict) -> bool:
        """Check if item has the _metadata_verified tag."""
        tags = item['data'].get('tags', [])
        return any(t.get('tag') == VERIFIED_TAG for t in tags)

    def _audit_item(self, item: Dict) -> Dict[str, Any]:
        """
        Audit a single item's metadata against APA requirements.

        Returns dict with:
          item_type, current_metadata, missing_fields, suspicious_fields,
          ok_fields, needs_verification
        """
        item_data = item['data']
        item_type = item_data.get('itemType', 'document')

        # Get requirements for this item type
        reqs = APA_FIELD_REQUIREMENTS.get(item_type, APA_FIELD_REQUIREMENTS['_default'])
        all_fields = reqs['required'] + reqs['recommended']

        # Build current metadata dict
        current_metadata = {}
        missing_fields = []
        suspicious_fields = []
        ok_fields = []

        for field in all_fields:
            if field == 'creators':
                # Special handling for creators
                creators = item_data.get('creators', [])
                if not creators:
                    current_metadata['creators'] = '(empty)'
                    missing_fields.append('creators')
                else:
                    # Format creators for display
                    creator_strs = []
                    for c in creators:
                        if 'lastName' in c:
                            name = f"{c.get('firstName', '')} {c['lastName']}".strip()
                        else:
                            name = c.get('name', '')
                        creator_strs.append(name)
                    creator_display = '; '.join(creator_strs)
                    current_metadata['creators'] = creator_display

                    # Check if suspicious
                    if self._is_suspicious_value(creator_display):
                        suspicious_fields.append('creators')
                    else:
                        ok_fields.append('creators')
            else:
                value = item_data.get(field, '')
                current_metadata[field] = value if value else '(empty)'

                if not value:
                    missing_fields.append(field)
                elif self._is_suspicious_value(value):
                    suspicious_fields.append(field)
                else:
                    ok_fields.append(field)

        needs_verification = len(missing_fields) > 0 or len(suspicious_fields) > 0

        return {
            'item_type': item_type,
            'current_metadata': current_metadata,
            'missing_fields': missing_fields,
            'suspicious_fields': suspicious_fields,
            'ok_fields': ok_fields,
            'needs_verification': needs_verification,
            'required_fields': reqs['required'],
            'recommended_fields': reqs['recommended'],
        }

    def _is_suspicious_value(self, value: str) -> bool:
        """Check if a field value looks like a placeholder."""
        if not value:
            return False
        normalized = value.strip().lower()
        return normalized in SUSPICIOUS_VALUES

    # ── Response parsing ────────────────────────────────────────────────

    def _parse_verification_response(self, response_text: str) -> Optional[Dict]:
        """
        Parse the LLM verification response into structured data.

        Returns dict with:
          type_assessment: {current, suggested, confidence, reason}
          fields: {field_name: {status, value, confidence}}
        """
        result = {
            'type_assessment': None,
            'fields': {},
        }

        lines = response_text.strip().split('\n')
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # Parse ITEM_TYPE_ASSESSMENT block
            if line.startswith('ITEM_TYPE_ASSESSMENT:'):
                assessment = {}
                i += 1
                while i < len(lines):
                    aline = lines[i].strip()
                    if aline.startswith('CURRENT:'):
                        assessment['current'] = aline[len('CURRENT:'):].strip()
                    elif aline.startswith('SUGGESTED:'):
                        assessment['suggested'] = aline[len('SUGGESTED:'):].strip()
                    elif aline.startswith('CONFIDENCE:'):
                        assessment['confidence'] = aline[len('CONFIDENCE:'):].strip().lower()
                    elif aline.startswith('REASON:'):
                        assessment['reason'] = aline[len('REASON:'):].strip()
                    elif aline.startswith('FIELD:') or aline == '':
                        break
                    i += 1
                if 'suggested' in assessment:
                    result['type_assessment'] = assessment
                continue

            # Parse FIELD blocks
            if line.startswith('FIELD:'):
                field_name = line[len('FIELD:'):].strip()
                field_data = {}
                i += 1
                while i < len(lines):
                    fline = lines[i].strip()
                    if fline.startswith('STATUS:'):
                        field_data['status'] = fline[len('STATUS:'):].strip().lower()
                    elif fline.startswith('VALUE:'):
                        field_data['value'] = fline[len('VALUE:'):].strip()
                    elif fline.startswith('CONFIDENCE:'):
                        field_data['confidence'] = fline[len('CONFIDENCE:'):].strip().lower()
                    elif fline.startswith('FIELD:') or fline.startswith('ITEM_TYPE_ASSESSMENT:'):
                        break
                    i += 1
                if 'value' in field_data and 'status' in field_data:
                    result['fields'][field_name] = field_data
                continue

            i += 1

        return result if (result['type_assessment'] or result['fields']) else None

    # ── Update computation ──────────────────────────────────────────────

    def _compute_field_updates(
        self,
        item: Dict,
        audit: Dict,
        parsed: Dict
    ) -> Dict[str, Dict]:
        """
        Determine which fields to update based on LLM verification results.

        Returns dict of field_name -> {old, new, action, confidence}
        Only includes fields that should actually be updated.
        """
        changes = {}
        item_data = item['data']

        for field_name, field_info in parsed.get('fields', {}).items():
            status = field_info.get('status', '')
            value = field_info.get('value', '')
            confidence = field_info.get('confidence', 'low')

            # Skip not_found results
            if status == 'not_found' or not value:
                continue

            # Determine if this field should be updated
            is_missing = field_name in audit['missing_fields']
            is_suspicious = field_name in audit['suspicious_fields']
            is_existing = not is_missing and not is_suspicious

            should_update = False

            if status == 'extracted' and (is_missing or is_suspicious):
                # Auto-fill missing/suspicious fields with high or medium confidence
                if confidence in ('high', 'medium'):
                    should_update = True
            elif status == 'corrected':
                if is_suspicious and confidence == 'high':
                    # Auto-fix suspicious fields with high confidence
                    should_update = True
                elif is_existing and self.force_rebuild and confidence == 'high':
                    # With --force, also correct existing fields
                    should_update = True
                # Otherwise: existing field corrections are reported but not applied
            elif status == 'confirmed':
                # No change needed
                continue

            if should_update:
                old_value = self._get_current_field_value(item_data, field_name)
                changes[field_name] = {
                    'old': old_value,
                    'new': value,
                    'action': status,
                    'confidence': confidence,
                }

        return changes

    def _compute_type_change(self, item: Dict, parsed: Dict) -> Optional[Dict]:
        """
        Determine if item type should be changed.

        Returns dict with {from, to, confidence, reason} or None.
        """
        assessment = parsed.get('type_assessment')
        if not assessment:
            return None

        current = item['data'].get('itemType', '')
        suggested = assessment.get('suggested', '')
        confidence = assessment.get('confidence', 'low')
        reason = assessment.get('reason', '')

        # Only change type if different and high confidence
        if suggested and suggested != current and confidence == 'high':
            return {
                'from': current,
                'to': suggested,
                'confidence': confidence,
                'reason': reason,
            }

        return None

    def _get_current_field_value(self, item_data: Dict, field_name: str) -> str:
        """Get the current value of a field, handling creators specially."""
        if field_name == 'creators':
            creators = item_data.get('creators', [])
            if not creators:
                return '(empty)'
            parts = []
            for c in creators:
                if 'lastName' in c:
                    parts.append(f"{c.get('firstName', '')} {c['lastName']}".strip())
                else:
                    parts.append(c.get('name', ''))
            return '; '.join(parts)
        return item_data.get(field_name, '(empty)')

    # ── Apply updates ───────────────────────────────────────────────────

    def _apply_updates(
        self,
        item: Dict,
        changes: Dict[str, Dict],
        type_change: Optional[Dict]
    ) -> bool:
        """
        Apply computed updates to a Zotero item via the API.

        If there's a type change, re-fetches the item template for the new type,
        preserves overlapping fields, then applies field updates.

        Returns True on success, False on failure.
        """
        item_data = item['data']

        # Handle type change first
        if type_change:
            new_type = type_change['to']
            try:
                # Get template for new type to know valid fields
                new_template = self.zot.item_template(new_type)
                template_fields = set(new_template.keys())

                # Change the item type
                item_data['itemType'] = new_type

                # Remove fields that don't exist in the new type
                # (Zotero API will reject unknown fields)
                fields_to_remove = []
                for key in list(item_data.keys()):
                    if key not in template_fields and key not in (
                        'key', 'version', 'tags', 'collections', 'relations',
                        'dateAdded', 'dateModified'
                    ):
                        fields_to_remove.append(key)

                for key in fields_to_remove:
                    del item_data[key]

                # Add any new fields from template that don't exist yet
                for key, default_val in new_template.items():
                    if key not in item_data:
                        item_data[key] = default_val

            except Exception as e:
                print(f"    Warning: Could not change type to {new_type}: {e}")
                # Continue with field updates even if type change fails

        # Apply field changes
        for field_name, change in changes.items():
            new_value = change['new']

            if field_name == 'creators':
                # Parse creators from LLM output
                creators = self._parse_creators_value(new_value)
                if creators:
                    item_data['creators'] = creators
            else:
                item_data[field_name] = new_value

        # Write to Zotero
        try:
            self.zot.update_item(item)
            return True
        except Exception as e:
            print(f"    Zotero API error: {e}")
            return False

    def _parse_creators_value(self, creators_str: str) -> List[Dict]:
        """
        Parse a creators string from LLM output into Zotero creators format.

        Accepts formats like:
          "LastName, FirstName; LastName2, FirstName2"
          "Organization Name"
          "FirstName LastName"
        """
        creators = []
        # Split by semicolons for multiple authors
        parts = [p.strip() for p in creators_str.split(';') if p.strip()]

        for part in parts:
            if ',' in part:
                # "LastName, FirstName" format
                name_parts = part.split(',', 1)
                last_name = name_parts[0].strip()
                first_name = name_parts[1].strip() if len(name_parts) > 1 else ''
                creators.append({
                    'creatorType': 'author',
                    'firstName': first_name,
                    'lastName': last_name,
                })
            elif ' ' in part:
                # "FirstName LastName" format
                words = part.strip().split()
                if len(words) >= 2:
                    creators.append({
                        'creatorType': 'author',
                        'firstName': ' '.join(words[:-1]),
                        'lastName': words[-1],
                    })
                else:
                    creators.append({
                        'creatorType': 'author',
                        'name': part.strip(),
                    })
            else:
                # Single name or organization
                creators.append({
                    'creatorType': 'author',
                    'name': part.strip(),
                })

        return creators

    # ── Tagging helpers ─────────────────────────────────────────────────

    def _tag_complete_items(
        self,
        all_audited: List[Dict],
        items_needing_llm: List
    ) -> None:
        """Tag items that passed audit (already complete) with _metadata_verified."""
        needing_keys = {item['key'] for item, _ in items_needing_llm}
        for item in all_audited:
            if item['key'] not in needing_keys and not self._has_verified_tag(item):
                self._add_verified_tag(item)

    def _tag_verified_items(
        self,
        items: List[Dict],
        parsed_results: Dict
    ) -> None:
        """Tag items that were successfully LLM-verified."""
        for item in items:
            item_key = item['key']
            # Only tag if LLM returned a result (even if no changes needed)
            if item_key in parsed_results and parsed_results[item_key] is not None:
                if not self._has_verified_tag(item):
                    self._add_verified_tag(item)

    def _add_verified_tag(self, item: Dict) -> None:
        """Add _metadata_verified tag to an item."""
        tags = item['data'].get('tags', [])
        tags.append({'tag': VERIFIED_TAG})
        item['data']['tags'] = tags
        try:
            self.zot.update_item(item)
        except Exception as e:
            if self.verbose:
                print(f"  Warning: Could not add verified tag to {item['key']}: {e}")

    # ── CSV Report ─────────────────────────────────────────────────────

    def _build_report_row(
        self,
        item: Dict,
        status: str,
        missing_fields: Optional[List[str]] = None,
        fields_updated: Optional[List[str]] = None,
        item_type_override: Optional[str] = None
    ) -> Dict[str, str]:
        """Build a single CSV report row for an item."""
        data = item['data']
        item_type = item_type_override or data.get('itemType', '')

        # Format creators as "Last, First; Last, First"
        creators = data.get('creators', [])
        creator_parts = []
        for c in creators:
            if 'lastName' in c:
                first = c.get('firstName', '')
                last = c['lastName']
                creator_parts.append(f"{last}, {first}" if first else last)
            else:
                creator_parts.append(c.get('name', ''))
        creators_str = '; '.join(creator_parts)

        # Get publication from type-appropriate field
        publication = ''
        for field in ['publicationTitle', 'bookTitle', 'websiteTitle',
                      'blogTitle', 'institution']:
            val = data.get(field, '')
            if val:
                publication = val
                break

        return {
            'item_key': item['key'],
            'item_type': item_type,
            'title': data.get('title', ''),
            'creators': creators_str,
            'date': data.get('date', ''),
            'publication': publication,
            'publisher': data.get('publisher', ''),
            'DOI': data.get('DOI', ''),
            'url': data.get('url', ''),
            'status': status,
            'missing_fields': '; '.join(missing_fields) if missing_fields else '',
            'fields_updated': '; '.join(fields_updated) if fields_updated else '',
        }

    def _generate_csv_report(self, report_rows: List[Dict], report_path: str) -> None:
        """Write CSV report of metadata audit results."""
        fieldnames = [
            'item_key', 'item_type', 'title', 'creators', 'date',
            'publication', 'publisher', 'DOI', 'url', 'status',
            'missing_fields', 'fields_updated',
        ]
        with open(report_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(report_rows)
        print(f"\nCSV report written: {report_path} ({len(report_rows)} items)")
