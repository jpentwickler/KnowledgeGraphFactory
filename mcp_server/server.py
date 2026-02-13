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


def _build_structured(state, driver, conn_info):
    """Build domain graph from CSVs (existing US008 behavior).

    Returns:
        dict with agent_response and status.
    """
    from pipelines import build_domain_graph

    neo4j_uri = os.environ.get("NEO4J_URI", "")

    if "approved_construction_plan" not in state:
        return {
            "agent_response": (
                "Cannot build structured graph: No approved construction plan.\n\n"
                "Please complete Stage 3 (Schema Proposal) first:\n"
                "1. Use kg_schema_proposal to design the schema\n"
                "2. Use kg_critic with scope='structured' to validate\n"
                "3. Approve the construction plan"
            ),
            "status": {"success": False, "error": "missing_construction_plan"},
        }

    results = build_domain_graph(state, driver)

    if results["errors"]:
        error_summary = "\n".join(f"  - {err}" for err in results["errors"])
        return {
            "agent_response": (
                f"Domain graph build completed with errors:\n\n{error_summary}\n\n"
                "Please review the errors and fix any data issues before retrying."
            ),
            "status": {
                "success": False,
                "errors": results["errors"],
                "verification": results.get("verification", {}),
            },
        }

    verification = results["verification"]
    neo4j_version = conn_info.get("neo4j_version", "unknown")
    database = conn_info.get("database", "neo4j")

    response = f"""Domain Graph built successfully!

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
{chr(10).join(f"    {rel_type}: {count}" for rel_type, count in verification['relationship_counts'].items())}"""

    return {
        "agent_response": response,
        "status": {
            "success": True,
            "neo4j_version": neo4j_version,
            "database": database,
            "verification": verification,
            "node_import": results["nodes"],
            "relationship_import": results["relationships"],
        },
    }


async def _build_unstructured(state, driver, message):
    """Build subject + lexical graphs from markdown files.

    Returns:
        dict with agent_response and status.
    """
    from pipelines import build_text_graph

    # Check prerequisites
    if "approved_entity_types" not in state:
        return {
            "agent_response": (
                "Cannot build text graph: No approved entity types.\n\n"
                "Please complete Stage 4 (NER Extraction) first."
            ),
            "status": {"success": False, "error": "missing_entity_types"},
        }

    if "approved_fact_types" not in state:
        return {
            "agent_response": (
                "Cannot build text graph: No approved fact types.\n\n"
                "Please complete Stage 5 (Fact Extraction) first."
            ),
            "status": {"success": False, "error": "missing_fact_types"},
        }

    unstructured = state.get("approved_files", {}).get("unstructured", [])
    if not unstructured:
        return {
            "agent_response": (
                "Cannot build text graph: No unstructured files in approved_files.\n\n"
                "Stage 2 (File Suggestion) must include markdown files."
            ),
            "status": {"success": False, "error": "no_unstructured_files"},
        }

    if not os.environ.get("OPENAI_API_KEY"):
        return {
            "agent_response": (
                "Cannot build text graph: OPENAI_API_KEY not set.\n\n"
                "Required for entity extraction (GPT-4o) and embeddings.\n"
                "Set OPENAI_API_KEY in your environment or .mcp.json."
            ),
            "status": {"success": False, "error": "missing_openai_key"},
        }

    results = await build_text_graph(state, driver, message)
    _save_state(state)  # Persist text_graph_progress

    processed = results["files_processed"]
    errors = results["errors"]
    progress = results["progress"]

    if not processed and not errors:
        return {
            "agent_response": (
                "All markdown files have already been processed.\n\n"
                f"Total processed: {progress['total_processed']}\n"
                f"Pending: {progress['total_pending']}"
            ),
            "status": {"success": True, "already_complete": True, "progress": progress},
        }

    per_file = results.get("per_file_results", [])

    lines = ["Text graph processing complete!\n"]
    if processed:
        lines.append(f"Files processed: {len(processed)}")
        for f in processed:
            # Find diagnostics for this file
            diag = next((r for r in per_file if r["file"] == f), {})
            d = diag.get("diagnostics", {})
            nodes_added = d.get("nodes_added", "?")
            result_info = diag.get("result", "")
            lines.append(f"  [OK] {f} (nodes added: {nodes_added})")
            if result_info:
                lines.append(f"       result: {result_info[:200]}")
    if errors:
        lines.append(f"\nErrors: {len(errors)}")
        for e in errors:
            lines.append(f"  [FAIL] {e}")
        # Show diagnostics for failed files too
        for r in per_file:
            if r.get("status") == "error":
                d = r.get("diagnostics", {})
                if d:
                    lines.append(f"       diagnostics: {d}")
    lines.append(
        f"\nProgress: {progress['total_processed']} processed, "
        f"{progress['total_pending']} pending"
    )
    if progress["pending_files"]:
        lines.append("Pending files:")
        for f in progress["pending_files"]:
            lines.append(f"  - {f}")

    return {
        "agent_response": "\n".join(lines),
        "status": {
            "success": len(errors) == 0,
            "files_processed": processed,
            "errors": errors,
            "progress": progress,
            "per_file_results": per_file,
        },
    }


