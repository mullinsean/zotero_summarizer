#!/usr/bin/env python3
"""
ZoteroResearcher Organization Module

Handles organization of sources to ensure all items have acceptable attachments.
"""

import requests
import trafilatura
import time
from typing import Optional, Dict, List, Tuple

# Handle both relative and absolute imports
try:
    from .zr_common import ZoteroResearcherBase
except ImportError:
    from zr_common import ZoteroResearcherBase


class ZoteroResearcherOrganizer(ZoteroResearcherBase):
    """Handles organization of sources to ensure acceptable attachments exist."""

    def is_txt_attachment(self, attachment: Dict) -> bool:
        """
        Check if an attachment is a text file.

        Args:
            attachment: The attachment item data

        Returns:
            True if the attachment is a text file
        """
        content_type = attachment['data'].get('contentType', '')
        filename = attachment['data'].get('filename', '')

        return (content_type == 'text/plain' or
                filename.lower().endswith('.txt'))

    def has_acceptable_attachment(self, item_key: str) -> bool:
        """
        Check if an item has at least one acceptable attachment (HTML, PDF, or TXT).

        Args:
            item_key: The key of the parent item

        Returns:
            True if item has acceptable attachment, False otherwise
        """
        attachments = self.get_item_attachments(item_key)

        for attachment in attachments:
            if (self.is_html_attachment(attachment) or
                self.is_pdf_attachment(attachment) or
                self.is_txt_attachment(attachment)):
                return True

        return False

    def promote_attachment_to_parent(self, attachment_item: Dict) -> Optional[str]:
        """
        Create a proper parent item from a standalone attachment and recreate
        the attachment as a child.

        Args:
            attachment_item: The standalone attachment item

        Returns:
            Key of the newly created parent item, or None on failure
        """
        try:
            attachment_data = attachment_item['data']

            # Extract metadata from attachment
            filename = attachment_data.get('filename', attachment_data.get('title', 'Untitled'))
            url = attachment_data.get('url', '')
            content_type = attachment_data.get('contentType', '')

            # Remove file extension from filename for title
            title = filename
            for ext in ['.pdf', '.html', '.htm', '.txt']:
                if title.lower().endswith(ext):
                    title = title[:-len(ext)]
                    break

            # Determine parent item type based on content type
            if content_type == 'application/pdf':
                item_type = 'document'
            elif content_type in ['text/html', 'application/xhtml+xml']:
                item_type = 'webpage'
            elif content_type == 'text/plain':
                item_type = 'document'
            else:
                item_type = 'document'  # Default

            # Create parent item
            parent_template = self.zot.item_template(item_type)
            parent_template['title'] = title
            if url and item_type == 'webpage':
                parent_template['url'] = url

            # Preserve tags from attachment
            if 'tags' in attachment_data:
                parent_template['tags'] = attachment_data['tags']

            # Preserve collections
            if 'collections' in attachment_data:
                parent_template['collections'] = attachment_data['collections']

            print(f"  → Creating parent item: \"{title}\"")
            result = self.zot.create_items([parent_template])

            if not result['successful']:
                print(f"  ❌ Failed to create parent item: {result}")
                return None

            parent_key = result['successful']['0']['key']

            # Now we need to recreate the attachment as a child
            # Get the file content first
            try:
                file_content = self.download_attachment(attachment_item['key'])
                if not file_content:
                    print(f"  ⚠️  Warning: Could not download attachment content")
                    # Parent created but attachment not linked
                    return parent_key

                # Upload as child attachment using attachment_simple with file content
                # Note: pyzotero requires different approach for file uploads
                # We'll use the update approach to link the existing attachment

                # Update attachment to have parent
                attachment_update = attachment_item.copy()
                attachment_update['data']['parentItem'] = parent_key

                print(f"  → Linking attachment to parent")
                update_result = self.zot.update_item(attachment_update)

                if update_result:
                    print(f"  ✅ Attachment linked to parent successfully")
                else:
                    print(f"  ⚠️  Warning: Could not link attachment to parent")

                return parent_key

            except Exception as e:
                print(f"  ⚠️  Warning: Error processing attachment: {e}")
                # Parent created but attachment not linked
                return parent_key

        except Exception as e:
            print(f"  ❌ Error promoting attachment: {e}")
            return None

    def save_webpage_snapshot(self, item: Dict) -> bool:
        """
        Fetch webpage content and save as HTML attachment.

        Args:
            item: The webpage item

        Returns:
            True if snapshot saved successfully, False otherwise
        """
        item_data = item['data']
        item_key = item['key']
        url = item_data.get('url', '')

        if not url:
            print(f"  ❌ No URL found for item")
            return False

        try:
            print(f"  → Fetching snapshot from: {url}")

            # Fetch HTML content
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # Extract main content using Trafilatura
            markdown = trafilatura.extract(
                response.text,
                output_format='markdown',
                include_links=True,
                include_images=False,
                include_tables=True
            )

            if not markdown:
                # Fallback: use raw HTML if Trafilatura fails
                print(f"  ⚠️  Trafilatura extraction failed, using raw HTML")
                html_content = response.text
            else:
                # We have markdown, but we need HTML for attachment
                # Use the original HTML
                html_content = response.text

            # Create attachment using pyzotero's attachment methods
            # We'll save to a temporary file and upload
            import tempfile
            import os

            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                f.write(html_content)
                temp_path = f.name

            try:
                # Upload as imported file attachment
                attachment_template = self.zot.item_template('attachment', 'imported_file')
                attachment_template['title'] = f"Snapshot of {item_data.get('title', 'webpage')}"
                attachment_template['parentItem'] = item_key
                attachment_template['contentType'] = 'text/html'
                attachment_template['filename'] = f"snapshot_{item_key}.html"

                # Create the attachment item first
                result = self.zot.create_items([attachment_template])

                if result['successful']:
                    attachment_key = result['successful']['0']['key']

                    # Upload the file
                    with open(temp_path, 'rb') as f:
                        upload_result = self.zot.upload_attachment(attachment_key, f)

                    print(f"  ✅ Snapshot saved as HTML attachment")
                    return True
                else:
                    print(f"  ❌ Failed to create attachment: {result}")
                    return False

            finally:
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        except requests.exceptions.RequestException as e:
            print(f"  ❌ Error fetching URL: {e}")
            return False
        except Exception as e:
            print(f"  ❌ Error saving snapshot: {e}")
            return False

    def organize_sources(self, collection_key: str) -> Dict[str, int]:
        """
        Organize sources in a collection to ensure all items have acceptable attachments.

        For each source:
        1. If parent item is an attachment, promote it to proper item
        2. If item has no acceptable attachments, try to save webpage snapshot
        3. Report items that cannot be auto-fixed

        Args:
            collection_key: The Zotero collection key

        Returns:
            Statistics dictionary with counts of actions taken
        """
        stats = {
            'total_items': 0,
            'already_ok': 0,
            'attachments_promoted': 0,
            'snapshots_saved': 0,
            'txt_attachments_found': 0,
            'issues': 0
        }

        issues_list = []

        print(f"\n{'='*80}")
        print(f"Organizing Sources in Collection")
        print(f"{'='*80}\n")
        print(f"Processing items...\n")

        # Get all items in collection
        items = self.get_collection_items(collection_key)

        if not items:
            print("No items found in collection")
            return stats

        for idx, item in enumerate(items, 1):
            item_data = item['data']
            item_key = item['key']
            item_type = item_data.get('itemType', 'unknown')
            item_title = item_data.get('title', 'Untitled')

            stats['total_items'] += 1

            print(f"{idx}. \"{item_title}\" ({item_type})")

            # Skip notes (they don't need attachments)
            if item_type == 'note':
                print(f"   ⏭️  Skipping (note item)")
                stats['already_ok'] += 1
                continue

            # Step 1: Check if parent item is actually an attachment
            if item_type == 'attachment':
                print(f"   ⚠️  Standalone attachment detected")
                new_parent_key = self.promote_attachment_to_parent(item)
                if new_parent_key:
                    print(f"   ✅ Attachment promoted to proper item")
                    stats['attachments_promoted'] += 1
                else:
                    print(f"   ❌ Failed to promote attachment")
                    stats['issues'] += 1
                    issues_list.append((item_title, item_type, "Failed to promote attachment"))
                print()
                continue

            # Step 2: Check if item has acceptable child attachments
            if self.has_acceptable_attachment(item_key):
                # Get attachment types for verbose output
                if self.verbose:
                    attachments = self.get_item_attachments(item_key)
                    types = []
                    for att in attachments:
                        if self.is_html_attachment(att):
                            types.append('HTML')
                        elif self.is_pdf_attachment(att):
                            types.append('PDF')
                        elif self.is_txt_attachment(att):
                            types.append('TXT')
                    print(f"   ✅ Has acceptable attachment(s): {', '.join(set(types))}")
                else:
                    print(f"   ✅ Has acceptable attachment - OK")
                stats['already_ok'] += 1
                print()
                continue

            # Step 3: Try to save webpage snapshot
            print(f"   ⚠️  No acceptable attachments found")

            if item_type == 'webpage' and item_data.get('url'):
                if self.save_webpage_snapshot(item):
                    stats['snapshots_saved'] += 1
                else:
                    stats['issues'] += 1
                    issues_list.append((item_title, item_type, "Failed to save snapshot"))
            else:
                # Cannot auto-fix
                reason = "No URL available" if item_type == 'webpage' else f"Item type '{item_type}' not supported for snapshot"
                print(f"   ❌ Cannot auto-fix: {reason}")
                stats['issues'] += 1
                issues_list.append((item_title, item_type, reason))

            print()

            # Rate limiting
            time.sleep(self.rate_limit_delay)

        # Print summary
        print(f"{'='*80}")
        print(f"Organization Complete")
        print(f"{'='*80}\n")
        print(f"Summary:")
        print(f"  Total items processed: {stats['total_items']}")
        print(f"  Already OK: {stats['already_ok']}")
        print(f"  Attachments promoted: {stats['attachments_promoted']}")
        print(f"  Snapshots saved: {stats['snapshots_saved']}")
        print(f"  Issues (cannot auto-fix): {stats['issues']}")

        if issues_list:
            print(f"\nItems with issues:")
            for title, item_type, reason in issues_list:
                print(f"  - \"{title}\" ({item_type}) - {reason}")

        print(f"\n{'='*80}\n")

        return stats
