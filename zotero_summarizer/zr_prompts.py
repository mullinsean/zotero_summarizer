"""
ZoteroResearcher Prompt Templates

This module contains all major LLM prompts used by the researcher.py module.
Edit these templates directly to customize the research assistant behavior.
"""


def general_summary_prompt(
    project_overview: str,
    tags_list: str,
    title: str,
    authors: str,
    date: str,
    content: str
) -> str:
    """
    Prompt for generating general summaries with tags and document type.

    Used in Phase 1 (build-summaries) to create project-aware summaries.

    Args:
        project_overview: Description of research project
        tags_list: Formatted list of available tags (e.g., "- tag1\n- tag2")
        title: Source title
        authors: Source authors
        date: Publication date
        content: Source content (truncated to ~50K chars)

    Returns:
        Formatted prompt string
    """
    return f"""You are analyzing sources for a research project.

Project Overview:
{project_overview}

Available Tags:
{tags_list}

Source Metadata:
- Title: {title}
- Authors: {authors}
- Date: {date}

Source Content:
{content}

Tasks:
1. Provide a comprehensive summary of this source (2-3 paragraphs)
2. Select all relevant tags from the provided list (only use tags from the list)
3. Identify the document type (e.g., research paper, blog post, technical article, industry report, etc.)

Format your response EXACTLY as follows:

SUMMARY:
<your summary here>

TAGS:
<comma-separated list of tags, e.g.: tag1, tag2, tag3>

DOCUMENT_TYPE:
<document type>"""


def relevance_evaluation_prompt(
    research_brief: str,
    title: str,
    authors: str,
    date: str,
    doc_type: str,
    tags: str,
    summary: str
) -> str:
    """
    Prompt for evaluating source relevance to research brief.

    Used in Phase 2 (query) to score sources on 0-10 scale.

    Args:
        research_brief: Research question/brief
        title: Source title
        authors: Source authors
        date: Publication date
        doc_type: Document type
        tags: Comma-separated tags
        summary: Source summary (truncated to ~10K chars)

    Returns:
        Formatted prompt string
    """
    return f"""Research Brief:
{research_brief}

Source Metadata:
- Title: {title}
- Authors: {authors}
- Date: {date}
- Type: {doc_type}
- Tags: {tags}

Source Summary:
{summary}

Rate the relevance of this source to the research brief on a scale of 0-10, where:
- 0 = Completely irrelevant
- 5 = Somewhat relevant, provides background or tangential information
- 10 = Highly relevant, directly addresses the research question

Consider the tags, metadata, and summary content when evaluating relevance.
Provide ONLY a single number (0-10) as your response, nothing else."""


def targeted_summary_prompt(
    research_brief: str,
    title: str,
    content_type: str,
    content: str
) -> str:
    """
    Prompt for generating detailed targeted summaries.

    Used in Phase 2 (query) for sources that meet relevance threshold.
    Generates detailed summary with quotes and relevance explanation.

    Args:
        research_brief: Research question/brief
        title: Source title
        content_type: Type of content (HTML, PDF, etc.)
        content: Full source content (truncated to ~100K chars)

    Returns:
        Formatted prompt string
    """
    return f"""Research Brief:
{research_brief}

Source Title: {title}
Source Type: {content_type}

Source Content:
{content}

Please provide:

1. **Summary** (2-3 paragraphs): A concise summary of this source focusing on aspects relevant to the research brief.

2. **Relevance Explanation** (1 paragraph): Explain specifically why this source is relevant to the research brief and how it contributes to answering the research question.

3. **Key Passages & Quotes**: Extract 3-5 key passages, quotes, or statistics from the source that are most relevant to the research brief. For each, provide:
   - The exact quote or passage
   - Brief context explaining its significance
   - Location (page number, section, etc.) if available

Format your response using clear markdown headings and structure."""
