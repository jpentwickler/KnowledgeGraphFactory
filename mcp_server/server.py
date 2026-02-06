"""MCP Server for KG-Factory.

Exposes KG-Factory agents as tools for Claude Code integration.
Uses FastMCP for the MCP protocol implementation.
"""

import os
import sys

# Add parent directory to path so we can import from kg-factory modules
_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root_dir)

# Load .env from project root (provides ANTHROPIC_API_KEY, etc.)
from dotenv import load_dotenv
load_dotenv(os.path.join(_root_dir, ".env"))

from fastmcp import FastMCP

from agents import UserIntentAgent
from core import load_state, save_state


# Create MCP server
mcp = FastMCP(
    "KG-Factory",
    instructions="""\
KG-Factory builds knowledge graphs through a multi-stage pipeline.
Each stage has a specialized agent that runs as a separate conversation.

## CRITICAL: You are a relay, not an interpreter

The kg_ tools connect to specialized agents that have their own conversation
with the user. Your job is to:
- Pass the user's message to the agent AS-IS
- Show the agent's response to the user AS-IS
- Do NOT read data files, analyze schemas, or add context on behalf of the user
- Do NOT answer questions the agent asks — let the user answer them
- Do NOT summarize or paraphrase — relay messages faithfully in both directions

The agents are designed to ask their own clarifying questions and guide the
user through the process. Let them do their job.

## Workflow

1. Call kg_get_state to check current pipeline progress
2. Call the appropriate kg_ agent tool, passing the user's message directly
3. Show the agent's response to the user
4. Repeat until the agent confirms approval
5. Each stage must be approved before moving to the next
6. Use kg_reset_state to start over if needed
"""
)

# State file path - defaults to state/current_state.json relative to working directory
STATE_FILE = os.path.join(
    os.environ.get("KG_STATE_DIR", "state"),
    "current_state.json"
)


def serialize_conversation(conversation: list) -> list:
    """Convert conversation to JSON-serializable format.

    The conversation list may contain Anthropic SDK objects (ContentBlock)
    that aren't directly JSON-serializable. This function converts them.

    Args:
        conversation: List of conversation messages.

    Returns:
        JSON-serializable list of messages.
    """
    if not conversation:
        return None

    serialized = []
    for msg in conversation:
        if msg["role"] == "assistant":
            content = []
            for block in msg["content"]:
                # Handle Anthropic SDK objects that have model_dump()
                if hasattr(block, "model_dump"):
                    content.append(block.model_dump())
                else:
                    content.append(block)
            serialized.append({"role": "assistant", "content": content})
        else:
            serialized.append(msg)
    return serialized


def load_session() -> tuple[dict, list]:
    """Load state and conversation from disk.

    Returns:
        Tuple of (state dict, conversation list).
        Conversation may be None if no history exists.
    """
    state = load_state(STATE_FILE)
    conversation = state.pop("_conversation_history", None)
    return state, conversation


def save_session(state: dict, conversation: list) -> None:
    """Save state and conversation to disk.

    Args:
        state: State dictionary to save.
        conversation: Conversation history to save.
    """
    state_to_save = state.copy()
    serialized = serialize_conversation(conversation)
    if serialized:
        state_to_save["_conversation_history"] = serialized
    save_state(state_to_save, STATE_FILE)


@mcp.tool
def kg_get_state() -> dict:
    """Get current KG-Factory pipeline state.

    Returns the current proposed and approved artifacts from the pipeline.
    Use this to check progress and see what's been completed.

    Returns:
        Dictionary with current state (excludes internal metadata).
    """
    state, _ = load_session()
    # Filter out internal keys (those starting with _)
    return {k: v for k, v in state.items() if not k.startswith("_")}


@mcp.tool
def kg_user_intent(message: str) -> dict:
    """Send a message to the User Intent Agent.

    Pass the user's message exactly as they wrote it. Do NOT add context,
    file contents, or analysis — the agent will ask its own questions.

    This is a multi-turn conversation. Call this tool once per user message.

    Args:
        message: The user's message, passed through exactly as written.

    Returns:
        Dictionary with agent response and current status.
    """
    state, conversation = load_session()

    agent = UserIntentAgent()
    response, state, conversation = agent.run(message, state, conversation)

    save_session(state, conversation)

    # Build status info
    status = {
        "has_proposed_goal": "proposed_user_goal" in state,
        "has_approved_goal": "approved_user_goal" in state,
    }

    if "proposed_user_goal" in state:
        status["proposed_goal"] = state["proposed_user_goal"]
    if "approved_user_goal" in state:
        status["approved_goal"] = state["approved_user_goal"]

    return {
        "agent_response": response,
        "status": status
    }


@mcp.tool
def kg_reset_state() -> dict:
    """Reset the KG-Factory state to start fresh.

    Clears all proposed/approved artifacts and conversation history.
    Use this to start over from the beginning.

    Returns:
        Confirmation message.
    """
    save_state({}, STATE_FILE)
    return {"message": "State reset. Ready to start fresh."}


if __name__ == "__main__":
    mcp.run()
