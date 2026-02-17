"""Tool handlers for Competency Questions (CQ) management.

Provides:
- Batch set/approve for User Intent Agent (initial CQ elicitation)
- CRUD operations for CQ Management Agent (mid-pipeline editing)
- format_competency_questions() helper for downstream prompt injection
"""

import copy

from core import (
    create_tool_schema,
    has_proposed,
    has_approved,
    get_proposed,
    get_approved,
)

_VALID_PRIORITIES = ("high", "medium", "low")
_VALID_CATEGORIES = None  # Free-form — no restriction on category values


# ---------------------------------------------------------------------------
# Helper: Working-Copy Pattern
# ---------------------------------------------------------------------------


def _ensure_working_copy(state: dict) -> dict:
    """If no proposed CQs exist but approved do, deep-copy approved to proposed.

    Returns the proposed_competency_questions dict (creating it if needed).
    """
    if "proposed_competency_questions" not in state:
        approved = state.get("approved_competency_questions")
        state["proposed_competency_questions"] = (
            copy.deepcopy(approved) if approved else {}
        )
    return state["proposed_competency_questions"]


# ---------------------------------------------------------------------------
# Helper: format_competency_questions (downstream prompt injection)
# ---------------------------------------------------------------------------


def format_competency_questions(state: dict) -> str:
    """Format approved CQs for injection into downstream agent prompts.

    Sorts by priority (high > medium > low), returns "(none)" if empty.

    Args:
        state: Current state dictionary.

    Returns:
        Formatted string listing competency questions.
    """
    cqs = get_approved(state, "competency_questions")
    if not cqs:
        return "(none)"

    priority_order = {"high": 0, "medium": 1, "low": 2}
    sorted_items = sorted(
        cqs.items(),
        key=lambda item: priority_order.get(item[1].get("priority", "low"), 3),
    )

    lines = []
    for cq_id, details in sorted_items:
        question = details.get("question", "")
        category = details.get("category", "general")
        priority = details.get("priority", "medium")
        lines.append(f"- [{cq_id}] ({priority}, {category}) {question}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool Schemas: User Intent Agent (batch set/approve)
# ---------------------------------------------------------------------------

TOOL_SET_PROPOSED_CQS = create_tool_schema(
    name="set_proposed_competency_questions",
    description=(
        "Save a batch of proposed competency questions. "
        "Each question must have a unique ID (e.g., CQ1), a question text, "
        "a category, and a priority level."
    ),
    properties={
        "competency_questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": (
                            "Unique identifier for this question (e.g., 'CQ1', 'CQ2')"
                        ),
                    },
                    "question": {
                        "type": "string",
                        "description": (
                            "The competency question the graph must answer. "
                            "Should be specific and answerable by graph traversal."
                        ),
                    },
                    "category": {
                        "type": "string",
                        "description": (
                            "Thematic category (e.g., 'supply_chain_impact', "
                            "'quality_analysis', 'customer_insights')"
                        ),
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Priority level for this question.",
                    },
                },
                "required": ["id", "question", "category", "priority"],
            },
            "description": "List of competency questions to propose.",
        }
    },
    required=["competency_questions"],
)

TOOL_APPROVE_PROPOSED_CQS = create_tool_schema(
    name="approve_proposed_competency_questions",
    description=(
        "Approve the proposed competency questions after the user explicitly "
        "confirms. Only use when user says 'approve', 'looks good', 'yes', "
        "or similar."
    ),
    properties={},
    required=[],
)


# ---------------------------------------------------------------------------
# Tool Schemas: CQ Management Agent (CRUD)
# ---------------------------------------------------------------------------

TOOL_ADD_CQ = create_tool_schema(
    name="add_competency_question",
    description=(
        "Add a single competency question to the proposed set. "
        "If the ID already exists, it will be overwritten with a warning."
    ),
    properties={
        "id": {
            "type": "string",
            "description": "Unique identifier (e.g., 'CQ8').",
        },
        "question": {
            "type": "string",
            "description": "The competency question text.",
        },
        "category": {
            "type": "string",
            "description": "Thematic category.",
        },
        "priority": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Priority level.",
        },
    },
    required=["id", "question", "category", "priority"],
)

