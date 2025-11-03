#!/usr/bin/env python3
"""
LLM-based HTML to Markdown extractor.

This module provides functionality to extract article content from HTML
using Large Language Models (Claude API).
"""

from typing import Optional
from anthropic import Anthropic
from bs4 import BeautifulSoup


class LLMExtractor:
    """Extract article content from HTML using Claude API."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        """
        Initialize the LLM extractor.

        Args:
            api_key: Anthropic API key
            model: Claude model to use (default: claude-haiku-4-5 for cost efficiency)
        """
        self.client = Anthropic(api_key=api_key)
        self.model = model

    def preprocess_html(self, html_content: str) -> str:
        """
        Preprocess HTML to remove non-content elements before sending to LLM.

        This reduces token usage by removing scripts, styles, and other obvious
        non-content elements while preserving the full article content.

        Args:
            html_content: Raw HTML content

        Returns:
            Cleaned HTML content with non-content elements removed
        """
        soup = BeautifulSoup(html_content, 'html.parser')

        # Remove non-content elements
        for element in soup(['script', 'style', 'noscript', 'iframe', 'svg']):
            element.decompose()

        # Remove HTML comments
        for comment in soup.find_all(string=lambda text: isinstance(text, str) and text.strip().startswith('<!--')):
            comment.extract()

        # Return cleaned HTML as string
        return str(soup)

    def extract_article_markdown(self, html_content: str, source_title: str = "") -> Optional[str]:
        """
        Extract article content from HTML and convert to clean Markdown.

        Uses Claude API to intelligently identify and extract the main article
        content, removing navigation, ads, footers, and other non-content elements.

        Args:
            html_content: Raw HTML content
            source_title: Optional title of the source for context

        Returns:
            Clean Markdown content, or None if extraction fails
        """
        try:
            # Preprocess HTML to remove obvious non-content elements
            print(f"  Preprocessing HTML (original size: {len(html_content)} chars)...")
            cleaned_html = self.preprocess_html(html_content)
            print(f"  After preprocessing: {len(cleaned_html)} chars")

            # Construct the prompt for Claude
            system_prompt = """You are an expert at extracting article content from HTML.
Your task is to:
1. Identify the main article content in the HTML
2. Remove all non-content elements (navigation, ads, footers, sidebars, comments, etc.)
3. Preserve the article structure, headings, links, lists, and formatting
4. Convert the content to clean, readable Markdown

Return ONLY the markdown content, with no preamble or explanation."""

            user_prompt = f"""Extract the main article content from this HTML and convert it to Markdown.

{f'Article title for context: {source_title}' if source_title else ''}

HTML content:
```html
{cleaned_html}
```

Return the article content as clean Markdown."""

            # Call Claude API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )

            # Extract the markdown content from the response
            if response.content and len(response.content) > 0:
                markdown = response.content[0].text
                return markdown.strip()
            else:
                print("  ✗ LLM returned empty response")
                return None

        except Exception as e:
            print(f"  ✗ LLM extraction error: {e}")
            return None

    def polish_markdown(self, markdown_content: str, source_title: str = "") -> Optional[str]:
        """
        Polish already-extracted markdown content using Claude.

        Takes markdown that was extracted by Trafilatura and improves formatting,
        structure, and readability.

        Args:
            markdown_content: Markdown content from Trafilatura
            source_title: Optional title of the source for context

        Returns:
            Polished markdown content, or None if polishing fails
        """
        try:
            # Construct the prompt for Claude
            system_prompt = """You are an expert at polishing and formatting markdown content.
Your task is to:
1. Improve the markdown formatting and structure
2. Fix any formatting issues or inconsistencies
3. Ensure proper heading hierarchy
4. Clean up any artifacts from extraction
5. Maintain all content and links
6. Make the document more readable

Return ONLY the polished markdown content, with no preamble or explanation."""

            user_prompt = f"""Polish this markdown content extracted from a web article.

{f'Article title for context: {source_title}' if source_title else ''}

Markdown content:
```markdown
{markdown_content}
```

Return the polished markdown content."""

            # Call Claude API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )

            # Extract the polished markdown from the response
            if response.content and len(response.content) > 0:
                polished = response.content[0].text
                return polished.strip()
            else:
                print("  ✗ LLM returned empty response")
                return None

        except Exception as e:
            print(f"  ✗ LLM polish error: {e}")
            return None

    def set_model(self, model: str):
        """
        Change the Claude model being used.

        Args:
            model: Model name (e.g., 'claude-haiku-4-5-20251001', 'claude-3-5-sonnet-20241022')
        """
        self.model = model
