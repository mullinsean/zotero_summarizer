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

# Handle both relative and absolute imports
try:
    from .zotero_base import ZoteroBaseProcessor
except ImportError:
    from zotero_base import ZoteroBaseProcessor


class ZoteroResearcher(ZoteroBaseProcessor):
    """Research assistant for analyzing Zotero collections based on research briefs."""

    def __init__(
        self,
        library_id: str,
        library_type: str,
        api_key: str,
        anthropic_api_key: str,
        research_brief: str,
        relevance_threshold: int = 6,
        max_sources: int = 50,
        cache_summaries: bool = True,
        use_sonnet: bool = False,
        verbose: bool = False
    ):
        """
        Initialize the Zotero researcher.

        Args:
            library_id: Your Zotero user ID or group ID
            library_type: 'user' or 'group'
            api_key: Your Zotero API key
            anthropic_api_key: Anthropic API key for Claude
            research_brief: The research brief text
            relevance_threshold: Minimum relevance score (0-10) to include source (default: 6)
            max_sources: Maximum number of sources to process (default: 50)
            cache_summaries: If True, cache general summaries for efficiency (default: True)
            use_sonnet: If True, use Sonnet for detailed summaries (higher quality, higher cost) (default: False)
            verbose: If True, show detailed information about all child items
        """
        # Initialize base class
        super().__init__(library_id, library_type, api_key, verbose)

        # Researcher-specific configuration
        self.anthropic_client = Anthropic(api_key=anthropic_api_key)
        self.research_brief = research_brief
        self.relevance_threshold = relevance_threshold
        self.max_sources = max_sources
        self.cache_summaries = cache_summaries
        self.use_sonnet = use_sonnet

        # Use Haiku for quick tasks (relevance, general summaries)
        self.haiku_model = "claude-haiku-4-5-20251001"
        # Sonnet for production-quality detailed analysis
        self.sonnet_model = "claude-sonnet-4-5-20250929"

        # Default to Haiku for detailed summaries (cost-efficient)
        # Use Sonnet only when use_sonnet=True (production mode)
        self.summary_model = self.sonnet_model if use_sonnet else self.haiku_model

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
        Check if an item has a cached general summary note.

        Args:
            item_key: The key of the item

        Returns:
            True if a general summary exists
        """
        return self.has_note_with_prefix(item_key, 'General Summary:')

    def create_general_summary(self, item_key: str, content: str, item_title: str) -> Optional[str]:
        """
        Create a cached general summary for quick relevance evaluation.

        Args:
            item_key: The key of the item
            content: The source content to summarize
            item_title: Title of the source

        Returns:
            The generated summary text, or None if generation fails
        """
        try:
            # Use Haiku for cost-efficient general summaries
            prompt = f"""Please provide a concise general summary of this source in 2-3 paragraphs.
Focus on the main topic, key arguments, and conclusions.

Title: {item_title}

Content:
{content[:50000]}  # Limit to ~50K chars to avoid token limits

Summary:"""

            response = self.anthropic_client.messages.create(
                model=self.haiku_model,
                max_tokens=2048,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            if response.content and len(response.content) > 0:
                summary = response.content[0].text.strip()

                # Save to Zotero as a cached note
                note_title = f"General Summary: {item_title}"
                if self.create_note(item_key, summary, note_title, convert_markdown=True):
                    return summary
                else:
                    print(f"  ⚠️  Failed to save general summary note")
                    # Still return the summary even if save failed
                    return summary

            return None

        except Exception as e:
            print(f"  ❌ Error creating general summary: {e}")
            return None

    def evaluate_source_relevance(self, summary: str, item_title: str) -> Optional[int]:
        """
        Evaluate how relevant a source is to the research brief.

        Args:
            summary: The source summary (general or full content)
            item_title: Title of the source

        Returns:
            Relevance score (0-10), or None if evaluation fails
        """
        try:
            # Use Haiku for fast, cheap relevance scoring
            prompt = f"""Research Brief:
{self.research_brief}

Source Title: {item_title}

Source Summary:
{summary[:10000]}  # Limit to ~10K chars

Rate the relevance of this source to the research brief on a scale of 0-10, where:
- 0 = Completely irrelevant
- 5 = Somewhat relevant, provides background or tangential information
- 10 = Highly relevant, directly addresses the research question

Provide ONLY a single number (0-10) as your response, nothing else."""

            response = self.anthropic_client.messages.create(
                model=self.haiku_model,
                max_tokens=10,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            if response.content and len(response.content) > 0:
                score_text = response.content[0].text.strip()
                # Extract number from response
                import re
                match = re.search(r'\b(\d+)\b', score_text)
                if match:
                    score = int(match.group(1))
                    # Clamp to 0-10 range
                    score = max(0, min(10, score))
                    return score

            print(f"  ⚠️  Could not parse relevance score from LLM response")
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

            # Use configured model (Haiku by default, Sonnet for production)
            prompt = f"""Research Brief:
{self.research_brief}

