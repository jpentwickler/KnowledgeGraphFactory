"""Schema Critic Agent — validates the proposed construction plan.

Stateless validator that pre-computes file context and injects the current
construction plan into the system prompt, making validation fast (1 API call
instead of 10-20). Uses a single submit_review tool for structured verdicts.

No conversation history needed — each validation is independent.
"""

import json

from core import run_agent_sync, get_approved
from tools.schema_tools import (
    TOOL_SUBMIT_REVIEW,
    handle_submit_review,
    build_file_context,
)


SYSTEM_PROMPT_TEMPLATE = """\
You are an expert at knowledge graph modeling with property graphs. \
Your job is to validate the proposed construction plan against the source data \
and user goal.

USER GOAL:
- Kind: {user_goal_kind}
- Description: {user_goal_description}

APPROVED FILE DATA:
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

After completing your analysis, you MUST call the 'submit_review' tool:
- If the schema is correct, call submit_review with verdict "valid" and an empty \
problems list.
- If the schema has problems, call submit_review with verdict "retry" and a list \
of specific, actionable problems to fix.\
"""


class SchemaCriticAgent:
    """Stateless critic agent for on-demand schema validation.

    Pre-computes file context and injects the current construction plan into
    the system prompt, making validation fast (1 API call instead of 10-20).

    No conversation history needed — each validation is independent.
    """

    def __init__(self):
        self.tools = [TOOL_SUBMIT_REVIEW]
        self.tool_handlers = {"submit_review": handle_submit_review}

    def run(self, state: dict) -> tuple[str, dict]:
        """Run a single-shot validation of the current proposed plan.

        Args:
            state: Current state dictionary (must contain proposed_construction_plan).

        Returns:
            (response text, updated state with _critic_verdict/_critic_problems)
        """
        # Extract user goal
        user_goal = get_approved(state, "user_goal") or {}
        user_goal_kind = user_goal.get("kind_of_graph", "unknown")
        user_goal_description = user_goal.get("graph_description", "No description available.")

        # Pre-compute file context
        file_context = build_file_context(state) or "No approved files found."

        # Format construction plan
        plan = state.get("proposed_construction_plan", {})
        construction_plan = json.dumps(plan, indent=2) if plan else "No plan proposed yet."

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            user_goal_kind=user_goal_kind,
            user_goal_description=user_goal_description,
            file_context=file_context,
            construction_plan=construction_plan,
        )

        response, state, _ = run_agent_sync(
            message="Validate the proposed construction plan.",
            state=state,
            system_prompt=system_prompt,
            tools=self.tools,
            tool_handlers=self.tool_handlers,
            conversation=None,
        )

        return response, state
