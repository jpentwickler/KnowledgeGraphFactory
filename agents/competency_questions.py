"""Competency Questions Management Agent — manages CQs at any pipeline stage.

Multi-turn conversational agent for adding, modifying, deleting, and approving
competency questions. Can be used at any point in the pipeline after the user
goal has been approved.

Uses template-based system prompt with dynamic context injection.
"""

from core import run_agent_sync, get_approved, has_approved
from core.tracing import traceable
from tools.competency_tools import (
    TOOL_ADD_CQ,
    TOOL_MODIFY_CQ,
    TOOL_DELETE_CQ,
    TOOL_GET_CQS,
    TOOL_APPROVE_CQ_CHANGES,
    handle_add_cq,
    handle_modify_cq,
    handle_delete_cq,
    handle_get_cqs,
    handle_approve_cq_changes,
    format_competency_questions,
)
from tools.extraction_tools import format_user_goal


SYSTEM_PROMPT_TEMPLATE = """\
You are the Competency Questions Manager, a specialist in defining what \
a knowledge graph must be able to answer.

Competency questions (CQs) are specific business questions that the graph \
must support. They scope the design, guide downstream agents, and serve as \
evaluation criteria.

## User Goal

{user_goal}

## Current Competency Questions

{current_cqs}

## Pipeline Progress

{pipeline_progress}

## Your Capabilities

You can:
- Add new competency questions (add_competency_question)
- Modify existing questions (modify_competency_question) — partial updates only
- Delete questions (delete_competency_question)
- View all questions (get_competency_questions)
- Approve changes (approve_competency_question_changes)

## Quality Guidelines

Good competency questions:
- Are specific and answerable by graph traversal
- Reference entity types and relationships (e.g., "Which suppliers provide \
parts for products with the most defect reports?")
- Cover different aspects: simple lookups, multi-hop queries, aggregations
- Have clear categories and appropriate priority levels

Bad competency questions:
- Are too vague ("What is the data about?")
- Cannot be answered by a graph ("What is the meaning of life?")
- Are redundant with other CQs

## Context-Aware Suggestions

Based on the pipeline progress above, you can suggest CQs that leverage \
what's already been designed. For example:
- If a construction plan exists, suggest CQs that traverse its relationships
- If entity types exist, suggest CQs about those entity categories
- If fact types exist, suggest CQs that follow those relationship paths

## Workflow

1. Call get_competency_questions to see the current state
2. Discuss with the user what changes they want
3. Make changes using add/modify/delete tools
4. Present the updated set for review
5. ONLY call approve_competency_question_changes when the user explicitly \
approves (says "approve", "looks good", "yes", etc.)

MOVE-ON RULE:
- Whenever you ask clarifying questions, end with a reminder like:
  "Or say 'move on' if you'd like me to proceed with what I have so far."
- When the user says "move on", "skip", "proceed", "that's enough", or similar:
  STOP asking questions and proceed with your best judgment.

Be concise and professional.\
"""


def _build_pipeline_progress(state: dict) -> str:
    """Summarize which pipeline stages are complete.

    Args:
        state: Current state dictionary.

    Returns:
        Formatted string describing completed stages.
    """
    stages = [
        ("User Goal", "user_goal"),
        ("Competency Questions", "competency_questions"),
        ("Files", "files"),
        ("Construction Plan", "construction_plan"),
        ("Entity Types", "entity_types"),
        ("Fact Types", "fact_types"),
    ]

    lines = []
    for label, key in stages:
        if has_approved(state, key):
            lines.append(f"- {label}: approved")
        else:
            lines.append(f"- {label}: not yet approved")

    return "\n".join(lines)


TOOLS = [
    TOOL_GET_CQS,
    TOOL_ADD_CQ,
    TOOL_MODIFY_CQ,
    TOOL_DELETE_CQ,
    TOOL_APPROVE_CQ_CHANGES,
]

TOOL_HANDLERS = {
    "get_competency_questions": handle_get_cqs,
    "add_competency_question": handle_add_cq,
    "modify_competency_question": handle_modify_cq,
    "delete_competency_question": handle_delete_cq,
    "approve_competency_question_changes": handle_approve_cq_changes,
}


class CompetencyQuestionsAgent:
    """Agent for managing competency questions at any pipeline stage."""

    def __init__(self):
        self.tools = TOOLS
        self.tool_handlers = TOOL_HANDLERS

    @traceable(name="competency_questions.run")
    def run(
        self, message: str, state: dict, conversation: list = None
    ) -> tuple[str, dict, list]:
        """Run a conversation turn with the CQ management agent.

        Args:
            message: User's message.
            state: Current state dictionary.
            conversation: Conversation history (None for fresh start).

        Returns:
            (response, updated_state, conversation)
        """
        user_goal = get_approved(state, "user_goal") or {}
        user_goal_str = format_user_goal(user_goal)
        current_cqs = format_competency_questions(state)
        pipeline_progress = _build_pipeline_progress(state)

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            user_goal=user_goal_str,
            current_cqs=current_cqs,
            pipeline_progress=pipeline_progress,
        )

        return run_agent_sync(
            message=message,
            state=state,
            system_prompt=system_prompt,
            tools=self.tools,
            tool_handlers=self.tool_handlers,
            conversation=conversation,
        )