Source Title: {item_title}
Source Type: {content_type}

Source Content:
{content[:100000]}  # Limit to ~100K chars

Please provide:

1. **Summary** (2-3 paragraphs): A concise summary of this source focusing on aspects relevant to the research brief.

2. **Relevance Explanation** (1 paragraph): Explain specifically why this source is relevant to the research brief and how it contributes to answering the research question.

3. **Key Passages & Quotes**: Extract 3-5 key passages, quotes, or statistics from the source that are most relevant to the research brief. For each, provide:
   - The exact quote or passage
   - Brief context explaining its significance
   - Location (page number, section, etc.) if available

Format your response using clear markdown headings and structure."""

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

            anchor = f"source-{idx}"

            # Build Zotero link
            library_type = 'groups' if self.zot.library_type == 'group' else 'library'
            zotero_link = f"zotero://select/{library_type}/{self.zot.library_id}/items/{item_key}"

            # Convert markdown to HTML
            summary_markdown = summary_data.get('full_text', 'Summary not available')
            summary_html = markdown.markdown(summary_markdown, extensions=['extra', 'nl2br'])

            html_parts.append(f"""
    <div class="source" id="{anchor}">
        <h3>{idx}. {item_title}</h3>
        <div class="metadata">
            <strong>Relevance Score:</strong> {score}/10<br>
            <strong>Content Type:</strong> {content_type}<br>
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
            <li>Relevant sources (≥ {self.relevance_threshold}/10): {stats.get('relevant', 0)}</li>
            <li>Sources with cached summaries: {stats.get('cached', 0)}</li>
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

    def run_research(self, collection_key: str) -> str:
        """
        Main orchestration method to run the research workflow.

        Args:
            collection_key: The Zotero collection key to analyze

        Returns:
            Path to the generated HTML report
        """
        start_time = time.time()

        print(f"\n{'='*80}")
        print(f"🔬 Research Analysis Starting")
        print(f"{'='*80}")
        print(f"Collection: {collection_key}")
        print(f"Relevance Threshold: {self.relevance_threshold}/10")
        print(f"Max Sources: {self.max_sources}")
        print(f"Summary Caching: {'Enabled' if self.cache_summaries else 'Disabled'}")
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

        # Phase 1: Extract content and evaluate relevance
        print(f"\n{'='*80}")
        print(f"Phase 1: Content Extraction & Relevance Evaluation")
        print(f"{'='*80}\n")

        sources_with_scores = []
        cached_summaries = 0
        evaluated = 0

        for idx, item in enumerate(items, 1):
            item_type = item['data'].get('itemType')
            if item_type in ['attachment', 'note']:
                continue

            item_title = item['data'].get('title', 'Untitled')
            item_key = item['key']

            print(f"\n[{idx}/{len(items)}] 📚 {item_title}")

            # Get source content
            content, content_type = self.get_source_content(item)
            if not content:
                print(f"  ⚠️  Could not extract content, skipping")
                continue

            print(f"  ✅ Extracted {len(content)} characters from {content_type}")

            # Get or create general summary for relevance evaluation
            summary_for_eval = content
            if self.cache_summaries:
                if self.has_general_summary(item_key):
                    print(f"  ♻️  Using cached general summary")
                    summary_note = self.get_note_with_prefix(item_key, 'General Summary:')
                    if summary_note:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(summary_note, 'html.parser')
                        summary_for_eval = soup.get_text().strip()
                        cached_summaries += 1
                else:
                    print(f"  🤖 Creating general summary (Haiku)...")
                    summary = self.create_general_summary(item_key, content, item_title)
                    if summary:
                        summary_for_eval = summary
                        cached_summaries += 1
                        print(f"  💾 Cached for future use")

            # Evaluate relevance
            print(f"  🎯 Evaluating relevance (Haiku)...")
            score = self.evaluate_source_relevance(summary_for_eval, item_title)

            if score is None:
                print(f"  ⚠️  Could not evaluate relevance, skipping")
                continue

            print(f"  📊 Relevance Score: {score}/10")
            evaluated += 1

            sources_with_scores.append({
                'item': item,
                'score': score,
                'content': content,
                'content_type': content_type
            })

            # Rate limiting
            time.sleep(0.5)

        # Filter and rank sources
        print(f"\n{'='*80}")
        print(f"Phase 2: Ranking & Filtering")
        print(f"{'='*80}\n")

        relevant_sources = [s for s in sources_with_scores if s['score'] >= self.relevance_threshold]
        relevant_sources = self.rank_sources(relevant_sources)

        print(f"  📊 Sources meeting threshold ({self.relevance_threshold}/10): {len(relevant_sources)}")

        if not relevant_sources:
            print(f"\n⚠️  No sources meet the relevance threshold of {self.relevance_threshold}/10")
            print(f"  Try lowering the threshold or refining your research brief")
            return ""

        # Phase 3: Generate detailed summaries
        print(f"\n{'='*80}")
        print(f"Phase 3: Detailed Research Summaries")
        print(f"{'='*80}\n")

        for idx, source_data in enumerate(relevant_sources, 1):
            item = source_data['item']
            item_title = item['data'].get('title', 'Untitled')
            score = source_data['score']
            content = source_data['content']
            content_type = source_data['content_type']

            print(f"\n[{idx}/{len(relevant_sources)}] 📝 {item_title} (Score: {score}/10)")
            model_name = "Sonnet" if self.use_sonnet else "Haiku"
            print(f"  🤖 Generating targeted summary ({model_name})...")

            summary_data = self.generate_targeted_summary(item, content, content_type)
            if summary_data:
                source_data['summary_data'] = summary_data
                print(f"  ✅ Summary generated")
            else:
                print(f"  ⚠️  Failed to generate summary")
                source_data['summary_data'] = {'full_text': 'Summary generation failed'}

            # Rate limiting
            time.sleep(0.5)

        # Phase 4: Compile HTML report
        print(f"\n{'='*80}")
        print(f"Phase 4: Compiling Research Report")
        print(f"{'='*80}\n")

        elapsed_time = time.time() - start_time
        stats = {
            'total': len(items),
            'evaluated': evaluated,
            'relevant': len(relevant_sources),
            'cached': cached_summaries,
            'time': f"{elapsed_time:.1f} seconds"
        }

        output_file = self.compile_research_html(collection_key, relevant_sources, stats)

        # Final summary
        print(f"\n{'='*80}")
        print(f"✅ Research Complete")
        print(f"{'='*80}")
        print(f"Total sources: {stats['total']}")
        print(f"Evaluated: {stats['evaluated']}")
        print(f"Relevant: {stats['relevant']}")
        print(f"Cached summaries: {stats['cached']}")
        print(f"Processing time: {stats['time']}")
        print(f"Report: {output_file}")
        print(f"{'='*80}\n")

        return output_file


