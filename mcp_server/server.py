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


def _format_node_results(nodes: list[dict]) -> str:
    """Format node import results for display."""
    if not nodes:
        return "  (none)"

    lines = []
    for node in nodes:
        status = "[OK]" if not node["errors"] else "[FAIL]"
        lines.append(f"  {status} {node['label']}: {node['count']} nodes")
        for error in node.get("errors", []):
            lines.append(f"      Error: {error}")
    return "\n".join(lines)


def _format_rel_results(rels: list[dict]) -> str:
    """Format relationship import results for display."""
    if not rels:
        return "  (none)"

    lines = []
    for rel in rels:
        status = "[OK]" if not rel["errors"] else "[FAIL]"
        orphan_note = ""
        if rel.get("orphans", 0) > 0:
            orphan_note = f" (WARNING: {rel['orphans']} orphans)"
        lines.append(f"  {status} {rel['type']}: {rel['count']} relationships{orphan_note}")
        for error in rel.get("errors", []):
            lines.append(f"      Error: {error}")
    return "\n".join(lines)


@mcp.tool
def kg_build_graph(message: str = "build") -> dict:
    """Build the knowledge graph in Neo4j from approved artifacts.

    This tool executes the graph construction pipeline, importing structured
    CSV data into Neo4j according to the approved construction plan.

    The build process:
    1. Validates all CSV files (duplicates, nulls, whitespace)
    2. Creates NODE KEY constraints for uniqueness + indexing
    3. Imports nodes via LOAD CSV + MERGE
    4. Imports relationships via LOAD CSV + MATCH + MERGE
    5. Verifies graph construction (node/relationship counts)

    Prerequisites:
    - Stage 3 must be completed (approved_construction_plan)
    - Neo4j instance must be running and accessible
    - Environment variables must be set (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    Note: Currently builds the Domain Graph only (CSV → Neo4j).
    Text processing (Subject/Lexical graphs) will be added in a future update.

    Args:
        message: Optional user message (e.g., "build the graph", "start")

    Returns:
        Dictionary with build results, verification stats, and any errors.
    """
    state = _load_clean_state()

    # Check prerequisites
    if "approved_construction_plan" not in state:
        return {
            "agent_response": (
                "Cannot build graph: No approved construction plan found.\n\n"
                "Please complete Stage 3 (Schema Proposal) first:\n"
                "1. Use kg_schema_proposal to design the schema\n"
                "2. Use kg_critic with scope='structured' to validate\n"
                "3. Approve the construction plan"
            ),
            "status": {
                "success": False,
                "error": "missing_construction_plan"
            }
        }

    # Check Neo4j environment variables
    neo4j_uri = os.environ.get("NEO4J_URI")
    neo4j_user = os.environ.get("NEO4J_USER")
    neo4j_password = os.environ.get("NEO4J_PASSWORD")

    if not all([neo4j_uri, neo4j_user, neo4j_password]):
        return {
            "agent_response": (
                "Cannot build graph: Neo4j credentials not configured.\n\n"
                "Please set these environment variables in your .mcp.json:\n"
                "- NEO4J_URI (e.g., neo4j+s://xxxxx.databases.neo4j.io)\n"
                "- NEO4J_USER (e.g., neo4j)\n"
                "- NEO4J_PASSWORD (your password)"
            ),
            "status": {
                "success": False,
                "error": "missing_neo4j_credentials"
            }
        }

    # Import domain builder
    try:
        from pipelines import build_domain_graph
        from utils import get_neo4j_driver, test_connection, close_driver
    except ImportError as exc:
        return {
            "agent_response": f"Failed to import graph builder modules: {exc}",
            "status": {
                "success": False,
                "error": "import_error"
            }
        }

    # Connect to Neo4j
    try:
        driver = get_neo4j_driver()
        conn_info = test_connection(driver)
        neo4j_version = conn_info.get("neo4j_version", "unknown")
        database = conn_info.get("database", "neo4j")
    except Exception as exc:
        return {
            "agent_response": (
                f"Failed to connect to Neo4j: {exc}\n\n"
                "Please check:\n"
                "1. Neo4j instance is running\n"
                "2. NEO4J_URI is correct\n"
                "3. Credentials are valid\n"
                "4. Network connectivity"
            ),
            "status": {
                "success": False,
                "error": "neo4j_connection_failed",
                "details": str(exc)
            }
        }

    # Build domain graph
    try:
        results = build_domain_graph(state, driver)

        # Close Neo4j connection
        close_driver(driver)

        # Check for errors
        if results["errors"]:
            error_summary = "\n".join(f"  - {err}" for err in results["errors"])
            response = f"""
Graph build completed with errors:

{error_summary}

Please review the errors and fix any data issues before retrying.
"""
            return {
                "agent_response": response,
                "status": {
                    "success": False,
                    "errors": results["errors"],
                    "verification": results.get("verification", {})
                }
            }

        # Success!
        verification = results["verification"]
        response = f"""
Domain Graph built successfully!

Connected to Neo4j {neo4j_version} (database: {database})

Nodes Imported:
{_format_node_results(results['nodes'])}

Relationships Imported:
{_format_rel_results(results['relationships'])}

Verification:
  Total nodes: {verification['total_nodes']}
  Total relationships: {verification['total_relationships']}
  Orphan nodes (no relationships): {verification['orphan_nodes']}

  Node counts by label:
{chr(10).join(f"    {label}: {count}" for label, count in verification['node_counts'].items())}

  Relationship counts by type:
{chr(10).join(f"    {rel_type}: {count}" for rel_type, count in verification['relationship_counts'].items())}

You can explore the graph in Neo4j Browser at: {neo4j_uri.replace('neo4j+s://', 'https://').replace('bolt://', 'http://').split(':')[0]}:7474

Useful queries:
  // View all nodes
  MATCH (n) RETURN n LIMIT 25

  // Check schema
  CALL db.schema.visualization()

  // Count all entities
  MATCH (n) RETURN labels(n) as label, count(*) as count
"""

        return {
            "agent_response": response,
            "status": {
                "success": True,
                "neo4j_version": neo4j_version,
                "database": database,
                "verification": verification,
                "node_import": results["nodes"],
                "relationship_import": results["relationships"]
            }
        }

    except Exception as exc:
        # Make sure to close driver even on error
        try:
            close_driver(driver)
        except:
            pass

        return {
            "agent_response": (
                f"Graph build failed with error:\n\n{exc}\n\n"
                "This may be due to:\n"
                "- Invalid CSV data (duplicates, missing values)\n"
                "- Neo4j connection issues\n"
                "- Permission problems\n\n"
                "Check the error message above for details."
            ),
            "status": {
                "success": False,
                "error": "build_failed",
                "details": str(exc)
            }
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
