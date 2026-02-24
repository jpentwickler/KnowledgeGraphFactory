"""MCP Server for KG-Factory.

Exposes KG-Factory agents as tools for Claude Code integration.
Uses FastMCP for the MCP protocol implementation.

Each agent maintains a rolling-window conversation history (last N messages)
so that multi-turn interactions preserve context between MCP calls.
All artifacts are persisted in state (proposed/approved values).
"""

import os
import re
import sys
import threading
import asyncio
import uuid
import inspect
import functools

# Add parent directory to path so we can import from kg-factory modules
_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root_dir)

# Load .env from project root (provides ANTHROPIC_API_KEY, etc.)
from dotenv import load_dotenv
load_dotenv(os.path.join(_root_dir, ".env"))

# Pre-cache langsmith runtime env BEFORE FastMCP takes over stdin/stdout.
# Langsmith's @traceable calls _insert_runtime_env() which invokes exec_git()
# (subprocess.check_output). On Windows, child processes inherit stdin, and
# when FastMCP uses stdio transport the stdin handle is managed by
# ProactorEventLoop's IOCP -- causing subprocess calls to deadlock.
# Calling these lru_cached functions early caches the results so subsequent
# calls during tracing never spawn subprocesses.
if os.environ.get("LANGSMITH_TRACING", "").lower() == "true":
    try:
        from langsmith.env._runtime_env import (
            get_runtime_environment,
            get_langchain_env_var_metadata,
        )
        get_runtime_environment()
        get_langchain_env_var_metadata()
    except Exception:
        pass

from fastmcp import FastMCP

from agents import (
    UserIntentAgent,
    FileSuggestionAgent,
    SchemaProposalAgent,
    SchemaCriticAgent,
    NerExtractionAgent,
    FactExtractionAgent,
    CompetencyQuestionsAgent,
)
from core import load_state, save_state
from core.tracing import mcp_traceable
from utils import get_neo4j_driver, test_connection, close_driver


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

## Background Processing

