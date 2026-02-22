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
    char_limit: int = 50000,
    key_questions: str = ""
) -> str:
    """
    Prompt for generating enhanced general summaries with rich metadata.

    Used in Phase 1 (build-summaries) to create project-aware summaries with
    classification, quality assessment, structural guidance, and key claims.

    Args:
        project_overview: Description of research project
        tags_list: Formatted list of available tags (e.g., "- tag1\n- tag2")
        title: Source title
        authors: Source authors
        date: Publication date
        content: Source content (truncated to char_limit)
        truncated: If True, content has been truncated
        char_limit: Character limit used for truncation
        key_questions: Optional numbered key questions from project overview

    Returns:
        Formatted prompt string
    """
    truncation_note = f"\n\n**NOTE: This source has been truncated to {char_limit:,} characters. You are analyzing a partial view of the full content.**" if truncated else ""

    key_questions_section = f"""
Key Research Questions:
{key_questions}
""" if key_questions else ""

    return f"""You are a research analyst creating a comprehensive summary and analysis of a source document for a research project. Your analysis will be used by downstream research agents, so provide rich structured metadata alongside the summary.

Project Overview:
{project_overview}
{key_questions_section}
Available Tags:
{tags_list}

Source Metadata:
- Title: {title}
- Authors: {authors}
- Date: {date}

Source Content:{truncation_note}
{content}

Analyze this source and provide a structured response. Follow these guidelines:

SUMMARY GUIDELINES:
1. Preserve the main topic, purpose, and key arguments
2. Retain key facts, statistics, and data points
3. Keep important quotes from credible sources
4. Maintain chronological order for time-sensitive content
5. Include relevant dates, names, and locations
6. Aim for 25-30% of original length

CLASSIFICATION GUIDELINES:
- Research Type: Determine based on the source's methodology and purpose
- Project Role: Assess how this source contributes to the research project
- Temporal Fit: Consider whether the publication date and content are current, foundational, or dated for this topic

QUALITY ASSESSMENT GUIDELINES:
- Look for indicators of peer review (journal publication, DOI, academic citations)
- Assess evidence strength based on methodology, sample size, and rigor
- Note any limitations the authors acknowledge or you identify
- Identify potential biases from funding, affiliations, or ideological stance

KEY CLAIMS GUIDELINES:
- Extract 3-5 key claims or findings from the source
- If key research questions are provided above, link claims to relevant question numbers using [Qn] notation
- If no key questions are provided, simply list the claims without question links

Format your response EXACTLY as follows (use these exact headers):

SUMMARY:
<2-4 paragraph comprehensive summary preserving key information>

TAGS:
<comma-separated list of tags from the available tags above>

DOCUMENT_TYPE:
<specific document type: e.g., journal article, government report, news article, white paper, blog post, speech transcript, dataset documentation, book chapter, etc.>

SOURCE_TYPE:
<exactly one of: report | article | primary-source | interview | LLM-generated | blog-opinion | other>
- report: Policy reports, white papers, technical reports, organizational publications
- article: Journal articles, news articles, magazine pieces
- primary-source: Original documents, speeches, raw data, official statements, legislation
- interview: Interview transcripts, Q&A sessions
- LLM-generated: AI-generated content, chatbot outputs
- blog-opinion: Blog posts, op-eds, opinion pieces, commentary
- other: Sources that don't fit above categories

RESEARCH_TYPE:
<exactly one of: empirical | theoretical | review | primary_source | commentary>
- empirical: Original data collection/analysis (surveys, experiments, case studies)
- theoretical: Conceptual or theoretical contribution
- review: Literature review, systematic review, or meta-analysis
- primary_source: Original documents, datasets, speeches, legislation
- commentary: Opinion, editorial, response, or analysis without original research

PROJECT_ROLE:
<exactly one of: background | core_evidence | methodology | counterargument | supporting>
- background: Provides context, foundations, or general understanding
- core_evidence: Directly addresses key research questions
- methodology: Useful for approach, methods, or frameworks
- counterargument: Challenges or complicates the project's thesis
- supporting: Tangentially relevant, provides supplementary information

STRUCTURAL_GUIDANCE:
Most Relevant Sections: <comma-separated list of section names or topics worth deep reading, e.g., "Section 3: Methodology, Results and Discussion, Appendix A">
Sections to Skip: <comma-separated list of sections that can be skipped for this project, or "None" if all sections are relevant>

QUALITY_INDICATORS:
Peer Reviewed: <yes | no | unclear>
Evidence Strength: <strong | moderate | weak> (for this project's needs)
Limitations: <brief description of key limitations, or "Not stated">
Potential Biases: <brief description of potential biases, or "None identified">

TEMPORAL_FIT:
Status: <current | dated | foundational>
- current: Recent and timely for this topic
- dated: Information may be outdated or superseded
- foundational: Classic or seminal work that remains relevant
Context: <brief explanation of temporal relevance, e.g., "Published 2023, covers latest policy developments" or "Pre-dates major regulatory changes in 2020">

KEY_CLAIMS:
<numbered list of 3-5 key claims or findings>
<If key questions were provided, link claims using [Qn] notation. Example:>
1. [Q1] Claim directly relevant to question 1...
2. [Q2, Q3] Claim relevant to multiple questions...
3. Claim without specific question linkage...
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


def research_synthesis_prompt(
    project_overview: str,
    research_brief: str,
    research_report: str,
    report_title: str = "Research Report",
    num_sources: int = 0,
    report_timestamp: str = None,
    zotero_link: str = None
) -> str:
    """
    Prompt for generating a meta-analysis synthesis of research findings.

    Used after Phase 2 (query) to create a high-level synthesis of the
    research report based on the original research brief and project overview.

    Args:
        project_overview: Description of research project and goals
        research_brief: The original research question/brief
        research_report: The full research report HTML content
        report_title: Title of the research report being synthesized
        num_sources: Number of sources in the research report
        report_timestamp: Timestamp when the research report was created
        zotero_link: Optional Zotero internal link to the research report note

    Returns:
        Formatted prompt string
    """
    # Truncate report if too long (keep first 400K chars to leave room for context)
    report_for_prompt = research_report[:400000] if len(research_report) > 400000 else research_report
    truncation_note = "\n\n**NOTE: This research report has been truncated to fit within the context window. You are analyzing a partial view of the full report.**" if len(research_report) > 400000 else ""

    # Build metadata section for the synthesis
    metadata_lines = []
    metadata_lines.append(f"**Report Title:** {report_title}")
    if report_timestamp:
        metadata_lines.append(f"**Report Created:** {report_timestamp}")
    if num_sources > 0:
        metadata_lines.append(f"**Number of Sources:** {num_sources}")
    if zotero_link:
        metadata_lines.append(f"**Zotero Link:** [{report_title}]({zotero_link})")

    metadata_section = "\n".join(metadata_lines)

    return f"""You are a research synthesis specialist tasked with creating a meta-analysis of research findings. You have been provided with a detailed research report that contains summaries of multiple sources. Your goal is to synthesize these findings into a cohesive, high-level analysis that directly addresses the original research brief.

