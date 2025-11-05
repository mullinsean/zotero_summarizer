# Research Assistant Refactoring Plan

## Overview
Refactor the research assistant to support a two-phase workflow:
1. **Phase 1: Build General Summaries** - Create enriched summaries with metadata and tags in advance
2. **Phase 2: Query Summaries** - Evaluate relevance and generate targeted summaries for specific research questions

## Current Architecture Problems
- General summaries created on-demand during query execution
- No metadata extraction from sources
- No tagging system to aid relevance evaluation
- Cannot reuse summaries efficiently across different research questions

## Proposed Architecture

### Phase 1: Build General Summaries (New)
**Purpose**: Pre-process all sources in a collection with context-aware summaries

**Inputs**:
- Collection key
- Project overview/outline file (plain text)
- Tag list file (plain text, one tag per line)
- Optional: --force flag to regenerate existing summaries

**Process**:
1. Load project overview and tag list
2. For each source in collection:
   - Extract content (Markdown Extract → HTML → PDF → URL)
   - Extract metadata from Zotero API and content:
     - Title (from Zotero item)
     - Authors (from Zotero item)
     - Date (from Zotero item)
     - Publication/Source (from Zotero item)
     - Document type (article, blog post, research paper, report, etc.)
     - URL (from Zotero item)
   - Generate general summary using LLM with project context
   - Assign relevant tags from provided list using LLM
   - Store in "General Summary" note with structured format
3. Progress reporting

**LLM Prompt Structure** (Haiku for cost efficiency):
```
You are analyzing sources for a research project.

Project Overview:
{project_overview}

Available Tags:
{tag_list}

Source Content:
{content}

Tasks:
1. Provide a comprehensive summary of this source (2-3 paragraphs)
2. Select all relevant tags from the provided list
3. Identify the document type (research paper, blog post, technical article, etc.)

Format your response as:
SUMMARY:
<summary text>

TAGS:
- tag1
- tag2

DOCUMENT_TYPE:
<type>
```

**Note Format** (structured for easy parsing):
```
General Summary

## Metadata
- **Title**: {title}
- **Authors**: {authors}
- **Date**: {date}
- **Publication**: {publication}
- **Type**: {document_type}
- **URL**: {url}

## Tags
{tag1}, {tag2}, {tag3}

## Summary
{summary_text}

---
Created: {timestamp}
Project: {project_name_from_overview}
```

### Phase 2: Query Summaries (Modified)
**Purpose**: Answer specific research questions using pre-built summaries

**Inputs**:
- Collection key
- Research brief/question file (plain text)
- Relevance threshold (default: 6)
- Max sources (default: 50)
- --use-sonnet flag for high-quality output

**Process**:
1. Load research brief
2. For each source in collection:
   - Check for "General Summary" note (skip if missing, or warn user)
   - Parse metadata, tags, and summary from note
   - Evaluate relevance using LLM (tags help inform relevance)
   - If relevant: generate targeted summary with quotes
3. Compile HTML report with metadata displayed

**Changes to Relevance Evaluation**:
- Include tags in relevance evaluation prompt
- Include metadata to help assess source quality/authority
- Tags help LLM understand topical alignment

**Modified LLM Prompt for Relevance** (Haiku):
```
Research Question:
{research_brief}

Source Metadata:
- Title: {title}
- Authors: {authors}
- Date: {date}
- Type: {document_type}
- Tags: {tags}

Source Summary:
{general_summary}

Rate this source's relevance to the research question on a scale of 0-10.
Consider the tags, metadata, and summary content.
```

### Phase 3: HTML Report Enhancement
**Display metadata in report**:
- Show author, date, publication in each source card
- Display tags as colored badges
- Add filtering/sorting by tags (future enhancement)

## Implementation Changes

### 1. New Command-Line Interface

**Build summaries**:
```bash
python researcher.py --build-summaries \
    --collection COLLECTION_KEY \
    --project-overview project.txt \
    --tags tags.txt \
    [--force]
```

**Query summaries** (existing, modified):
```bash
python researcher.py --query \
    --collection COLLECTION_KEY \
    --brief research_brief.txt \
    [--threshold 6] \
    [--use-sonnet]
```

**Default behavior**: If no mode specified, use --query for backward compatibility

### 2. File Structure

**New input files**:
- `project_overview.txt` - Plain text description of research project and goals
- `tags.txt` - Plain text list of tags, one per line

**Example project_overview.txt**:
```
This project examines the impact of artificial intelligence on software development.
Key areas include: code generation tools, automated testing, productivity metrics,
and ethical considerations. The research will inform a technical report for
software engineering managers.
```

