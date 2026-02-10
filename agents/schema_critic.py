"""Schema Critic Agent — validates proposed artifacts at each pipeline stage.

Stateless validator that pre-computes context and injects it into the system
prompt. Supports two scopes:

- "structured": Validates the construction plan against CSV files.
- "unstructured": Validates entity types and fact types against markdown files.

Uses a single submit_review tool for structured verdicts.
No conversation history needed — each validation is independent.
"""

import json

from core import run_agent_sync, get_approved
from tools.schema_tools import (
    TOOL_SUBMIT_REVIEW,
    handle_submit_review,
    build_file_context,
)
from tools.extraction_tools import (
    build_markdown_context,
    build_well_known_types,
)


STRUCTURED_PROMPT_TEMPLATE = """\
You are an expert at knowledge graph modeling with property graphs. \
Your job is to validate the proposed construction plan against the source data \
and user goal.

USER GOAL:
- Kind: {user_goal_kind}
- Description: {user_goal_description}

APPROVED FILE DATA (structured CSV files only):
{file_context}

CURRENT PROPOSED CONSTRUCTION PLAN:
{construction_plan}

VALIDATION RULES:

Criticize the proposed schema for relevance and correctness:
- Are unique identifiers actually unique? Check the sample data above for duplicates.
- Could any nodes be relationships instead? Double-check that unique identifiers are \
unique and not references to other nodes.
- Can you manually trace through the source data to find the necessary information for \
answering a hypothetical question?
- Is every node in the schema connected? What relationships could be missing? \
Every node should connect to at least one other node.
- Are hierarchical container relationships missing?
- Are any relationships redundant? A relationship between two nodes is redundant if it \
is semantically equivalent to or the inverse of another relationship between those two nodes.
- Do the column references in the plan match the actual column names in the files?
- For each relationship, trace a sample row from its source file:
  1. Read the from_node_column value — does it match exactly one FROM node's unique identifier?
  2. Read the to_node_column value — does it match exactly one TO node's unique identifier?
  If either lookup fails, the column reference is wrong.

INSTRUCTIONS:

Analyze the construction plan against the file data above. You have all the context \
you need -- do NOT ask for more information.

You are validating ONLY the structured data construction plan. Unstructured files \
(markdown) are handled by separate NER and Fact Extraction stages -- do NOT flag \
their absence from the plan.

After completing your analysis, you MUST call the 'submit_review' tool:
- If the schema is correct, call submit_review with verdict "valid" and an empty \
problems list.
- If the schema has problems, call submit_review with verdict "retry" and a list \
of specific, actionable problems to fix.\
"""


UNSTRUCTURED_PROMPT_TEMPLATE = """\
You are an expert at knowledge graph modeling with property graphs. \
Your job is to validate the proposed entity types and fact types against the \
source text and user goal.

USER GOAL:
- Kind: {user_goal_kind}
- Description: {user_goal_description}

WELL-KNOWN ENTITY TYPES (from the construction plan):
{well_known_types}

APPROVED FILE PREVIEWS (unstructured text):
{file_context}

PROPOSED ENTITY TYPES:
{entity_types}

PROPOSED FACT TYPES:
{fact_types}

VALIDATION RULES -- ENTITY TYPES:

1. Well-known coverage: For each well-known type listed above, check if it \
appears in the text previews. If a well-known type is NOT included in the \
proposed entity types but IS mentioned in the text, flag it as missing.

2. Text grounding: For each proposed entity type, verify that examples of \
that type actually appear in the file previews. If you cannot find any \
mentions of a proposed type in the text, flag it as ungrounded.

3. No overlapping types: Check for entity types that capture the same concept \
under different names (e.g., "Defect" and "Issue" both meaning product problems). \
Flag overlaps and recommend which to keep.

4. No quantities as entities: Entity types should represent things, not \
measurements. Types like "Rating", "Price", "Age", "Count" should be properties \
on another entity, not standalone types. Flag any proposed types that are \
quantities or measurements.

5. Goal relevance: Every proposed entity type should clearly support the \
user's stated goal. Flag types that have no obvious connection to the goal.

6. Format: Entity type names should be PascalCase singular nouns (e.g., \
"ProductIssue", not "product_issues" or "Issues").

VALIDATION RULES -- FACT TYPES (skip if none proposed):

7. Entity membership: Both subject and object of every fact type must be \
proposed entity types. Flag any fact type that references a type not in the \
entity types list.

8. Predicate specificity: Flag vague predicates like "related_to", \
"associated_with", "connected_to", "has_relationship". Predicates should \
describe a specific, meaningful connection.

9. No redundant relationships: Check for fact types that are semantically \
equivalent or inverse of each other (e.g., "has_issue" and "issue_of" between \
the same two types). Flag redundancies.

10. Text grounding: For each proposed fact type, verify that the relationship \
pattern appears in the file previews. Can you find sentences where the subject \
and object co-occur in the described relationship? If not, flag as ungrounded.

11. Predicate format: Predicates should be lowercase_with_underscores \
(e.g., "has_issue", not "HAS_ISSUE" or "hasIssue"). Flag format violations.

12. Directionality: Check that the subject-object direction makes semantic \
sense. For example, (Product)-[has_issue]->(Issue) is correct, but \
(Issue)-[has_issue]->(Product) is backwards. Flag suspicious directionality.

INSTRUCTIONS:

Analyze the proposed entity types (and fact types, if present) against the \
file previews above. You have all the context you need -- do NOT ask for \
more information.

After completing your analysis, you MUST call the 'submit_review' tool:
- If the proposals are correct, call submit_review with verdict "valid" and \
an empty problems list.
- If the proposals have problems, call submit_review with verdict "retry" and \
a list of specific, actionable problems to fix.\
"""


