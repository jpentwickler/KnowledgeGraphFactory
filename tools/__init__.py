"""Tool handlers for KG-Factory agents."""

from tools.intent_tools import (
    TOOL_SET_PROPOSED_GOAL,
    TOOL_APPROVE_PROPOSED_GOAL,
    handle_set_proposed_goal,
    handle_approve_proposed_goal,
)

__all__ = [
    "TOOL_SET_PROPOSED_GOAL",
    "TOOL_APPROVE_PROPOSED_GOAL",
    "handle_set_proposed_goal",
    "handle_approve_proposed_goal",
]
