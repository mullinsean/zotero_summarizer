# Zotero-Native Research Workflow Plan

## Overview

Refactor the research assistant to use Zotero's native collection and note system for storing all configuration, inputs, and outputs. This eliminates external text files and makes the entire research workflow self-contained and portable within Zotero.

## Status of Current Implementation

**What's Been Done:**
- ✅ Two-phase workflow (build summaries, then query)
- ✅ Metadata extraction from Zotero API
- ✅ Tag assignment using LLM
- ✅ Structured "General Summary" notes stored in Zotero
- ✅ HTML report generation with metadata and tags
- ✅ File-based inputs: project_overview.txt, tags.txt, research_brief.txt

**Current Pain Points:**
- External text files not portable with Zotero library
- Must manage separate files alongside Zotero collection
- No visual organization of research workflow in Zotero UI
- Configuration scattered across filesystem

## Proposed Architecture: Three-Stage Zotero-Native Workflow

### Stage 1: Initialize Collection (`--init-collection`)

**Purpose:** Set up a collection for use with the researcher tool by creating a dedicated subcollection with configuration templates.

**Command:**
```bash
python researcher.py --init-collection --collection COLLECTION_KEY
```

**Process:**
1. **Create Subcollection:**
   - Create a subcollection named "ZoteroResearcher" inside the specified collection
   - This subcollection will contain all configuration and outputs
   - Store subcollection key for future reference

2. **Create Configuration Template Notes:**
   Create three template notes as **top-level notes** (not attached to items) in the ZoteroResearcher subcollection:

   **a) "📋 Project Overview" note:**
   ```
   Project Overview
   ================

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

   **b) "🏷️ Research Tags" note:**
   ```
   Research Tags
   =============

   [TODO: Replace this template with your tag list]

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
   Edit this note before running --build-summaries
   ```

   **c) "❓ Research Brief Template" note:**
   ```
   Research Brief Template
   =======================

   [TODO: Copy this note and fill in your specific research question]

   State your specific research question or topic. This will be used
   to evaluate source relevance and generate targeted summaries.

   Instructions:
   1. Duplicate this note in Zotero (right-click → Duplicate Item)
   2. Rename it to describe your research question
   3. Replace this template with your actual research question
   4. Run --query-summary with your collection key

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
   ```

3. **Confirmation Output:**
   ```
   ✅ Collection initialized for ZoteroResearcher

   Created subcollection: "ZoteroResearcher" (KEY: ABC123)

   📋 Configuration templates created:
      - Project Overview (edit before building summaries)
      - Research Tags (edit before building summaries)
      - Research Brief Template (duplicate and edit for each query)

   📝 Next steps:
      1. Open the "ZoteroResearcher" subcollection in Zotero
      2. Edit "Project Overview" with your project description
      3. Edit "Research Tags" with your tag list
      4. Run: python researcher.py --build-summaries --collection KEY
   ```

4. **Idempotency:**
   - If ZoteroResearcher subcollection already exists, prompt user:
     ```
     ⚠️  Collection already initialized with ZoteroResearcher subcollection

     Options:
     1. Skip (use existing configuration)
     2. Recreate templates (--force flag)

     Run with --force to recreate template notes.
     ```

### Stage 2: Build General Summaries (`--build-summaries`)

**Purpose:** Generate project-aware summaries with metadata and tags for all sources in the collection.

**Command:**
```bash
python researcher.py --build-summaries --collection COLLECTION_KEY [--force]
```

**Process:**
1. **Verify Initialization:**
   - Check if ZoteroResearcher subcollection exists
   - If not, prompt: "Collection not initialized. Run --init-collection first."

2. **Load Configuration from Subcollection Notes:**
   - Search ZoteroResearcher subcollection for notes with titles:
     - "📋 Project Overview" → extract project description
     - "🏷️ Research Tags" → parse tag list (one per line)
   - If templates still contain "[TODO:", warn user to edit them first
   - Display loaded config for confirmation:
     ```
     📋 Project Overview: 450 characters loaded
     🏷️ Research Tags: 12 tags loaded
     ```

3. **Build Summaries (existing logic):**
   - For each source in **parent collection** (not subcollection):
     - Extract content and metadata
     - Generate project-aware summary with LLM
     - Assign tags from provided list
     - Create "General Summary" note attached to source (as currently implemented)
     - Skip if note exists (unless --force)

4. **Progress & Stats Output:**
   ```
   📚 Building General Summaries
   ================================================================================
   Collection: AI Research Papers (50 sources)
   Project: Impact of AI on Software Development
   Tags: 12 available
   ================================================================================

   [1/50] 📚 "GitHub Copilot Effectiveness Study"
     ✅ Extracted 15,245 characters from PDF
     🤖 Generating summary with tags (Haiku)...
     ✅ Summary created
        Type: Research Paper
        Tags: GitHub Copilot, Developer Productivity, Empirical Studies

   [... continues ...]

   ================================================================================
   ✅ Build Complete
   ================================================================================
   Total items: 50
   Processed: 48
   Created: 45
   Skipped (existing): 3
   Errors: 2
   Processing time: 143.5 seconds
   ================================================================================
   ```

### Stage 3: Run Query Summary (`--query-summary`)

**Purpose:** Evaluate source relevance for a specific research question and generate a detailed research report.

**Command:**
```bash
python researcher.py --query-summary --collection COLLECTION_KEY \
    [--threshold 6] [--use-sonnet]