TOOL_MODIFY_CQ = create_tool_schema(
    name="modify_competency_question",
    description=(
        "Modify an existing competency question by ID. "
        "Only the provided fields are updated; others remain unchanged."
    ),
    properties={
        "id": {
            "type": "string",
            "description": "ID of the question to modify.",
        },
        "question": {
            "type": "string",
            "description": "New question text (optional).",
        },
        "category": {
            "type": "string",
            "description": "New category (optional).",
        },
        "priority": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "New priority level (optional).",
        },
    },
    required=["id"],
)

TOOL_DELETE_CQ = create_tool_schema(
    name="delete_competency_question",
    description="Remove a competency question by its ID.",
    properties={
        "id": {
            "type": "string",
            "description": "ID of the question to remove.",
        },
    },
    required=["id"],
)

TOOL_GET_CQS = create_tool_schema(
    name="get_competency_questions",
    description=(
        "Get the current competency questions (proposed and/or approved)."
    ),
    properties={},
    required=[],
)

TOOL_APPROVE_CQ_CHANGES = create_tool_schema(
    name="approve_competency_question_changes",
    description=(
        "Approve the current proposed competency questions, replacing the "
        "approved set. Only use when user explicitly approves."
    ),
    properties={},
    required=[],
)


# ---------------------------------------------------------------------------
# Handlers: User Intent Agent (batch set/approve)
# ---------------------------------------------------------------------------


def handle_set_proposed_cqs(state: dict, competency_questions: list) -> dict:
    """Save a batch of proposed competency questions.

    Validates:
    - No duplicate IDs within the batch
    - All required fields present per CQ
    - Priority is valid

    Args:
        state: Current state dictionary.
        competency_questions: List of CQ dicts with id, question, category, priority.

    Returns:
        Tool result with the proposed CQs or validation error.
    """
    if not competency_questions:
        return {
            "status": "error",
            "message": "competency_questions list is empty.",
        }

    result = {}
    seen_ids = set()

    for cq in competency_questions:
        cq_id = cq.get("id", "").strip()
        question = cq.get("question", "").strip()
        category = cq.get("category", "").strip()
        priority = cq.get("priority", "").strip()

        if not cq_id:
            return {"status": "error", "message": "Each CQ must have a non-empty 'id'."}
        if not question:
            return {
                "status": "error",
                "message": f"CQ '{cq_id}' is missing 'question'.",
            }
        if not category:
            return {
                "status": "error",
                "message": f"CQ '{cq_id}' is missing 'category'.",
            }
        if priority not in _VALID_PRIORITIES:
            return {
                "status": "error",
                "message": (
                    f"CQ '{cq_id}' has invalid priority '{priority}'. "
                    f"Must be one of: {', '.join(_VALID_PRIORITIES)}."
                ),
            }
        if cq_id in seen_ids:
            return {
                "status": "error",
                "message": f"Duplicate CQ ID '{cq_id}' in the batch.",
            }

        seen_ids.add(cq_id)
        result[cq_id] = {
            "question": question,
            "category": category,
            "priority": priority,
        }

    state["proposed_competency_questions"] = result
    return {
        "status": "success",
        "message": (
            f"Proposed {len(result)} competency questions. "
            "Present to user for approval."
        ),
        "proposed_competency_questions": result,
    }


def handle_approve_proposed_cqs(state: dict) -> dict:
    """Approve the proposed competency questions.

    Args:
        state: Current state dictionary.

    Returns:
        Tool result with approved CQs or error if no proposal exists.
    """
    if "proposed_competency_questions" not in state:
        return {
            "status": "error",
            "message": "No proposed competency questions to approve.",
        }

    state["approved_competency_questions"] = copy.deepcopy(
        state["proposed_competency_questions"]
    )
    return {
        "status": "success",
        "message": (
            f"Competency questions approved "
            f"({len(state['approved_competency_questions'])} total)."
        ),
        "approved_competency_questions": state["approved_competency_questions"],
    }


# ---------------------------------------------------------------------------
# Handlers: CQ Management Agent (CRUD)
# ---------------------------------------------------------------------------


