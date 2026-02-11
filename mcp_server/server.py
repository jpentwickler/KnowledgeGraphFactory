"""MCP Server for KG-Factory.

Exposes KG-Factory agents as tools for Claude Code integration.
Uses FastMCP for the MCP protocol implementation.

Each agent maintains a rolling-window conversation history (last N messages)
so that multi-turn interactions preserve context between MCP calls.
All artifacts are persisted in state (proposed/approved values).
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

from agents import (
    UserIntentAgent,
    FileSuggestionAgent,
    SchemaProposalAgent,
    SchemaCriticAgent,
    NerExtractionAgent,
    FactExtractionAgent,
)
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

# Rolling window: max conversation messages stored per agent.
# ~5 full exchanges (user + assistant + tool pairs).
MAX_CONVERSATION_MESSAGES = 20

_CONVERSATION_SUFFIX = "_conversation"


def _is_conversation_key(key: str) -> bool:
    """Check if a state key is a conversation history key."""
    return key.startswith("_") and key.endswith(_CONVERSATION_SUFFIX)


def _should_persist(key: str) -> bool:
    """Check if a state key should be persisted to disk.

    Artifact keys (no underscore prefix) and conversation keys are persisted.
    Other underscore-prefixed keys (e.g. _critic_verdict) are ephemeral.
    """
    return not key.startswith("_") or _is_conversation_key(key)


def _serialize_conversation(conversation: list[dict]) -> list[dict]:
    """Convert a conversation to a JSON-serializable format.

    Assistant messages contain Anthropic SDK objects (TextBlock, ToolUseBlock)
    which must be converted to dicts via model_dump(). User messages are
    already JSON-safe (plain strings or tool_result dicts).
    """
    serialized = []
    for msg in conversation:
        role = msg["role"]
        content = msg["content"]

        if role == "assistant" and isinstance(content, list):
            serialized_content = []
            for block in content:
                if hasattr(block, "model_dump"):
                    serialized_content.append(block.model_dump())
                else:
                    serialized_content.append(block)
            serialized.append({"role": role, "content": serialized_content})
        else:
            serialized.append(msg)

    return serialized


def _trim_conversation(
    conversation: list[dict],
    max_messages: int = MAX_CONVERSATION_MESSAGES,
) -> list[dict]:
    """Trim a conversation to the last N messages, respecting tool-pair boundaries.

    After trimming to the last N messages, scans forward to find a clean
    boundary -- a user message with plain string content (not a tool_result).
    This prevents splitting tool_use/tool_result pairs which would crash the
    Claude API.
    """
    if not conversation or len(conversation) <= max_messages:
        return conversation

    start_idx = len(conversation) - max_messages

    # Scan forward to a user message with plain string content
    while start_idx < len(conversation):
        msg = conversation[start_idx]
        if msg["role"] == "user" and isinstance(msg["content"], str):
            break
        start_idx += 1

    if start_idx >= len(conversation):
        return []

    return conversation[start_idx:]


def _pop_conversation(state: dict, conv_key: str) -> list | None:
    """Extract conversation from state for agent use."""
    return state.pop(conv_key, None)


def _store_conversation(
    state: dict, conv_key: str, conversation: list
) -> None:
    """Serialize, trim, and store conversation back into state."""
    conversation = _serialize_conversation(conversation)
    conversation = _trim_conversation(conversation)
    state[conv_key] = conversation


def _load_clean_state() -> dict:
    """Load state from disk, preserving artifacts and conversation keys.

    Strips ephemeral underscore-prefixed keys (e.g. _critic_verdict)
    but preserves conversation keys (e.g. _user_intent_conversation).
    """
    raw_state = load_state(STATE_FILE)
    return {k: v for k, v in raw_state.items() if _should_persist(k)}


def _save_state(state: dict) -> None:
    """Save state to disk, preserving artifacts and conversation keys.

    Merges updated state into the existing file so that keys not touched
    by this agent call are preserved.
    """
    raw_state = load_state(STATE_FILE)

    # Keep artifacts + conversation keys from existing state
    clean_raw = {k: v for k, v in raw_state.items() if _should_persist(k)}

    # Merge in updated state
    clean_raw.update(state)

    # Final clean: remove any ephemeral keys that came from agent
    final = {k: v for k, v in clean_raw.items() if _should_persist(k)}

    save_state(final, STATE_FILE)


@mcp.tool
def kg_get_state() -> dict:
    """Get current KG-Factory pipeline state.

    Returns the current proposed and approved artifacts from the pipeline.
    Use this to check progress and see what's been completed.

    Returns:
        Dictionary with current state (excludes internal metadata).
    """
    state = _load_clean_state()
    # Exclude conversation keys from public display
    return {k: v for k, v in state.items() if not _is_conversation_key(k)}


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
    state = _load_clean_state()
    conversation = _pop_conversation(state, "_user_intent_conversation")

    agent = UserIntentAgent()
    response, state, conversation = agent.run(message, state, conversation)

    _store_conversation(state, "_user_intent_conversation", conversation)
    _save_state(state)

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
def kg_file_suggestion(message: str) -> dict:
    """Send a message to the File Suggestion Agent.

    Pass the user's message exactly as they wrote it. Do NOT add context,
    file contents, or analysis — the agent will ask its own questions.

    This is a multi-turn conversation. Call this tool once per user message.
    Stage 1 (User Intent) must be completed before using this agent.

    Args:
        message: The user's message, passed through exactly as written.

    Returns:
        Dictionary with agent response and current status.
    """
    state = _load_clean_state()
    conversation = _pop_conversation(state, "_file_suggestion_conversation")

    agent = FileSuggestionAgent()
    response, state, conversation = agent.run(message, state, conversation)

    _store_conversation(state, "_file_suggestion_conversation", conversation)
    _save_state(state)

    # Build status info
    status = {
        "has_proposed_files": "proposed_files" in state,
        "has_approved_files": "approved_files" in state,
    }

    if "proposed_files" in state:
        status["proposed_files"] = state["proposed_files"]
    if "approved_files" in state:
        status["approved_files"] = state["approved_files"]

    return {
        "agent_response": response,
        "status": status
    }


@mcp.tool
def kg_schema_proposal(message: str) -> dict:
    """Send a message to the Schema Proposal Agent.

    Pass the user's message exactly as they wrote it. Do NOT add context,
    file contents, or analysis -- the agent has all file data pre-loaded.

    This is a multi-turn conversation. Call this tool once per user message.
    Stages 1 (User Intent) and 2 (File Suggestion) must be completed first.

    Args:
        message: The user's message, passed through exactly as written.

    Returns:
        Dictionary with agent response and current status.
    """
    state = _load_clean_state()
    conversation = _pop_conversation(state, "_schema_proposal_conversation")

    agent = SchemaProposalAgent()
    response, state, conversation = agent.run(message, state, conversation)

    _store_conversation(state, "_schema_proposal_conversation", conversation)
    _save_state(state)

    # Build status info
    status = {
        "has_proposed_construction_plan": "proposed_construction_plan" in state,
        "has_approved_construction_plan": "approved_construction_plan" in state,
    }

    if "proposed_construction_plan" in state:
        plan = state["proposed_construction_plan"]
        status["proposed_plan_summary"] = {
            "node_count": sum(
                1 for v in plan.values()
                if v.get("construction_type") == "node"
            ),
            "relationship_count": sum(
                1 for v in plan.values()
                if v.get("construction_type") == "relationship"
            ),
            "labels": list(plan.keys()),
        }

    if "approved_construction_plan" in state:
        status["approved_construction_plan"] = state["approved_construction_plan"]

    return {
        "agent_response": response,
        "status": status,
    }


@mcp.tool
def kg_critic(scope: str = "structured") -> dict:
    """Run the critic agent to review proposed artifacts for problems.

    The critic is an independent reviewer that checks for errors, missing
    elements, and inconsistencies. It does NOT approve or finalize anything.

    Two scopes are available:
    - "structured" (default): Reviews the construction plan against CSV files.
      Use after kg_schema_proposal to check column references, identifier
      uniqueness, and relationship correctness.
    - "unstructured": Reviews entity types and fact types against markdown files.
      Use after kg_ner_extraction or kg_fact_extraction to check text grounding,
      overlapping types, and predicate quality.

    No message needed -- the critic analyzes whatever is currently proposed.

    Args:
        scope: What to review. "structured" or "unstructured".

    Returns:
        Dictionary with critic verdict, problems list, and response text.
    """
    state = _load_clean_state()

    if scope == "structured":
        if "proposed_construction_plan" not in state:
            return {
                "agent_response": "No proposed construction plan to review. "
                "Use kg_schema_proposal first to create a plan.",
                "status": {"error": "no_proposed_plan"},
            }
    elif scope == "unstructured":
        has_entities = (
            "proposed_entity_types" in state or "approved_entity_types" in state
        )
        if not has_entities:
            return {
                "agent_response": "No entity types to review. "
                "Use kg_ner_extraction first to propose entity types.",
                "status": {"error": "no_entity_types"},
            }
    else:
        return {
            "agent_response": f"Invalid scope: '{scope}'. Use 'structured' or 'unstructured'.",
            "status": {"error": "invalid_scope"},
        }

    critic = SchemaCriticAgent()
    response, state = critic.run(state, scope=scope)

    _save_state(state)

    verdict = state.get("_critic_verdict", "unknown")
    problems = state.get("_critic_problems", [])

    return {
        "agent_response": response,
        "status": {
            "scope": scope,
            "verdict": verdict,
            "problems": problems,
            "problem_count": len(problems),
        },
    }


@mcp.tool
def kg_ner_extraction(message: str) -> dict:
    """Send a message to the NER Extraction Agent.

    The agent analyzes approved markdown files and proposes entity types
    (categories) to extract. Entity types include well-known types from
    the construction plan and discovered types from the text.

    Pass the user's message exactly as they wrote it. Multi-turn conversation.
    Call once per user message. Stages 1-3 must be completed first.

    Args:
        message: The user's message, passed through exactly as written.

    Returns:
        Dictionary with agent response, status, and pre-computation summary.
    """
    state = _load_clean_state()
    conversation = _pop_conversation(state, "_ner_extraction_conversation")

    agent = NerExtractionAgent()
    response, state, conversation = agent.run(message, state, conversation)

    _store_conversation(state, "_ner_extraction_conversation", conversation)
    _save_state(state)

    # Build status info
    status = {
        "has_proposed_entities": "proposed_entity_types" in state,
        "has_approved_entities": "approved_entity_types" in state,
    }

    if "proposed_entity_types" in state:
        status["proposed_entities"] = state["proposed_entity_types"]
        status["entity_count"] = len(state["proposed_entity_types"])

    if "approved_entity_types" in state:
        status["approved_entities"] = state["approved_entity_types"]

    # Pre-computation summary for transparency
    unstructured = state.get("approved_files", {}).get("unstructured", [])
    construction_plan = state.get("approved_construction_plan", {})
    well_known = [
        entry["label"]
        for entry in construction_plan.values()
        if entry.get("construction_type") == "node"
    ]

    status["pre_computation_summary"] = {
        "files_analyzed": len(unstructured),
        "file_names": [f["path"] for f in unstructured],
        "well_known_types": well_known,
    }

    return {
        "agent_response": response,
        "status": status,
    }


@mcp.tool
def kg_fact_extraction(message: str) -> dict:
    """Send a message to the Fact Extraction Agent.

    The agent analyzes approved markdown files and proposes fact types
    (relationship templates) between approved entity types. Fact types
    define directed relationships like (Product)-[has_issue]->(Issue).

    Pass the user's message exactly as they wrote it. Multi-turn conversation.
    Call once per user message. Stages 1-4 must be completed first.

    Args:
        message: The user's message, passed through exactly as written.

    Returns:
        Dictionary with agent response, status, and pre-computation summary.
    """
    state = _load_clean_state()
    conversation = _pop_conversation(state, "_fact_extraction_conversation")

    agent = FactExtractionAgent()
    response, state, conversation = agent.run(message, state, conversation)

    _store_conversation(state, "_fact_extraction_conversation", conversation)
    _save_state(state)

    # Build status info
    status = {
        "has_proposed_facts": "proposed_fact_types" in state,
        "has_approved_facts": "approved_fact_types" in state,
    }

    if "proposed_fact_types" in state:
        status["proposed_facts"] = state["proposed_fact_types"]
        status["fact_count"] = len(state["proposed_fact_types"])

    if "approved_fact_types" in state:
        status["approved_facts"] = state["approved_fact_types"]

    # Pre-computation summary for transparency
    entity_types = state.get("approved_entity_types", {})
    unstructured = state.get("approved_files", {}).get("unstructured", [])

    status["pre_computation_summary"] = {
        "files_analyzed": len(unstructured),
        "file_names": [f["path"] for f in unstructured],
        "entity_types_available": sorted(entity_types.keys()),
    }

    return {
        "agent_response": response,
        "status": status,
    }


@mcp.tool
def kg_reset_state() -> dict:
    """Reset the KG-Factory state to start fresh.

    Clears all proposed/approved artifacts.
    Use this to start over from the beginning.

    Returns:
        Confirmation message.
    """
    save_state({}, STATE_FILE)
    return {"message": "State reset. Ready to start fresh."}


if __name__ == "__main__":
    mcp.run()