```

**Process:**
1. **Verify Initialization & Build:**
   - Check if ZoteroResearcher subcollection exists
   - If not, prompt: "Collection not initialized. Run --init-collection first."
   - Check if general summaries exist for sources
   - If few exist, warn: "Only 3/50 sources have general summaries. Run --build-summaries first."

2. **Discover Research Briefs:**
   - Search ZoteroResearcher subcollection for notes (exclude templates)
   - Look for notes that are NOT:
     - "📋 Project Overview"
     - "🏷️ Research Tags"
     - "❓ Research Brief Template"
   - If multiple research briefs found, prompt user to select:
     ```
     🔍 Found 3 research briefs in ZoteroResearcher subcollection:

     1. "Impact of AI on Developer Productivity" (2025-01-10)
     2. "Code Quality Metrics with AI Tools" (2025-01-08)
     3. "Ethical Considerations in AI-Assisted Development" (2025-01-05)

     Which brief would you like to use for this query?
     Enter number (1-3): _
     ```
   - If only one research brief (non-template) found, use it automatically:
     ```
     ✅ Using research brief: "Impact of AI on Developer Productivity"
     ```
   - If none found, prompt:
     ```
     ❌ No research briefs found in ZoteroResearcher subcollection

     Please:
     1. Open the ZoteroResearcher subcollection in Zotero
     2. Duplicate the "Research Brief Template" note
     3. Edit it with your research question
     4. Run this command again
     ```

3. **Run Query (existing logic):**
   - Parse general summaries with metadata and tags
   - Evaluate relevance using LLM
   - Filter by threshold
   - Rank by relevance score
   - Generate detailed targeted summaries
   - (Same as current implementation)

4. **Output Research Report as Zotero Note:**

   **Instead of HTML file, create a note in ZoteroResearcher subcollection:**

   **Note Title:** `📊 Research Report: {brief_title_short} - {timestamp}`

   **Note Content Format:**
   ```html
   <h1>📊 Research Report</h1>

   <div style="background: #f0f8ff; padding: 15px; border-left: 4px solid #3498db; margin-bottom: 20px;">
       <strong>Research Brief:</strong> Impact of AI on Developer Productivity<br>
       <strong>Generated:</strong> 2025-01-15 14:30<br>
       <strong>Collection:</strong> AI Research Papers<br>
       <strong>Relevant Sources:</strong> 12/50 (threshold: 6/10)
   </div>

   <h2>Research Brief</h2>
   <div style="background: #f9f9f9; padding: 15px; margin-bottom: 20px;">
   {full research brief text}
   </div>

   <h2>Table of Contents</h2>
   <ol>
       <li><a href="zotero://select/items/ITEMKEY1">Source Title 1</a> - Relevance: 9/10</li>
       <li><a href="zotero://select/items/ITEMKEY2">Source Title 2</a> - Relevance: 8/10</li>
       ...
   </ol>

   <h2>Relevant Sources</h2>

   <div style="border-left: 4px solid #3498db; padding-left: 20px; margin: 30px 0;">
       <h3>1. Source Title 1</h3>

       <div style="background: #f8f9fa; padding: 10px; margin-bottom: 15px;">
           <strong>Authors:</strong> John Smith, Jane Doe<br>
           <strong>Date:</strong> 2024<br>
           <strong>Type:</strong> Research Paper<br>
           <strong>Tags:</strong>
           <span style="background: #3498db; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.85em;">GitHub Copilot</span>
           <span style="background: #3498db; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.85em;">Developer Productivity</span><br>
           <strong>Relevance Score:</strong> 9/10<br>
           <strong>Zotero Link:</strong> <a href="zotero://select/items/ITEMKEY">Open in Zotero</a>
       </div>

       <h4>Summary</h4>
       <p>{targeted summary with markdown formatting}</p>

       <h4>Relevance</h4>
       <p>{why this source is relevant}</p>

       <h4>Key Passages & Quotes</h4>
       <blockquote style="background: #f0f8ff; border-left: 3px solid #3498db; padding: 10px; margin: 10px 0;">
           <p><strong>Quote:</strong> "..."</p>
           <p><strong>Context:</strong> ...</p>
       </blockquote>
   </div>

   <!-- Repeat for each source -->

   <h2>📊 Statistics</h2>
   <ul>
       <li>Total sources: 50</li>
       <li>Evaluated: 48</li>
       <li>Relevant (≥ 6/10): 12</li>
       <li>Processing time: 45.2 seconds</li>
   </ul>

   <hr>
   <p style="font-size: 0.85em; color: #7f8c8d;">
   Generated by ZoteroResearcher |
   Based on research brief: <a href="zotero://select/items/BRIEFITEMKEY">View Brief</a>
   </p>
   ```

5. **Attach Original Brief as Child:**
   - After creating the research report note, create a link to the original research brief
   - Store the brief's item key in the report note metadata or as a related item
   - This creates traceability: Report → Original Brief

6. **Set Zotero Metadata on Report Note:**
   - **Title:** `📊 Research Report: {brief_title_short} - {timestamp}`
   - **Tags:** Add Zotero tags (not collection tags):
     - `ZoteroResearcher`
     - `ResearchReport`
     - `{collection_name}`
   - **Date Added:** Current timestamp
   - **Related Items:** Link to the research brief note that was used

7. **Confirmation Output:**
   ```
   ✅ Query Complete
   ================================================================================

   📊 Research Report created in ZoteroResearcher subcollection

   Title: Research Report: AI Productivity - 2025-01-15
   Relevant Sources: 12/50 (threshold: 6/10)

   📝 Open in Zotero:
      - Collection: AI Research Papers > ZoteroResearcher
      - Look for note titled: "📊 Research Report: AI Productivity..."

   ⏱️  Processing Stats:
      Total sources: 50
      Evaluated: 48
      Relevant: 12
      Time: 45.2 seconds

   ================================================================================
   ```

## Benefits of Zotero-Native Approach

1. **Portability:** Everything stored in Zotero, syncs across devices
2. **Visual Organization:** Clear hierarchy in Zotero UI (main collection → ZoteroResearcher subcollection)
3. **Traceability:** Reports linked to their source briefs
4. **No External Files:** No need to manage text files separately
5. **Zotero Integration:** Reports accessible directly in Zotero, searchable
6. **Collaborative:** If using Zotero groups, entire workflow is shared
7. **Version Control:** Zotero's sync handles versioning
8. **Rich Formatting:** HTML notes support links, styling, embedded content

## Migration from Current File-Based Approach

**Two Modes of Operation:**

1. **Legacy Mode (file-based):**
   ```bash
   # Still supported for existing users
   python researcher.py --build-summaries --collection KEY \
       --project-overview overview.txt --tags tags.txt

   python researcher.py --query --collection KEY --brief brief.txt
   ```

2. **Zotero-Native Mode (new):**
   ```bash
   # New workflow, stores everything in Zotero
   python researcher.py --init-collection --collection KEY
   # Edit notes in Zotero UI
   python researcher.py --build-summaries --collection KEY
   # Create research brief note in Zotero UI
   python researcher.py --query-summary --collection KEY
   ```

**Detection Logic:**
- If `--project-overview` or `--tags` flags provided → Use file-based mode
- If neither provided → Look for Zotero subcollection and notes
- If subcollection not found → Prompt to either:
  - Run `--init-collection`, OR
  - Provide `--project-overview` and `--tags` files

**Migration Path for Existing Users:**
1. Run `--init-collection` on existing collection
2. Copy content from text files into template notes in Zotero
3. Existing "General Summary" notes are compatible (no changes needed)
4. Start using Zotero-native workflow for new queries

## Implementation Details

### 1. Subcollection Management

**Create Subcollection:**
```python
def create_researcher_subcollection(self, parent_collection_key: str) -> str:
    """
    Create ZoteroResearcher subcollection inside parent collection.

    Args:
        parent_collection_key: Key of parent collection

    Returns:
        Key of created subcollection
    """
    # Check if already exists
    collections = self.zot.collections_sub(parent_collection_key)
    for coll in collections:
        if coll['data']['name'] == 'ZoteroResearcher':
            return coll['key']

    # Create new subcollection
    template = self.zot.collection_template()
    template['name'] = 'ZoteroResearcher'
    template['parentCollection'] = parent_collection_key

    result = self.zot.create_collections([template])
    return result['successful']['0']['key']
