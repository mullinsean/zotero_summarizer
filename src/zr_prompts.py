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
    return f"""You are a meticulous relevance rater. Read the RESEARCH BRIEF and the SOURCE (metadata + summary), then rate how relevant the SOURCE is to the BRIEF.

Output Rules (STRICT):
- Return ONLY a single integer between 0 and 10 inclusive.
- No words, no spaces, no punctuation, no JSON, no explanation.
- If you cannot evaluate (e.g., empty text, wrong language, corrupted), output 0.
- Your output must match this regex: ^([0-9]|10)$

Scoring Rubric (compute 0–10, round to nearest integer, then apply the bonus rule below; cap at 10):
1) Topical Alignment (0–5) — Does the SOURCE directly address the BRIEF’s research question/scope?
   0–1: tangential/mostly off-topic
   2–3: partially related; covers some aspects
   4: strongly related; substantial overlap
   5: directly on-point and central
   Use the Tags to refine alignment: overlapping tags with BRIEF keywords → stronger alignment; contradictory/orthogonal tags → weaker.

2) Credibility & Source Type (0–3) — Trustworthiness/authoritativeness.
   3: primary/official sources (government/statistical agencies, legislation, ministerial speeches/transcripts, audited administrative datasets) OR peer-reviewed studies/standards bodies
   2: reputable think tanks, established news with transparent methods/sourcing, named experts with citations
   1: mixed/unclear sourcing; lightly referenced blogs
   0: anonymous, unsourced, promotional, or unverifiable
   Tags indicating "government", "official statistics", "legislation", "ministerial speech", "dataset" should strengthen this category.

3) Timeliness / Temporal Fit (0–1) — Recency or correct historical window for the topic.
   1: timely for a fast-moving topic OR clearly within the required time period
   0: dated/mismatched timeframe

4) Utility & Specificity (0–1) — Actionable content (methods, data tables, case studies, concrete findings).
   1: offers directly usable specifics
   0: generic commentary only

Bonus Rule (apply after summing 0–10, then cap at 10):
+1 if the BRIEF explicitly asks for quantitative figures/data and the SOURCE contains directly usable quantitative evidence (e.g., tables/datasets/clear methods/statistics). Cap the final score at 10.

Research Brief:
{research_brief}

Source Metadata:
- Title: {title}
- Authors: {authors}
- Date: {date}
- Type: {doc_type}
- Tags: {tags}

Source Summary:
{summary}
"""



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


def metadata_extraction_prompt(
    content: str,
    filename: str,
    content_type: str
) -> str:
    """
    Prompt for extracting metadata from source content.

    Used in organize-sources workflow when creating parent items from attachments.
    Attempts to extract: Title, Author(s), Publication, Date

    Args:
        content: Source content (first 10,000 characters)
        filename: Original filename of the attachment
        content_type: MIME type of the attachment

    Returns:
        Formatted prompt string
    """
    return f"""You are analyzing a document to extract bibliographic metadata. The document was uploaded as an attachment with the following properties:

Filename: {filename}
Content Type: {content_type}

Content (first 10,000 characters):
{content}

Please extract the following metadata from this document:

1. **Title**: The full title of the document
2. **Authors**: The author(s) of the document (if multiple, separate with commas)
3. **Publication**: The publication venue (journal, website, publisher, etc.)
4. **Date**: Publication date or date referenced in the document

Guidelines:
- If a field cannot be determined from the content, respond with "Unknown"
- For the title, if no clear title is present, derive a descriptive title from the content
- For authors, look for bylines, author sections, or signatures
- For publication, look for journal names, website names, publisher information, or source attribution
- For dates, look for publication dates, copyright dates, or date stamps (format as YYYY-MM-DD if possible, or YYYY if only year is available)
- Make sure no extra characters before or after a title or author name is included.  Be very precise.

Format your response EXACTLY as follows:

TITLE:
<title here>

AUTHORS:
<authors here>

PUBLICATION:
<publication here>

DATE:
<date here>

Provide ONLY the metadata in the format above, nothing else."""
