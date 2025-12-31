# ZoteroResearcher Workflows

Detailed workflow documentation for ZoteroResearcher. For CLI commands, see [commands.md](commands.md).

## Two-Phase Workflow Overview

ZoteroResearcher uses a **two-phase workflow** with **project-based organization**:

### Phase 1 - Build Summaries (`--build-summaries`)

- Pre-process all sources with project-aware summaries
- Extract metadata (authors, date, publication, type, URL)
- Generate context-aware summaries informed by project overview
- Assign relevant tags from user-provided list
- Create structured "General Summary" notes in Zotero
- Run once per project, reuse across multiple queries
- Uses parallel LLM processing for efficiency

### Phase 2 - Query (`--query-summary`)

- Load research brief from Zotero notes
- Parse pre-built summaries with metadata and tags
- Evaluate relevance using metadata + tags + summary content (parallel processing)
- Rank sources by relevance score
- Generate detailed targeted summaries for relevant sources (parallel processing)
- Output professional HTML report
- Smart storage: reports <1MB as notes, >1MB as files with stub notes

### Phase 3 - Research Synthesis (automatic after Phase 2)

- Automatically triggered after creating research report (can be disabled in config)
- Loads project overview and research brief from Zotero notes
- Analyzes the full research report to create a meta-analysis synthesis
- Uses Claude Sonnet (always, regardless of use_sonnet setting) for high-quality analysis
- Generates comprehensive synthesis including:
  - Executive Summary
  - Main Themes and Patterns
  - Key Findings (with source citations)
  - Implications and Insights
  - Recommendations
  - Research Gaps and Future Directions
- Saves as "Research Synthesis: {title}" note in project subcollection
- Can be disabled by setting `generate_synthesis=false` in Project Config

## Key Features

- Project-based organization (multiple projects per collection)
- Two-phase workflow: build once, query multiple times
- Context-aware summaries informed by project overview
- Tag-based categorization from user-defined taxonomy
- Rich metadata extraction from Zotero API
- Relevance evaluation using metadata + tags + summary
- Professional HTML reports with metadata and tag badges
- Parallel LLM processing for speed and efficiency
- Cost-efficient: expensive summarization separate from cheap relevance checks

## LLM Model Strategy

- **Claude Haiku 4.5** for Phase 1 general summaries (cost-efficient)
- **Claude Haiku 4.5** for relevance evaluation (fast, cheap)
- **Claude Haiku 4.5** for detailed targeted summaries by default (cost-efficient)
- **Claude Sonnet 4.5** for detailed targeted summaries with Project Config override (production quality)
- **Claude Sonnet 4.5** for research synthesis (always, high-quality meta-analysis)

## Benefits of Two-Phase Approach

- **Efficiency**: Build summaries once, query many times
- **Context-Aware**: Summaries informed by project overview
- **Better Relevance**: Tags help LLM evaluate topical alignment
- **Metadata Rich**: Display source provenance and authority
- **Flexibility**: Run multiple queries against same summary set
- **Cost Optimization**: ~90% cost reduction by separating phases

---

## Zotero-Native Workflow (Project-Based)

### Initialization (run once per project)

1. Run `--init-collection --collection KEY --project "PROJECT_NAME"`
2. Creates project-specific subcollection: `【ZResearcher: PROJECT_NAME】`
3. Creates four template notes in the subcollection:
   - **【Project Overview: PROJECT_NAME】**: Describe research project and goals
   - **【Research Tags: PROJECT_NAME】**: Tag list (one per line)
   - **【Research Brief: PROJECT_NAME】**: Research question/brief
   - **【Project Config: PROJECT_NAME】**: Optional performance & LLM tuning