Research Brief:
{research_brief}

Research Report:{truncation_note}
{report_for_prompt}

Please create a comprehensive research synthesis that includes:

**IMPORTANT:** Begin your synthesis with the following metadata section (copy this exactly at the very beginning of your response):

---
## Research Report Metadata

{metadata_section}

---

After the metadata section, continue with the synthesis structure below:

## 1. Executive Summary
Provide a concise 2-3 paragraph overview of the key findings and their significance to the research brief.

## 2. Main Themes and Patterns
Identify and analyze the major themes, patterns, and trends that emerge across the sources. Group related findings together and explain their significance.

## 3. Key Findings
Present the most important findings from the research, organized by theme or topic. Include:
- Quantitative data and statistics where available
- Qualitative insights and expert opinions
- Consensus areas (where multiple sources agree)
- Areas of disagreement or debate
- Notable gaps in the research

For each finding, cite the specific sources (by title) that support it.

## 4. Implications and Insights
Discuss the broader implications of these findings for the research question. What do these findings mean? How do they address the original research brief?

## 5. Recommendations
Based on the synthesis of findings, provide actionable recommendations or next steps related to the research question.

## 6. Research Gaps and Future Directions
Identify areas where the research is incomplete or where further investigation would be valuable.

Guidelines:
- Write in a clear, professional academic tone
- Use markdown formatting for structure and readability
- Cite sources by title when referencing specific findings
- Focus on synthesis and analysis, not just summary
- Connect findings back to the original research brief
- Highlight both areas of consensus and debate
- Be specific - use concrete examples, quotes, and data points
- Aim for 1500-2500 words

