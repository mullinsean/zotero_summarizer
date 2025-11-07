"""
ZoteroResearcher Prompt Templates

This module contains all major LLM prompts used by the zresearcher.py module.
Edit these templates directly to customize the research assistant behavior.
"""


def general_summary_prompt(
    project_overview: str,
    tags_list: str,
    title: str,
    authors: str,
    date: str,
    content: str,
    truncated: bool = False,
    char_limit: int = 50000
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
        content: Source content (truncated to char_limit)
        truncated: If True, content has been truncated
        char_limit: Character limit used for truncation

    Returns:
        Formatted prompt string
    """
    truncation_note = f"\n\n**NOTE: This source has been truncated to {char_limit:,} characters. You are analyzing a partial view of the full content.**" if truncated else ""

    return f"""You are tasked with summarizing the raw content of a research source, which could be a website, a report, an academic paper or a transcript. Your goal is to create a summary that preserves the most important information from the original source. This summary will be used by a downstream research agent, so it's crucial to maintain the key details without losing essential information.

Project Overview:
{project_overview}

Available Tags:
{tags_list}

Source Metadata:
- Title: {title}
- Authors: {authors}
- Date: {date}

Source Content:{truncation_note}
{content}

Please follow these guidelines to create your summary:

1. Identify and preserve the main topic or purpose of the webpage.
2. Retain key facts, statistics, and data points that are central to the content's message.
3. Keep important quotes from credible sources or experts.
4. Maintain the chronological order of events if the content is time-sensitive or historical.
5. Preserve any lists or step-by-step instructions if present.
6. Include relevant dates, names, and locations that are crucial to understanding the content.
7. Summarize lengthy explanations while keeping the core message intact.

When handling different types of content:

- For news articles: Focus on the who, what, when, where, why, and how.
- For scientific content: Preserve methodology, results, and conclusions.
- For opinion pieces: Maintain the main arguments and supporting points.
- For product pages: Keep key features, specifications, and unique selling points.

Your summary should be significantly shorter than the original content but comprehensive enough to stand alone as a source of information. Aim for about 25-30 percent of the original length, unless the content is already concise.

Format your response EXACTLY as follows:

SUMMARY:
<your summary here>

TAGS:
<comma-separated list of tags, e.g.: tag1, tag2, tag3>

DOCUMENT_TYPE:
<document type>

Remember, your goal is to create a summary that can be easily understood and utilized by a downstream research agent while preserving the most critical information from the original source.
"""


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
    content: str,
    truncated: bool = False,
    char_limit: int = 100000
) -> str:
    """
    Prompt for generating detailed targeted summaries.

    Used in Phase 2 (query) for sources that meet relevance threshold.
    Generates detailed summary with quotes and relevance explanation.

    Args:
        research_brief: Research question/brief
        title: Source title
        content_type: Type of content (HTML, PDF, etc.)
        content: Full source content (truncated to char_limit)
        truncated: If True, content has been truncated
        char_limit: Character limit used for truncation

    Returns:
        Formatted prompt string
    """
    truncation_note = f"\n\n**NOTE: This source has been truncated to {char_limit:,} characters. You are analyzing a partial view of the full content.**" if truncated else ""

    return f"""Research Brief:
{research_brief}

Source Title: {title}
Source Type: {content_type}

Source Content:{truncation_note}
{content}

Please provide:

1. **Summary** (2-3 paragraphs): A concise summary of this source focusing on aspects relevant to the research brief.

2. **Relevance Explanation** (1 paragraph): Explain specifically why this source is relevant to the research brief and how it contributes to answering the research question.

3. **Key Passages & Quotes**: Extract 3-5 key passages, quotes, or statistics from the source that are most relevant to the research brief. For each, provide:
   - The exact quote or passage
   - Brief context explaining its significance
   - Location (page number, section, etc.) if available

Format your response using clear markdown headings and structure."""
