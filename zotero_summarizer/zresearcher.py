#!/usr/bin/env python3
"""
Zotero Researcher

This script performs sophisticated research tasks on a Zotero collection.
It evaluates sources based on relevance to a research brief, ranks them,
and generates targeted summaries with key quotes and statistics.
"""

import os
import io
import time
from typing import Optional, Dict, List, Tuple
from datetime import datetime
import fitz  # PyMuPDF
import trafilatura
import requests
import markdown
from anthropic import Anthropic

# Import prompt templates - handle both relative and absolute imports
try:
    from . import zr_prompts
    from .zr_llm_client import ZRLLMClient
except ImportError:
    import zr_prompts
    from zr_llm_client import ZRLLMClient

# Handle both relative and absolute imports
try:
    from .zotero_base import ZoteroBaseProcessor
except ImportError:
    from zotero_base import ZoteroBaseProcessor


def validate_project_name(name: str) -> str:
    """
    Validate and sanitize project name.

    Args:
        name: Raw project name from user

    Returns:
        Validated project name

    Raises:
        ValueError: If project name is invalid
    """
    if not name:
        raise ValueError("Project name cannot be empty")

    name = name.strip()

    if not name:
        raise ValueError("Project name cannot be empty or whitespace only")

    if len(name) > 50:
        raise ValueError(f"Project name too long: '{name}' (max 50 characters)")

    # Check for problematic characters
    # Zotero handles most characters fine, but let's be cautious with special chars
    problematic_chars = ['【', '】', '\n', '\r', '\t']
    for char in problematic_chars:
        if char in name:
            raise ValueError(f"Project name contains invalid character: '{char}'")

    return name