4. Edit template notes in Zotero (remove [TODO: markers)

### Phase 1 - Build Summaries

1. Run `--build-summaries --collection KEY --project "PROJECT_NAME"`
2. Load project overview, tags, and config from Zotero notes
3. For each source in collection:
   - Extract metadata from Zotero API
   - Get source content (HTML/PDF/URL)
   - Generate context-aware summary with LLM (parallel processing)
   - Assign relevant tags from provided list
   - Identify document type (LLM)
   - Create structured "General Summary" note in Zotero
4. Skip existing summaries unless `--force` flag used

### Phase 2 - Query Summary

1. Run `--query-summary --collection KEY --project "PROJECT_NAME"`
2. Load research brief and config from Zotero notes
3. For each source in collection:
   - Load and parse "General Summary" note
   - Extract metadata, tags, and summary
   - Evaluate relevance using metadata + tags + summary (parallel processing)
   - If score ≥ threshold: add to relevant sources list
4. Rank relevant sources by score
5. Generate detailed targeted summaries with quotes (parallel processing)
6. Generate HTML report with LLM-generated title
7. **Smart storage:**
   - If report <1MB: Create full note in project subcollection
   - If report >1MB: Save as HTML file + create stub note with file location

### Phase 3 - Research Synthesis (automatic)

1. After research report is created (if `generate_synthesis=true` in config)
2. Load project overview from Zotero notes
3. Send report + project overview + research brief to Claude Sonnet
4. Generate comprehensive meta-analysis synthesis
5. Save as "Research Synthesis: {title}" note in project subcollection

---

## Data Flow Details

### Initialization

1. Load Zotero credentials and LLM API key from environment variables
2. Validate project name and collection key
3. Route to appropriate workflow module (Init/Build/Query)

### Phase 1 - Build Summaries Data Flow

1. Load project overview, tags, and config from Zotero subcollection notes
2. For each item in collection:
   - Skip if already a note/attachment
   - Check for existing project-specific summary (skip unless `--force`)
   - Extract metadata from Zotero API
   - Get source content using priority: Markdown Extract → HTML → PDF → URL
   - Build batch of LLM requests
3. Process batch in parallel with configured worker count
4. Create structured "General Summary" notes in Zotero with metadata, tags, and summary

### Phase 2 - Query Summary Data Flow

1. Load research brief and config from Zotero subcollection notes
2. For each item in collection:
   - Load and parse existing "General Summary" note
   - Extract metadata, tags, and summary
   - Build batch of relevance evaluation requests
3. Process relevance evaluations in parallel
4. Filter sources by relevance threshold
5. Rank sources by relevance score
6. Build batch of targeted summary requests for relevant sources
7. Process targeted summaries in parallel
8. Generate HTML report with LLM-generated title
9. Smart storage: Save as note if <1MB, otherwise save as file with stub note

### Phase 3 - Research Synthesis Data Flow

1. Check if synthesis is enabled (`generate_synthesis=true` in config, default: enabled)
2. Load project overview from Zotero notes
3. Generate synthesis prompt with:
   - Project overview
   - Research brief
   - Full research report HTML content (truncated to 400K chars if needed)
4. Call Claude Sonnet with synthesis prompt (16K max tokens)
5. Create "Research Synthesis: {title}" note in project subcollection

---

## Structured Note Format

General summaries are stored in Zotero with this structure:

```
General Summary

## Metadata
- **Title**: <title>
- **Authors**: <authors>
- **Date**: <date>
- **Publication**: <publication>
- **Type**: <document type determined by LLM>
- **URL**: <url>

## Tags
<comma-separated tags>

## Summary
<summary text>

---
Created: <timestamp>
Project: <project name>
```

---

## Template Notes

The `--init-collection` command creates a "ZoteroResearcher" subcollection with template notes:

### 1. Project Overview Template

```
[TODO: Replace this template with your project description]

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
Edit this note before running --build-summaries
```

### 2. Research Tags Template

```
[TODO: Replace with your research tags, one per line]

Example tags:
artificial-intelligence
software-development
code-generation
automated-testing
productivity-metrics
ethics

---
Template created by ZoteroResearcher
Edit this note before running --build-summaries
```

### 3. Research Brief Template

```
[TODO: Replace this template with your research question]

Describe the specific research question or brief you want to answer.
This will be used to evaluate relevance of sources and generate targeted summaries.

Example:
What are the current challenges and best practices for integrating
AI-powered code generation tools into enterprise software development
workflows? Focus on adoption barriers, productivity impacts, and
quality assurance approaches.

---
Template created by ZoteroResearcher
Edit this note before running --query-summary
```

### Template Validation

- The tool checks for `[TODO:` markers when loading configuration
- If markers are found, it will refuse to run and prompt you to edit the notes
- This ensures you don't accidentally run with placeholder templates
