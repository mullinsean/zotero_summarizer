#!/usr/bin/env python3
"""
LLM-based HTML to Markdown extractor.

This module provides functionality to extract article content from HTML
using Large Language Models (Claude API).
"""

from typing import Optional
from anthropic import Anthropic


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
{html_content[:100000]}
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

    def set_model(self, model: str):
        """
        Change the Claude model being used.

        Args:
            model: Model name (e.g., 'claude-3-5-haiku-20241022', 'claude-3-5-sonnet-20241022')
        """
        self.model = model