def main():
    """Main entry point."""
    import argparse
    from dotenv import load_dotenv

    # Load environment variables
    load_dotenv()

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Analyze Zotero collection based on research brief'
    )
    parser.add_argument(
        '--list-collections',
        action='store_true',
        help='List all available collections and exit'
    )
    parser.add_argument(
        '--collection',
        type=str,
        help='Collection key to analyze (overrides ZOTERO_COLLECTION_KEY env var)'
    )
    parser.add_argument(
        '--brief',
        type=str,
        required='--list-collections' not in __import__('sys').argv,
        help='Path to research brief text file (required)'
    )
    parser.add_argument(
        '--threshold',
        type=int,
        default=6,
        help='Relevance threshold 0-10 (default: 6)'
    )
    parser.add_argument(
        '--max-sources',
        type=int,
        default=50,
        help='Maximum number of sources to process (default: 50)'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='Output HTML file path (default: auto-generated)'
    )
    parser.add_argument(
        '--no-cache-summaries',
        action='store_true',
        help='Disable summary caching'
    )
    parser.add_argument(
        '--use-sonnet',
        action='store_true',
        help='Use Sonnet for detailed summaries (higher quality, higher cost). Default: Haiku (cost-efficient)'
    )
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Show detailed information about all child items'
    )

    args = parser.parse_args()

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

    # Initialize researcher (with placeholder brief for --list-collections)
    researcher = ZoteroResearcher(
        library_id,
        library_type,
        zotero_api_key,
        anthropic_api_key,
        research_brief="",  # Will be loaded below if needed
        relevance_threshold=args.threshold,
        max_sources=args.max_sources,
        cache_summaries=not args.no_cache_summaries,
        use_sonnet=args.use_sonnet,
        verbose=args.verbose
    )

    # Handle --list-collections flag
    if args.list_collections:
        researcher.print_collections()
        return

    # Validate collection key
    if not collection_key:
        print("Error: No collection specified")
        print("Either:")
        print("  1. Set ZOTERO_COLLECTION_KEY in your .env file, or")
        print("  2. Use --collection COLLECTION_KEY argument")
        print("\nTip: Run with --list-collections to see available collections")
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

    # Run research
    output_file = researcher.run_research(collection_key)

    if output_file and args.output:
        # Rename to user-specified output
        import shutil
        try:
            shutil.move(output_file, args.output)
            print(f"✅ Report moved to: {args.output}")
        except Exception as e:
            print(f"⚠️  Could not move to {args.output}: {e}")


if __name__ == '__main__':
    main()
