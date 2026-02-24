"""Schema Critic Agent — validates proposed artifacts at each pipeline stage.

Stateless validator that pre-computes context and injects it into the system
prompt. Supports three scopes:

- "structured": Validates the construction plan against CSV files.
- "unstructured": Validates entity types and fact types against markdown files.
- "competency": Validates competency questions against available artifacts.

Uses a single submit_review tool for structured verdicts.
No conversation history needed — each validation is independent.
"""

import json

from core import run_agent_sync, get_approved
from core.tracing import traceable
from tools.schema_tools import (
    TOOL_SUBMIT_REVIEW,
    handle_submit_review,
    build_file_context,
)
from tools.extraction_tools import (
    build_markdown_context,
    build_well_known_types,
)
from tools.competency_tools import format_competency_questions


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
- Can you trace sample rows through the proposed nodes and relationships to verify \
the data flow is correct?
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

You are validating ONLY the structured data construction plan (CSV files). \
The user goal may describe a broader knowledge graph that includes unstructured \
text sources. Your validation scope is LIMITED to the CSV data shown above. \
Do NOT flag coverage gaps for information that would come from unstructured files \
-- those are handled by separate NER and Fact Extraction pipeline stages.

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

GROUNDING EVIDENCE (gathered by the NER agent via search_files):
{entity_evidence}

This evidence was gathered by the NER agent during its analysis. For each
discovered entity type, the agent searched for relevant patterns and recorded
the results. Use this evidence to assess text grounding quality:
- Types with high mention counts across multiple files are well-grounded
- Types with 0 mentions or no evidence may be ungrounded
- Check that search patterns are relevant to the entity type
- Check that example excerpts actually support the entity type

VALIDATION RULES -- ENTITY TYPES:

1. Well-known coverage: For each well-known type listed above, check if it \
appears in the text previews. If a well-known type is NOT included in the \
proposed entity types but IS mentioned in the text, flag it as missing.

2. Search pattern relevance: For discovered types with evidence, check that \
the search patterns used are relevant to the entity type. For example, \
searching "defect" for a "Defect" type is good, but searching "the" would \
be meaningless. Flag types where the patterns don't match the concept.

3. Excerpt authenticity: Check that the example excerpts actually support \
the entity type. The excerpts should contain real mentions of the concept, \
not incidental word matches. Flag types where excerpts don't demonstrate \
genuine entity instances.

4. Evidence distribution: Check whether evidence comes from multiple files \
or is concentrated in just one. Types grounded across multiple files are \
stronger. Flag types with evidence from only one file if multiple files \
are available.

5. Evidence sufficiency: Discovered types should have meaningful evidence. \
Types with fewer than 3 total mentions may be too rare to justify as a \
separate entity type. Flag types with very low mention counts.

6. Missing evidence: Discovered types that have NO grounding evidence at \
all should be flagged. The NER agent should have gathered evidence before \
proposing discovered types. Missing evidence suggests the type was proposed \
without verification.

7. No overlapping types: Check for entity types that capture the same concept \
under different names (e.g., "Defect" and "Issue" both meaning product problems). \
Flag overlaps and recommend which to keep.

8. No quantities as entities: Entity types should represent things, not \
measurements. Types like "Rating", "Price", "Age", "Count" should be properties \
on another entity, not standalone types. Flag any proposed types that are \
quantities or measurements.

9. Goal relevance: Every proposed entity type should clearly support the \
user's stated goal. Flag types that have no obvious connection to the goal.

10. Format: Entity type names should be PascalCase singular nouns (e.g., \
"ProductIssue", not "product_issues" or "Issues").

VALIDATION RULES -- FACT TYPES (skip if none proposed):

11. Entity membership: Both subject and object of every fact type must be \
proposed entity types. Flag any fact type that references a type not in the \
entity types list.

12. Predicate specificity: Flag vague predicates like "related_to", \
"associated_with", "connected_to", "has_relationship". Predicates should \
describe a specific, meaningful connection.

13. No redundant relationships: Check for fact types that are semantically \
equivalent or inverse of each other (e.g., "has_issue" and "issue_of" between \
the same two types). Flag redundancies.

14. Text grounding: For each proposed fact type, verify that the relationship \
pattern appears in the file previews. Can you find sentences where the subject \
and object co-occur in the described relationship? If not, flag as ungrounded.