```

**Get Subcollection:**
```python
def get_researcher_subcollection(self, parent_collection_key: str) -> Optional[str]:
    """
    Get ZoteroResearcher subcollection key if it exists.

    Returns:
        Subcollection key or None if not found
    """
    collections = self.zot.collections_sub(parent_collection_key)
    for coll in collections:
        if coll['data']['name'] == 'ZoteroResearcher':
            return coll['key']
    return None
```

### 2. Note Creation in Collection

**Create Standalone Note:**
```python
def create_standalone_note(self, collection_key: str, title: str, content: str, tags: List[str] = None) -> str:
    """
    Create a standalone note (not attached to an item) in a collection.

    Args:
        collection_key: Collection to add note to
        title: Note title (will be first line of HTML)
        content: Note content (HTML format)
        tags: Optional list of Zotero tags

    Returns:
        Item key of created note
    """
    template = self.zot.item_template('note')

    # Format note with title as heading
    full_content = f"<h1>{title}</h1>\n{content}"
    template['note'] = full_content
    template['collections'] = [collection_key]

    if tags:
        template['tags'] = [{'tag': tag} for tag in tags]

    result = self.zot.create_items([template])
    return result['successful']['0']['key']
```

### 3. Reading Notes from Collection

**Get All Notes in Collection:**
```python
def get_collection_notes(self, collection_key: str) -> List[Dict]:
    """
    Get all standalone notes in a collection.

    Returns:
        List of note items
    """
    items = self.zot.collection_items(collection_key)
    notes = [item for item in items if item['data']['itemType'] == 'note']
    return notes