class ZoteroResearcher(ZoteroBaseProcessor):
    """Research assistant for analyzing Zotero collections based on research briefs."""

    # Content truncation limits for LLM processing
    GENERAL_SUMMARY_CHAR_LIMIT = 50000   # Phase 1: General summaries
    TARGETED_SUMMARY_CHAR_LIMIT = 100000  # Phase 2: Targeted summaries

    def __init__(
        self,
        library_id: str,
        library_type: str,
        api_key: str,
        anthropic_api_key: str,
        project_name: str = None,
        research_brief: str = "",
        project_overview: str = "",
        tags: List[str] = None,
        relevance_threshold: int = 6,
        max_sources: int = 50,
        use_sonnet: bool = False,
        force_rebuild: bool = False,
        max_workers: int = 20,
        rate_limit_delay: float = 0.1,
        verbose: bool = False
    ):
        """
        Initialize the Zotero researcher.

        Args:
            library_id: Your Zotero user ID or group ID
            library_type: 'user' or 'group'
            api_key: Your Zotero API key
            anthropic_api_key: Anthropic API key for Claude
            project_name: Name of the research project (used for organizing subcollections and notes)
            research_brief: The research brief/question text (for query phase)
            project_overview: The project overview text (for build phase)
            tags: List of tags for categorization (for build phase)
            relevance_threshold: Minimum relevance score (0-10) to include source (default: 6)
            max_sources: Maximum number of sources to process (default: 50)
            use_sonnet: If True, use Sonnet for detailed summaries (higher quality, higher cost) (default: False)
            force_rebuild: If True, force rebuild of existing general summaries (default: False)
            max_workers: Number of concurrent threads for parallel LLM calls (default: 10)
            rate_limit_delay: Delay in seconds between parallel request submissions (default: 0.1)
            verbose: If True, show detailed information about all child items
        """
        # Initialize base class
        super().__init__(library_id, library_type, api_key, verbose)

        # Validate and store project name
        self.project_name = validate_project_name(project_name) if project_name else None

        # Researcher-specific configuration
        self.anthropic_client = Anthropic(api_key=anthropic_api_key)
        self.research_brief = research_brief
        self.project_overview = project_overview
        self.tags = tags or []
        self.relevance_threshold = relevance_threshold
        self.max_sources = max_sources
        self.use_sonnet = use_sonnet
        self.force_rebuild = force_rebuild
        self.max_workers = max_workers
        self.rate_limit_delay = rate_limit_delay

        # Use Haiku for quick tasks (relevance, general summaries)
        self.haiku_model = "claude-haiku-4-5-20251001"
        # Sonnet for production-quality detailed analysis
        self.sonnet_model = "claude-sonnet-4-5-20250929"

        # Default to Haiku for detailed summaries (cost-efficient)
        # Use Sonnet only when use_sonnet=True (production mode)
        self.summary_model = self.sonnet_model if use_sonnet else self.haiku_model

        # Initialize centralized LLM client for all API calls
        self.llm_client = ZRLLMClient(
            anthropic_client=self.anthropic_client,
            default_model=self.haiku_model,
            verbose=verbose
        )

    def _get_subcollection_name(self) -> str:
        """Get project-specific subcollection name."""
        if not self.project_name:
            raise ValueError("Project name is required but not set")
        return f"【ZResearcher: {self.project_name}】"

    def _get_project_overview_note_title(self) -> str:
        """Get project-specific overview note title."""
        if not self.project_name:
            raise ValueError("Project name is required but not set")
        return f"【Project Overview: {self.project_name}】"

    def _get_research_tags_note_title(self) -> str:
        """Get project-specific tags note title."""
        if not self.project_name:
            raise ValueError("Project name is required but not set")
        return f"【Research Tags: {self.project_name}】"

    def _get_research_brief_note_title(self) -> str:
        """Get project-specific brief note title."""
        if not self.project_name:
            raise ValueError("Project name is required but not set")
        return f"【Research Brief: {self.project_name}】"

    def _get_summary_note_prefix(self) -> str:
        """Get project-specific summary note prefix (used as note title/heading)."""
        if not self.project_name:
            raise ValueError("Project name is required but not set")
        return f"【ZResearcher Summary: {self.project_name}】"

    def load_research_brief(self, brief_file: str) -> str:
        """
        Load research brief from a text file.

        Args:
            brief_file: Path to the research brief file

        Returns:
            Research brief text

        Raises:
            FileNotFoundError: If brief file doesn't exist
        """
        if not os.path.exists(brief_file):
            raise FileNotFoundError(f"Research brief file not found: {brief_file}")

        with open(brief_file, 'r', encoding='utf-8') as f:
            brief_text = f.read().strip()

        if not brief_text:
            raise ValueError(f"Research brief file is empty: {brief_file}")

        return brief_text

    def load_project_overview(self, overview_file: str) -> str:
        """
        Load project overview from a text file.

        Args:
            overview_file: Path to the project overview file

        Returns:
            Project overview text

        Raises:
            FileNotFoundError: If overview file doesn't exist
        """
        if not os.path.exists(overview_file):
            raise FileNotFoundError(f"Project overview file not found: {overview_file}")

        with open(overview_file, 'r', encoding='utf-8') as f:
            overview_text = f.read().strip()

        if not overview_text:
            raise ValueError(f"Project overview file is empty: {overview_file}")

        return overview_text

    def load_tags(self, tags_file: str) -> List[str]:
        """
        Load tags from a text file (one tag per line).

        Args:
            tags_file: Path to the tags file

        Returns:
            List of tags

        Raises:
            FileNotFoundError: If tags file doesn't exist
        """
        if not os.path.exists(tags_file):
            raise FileNotFoundError(f"Tags file not found: {tags_file}")

        with open(tags_file, 'r', encoding='utf-8') as f:
            tags = [line.strip() for line in f if line.strip()]

        if not tags:
            raise ValueError(f"Tags file is empty or has no valid tags: {tags_file}")

        return tags

    def extract_metadata(self, item: Dict) -> Dict:
        """
        Extract metadata from a Zotero item.

        Args:
            item: The Zotero item

        Returns:
            Dict with metadata fields (title, authors, date, publication, url, itemType)
        """
        item_data = item['data']

        # Extract basic fields
        metadata = {
            'title': item_data.get('title', 'Untitled'),
            'date': item_data.get('date', 'Unknown date'),
            'publication': item_data.get('publicationTitle', item_data.get('bookTitle', '')),
            'url': item_data.get('url', ''),
            'itemType': item_data.get('itemType', 'unknown')
        }

        # Extract authors/creators
        creators = item_data.get('creators', [])
        if creators:
            authors = []
            for creator in creators:
                if 'lastName' in creator:
                    if 'firstName' in creator:
                        authors.append(f"{creator['firstName']} {creator['lastName']}")
                    else:
                        authors.append(creator['lastName'])
                elif 'name' in creator:
                    authors.append(creator['name'])
            metadata['authors'] = ', '.join(authors) if authors else 'Unknown author'
        else:
            metadata['authors'] = 'Unknown author'

        return metadata

    def extract_text_from_html(self, html_content: bytes, attachment_url: Optional[str] = None) -> Optional[str]:
        """
        Extract text from HTML content using Trafilatura.
        Reused from summarize_sources.py.

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
        Reused from summarize_sources.py.

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

    def get_source_content(self, item: Dict) -> Tuple[Optional[str], Optional[str]]:
        """
        Get content from a source using priority order:
        1. Existing "Markdown Extract" note
        2. HTML snapshot (Trafilatura)
        3. PDF attachment (PyMuPDF)
        4. URL fetch (for webpage items)

        Args:
            item: The Zotero item

        Returns:
            Tuple of (content_text, content_type) or (None, None) if extraction fails
        """
        item_key = item['key']
        item_data = item['data']
        item_title = item_data.get('title', 'Untitled')

        # Priority 1: Check for existing Markdown Extract note
        if self.has_note_with_prefix(item_key, 'Markdown Extract:'):
            print(f"  📝 Found existing Markdown Extract note")
            markdown_note = self.get_note_with_prefix(item_key, 'Markdown Extract:')
            if markdown_note:
                # Strip HTML tags if present (notes are stored as HTML)
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(markdown_note, 'html.parser')
                text_content = soup.get_text()
                return text_content.strip(), "Markdown Extract"

        # Get attachments
        attachments = self.get_item_attachments(item_key)

        if attachments:
            # Priority 2: Try HTML attachment
            for attachment in attachments:
                if self.is_html_attachment(attachment):
                    attachment_title = attachment['data'].get('title', 'Untitled')
                    attachment_key = attachment['key']
                    attachment_url = attachment['data'].get('url')

                    print(f"  📄 Found HTML attachment: {attachment_title}")
                    print(f"  📥 Downloading and extracting...")

                    html_content = self.download_attachment(attachment_key)
                    if html_content:
                        extracted = self.extract_text_from_html(html_content, attachment_url)
                        if extracted:
                            return extracted, "HTML"

            # Priority 3: Try PDF attachment
            for attachment in attachments:
                if self.is_pdf_attachment(attachment):
                    attachment_title = attachment['data'].get('title', 'Untitled')
                    attachment_key = attachment['key']

                    print(f"  📄 Found PDF attachment: {attachment_title}")
                    print(f"  📥 Downloading and extracting...")

                    pdf_content = self.download_attachment(attachment_key)
                    if pdf_content:
                        extracted = self.extract_text_from_pdf(pdf_content)
                        if extracted:
                            return extracted, "PDF"

        # Priority 4: Try fetching from URL (for webpage items)
        item_url = item_data.get('url')
        if item_url and item_data.get('itemType') == 'webpage':
            print(f"  🌐 Fetching from URL: {item_url}")
            try:
                response = requests.get(item_url, timeout=30)
                response.raise_for_status()
                markdown = trafilatura.extract(
                    response.text,
                    output_format='markdown',
                    include_links=True,
                    include_images=False,
                    include_tables=True
                )
                if markdown:
                    return markdown.strip(), "URL"
            except Exception as e:
                print(f"  ❌ Error fetching URL: {e}")

        return None, None

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

    def create_general_summary_with_tags(
        self,
        item_key: str,
        content: str,
        metadata: Dict
    ) -> Optional[Dict]:
        """
        Create a general summary with metadata, tags, and document type.

        Args:
            item_key: The key of the item
            content: The source content to summarize
            metadata: Metadata dict

        Returns:
            Dict with 'summary', 'tags', 'document_type' keys, or None if generation fails
        """
        try:
            # Build tags list for prompt
            tags_list = '\n'.join([f"- {tag}" for tag in self.tags])

            # Use Haiku for cost-efficient general summaries
            truncated = len(content) > self.GENERAL_SUMMARY_CHAR_LIMIT
            prompt = zr_prompts.general_summary_prompt(
                project_overview=self.project_overview,
                tags_list=tags_list,
                title=metadata.get('title', 'Untitled'),
                authors=metadata.get('authors', 'Unknown'),
                date=metadata.get('date', 'Unknown'),
                content=content[:self.GENERAL_SUMMARY_CHAR_LIMIT],
                truncated=truncated,
                char_limit=self.GENERAL_SUMMARY_CHAR_LIMIT
            )

            response = self.anthropic_client.messages.create(
                model=self.haiku_model,
                max_tokens=2048,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            if response.content and len(response.content) > 0:
                llm_response = response.content[0].text.strip()

                # Parse LLM response
                import re
                summary_match = re.search(r'SUMMARY:\s*(.+?)\s*TAGS:', llm_response, re.DOTALL)
                tags_match = re.search(r'TAGS:\s*(.+?)\s*DOCUMENT_TYPE:', llm_response, re.DOTALL)
                doctype_match = re.search(r'DOCUMENT_TYPE:\s*(.+?)$', llm_response, re.DOTALL)

                summary = summary_match.group(1).strip() if summary_match else "Summary not available"
                tags_str = tags_match.group(1).strip() if tags_match else ""
                document_type = doctype_match.group(1).strip() if doctype_match else "Unknown"

                # Parse tags (comma-separated)
                assigned_tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]

                # Format and save structured note
                note_content = self.format_general_summary_note(
                    metadata,
                    assigned_tags,
                    summary,
                    document_type
                )

                note_title = f"【ZResearcher Summary】 {metadata.get('title', 'Untitled')}"
                if self.create_note(item_key, note_content, note_title, convert_markdown=True):
                    return {
                        'summary': summary,
                        'tags': assigned_tags,
                        'document_type': document_type
                    }
                else:
                    print(f"  ⚠️  Failed to save general summary note")
                    # Still return the data even if save failed
                    return {
                        'summary': summary,
                        'tags': assigned_tags,
                        'document_type': document_type
                    }

            return None

        except Exception as e:
            print(f"  ❌ Error creating general summary: {e}")
            return None

    def evaluate_source_relevance(
        self,
        summary: str,
        metadata: Dict,
        tags: List[str]
    ) -> Optional[int]:
        """
        Evaluate how relevant a source is to the research brief.

        Args:
            summary: The source summary
            metadata: Metadata dict (title, authors, date, type, etc.)
            tags: List of assigned tags

        Returns:
            Relevance score (0-10), or None if evaluation fails
        """
        try:
            # Format tags for display
            tags_str = ', '.join(tags) if tags else 'None'

            # Use Haiku for fast, cheap relevance scoring
            prompt = zr_prompts.relevance_evaluation_prompt(
                research_brief=self.research_brief,
                title=metadata.get('title', 'Untitled'),
                authors=metadata.get('authors', 'Unknown'),
                date=metadata.get('date', 'Unknown'),
                doc_type=metadata.get('type', 'Unknown'),
                tags=tags_str,
                summary=summary[:10000]
            )

            response = self.anthropic_client.messages.create(
                model=self.haiku_model,
                max_tokens=10,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            if response.content and len(response.content) > 0:
                score_text = response.content[0].text.strip()

                # Try to extract number from response (handle various formats)
                import re
                # Try matching just a number first
                match = re.search(r'^(\d+)$', score_text)
                if not match:
                    # Try finding any number in the text
                    match = re.search(r'\b(\d+)\b', score_text)

                if match:
                    score = int(match.group(1))
                    # Clamp to 0-10 range
                    score = max(0, min(10, score))
                    return score
                else:
                    if self.verbose:
                        print(f"  ⚠️  Could not parse score from response: '{score_text[:100]}'")
                    else:
                        print(f"  ⚠️  Could not parse relevance score from LLM response")
                    return None

            print(f"  ⚠️  Empty response from LLM")
            return None

        except Exception as e:
            print(f"  ❌ Error evaluating relevance: {e}")
            return None

    def rank_sources(self, sources_with_scores: List[Dict]) -> List[Dict]:
        """
        Sort sources by relevance score (descending).

        Args:
            sources_with_scores: List of dicts with 'item', 'score', and 'content' keys

        Returns:
            Sorted list (highest relevance first)
        """
        return sorted(sources_with_scores, key=lambda x: x['score'], reverse=True)

    def generate_targeted_summary(self, item: Dict, content: str, content_type: str) -> Optional[Dict]:
        """
        Generate a detailed research summary with quotes and relevance explanation.

        Args:
            item: The Zotero item
            content: The source content
            content_type: Type of content (HTML, PDF, etc.)

        Returns:
            Dict with 'summary', 'relevance_explanation', and 'quotes' keys, or None if fails
        """
        try:
            item_title = item['data'].get('title', 'Untitled')
            truncated = len(content) > self.TARGETED_SUMMARY_CHAR_LIMIT

            # Use configured model (Haiku by default, Sonnet for production)
            prompt = zr_prompts.targeted_summary_prompt(
                research_brief=self.research_brief,
                title=item_title,
                content_type=content_type,
                content=content[:self.TARGETED_SUMMARY_CHAR_LIMIT],
                truncated=truncated,
                char_limit=self.TARGETED_SUMMARY_CHAR_LIMIT
            )

            response = self.anthropic_client.messages.create(
                model=self.summary_model,
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            if response.content and len(response.content) > 0:
                full_response = response.content[0].text.strip()

                return {
                    'summary': full_response,
                    'full_text': full_response  # Store full formatted response
                }

            return None

        except Exception as e:
            print(f"  ❌ Error generating targeted summary: {e}")
            return None

    def build_general_summaries(self, collection_key: str) -> None:
        """
        Phase 1: Build general summaries for all sources in a collection.

        Supports two modes:
        - File-based: project_overview and tags already loaded from files
        - Zotero-native: loads project_overview and tags from Zotero subcollection

        Args:
            collection_key: The Zotero collection key to process
        """
        start_time = time.time()

        # Detect mode: if project_overview and tags are empty, try loading from Zotero
        if not self.project_overview and not self.tags:
            print(f"\n📋 No project overview or tags provided via files")
            print(f"   Attempting to load from {self._get_subcollection_name()} subcollection...\n")

            try:
                self.project_overview = self.load_project_overview_from_zotero(collection_key)
                print(f"✅ Loaded project overview from Zotero ({len(self.project_overview)} characters)")

                self.tags = self.load_tags_from_zotero(collection_key)
                print(f"✅ Loaded {len(self.tags)} tags from Zotero")
                print(f"   Tags: {', '.join(self.tags[:5])}{', ...' if len(self.tags) > 5 else ''}\n")

            except (FileNotFoundError, ValueError) as e:
                print(f"❌ Error loading configuration from Zotero: {e}")
                print(f"\nOptions:")
                print(f"   1. Run --init-collection first to create configuration notes")
                print(f"   2. Provide files: --project-overview FILE --tags FILE\n")
                return

        # Validate configuration
        if not self.project_overview or not self.tags:
            print(f"❌ Missing configuration:")
            if not self.project_overview:
                print(f"   - Project overview required")
            if not self.tags:
                print(f"   - Tags required")
            print(f"\nProvide via files (--project-overview, --tags) or Zotero notes (--init-collection)")
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

    def compile_research_html(
        self,
        collection_key: str,
        relevant_sources: List[Dict],
        stats: Dict
    ) -> str:
        """
        Compile all research results into an HTML document with linked TOC.

        Args:
            collection_key: The collection key
            relevant_sources: List of dicts with source data and summaries
            stats: Statistics dict with processing info

        Returns:
            Filename of the generated HTML file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"research_report_{collection_key}_{timestamp}.html"

        # Build HTML document
        html_parts = []

        # HTML header with styles (adapted from summarize_sources.py)
        html_parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Research Report</title>
    <style>
        body {
            font-family: Georgia, serif;
            line-height: 1.6;
            max-width: 900px;
            margin: 40px auto;
            padding: 0 20px;
            background-color: #f5f5f5;
            color: #333;
        }
        .header {
            background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
            color: white;
            padding: 40px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .header h1 {
            margin: 0 0 15px 0;
            font-size: 2.5em;
        }
        .header .meta {
            opacity: 0.9;
            font-size: 14px;
            line-height: 1.8;
        }
        .research-brief {
            background-color: white;
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
        .research-brief .brief-text {
            font-style: italic;
            color: #555;
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
            white-space: pre-wrap;
        }
        .toc {
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .toc h2 {
            margin-top: 0;
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }
        .toc ol {
            line-height: 2.2;
        }
        .toc a {
            color: #3498db;
            text-decoration: none;
            font-weight: 500;
        }
        .toc a:hover {
            text-decoration: underline;
        }
        .toc .relevance-score {
            display: inline-block;
            background-color: #3498db;
            color: white;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.9em;
            margin-left: 10px;
            font-weight: bold;
        }
        .toc .relevance-score.high {
            background-color: #27ae60;
        }
        .toc .relevance-score.medium {
            background-color: #f39c12;
        }
        .source {
            background-color: white;
            padding: 35px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border-left: 5px solid #3498db;
        }
        .source h3 {
            color: #2c3e50;
            font-size: 1.8em;
            margin-top: 0;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }
        .source .metadata {
            color: #7f8c8d;
            font-size: 0.9em;
            margin-bottom: 20px;
            padding: 15px;
            background-color: #f8f9fa;
            border-radius: 5px;
        }
        .source .metadata strong {
            color: #2c3e50;
        }
        .tag-badge {
            display: inline-block;
            background-color: #3498db;
            color: white;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 0.85em;
            margin-right: 6px;
            margin-bottom: 4px;
            font-weight: 500;
        }
        .source .content-section {
            margin-top: 25px;
        }
        .source .content-section h1,
        .source .content-section h2,
        .source .content-section h3,
        .source .content-section h4 {
            color: #34495e;
            border-left: 4px solid #3498db;
            padding-left: 15px;
            margin-top: 30px;
            margin-bottom: 15px;
        }
        .source .content-section h1 { font-size: 1.5em; }
        .source .content-section h2 { font-size: 1.3em; }
        .source .content-section h3 { font-size: 1.15em; }
        .source .content-section h4 { font-size: 1em; }
        .source .content-section p {
            margin: 15px 0;
            line-height: 1.8;
        }
        .source .content-section ul,
        .source .content-section ol {
            margin: 15px 0;
            padding-left: 30px;
            line-height: 1.8;
        }
        .source .content-section li {
            margin: 8px 0;
        }
        .source .content-section blockquote {
            background: #f0f8ff;
            border-left: 4px solid #3498db;
            padding: 15px 20px;
            margin: 20px 0;
            font-style: italic;
        }
        .source .content-section code {
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }
        .source .content-section pre {
            background: #f4f4f4;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            margin: 20px 0;
        }
        .source .content-section pre code {
            background: none;
            padding: 0;
        }
        .source .content-section strong {
            color: #2c3e50;
            font-weight: 600;
        }
        .source .content-section em {
            font-style: italic;
        }
        .source .content-section a {
            color: #3498db;
            text-decoration: none;
        }
        .source .content-section a:hover {
            text-decoration: underline;
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
        <h1>🔬 Research Report</h1>
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
        <h2>📋 Research Brief</h2>
        <div class="brief-text">{self.research_brief}</div>
    </div>
""")

        # Table of Contents
        html_parts.append("""
    <div class="toc">
        <h2>📑 Table of Contents</h2>
        <ol>
""")

        for idx, source_data in enumerate(relevant_sources, 1):
            item_title = source_data['item']['data'].get('title', 'Untitled')
            score = source_data['score']
            anchor = f"source-{idx}"

            # Color-code relevance scores
            score_class = "high" if score >= 8 else ("medium" if score >= 6 else "")

            html_parts.append(
                f'            <li><a href="#{anchor}">{item_title}</a>'
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
        <h2>📊 Research Statistics</h2>
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

        # Write file
        full_html = ''.join(html_parts)

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(full_html)
            print(f"\n  ✅ Research report saved to: {filename}")
            return filename
        except Exception as e:
            print(f"\n  ❌ Error saving research report: {e}")
            return ""

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
        subcollection_name = self._get_subcollection_name()
        note_title = self._get_project_overview_note_title()

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
                        "Please edit the note in Zotero before building summaries."
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
            f"Run --init-collection --project \"{self.project_name}\" first."
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
        subcollection_name = self._get_subcollection_name()
        note_title = self._get_research_tags_note_title()

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
                        "Please edit the note in Zotero before building summaries."
                    )

                # Remove template footer if present
                if '---' in content:
                    content = content.split('---')[0]

                # Remove title line
                lines = content.split('\n')
                if lines and note_title in lines[0]:
                    lines = lines[1:]

                # Parse tags (one per line), filter empty lines
                tags = [line.strip() for line in lines if line.strip() and not line.startswith('Example')]

                if not tags:
                    raise ValueError(f"{note_title} is empty. Please add tags.")

                return tags

        raise FileNotFoundError(
            f"{note_title} not found in {subcollection_name} subcollection. "
            f"Run --init-collection --project \"{self.project_name}\" first."
        )

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
        subcollection_name = self._get_subcollection_name()
        note_title = self._get_research_brief_note_title()

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
                        "Please edit the note in Zotero before running query."
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
            f"Run --init-collection --project \"{self.project_name}\" first, then edit the {note_title} note."
        )

    def init_collection(self, collection_key: str, force: bool = False) -> bool:
        """
        Initialize a collection for use with ZoteroResearcher.

        Creates a project-specific subcollection and populates it with
        template notes for configuration.

        Args:
            collection_key: The Zotero collection key to initialize
            force: If True, recreate templates even if subcollection exists

        Returns:
            True if initialization successful
        """
        subcollection_name = self._get_subcollection_name()

        print(f"\n{'='*80}")
        print(f"Initializing Collection for Project: {self.project_name}")
        print(f"{'='*80}\n")

        # Check if subcollection already exists
        existing_key = self.get_subcollection(collection_key, subcollection_name)

        if existing_key and not force:
            print(f"⚠️  Project already initialized with {subcollection_name} subcollection")
            print(f"   Subcollection Key: {existing_key}")
            print(f"\n   Options:")
            print(f"   1. Use existing configuration (edit notes in Zotero)")
            print(f"   2. Recreate templates (run with --force flag)")
            print(f"\n   Run with --force to recreate template notes.\n")
            return False

        # Create or get subcollection
        print(f"Creating {subcollection_name} subcollection...")
        subcollection_key = self.create_subcollection(collection_key, subcollection_name)

        if not subcollection_key:
            print(f"❌ Failed to create subcollection")
            return False

        print(f"✅ Subcollection created: {subcollection_key}\n")

        # Create template notes
        print(f"Creating configuration templates...\n")

        # Template 1: Project Overview
        project_overview_content = """[TODO: Replace this template with your project description]

Describe your research project, goals, and key areas of interest.
This context will inform the general summaries created for each source.

Example:
This project examines the impact of artificial intelligence on
software development practices. Key areas include: code generation
tools, automated testing, productivity metrics, and ethical
considerations. The research will inform a technical report for
software engineering managers.

---
Template created by ZoteroResearcher
Edit this note before running --build-summaries"""

        overview_key = self.create_standalone_note(
            subcollection_key,
            project_overview_content,
            self._get_project_overview_note_title(),
            convert_markdown=True
        )

        if overview_key:
            print(f"   ✅ Created: {self._get_project_overview_note_title()}")
        else:
            print(f"   ❌ Failed to create: {self._get_project_overview_note_title()}")

        # Template 2: Research Tags
        research_tags_content = """[TODO: Replace this template with your tag list]

List one tag per line. These tags will be assigned to sources
during summary building to categorize them by topic/theme.

Example tags:
AI Code Generation
Automated Testing
Developer Productivity
Code Quality
Ethics
GitHub Copilot
Empirical Studies
Case Studies

---
Template created by ZoteroResearcher
Edit this note before running --build-summaries"""

        tags_key = self.create_standalone_note(
            subcollection_key,
            research_tags_content,
            self._get_research_tags_note_title(),
            convert_markdown=True
        )

        if tags_key:
            print(f"   ✅ Created: {self._get_research_tags_note_title()}")
        else:
            print(f"   ❌ Failed to create: {self._get_research_tags_note_title()}")

        # Template 3: Research Brief
        research_brief_content = """[TODO: Replace this template with your specific research question]

State your specific research question or topic. This will be used
to evaluate source relevance and generate targeted summaries.

Example:
Research Topic: Impact of AI Code Generation on Developer Productivity

I am researching how AI-assisted code generation tools (GitHub Copilot,
ChatGPT, etc.) impact developer productivity and code quality.
Specifically, I am interested in:

1. Quantitative productivity metrics (velocity, time savings)
2. Code quality impacts (bugs, maintainability)
3. Developer experience and workflow changes
4. Empirical studies with measurable results

Please focus on peer-reviewed research and industry reports
published in the last 3 years.

---
Template created by ZoteroResearcher
Edit this note before running --query-summary"""

        brief_key = self.create_standalone_note(
            subcollection_key,
            research_brief_content,
            self._get_research_brief_note_title(),
            convert_markdown=True
        )

        if brief_key:
            print(f"   ✅ Created: {self._get_research_brief_note_title()}")
        else:
            print(f"   ❌ Failed to create: {self._get_research_brief_note_title()}")

        # Final output
        print(f"\n{'='*80}")
        print(f"✅ Project Initialized Successfully")
        print(f"{'='*80}\n")
        print(f"{subcollection_name} subcollection created: {subcollection_key}\n")
        print(f"Configuration templates created:")
        print(f"   - {self._get_project_overview_note_title()} (edit before building summaries)")
        print(f"   - {self._get_research_tags_note_title()} (edit before building summaries)")
        print(f"   - {self._get_research_brief_note_title()} (edit before running queries)\n")
        print(f"Next steps:")
        print(f"   1. Open the '{subcollection_name}' subcollection in Zotero")
        print(f"   2. Edit '{self._get_project_overview_note_title()}' with your project description")
        print(f"   3. Edit '{self._get_research_tags_note_title()}' with your tag list")
        print(f"   4. Edit '{self._get_research_brief_note_title()}' with your research question")
        print(f"   5. Run: python zresearcher.py --build-summaries --collection {collection_key} --project \"{self.project_name}\"")
        print(f"{'='*80}\n")

        return True

    def list_projects(self, collection_key: str):
        """
        List all ZResearcher projects in a collection.

        Args:
            collection_key: Collection key to scan for projects
        """
        print(f"\n{'='*80}")
        print(f"ZResearcher Projects in Collection")
        print(f"{'='*80}\n")
        print(f"Scanning for project subcollections...\n")

        # Get all subcollections
        try:
            subcollections = self.zot.collections_sub(collection_key)
        except Exception as e:
            print(f"❌ Error fetching subcollections: {e}")
            return

        # Filter for ZResearcher projects
        projects = []
        for subcoll in subcollections:
            name = subcoll['data'].get('name', '')
            # Match pattern: 【ZResearcher: PROJECT_NAME】
            if name.startswith('【ZResearcher:') and name.endswith('】'):
                # Extract project name
                project_name = name[len('【ZResearcher:'):-1].strip()
                projects.append({
                    'name': project_name,
                    'subcollection_name': name,
                    'key': subcoll['key'],
                    'num_items': subcoll['meta'].get('numItems', 0)
                })

        if not projects:
            print("No ZResearcher projects found in this collection.")
            print("\nTo create a project, run:")
            print(f"  python zresearcher.py --init-collection --collection {collection_key} --project \"PROJECT_NAME\"\n")
            return

        print(f"Found {len(projects)} project(s):\n")

        for idx, project in enumerate(projects, 1):
            print(f"{idx}. {project['name']}")
            print(f"   Subcollection: {project['subcollection_name']}")
            print(f"   Key: {project['key']}")
            print(f"   Items: {project['num_items']}")

            # Check for sources with summaries
            try:
                items = self.get_collection_items(collection_key)
                summaries_count = 0
                summary_prefix = f"【ZResearcher Summary: {project['name']}】:"

                for item in items:
                    item_type = item['data'].get('itemType')
                    if item_type in ['attachment', 'note']:
                        continue
                    if self.has_note_with_prefix(item['key'], summary_prefix):
                        summaries_count += 1

                print(f"   Sources with summaries: {summaries_count}/{len([i for i in items if i['data'].get('itemType') not in ['attachment', 'note']])}")
            except Exception:
                print(f"   Sources with summaries: Unable to count")

            print()

        print(f"{'='*80}\n")

    def run_query(self, collection_key: str) -> str:
        """
        Phase 2: Query sources based on research brief using pre-built summaries.

        Args:
            collection_key: The Zotero collection key to analyze

        Returns:
            Path to the generated HTML report
        """
        start_time = time.time()

        print(f"\n{'='*80}")
        print(f"🔬 Research Query Starting")
        print(f"{'='*80}")
        print(f"Collection: {collection_key}")
        print(f"Relevance Threshold: {self.relevance_threshold}/10")
        print(f"Max Sources: {self.max_sources}")
        print(f"Summary Model: {self.summary_model} ({'Sonnet - High Quality' if self.use_sonnet else 'Haiku - Cost Efficient'})")
        print(f"{'='*80}\n")

        # Get collection items
        items = self.get_collection_items(collection_key)
        if not items:
            print("❌ No items found in collection")
            return ""

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
            if not self.has_general_summary(item_key):
                print(f"[{idx}/{len(items)}] ⚠️  {item_title} - no summary (run --build-summaries first)")
                missing_summaries += 1
                continue

            # Parse general summary note
            summary_note = self.get_note_with_prefix(item_key, self._get_summary_note_prefix())
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

        if not items_with_summaries:
            print(f"\n⚠️  No items with summaries found. Run --build-summaries first.")
            return ""

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
                match = re.search(r'^(\d+)$', response_text.strip())
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

        print(f"  📊 Sources meeting threshold ({self.relevance_threshold}/10): {len(relevant_sources)}")

        if not relevant_sources:
            print(f"\n⚠️  No sources meet the relevance threshold of {self.relevance_threshold}/10")
            if missing_summaries > 0:
                print(f"  Note: {missing_summaries} sources were missing summaries. Run --build-summaries first.")
            print(f"  Try lowering the threshold or refining your research brief")
            return ""

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
        print(f"Step 3.2: Generating summaries in parallel ({model_name}, {self.max_workers} workers)...")
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

        # Phase 4: Compile HTML report
        print(f"\n{'='*80}")
        print(f"Phase 4: Compiling Research Report")
        print(f"{'='*80}\n")

        elapsed_time = time.time() - start_time
        stats = {
            'total': len(items),
            'evaluated': evaluated,
            'relevant': len(relevant_sources),
            'missing_summaries': missing_summaries,
            'time': f"{elapsed_time:.1f} seconds"
        }

        output_file = self.compile_research_html(collection_key, relevant_sources, stats)

        # Final summary
        print(f"\n{'='*80}")
        print(f"✅ Query Complete")
        print(f"{'='*80}")
        print(f"Total sources: {stats['total']}")
        print(f"Evaluated: {stats['evaluated']}")
        print(f"Missing summaries: {stats['missing_summaries']}")
        print(f"Relevant: {stats['relevant']}")
        print(f"Processing time: {stats['time']}")
        print(f"Report: {output_file}")
        print(f"{'='*80}\n")

        return output_file

    def run_query_summary(self, collection_key: str) -> Optional[str]:
        """
        Phase 2 (Zotero-native): Query sources based on research brief from Zotero notes.

        Loads research brief from project-specific subcollection, runs query,
        and stores report as a Zotero note (or HTML file if >1MB).

        Args:
            collection_key: The Zotero collection key to analyze

        Returns:
            Note key if report stored as note, or file path if stored as HTML file
        """
        start_time = time.time()

        print(f"\n{'='*80}")
        print(f"Research Query Summary (Zotero-native mode)")
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
            print(f"   2. Edit the {self._get_research_brief_note_title()} note in {self._get_subcollection_name()}")
            print(f"   3. Use file-based mode: --query --collection KEY --project \"{self.project_name}\" --brief FILE\n")
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

        # Get collection items
        items = self.get_collection_items(collection_key)
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
            if not self.has_general_summary(item_key):
                print(f"[{idx}/{len(items)}] ⚠️  {item_title} - no summary (run --build-summaries first)")
                missing_summaries += 1
                continue

            # Parse general summary note
            summary_note = self.get_note_with_prefix(item_key, self._get_summary_note_prefix())
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
        print(f"Step 3.2: Generating summaries in parallel ({model_name}, {self.max_workers} workers)...")
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

        # Generate HTML content (but don't save to file yet)
        html_content = self._compile_research_html_string(collection_key, relevant_sources, stats)

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
                f"Research Report - {datetime.now().strftime('%Y-%m-%d')} (See File)",
                convert_markdown=True
            )

            if note_key:
                print(f"  ✅ Stub note created in {self._get_subcollection_name()}")
            else:
                print(f"  ⚠️  Failed to create stub note")

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
            print(f"{'='*80}\n")

            return output_file

        # If report <1MB, create full note in Zotero
        else:
            print(f"  Creating note in {self._get_subcollection_name()}...")

            # Extract title from research brief (first line or first 100 chars)
            brief_lines = self.research_brief.strip().split('\n')
            brief_title = brief_lines[0] if brief_lines else "Research Report"
            if len(brief_title) > 100:
                brief_title = brief_title[:97] + "..."

            note_title = f"Research Report - {datetime.now().strftime('%Y-%m-%d')}: {brief_title}"

            # Create note with HTML content directly (no markdown conversion)
            note_key = self.create_standalone_note(
                subcollection_key,
                html_content,
                note_title,
                convert_markdown=False  # Already HTML
            )

            if note_key:
                print(f"  ✅ Report note created in {self._get_subcollection_name()}")
            else:
                print(f"  ❌ Failed to create report note")
                return None

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
            print(f"{'='*80}\n")

            return note_key

    def _compile_research_html_string(self, collection_key: str, relevant_sources: List[Dict], stats: Dict) -> str:
        """
        Internal method: Generate HTML report as string (doesn't save to file).

        Args:
            collection_key: Collection key
            relevant_sources: List of relevant sources with summaries
            stats: Statistics dict

        Returns:
            HTML content as string
        """
        # Reuse existing compile_research_html logic but return string instead of saving
        html_parts = []

        # HTML header
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
        <h1>Research Report</h1>
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
                f'            <li><a href="#{anchor}">{item_title}</a>'
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


def main():
    """Main entry point."""
    import argparse
    from dotenv import load_dotenv

    # Load environment variables
    load_dotenv()

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Two-phase research assistant for Zotero collections',
        epilog="""
Examples:
  # List collections
  python zresearcher.py --list-collections

  # List projects in a collection
  python zresearcher.py --list-projects --collection KEY

  # Initialize collection for Zotero-native workflow
  python zresearcher.py --init-collection --collection KEY --project "AI Productivity"

  # Phase 1: Build general summaries (Zotero-native mode)
  python zresearcher.py --build-summaries --collection KEY --project "AI Productivity"

  # Phase 1: Build general summaries (file-based mode)
  python zresearcher.py --build-summaries --collection KEY --project "AI Productivity" \\
      --project-overview overview.txt --tags tags.txt

  # Phase 2: Query with research brief (Zotero-native mode)
  python zresearcher.py --query-summary --collection KEY --project "AI Productivity"

  # Phase 2: Query with research brief (file-based mode)
  python zresearcher.py --query --collection KEY --project "AI Productivity" --brief brief.txt

  # Rebuild all summaries for a project
  python zresearcher.py --build-summaries --collection KEY --project "AI Productivity" --force
        """
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--list-collections',
        action='store_true',
        help='List all available collections and exit'
    )
    mode_group.add_argument(
        '--list-projects',
        action='store_true',
        help='List all ZResearcher projects in a collection'
    )
    mode_group.add_argument(
        '--init-collection',
        action='store_true',
        help='Initialize collection with project-specific 【ZResearcher: PROJECT】 subcollection and templates'
    )
    mode_group.add_argument(
        '--build-summaries',
        action='store_true',
        help='Phase 1: Build general summaries with metadata and tags'
    )
    mode_group.add_argument(
        '--query-summary',
        action='store_true',
        help='Phase 2: Query sources using research brief from Zotero notes (Zotero-native mode)'
    )
    mode_group.add_argument(
        '--query',
        action='store_true',
        help='Phase 2: Query sources based on research brief from file (file-based mode, default if no mode specified)'
    )

    # Common arguments
    parser.add_argument(
        '--collection',
        type=str,
        help='Collection key to process (overrides ZOTERO_COLLECTION_KEY env var)'
    )
    parser.add_argument(
        '--project',
        type=str,
        required=False,
        help='Project name for organizing research (required for most operations). Each project has its own subcollection and configuration.'
    )
    parser.add_argument(
        '--max-sources',
        type=int,
        default=50,
        help='Maximum number of sources to process (default: 50)'
    )
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Show detailed information about all child items'
    )

    # Phase 1 (build) arguments
    parser.add_argument(
        '--project-overview',
        type=str,
        help='[Build] Path to project overview text file (file-based mode). If omitted, loads from Zotero notes (Zotero-native mode)'
    )
    parser.add_argument(
        '--tags',
        type=str,
        help='[Build] Path to tags text file (file-based mode). If omitted, loads from Zotero notes (Zotero-native mode)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='[Build] Force rebuild of existing summaries'
    )

    # Phase 2 (query) arguments
    parser.add_argument(
        '--brief',
        type=str,
        help='[Query] Path to research brief text file'
    )
    parser.add_argument(
        '--threshold',
        type=int,
        default=6,
        help='[Query] Relevance threshold 0-10 (default: 6)'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='[Query] Output HTML file path (default: auto-generated)'
    )
    parser.add_argument(
        '--use-sonnet',
        action='store_true',
        help='[Query] Use Sonnet for detailed summaries (higher quality, higher cost). Default: Haiku (cost-efficient)'
    )

    # Performance tuning arguments
    parser.add_argument(
        '--max-workers',
        type=int,
        default=20,
        help='Number of concurrent threads for parallel LLM calls (default: 20). Increase for faster processing, decrease if hitting rate limits.'
    )
    parser.add_argument(
        '--rate-limit-delay',
        type=float,
        default=0.1,
        help='Delay in seconds between parallel request submissions (default: 0.1). Increase if hitting Anthropic rate limits.'
    )

    args = parser.parse_args()

    # Determine mode (default to query for backward compatibility)
    if not args.list_collections and not args.list_projects and not args.init_collection and not args.build_summaries and not args.query_summary and not args.query:
        args.query = True

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

    # Validate project name is provided for operations that require it
    operations_requiring_project = [
        args.init_collection,
        args.build_summaries,
        args.query,
        args.query_summary
    ]
    if any(operations_requiring_project) and not args.project:
        print("Error: --project is required for this operation")
        print("Example: python zresearcher.py --init-collection --collection KEY --project \"AI Productivity\"")
        return

    # Validate project name format if provided
    project_name = None
    if args.project:
        try:
            project_name = validate_project_name(args.project)
        except ValueError as e:
            print(f"Error: Invalid project name: {e}")
            return

    # Initialize researcher
    researcher = ZoteroResearcher(
        library_id,
        library_type,
        zotero_api_key,
        anthropic_api_key,
        project_name=project_name,
        research_brief="",
        project_overview="",
        tags=[],
        relevance_threshold=args.threshold,
        max_sources=args.max_sources,
        use_sonnet=args.use_sonnet,
        force_rebuild=args.force,
        max_workers=args.max_workers,
        rate_limit_delay=args.rate_limit_delay,
        verbose=args.verbose
    )

    # Handle --list-collections flag
    if args.list_collections:
        researcher.print_collections()
        return

    # Handle --list-projects flag
    if args.list_projects:
        if not collection_key:
            print("Error: --collection required for --list-projects")
            print("Example: python zresearcher.py --list-projects --collection ABC123")
            return
        researcher.list_projects(collection_key)
        return

    # Handle --init-collection flag
    if args.init_collection:
        if not collection_key:
            print("Error: --collection required for --init-collection")
            print("Example: python zresearcher.py --init-collection --collection ABC123")
            return

        researcher.init_collection(collection_key, force=args.force)
        return

    # Validate collection key
    if not collection_key:
        print("Error: No collection specified")
        print("Either:")
        print("  1. Set ZOTERO_COLLECTION_KEY in your .env file, or")
        print("  2. Use --collection COLLECTION_KEY argument")
        print("\nTip: Run with --list-collections to see available collections")
        return

    # Handle --build-summaries mode
    if args.build_summaries:
        # Load project overview and tags from files if provided (file-based mode)
        if args.project_overview:
            try:
                project_overview = researcher.load_project_overview(args.project_overview)
                researcher.project_overview = project_overview
                print(f"✅ Loaded project overview from: {args.project_overview}")
                print(f"   Length: {len(project_overview)} characters")
            except Exception as e:
                print(f"❌ Error loading project overview: {e}")
                return

        if args.tags:
            try:
                tags = researcher.load_tags(args.tags)
                researcher.tags = tags
                print(f"✅ Loaded {len(tags)} tags from: {args.tags}")
                print(f"   Tags: {', '.join(tags[:5])}{', ...' if len(tags) > 5 else ''}\n")
            except Exception as e:
                print(f"❌ Error loading tags: {e}")
                return

        # Build summaries (will auto-detect mode: file-based vs Zotero-native)
        researcher.build_general_summaries(collection_key)
        return

    # Handle --query-summary mode (Zotero-native)
    if args.query_summary:
        # Run query with research brief from Zotero
        result = researcher.run_query_summary(collection_key)

        if result:
            if result.endswith('.html'):
                print(f"Note: Large report saved as file (with stub note in Zotero)")
            else:
                print(f"Note: Report saved as note in project subcollection")
        return

    # Handle --query mode (file-based)
    if args.query:
        if not args.brief:
            print("Error: --brief is required for --query mode")
            print("Example: python zresearcher.py --query --collection KEY --brief brief.txt")
            print("\nNote: You must run --build-summaries first to create general summaries.")
            return

        # Load research brief
        try:
            research_brief = researcher.load_research_brief(args.brief)
            researcher.research_brief = research_brief
            print(f"✅ Loaded research brief from: {args.brief}")
            print(f"   Brief length: {len(research_brief)} characters\n")
        except Exception as e:
            print(f"❌ Error loading research brief: {e}")
            return

        # Run query
        output_file = researcher.run_query(collection_key)

        if output_file and args.output:
            # Rename to user-specified output
            import shutil
            try:
                shutil.move(output_file, args.output)
                print(f"✅ Report moved to: {args.output}")
            except Exception as e:
                print(f"⚠️  Could not move to {args.output}: {e}")
        return


if __name__ == '__main__':
    main()