15. Predicate format: Predicates should be lowercase_with_underscores \
(e.g., "has_issue", not "HAS_ISSUE" or "hasIssue"). Flag format violations.

16. Directionality: Check that the subject-object direction makes semantic \
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


COMPETENCY_PROMPT_TEMPLATE = """\
You are an expert at knowledge graph modeling with property graphs. \
Your job is to validate the proposed competency questions against the \
user goal and any available schema artifacts.

USER GOAL:
- Kind: {user_goal_kind}
- Description: {user_goal_description}

COMPETENCY QUESTIONS TO VALIDATE:
{competency_questions}

{available_artifacts}

VALIDATION RULES:

1. Goal relevance: Every CQ should clearly connect to the stated user goal. \
Flag questions that have no obvious relationship to the goal.

2. Specificity: CQs should be specific enough to answer via graph traversal. \
Flag vague questions like "What is the data about?" or "How are things related?"

3. Answerability: Each CQ should be answerable by traversing nodes and \
relationships. Flag questions that require information not in a graph \
(e.g., "What is the future trend?").

4. No redundancy: Check for CQs that ask the same thing in different words. \
Flag duplicates and recommend which to keep.

5. Priority correctness: High-priority CQs should be core to the stated goal. \
Flag any high-priority CQ that seems peripheral, or low-priority CQs that \
seem essential.

6. Category consistency: CQs in the same category should be thematically \
related. Flag any CQ that seems miscategorized.

7. Coverage: Are there obvious aspects of the user goal that no CQ addresses? \
Flag gaps in coverage.

{schema_validation_rules}

INSTRUCTIONS:

Analyze the competency questions against the user goal and any available \
artifacts above. You have all the context you need -- do NOT ask for more \
information.

After completing your analysis, you MUST call the 'submit_review' tool:
- If the CQs are well-formed, call submit_review with verdict "valid" and \
an empty problems list.
- If the CQs have problems, call submit_review with verdict "retry" and a \
list of specific, actionable problems to fix.\
"""


def _build_available_artifacts(state: dict) -> str:
    """Dynamically build the artifacts section based on what's approved.

    Args:
        state: Current state dictionary.

    Returns:
        Formatted string describing available artifacts.
    """
    sections = []

    plan = get_approved(state, "construction_plan")
    if plan:
        plan_summary = json.dumps(plan, indent=2)
        sections.append(f"APPROVED CONSTRUCTION PLAN:\n{plan_summary}")

    entities = get_approved(state, "entity_types")
    if entities:
        lines = []
        for name, details in entities.items():
            source = details.get("source", "unknown")
            description = details.get("description", "No description")
            lines.append(f"- {name} ({source}): {description}")
        sections.append("APPROVED ENTITY TYPES:\n" + "\n".join(lines))

    facts = get_approved(state, "fact_types")
    if facts:
        lines = []
        for predicate, triple in facts.items():
            subj = triple.get("subject_label", "?")
            obj = triple.get("object_label", "?")
            lines.append(f"- ({subj})-[{predicate}]->({obj})")
        sections.append("APPROVED FACT TYPES:\n" + "\n".join(lines))

    if not sections:
        return "AVAILABLE ARTIFACTS:\n(none -- only the user goal is available)"

    return "AVAILABLE ARTIFACTS:\n\n" + "\n\n".join(sections)


def _build_schema_validation_rules(state: dict) -> str:
    """Build schema-specific validation rules based on available artifacts.

    Args:
        state: Current state dictionary.

    Returns:
        Extra validation rules for when schema artifacts are available.
    """
    rules = []

    if get_approved(state, "construction_plan"):
        rules.append(
            "8. Schema coverage: For each CQ, check whether the construction "
            "plan contains the node labels and relationship types needed to "
            "answer it. Flag CQs that reference concepts not in the schema."
        )

    if get_approved(state, "entity_types"):
        rules.append(
            "9. Entity type coverage: For each CQ, check whether the approved "
            "entity types include the categories needed. Flag CQs that assume "
            "entity types not in the approved set."
        )

    if get_approved(state, "fact_types"):
        rules.append(
            "10. Relationship coverage: For each CQ, trace the traversal path "
            "through approved fact types. Flag CQs where the needed "
            "relationship path does not exist in the approved fact types."
        )

    if not rules:
        return (
            "Note: No schema artifacts are approved yet. Validate only "
            "internal consistency, specificity, and goal relevance."
        )

    return "SCHEMA-SPECIFIC VALIDATION:\n\n" + "\n\n".join(rules)


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


