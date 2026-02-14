"""KG-Factory Core Framework.

Provides the foundational components for building knowledge graph agents:
- Agent runner for Claude API interaction
- State management for proposed/approved artifacts
- Tool utilities for creating and executing tools
"""

from core.agent import run_agent, run_agent_sync
from core.tracing import traceable, wrap_anthropic, mcp_traceable
from core.state import (
    load_state,
    save_state,
    get_approved,
    get_proposed,
    set_proposed,
    approve,
    has_approved,
    has_proposed,
)
from core.tools import (
    create_tool_schema,
    execute_tool,
    format_tool_result,
    format_tool_error,
)

__all__ = [
    # Agent
    "run_agent",
    "run_agent_sync",
    # State
    "load_state",
    "save_state",
    "get_approved",
    "get_proposed",
    "set_proposed",
    "approve",
    "has_approved",
    "has_proposed",
    # Tools
    "create_tool_schema",
    "execute_tool",
    "format_tool_result",
    "format_tool_error",
    # Tracing
    "traceable",
    "wrap_anthropic",
    "mcp_traceable",
]