```

**Parse Note Title from HTML:**
```python
def get_note_title(self, note_html: str) -> str:
    """
    Extract title from note HTML (first h1 or first line).

    Args:
        note_html: HTML content of note

    Returns:
        Note title
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(note_html, 'html.parser')

    # Try to find h1
    h1 = soup.find('h1')
    if h1:
        return h1.get_text().strip()

    # Fall back to first non-empty line
    text = soup.get_text().strip()
    first_line = text.split('\n')[0] if text else 'Untitled'
    return first_line.strip()
```

### 4. Configuration Loading

**Load Project Overview from Zotero:**
```python
def load_project_overview_from_zotero(self, subcollection_key: str) -> str:
    """
    Load project overview from ZoteroResearcher subcollection note.

    Returns:
        Project overview text

    Raises:
        FileNotFoundError: If note not found
        ValueError: If note still contains template placeholder
    """
    notes = self.get_collection_notes(subcollection_key)

    for note in notes:
        title = self.get_note_title(note['data']['note'])
        if '📋 Project Overview' in title or 'Project Overview' in title:
            content = self.extract_text_from_note_html(note['data']['note'])

            # Check if still template
            if '[TODO:' in content:
                raise ValueError(
                    "Project Overview note still contains template. "
                    "Please edit the note in Zotero before building summaries."
                )

            # Remove header and footer
            content = self.clean_template_content(content)
            return content.strip()

    raise FileNotFoundError(
        "Project Overview note not found in ZoteroResearcher subcollection. "
        "Run --init-collection first."
    )
```

**Load Tags from Zotero:**
```python
def load_tags_from_zotero(self, subcollection_key: str) -> List[str]:
    """
    Load research tags from ZoteroResearcher subcollection note.

    Returns:
        List of tags (one per line from note)

    Raises:
        FileNotFoundError: If note not found
        ValueError: If note still contains template placeholder
    """
    notes = self.get_collection_notes(subcollection_key)

    for note in notes:
        title = self.get_note_title(note['data']['note'])
        if '🏷️ Research Tags' in title or 'Research Tags' in title:
            content = self.extract_text_from_note_html(note['data']['note'])

            # Check if still template
            if '[TODO:' in content:
                raise ValueError(
                    "Research Tags note still contains template. "
                    "Please edit the note in Zotero before building summaries."
                )

            # Parse tags (one per line)
            content = self.clean_template_content(content)
            tags = [line.strip() for line in content.split('\n') if line.strip()]

            if not tags:
                raise ValueError("Research Tags note is empty. Please add tags.")

            return tags

    raise FileNotFoundError(
        "Research Tags note not found in ZoteroResearcher subcollection. "
        "Run --init-collection first."
    )
```

### 5. Report Output as Note

**Create Research Report Note:**
```python
def create_research_report_note(
    self,
    subcollection_key: str,
    brief_title: str,
    brief_content: str,
    relevant_sources: List[Dict],
    stats: Dict,
    brief_item_key: Optional[str] = None
) -> str:
    """
    Create research report as a note in ZoteroResearcher subcollection.

    Args:
        subcollection_key: Key of ZoteroResearcher subcollection
        brief_title: Title of research brief
        brief_content: Full research brief text
        relevant_sources: List of relevant sources with summaries
        stats: Processing statistics
        brief_item_key: Optional item key of original brief note for linking

    Returns:
        Item key of created report note
    """
    # Generate HTML report content (similar to current compile_research_html)
    html_content = self._build_report_html(
        brief_title, brief_content, relevant_sources, stats
    )

    # Create report note
    timestamp = datetime.now().strftime("%Y-%m-%d")
    brief_short = brief_title[:50] + "..." if len(brief_title) > 50 else brief_title
    title = f"📊 Research Report: {brief_short} - {timestamp}"

    tags = ['ZoteroResearcher', 'ResearchReport']

    report_key = self.create_standalone_note(
        subcollection_key,
        title,
        html_content,
        tags
    )

    # Link to original brief if provided
    if brief_item_key:
        # TODO: Use Zotero relations API to link report to brief
        pass

    return report_key
```

## CLI Changes

### New Commands

**Initialize Collection:**
```bash
python researcher.py --init-collection --collection COLLECTION_KEY [--force]
```

**Build Summaries (Zotero-native mode):**
```bash
python researcher.py --build-summaries --collection COLLECTION_KEY [--force]
```
- Looks for ZoteroResearcher subcollection
- Loads project overview and tags from notes
- Falls back to file-based mode if `--project-overview` and `--tags` provided

**Query Summary (Zotero-native mode):**
```bash
python researcher.py --query-summary --collection COLLECTION_KEY \
    [--brief-title "Partial Title"] \
    [--threshold 6] \
    [--use-sonnet]
```
- Looks for research brief notes in ZoteroResearcher subcollection
- If multiple found, prompts user to select
- Optional `--brief-title` to filter/select specific brief
- Creates report note in ZoteroResearcher subcollection

### Updated Help Text

```
usage: researcher.py [-h]
                     [--list-collections]
                     [--init-collection]
                     [--build-summaries]
                     [--query | --query-summary]
                     [--collection COLLECTION]
                     [--project-overview FILE]
                     [--tags FILE]
                     [--brief FILE]
                     [--brief-title TEXT]
                     [--threshold N]
                     [--max-sources N]
                     [--force]
                     [--use-sonnet]
                     [--verbose]

Zotero Research Assistant - Two-phase workflow with Zotero-native storage

Workflow Modes:
  --list-collections    List available collections
  --init-collection     Initialize collection with ZoteroResearcher subcollection
  --build-summaries     Build general summaries (Phase 1)
  --query               Query with research brief from file (legacy)
  --query-summary       Query with research brief from Zotero note (new)

Collection:
  --collection KEY      Collection key to process

Configuration (file-based mode):
  --project-overview FILE    Path to project overview file
  --tags FILE                Path to tags file
  --brief FILE               Path to research brief file

Configuration (Zotero-native mode):
  --brief-title TEXT    Filter research briefs by title (optional)

Options:
  --threshold N         Relevance threshold 0-10 (default: 6)
  --max-sources N       Max sources to process (default: 50)
  --force               Force rebuild/recreate
  --use-sonnet          Use Sonnet for high-quality summaries (default: Haiku)
  --verbose, -v         Show detailed information

Examples:
  # Zotero-native workflow (recommended)
  python researcher.py --init-collection --collection ABC123
  # Edit notes in Zotero UI: Project Overview, Research Tags
  python researcher.py --build-summaries --collection ABC123
  # Create research brief note in Zotero UI
  python researcher.py --query-summary --collection ABC123

  # File-based workflow (legacy)
  python researcher.py --build-summaries --collection ABC123 \
      --project-overview overview.txt --tags tags.txt
  python researcher.py --query --collection ABC123 --brief brief.txt
```

## Implementation Order

1. **Subcollection Management** (2 hours)
   - `create_researcher_subcollection()`
   - `get_researcher_subcollection()`
   - `create_standalone_note()`
   - `get_collection_notes()`
   - `get_note_title()`

2. **Initialize Collection Command** (2 hours)
   - Create template notes with emojis and formatting
   - Handle --force flag for recreation
   - User-friendly output messages

3. **Configuration Loading from Zotero** (2 hours)
   - `load_project_overview_from_zotero()`
   - `load_tags_from_zotero()`
   - Template detection and validation
   - Clean content extraction

4. **Build Summaries Integration** (1 hour)
   - Update --build-summaries to detect mode (file vs Zotero)
   - Load from Zotero if no files provided
   - Maintain backward compatibility

5. **Research Brief Discovery** (2 hours)
   - Discover research brief notes in subcollection
   - Interactive selection if multiple found
   - `--brief-title` filter support

6. **Report Note Generation** (3 hours)
   - Convert HTML report to note format
   - `create_research_report_note()`
   - Link to original brief
   - Set appropriate metadata and tags

7. **Query Summary Command** (1 hour)
   - Implement --query-summary workflow
   - Integrate with existing query logic
   - Output report as note instead of file

8. **CLI Updates** (1 hour)
   - Update argument parser
   - Update help text and examples
   - Mode detection logic

9. **Testing** (2 hours)
   - Test initialize workflow
   - Test build with Zotero config
   - Test query with Zotero brief
   - Test multi-brief selection
   - Test error cases (missing templates, etc.)

10. **Documentation** (1 hour)
    - Update CLAUDE.md
    - Add workflow examples
    - Migration guide

**Total Estimated Effort: ~17 hours**

## Optional Future Enhancements

**Phase 2 (Later):**
1. **Source Organization on Init:**
   - Check each source for type (HTML, PDF)
   - If attachment is parent node, restructure as child
   - Create proper parent node with extracted metadata
   - This improves Zotero library organization

2. **Export Research Report:**
   - Add `--export-html` flag to also save report as HTML file
   - Add `--export-pdf` flag to generate PDF from note

3. **Batch Processing:**
   - Process all research briefs in subcollection at once
   - `--query-all` command

4. **Report Management:**
   - Archive old reports
   - Compare reports across queries
   - Report version tracking

## Design Decisions (Approved)

1. **Report Note Size:** If report > 1MB:
   - Output as HTML file instead
   - Create short stub note with message: "Report too large for Zotero note. Saved to: report_filename.html"
   - ✓ **Approved**

2. **Brief Selection:** Use standard filename "Research Brief" - no discovery/selection needed:
   - Single standard note name eliminates ambiguity
   - User replaces content for each query (or duplicates and renames for history)
   - ✓ **Approved**

3. **Template Markers:** Plain text only (no emojis):
   - "Project Overview"
   - "Research Tags"
   - "Research Brief"
   - More compatible and searchable
   - ✓ **Approved**

4. **Related Items:** Link report to brief only, not all sources
   - Avoids creating excessive relations
   - ✓ **Approved**

5. **Legacy Mode:** Keep file-based mode for debugging purposes
   - Both modes supported indefinitely
   - ✓ **Approved**

6. **Restructure Attachments:** Defer to future phase
   - Not included in current implementation
   - ✓ **Approved**

## Success Criteria

- [ ] Can initialize collection with one command
- [ ] Templates are clear and easy to edit in Zotero UI
- [ ] Configuration loads successfully from Zotero notes
- [ ] Research briefs can be discovered and selected
- [ ] Report notes are well-formatted and readable in Zotero
- [ ] Zotero links (zotero://select/...) work correctly
- [ ] Entire workflow is completable without external files
- [ ] Backward compatibility with file-based mode maintained
- [ ] Clear error messages guide users through workflow

---

**Created:** 2025-01-15
**Status:** Draft - Awaiting Review