def _build_resolve(state, driver):
    """Run entity resolution to link subject graph to domain graph.

    Returns:
        dict with agent_response and status.
    """
    from pipelines import resolve_entities

    results = resolve_entities(state, driver)
    _save_state(state)  # Persist text_graph_progress.entity_resolution

    labels_checked = results["labels_checked"]
    labels_resolved = results["labels_resolved"]
    total = results["total_correspondences"]

    if not labels_checked:
        return {
            "agent_response": (
                "Entity resolution: No entity labels found in the subject graph.\n\n"
                "Has the text graph been built? Use scope='unstructured' first."
            ),
            "status": {"success": False, "error": "no_entity_labels"},
        }

    lines = ["Entity resolution complete!\n"]
    lines.append(f"Labels checked: {', '.join(labels_checked)}")
    if labels_resolved:
        lines.append(f"Labels resolved: {', '.join(labels_resolved)}")
    lines.append(f"Total CORRESPONDS_TO relationships: {total}")

    lines.append("\nPer-label results:")
    for result in results["per_label_results"]:
        label = result["label"]
        status = result["status"]
        if status == "resolved":
            lines.append(
                f"  [OK] {label}: {result['entity_key']} <-> {result['domain_key']} "
                f"(similarity {result['key_similarity']:.2f}), "
                f"{result['relationships_created']} correspondences"
            )
        elif status == "error":
            lines.append(f"  [FAIL] {label}: {result['error']}")
        else:
            lines.append(f"  [SKIP] {label}: {result.get('message', status)}")

    return {
        "agent_response": "\n".join(lines),
        "status": {
            "success": True,
            "labels_checked": labels_checked,
            "labels_resolved": labels_resolved,
            "total_correspondences": total,
            "per_label_results": results["per_label_results"],
        },
    }