Some tools may return {"processing": true, "task_id": "..."} instead of
immediate results. When this happens:
1. Show the user that processing has started
2. Wait 5-10 seconds
3. Call kg_get_result(task_id) to check for the result
4. If still processing, wait and retry (up to ~2 minutes)
5. Once complete, show the full result to the user
"""
)

# Session-scoped active project (set by kg_project tool).
_active_project: str | None = None

# Background task storage (for async mode in Cowork)
_background_results: dict[str, dict] = {}    # task_id -> result dict
_background_lock = threading.Lock()


def _is_async_mode() -> bool:
    """Check if async background execution is enabled."""
    return os.environ.get("KG_ASYNC_TOOLS", "").lower() == "true"


def _start_background(func, task_id: str, *args, **kwargs):
    """Run func in a background thread, store result when done.

    For async functions, creates a new event loop in the thread.
    For sync functions, calls directly.
    """
    def _worker():
        try:
            if asyncio.iscoroutinefunction(func):
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(func(*args, **kwargs))
                finally:
                    loop.close()
            else:
                result = func(*args, **kwargs)
        except Exception as e:
            result = {
                "agent_response": f"Background task failed: {e}",
                "status": {"error": str(e)},
            }
        with _background_lock:
            _background_results[task_id] = result

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


def _async_capable(tool_name: str):
    """Decorator: in async mode, run tool in background and return task ID."""
    def decorator(func):
        original_sig = inspect.signature(func)

        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                if not _is_async_mode():
                    return await func(*args, **kwargs)
                task_id = f"{tool_name}_{uuid.uuid4().hex[:8]}"
                _start_background(func, task_id, *args, **kwargs)
                return {
                    "processing": True,
                    "task_id": task_id,
                    "message": f"Started {tool_name}. Call kg_get_result('{task_id}') to check progress.",
                }
        else:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                if not _is_async_mode():
                    return func(*args, **kwargs)
                task_id = f"{tool_name}_{uuid.uuid4().hex[:8]}"
                _start_background(func, task_id, *args, **kwargs)
                return {
                    "processing": True,
                    "task_id": task_id,
                    "message": f"Started {tool_name}. Call kg_get_result('{task_id}') to check progress.",
                }

        # Preserve original signature for FastMCP schema generation
        wrapper.__signature__ = original_sig
        return wrapper
    return decorator


def _get_state_file() -> str:
    """Resolve the state file path based on active project or env vars.

    Priority: KG_BASE_DIR + _active_project > KG_STATE_DIR > default.
    """
    base_dir = os.environ.get("KG_BASE_DIR")
    if base_dir and _active_project:
        return os.path.join(base_dir, _active_project, "state", "current_state.json")
    state_dir = os.environ.get("KG_STATE_DIR", "state")
    return os.path.join(state_dir, "current_state.json")

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
    raw_state = load_state(_get_state_file())
    return {k: v for k, v in raw_state.items() if _should_persist(k)}


def _save_state(state: dict) -> None:
    """Save state to disk, preserving artifacts and conversation keys.

    Merges updated state into the existing file so that keys not touched
    by this agent call are preserved.
    """
    raw_state = load_state(_get_state_file())

    # Keep artifacts + conversation keys from existing state
    clean_raw = {k: v for k, v in raw_state.items() if _should_persist(k)}

    # Merge in updated state
    clean_raw.update(state)

    # Final clean: remove any ephemeral keys that came from agent
    final = {k: v for k, v in clean_raw.items() if _should_persist(k)}

    save_state(final, _get_state_file())


@mcp.tool
@mcp_traceable(name="mcp.kg_get_state")
def kg_get_state() -> dict:
    """Get current KG-Factory pipeline state.

    Returns the current proposed and approved artifacts from the pipeline.
    Use this to check progress and see what's been completed.

    Returns:
        Dictionary with current state (excludes internal metadata).
    """
    state = _load_clean_state()
    # Exclude conversation keys from public display
    result = {k: v for k, v in state.items() if not _is_conversation_key(k)}
    if os.environ.get("KG_BASE_DIR"):
        result["_active_project"] = _active_project
    return result


def _run_kg_get_result(task_id: str) -> dict:
    """Core implementation (testable without MCP decoration)."""
    with _background_lock:
        if task_id in _background_results:
            return _background_results.pop(task_id)
    return {
        "processing": True,
        "task_id": task_id,
        "message": "Still processing. Call kg_get_result again in a few seconds.",
    }


@mcp.tool
@mcp_traceable(name="mcp.kg_get_result")
def kg_get_result(task_id: str) -> dict:
    """Check the result of a background task.

    When a tool returns {"processing": true, "task_id": "..."}, call this
    tool with that task_id to check if it has finished. If still processing,
    wait a few seconds and try again.

    Args:
        task_id: The task ID returned by the original tool call.

    Returns:
        The original tool's result if complete, or
        {"processing": true, "task_id": ..., "message": ...} if still running.
    """
    return _run_kg_get_result(task_id)


# ---------------------------------------------------------------------------
# Project management helpers
# ---------------------------------------------------------------------------

import re as _re


def _check_project_active() -> dict | None:
    """Return error dict if KG_BASE_DIR is set but no project is active. None to proceed."""
    if not os.environ.get("KG_BASE_DIR"):
        return None  # backwards compat -- no guard
    if _active_project:
        return None  # project selected -- proceed
    return {
        "agent_response": (
            "No project selected. Use kg_project to list, open, or create a project first.\n\n"
            "Examples:\n"
            "  kg_project('list')\n"
            "  kg_project('create my_project')\n"
            "  kg_project('open my_project')"
        ),
        "status": {"error": "no_active_project"},
    }


def _validate_project_name(name: str) -> str | None:
    """Return error message if name is invalid, None if valid."""
    if not name:
        return "Project name cannot be empty."
    if ".." in name or "/" in name or "\\" in name:
        return "Project name cannot contain '..', '/' or '\\'."
    if " " in name:
        return "Project name cannot contain spaces. Use underscores or hyphens."
    if not _re.fullmatch(r"[A-Za-z0-9_-]+", name):
        return "Project name must contain only letters, digits, underscores, or hyphens."
    return None


def _detect_stage(state: dict) -> str:
    """Determine how far the pipeline has progressed."""
    if state.get("cq_evaluation_results"):
        return "evaluated"
    if state.get("text_graph_progress"):
        return "graph built"
    if state.get("approved_construction_plan"):
        return "schema approved"
    if state.get("approved_files"):
        return "files selected"
    if state.get("approved_user_goal"):
        return "goal defined"
    return "new"


def _count_data_files(data_dir: str) -> int:
    """Count CSV and markdown files under data_dir."""
    count = 0
    if not os.path.isdir(data_dir):
        return 0
    for root, _dirs, files in os.walk(data_dir):
        for f in files:
            if f.endswith((".csv", ".md", ".markdown")):
                count += 1
    return count


def _activate_project(name: str, base_dir: str) -> None:
    """Set active project and update KG_DATA_DIR for file_tools."""
    global _active_project
    _active_project = name
    os.environ["KG_DATA_DIR"] = os.path.join(base_dir, name, "data")

    # Write marker for query server
    marker = os.path.join(base_dir, "_last_active_project")
    with open(marker, "w", encoding="utf-8") as f:
        f.write(name)

    # Clear all in-memory agent conversations from previous project
    state = _load_clean_state()
    conv_keys = [k for k in state if _is_conversation_key(k)]
    for k in conv_keys:
        del state[k]
    if conv_keys:
        _save_state(state)


def _parse_project_command(message: str) -> tuple[str, str]:
    """Parse command and argument from message.

    Returns:
        (command, argument) tuple. command is one of:
        'list', 'create', 'open', 'status', 'unknown'.
    """
    msg = message.strip().lower()

    if msg in ("list", "ls"):
        return ("list", "")
    if msg in ("status", "info"):
        return ("status", "")

    # For commands with arguments, preserve original case of the argument
    stripped = message.strip()
    if msg.startswith(("create ", "new ")):
        arg_start = stripped.index(" ") + 1
        return ("create", stripped[arg_start:].strip())
    if msg.startswith("open "):
        return ("open", stripped[5:].strip())

    return ("unknown", message)


def _project_list(base_dir: str) -> dict:
    """List available projects under base_dir."""
    if not os.path.isdir(base_dir):
        return {
            "agent_response": f"Base directory does not exist: {base_dir}",
            "status": {"error": "base_dir_missing"},
        }

    projects = []
    for entry in sorted(os.listdir(base_dir)):
        entry_path = os.path.join(base_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        # Must have state/ or data/ subfolder to be a project
        has_state = os.path.isdir(os.path.join(entry_path, "state"))
        has_data = os.path.isdir(os.path.join(entry_path, "data"))
        if not (has_state or has_data):
            continue

        # Load state to detect stage
        state_file = os.path.join(entry_path, "state", "current_state.json")
        try:
            project_state = load_state(state_file)
        except Exception:
            project_state = {}

        stage = _detect_stage(project_state)
        data_count = _count_data_files(os.path.join(entry_path, "data"))

        projects.append({
            "name": entry,
            "stage": stage,
            "data_files": data_count,
        })

    if not projects:
        lines = [
            "No projects found.\n",
            "Create one with: kg_project('create my_project')",
        ]
    else:
        lines = ["Available projects:"]
        for i, p in enumerate(projects, 1):
            active = " (active)" if p["name"] == _active_project else ""
            lines.append(
                f"  {i}. {p['name']} ({p['stage']}, {p['data_files']} data files){active}"
            )

        lines.append("")
        if _active_project:
            lines.append(f"Active project: {_active_project}")
        else:
            lines.append("No project selected.")

    return {
        "agent_response": "\n".join(lines),
        "status": {"projects": projects, "active_project": _active_project},
    }


def _project_create(name: str, base_dir: str) -> dict:
    """Create a new project."""
    error = _validate_project_name(name)
    if error:
        return {
            "agent_response": f"Invalid project name: {error}",
            "status": {"error": "invalid_name"},
        }

    project_dir = os.path.join(base_dir, name)
    if os.path.exists(project_dir):
        return {
            "agent_response": (
                f"Project '{name}' already exists. Use kg_project('open {name}') to open it."
            ),
            "status": {"error": "already_exists"},
        }

    # Create directories
    os.makedirs(os.path.join(project_dir, "state"), exist_ok=True)
    os.makedirs(os.path.join(project_dir, "data"), exist_ok=True)

    _activate_project(name, base_dir)

    data_path = os.path.join(base_dir, name, "data")
    return {
        "agent_response": (
            f'Project "{name}" created.\n'
            f"  State: {os.path.join(base_dir, name, 'state')}\n"
            f"  Data:  {data_path}\n\n"
            "Place your CSV and markdown files in the data directory, "
            "then we can start defining your graph goal."
        ),
        "status": {"created": name, "active_project": name, "data_dir": data_path},
    }


def _project_open(name: str, base_dir: str) -> dict:
    """Open an existing project."""
    project_dir = os.path.join(base_dir, name)
    if not os.path.isdir(project_dir):
        return {
            "agent_response": (
                f"Project '{name}' not found. Use kg_project('create {name}') to create it."
            ),
            "status": {"error": "not_found"},
        }

    _activate_project(name, base_dir)

    # Load and summarize state
    state = _load_clean_state()
    stage = _detect_stage(state)
    data_count = _count_data_files(os.path.join(base_dir, name, "data"))

    # Summarize approved artifacts
    artifacts = []
    if state.get("approved_user_goal"):
        goal = state["approved_user_goal"]
        goal_text = goal.get("description", "") if isinstance(goal, dict) else str(goal)
        artifacts.append(f"  Goal: {goal_text[:100]}")
    if state.get("approved_files"):
        files = state["approved_files"]
        structured = files.get("structured", [])
        unstructured = files.get("unstructured", [])
        artifacts.append(f"  Files: {len(structured)} structured, {len(unstructured)} unstructured")
    if state.get("approved_construction_plan"):
        plan = state["approved_construction_plan"]
        artifacts.append(f"  Schema: {len(plan)} entries")
    if state.get("approved_entity_types"):
        artifacts.append(f"  Entity types: {len(state['approved_entity_types'])}")
    if state.get("approved_fact_types"):
        artifacts.append(f"  Fact types: {len(state['approved_fact_types'])}")

    lines = [
        f'Opened project "{name}".',
        f"  Stage: {stage}",
        f"  Data files: {data_count}",
    ]
    if artifacts:
        lines.append("  Approved artifacts:")
        lines.extend(f"    {a.strip()}" for a in artifacts)

    return {
        "agent_response": "\n".join(lines),
        "status": {"opened": name, "active_project": name, "stage": stage},
    }


def _project_status(base_dir: str) -> dict:
    """Return active project info or guidance."""
    if not _active_project:
        return {
            "agent_response": (
                "No project selected.\n\n"
                "Use kg_project('list') to see available projects, or\n"
                "kg_project('create <name>') to start a new one."
            ),
            "status": {"active_project": None},
        }

    state = _load_clean_state()
    stage = _detect_stage(state)
    data_count = _count_data_files(os.path.join(base_dir, _active_project, "data"))

    return {
        "agent_response": (
            f"Active project: {_active_project}\n"
            f"  Stage: {stage}\n"
            f"  Data files: {data_count}"
        ),
        "status": {"active_project": _active_project, "stage": stage, "data_files": data_count},
    }


def _run_kg_project(message: str) -> dict:
    """Core implementation of project management (testable without MCP)."""
    base_dir = os.environ.get("KG_BASE_DIR")
    if not base_dir:
        return {
            "agent_response": (
                "KG_BASE_DIR not set. Set it in your MCP server config to enable "
                "project management.\n\n"
                "Example in claude_desktop_config.json:\n"
                '  "env": {"KG_BASE_DIR": "/path/to/projects"}'
            ),
            "status": {"error": "no_base_dir"},
        }

    command, arg = _parse_project_command(message)

    if command == "list":
        return _project_list(base_dir)
    elif command == "create":
        return _project_create(arg, base_dir)
    elif command == "open":
        return _project_open(arg, base_dir)
    elif command == "status":
        return _project_status(base_dir)
    else:
        return {
            "agent_response": (
                "Unknown command. Available commands:\n\n"
                "  kg_project('list')           - List available projects\n"
                "  kg_project('create <name>')  - Create a new project\n"
                "  kg_project('open <name>')    - Open an existing project\n"
                "  kg_project('status')         - Show active project info"
            ),
            "status": {"error": "unknown_command"},
        }


@mcp.tool
@mcp_traceable(name="mcp.kg_project")
def kg_project(message: str) -> dict:
    """Manage KG-Factory projects.

    Use 'list' to see projects, 'create <name>' to start a new one,
    'open <name>' to switch to an existing one, 'status' to see the
    active project.

    Args:
        message: Command string (e.g., "list", "create my_project", "open my_project", "status").

    Returns:
        Dictionary with project info and status.
    """
    return _run_kg_project(message)


@mcp.tool
@mcp_traceable(name="mcp.kg_user_intent")
@_async_capable("kg_user_intent")
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
    guard = _check_project_active()
    if guard:
        return guard
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
        "has_proposed_cqs": "proposed_competency_questions" in state,
        "has_approved_cqs": "approved_competency_questions" in state,
    }

    if "proposed_user_goal" in state:
        status["proposed_goal"] = state["proposed_user_goal"]
    if "approved_user_goal" in state:
        status["approved_goal"] = state["approved_user_goal"]
    if "proposed_competency_questions" in state:
        status["proposed_cqs"] = state["proposed_competency_questions"]
    if "approved_competency_questions" in state:
        status["approved_cqs"] = state["approved_competency_questions"]

    return {
        "agent_response": response,
        "status": status
    }


@mcp.tool
@mcp_traceable(name="mcp.kg_file_suggestion")
@_async_capable("kg_file_suggestion")
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
    guard = _check_project_active()
    if guard:
        return guard
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
@mcp_traceable(name="mcp.kg_schema_proposal")
@_async_capable("kg_schema_proposal")
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
    guard = _check_project_active()
    if guard:
        return guard
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
@mcp_traceable(name="mcp.kg_competency_questions")
@_async_capable("kg_competency_questions")
def kg_competency_questions(message: str) -> dict:
    """Send a message to the Competency Questions Management Agent.

    Manages competency questions at any pipeline stage. Can add, modify,
    delete, and approve competency questions that define what the knowledge
    graph must be able to answer.

    Pass the user's message exactly as they wrote it. Multi-turn conversation.
    Call once per user message. Stage 1 (User Intent) must be completed first.

    Args:
        message: The user's message, passed through exactly as written.

    Returns:
        Dictionary with agent response and current status.
    """
    guard = _check_project_active()
    if guard:
        return guard
    state = _load_clean_state()
    conversation = _pop_conversation(state, "_competency_questions_conversation")

    agent = CompetencyQuestionsAgent()
    response, state, conversation = agent.run(message, state, conversation)

    _store_conversation(
        state, "_competency_questions_conversation", conversation
    )
    _save_state(state)

    # Build status info
    status = {
        "has_proposed_cqs": "proposed_competency_questions" in state,
        "has_approved_cqs": "approved_competency_questions" in state,
    }

    if "proposed_competency_questions" in state:
        status["proposed_cqs"] = state["proposed_competency_questions"]
        status["proposed_count"] = len(state["proposed_competency_questions"])

    if "approved_competency_questions" in state:
        status["approved_cqs"] = state["approved_competency_questions"]
        status["approved_count"] = len(state["approved_competency_questions"])

    return {
        "agent_response": response,
        "status": status,
    }


@mcp.tool
@mcp_traceable(name="mcp.kg_critic")
@_async_capable("kg_critic")
def kg_critic(scope: str = "structured") -> dict:
    """Run the critic agent to review proposed artifacts for problems.

    The critic is an independent reviewer that checks for errors, missing
    elements, and inconsistencies. It does NOT approve or finalize anything.

    Three scopes are available:
    - "structured" (default): Reviews the construction plan against CSV files.
      Use after kg_schema_proposal to check column references, identifier
      uniqueness, and relationship correctness.
    - "unstructured": Reviews entity types and fact types against markdown files.
      Use after kg_ner_extraction or kg_fact_extraction to check text grounding,
      overlapping types, and predicate quality.
    - "competency": Reviews competency questions against available artifacts.
      Use after kg_user_intent or kg_competency_questions to validate CQs.

    No message needed -- the critic analyzes whatever is currently proposed.

    Args:
        scope: What to review. "structured", "unstructured", or "competency".

    Returns:
        Dictionary with critic verdict, problems list, and response text.
    """
    guard = _check_project_active()
    if guard:
        return guard
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
    elif scope == "competency":
        has_cqs = (
            "proposed_competency_questions" in state
            or "approved_competency_questions" in state
        )
        if not has_cqs:
            return {
                "agent_response": "No competency questions to review. "
                "Use kg_user_intent or kg_competency_questions first.",
                "status": {"error": "no_competency_questions"},
            }
    else:
        return {
            "agent_response": (
                f"Invalid scope: '{scope}'. "
                "Use 'structured', 'unstructured', or 'competency'."
            ),
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


def _run_ner_extraction(message: str) -> dict:
    """Core implementation for kg_ner_extraction (testable without MCP decoration)."""
    guard = _check_project_active()
    if guard:
        return guard
    state = _load_clean_state()
    conversation = _pop_conversation(state, "_ner_extraction_conversation")
    has_prior_proposal = "proposed_entity_types" in state

    # First call: use structured output (fast path)
    if conversation is None and not has_prior_proposal:
        try:
            from tools.extraction_tools import (
                build_file_content,
                propose_entity_types,
                gather_evidence,
                merge_entity_proposals,
                _format_entity_proposal_response,
            )

            content, fits = build_file_content(state)

            if fits:
                result = propose_entity_types(
                    state, content=content, user_message=message
                )
            else:
                # Per-file fallback for large content
                proposals = []
                for _path, file_text in content.items():
                    proposals.append(propose_entity_types(state, content=file_text))
                result = merge_entity_proposals(proposals)

            # Gather evidence programmatically (no LLM calls)
            entity_types_with_evidence = gather_evidence(
                state, result["entity_types"]
            )

            # Save as proposed (same format as handle_set_proposed_entities)
            proposed = {}
            for et in entity_types_with_evidence:
                entry = {
                    "source": et["source"],
                    "description": et["description"],
                }
                if "grounding_evidence" in et:
                    entry["grounding_evidence"] = et["grounding_evidence"]
                proposed[et["name"]] = entry
            state["proposed_entity_types"] = proposed

            response = _format_entity_proposal_response(
                result, entity_types_with_evidence
            )

            # Seed conversation so agent loop has context on follow-up calls
            seed = [
                {"role": "user", "content": message},
                {"role": "assistant", "content": response},
            ]
            _store_conversation(state, "_ner_extraction_conversation", seed)

            _save_state(state)

            # Build status
            status = {
                "has_proposed_entities": True,
                "has_approved_entities": "approved_entity_types" in state,
                "proposed_entities": proposed,
                "entity_count": len(proposed),
                "mode": "structured_output",
            }
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
            return {"agent_response": response, "status": status}

        except Exception as exc:
            # Fallback to agent loop on error
            import logging
            logging.getLogger(__name__).warning(
                "Structured output failed, falling back to agent loop: %s", exc
            )
            # Re-load state (may have been partially modified)
            state = _load_clean_state()
            conversation = None

    # Iteration path: existing agent loop
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
@mcp_traceable(name="mcp.kg_ner_extraction")
@_async_capable("kg_ner_extraction")
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
    return _run_ner_extraction(message)


def _run_fact_extraction(message: str) -> dict:
    """Core implementation for kg_fact_extraction (testable without MCP decoration)."""
    guard = _check_project_active()
    if guard:
        return guard
    state = _load_clean_state()
    conversation = _pop_conversation(state, "_fact_extraction_conversation")
    has_prior_proposal = "proposed_fact_types" in state

    # First call: use structured output (fast path)
    if conversation is None and not has_prior_proposal:
        try:
            from tools.extraction_tools import (
                build_file_content,
                propose_fact_types,
                merge_fact_proposals,
                _format_fact_proposal_response,
            )

            content, fits = build_file_content(state)

            if fits:
                result = propose_fact_types(
                    state, content=content, user_message=message
                )
            else:
                # Per-file fallback for large content
                proposals = []
                for _path, file_text in content.items():
                    proposals.append(propose_fact_types(state, content=file_text))
                result = merge_fact_proposals(proposals)

            # Validate subject/object against approved entity types
            approved_entities = state.get("approved_entity_types", {})
            valid_facts = {}
            for ft in result.get("fact_types", []):
                subj = ft["subject"]
                obj = ft["object"]
                pred = ft["predicate"]
                # Skip if subject or object not in approved entities
                if subj not in approved_entities or obj not in approved_entities:
                    continue
                # Skip if predicate format is invalid
                if not re.match(r"^[a-z][a-z0-9_]*$", pred):
                    continue
                valid_facts[pred] = {
                    "subject_label": subj,
                    "predicate_label": pred,
                    "object_label": obj,
                    "description": ft.get("description", ""),
                }

            state["proposed_fact_types"] = valid_facts

            response = _format_fact_proposal_response(result)

            # Seed conversation so agent loop has context on follow-up calls
            seed = [
                {"role": "user", "content": message},
                {"role": "assistant", "content": response},
            ]
            _store_conversation(state, "_fact_extraction_conversation", seed)

            _save_state(state)

            # Build status
            entity_types = state.get("approved_entity_types", {})
            unstructured = state.get("approved_files", {}).get("unstructured", [])
            status = {
                "has_proposed_facts": True,
                "has_approved_facts": "approved_fact_types" in state,
                "proposed_facts": valid_facts,
                "fact_count": len(valid_facts),
                "mode": "structured_output",
                "pre_computation_summary": {
                    "files_analyzed": len(unstructured),
                    "file_names": [f["path"] for f in unstructured],
                    "entity_types_available": sorted(entity_types.keys()),
                },
            }
            return {"agent_response": response, "status": status}

        except Exception as exc:
            # Fallback to agent loop on error
            import logging
            logging.getLogger(__name__).warning(
                "Structured output failed, falling back to agent loop: %s", exc
            )
            state = _load_clean_state()
            conversation = None

    # Iteration path: existing agent loop
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
@mcp_traceable(name="mcp.kg_fact_extraction")
@_async_capable("kg_fact_extraction")
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
    return _run_fact_extraction(message)


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


def _create_text_indexes(driver) -> dict:
    """Create chunk-embeddings (vector) and chunk-fulltext indexes.

    Idempotent: Uses IF NOT EXISTS + SHOW INDEXES check.
    Non-blocking: Failures logged, don't stop graph building.

    Args:
        driver: Neo4j driver instance

    Returns:
        {
            "chunk-embeddings": {"status": "created"|"exists"|"failed", "message": str},
            "chunk-fulltext": {"status": "created"|"exists"|"failed", "message": str}
        }
    """
    results = {}

    # Define indexes to create
    indexes = {
        "chunk-embeddings": {
            "type": "vector",
            "cypher": """
                CREATE VECTOR INDEX `chunk-embeddings` IF NOT EXISTS
                FOR (c:Chunk) ON c.embedding
                OPTIONS {indexConfig: {
                    `vector.dimensions`: 3072,
                    `vector.similarity_function`: 'cosine'
                }}
            """
        },
        "chunk-fulltext": {
            "type": "fulltext",
            "cypher": """
                CREATE FULLTEXT INDEX `chunk-fulltext` IF NOT EXISTS
                FOR (c:Chunk) ON EACH [c.text]
            """
        }
    }

    with driver.session() as session:
        # Check existing indexes first
        try:
            existing_indexes = session.run("SHOW INDEXES YIELD name RETURN name")
            existing_names = {record["name"] for record in existing_indexes}
        except Exception as e:
            # If SHOW INDEXES fails, proceed with IF NOT EXISTS logic
            existing_names = set()
            print(f"Warning: Could not check existing indexes: {e}")

        # Create each index
        for index_name, config in indexes.items():
            try:
                # Check if already exists
                if index_name in existing_names:
                    results[index_name] = {
                        "status": "exists",
                        "message": f"{config['type'].capitalize()} index already exists"
                    }
                    continue

                # Create index
                session.run(config["cypher"])
                results[index_name] = {
                    "status": "created",
                    "message": f"{config['type'].capitalize()} index created successfully"
                }

            except Exception as e:
                error_msg = str(e)
                results[index_name] = {
                    "status": "failed",
                    "message": f"Failed to create {config['type']} index: {error_msg}"
                }

                # Log warning but don't raise (non-blocking)
                if "insufficient privilege" in error_msg.lower():
                    print(f"Warning: Insufficient privileges to create index '{index_name}'. "
                          "Vector/hybrid search may not work. Contact your Neo4j admin.")
                else:
                    print(f"Warning: Failed to create index '{index_name}': {error_msg}")

    return results


@mcp_traceable(name="mcp._build_structured")
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


@mcp_traceable(name="mcp._build_unstructured")
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

    # Create indexes after first successful file processing (Phase 3: US013)
    if results["files_processed"] and "_index_creation_attempted" not in state:
        index_status = _create_text_indexes(driver)
        state["_index_creation_status"] = index_status
        state["_index_creation_attempted"] = True
        _save_state(state)  # Persist ephemeral status for debugging

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


@mcp_traceable(name="mcp._build_resolve")
def _build_resolve(state, driver, message=""):
    """Run entity resolution to link subject graph to domain graph.

    Supports two modes:
    - Initial run: auto-resolves confident matches, displays candidates for review
    - Approval: creates links for human-approved candidates

    Args:
        state: Pipeline state dict.
        driver: Neo4j driver instance.
        message: Controls behavior — empty/"resolve" for initial run,
                 "approve all"/"approve 1,2,3"/"skip"/"reject" for candidate review.

    Returns:
        dict with agent_response and status.
    """
    msg_lower = message.strip().lower()

    # --- Approval mode: handle previously proposed candidates ---
    if msg_lower.startswith("approve") or msg_lower in ("reject", "skip"):
        return _handle_candidate_approval(state, driver, msg_lower)

    # --- Initial run: auto-resolve + discover candidates ---
    from pipelines import resolve_entities

    results = resolve_entities(state, driver)
    _save_state(state)  # Persist text_graph_progress + proposed_resolution_candidates

    labels_checked = results["labels_checked"]
    labels_resolved = results["labels_resolved"]
    total = results["total_correspondences"]
    candidates = results.get("candidates", [])

    if not labels_checked:
        return {
            "agent_response": (
                "Entity resolution: No entity labels found in the subject graph.\n\n"
                "Has the text graph been built? Use scope='unstructured' first."
            ),
            "status": {"success": False, "error": "no_entity_labels"},
        }

    lines = ["Entity resolution complete!\n"]

    # Auto-resolved summary
    lines.append("Auto-resolved:")
    for result in results["per_label_results"]:
        label = result["label"]
        status = result["status"]
        if status == "resolved":
            lines.append(
                f"  [OK] {label}: {result['entity_key']} <-> {result['domain_key']}, "
                f"{result['relationships_created']} correspondences"
            )
        elif status == "error":
            lines.append(f"  [FAIL] {label}: {result['error']}")
        else:
            lines.append(f"  [SKIP] {label}: {result.get('message', status)}")

    lines.append(f"\nTotal CORRESPONDS_TO relationships: {total}")

    # Candidate summary
    if candidates:
        lines.append(f"\nCandidates requiring approval ({len(candidates)}):")
        for i, c in enumerate(candidates, 1):
            lines.append(
                f'  [{i}] "{c["entity_name"]}" -> "{c["domain_name"]}" '
                f'({c["label"]}, distance: {c["distance"]:.3f})'
            )
        lines.append('\nReply with: "approve all", "approve 1,2", or "skip"')

    return {
        "agent_response": "\n".join(lines),
        "status": {
            "success": True,
            "labels_checked": labels_checked,
            "labels_resolved": labels_resolved,
            "total_correspondences": total,
            "per_label_results": results["per_label_results"],
            "candidates_count": len(candidates),
        },
    }


def _handle_candidate_approval(state, driver, msg_lower):
    """Process human approval/rejection of resolution candidates.

    Args:
        state: Pipeline state dict.
        driver: Neo4j driver instance.
        msg_lower: Lowercased message string.

    Returns:
        dict with agent_response and status.
    """
    from pipelines import create_correspondences_for_candidates

    candidates = state.get("proposed_resolution_candidates", [])
    if not candidates:
        return {
            "agent_response": (
                "No pending resolution candidates to approve.\n\n"
                "Run entity resolution first with scope='resolve'."
            ),
            "status": {"success": False, "error": "no_candidates"},
        }

    # Reject / skip — clear candidates without creating links
    if msg_lower in ("reject", "skip"):
        state.pop("proposed_resolution_candidates", None)
        _save_state(state)
        return {
            "agent_response": (
                f"Skipped {len(candidates)} candidate(s). "
                "No additional links created."
            ),
            "status": {"success": True, "action": "skipped", "count": 0},
        }

    # Determine which candidates are approved
    if msg_lower == "approve all":
        approved = candidates
    else:
        # Parse "approve 1,2,3" or "approve 1, 3, 5"
        index_str = msg_lower.replace("approve", "").strip()
        try:
            indices = [int(x.strip()) for x in index_str.split(",") if x.strip()]
        except ValueError:
            return {
                "agent_response": (
                    f"Could not parse indices from: '{msg_lower}'\n\n"
                    'Expected: "approve all", "approve 1,2,3", or "skip"'
                ),
                "status": {"success": False, "error": "parse_error"},
            }
        # Validate indices (1-based)
        invalid = [i for i in indices if i < 1 or i > len(candidates)]
        if invalid:
            return {
                "agent_response": (
                    f"Invalid indices: {invalid}. "
                    f"Valid range: 1-{len(candidates)}."
                ),
                "status": {"success": False, "error": "invalid_indices"},
            }
        approved = [candidates[i - 1] for i in indices]

    # Group approved candidates by (label, entity_key, domain_key)
    groups = {}
    for c in approved:
        key = (c["label"], c["entity_key"], c["domain_key"])
        groups.setdefault(key, []).append(c)

    total_created = 0
    lines = ["Approved candidates linked!\n"]

    for (label, entity_key, domain_key), pairs in groups.items():
        count = create_correspondences_for_candidates(
            driver, label, entity_key, domain_key, pairs
        )
        total_created += count
        for p in pairs:
            lines.append(
                f'  [OK] {label}: "{p["entity_name"]}" -> "{p["domain_name"]}"'
            )

    lines.append(f"\nTotal new CORRESPONDS_TO relationships: {total_created}")

    # Move from proposed to approved
    state["approved_resolution_candidates"] = approved
    state.pop("proposed_resolution_candidates", None)
    _save_state(state)

    return {
        "agent_response": "\n".join(lines),
        "status": {
            "success": True,
            "action": "approved",
            "count": total_created,
            "approved_pairs": len(approved),
        },
    }


@mcp.tool
@mcp_traceable(name="mcp.kg_build_graph")
@_async_capable("kg_build_graph")
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
    guard = _check_project_active()
    if guard:
        return guard
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
            result = _build_resolve(state, driver, message)

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
@mcp_traceable(name="mcp.kg_query")
@_async_capable("kg_query")
async def kg_query(question: str, context: str = "") -> dict:
    """Query the knowledge graph with adaptive retrieval.

    Automatically selects optimal strategy based on question type and available graph layers:
    - schema: Graph structure exploration
    - cypher: Structured traversal queries
    - vector: Semantic similarity search
    - hybrid: Vector + keyword search
    - cross_layer: Hybrid search + domain entity traversal

    Args:
        question: Natural language question or Cypher query
        context: Optional context to guide strategy selection (default: "")

    Returns:
        {
            "answer": str,              # Formatted query results
            "evidence": list,           # Raw evidence items
            "confidence": float,        # 0.0-1.0 confidence score
            "details": dict,            # Strategy, parameters, metadata
            "status": {
                "success": bool,
                "selected_strategy": str,
                "reasoning": str,
                "error": str (if failed)
            }
        }

    Examples:
        # Schema exploration
        kg_query("What labels exist in the graph?")

        # Cypher query
        kg_query("MATCH (s:Supplier) RETURN s.name LIMIT 5")

        # Semantic search
        kg_query("Tell me about supply chain delays")

        # Hybrid search
        kg_query("Documents about quality issues")

        # Cross-layer traversal
        kg_query("What suppliers are mentioned in reviews?")
    """
    guard = _check_project_active()
    if guard:
        return guard
    from pipelines.query_builder import (
        _select_retrieval_strategy,
        _execute_schema_query,
        _execute_cypher,
        _execute_vector_search,
        _execute_hybrid_search,
        _execute_cross_layer_traversal
    )

    try:
        state = _load_clean_state()
        driver = get_neo4j_driver()

        try:
            # Select strategy via Claude
            strategy_data = await _select_retrieval_strategy(question, context, state)
            strategy = strategy_data["strategy"]
            params = strategy_data.get("parameters", {})
            reasoning = strategy_data.get("reasoning", "")

            # Execute selected strategy
            if strategy == "schema":
                result = _execute_schema_query(driver, state)
            elif strategy == "cypher":
                result = _execute_cypher(driver, params["cypher_query"])
            elif strategy == "vector":
                result = _execute_vector_search(driver, question, params.get("top_k", 5))
            elif strategy == "hybrid":
                result = _execute_hybrid_search(driver, question, params.get("top_k", 5))
            elif strategy == "cross_layer":
                result = _execute_cross_layer_traversal(driver, question, params.get("top_k", 5), state)
            else:
                # Fallback to schema if unknown strategy
                result = _execute_schema_query(driver, state)
                reasoning = f"Unknown strategy '{strategy}', falling back to schema"

            # Add status metadata
            result["status"] = {
                "success": True,
                "selected_strategy": strategy,
                "reasoning": reasoning
            }

            return result

        finally:
            close_driver(driver)

    except Exception as e:
        error_msg = str(e)
        return {
            "answer": f"Query failed: {error_msg}",
            "evidence": [],
            "confidence": 0.0,
            "details": {},
            "status": {
                "success": False,
                "error": error_msg
            }
        }


def _classify_cqs_batch(cqs: dict, state: dict) -> dict:
    """Classify all CQs in a single Claude call.

    Makes one API call that receives all CQ questions and the graph schema,
    then classifies each as "cross_layer" (semantic) or "cypher" (structural/
    aggregation). For cypher CQs, a valid read-only Cypher query is generated.

    Args:
        cqs: {cq_id: cq_data} subset to classify.
        state: Pipeline state for schema context extraction.

    Returns:
        {cq_id: {"strategy": "cross_layer"|"cypher", "cypher_query": str|None}}
        Falls back to all cross_layer on any error.
    """
    import json as _json
    import anthropic
    from core.tracing import wrap_anthropic
    from tools.query_tools import (
        _get_domain_labels,
        _get_domain_node_properties,
        _get_domain_relationships,
        _get_text_entities,
        _get_text_relationships,
        _validate_read_only_cypher,
    )

    fallback = {cq_id: {"strategy": "cross_layer", "cypher_query": None} for cq_id in cqs}

    try:
        # Build schema context (same as _select_retrieval_strategy)
        domain_labels = _get_domain_labels(state)
        domain_node_props = _get_domain_node_properties(state)
        domain_rels = _get_domain_relationships(state)
        text_entities = _get_text_entities(state)
        text_rels = _get_text_relationships(state)

        graph_context = []
        if domain_node_props:
            lines = ["Domain nodes:"]
            for label, props in domain_node_props.items():
                if props:
                    lines.append(f"  {label} [{', '.join(props)}]")
                else:
                    lines.append(f"  {label}")
            graph_context.append("\n".join(lines))
        elif domain_labels:
            graph_context.append(f"Domain nodes: {', '.join(domain_labels)}")
        if domain_rels:
            rel_strs = []
            for r in domain_rels:
                s = f"{r['type']} ({r['from']} -> {r['to']}"
                if r.get("properties"):
                    s += f" [{', '.join(r['properties'])}]"
                s += ")"
                rel_strs.append(s)
            graph_context.append(f"Domain relationships: {', '.join(rel_strs)}")
        if text_entities:
            graph_context.append(f"Text entities: {', '.join(text_entities[:5])}")
        if text_rels:
            rel_strs = [f"{r['type']} ({r['from']} -> {r['to']})" for r in text_rels]
            graph_context.append(f"Text relationships: {', '.join(rel_strs)}")

        graph_summary = "\n".join(graph_context) if graph_context else "(no graph built yet)"

        system_prompt = f"""You are a knowledge graph query classifier.