def _format_entity_evidence(state: dict) -> str:
    """Format grounding evidence from proposed/approved entity types.

    Reads the grounding_evidence field stored alongside entity type proposals.
    Well-known types don't need evidence. Discovered types without evidence
    are flagged.

    Args:
        state: Current state dictionary with proposed or approved entity types.

    Returns:
        Formatted string for prompt injection.
    """
    entities = state.get("proposed_entity_types") or state.get("approved_entity_types", {})
    if not entities:
        return "(no entity types to validate)"

    lines = []
    for name, details in entities.items():
        source = details.get("source", "unknown")
        evidence = details.get("grounding_evidence")

        if source == "well_known":
            lines.append(f"- {name} (well_known): No evidence required")
        elif evidence:
            patterns = ", ".join(evidence.get("search_patterns", []))
            total = evidence.get("total_mentions", 0)
            files = evidence.get("files_with_evidence", 0)
            excerpts = evidence.get("example_excerpts", [])
            top_excerpts = excerpts[:3]
            excerpt_strs = [f'"{e}"' for e in top_excerpts]

            lines.append(
                f"- {name} (discovered): {total} mentions across {files} file(s), "
                f"patterns: [{patterns}]"
            )
            if excerpt_strs:
                lines.append(f"  Examples: {', '.join(excerpt_strs)}")
        else:
            lines.append(f"- {name} (discovered): NO EVIDENCE PROVIDED")

    return "\n".join(lines)


class SchemaCriticAgent:
    """Stateless critic agent for on-demand validation.

    Supports three scopes:
    - "structured": Validates the construction plan against CSV files.
    - "unstructured": Validates entity types and fact types against markdown files.
    - "competency": Validates competency questions against available artifacts.

    Pre-computes context and injects it into the system prompt.
    No conversation history needed -- each validation is independent.
    """

    def __init__(self):
        self.tools = [TOOL_SUBMIT_REVIEW]
        self.tool_handlers = {"submit_review": handle_submit_review}

    @traceable(name="schema_critic.run")
    def run(self, state: dict, scope: str = "structured") -> tuple[str, dict]:
        """Run a single-shot validation.

        Args:
            state: Current state dictionary.
            scope: What to validate.
                "structured" validates the construction plan against CSV files.
                "unstructured" validates entity types and fact types against
                    markdown files.
                "competency" validates competency questions against available
                    artifacts.

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
            entity_evidence = _format_entity_evidence(state)

            system_prompt = UNSTRUCTURED_PROMPT_TEMPLATE.format(
                user_goal_kind=user_goal_kind,
                user_goal_description=user_goal_description,
                well_known_types=well_known_types,
                file_context=file_context,
                entity_types=entity_types,
                fact_types=fact_types,
                entity_evidence=entity_evidence,
            )

            if state.get("proposed_fact_types") or state.get("approved_fact_types"):
                message = "Validate the proposed entity types and fact types."
            else:
                message = "Validate the proposed entity types."

        elif scope == "competency":
            # Get CQs: proposed takes priority over approved
            cqs = state.get("proposed_competency_questions") or state.get(
                "approved_competency_questions", {}
            )
            if not cqs:
                cq_text = "(none)"
            else:
                lines = []
                for cq_id, details in cqs.items():
                    q = details.get("question", "")
                    cat = details.get("category", "general")
                    pri = details.get("priority", "medium")
                    lines.append(f"- [{cq_id}] ({pri}, {cat}) {q}")
                cq_text = "\n".join(lines)

            available_artifacts = _build_available_artifacts(state)
            schema_rules = _build_schema_validation_rules(state)

            system_prompt = COMPETENCY_PROMPT_TEMPLATE.format(
                user_goal_kind=user_goal_kind,
                user_goal_description=user_goal_description,
                competency_questions=cq_text,
                available_artifacts=available_artifacts,
                schema_validation_rules=schema_rules,
            )
            message = "Validate the proposed competency questions."

        else:
            raise ValueError(
                f"Invalid scope: {scope}. "
                "Use 'structured', 'unstructured', or 'competency'."
            )

        response, state, _ = run_agent_sync(
            message=message,
            state=state,
            system_prompt=system_prompt,
            tools=self.tools,
            tool_handlers=self.tool_handlers,
            conversation=None,
        )

        return response, state
