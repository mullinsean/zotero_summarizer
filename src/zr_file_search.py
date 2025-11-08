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
            self.genai_client = genai.Client(api_key=gemini_api_key)
            self.genai_types = types
        except ImportError:
            raise ImportError(
                "google-generativeai package not found. "
                "Install it with: pip install google-generativeai"
            )

        # Gemini File Search state
        self.file_search_store_name = None
        self.uploaded_files = {}  # Map of item_key -> document_name

    def _get_research_report_note_title(self, report_number: int = 1) -> str:
        """Get project-specific research report note title."""
        if not self.project_name:
            raise ValueError("Project name is required but not set")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"【Research Report #{report_number}: {timestamp}】"

    def _load_gemini_state_from_config(self, collection_key: str) -> Dict:
        """
        Load Gemini file upload state from Project Config.

        Args:
            collection_key: Parent collection key

        Returns:
            Dict with gemini_file_search_store_name and gemini_uploaded_files
        """
        try:
            config = self.load_project_config_from_zotero(collection_key)

            # Extract Gemini-specific state
            gemini_state = {
                'file_search_store_name': config.get('gemini_file_search_store_name', ''),
                'uploaded_files': {}
            }

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
            return {'file_search_store_name': '', 'uploaded_files': {}}

    def _save_gemini_state_to_config(self, collection_key: str):
        """
        Save Gemini file upload state to Project Config note.

        Args:
            collection_key: Parent collection key
        """
        subcollection_name = self._get_subcollection_name()
        note_title = self._get_project_config_note_title()

        # Get project-specific subcollection
        subcollection_key = self.get_subcollection(collection_key, subcollection_name)
        if not subcollection_key:
            raise FileNotFoundError(
                f"{subcollection_name} subcollection not found. "
                f"Run --init-collection --project \"{self.project_name}\" first."
            )

        # Get config note
        notes = self.get_collection_notes(subcollection_key)
        config_note = None

        for note in notes:
            title = self.get_note_title_from_html(note['data']['note'])
            if note_title in title:
                config_note = note
                break

        if not config_note:
            raise FileNotFoundError(
                f"{note_title} not found in {subcollection_name} subcollection."
            )

        # Extract existing content
        content = self.extract_text_from_note_html(config_note['data']['note'])

        # Update or add Gemini state lines
        lines = content.split('\n')
        new_lines = []
        found_corpus = False
        found_files = False

        for line in lines:
            if line.strip().startswith('gemini_file_search_store_name='):
                new_lines.append(f"gemini_file_search_store_name={self.file_search_store_name}")
                found_corpus = True
            elif line.strip().startswith('gemini_uploaded_files='):
                uploaded_files_json = json.dumps(self.uploaded_files)
                new_lines.append(f"gemini_uploaded_files={uploaded_files_json}")
                found_files = True
            else:
                new_lines.append(line)

        # Add new entries if not found
        if not found_corpus:
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
                new_lines.insert(insert_idx + 2, '# Gemini File Search State (managed automatically)')
                new_lines.insert(insert_idx + 3, '# ============================================================')
                new_lines.insert(insert_idx + 4, f'gemini_file_search_store_name={self.file_search_store_name}')
                insert_idx += 5
            else:
                new_lines.insert(insert_idx, f'gemini_file_search_store_name={self.file_search_store_name}')
                insert_idx += 1

            if not found_files:
                uploaded_files_json = json.dumps(self.uploaded_files)
                new_lines.insert(insert_idx, f'gemini_uploaded_files={uploaded_files_json}')

        elif not found_files:
            # Add files entry after file search store
            for i, line in enumerate(new_lines):
                if line.strip().startswith('gemini_file_search_store_name='):
                    uploaded_files_json = json.dumps(self.uploaded_files)
                    new_lines.insert(i + 1, f'gemini_uploaded_files={uploaded_files_json}')
                    break

        # Update note content
        updated_content = '\n'.join(new_lines)

        # Wrap in code block to preserve formatting
        updated_html = self.markdown_to_html(f"```\n{updated_content}\n```")

        # Update the note
        config_note['data']['note'] = updated_html
        self.zot.update_item(config_note)

        if self.verbose:
            print(f"  ✅ Updated Gemini state in {note_title}")

    def upload_files_to_gemini(self, collection_key: str) -> bool:
        """
        Upload all compatible sources from collection to Google Gemini File Search.

        Args:
            collection_key: Collection key to process

        Returns:
            True if upload successful
        """
        print(f"\n{'='*80}")
        print(f"Uploading Files to Google Gemini File Search")
        print(f"Project: {self.project_name}")
        print(f"{'='*80}\n")

        # Load existing Gemini state
        gemini_state = self._load_gemini_state_from_config(collection_key)
        self.file_search_store_name = gemini_state['file_search_store_name']
        self.uploaded_files = gemini_state['uploaded_files']

        # Create or get file search store
        if not self.file_search_store_name or self.force_rebuild:
            store_display_name = f"zotero_{self.project_name.replace(' ', '_')}_{int(time.time())}"

            try:
                # Create a new file search store
                file_search_store = self.genai_client.file_search_stores.create(
                    config={'display_name': store_display_name}
                )
                self.file_search_store_name = file_search_store.name
                self.uploaded_files = {}  # Reset on new store

                print(f"✅ Created new Gemini file search store: {store_display_name}")
                print(f"   Store name: {self.file_search_store_name}\n")
            except Exception as e:
                print(f"❌ Error creating Gemini file search store: {e}")
                import traceback
                traceback.print_exc()
                return False
        else:
            print(f"ℹ️  Using existing Gemini file search store: {self.file_search_store_name}")
            print(f"   {len(self.uploaded_files)} files already uploaded\n")

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
                    print(f"  ☁️  Uploading to Gemini...")

                    # Upload and import file into file search store
                    operation = self.genai_client.file_search_stores.upload_to_file_search_store(
                        file=temp_path,
                        file_search_store_name=self.file_search_store_name,
                        config={
                            'display_name': f"{item_title} - {attachment_title}"
                        }
                    )

                    # Wait for upload to complete
                    print(f"  ⏳ Processing...")
                    max_wait = 60  # Max 60 seconds
                    waited = 0
                    while not operation.done and waited < max_wait:
                        time.sleep(2)
                        waited += 2
                        operation = self.genai_client.operations.get(operation.name)

                    if not operation.done:
                        print(f"  ⚠️  Upload timed out after {max_wait}s, may still be processing")

                    # Track uploaded file
                    self.uploaded_files[item_key] = operation.name
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
        print(f"  Uploaded: {uploaded_count}")
        print(f"  Skipped: {skipped_count}")
        print(f"  Errors: {error_count}")
        print(f"  Total in corpus: {len(self.uploaded_files)}")
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
        subcollection_name = self._get_subcollection_name()
        note_title = self._get_query_request_note_title()

        # Get project-specific subcollection
        subcollection_key = self.get_subcollection(collection_key, subcollection_name)
        if not subcollection_key:
            raise FileNotFoundError(
                f"{subcollection_name} subcollection not found. "
                f"Run --init-collection --project \"{self.project_name}\" first."
            )

        # Get all notes in subcollection
        notes = self.get_collection_notes(subcollection_key)

        for note in notes:
            title = self.get_note_title_from_html(note['data']['note'])
            if note_title in title:
                content = self.extract_text_from_note_html(note['data']['note'])

                # Check if still template
                if '[TODO:' in content:
                    raise ValueError(
                        f"{note_title} still contains template. "
                        "Please edit the note in Zotero before running file search."
                    )

                # Remove template footer if present
                if '---' in content:
                    content = content.split('---')[0]

                # Remove title line
                lines = content.split('\n')
                if lines and note_title in lines[0]:
                    content = '\n'.join(lines[1:])

                return content.strip()

        raise FileNotFoundError(
            f"{note_title} not found in {subcollection_name} subcollection. "
            f"Please create this note in Zotero with your query."
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

        # Auto-upload if no file search store or no files uploaded
        if not self.file_search_store_name or not self.uploaded_files:
            print(f"ℹ️  No files uploaded yet. Uploading collection to Gemini...\n")

            # Upload files
            success = self.upload_files_to_gemini(collection_key)

            if not success:
                print(f"❌ File upload failed. Cannot proceed with query.")
                return None

            print(f"\n{'='*80}")
            print(f"Files uploaded successfully. Proceeding with query...")
            print(f"{'='*80}\n")
        else:
            print(f"ℹ️  Using existing Gemini file search store: {self.file_search_store_name}")
            print(f"   Files in store: {len(self.uploaded_files)}\n")

        # Load query request
        print(f"Loading query request from Zotero...")
        try:
            query_request = self.load_query_request_from_zotero(collection_key)
            print(f"✅ Query request loaded\n")
            print(f"Query preview: {query_request[:200]}...\n" if len(query_request) > 200 else f"Query: {query_request}\n")
        except (FileNotFoundError, ValueError) as e:
            print(f"❌ {e}")
            return None

        # Run Gemini File Search query
        print(f"Running Gemini File Search query...")

        try:
            # Query using File Search tool
            response = self.genai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=query_request,
                config=self.genai_types.GenerateContentConfig(
                    tools=[
                        self.genai_types.Tool(
                            file_search=self.genai_types.FileSearch(
                                file_search_store_names=[self.file_search_store_name]
                            )
                        )
                    ]
                )
            )

            # Extract response text
            response_text = response.text if hasattr(response, 'text') else str(response)

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
