#!/usr/bin/env python3
"""
ZoteroResearcher Initialization Module

Handles collection initialization with project templates.
"""

# Handle both relative and absolute imports
try:
    from .zr_common import ZoteroResearcherBase
except ImportError:
    from zr_common import ZoteroResearcherBase


class ZoteroResearcherInit(ZoteroResearcherBase):
    """Handles initialization of collections with project-specific templates."""

    def init_collection(self, collection_key: str, force: bool = False) -> bool:
        """
        Initialize a collection for use with ZoteroResearcher.

        Creates a project-specific subcollection and populates it with
        template notes for configuration.

        Args:
            collection_key: The Zotero collection key to initialize
            force: If True, recreate templates even if subcollection exists

        Returns:
            True if initialization successful
        """
        subcollection_name = self._get_subcollection_name()

        print(f"\n{'='*80}")
        print(f"Initializing Collection for Project: {self.project_name}")
        print(f"{'='*80}\n")

        # Check if subcollection already exists
        existing_key = self.get_subcollection(collection_key, subcollection_name)

        if existing_key and not force:
            print(f"⚠️  Project already initialized with {subcollection_name} subcollection")
            print(f"   Subcollection Key: {existing_key}")
            print(f"\n   Options:")
            print(f"   1. Use existing configuration (edit notes in Zotero)")
            print(f"   2. Recreate templates (run with --force flag)")
            print(f"\n   Run with --force to recreate template notes.\n")
            return False

        # Create or get subcollection
        print(f"Creating {subcollection_name} subcollection...")
        subcollection_key = self.create_subcollection(collection_key, subcollection_name)

        if not subcollection_key:
            print(f"❌ Failed to create subcollection")
            return False

        print(f"✅ Subcollection created: {subcollection_key}\n")

        # Create template notes
        print(f"Creating configuration templates...\n")

        # Template 1: Project Overview
        project_overview_content = """[TODO: Replace this template with your project description]

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
Edit this note before running --build-summaries"""

        overview_key = self.create_standalone_note(
            subcollection_key,
            project_overview_content,
            self._get_project_overview_note_title(),
            convert_markdown=True
        )

        if overview_key:
            print(f"   ✅ Created: {self._get_project_overview_note_title()}")
        else:
            print(f"   ❌ Failed to create: {self._get_project_overview_note_title()}")

        # Template 2: Research Tags
        research_tags_content = """[TODO: Replace this template with your tag list]

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
Edit this note before running --build-summaries"""

        tags_key = self.create_standalone_note(
            subcollection_key,
            research_tags_content,
            self._get_research_tags_note_title(),
            convert_markdown=True
        )

        if tags_key:
            print(f"   ✅ Created: {self._get_research_tags_note_title()}")
        else:
            print(f"   ❌ Failed to create: {self._get_research_tags_note_title()}")

        # Template 3: Research Brief
        research_brief_content = """[TODO: Replace this template with your specific research question]

State your specific research question or topic. This will be used
to evaluate source relevance and generate targeted summaries.

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
Edit this note before running --query-summary"""

        brief_key = self.create_standalone_note(
            subcollection_key,
            research_brief_content,
            self._get_research_brief_note_title(),
            convert_markdown=True
        )

        if brief_key:
            print(f"   ✅ Created: {self._get_research_brief_note_title()}")
        else:
            print(f"   ❌ Failed to create: {self._get_research_brief_note_title()}")

        # Template 4: Query Request (for File Search)
        query_request_content = """[TODO: Replace this template with your File Search query]

Enter your query for the Gemini File Search feature. This will be used
to search across all uploaded files in your collection using RAG.

Example:
What are the main findings and statistical evidence about the impact
of AI-assisted code generation on developer productivity? Please cite
specific studies and include quantitative results where available.

---
Template created by ZoteroResearcher
Edit this note before running --file-search"""

        query_request_key = self.create_standalone_note(
            subcollection_key,
            query_request_content,
            self._get_query_request_note_title(),
            convert_markdown=True
        )

        if query_request_key:
            print(f"   ✅ Created: {self._get_query_request_note_title()}")
        else:
            print(f"   ❌ Failed to create: {self._get_query_request_note_title()}")

        # Template 5: Project Configuration
        # Wrap in code block for proper formatting (monospace, preserved line breaks)
        config_template = self._get_default_config_template()
        config_content = f"```\n{config_template}\n```"

        config_key = self.create_standalone_note(
            subcollection_key,
            config_content,
            self._get_project_config_note_title(),
            convert_markdown=True  # Convert to HTML for proper rendering
        )

        if config_key:
            print(f"   ✅ Created: {self._get_project_config_note_title()}")
        else:
            print(f"   ❌ Failed to create: {self._get_project_config_note_title()}")

        # Final output
        print(f"\n{'='*80}")
        print(f"✅ Project Initialized Successfully")
        print(f"{'='*80}\n")
        print(f"{subcollection_name} subcollection created: {subcollection_key}\n")
        print(f"Configuration templates created:")
        print(f"   - {self._get_project_overview_note_title()} (edit before building summaries)")
        print(f"   - {self._get_research_tags_note_title()} (edit before building summaries)")
        print(f"   - {self._get_research_brief_note_title()} (edit before running --query-summary)")
        print(f"   - {self._get_query_request_note_title()} (edit before running --file-search)")
        print(f"   - {self._get_project_config_note_title()} (optional: customize project settings)\n")
        print(f"Next steps:")
        print(f"   1. Open the '{subcollection_name}' subcollection in Zotero")
        print(f"   2. Edit '{self._get_project_overview_note_title()}' with your project description")
        print(f"   3. Edit '{self._get_research_tags_note_title()}' with your tag list")
        print(f"   4. Edit '{self._get_research_brief_note_title()}' with your research question (for --query-summary)")
        print(f"   5. Edit '{self._get_query_request_note_title()}' with your search query (for --file-search)")
        print(f"   6. (Optional) Edit '{self._get_project_config_note_title()}' to customize settings")
        print(f"   7. Run: python zresearcher.py --build-summaries --collection {collection_key} --project \"{self.project_name}\"")
        print(f"{'='*80}\n")

        return True

    def list_projects(self, collection_key: str):
        """
        List all ZResearcher projects in a collection.

        Args:
            collection_key: Collection key to scan for projects
        """
        print(f"\n{'='*80}")
        print(f"ZResearcher Projects in Collection")
        print(f"{'='*80}\n")
        print(f"Scanning for project subcollections...\n")

        # Get all subcollections
        try:
            subcollections = self.zot.collections_sub(collection_key)
        except Exception as e:
            print(f"❌ Error fetching subcollections: {e}")
            return

        # Filter for ZResearcher projects
        projects = []
        for subcoll in subcollections:
            name = subcoll['data'].get('name', '')
            # Match pattern: 【ZResearcher: PROJECT_NAME】
            if name.startswith('【ZResearcher:') and name.endswith('】'):
                # Extract project name
                project_name = name[len('【ZResearcher:'):-1].strip()
                projects.append({
                    'name': project_name,
                    'subcollection_name': name,
                    'key': subcoll['key'],
                    'num_items': subcoll['meta'].get('numItems', 0)
                })

        if not projects:
            print("No ZResearcher projects found in this collection.")
            print("\nTo create a project, run:")
            print(f"  python zresearcher.py --init-collection --collection {collection_key} --project \"PROJECT_NAME\"\n")
            return

        print(f"Found {len(projects)} project(s):\n")

        for idx, project in enumerate(projects, 1):
            print(f"{idx}. {project['name']}")
            print(f"   Subcollection: {project['subcollection_name']}")
            print(f"   Key: {project['key']}")
            print(f"   Items: {project['num_items']}")

            # Check for sources with summaries
            try:
                items = self.get_collection_items(collection_key)
                summaries_count = 0
                summary_prefix = f"【ZResearcher Summary: {project['name']}】"

                for item in items:
                    item_type = item['data'].get('itemType')
                    if item_type in ['attachment', 'note']:
                        continue
                    if self.has_note_with_prefix(item['key'], summary_prefix, collection_key):
                        summaries_count += 1

                print(f"   Sources with summaries: {summaries_count}/{len([i for i in items if i['data'].get('itemType') not in ['attachment', 'note']])}")
            except Exception:
                print(f"   Sources with summaries: Unable to count")

            print()

        print(f"{'='*80}\n")
