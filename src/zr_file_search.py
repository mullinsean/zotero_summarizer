#!/usr/bin/env python3
"""
ZoteroResearcher File Search Module

Handles Google Gemini File Search integration for RAG-based querying.
"""

import os
import json
import time
from typing import Optional, Dict, List
from datetime import datetime

# Handle both relative and absolute imports
try:
    from .zr_common import ZoteroResearcherBase
except ImportError:
    from zr_common import ZoteroResearcherBase


class ZoteroFileSearcher(ZoteroResearcherBase):
    """Handles Google Gemini File Search for RAG-based querying of sources."""

    def __init__(
        self,
        library_id: str,
        library_type: str,
        api_key: str,
        anthropic_api_key: str,
        gemini_api_key: str,
        project_name: str = None,
        force_rebuild: bool = False,
        verbose: bool = False
    ):
        """
        Initialize the Zotero File Searcher.

        Args:
            library_id: Your Zotero user ID or group ID
            library_type: 'user' or 'group'
            api_key: Your Zotero API key
            anthropic_api_key: Anthropic API key for Claude
            gemini_api_key: Google Gemini API key
            project_name: Name of the research project
            force_rebuild: If True, force re-upload of files
            verbose: If True, show detailed information
        """
        super().__init__(
            library_id,
            library_type,
            api_key,
            anthropic_api_key,
            project_name,
            force_rebuild,
            verbose
        )

        # Import Gemini SDK
        try:
            from google import genai
            from google.genai import types
            self.genai = genai
            self.genai_types = types
            self.genai_client = genai.Client(api_key=gemini_api_key)
        except ImportError:
            raise ImportError(
                "google-genai package not found. "
                "Install it with: uv pip install google-genai"
            )

        # Gemini File Search state
        self.file_search_store_name = None  # File search store name
        self.uploaded_files = {}  # Map of item_key -> file name for tracking

    def _get_research_report_note_title(self, report_number: int = 1) -> str:
        """Get project-specific research report note title."""
        if not self.project_name:
            raise ValueError("Project name is required but not set")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"【Research Report #{report_number}: {timestamp}】"

    def _load_gemini_state_from_config(self, collection_key: str) -> Dict:
        """
        Load Gemini file search state from Project Config.

        Args:
            collection_key: Parent collection key

        Returns:
            Dict with file_search_store_name and uploaded_files
        """
        try:
            config = self.load_project_config_from_zotero(collection_key)

            # Extract Gemini-specific state
            gemini_state = {
                'file_search_store_name': None,
                'uploaded_files': {}
            }

            # Parse file search store name
            store_name = config.get('gemini_file_search_store', '')
            if store_name:
                gemini_state['file_search_store_name'] = store_name

            # Parse uploaded files JSON if present
            uploaded_files_json = config.get('gemini_uploaded_files', '')
            if uploaded_files_json:
                try:
                    gemini_state['uploaded_files'] = json.loads(uploaded_files_json)
                except json.JSONDecodeError:
                    print("  ⚠️  Warning: Could not parse gemini_uploaded_files from config")
                    gemini_state['uploaded_files'] = {}

            return gemini_state

        except FileNotFoundError:
            # Config doesn't exist yet - return empty state
            return {'file_search_store_name': None, 'uploaded_files': {}}

    def _save_gemini_state_to_config(self, collection_key: str):
        """
        Save Gemini file search state to Project Config note.

        Args:
            collection_key: Parent collection key
        """
        note_title = self._get_project_config_note_title()

        # Find the config note
        config_note = self.get_note_from_subcollection(collection_key, note_title)
        if not config_note:
            raise FileNotFoundError(
                f"{note_title} not found. "
                f"Run --init-collection --project \"{self.project_name}\" first."
            )

        # Extract existing content
        content = self.extract_text_from_note_html(config_note['data']['note'])

        # Update or add Gemini state lines
        lines = content.split('\n')
        new_lines = []
        found_store = False
        found_files = False

        for line in lines:
            if line.strip().startswith('gemini_file_search_store='):
                if self.file_search_store_name:
                    new_lines.append(f"gemini_file_search_store={self.file_search_store_name}")
                found_store = True
            elif line.strip().startswith('gemini_uploaded_files='):
                uploaded_files_json = json.dumps(self.uploaded_files)
                new_lines.append(f"gemini_uploaded_files={uploaded_files_json}")
                found_files = True
            else:
                new_lines.append(line)

        # Add new entries if not found
        if not found_store or not found_files:
            # Insert before the notes section
            insert_idx = len(new_lines)
            for i, line in enumerate(new_lines):
                if line.strip().startswith('# ===') and 'Notes' in line:
                    insert_idx = i
                    break

            if insert_idx > 0 and not new_lines[insert_idx - 1].strip().startswith('# ==='):
                # Add Gemini section header
                new_lines.insert(insert_idx, '')
                new_lines.insert(insert_idx + 1, '# ============================================================')
                new_lines.insert(insert_idx + 2, '# Gemini File API State (managed automatically)')
                new_lines.insert(insert_idx + 3, '# ============================================================')
                idx = insert_idx + 4
                if not found_store and self.file_search_store_name:
                    new_lines.insert(idx, f'gemini_file_search_store={self.file_search_store_name}')
                    idx += 1
                if not found_files:
                    uploaded_files_json = json.dumps(self.uploaded_files)
                    new_lines.insert(idx, f'gemini_uploaded_files={uploaded_files_json}')
            else:
                if not found_store and self.file_search_store_name:
                    new_lines.insert(insert_idx, f'gemini_file_search_store={self.file_search_store_name}')
                    insert_idx += 1
                if not found_files:
                    uploaded_files_json = json.dumps(self.uploaded_files)
                    new_lines.insert(insert_idx, f'gemini_uploaded_files={uploaded_files_json}')

        # Update note content using generic method
        updated_content = '\n'.join(new_lines)
        self.update_note_in_subcollection(
            collection_key,
            note_title,
            updated_content,
            preserve_formatting=True
        )

    def upload_files_to_gemini(self, collection_key: str) -> bool:
        """
        Upload all compatible sources from collection to Google Gemini File Search Store.

        Args:
            collection_key: Collection key to process

        Returns:
            True if upload successful
        """
        print(f"\n{'='*80}")
        print(f"Uploading Files to Google Gemini File Search Store")
        print(f"Project: {self.project_name}")
        print(f"{'='*80}\n")

        # Load existing Gemini state
        gemini_state = self._load_gemini_state_from_config(collection_key)
        self.file_search_store_name = gemini_state['file_search_store_name']
        self.uploaded_files = gemini_state['uploaded_files']

        # Force rebuild: delete old store and create new one
        if self.force_rebuild and self.file_search_store_name:
            print(f"🗑️  Force rebuild: Deleting existing file search store...")
            try:
                self.genai_client.file_search_stores.delete(name=self.file_search_store_name)
                print(f"  Deleted store: {self.file_search_store_name}")
                self.file_search_store_name = None
                self.uploaded_files = {}
            except Exception as e:
                print(f"  Error deleting store: {e}")
                # Continue anyway - we'll create a new store
                self.file_search_store_name = None
                self.uploaded_files = {}
            print()

        # Create file search store if needed
        if not self.file_search_store_name:
            print(f"Creating new file search store...")
            try:
                # Create store with display name in config
                store = self.genai_client.file_search_stores.create(
                    config={'display_name': f'ZResearcher: {self.project_name}'}
                )
                self.file_search_store_name = store.name
                print(f"✅ Created store: {self.file_search_store_name}\n")
            except Exception as e:
                print(f"❌ Error creating file search store: {e}")
                import traceback
                traceback.print_exc()
                return False
        else:
            print(f"ℹ️  Using existing file search store: {self.file_search_store_name}\n")

        # Get collection items
        print(f"Loading collection items...")
        items = self.get_collection_items(collection_key)
        print(f"Found {len(items)} items in collection\n")

        # Process each item
        uploaded_count = 0
        skipped_count = 0
        error_count = 0

        for idx, item in enumerate(items, 1):
            item_key = item['key']
            item_data = item['data']
            item_type = item_data.get('itemType')

            # Skip notes and standalone attachments
            if item_type in ['note', 'attachment']:
                continue

            item_title = item_data.get('title', 'Untitled')
            print(f"[{idx}/{len(items)}] {item_title}")

            # Check if already uploaded (and not forcing rebuild)
            if item_key in self.uploaded_files and not self.force_rebuild:
                print(f"  ⏭️  Already uploaded, skipping...")
                skipped_count += 1
                continue

            # Get attachments
            attachments = self.get_item_attachments(item_key)

            if not attachments:
                print(f"  ⚠️  No attachments found, skipping...")
                skipped_count += 1
                continue

            # Try to find a compatible attachment (PDF, HTML, TXT)
            uploaded = False

            for attachment in attachments:
                attachment_type = attachment['data'].get('contentType', '')
                attachment_title = attachment['data'].get('title', 'Untitled')
                attachment_key = attachment['key']

                # Check if compatible file type
                if not (self.is_pdf_attachment(attachment) or
                       self.is_html_attachment(attachment) or
                       self.is_txt_attachment(attachment)):
                    continue

                print(f"  📄 Found attachment: {attachment_title}")
                print(f"  📥 Downloading...")

                # Download attachment
                content = self.download_attachment(attachment_key)

                if not content:
                    print(f"  ❌ Failed to download attachment")
                    continue

                # Determine file extension
                if self.is_pdf_attachment(attachment):
                    ext = 'pdf'
                elif self.is_html_attachment(attachment):
                    ext = 'html'
                elif self.is_txt_attachment(attachment):
                    ext = 'txt'
                else:
                    ext = 'bin'

                # Create temporary file for upload
                temp_filename = f"zotero_{item_key}_{attachment_key}.{ext}"
                temp_path = f"/tmp/{temp_filename}"

                try:
                    # Write content to temp file
                    with open(temp_path, 'wb') as f:
                        f.write(content)

                    # Upload to Gemini File Search Store
                    print(f"  ☁️  Uploading to file search store...")

                    upload_op = self.genai_client.file_search_stores.upload_to_file_search_store(
                        file=temp_path,
                        file_search_store_name=self.file_search_store_name,
                        config={'display_name': f"{item_title} - {attachment_title}"}
                    )

                    # Wait for upload operation to complete
                    print(f"  ⏳ Waiting for upload to complete...")
                    max_wait = 120  # 2 minutes
                    waited = 0
                    while not upload_op.done and waited < max_wait:
                        time.sleep(5)
                        waited += 5
                        upload_op = self.genai_client.operations.get(upload_op)

                    if not upload_op.done:
                        print(f"  ⚠️  Upload operation timed out after {max_wait}s")
                        error_count += 1
                    else:
                        # Track uploaded file
                        self.uploaded_files[item_key] = temp_filename
                        uploaded_count += 1
                        uploaded = True

                        print(f"  ✅ Uploaded successfully")

                    # Clean up temp file
                    os.remove(temp_path)

                    break  # Successfully uploaded, move to next item

                except Exception as e:
                    print(f"  ❌ Error uploading: {e}")
                    import traceback
                    traceback.print_exc()
                    error_count += 1
                    # Clean up temp file on error
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    continue

            if not uploaded and attachments:
                print(f"  ⚠️  No compatible attachments found")
                skipped_count += 1

            # Rate limiting
            time.sleep(self.rate_limit_delay)

        # Save state
        print(f"\n{'='*80}")
        print(f"Upload Summary")
        print(f"{'='*80}")
        print(f"  Store: {self.file_search_store_name}")
        print(f"  Uploaded: {uploaded_count}")
        print(f"  Skipped: {skipped_count}")
        print(f"  Errors: {error_count}")
        print(f"  Total files in store: {len(self.uploaded_files)}")
        print(f"{'='*80}\n")

        # Save Gemini state to config
        print(f"Saving upload state to Project Config...")
        self._save_gemini_state_to_config(collection_key)
        print(f"✅ State saved successfully\n")

        return True

    def load_query_request_from_zotero(self, collection_key: str) -> str:
        """
        Load query request from project-specific subcollection note.

        Args:
            collection_key: Parent collection key

        Returns:
            Query request text

        Raises:
            FileNotFoundError: If subcollection or note not found
            ValueError: If note still contains template placeholder
        """
        return self.load_note_from_subcollection(
            collection_key,
            self._get_query_request_note_title(),
            check_todo=True,
            remove_title_line=True,
            remove_footer=True,
            operation_name="running file search"
        )

    def run_file_search(self, collection_key: str) -> Optional[str]:
        """
        Run Gemini File Search query and save results as Research Report.
        Automatically uploads files if not already uploaded.

        Args:
            collection_key: Collection key to process

        Returns:
            Report note key if successful, None otherwise
        """
        print(f"\n{'='*80}")
        print(f"Running Gemini File Search Query")
        print(f"Project: {self.project_name}")
        print(f"{'='*80}\n")

        # Load Gemini state
        gemini_state = self._load_gemini_state_from_config(collection_key)
        self.file_search_store_name = gemini_state['file_search_store_name']
        self.uploaded_files = gemini_state['uploaded_files']

        # Auto-upload if no store exists
        if not self.file_search_store_name:
            print(f"ℹ️  No file search store found. Creating store and uploading files...\n")

            # Upload files
            success = self.upload_files_to_gemini(collection_key)

            if not success:
                print(f"❌ File upload failed. Cannot proceed with query.")
                return None

            print(f"\n{'='*80}")
            print(f"Files uploaded successfully. Proceeding with query...")
            print(f"{'='*80}\n")
        else:
            print(f"ℹ️  Using existing file search store")
            print(f"   Store: {self.file_search_store_name}")
            print(f"   Files: {len(self.uploaded_files)}\n")

        # Load query request
        print(f"Loading query request from Zotero...")
        try:
            query_request = self.load_query_request_from_zotero(collection_key)
            print(f"✅ Query request loaded\n")
            print(f"Query preview: {query_request[:200]}...\n" if len(query_request) > 200 else f"Query: {query_request}\n")
        except (FileNotFoundError, ValueError) as e:
            print(f"❌ {e}")
            return None

        # Run Gemini query using file search store as a tool
        print(f"Running Gemini query with file search store...")
        print(f"Files available: {len(self.uploaded_files)}\n")

        try:
            # Generate response using file search store as a tool
            print(f"Generating response (this may take a moment)...")
            response = self.genai_client.models.generate_content(
                model='gemini-2.5-pro-latest',
                contents=query_request,
                config=self.genai_types.GenerateContentConfig(
                    tools=[
                        self.genai_types.Tool(
                            file_search={'file_search_store_names': [self.file_search_store_name]}
                        )
                    ]
                )
            )

            # Extract response text
            response_text = response.text if hasattr(response, 'text') else str(response)

            # Extract grounding sources if available
            sources = []
            if hasattr(response, 'candidates') and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if hasattr(candidate, 'grounding_metadata'):
                    grounding = candidate.grounding_metadata
                    if hasattr(grounding, 'grounding_chunks'):
                        sources = {
                            chunk.retrieved_context.title
                            for chunk in grounding.grounding_chunks
                            if hasattr(chunk, 'retrieved_context') and hasattr(chunk.retrieved_context, 'title')
                        }
                        if sources:
                            print(f"📚 Grounding sources: {', '.join(sources)}\n")

            print(f"✅ Query completed\n")
            print(f"Response preview: {response_text[:500]}...\n" if len(response_text) > 500 else f"Response: {response_text}\n")

        except Exception as e:
            print(f"❌ Error running Gemini query: {e}")
            import traceback
            traceback.print_exc()
            return None

        # Create Research Report note
        print(f"Creating Research Report note in Zotero...")

        # Get subcollection
        subcollection_key = self.get_subcollection(collection_key, self._get_subcollection_name())

        # Count existing reports to generate report number
        notes = self.get_collection_notes(subcollection_key)
        report_count = sum(1 for note in notes if '【Research Report #' in self.get_note_title_from_html(note['data']['note']))
        report_number = report_count + 1

        # Format report
        report_title = self._get_research_report_note_title(report_number)

        sources_section = ""
        if sources:
            sources_list = "\n".join([f"- {source}" for source in sorted(sources)])
            sources_section = f"""

## Grounding Sources

{sources_list}

---
"""

        report_content = f"""# {report_title}

**Project:** {self.project_name}
**Query Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Files Searched:** {len(self.uploaded_files)}

---

## Query Request

{query_request}

---

## Results

{response_text}
{sources_section}

---

*Generated by ZoteroResearcher File Search (Google Gemini)*
"""

        # Create note
        try:
            note_key = self.create_standalone_note(
                subcollection_key,
                report_content,
                report_title,
                convert_markdown=True
            )

            if note_key:
                print(f"✅ Research Report created: {report_title}")
                print(f"   Note key: {note_key}\n")
                print(f"{'='*80}\n")
                return note_key
            else:
                print(f"❌ Failed to create Research Report note\n")
                return None

        except Exception as e:
            print(f"❌ Error creating note: {e}")
            return None