**Example tags.txt**:
```
AI Code Generation
Automated Testing
Developer Productivity
Code Quality
Ethics
GitHub Copilot
ChatGPT
Empirical Studies
Case Studies
```

### 3. Code Structure Changes

**New Methods**:
- `build_general_summaries()` - Main orchestration for Phase 1
- `load_project_overview(filepath)` - Load project context
- `load_tags(filepath)` - Load tag list
- `extract_metadata(item)` - Extract metadata from Zotero item
- `create_general_summary_with_tags()` - Generate summary + tags with LLM
- `parse_general_summary_note()` - Parse structured note format
- `format_general_summary_note()` - Create structured note content

**Modified Methods**:
- `evaluate_source_relevance()` - Include metadata and tags in evaluation
- `compile_research_html()` - Display metadata and tags in report
- `run_research()` - Renamed to `run_query()` for clarity

**Refactored Methods**:
- `has_general_summary()` - Already exists
- `get_source_content()` - Already exists
- `create_note()` - Already exists (from base class)

### 4. Metadata Extraction

**From Zotero API** (item data):
- `title` - item['data']['title']
- `creators` - item['data']['creators'] (authors/editors)
- `date` - item['data']['date']
- `publicationTitle` - item['data'].get('publicationTitle', '')
- `url` - item['data'].get('url', '')
- `itemType` - item['data']['itemType']

**From LLM Analysis**:
- Document type (more specific than Zotero itemType)
- Tags assignment

### 5. Note Format Parsing

Use regex or simple parsing to extract sections from note:
```python
def parse_general_summary_note(self, note_content):
    """Parse structured general summary note."""
    metadata = {}
    tags = []
    summary = ""

    # Parse metadata section
    # Parse tags section
    # Parse summary section

    return {
        'metadata': metadata,
        'tags': tags,
        'summary': summary
    }
```

## Backward Compatibility

**Old workflow** (single research brief, creates summaries on-demand):
```bash
python researcher.py --brief research_brief.txt --collection KEY
```

**New workflow** (two-phase):
```bash
# Phase 1: Build summaries once
python researcher.py --build-summaries --collection KEY \
    --project-overview overview.txt --tags tags.txt

# Phase 2: Query multiple times
python researcher.py --query --brief question1.txt --collection KEY
python researcher.py --query --brief question2.txt --collection KEY
```

**Decision**: Keep both workflows
- If `--build-summaries` specified: Run Phase 1 only
- If `--query` specified or default: Run Phase 2 (existing behavior)
- Phase 2 can still create basic summaries if none exist (fallback)

## Benefits

1. **Efficiency**: Build summaries once, query many times
2. **Context-Aware**: Summaries informed by project overview
3. **Better Relevance**: Tags help LLM evaluate topical alignment
4. **Metadata Rich**: Display source provenance and authority
5. **Flexibility**: Can run multiple queries against same summary set
6. **Cost Optimization**: Expensive summarization separate from cheap relevance evaluation

## Example Files

See:
- `example_project_overview.txt` (to be created)
- `example_tags.txt` (to be created)
- `example_research_brief.txt` (already exists)

## Testing Plan

1. Test Phase 1: Build summaries for test collection
2. Verify note format and content
3. Test Phase 2: Query against pre-built summaries
4. Test --force flag to regenerate summaries
5. Test backward compatibility (single-phase workflow)
6. Test missing summary handling
7. Test HTML report with metadata display

## Documentation Updates

- `CLAUDE.md` - Update command examples and workflow
- `README.md` - Update usage instructions
- `researcher.py` - Update docstrings and help text

## Migration Path

For existing users:
1. Old command still works (creates basic summaries on-demand)
2. To use new workflow: Run --build-summaries first
3. Note format is backward compatible (parsing handles both formats)

## Open Questions

1. **Tag limit**: Should we limit number of tags per source? (Suggestion: no limit, LLM decides)
2. **Tag suggestions**: Should LLM suggest new tags not in list? (Suggestion: Phase 2 feature)
3. **Summary length**: Should we specify length for general summaries? (Suggestion: 2-3 paragraphs, configurable)
4. **Note versioning**: How to handle project overview changes? (Suggestion: timestamp and project name in note)

## Implementation Order

1. Create example input files (project_overview.txt, tags.txt)
2. Implement metadata extraction methods
3. Implement Phase 1 methods (build_general_summaries)
4. Update note format and parsing
5. Modify Phase 2 methods (evaluate_source_relevance)
6. Update HTML report generation
7. Update CLI argument parsing
8. Test both phases
9. Update documentation

## Estimated Effort

- Implementation: 2-3 hours
- Testing: 1 hour
- Documentation: 30 minutes
- **Total: ~4 hours**