Graph schema:
{graph_summary}

Classify each competency question as either:
- "cypher": The question asks for counts, aggregations, rankings, or precise
  structural lookups answerable by a single Cypher query using the known schema.
  For these, generate a safe, read-only Cypher query.
- "cross_layer": The question involves semantic understanding, sentiment,
  qualitative content, or requires searching unstructured text from reviews
  or documents.

Rules for Cypher queries:
- Blocked keywords: CREATE, DELETE, SET, REMOVE, MERGE
- Must contain: MATCH or RETURN
- Use only the node labels and relationship types listed in the schema above
- Use property names as they appear in the schema
- If the question requires data from both domain and text layers, classify as "cross_layer"

Respond with JSON only (no markdown):
{{
  "<cq_id>": {{
    "strategy": "cross_layer" | "cypher",
    "cypher_query": "<query>" | null,
    "reasoning": "<one sentence>"
  }},
  ...
}}"""

        cq_lines = "\n".join(
            f"{cq_id}: {cq_data['question']}"
            for cq_id, cq_data in cqs.items()
        )
        user_message = f"Classify these competency questions:\n{cq_lines}"

        client = wrap_anthropic(anthropic.Anthropic())
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}]
        )

        response_text = response.content[0].text.strip()
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        raw = _json.loads(response_text)

        result = {}
        for cq_id in cqs:
            entry = raw.get(cq_id, {})
            strategy = entry.get("strategy", "cross_layer")
            cypher_query = entry.get("cypher_query") or None

            if strategy == "cypher" and cypher_query:
                try:
                    _validate_read_only_cypher(cypher_query)
                except ValueError:
                    strategy = "cross_layer"
                    cypher_query = None
            elif strategy == "cypher":
                # No query provided — downgrade
                strategy = "cross_layer"

            result[cq_id] = {"strategy": strategy, "cypher_query": cypher_query}

        # Fill in any CQ IDs Claude missed
        for cq_id in cqs:
            if cq_id not in result:
                result[cq_id] = {"strategy": "cross_layer", "cypher_query": None}

        return result

    except Exception as e:
        print(f"Warning: Batch CQ classification failed: {e}")
        return fallback


def _evaluate_single_cq(
    driver,
    question: str,
    state: dict,
    strategy_result: dict | None = None,
) -> dict:
    """Evaluate a single competency question.

    Executes the pre-computed strategy from _classify_cqs_batch, then falls
    back to remaining semantic strategies if the primary yields no evidence.

    Args:
        driver: Neo4j driver instance
        question: CQ question text
        state: Pipeline state (for cross_layer schema context)
        strategy_result: Pre-computed {strategy, cypher_query} from
            _classify_cqs_batch. Defaults to cross_layer when not provided.

    Returns:
        {
            "strategy_used": str,
            "strategies_tried": [str],
            "evidence_count": int,
            "has_cross_layer_bridge": bool,
            "evidence": list               # Capped at 10 items
        }
    """
    from pipelines.query_builder import (
        _execute_cypher,
        _execute_vector_search,
        _execute_hybrid_search,
        _execute_cross_layer_traversal,
    )

    strategies_tried = []
    all_evidence = []
    has_cross_layer_bridge = False
    strategy_used = None

    if strategy_result is None:
        strategy_result = {}
    primary_strategy = strategy_result.get("strategy", "cross_layer")
    cypher_query = strategy_result.get("cypher_query")
    params = {"cypher_query": cypher_query} if cypher_query else {}

    def _try_strategy(strategy, params):
        """Execute a strategy and return evidence list, or [] on failure."""
        nonlocal has_cross_layer_bridge
        try:
            if strategy == "cypher":
                query = params.get("cypher_query", "")
                if not query:
                    return []
                result = _execute_cypher(driver, query)
            elif strategy == "vector":
                result = _execute_vector_search(driver, question, top_k=5)
            elif strategy == "hybrid":
                result = _execute_hybrid_search(driver, question, top_k=5)
            elif strategy == "cross_layer":
                result = _execute_cross_layer_traversal(
                    driver, question, top_k=5, state=state
                )
            else:
                return []

            evidence = result.get("evidence", [])
            if evidence and strategy == "cross_layer":
                has_cross_layer_bridge = any(
                    e.get("metadata", {}).get("domain_entity") is not None
                    for e in evidence
                )
            return evidence
        except Exception:
            return []

    # Try primary strategy
    evidence = _try_strategy(primary_strategy, params)
    if evidence:
        strategies_tried.append(primary_strategy)
        strategy_used = primary_strategy
        all_evidence.extend(evidence)
    else:
        # Fallback: try remaining semantic strategies (skip schema and already-tried)
        for fallback in ["vector", "hybrid", "cross_layer"]:
            if fallback == primary_strategy:
                continue
            evidence = _try_strategy(fallback, {})
            if evidence:
                strategies_tried.append(fallback)
                if strategy_used is None:
                    strategy_used = fallback
                all_evidence.extend(evidence)

    # Deduplicate evidence by first 100 chars of content (or full record for cypher)
    seen = set()
    unique_evidence = []
    for e in all_evidence:
        key = str(e.get("content") or e)[:100]
        if key and key not in seen:
            seen.add(key)
            unique_evidence.append(e)

    return {
        "strategy_used": strategy_used or primary_strategy,
        "strategies_tried": strategies_tried,
        "evidence_count": len(unique_evidence),
        "has_cross_layer_bridge": has_cross_layer_bridge,
        "evidence": unique_evidence[:10],
    }


# Priority sort order for CQ results
_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _run_cq_evaluation(cq_id: str = "", cq_ids: list[str] = None) -> dict:
    """Core implementation of CQ evaluation (testable without MCP decoration).

    Args:
        cq_id: Single approved CQ ID to evaluate (e.g., "CQ3").
        cq_ids: List of approved CQ IDs to evaluate (e.g., ["CQ1", "CQ3"]).
                If neither provided: evaluates ALL approved CQs.

    Returns:
        Single CQ: Individual assessment with evidence details.
        Multiple CQs: Coverage scorecard with per-CQ results.
    """
    guard = _check_project_active()
    if guard:
        return guard
    from datetime import datetime, timezone

    state = _load_clean_state()

    cqs = state.get("approved_competency_questions", {})
    if not cqs:
        return {
            "agent_response": (
                "No approved competency questions to evaluate.\n\n"
                "Use kg_user_intent or kg_competency_questions first to "
                "define and approve competency questions."
            ),
            "status": {"error": "no_approved_cqs"},
        }

    # Determine which CQs to evaluate
    if cq_id:
        if cq_id not in cqs:
            return {
                "agent_response": (
                    f"CQ ID '{cq_id}' not found in approved CQs.\n"
                    f"Available CQ IDs: {', '.join(sorted(cqs.keys()))}"
                ),
                "status": {"error": "cq_not_found"},
            }
        cqs_to_evaluate = {cq_id: cqs[cq_id]}
        is_single = True
    elif cq_ids:
        cqs_to_evaluate = {
            cid: cqs[cid] for cid in cq_ids if cid in cqs
        }
        if not cqs_to_evaluate:
            return {
                "agent_response": (
                    "None of the provided CQ IDs found in approved CQs.\n"
                    f"Available CQ IDs: {', '.join(sorted(cqs.keys()))}"
                ),
                "status": {"error": "cqs_not_found"},
            }
        is_single = False
    else:
        cqs_to_evaluate = cqs
        is_single = False

    # Connect to Neo4j
    try:
        driver = get_neo4j_driver()
    except Exception as exc:
        return {
            "agent_response": (
                f"Failed to connect to Neo4j: {exc}\n\n"
                "Please check Neo4j credentials and connectivity."
            ),
            "status": {"success": False, "error": "neo4j_connection_failed"},
        }

    try:
        # Classify all CQs in one Claude call before the evaluation loop
        classifications = _classify_cqs_batch(cqs_to_evaluate, state)

        results = []
        answerable_count = 0
        partial_count = 0
        not_answerable_count = 0

        for cq_id_iter, cq_data in cqs_to_evaluate.items():
            question = cq_data["question"]
            category = cq_data.get("category", "unknown")
            priority = cq_data.get("priority", "medium")

            cq_strategy = classifications.get(
                cq_id_iter, {"strategy": "cross_layer", "cypher_query": None}
            )
            eval_result = _evaluate_single_cq(
                driver, question, state, strategy_result=cq_strategy
            )

            evidence_count = eval_result["evidence_count"]
            has_bridge = eval_result["has_cross_layer_bridge"]
            strategy_used = eval_result.get("strategy_used", "")

            # Classify answerability
            if strategy_used == "cypher" and evidence_count > 0:
                # Cypher directly answers structural/aggregation questions
                status = "answerable"
                answerable_count += 1
            elif evidence_count > 2 and has_bridge:
                # Semantic evidence with domain entity linkage
                status = "answerable"
                answerable_count += 1
            elif evidence_count > 0:
                status = "partial"
                partial_count += 1
            else:
                status = "not_answerable"
                not_answerable_count += 1

            results.append({
                "cq_id": cq_id_iter,
                "question": question,
                "category": category,
                "priority": priority,
                "status": status,
                "evidence_count": evidence_count,
                "has_cross_layer_bridge": has_bridge,
                "strategies_tried": eval_result["strategies_tried"],
                "strategy_used": strategy_used,
            })

        # Sort by priority (high > medium > low), then CQ ID
        results.sort(
            key=lambda r: (
                _PRIORITY_ORDER.get(r["priority"], 99),
                r["cq_id"],
            )
        )

        total = len(results)
        coverage_score = (
            (answerable_count + 0.5 * partial_count) / total
            if total > 0 else 0.0
        )

        # Store results in state
        state["cq_evaluation_results"] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total": total,
            "answerable": answerable_count,
            "partial": partial_count,
            "not_answerable": not_answerable_count,
            "coverage_score": round(coverage_score, 3),
            "per_cq_results": results,
        }
        _save_state(state)

        if is_single:
            r = results[0]
            note = {
                "answerable": "Evidence found with cross-layer bridge",
                "partial": "Some evidence found but incomplete coverage",
                "not_answerable": "No evidence found in the graph",
            }[r["status"]]

            return {
                "agent_response": (
                    f"CQ Assessment: {r['cq_id']}\n\n"
                    f"Question: {r['question']}\n"
                    f"Category: {r['category']}\n"
                    f"Priority: {r['priority']}\n"
                    f"Status: {r['status'].upper()}\n"
                    f"Evidence: {r['evidence_count']} items\n"
                    f"Cross-layer bridge: "
                    f"{'Yes' if r['has_cross_layer_bridge'] else 'No'}\n"
                    f"Strategies tried: {', '.join(r['strategies_tried']) or 'none'}\n"
                    f"Note: {note}"
                ),
                "status": {
                    "success": True,
                    "cq_id": r["cq_id"],
                    "question": r["question"],
                    "category": r["category"],
                    "priority": r["priority"],
                    "evidence_found": r["evidence_count"] > 0,
                    "strategies_tried": r["strategies_tried"],
                    "evidence_count": r["evidence_count"],
                    "has_cross_layer_bridge": r["has_cross_layer_bridge"],
                    "assessment": {
                        "status": r["status"],
                        "note": note,
                    },
                },
            }
        else:
            lines = [
                f"Competency Question Evaluation: {total} questions\n",
                f"Answerable: {answerable_count}",
                f"Partial: {partial_count}",
                f"Not Answerable: {not_answerable_count}",
                f"Coverage Score: {coverage_score:.1%}\n",
                "Per-CQ Results:",
            ]
            for r in results:
                icon = {
                    "answerable": "[OK]",
                    "partial": "[PARTIAL]",
                    "not_answerable": "[FAIL]",
                }[r["status"]]
                q_display = r["question"]
                if len(q_display) > 60:
                    q_display = q_display[:60] + "..."
                lines.append(
                    f"  {icon} {r['cq_id']}: {q_display} "
                    f"({r['evidence_count']} evidence)"
                )

            return {
                "agent_response": "\n".join(lines),
                "status": {
                    "success": True,
                    "total": total,
                    "answerable": answerable_count,
                    "partial": partial_count,
                    "not_answerable": not_answerable_count,
                    "coverage_score": round(coverage_score, 3),
                },
                "results": results,
            }

    except Exception as exc:
        return {
            "agent_response": (
                f"CQ evaluation failed: {exc}\n\n"
                "This may be due to:\n"
                "- Neo4j connection issues\n"
                "- Missing OPENAI_API_KEY for vector-based strategies\n"
                "- Missing indexes (build the text graph first)"
            ),
            "status": {"success": False, "error": str(exc)},
        }

    finally:
        try:
            close_driver(driver)
        except Exception:
            pass


@mcp.tool
@mcp_traceable(name="mcp.kg_evaluate_cqs")
@_async_capable("kg_evaluate_cqs")
def kg_evaluate_cqs(cq_id: str = "", cq_ids: list[str] = None) -> dict:
    """Evaluate approved competency questions against the knowledge graph.

    Tests whether approved CQs are answerable by gathering evidence from
    the graph using vector, hybrid, and cross-layer strategies. Returns
    assessment metrics (not answers).

    Works with approved CQs only. For ad-hoc questions, use kg_query.

    Args:
        cq_id: Single approved CQ ID to evaluate (e.g., "CQ3").
        cq_ids: List of approved CQ IDs to evaluate (e.g., ["CQ1", "CQ3"]).
                If neither provided: evaluates ALL approved CQs.

    Returns:
        Single CQ: Individual assessment with evidence details.
        Multiple CQs: Coverage scorecard with per-CQ results.
    """
    return _run_cq_evaluation(cq_id, cq_ids)


def _run_kg_diagram(scope: str = "auto") -> dict:
    """Core implementation of Mermaid diagram generation (testable without MCP).

    Args:
        scope: What to diagram.
            "schema" - from approved state artifacts (no Neo4j needed)
            "live" - from actual Neo4j graph (requires connection)
            "auto" - try live first, fall back to schema

    Returns:
        Dict with agent_response, status, and mermaid keys.
    """
    guard = _check_project_active()
    if guard:
        return guard
    from utils.mermaid import generate_schema_diagram, generate_live_diagram

    valid_scopes = ("schema", "live", "auto")
    if scope not in valid_scopes:
        return {
            "agent_response": (
                f"Invalid scope: '{scope}'.\n\n"
                f"Valid scopes: {', '.join(valid_scopes)}\n"
                "- schema: from approved state artifacts (no Neo4j needed)\n"
                "- live: from actual Neo4j graph (requires connection)\n"
                "- auto: try live first, fall back to schema"
            ),
            "status": {"success": False, "error": "invalid_scope"},
        }

    state = _load_clean_state()
    mermaid_markup = ""
    used_scope = scope

    if scope == "schema":
        mermaid_markup = generate_schema_diagram(state)

    elif scope == "live":
        try:
            driver = get_neo4j_driver()
            try:
                mermaid_markup = generate_live_diagram(driver, state)
            finally:
                close_driver(driver)
        except Exception as exc:
            return {
                "agent_response": (
                    f"Failed to generate live diagram: {exc}\n\n"
                    "Check Neo4j connection or use scope='schema' instead."
                ),
                "status": {"success": False, "error": str(exc)},
            }

    elif scope == "auto":
        # Try live first, fall back to schema
        try:
            driver = get_neo4j_driver()
            try:
                mermaid_markup = generate_live_diagram(driver, state)
                if mermaid_markup:
                    used_scope = "live"
            finally:
                close_driver(driver)
        except Exception:
            pass

        if not mermaid_markup:
            mermaid_markup = generate_schema_diagram(state)
            if mermaid_markup:
                used_scope = "schema"

    if not mermaid_markup:
        return {
            "agent_response": (
                "No diagram data available.\n\n"
                "To generate a schema diagram, approve artifacts first:\n"
                "- Use kg_schema_proposal for structured schema\n"
                "- Use kg_ner_extraction / kg_fact_extraction for text layer\n\n"
                "To generate a live diagram, build the graph first:\n"
                "- Use kg_build_graph to populate Neo4j"
            ),
            "status": {"success": False, "error": "no_data"},
        }

    # Write diagram.mmd to state directory
    state_dir = os.path.dirname(_get_state_file())
    os.makedirs(state_dir, exist_ok=True)
    diagram_path = os.path.join(state_dir, "diagram.mmd")
    with open(diagram_path, "w", encoding="utf-8") as f:
        f.write(mermaid_markup + "\n")

    return {
        "agent_response": (
            f"Diagram saved to {diagram_path}\n\n"
            f"```mermaid\n{mermaid_markup}\n```"
        ),
        "status": {"success": True, "scope": used_scope, "file": diagram_path},
        "mermaid": mermaid_markup,
    }


@mcp.tool
@mcp_traceable(name="mcp.kg_diagram")
@_async_capable("kg_diagram")
def kg_diagram(scope: str = "auto") -> dict:
    """Generate a Mermaid diagram of the knowledge graph schema.

    Creates a visual schema diagram showing node types (with counts for
    live graphs) and relationship types. Saves to state/diagram.mmd for
    viewing with a Mermaid viewer.

    Args:
        scope: What to diagram.
            "schema" - from approved state artifacts (no Neo4j needed)
            "live" - from actual Neo4j graph (requires connection)
            "auto" (default) - try live first, fall back to schema

    Returns:
        Dict with Mermaid markup, file path, and status metadata.
    """
    return _run_kg_diagram(scope)


@mcp.tool
@mcp_traceable(name="mcp.kg_reset_state")
def kg_reset_state() -> dict:
    """Reset the KG-Factory state to start fresh.

    Clears all proposed/approved artifacts.
    Use this to start over from the beginning.

    Returns:
        Confirmation message.
    """
    save_state({}, _get_state_file())
    return {"message": "State reset. Ready to start fresh."}


if __name__ == "__main__":
    mcp.run()
