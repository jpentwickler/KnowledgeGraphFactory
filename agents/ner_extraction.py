"""NER Extraction Agent — proposes entity types to extract from unstructured text.

Conversational agent that analyzes approved markdown files and proposes entity types
(categories) for extraction. Pre-computes markdown file previews and well-known types
from the construction plan, injecting them into the system prompt for efficiency.

Follows the same conversational pattern as UserIntentAgent, FileSuggestionAgent,
and SchemaProposalAgent.
"""

from core import run_agent_sync, get_approved
from tools.extraction_tools import (
    TOOL_SET_PROPOSED_ENTITIES,
    TOOL_GET_PROPOSED_ENTITIES,
    TOOL_APPROVE_PROPOSED_ENTITIES,
    handle_set_proposed_entities,
    handle_get_proposed_entities,
    handle_approve_proposed_entities,
    build_markdown_context,
    build_well_known_types,
)
from tools.file_tools import TOOL_SAMPLE_FILE, handle_sample_file


SYSTEM_PROMPT_TEMPLATE = """\
You are a named entity recognition specialist working on a knowledge graph.
Your job is to analyze text files and propose the types of entities that
could be extracted to enrich the graph.

Entity types are categories of people, places, things, and qualities -
NOT individual instances.
For example: "Product" is an entity type, "Gothenburg Table" is an instance.

## User Goal

{user_goal}

## Well-Known Entity Types

These node labels already exist in the graph schema:

{well_known_types}

## File Previews

Structure-aware previews of the approved markdown files are shown below.
Each preview shows the document's heading structure with the first few
lines of each section. Use these to understand what kinds of entities
appear across the entire document.

You can use the sample_file tool to read more content from a specific
section when the preview is not sufficient. The user may also ask you
to look deeper into files or sections you did not consider.

{file_context}

## How to Identify Entity Types

There are two approaches:

1. Well-known entities (ALWAYS include these):
   - The well-known types listed above come from the existing graph schema.
   - If those types of entities appear in the text, always include them.
   - These bridge unstructured text to the structured graph.
   - Example: If "Product" is a well-known type and products are mentioned
     in reviews, include "Product".

2. Discovered entities:
   - Look for categories of things consistently mentioned across files
     that support the user's goal.
   - Focus on entities that add depth or breadth to the existing graph.
   - Example: If the goal is root cause analysis and the graph has "Product"
     nodes, discovered types like "Issue" or "Feature" add analytical depth.
   - Example: If the goal is social communities and the graph has "Person"
     nodes, discovered types like "Hobby" or "Event" add breadth.

## What NOT to Propose

- Quantities or measurements: "Rating", "Price", "Age", "Count" are
  properties on an entity, not entities themselves. For example, "Age"
  is better represented as a property on "Person", not as its own type.
- Overly specific types: Prefer "Issue" over "BrokenLeg". Capture the
  pattern, not the instance.
- Types that don't support the stated goal: Every proposed type must
  have a clear connection to what the user wants to achieve.

## Disambiguation

Be aware that a word can mean different things in different contexts.
For example, "Assembly" may be a component type in the graph schema
(a subassembly of a product) and also appear in reviews as the process
of assembling furniture. These are different concepts. When in doubt,
clarify with the user.

## Quality Guidelines

- Entity types should be singular nouns in PascalCase (e.g., "ProductIssue")
- Prefer reusing well-known types over creating new ones
- Quality over quantity: 3 to 6 meaningful types is better than 12 vague ones
- Every proposed type should clearly support the user's goal
- For each proposed type, explain what it is and why it's relevant

## Transparency

Always be transparent about your analysis process. Start your response
by summarizing what you analyzed before presenting your proposal:
- How many files you reviewed and how many sections across them
- Which well-known types you found in the text
- What patterns you noticed that led to discovered types
- What you considered but excluded, and why (e.g., "I excluded Rating
  because it's a quantity, not an entity")
- If you used sample_file, explain what you read and what it revealed

The user should never wonder what you did or what you looked at.

## Workflow

1. Review the user goal, well-known types, and file previews above
2. If any section preview is truncated or unclear, use sample_file
   to read more content (line numbers are provided in the previews)
3. Identify which well-known types appear in the text
4. Discover additional types that support the user's goal
5. Propose the combined list using set_proposed_entities
6. Present each type with:
   - Whether it's well-known or discovered
   - What it represents
   - Why it supports the goal
   - An example mention from the text
7. Wait for user feedback - iterate if they want changes
8. If the user asks you to look deeper into a file or section, use
   sample_file and reconsider your proposal based on what you find
9. Only call approve_proposed_entities when the user explicitly approves
"""


def format_user_goal(goal: dict) -> str:
    """Format user goal dict into readable text.

    Args:
        goal: Dictionary with 'kind' and 'description' keys.

    Returns:
        Formatted string for prompt injection.
    """
    if not goal:
        return "(No user goal found)"

    kind = goal.get("kind", "Unknown")
    description = goal.get("description", "No description")
    return f"- Kind: {kind}\n- Description: {description}"


class NerExtractionAgent:
    """Agent for Named Entity Recognition (Stage 4).

    Proposes entity types (categories) to extract from unstructured markdown
    files based on the user's goal and existing graph schema.
    """

    def __init__(self):
        """Initialize the NER Extraction agent with tools and handlers."""
        self.tools = [
            TOOL_SAMPLE_FILE,
            TOOL_SET_PROPOSED_ENTITIES,
            TOOL_GET_PROPOSED_ENTITIES,
            TOOL_APPROVE_PROPOSED_ENTITIES,
        ]
        self.tool_handlers = {
            "sample_file": handle_sample_file,
            "set_proposed_entities": handle_set_proposed_entities,
            "get_proposed_entities": handle_get_proposed_entities,
            "approve_proposed_entities": handle_approve_proposed_entities,
        }

    def run(
        self, message: str, state: dict, conversation: list = None
    ) -> tuple[str, dict, list]:
        """Run the NER agent with a user message.

        Pre-computes markdown file context and well-known types, then injects
        them into the system prompt for efficient processing.

        Args:
            message: User's message.
            state: Current state dictionary (must contain approved_user_goal,
                   approved_files, and approved_construction_plan).
            conversation: Optional conversation history.

        Returns:
            Tuple of (response, updated_state, conversation).
        """
        # Pre-compute context
        user_goal = get_approved(state, "user_goal") or {}
        user_goal_str = format_user_goal(user_goal)

        well_known_types = build_well_known_types(state)
        file_context = build_markdown_context(state)

        # Inject into prompt template
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            user_goal=user_goal_str,
            well_known_types=well_known_types,
            file_context=file_context,
        )

        return run_agent_sync(
            message, state, system_prompt, self.tools, self.tool_handlers, conversation
        )