@mcp.tool
async def kg_build_graph(message: str = "build", scope: str = "structured") -> dict:
    """Build the knowledge graph in Neo4j from approved artifacts.

    Args:
        message: Instructions for the build. For scope="unstructured", controls
                 which files to process:
                 - A specific filename (e.g., "gothenburg_table_reviews.md")
                 - "next" to process the next unprocessed file
                 - "all" or "remaining" to process all pending files
        scope: What to build.
            - "structured" (default): Domain graph from CSVs
            - "unstructured": Subject + Lexical graphs from markdown files
            - "resolve": Entity resolution (link Subject to Domain graph)
            - "all": Everything in sequence (structured -> unstructured -> resolve)

    Returns:
        Dictionary with build results, verification stats, and any errors.
    """
    valid_scopes = ("structured", "unstructured", "resolve", "all")
    if scope not in valid_scopes:
        return {
            "agent_response": (
                f"Invalid scope: '{scope}'.\n\n"
                f"Valid scopes: {', '.join(valid_scopes)}\n"
                "- structured: Build domain graph from CSVs\n"
                "- unstructured: Build subject + lexical graphs from markdown\n"
                "- resolve: Link subject graph entities to domain graph nodes\n"
                "- all: Run all three in sequence"
            ),
            "status": {"success": False, "error": "invalid_scope"},
        }

    state = _load_clean_state()

    # Check Neo4j credentials (needed for all scopes)
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
            "status": {"success": False, "error": "missing_neo4j_credentials"},
        }

    # Import modules
    try:
        from utils import get_neo4j_driver, test_connection, close_driver
    except ImportError as exc:
        return {
            "agent_response": f"Failed to import graph builder modules: {exc}",
            "status": {"success": False, "error": "import_error"},
        }

    # Connect to Neo4j
    try:
        driver = get_neo4j_driver()
        conn_info = test_connection(driver)
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
                "details": str(exc),
            },
        }

    try:
        if scope == "structured":
            result = _build_structured(state, driver, conn_info)

        elif scope == "unstructured":
            result = await _build_unstructured(state, driver, message)

        elif scope == "resolve":
            result = _build_resolve(state, driver)

        elif scope == "all":
            # Run all three phases in sequence
            all_lines = []
            all_status = {"success": True, "phases": {}}

            # Phase 1: Structured
            if "approved_construction_plan" in state:
                all_lines.append("[Phase 1/3] Building domain graph from CSVs...")
                structured_result = _build_structured(state, driver, conn_info)
                all_status["phases"]["structured"] = structured_result["status"]
                all_lines.append(structured_result["agent_response"])
                if not structured_result["status"].get("success", False):
                    all_status["success"] = False
            else:
                all_lines.append(
                    "[Phase 1/3] Skipped: No approved construction plan."
                )

            # Phase 2: Unstructured
            has_unstructured = bool(
                state.get("approved_files", {}).get("unstructured", [])
            )
            has_entities = "approved_entity_types" in state
            has_facts = "approved_fact_types" in state
            has_openai = bool(os.environ.get("OPENAI_API_KEY"))

            if has_unstructured and has_entities and has_facts and has_openai:
                all_lines.append(
                    "\n[Phase 2/3] Building text graph from markdown files..."
                )
                unstructured_result = await _build_unstructured(state, driver, "all")
                all_status["phases"]["unstructured"] = unstructured_result["status"]
                all_lines.append(unstructured_result["agent_response"])
                if not unstructured_result["status"].get("success", False):
                    all_status["success"] = False
            else:
                missing = []
                if not has_unstructured:
                    missing.append("unstructured files")
                if not has_entities:
                    missing.append("approved entity types")
                if not has_facts:
                    missing.append("approved fact types")
                if not has_openai:
                    missing.append("OPENAI_API_KEY")
                all_lines.append(
                    f"\n[Phase 2/3] Skipped: Missing {', '.join(missing)}."
                )

            # Phase 3: Entity Resolution
            all_lines.append("\n[Phase 3/3] Running entity resolution...")
            resolve_result = _build_resolve(state, driver)
            all_status["phases"]["resolve"] = resolve_result["status"]
            all_lines.append(resolve_result["agent_response"])

            result = {
                "agent_response": "\n".join(all_lines),
                "status": all_status,
            }

        close_driver(driver)
        return result

    except Exception as exc:
        try:
            close_driver(driver)
        except Exception:
            pass

        return {
            "agent_response": (
                f"Graph build failed with error:\n\n{exc}\n\n"
                "This may be due to:\n"
                "- Invalid CSV data (duplicates, missing values)\n"
                "- Neo4j connection issues\n"
                "- Missing OPENAI_API_KEY for text processing\n"
                "- Missing APOC plugin for entity resolution\n\n"
                "Check the error message above for details."
            ),
            "status": {
                "success": False,
                "error": "build_failed",
                "details": str(exc),
            },
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