def handle_add_cq(
    state: dict, id: str, question: str, category: str, priority: str
) -> dict:
    """Add a single competency question.

    Initializes a working copy from approved CQs if needed.
    If the ID already exists, overwrites with a warning.

    Args:
        state: Current state dictionary.
        id: Unique CQ identifier.
        question: The competency question text.
        category: Thematic category.
        priority: Priority level (high/medium/low).

    Returns:
        Tool result with the added CQ.
    """
    if priority not in _VALID_PRIORITIES:
        return {
            "status": "error",
            "message": (
                f"Invalid priority '{priority}'. "
                f"Must be one of: {', '.join(_VALID_PRIORITIES)}."
            ),
        }

    proposed = _ensure_working_copy(state)

    overwrite = id in proposed
    proposed[id] = {
        "question": question,
        "category": category,
        "priority": priority,
    }

    msg = f"Added CQ '{id}'. Total proposed: {len(proposed)}."
    if overwrite:
        msg = f"Overwrote existing CQ '{id}'. Total proposed: {len(proposed)}."

    return {
        "status": "success",
        "message": msg,
        "overwritten": overwrite,
        "cq": {id: proposed[id]},
    }


def handle_modify_cq(
    state: dict,
    id: str,
    question: str = None,
    category: str = None,
    priority: str = None,
) -> dict:
    """Modify an existing competency question by ID.

    Only non-None fields are updated.

    Args:
        state: Current state dictionary.
        id: ID of the CQ to modify.
        question: New question text (optional).
        category: New category (optional).
        priority: New priority (optional).

    Returns:
        Tool result with the updated CQ or error.
    """
    if priority is not None and priority not in _VALID_PRIORITIES:
        return {
            "status": "error",
            "message": (
                f"Invalid priority '{priority}'. "
                f"Must be one of: {', '.join(_VALID_PRIORITIES)}."
            ),
        }

    proposed = _ensure_working_copy(state)

    if id not in proposed:
        available = ", ".join(sorted(proposed.keys())) if proposed else "(none)"
        return {
            "status": "error",
            "message": (
                f"CQ '{id}' not found in proposed questions. "
                f"Available IDs: {available}"
            ),
        }

    if question is not None:
        proposed[id]["question"] = question
    if category is not None:
        proposed[id]["category"] = category
    if priority is not None:
        proposed[id]["priority"] = priority

    return {
        "status": "success",
        "message": f"Modified CQ '{id}'.",
        "cq": {id: proposed[id]},
    }


def handle_delete_cq(state: dict, id: str) -> dict:
    """Remove a competency question by ID.

    Args:
        state: Current state dictionary.
        id: ID of the CQ to remove.

    Returns:
        Tool result confirming removal or error.
    """
    proposed = _ensure_working_copy(state)

    if id not in proposed:
        available = ", ".join(sorted(proposed.keys())) if proposed else "(none)"
        return {
            "status": "error",
            "message": (
                f"CQ '{id}' not found in proposed questions. "
                f"Available IDs: {available}"
            ),
        }

    removed = proposed.pop(id)
    return {
        "status": "success",
        "message": f"Removed CQ '{id}'. Remaining: {len(proposed)}.",
        "removed": {id: removed},
    }


def handle_get_cqs(state: dict) -> dict:
    """Get current competency questions (proposed and/or approved).

    Args:
        state: Current state dictionary.

    Returns:
        Tool result with proposed and approved CQs.
    """
    proposed = state.get("proposed_competency_questions", {})
    approved = state.get("approved_competency_questions", {})

    return {
        "status": "success",
        "proposed_competency_questions": proposed,
        "approved_competency_questions": approved,
        "proposed_count": len(proposed),
        "approved_count": len(approved),
    }


def handle_approve_cq_changes(state: dict) -> dict:
    """Approve the current proposed CQs, replacing the approved set.

    Same logic as handle_approve_proposed_cqs — provided as a separate
    tool name for the CQ Management Agent.

    Args:
        state: Current state dictionary.

    Returns:
        Tool result with approved CQs or error.
    """
    if "proposed_competency_questions" not in state:
        return {
            "status": "error",
            "message": "No proposed competency questions to approve.",
        }

    state["approved_competency_questions"] = copy.deepcopy(
        state["proposed_competency_questions"]
    )
    return {
        "status": "success",
        "message": (
            f"Competency questions approved "
            f"({len(state['approved_competency_questions'])} total)."
        ),
        "approved_competency_questions": state["approved_competency_questions"],
    }
