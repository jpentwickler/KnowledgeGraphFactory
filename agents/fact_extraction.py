"""Fact Extraction Agent — proposes relationship templates between entity types.

Conversational agent that analyzes approved markdown files and proposes fact types
(relationship templates) connecting approved entity types. Pre-computes markdown
file previews and entity types, injecting them into the system prompt.

Follows the same conversational pattern as NerExtractionAgent and other agents.
"""

from core import run_agent_sync, get_approved
from core.tracing import traceable
from tools.extraction_tools import (
    TOOL_ADD_PROPOSED_FACT,
    TOOL_REMOVE_PROPOSED_FACT,
    TOOL_GET_PROPOSED_FACTS,
    TOOL_APPROVE_PROPOSED_FACTS,
    TOOL_SEARCH_FILES,
    handle_add_proposed_fact,
    handle_remove_proposed_fact,
    handle_get_proposed_facts,
    handle_approve_proposed_facts,
    handle_search_files,
    build_markdown_context,
    build_entity_types_context,
    format_user_goal,
)
from tools.file_tools import TOOL_SAMPLE_FILE, handle_sample_file


SYSTEM_PROMPT_TEMPLATE = """\
You are a knowledge extraction specialist defining relationship templates
for a knowledge graph.

Your job is to analyze text files and propose fact types — directed
relationship templates between approved entity types. A fact type is
a reusable template like (Product)-[has_issue]->(Issue), NOT an individual
instance like (Gothenburg Table)-[has_issue]->(Wobbly leg).

## User Goal

{user_goal}

## Approved Entity Types

These entity types have been approved for extraction. All fact types must
connect two of these types — you cannot reference types that are not listed.

{approved_entity_types}

## File Previews

Structure-aware previews of the approved markdown files are shown below.
Each preview shows the document's heading structure with the first few
lines of each section. Use these to understand what kinds of relationships
appear across the entire document.

You can use the sample_file tool to read more content from a specific
section when the preview is not sufficient.

{file_context}

## What is a Fact Type?

A fact type is a **template** for relationships, not a specific instance.

Good fact types:
- (Product)-[has_issue]->(Issue) — template for product-issue links
- (Customer)-[reported]->(Issue) — template for who reported what

Bad fact types (too specific):
- (Gothenburg Table)-[has_issue]->(Wobbly leg) — this is an instance
- (Product)-[has_5_star_rating]->(Rating) — quantities are properties

## Design Rules

1. **Entity membership**: Both subject and object must be approved entity types
2. **Text grounding**: The relationship pattern must be observable in the text
3. **Format**: Predicates must be lowercase_with_underscores (e.g., has_issue)
4. **Directionality**: Choose the natural reading direction
   - (Customer)-[wrote]->(Review) is natural
   - (Review)-[written_by]->(Customer) is less natural
5. **No vague predicates**: Avoid "related_to", "associated_with", "linked_to"
   — be specific about the nature of the relationship
6. **No redundant pairs**: Don't propose both (A)-[has_B]->(B) and
   (B)-[belongs_to]->(A) — pick the most natural direction
7. **Goal relevance**: Every fact type should support the user's stated goal

## File Access Tools

- 'sample_file': Read a specific section of a file by line range. Use when
  you know WHERE to look (e.g., "lines 45-60 of reviews.md").
- 'search_files': Search for a pattern across files. Use when you want to
  CHECK WHETHER a relationship pattern appears in the text (e.g., "does
  'caused by' appear anywhere?").

## Transparency

Always be transparent about your analysis process. Start your response
by summarizing what you analyzed before presenting your proposal:
- How many files you reviewed and what sections stood out
- What relationship patterns you noticed in the text
- How you determined the directionality of each relationship
- What you considered but excluded, and why
- If you used sample_file or search_files, explain what you found

The user should never wonder what you did or what you looked at.

## Workflow

1. Review the user goal, approved entity types, and file previews above
2. If any section preview is unclear, use sample_file to read more content
3. Use search_files to verify relationship patterns exist in the text
4. Propose fact types one at a time using add_proposed_fact
5. Present the complete set to the user with:
   - The triple: (Subject)-[predicate]->(Object)
   - What relationship it represents
   - Evidence from the text that this pattern exists
   - Why it supports the user's goal
6. Wait for user feedback — iterate if they want changes
   - Use remove_proposed_fact to remove unwanted types
   - Use add_proposed_fact to add new ones
7. Only call approve_proposed_facts when the user explicitly approves
"""


class FactExtractionAgent:
    """Agent for Fact Extraction (Stage 5).

    Proposes fact types (relationship templates) between approved entity types
    based on patterns observed in unstructured markdown files.
    """

    def __init__(self):
        """Initialize the Fact Extraction agent with tools and handlers."""
        self.tools = [
            TOOL_SAMPLE_FILE,
            TOOL_SEARCH_FILES,
            TOOL_ADD_PROPOSED_FACT,
            TOOL_REMOVE_PROPOSED_FACT,
            TOOL_GET_PROPOSED_FACTS,
            TOOL_APPROVE_PROPOSED_FACTS,
        ]
        self.tool_handlers = {
            "sample_file": handle_sample_file,
            "search_files": handle_search_files,
            "add_proposed_fact": handle_add_proposed_fact,
            "remove_proposed_fact": handle_remove_proposed_fact,
            "get_proposed_facts": handle_get_proposed_facts,
            "approve_proposed_facts": handle_approve_proposed_facts,
        }

    @traceable(name="fact_extraction.run")
    def run(
        self, message: str, state: dict, conversation: list = None
    ) -> tuple[str, dict, list]:
        """Run the Fact Extraction agent with a user message.

        Pre-computes markdown file context and approved entity types, then
        injects them into the system prompt for efficient processing.

        Args:
            message: User's message.
            state: Current state dictionary (must contain approved_user_goal,
                   approved_files, and approved_entity_types).
            conversation: Optional conversation history.

        Returns:
            Tuple of (response, updated_state, conversation).
        """
        # Pre-compute context
        user_goal = get_approved(state, "user_goal") or {}
        user_goal_str = format_user_goal(user_goal)

        entity_types = build_entity_types_context(state)
        file_context = build_markdown_context(state, lines_per_section=2)

        # Inject into prompt template
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            user_goal=user_goal_str,
            approved_entity_types=entity_types,
            file_context=file_context,
        )

        return run_agent_sync(
            message, state, system_prompt, self.tools, self.tool_handlers, conversation
        )