def _format_entity_types(state: dict) -> str:
    """Get entity types for validation -- proposed takes priority over approved."""
    entities = state.get("proposed_entity_types") or state.get("approved_entity_types", {})
    if not entities:
        return "(none)"
    lines = []
    for name, details in entities.items():
        source = details.get("source", "unknown")
        description = details.get("description", "No description")
        lines.append(f"- {name} ({source}): {description}")
    return "\n".join(lines)


def _format_fact_types(state: dict) -> str:
    """Format fact types for validation -- proposed takes priority over approved."""
    facts = state.get("proposed_fact_types") or state.get("approved_fact_types", {})
    if not facts:
        return "(none -- only entity types are available for validation)"
    lines = []
    for predicate, triple in facts.items():
        subj = triple.get("subject_label", "?")
        obj = triple.get("object_label", "?")
        lines.append(f"- ({subj})-[{predicate}]->({obj})")
    return "\n".join(lines)


class SchemaCriticAgent:
    """Stateless critic agent for on-demand validation.

    Supports two scopes:
    - "structured": Validates the construction plan against CSV files.
    - "unstructured": Validates entity types and fact types against markdown files.

    Pre-computes context and injects it into the system prompt.
    No conversation history needed -- each validation is independent.
    """

    def __init__(self):
        self.tools = [TOOL_SUBMIT_REVIEW]
        self.tool_handlers = {"submit_review": handle_submit_review}

    def run(self, state: dict, scope: str = "structured") -> tuple[str, dict]:
        """Run a single-shot validation.

        Args:
            state: Current state dictionary.
            scope: What to validate. "structured" validates the construction
                plan against CSV files. "unstructured" validates entity types
                and fact types against markdown files.

        Returns:
            (response text, updated state with _critic_verdict/_critic_problems)
        """
        # Extract user goal (shared by both scopes)
        user_goal = get_approved(state, "user_goal") or {}
        user_goal_kind = user_goal.get("kind_of_graph", "unknown")
        user_goal_description = user_goal.get("graph_description", "No description available.")

        if scope == "structured":
            file_context = build_file_context(state, scope="structured") or "No approved files found."

            plan = state.get("proposed_construction_plan", {})
            construction_plan = json.dumps(plan, indent=2) if plan else "No plan proposed yet."

            system_prompt = STRUCTURED_PROMPT_TEMPLATE.format(
                user_goal_kind=user_goal_kind,
                user_goal_description=user_goal_description,
                file_context=file_context,
                construction_plan=construction_plan,
            )
            message = "Validate the proposed construction plan."

        elif scope == "unstructured":
            file_context = build_markdown_context(state) or "No approved markdown files found."
            well_known_types = build_well_known_types(state)
            entity_types = _format_entity_types(state)
            fact_types = _format_fact_types(state)

            system_prompt = UNSTRUCTURED_PROMPT_TEMPLATE.format(
                user_goal_kind=user_goal_kind,
                user_goal_description=user_goal_description,
                well_known_types=well_known_types,
                file_context=file_context,
                entity_types=entity_types,
                fact_types=fact_types,
            )

            if state.get("proposed_fact_types") or state.get("approved_fact_types"):
                message = "Validate the proposed entity types and fact types."
            else:
                message = "Validate the proposed entity types."

        else:
            raise ValueError(f"Invalid scope: {scope}. Use 'structured' or 'unstructured'.")

        response, state, _ = run_agent_sync(
            message=message,
            state=state,
            system_prompt=system_prompt,
            tools=self.tools,
            tool_handlers=self.tool_handlers,
            conversation=None,
        )

        return response, state
