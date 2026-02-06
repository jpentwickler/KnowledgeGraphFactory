"""Tool utilities for KG-Factory agents.

Provides utilities for creating tool schemas, executing tools,
and formatting tool results for the Claude API.
"""

import json
from typing import Any, Callable


def create_tool_schema(
    name: str,
    description: str,
    properties: dict[str, dict],
    required: list[str] | None = None
) -> dict:
    """Create a tool schema for the Claude API.

    Args:
        name: Tool name (must be unique within an agent).
        description: Description of what the tool does.
        properties: Dictionary of property schemas. Each property should have
            at minimum a "type" key.
        required: List of required property names. Defaults to empty list.

    Returns:
        Tool schema dictionary compatible with Claude API.

    Example:
        >>> schema = create_tool_schema(
        ...     "set_goal",
        ...     "Set the proposed goal",
        ...     {"goal": {"type": "string", "description": "The goal text"}},
        ...     ["goal"]
        ... )
    """
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required or []
        }
    }


def execute_tool(
    tool_handlers: dict[str, Callable],
    tool_name: str,
    tool_input: dict,
    state: dict
) -> dict:
    """Execute a tool handler with the given input.

    Args:
        tool_handlers: Dictionary mapping tool names to handler functions.
            Each handler should have signature: (state: dict, **kwargs) -> dict
        tool_name: Name of the tool to execute.
        tool_input: Input parameters for the tool.
        state: Current state dictionary (passed to handler, may be modified).

    Returns:
        Tool result dictionary from the handler.

    Raises:
        KeyError: If tool_name is not found in tool_handlers.
    """
    if tool_name not in tool_handlers:
        raise KeyError(f"Unknown tool: {tool_name}")

    handler = tool_handlers[tool_name]
    return handler(state, **tool_input)


def format_tool_result(tool_use_id: str, result: Any) -> dict:
    """Format a tool result for sending back to Claude.

    Args:
        tool_use_id: The tool_use_id from the tool_use block.
        result: The result from the tool handler (will be JSON serialized).

    Returns:
        Tool result message content block.
    """
    if isinstance(result, str):
        content = result
    else:
        content = json.dumps(result)

    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content
    }


def format_tool_error(tool_use_id: str, error: str) -> dict:
    """Format a tool error for sending back to Claude.

    Args:
        tool_use_id: The tool_use_id from the tool_use block.
        error: Error message describing what went wrong.

    Returns:
        Tool result message content block with is_error flag.
    """
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps({"error": error}),
        "is_error": True
    }