Format your response using clear markdown headings (##) and structure. Begin your synthesis below:"""


def metadata_verification_prompt(
    item_type: str,
    current_metadata: dict,
    missing_fields: list,
    suspicious_fields: list,
    content: str
) -> str:
    """
    Prompt for verifying and extracting bibliographic metadata from source content.

    Used by --verify-metadata to audit Zotero items against APA 7th edition
    requirements and extract missing or correct suspicious field values.

    Args:
        item_type: Current Zotero item type (e.g., "journalArticle", "document")
        current_metadata: Dict of current field values (field_name -> value)
        missing_fields: List of field names that are empty/missing
        suspicious_fields: List of field names with suspicious values
        content: Source content (first ~15K chars)

    Returns:
        Formatted prompt string
    """
    # Format current metadata for display
    metadata_lines = []
    for field, value in current_metadata.items():
        status = ""
        if field in missing_fields:
            status = " [MISSING]"
        elif field in suspicious_fields:
            status = " [SUSPICIOUS]"
        metadata_lines.append(f"  {field}: {value}{status}")
    metadata_display = "\n".join(metadata_lines)

    fields_needing_attention = missing_fields + suspicious_fields
    fields_list = ", ".join(fields_needing_attention) if fields_needing_attention else "none"

    return f"""You are a bibliographic metadata specialist. Your task is to verify and extract accurate bibliographic metadata from the source content below. This metadata will be used to generate APA 7th edition citations.

Current Item Type: {item_type}

Current Metadata:
{metadata_display}

Fields Needing Attention: {fields_list}

Source Content (may be truncated):
{content}

INSTRUCTIONS:
1. First, assess whether the current item type is correct based on the source content.
2. Then, for each bibliographic field listed below, verify the current value or extract it from the content.
3. For creators/authors: provide as "LastName, FirstName" separated by semicolons for multiple authors. If the author is an organization, provide just the organization name.
4. For dates: use YYYY-MM-DD format if possible, YYYY-MM if only month available, or YYYY if only year.
5. Verify ALL fields listed above, including those with existing values. For fields marked [MISSING] or [SUSPICIOUS], focus on extracting or correcting values. For other fields, confirm they are correct or provide corrections if you find errors.
6. For creators/authors, pay special attention to:
   - Whether the listed author is the actual author or the website/publication name
   - Organization names incorrectly split into first/last name fields (provide as a single organization name instead)
   - Usernames or handles instead of real author names
   - Missing co-authors when the source content lists multiple authors

FORMAT YOUR RESPONSE EXACTLY AS FOLLOWS:

ITEM_TYPE_ASSESSMENT:
CURRENT: {item_type}
SUGGESTED: <suggested item type, or same as current if correct>
CONFIDENCE: <high | medium | low>
REASON: <brief explanation>

Then for each field you can verify or extract, provide a block like this:

FIELD: <field_name>
STATUS: <confirmed | corrected | extracted | not_found>
VALUE: <the value>
CONFIDENCE: <high | medium | low>

STATUS meanings:
- confirmed: current value is correct
- corrected: current value was wrong, providing correct value
- extracted: field was missing/empty, extracted from content
- not_found: could not determine value from content

Provide ONLY the structured output above, nothing else."""
