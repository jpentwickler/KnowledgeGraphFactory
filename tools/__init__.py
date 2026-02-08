"""Tool handlers for KG-Factory agents."""

from tools.intent_tools import (
    TOOL_SET_PROPOSED_GOAL,
    TOOL_APPROVE_PROPOSED_GOAL,
    handle_set_proposed_goal,
    handle_approve_proposed_goal,
)

from tools.file_tools import (
    TOOL_GET_APPROVED_USER_GOAL,
    TOOL_LIST_AVAILABLE_FILES,
    TOOL_GET_FILE_INFO,
    TOOL_SAMPLE_FILE,
    TOOL_SET_PROPOSED_FILES,
    TOOL_APPROVE_PROPOSED_FILES,
    handle_get_approved_user_goal,
    handle_list_available_files,
    handle_get_file_info,
    handle_sample_file,
    handle_set_proposed_files,
    handle_approve_proposed_files,
)

__all__ = [
    # Intent tools (Stage 1)
    "TOOL_SET_PROPOSED_GOAL",
    "TOOL_APPROVE_PROPOSED_GOAL",
    "handle_set_proposed_goal",
    "handle_approve_proposed_goal",
    # File tools (Stage 2)
    "TOOL_GET_APPROVED_USER_GOAL",
    "TOOL_LIST_AVAILABLE_FILES",
    "TOOL_GET_FILE_INFO",
    "TOOL_SAMPLE_FILE",
    "TOOL_SET_PROPOSED_FILES",
    "TOOL_APPROVE_PROPOSED_FILES",
    "handle_get_approved_user_goal",
    "handle_list_available_files",
    "handle_get_file_info",
    "handle_sample_file",
    "handle_set_proposed_files",
    "handle_approve_proposed_files",
]
