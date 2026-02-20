# US015: Standalone Query Agent & Platform Integration

## User Story

**As a** KG-Factory User
**I want** a standalone conversational agent that can chat with my knowledge graph, handle follow-up questions, combine evidence from multiple retrievers, and synthesize natural language answers
**So that** I can ship the agent alongside my built knowledge graph to Claude Cowork and/or OpenClaw, giving my personal assistant deep access to domain-specific knowledge

## Story Points: 13

## Status: Not Started

## Acceptance Criteria

### Query Agent (`agents/query_agent.py`)

- [ ] `QueryAgent` class following the established agent pattern (system prompt + tools + handlers)
- [ ] Uses `run_agent_sync()` from `core/agent.py` (same pattern as all other agents)
- [ ] System prompt teaches Claude about 5 retriever tools with intent-based descriptions
- [ ] Returns `(response, state, conversation)` tuple (standard agent contract)
- [ ] Decorated with `@traceable(name="query_agent.run")`
- [ ] Multi-turn conversation: Claude resolves follow-up references from conversation context
- [ ] No separate `_select_retrieval_strategy()` call — Claude IS the strategist via tool calling
- [ ] Synthesizes natural language answers from evidence (not raw evidence dumps)

### Agent Tools (`tools/query_agent_tools.py`)

Five tools with intent-based names wrapping existing `_execute_*` functions:

- [ ] `discover_graph` — wraps `_execute_schema_query()` + live Neo4j label discovery
  - Caches discovered labels in `state["_discovered_labels"]` (ephemeral, `_` prefix)
  - Returns formatted schema summary with both layers
- [ ] `search_text(query, top_k)` — wraps `_execute_vector_search()`
  - Best for: broad content questions, thematic exploration
  - Default `top_k=5`
- [ ] `search_keywords(query, top_k)` — wraps `_execute_hybrid_search()`
  - Best for: specific terms + semantic meaning
  - Default `top_k=5`
- [ ] `search_entities(query, top_k)` — wraps `_execute_cross_layer_traversal()`
  - Best for: linking text content to domain entities
  - Uses `state["_discovered_labels"]` when state file is absent, falls back to `_get_domain_labels(state)`
  - Default `top_k=5`
- [ ] `run_cypher(query)` — wraps `_execute_cypher()`
  - Best for: precise structural queries, counting, aggregation
  - Read-only validation via `_validate_read_only_cypher()`

All tool handlers:
- [ ] Take `state` as first parameter (standard handler pattern)
- [ ] Return dict with `status` and `message` keys
- [ ] Include retriever results in return for Claude to synthesize
- [ ] Use `state["_driver"]` for Neo4j driver (injected by MCP server)

### Runtime Graph Discovery

- [ ] `discover_graph` queries Neo4j directly for labels, relationships, counts
- [ ] Discovered labels cached in `state["_discovered_labels"]` (ephemeral key)
- [ ] `search_entities` handler checks `state["_discovered_labels"]` first, then `_get_domain_labels(state)`
- [ ] Agent works in two modes:
  - **With state file**: rich context from construction plan (entity descriptions, etc.)
  - **Without state file**: discovers structure from Neo4j directly
- [ ] The graph is the source of truth, not the JSON file

### Multi-Strategy Retrieval (Sequential, Claude-Driven)

- [ ] Claude can call multiple tools in sequence within a single turn
- [ ] Claude evaluates results after each tool call — decides if evidence is sufficient
- [ ] Claude can reformulate queries based on intermediate results
- [ ] No automatic RRF merge — Claude synthesizes intelligently from all evidence seen
- [ ] Example flow: `search_text` returns partial results → Claude calls `search_entities` for more → synthesizes from both

### Query MCP Server (`mcp_server/query_server.py`)

Separate, lightweight MCP server exposing only query capabilities:

- [ ] `kg_chat(message: str, session_id: str = "default")` — conversational query tool
  - Wraps `QueryAgent.run()` with per-session conversation management
  - Returns: `{answer: str, sources: list, confidence: float, strategies_used: list}`
  - Session management via rolling-window conversation persistence (reuses `_serialize_conversation` / `_trim_conversation` pattern)
  - 20-message rolling window per session (configurable)
- [ ] `kg_graph_info()` — lightweight schema check
  - Returns labels, relationship types, node counts, index status
  - No conversation state required
  - For OpenClaw to decide if KG has relevant data before starting a session
- [ ] Decorated with `@mcp.tool` and `@mcp_traceable(name="mcp.kg_chat")` / `@mcp_traceable(name="mcp.kg_graph_info")`
- [ ] Driver lifecycle: one driver created at startup, shared across calls (read-only server)
- [ ] State loading: tries state file, falls back to empty state (graph discovery handles the rest)
- [ ] LangSmith subprocess deadlock prevention (same pre-cache pattern as `server.py`)
- [ ] Does NOT import construction agents (minimal dependencies)
- [ ] Does NOT expose `kg_reset_state`, `kg_build_graph`, or any mutation tools

### Shared Skill (`skills/knowledge-graph/SKILL.md`)

- [ ] Skill frontmatter with `name`, `description`, `metadata` (emoji, required env vars)
- [ ] `description` drives selective injection on both platforms (only injected when user message matches)
- [ ] Documents when to use `kg_chat` vs `kg_graph_info`
- [ ] Includes usage tips (same session_id for follow-ups, start with kg_graph_info, etc.)
- [ ] Lists required environment variables: `NEO4J_URI`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
- [ ] Works in both Cowork (progressive disclosure) and OpenClaw (selective injection)

### Claude Cowork Plugin (`plugins/cowork/`)

- [ ] Plugin manifest at `.claude-plugin/plugin.json` with name, version, description, author
- [ ] `claude_plugin_version: "1"` in manifest
- [ ] `.mcp.json` at plugin root with `domain-kg` server configuration
- [ ] `.mcp.json` uses absolute path to Python venv executable (not just `"python"`)
- [ ] `.mcp.json` includes `PYTHONPATH` pointing to KG-Factory project root
- [ ] Symlink or copy of `skills/knowledge-graph/SKILL.md` into plugin `skills/` directory
- [ ] Plugin loads correctly when placed in `~/.claude/plugins/` or loaded via Agent SDK
- [ ] Cowork discovers `kg_chat` and `kg_graph_info` tools after plugin install
- [ ] No stdout pollution from query_server.py (FastMCP handles this correctly)

### LangSmith Observability

Follows the established US011 pattern. All new components are traced:

- [ ] `QueryAgent.run()` decorated with `@traceable(name="query_agent.run")`
- [ ] All 5 tool handlers decorated with `@traceable(name="query_agent.tool.<name>")`
- [ ] `kg_chat` MCP tool decorated with `@mcp_traceable(name="mcp.kg_chat")`
- [ ] `kg_graph_info` MCP tool decorated with `@mcp_traceable(name="mcp.kg_graph_info")`
- [ ] Session management helpers NOT traced (operational, not analytical)
- [ ] Trace hierarchy:

```
mcp.kg_chat                              # @mcp_traceable on MCP function
  -> query_agent.run                     # @traceable on QueryAgent.run()
    -> Claude API call                   # wrap_anthropic() auto-capture
    -> query_agent.tool.search_entities  # @traceable on tool handler
      -> query.execute_cross_layer       # existing @traceable from US013
    -> Claude API call                   # wrap_anthropic() (synthesis turn)
```

- [ ] Opt-in: only active when `LANGSMITH_TRACING=true`
- [ ] Zero impact when disabled (no-op decorators via `core/tracing.py`)
- [ ] No changes to existing tracing on `_execute_*` functions (they keep their own `@traceable` decorators from US013)
- [ ] Pre-cache `get_runtime_environment()` and `get_langchain_env_var_metadata()` in `query_server.py` before `FastMCP` init (Windows deadlock prevention, same as `server.py`)

### Error Handling

- [ ] Neo4j connection failure at startup: clear error with connection details
- [ ] Missing `OPENAI_API_KEY`: clear error when vector-based tools are called (not at startup)
- [ ] Missing `ANTHROPIC_API_KEY`: clear error at agent initialization
- [ ] Session not found: creates new session transparently
- [ ] Empty graph: `discover_graph` returns helpful message, agent explains no data available
- [ ] Index not found: tool handler returns error, agent suggests building text graph first
- [ ] Driver connection lost mid-session: attempt reconnect, clear error if fails

## Definition of Done

- [ ] Code implemented and working
- [ ] Unit tests for all 5 tool handlers (mock Neo4j driver, mock `_execute_*` functions)
- [ ] Unit tests for session management (create, retrieve, trim, independent sessions)
- [ ] Unit tests for graph discovery and label caching
- [ ] Unit tests for `kg_chat` and `kg_graph_info` MCP tools (extract impl functions, test directly)
- [ ] Interactive test: `tests/test_10_query_agent.py` — multi-turn conversation demonstrating:
  - Graph structure discovery
  - Domain question with synthesized answer
  - Follow-up question (reference resolution from context)
  - Cross-layer question
  - Cypher question
- [ ] All existing tests still pass (305+ unit tests)
- [ ] LangSmith traces verified (trace hierarchy visible in dashboard when enabled)
- [ ] Query server starts and responds to MCP calls
- [ ] Shared SKILL.md created and validated (correct frontmatter format for both platforms)
- [ ] Cowork plugin created (`plugins/cowork/`) with valid manifest and `.mcp.json`
- [ ] Cowork plugin loads in Claude Desktop (tools discovered, skill activates)
- [ ] Code reviewed
- [ ] Documentation in code (docstrings for all public functions)

## Technical Notes

### Architecture

```
kg_chat(message, session_id)
  |
  +-> Load/create session conversation
  +-> QueryAgent.run(message, state, conversation)
  |     |
  |     +-> run_agent_sync()                    # From core/agent.py
  |           |
  |           +-> Claude API call               # Wrapped with wrap_anthropic()
  |           +-> Tool call: discover_graph
  |           |     +-> _execute_schema_query()  # From US013
  |           |     +-> Live Neo4j label query
  |           |     +-> Cache labels in state
  |           +-> Claude API call               # Claude decides next tool
  |           +-> Tool call: search_entities
  |           |     +-> _execute_cross_layer_traversal()  # From US013
  |           +-> Claude API call               # Claude synthesizes answer
  |           +-> Return: (response, state, conversation)
  |
  +-> Store updated conversation for session
  +-> Extract metadata (sources, confidence, strategies_used)
  +-> Return: {answer, sources, confidence, strategies_used}
```

### Retriever Sharing Model

```
pipelines/query_builder.py
├── _execute_schema_query()
├── _execute_cypher()
├── _execute_vector_search()
├── _execute_hybrid_search()
└── _execute_cross_layer_traversal()
         |
         +-- used by: kg_query         (MCP tool, one-shot, Claude Code)
         +-- used by: kg_evaluate_cqs  (MCP tool, batch, Claude Code)
         +-- used by: QueryAgent       (conversational, OpenClaw)    <-- NEW
```

Improvements to `_execute_*` functions flow to all three consumers automatically.

### Files to Create

```
agents/
  query_agent.py                  # NEW: QueryAgent class

tools/
  query_agent_tools.py            # NEW: 5 tool schemas + handlers

mcp_server/
  query_server.py                 # NEW: Query-only MCP server (2 tools)

skills/
  knowledge-graph/
    SKILL.md                      # NEW: Shared skill (Cowork + OpenClaw)

plugins/
  cowork/
    .claude-plugin/
      plugin.json                 # NEW: Cowork plugin manifest
    .mcp.json                     # NEW: MCP server config for Cowork
    skills/
      knowledge-graph/
        SKILL.md                  # SYMLINK or COPY from skills/

tests/
  test_10_query_agent.py          # NEW: Interactive multi-turn test
  unit/
    test_query_agent.py           # NEW: Unit tests for agent + tools
    test_query_server.py          # NEW: Unit tests for MCP server
```

### Files NOT Modified

```
mcp_server/server.py              # UNCHANGED: construction server stays as-is
pipelines/query_builder.py        # UNCHANGED: shared retrievers
tools/query_tools.py              # UNCHANGED: shared helpers
core/agent.py                     # UNCHANGED: run_agent_sync
core/state.py                     # UNCHANGED: state utilities
core/tracing.py                   # UNCHANGED: @traceable, @mcp_traceable
utils/neo4j_utils.py              # UNCHANGED: driver utilities
```

### Component Specifications

#### 1. QueryAgent (`agents/query_agent.py`)

```python
from core import run_agent_sync
from core.tracing import traceable
from tools.query_agent_tools import (
    TOOL_DISCOVER_GRAPH, TOOL_SEARCH_TEXT, TOOL_SEARCH_KEYWORDS,
    TOOL_SEARCH_ENTITIES, TOOL_RUN_CYPHER,
    handle_discover_graph, handle_search_text, handle_search_keywords,
    handle_search_entities, handle_run_cypher,
)


SYSTEM_PROMPT = """You are a Knowledge Graph Query Agent. You answer questions
by querying a knowledge graph that has two layers:

DOMAIN LAYER (structured data):
  Built from CSV files. Contains business entities and relationships.

TEXT LAYER (unstructured data):
  Built from markdown documents. Contains chunks, extracted entities,
  and embeddings. Entities are linked to domain nodes via CORRESPONDS_TO.

YOUR TOOLS:

discover_graph -- Call first if you don't know the graph structure.
  Returns labels, relationships, node counts for both layers.

search_text(query) -- Semantic search on text chunks.
  Best for: broad content questions, thematic exploration.

search_keywords(query) -- Semantic + keyword search on text chunks.
  Best for: questions with specific terms plus meaning.

search_entities(query) -- Semantic + keyword + entity traversal.
  Best for: questions linking text to domain entities.
  Traverses FROM_CHUNK and CORRESPONDS_TO relationships.

run_cypher(query) -- Execute a read-only Cypher query.
  Best for: precise structural questions, counting, aggregation.
  ONLY read-only: no CREATE, DELETE, SET, REMOVE, MERGE.

HOW TO WORK:
1. If you don't know the graph yet, call discover_graph first.
2. Choose the tool that fits the question. Call multiple if needed.
3. ALWAYS synthesize results into a clear, conversational answer.
4. If results are insufficient, try a different tool or reformulate.
5. Offer follow-up suggestions when relevant.
"""


TOOLS = [
    TOOL_DISCOVER_GRAPH,
    TOOL_SEARCH_TEXT,
    TOOL_SEARCH_KEYWORDS,
    TOOL_SEARCH_ENTITIES,
    TOOL_RUN_CYPHER,
]


TOOL_HANDLERS = {
    "discover_graph": handle_discover_graph,
    "search_text": handle_search_text,
    "search_keywords": handle_search_keywords,
    "search_entities": handle_search_entities,
    "run_cypher": handle_run_cypher,
}


class QueryAgent:
    """Conversational agent for querying the knowledge graph."""

    @traceable(name="query_agent.run")
    def run(self, message: str, state: dict,
            conversation: list | None = None) -> tuple[str, dict, list]:
        return run_agent_sync(
            message=message,
            state=state,
            system_prompt=SYSTEM_PROMPT,
            tools=TOOLS,
            tool_handlers=TOOL_HANDLERS,
            conversation=conversation,
        )
```

#### 2. Tool Handlers (`tools/query_agent_tools.py`)

```python
from core.tracing import traceable


# --- Tool Schemas ---

TOOL_DISCOVER_GRAPH = {
    "name": "discover_graph",
    "description": "Get knowledge graph structure: labels, relationships, "
                   "node counts, layer classification. Call this first.",
    "input_schema": {
        "type": "object",
        "properties": {},
    }
}

TOOL_SEARCH_TEXT = {
    "name": "search_text",
    "description": "Semantic search on text chunks. Best for broad content "
                   "questions and thematic exploration.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language search query"
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results (default 5)",
                "default": 5
            },
        },
        "required": ["query"]
    }
}

TOOL_SEARCH_KEYWORDS = {
    "name": "search_keywords",
    "description": "Semantic + keyword search on text chunks. Best for "
                   "questions with specific terms plus meaning.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language search query with keywords"
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results (default 5)",
                "default": 5
            },
        },
        "required": ["query"]
    }
}

TOOL_SEARCH_ENTITIES = {
    "name": "search_entities",
    "description": "Semantic + keyword search + entity traversal across "
                   "text and domain layers. Best for questions linking text "
                   "to domain entities. Traverses FROM_CHUNK and "
                   "CORRESPONDS_TO relationships.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language query about entities"
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results (default 5)",
                "default": 5
            },
        },
        "required": ["query"]
    }
}

TOOL_RUN_CYPHER = {
    "name": "run_cypher",
    "description": "Execute a read-only Cypher query. Best for precise "
                   "structural questions, counting, aggregation. "
                   "No mutations allowed (CREATE, DELETE, SET, REMOVE, MERGE "
                   "are blocked).",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Read-only Cypher query"
            },
        },
        "required": ["query"]
    }
}


# --- Tool Handlers ---

@traceable(name="query_agent.tool.discover_graph")
def handle_discover_graph(state: dict) -> dict:
    """Query Neo4j for graph schema and cache discovered labels."""
    from pipelines.query_builder import _execute_schema_query

    driver = state["_driver"]
    schema_result = _execute_schema_query(driver, state)

    # Live label discovery from Neo4j (not from state file)
    with driver.session() as session:
        result = session.run("""
            MATCH (n)
            WHERE NOT any(l IN labels(n) WHERE l STARTS WITH '__')
              AND NOT any(l IN labels(n) WHERE l IN ['Chunk', 'Document'])
            RETURN DISTINCT
              [l IN labels(n) WHERE NOT l STARTS WITH '__'][0] AS label,
              count(n) AS count
        """)
        discovered = [dict(r) for r in result]

    # Cache for search_entities to use
    state["_discovered_labels"] = [
        row["label"] for row in discovered if row["label"]
    ]

    return {
        "status": "success",
        "message": schema_result["answer"],
        "discovered_labels": state["_discovered_labels"],
    }


@traceable(name="query_agent.tool.search_text")
def handle_search_text(state: dict, query: str, top_k: int = 5) -> dict:
    """Semantic vector search on text chunks."""
    from pipelines.query_builder import _execute_vector_search

    driver = state["_driver"]
    result = _execute_vector_search(driver, query, top_k)
    return {
        "status": "success",
        "message": result["answer"],
        "evidence": result["evidence"],
        "confidence": result["confidence"],
    }


@traceable(name="query_agent.tool.search_keywords")
def handle_search_keywords(state: dict, query: str, top_k: int = 5) -> dict:
    """Semantic + keyword search on text chunks."""
    from pipelines.query_builder import _execute_hybrid_search

    driver = state["_driver"]
    result = _execute_hybrid_search(driver, query, top_k)
    return {
        "status": "success",
        "message": result["answer"],
        "evidence": result["evidence"],
        "confidence": result["confidence"],
    }


@traceable(name="query_agent.tool.search_entities")
def handle_search_entities(state: dict, query: str, top_k: int = 5) -> dict:
    """Semantic + keyword search + cross-layer entity traversal."""
    from pipelines.query_builder import _execute_cross_layer_traversal
    from tools.query_tools import _get_domain_labels, _get_text_entities

    driver = state["_driver"]

    # Use discovered labels if state file is absent
    if not _get_domain_labels(state) and "_discovered_labels" in state:
        # Inject discovered labels into state for cross-layer
        # so _execute_cross_layer_traversal can use them
        state.setdefault("approved_construction_plan", {})
        for label in state["_discovered_labels"]:
            state["approved_construction_plan"][label] = {
                "construction_type": "node",
                "label": label,
            }

    result = _execute_cross_layer_traversal(driver, query, top_k, state)
    return {
        "status": "success",
        "message": result["answer"],
        "evidence": result["evidence"],
        "confidence": result["confidence"],
    }


@traceable(name="query_agent.tool.run_cypher")
def handle_run_cypher(state: dict, query: str) -> dict:
    """Execute read-only Cypher query."""
    from pipelines.query_builder import _execute_cypher

    driver = state["_driver"]
    result = _execute_cypher(driver, query)
    return {
        "status": "success",
        "message": result["answer"],
        "evidence": result["evidence"],
        "confidence": result["confidence"],
    }
```

#### 3. Query MCP Server (`mcp_server/query_server.py`)

```python
"""Query-only MCP server for OpenClaw integration.

Exposes the Query Agent as MCP tools for conversational knowledge graph
access. Separate from the construction server (server.py) for security
and deployment isolation.
"""

import os
import sys
import json

_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(_root_dir, ".env"))

# Pre-cache langsmith runtime env (Windows deadlock prevention)
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
from agents.query_agent import QueryAgent
from core import load_state
from core.tracing import mcp_traceable
from utils import get_neo4j_driver, close_driver

mcp = FastMCP(
    "KG-Query",
    instructions="""\
Knowledge Graph Query Agent. Ask questions about the domain knowledge graph.

Tools:
- kg_chat: Conversational query with follow-up support
- kg_graph_info: Quick schema check
""",
)

# Shared state
_sessions: dict[str, list] = {}    # session_id -> conversation
_driver = None
_agent = QueryAgent()
_state = {}

MAX_CONVERSATION_MESSAGES = 20


def _get_driver():
    global _driver
    if _driver is None:
        _driver = get_neo4j_driver()
    return _driver


def _load_state_once():
    global _state
    if not _state:
        try:
            _state = load_state(
                os.path.join(_root_dir, "state", "current_state.json")
            )
        except FileNotFoundError:
            _state = {}
    return _state


def _trim_conversation(conversation: list, max_messages: int) -> list:
    if len(conversation) <= max_messages:
        return conversation
    return conversation[-max_messages:]


@mcp.tool
@mcp_traceable(name="mcp.kg_chat")
def kg_chat(message: str, session_id: str = "default") -> dict:
    """Chat with the knowledge graph using natural language.

    Maintains conversation per session for follow-up questions.

    Args:
        message: Natural language question or follow-up
        session_id: Session ID for conversation continuity (default: "default")

    Returns:
        Synthesized answer with sources and confidence.
    """
    driver = _get_driver()
    state = _load_state_once()

    # Inject driver for tool handlers
    state["_driver"] = driver

    # Get or create session conversation
    conversation = _sessions.get(session_id, [])

    # Run agent
    response, state, conversation = _agent.run(
        message=message,
        state=state,
        conversation=conversation,
    )

    # Trim and store conversation
    conversation = _trim_conversation(conversation, MAX_CONVERSATION_MESSAGES)
    _sessions[session_id] = conversation

    # Extract metadata from state (tools may have set these)
    return {
        "answer": response,
        "sources": [],          # TODO: extract from evidence
        "confidence": 0.0,      # TODO: aggregate from tool results
        "strategies_used": [],  # TODO: track which tools were called
    }


@mcp.tool
@mcp_traceable(name="mcp.kg_graph_info")
def kg_graph_info() -> dict:
    """Get knowledge graph schema: labels, relationships, counts.

    Quick check of what data is available. No conversation state needed.
    Call this before starting a kg_chat session to understand the graph.
    """
    from pipelines.query_builder import _execute_schema_query

    driver = _get_driver()
    state = _load_state_once()

    result = _execute_schema_query(driver, state)
    return {
        "schema": result["answer"],
        "evidence": result["evidence"],
    }


if __name__ == "__main__":
    mcp.run()
```

#### 4. OpenClaw Skill (`skills/knowledge-graph/SKILL.md`)

```markdown
---
name: knowledge-graph
description: >
  Query a domain knowledge graph built with KG-Factory. Use when the user
  asks about domain-specific data, business entities, relationships between
  entities, or content from documents that have been indexed. Do NOT use
  for general knowledge questions -- only for data in the user's graph.
metadata: {"openclaw":{"emoji":"graph","requires":{"env":["NEO4J_URI","ANTHROPIC_API_KEY","OPENAI_API_KEY"]}}}
---

# Knowledge Graph Query

Chat with your domain knowledge graph using natural language.

## When to use this skill

Use `kg_chat` when the user asks about:
- Business entities (suppliers, products, customers, etc.)
- Relationships between entities ("which suppliers provide X?")
- Content from indexed documents (reviews, reports, specs)
- Cross-referencing structured data with document content
- Aggregations or counts over domain data

Do NOT use for:
- General knowledge ("what is Neo4j?")
- Questions about files on disk (use filesystem tools)
- Web searches (use web_search)

## Tools

### kg_chat(message, session_id)
Conversational query with follow-up support. Maintains context per session.

- Use the SAME session_id for related questions in one conversation
- The agent handles strategy selection internally
- Returns synthesized answers, not raw data

### kg_graph_info()
Quick check of what's in the graph. Call this first if unsure whether
the graph has relevant data.

## Tips
- Start with kg_graph_info() to understand available data
- Use specific entity names when you know them
- Follow up with "tell me more about X" for deeper exploration
```

#### 5. Cowork Plugin Manifest (`plugins/cowork/.claude-plugin/plugin.json`)

```json
{
  "name": "kg-query",
  "version": "0.1.0",
  "description": "Query a domain knowledge graph built with KG-Factory. Provides conversational access to structured and unstructured data through semantic search, keyword matching, entity traversal, and Cypher queries.",
  "author": "KG-Factory",
  "claude_plugin_version": "1"
}
```

#### 6. Cowork MCP Config (`plugins/cowork/.mcp.json`)

```json
{
  "mcpServers": {
    "domain-kg": {
      "command": "/absolute/path/to/.venv/Scripts/python.exe",
      "args": ["-m", "mcp_server.query_server"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/KnowledgeGraphFactory",
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "password",
        "OPENAI_API_KEY": "sk-...",
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

**Note**: The `.mcp.json` requires user customization (absolute paths, credentials) after cloning the plugin. This is documented in the SKILL.md setup instructions.

### OpenClaw Configuration Examples

**Option A: mcp-adapter plugin** (recommended):

```jsonc
{
  "plugins": {
    "entries": {
      "mcp-adapter": {
        "enabled": true,
        "config": {
          "toolPrefix": true,
          "servers": [
            {
              "name": "domain-kg",
              "transport": "stdio",
              "command": "python",
              "args": ["-m", "mcp_server.query_server"],
              "env": {
                "NEO4J_URI": "${NEO4J_URI}",
                "NEO4J_USER": "${NEO4J_USER}",
                "NEO4J_PASSWORD": "${NEO4J_PASSWORD}",
                "OPENAI_API_KEY": "${OPENAI_API_KEY}",
                "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}"
              }
            }
          ]
        }
      }
    }
  }
}
```

**Option B: Native mcp.servers** (per-agent):

```jsonc
{
  "agents": {
    "list": [
      {
        "id": "main",
        "default": true,
        "mcp": {
          "servers": [
            {
              "name": "domain-kg",
              "command": "python",
              "args": ["-m", "mcp_server.query_server"],
              "env": {
                "NEO4J_URI": "bolt://localhost:7687",
                "NEO4J_USER": "neo4j",
                "NEO4J_PASSWORD": "password",
                "OPENAI_API_KEY": "sk-...",
                "ANTHROPIC_API_KEY": "sk-ant-..."
              }
            }
          ]
        }
      }
    ]
  }
}
```

**Sub-agent tool restrictions** (for deep research sessions):

```jsonc
{
  "tools": {
    "subagents": {
      "tools": {
        "allow": ["domain-kg_kg_chat", "domain-kg_kg_graph_info"],
        "deny": ["group:fs", "group:sessions", "exec"]
      }
    }
  }
}
```

### Testing MCP Tools (Pattern)

Following the US014 pattern: extract implementation into callable functions, MCP tool delegates to them. Tests import and call the impl function directly.

```python
# In query_server.py
def _run_kg_chat(message: str, session_id: str) -> dict:
    """Implementation extracted for testability."""
    # ... actual logic ...

@mcp.tool
@mcp_traceable(name="mcp.kg_chat")
def kg_chat(message: str, session_id: str = "default") -> dict:
    return _run_kg_chat(message, session_id)

# In tests
from mcp_server.query_server import _run_kg_chat
```

## Dependencies

### Internal

- **US013**: Query Infrastructure (provides `_execute_*` strategy functions in `query_builder.py`)
- **US011**: LangSmith Observability (provides `@traceable`, `@mcp_traceable`, `wrap_anthropic`)
- Existing `core/agent.py` (`run_agent_sync`)
- Existing `core/state.py` (state management)
- Existing `core/tracing.py` (tracing utilities)
- Existing `utils/neo4j_utils.py` (driver management)

### Python Packages

- `fastmcp<3` (MCP server, already in requirements)
- `anthropic>=0.40.0` (Claude API, already in requirements)
- `neo4j-graphrag>=1.0.0` (retrievers, already in requirements)
- `openai>=1.0.0` (embeddings, already in requirements)

### External (Platform-Specific)

- **Claude Cowork**: Claude Desktop with paid subscription (Pro $20/mo+). Cowork tab available since Jan 2026.
- **OpenClaw**: Node.js 22+, `openclaw` CLI, `mcp-adapter` plugin. Free (self-hosted).

## Claude Cowork Installation & Integration Guide

### Prerequisites

- **Claude Desktop** installed (macOS or Windows)
- **Claude paid plan** — Pro ($20/mo), Max ($100/$200/mo), Team, or Enterprise
- **Python 3.10+** with KG-Factory dependencies installed in a virtual environment
- **Neo4j** running with a built knowledge graph
- API keys: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
- Neo4j credentials: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`

### Step 1: Verify Cowork Is Available

Open Claude Desktop. You should see a **Cowork** tab alongside the regular Chat tab. If not:
- Ensure your Claude subscription is active (Pro or higher)
- Update Claude Desktop to the latest version
- Cowork was released January 2026 — older versions don't have it

### Step 2: Prepare the Plugin

The Cowork plugin is in `plugins/cowork/` in the KG-Factory project. Before installing, customize the `.mcp.json` with your absolute paths and credentials:

**Windows:**
```json
{
  "mcpServers": {
    "domain-kg": {
      "command": "C:/Users/yourname/path/to/KnowledgeGraphFactory/.venv/Scripts/python.exe",
      "args": ["-m", "mcp_server.query_server"],
      "env": {
        "PYTHONPATH": "C:/Users/yourname/path/to/KnowledgeGraphFactory",
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "your-password",
        "OPENAI_API_KEY": "sk-your-key",
        "ANTHROPIC_API_KEY": "sk-ant-your-key"
      }
    }
  }
}
```

**macOS/Linux:**
```json
{
  "mcpServers": {
    "domain-kg": {
      "command": "/Users/yourname/path/to/KnowledgeGraphFactory/.venv/bin/python",
      "args": ["-m", "mcp_server.query_server"],
      "env": {
        "PYTHONPATH": "/Users/yourname/path/to/KnowledgeGraphFactory",
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "your-password",
        "OPENAI_API_KEY": "sk-your-key",
        "ANTHROPIC_API_KEY": "sk-ant-your-key"
      }
    }
  }
}
```

### Step 3: Install the Plugin

Copy the plugin folder to Cowork's plugin directory:

**Windows:**
```powershell
Copy-Item -Recurse plugins\cowork "$env:USERPROFILE\.claude\plugins\kg-query"
```

**macOS/Linux:**
```bash
cp -r plugins/cowork ~/.claude/plugins/kg-query
```

Alternatively, load the plugin programmatically via the Claude Agent SDK:
```python
from claude_agent_sdk import query

async for message in query(
    prompt="What's in my knowledge graph?",
    options={"plugins": [{"type": "local", "path": "./plugins/cowork"}]}
):
    print(message)
```

### Step 4: Verify the Integration

1. Open Claude Desktop and switch to the **Cowork** tab
2. Grant file access to a working folder if prompted
3. Ask: **"What's in my knowledge graph?"**
   - Cowork should call `kg_graph_info()` and display the schema
4. Ask: **"What quality issues are customers reporting?"**
   - Cowork should call `kg_chat()` and return a synthesized answer
5. Ask a follow-up: **"Which products are most affected?"**
   - Tests conversation continuity within the same session

### Step 5: Check MCP Connection (Troubleshooting)

If tools are not discovered, check the MCP server manually:

```bash
# Test the query server directly
cd /path/to/KnowledgeGraphFactory
.venv/Scripts/python -m mcp_server.query_server
```

The server should start and wait for stdin input (MCP protocol). If it crashes, check:
- Python venv path is correct in `.mcp.json`
- `PYTHONPATH` points to the KG-Factory project root
- All required env vars are set
- Neo4j is running and accessible

### Cowork Troubleshooting

| Problem | Solution |
|---------|----------|
| Cowork tab not visible | Update Claude Desktop to latest version. Requires paid plan (Pro+). |
| Tools not discovered | Check `.mcp.json` — `command` must be absolute path to Python in venv |
| `ModuleNotFoundError` | Add `PYTHONPATH` to `.mcp.json` env pointing to KG-Factory root |
| Server hangs on Windows | Ensure LangSmith pre-cache is in `query_server.py` (Windows stdin deadlock) |
| `OPENAI_API_KEY` not found | Add to `.mcp.json` env section |
| Plugin not loading | Verify `.claude-plugin/plugin.json` exists and has valid JSON |
| Skill not activating | Ask a domain-specific question (not general knowledge). Skill activates on relevance. |
| Neo4j connection refused | Verify Neo4j is running and `NEO4J_URI` is correct |
| Double API costs | Expected. Cowork's Claude + QueryAgent's Claude are separate LLM calls. Use `kg_graph_info` first (no LLM cost) to check relevance. |

---

## OpenClaw Installation & Integration Guide

### Prerequisites

- **Node.js 22+** (required by OpenClaw)
- **Python 3.10+** with KG-Factory dependencies installed in a virtual environment
- **Neo4j** running with a built knowledge graph (completed construction pipeline)
- API keys: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
- Neo4j credentials: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`

### Step 1: Install OpenClaw

**Windows (PowerShell):**
```powershell
iwr -useb https://openclaw.ai/install.ps1 | iex
```

**macOS / Linux / WSL2:**
```bash
curl -fsSL https://openclaw.ai/install.sh | bash
```

**Or via npm** (if Node 22+ already installed):
```bash
npm install -g openclaw@latest
openclaw onboard --install-daemon
```

The onboarding wizard runs automatically and prompts for:
1. **Authentication** — enter your Anthropic API key
2. **Gateway settings** — defaults are fine (port 18789)
3. **LLM provider** — select Anthropic/Claude
4. **Channels** — skip for now (configure WhatsApp/Telegram/Slack later)

Verify installation:
```bash
openclaw doctor          # Health check
openclaw gateway status  # Should show "Runtime: running"
```

### Step 2: Install the mcp-adapter Plugin

The `mcp-adapter` plugin provides full MCP tool discovery and is the recommended integration path:

```bash
openclaw plugins install mcp-adapter
```

Verify:
```bash
openclaw plugins list
# Expected: "MCP Adapter | mcp-adapter | loaded"
```

### Step 3: Set Up Environment Secrets

Add API keys and Neo4j credentials to OpenClaw's secrets file (`~/.openclaw/.env`):

```env
ANTHROPIC_API_KEY=sk-ant-your-key-here
OPENAI_API_KEY=sk-your-key-here
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password-here
```

OpenClaw injects these into child processes. The `${VAR}` syntax in `openclaw.json` references values from this file.

### Step 4: Configure the KG Query MCP Server

Edit `~/.openclaw/openclaw.json` and add the KG-Factory query server:

```jsonc
{
  "plugins": {
    "entries": {
      "mcp-adapter": {
        "enabled": true,
        "config": {
          "toolPrefix": true,
          "servers": [
            {
              "name": "domain-kg",
              "transport": "stdio",
              "command": "/absolute/path/to/KnowledgeGraphFactory/.venv/Scripts/python.exe",
              "args": ["-m", "mcp_server.query_server"],
              "env": {
                "PYTHONPATH": "/absolute/path/to/KnowledgeGraphFactory",
                "NEO4J_URI": "${NEO4J_URI}",
                "NEO4J_USER": "${NEO4J_USER}",
                "NEO4J_PASSWORD": "${NEO4J_PASSWORD}",
                "OPENAI_API_KEY": "${OPENAI_API_KEY}",
                "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}"
              }
            }
          ]
        }
      }
    }
  },
  "tools": {
    "sandbox": {
      "tools": {
        "allow": ["group:runtime", "group:fs", "mcp-adapter"]
      }
    }
  }
}
```

**Critical details:**

1. **`command` must be the absolute path to the Python executable inside the virtual environment**, not just `"python"`. OpenClaw does not manage Python venvs — it spawns whatever executable you point to:
   - Windows: `.venv/Scripts/python.exe`
   - Linux/macOS: `.venv/bin/python`

2. **`PYTHONPATH`** must point to the KG-Factory project root so `python -m mcp_server.query_server` can find the package.

3. **No `print()` to stdout** in the Python server. OpenClaw uses stdout exclusively for MCP protocol messages (JSON-RPC 2.0). Debug output must go to stderr or a log file. FastMCP handles this correctly.

4. **`${VAR}` syntax** references values from `~/.openclaw/.env` (Step 3).

Restart the gateway to pick up changes:
```bash
openclaw gateway restart
```

At startup, `mcp-adapter` will:
1. Spawn `python -m mcp_server.query_server` as a child process
2. Communicate over stdio (JSON-RPC 2.0)
3. Call `listTools()` — discovers `kg_chat` and `kg_graph_info`
4. Register them as `domain-kg_kg_chat` and `domain-kg_kg_graph_info`

### Step 5: Install the OpenClaw Skill

Create the skill directory and SKILL.md:

```bash
mkdir -p ~/.openclaw/skills/knowledge-graph
```

Copy `skills/knowledge-graph/SKILL.md` from the KG-Factory project (created in this user story) to `~/.openclaw/skills/knowledge-graph/SKILL.md`.

The tool names in the SKILL.md must include the `domain-kg_` prefix (matching `toolPrefix: true` in mcp-adapter config):
- `domain-kg_kg_chat(message, session_id)`
- `domain-kg_kg_graph_info()`

Skills are auto-discovered. OpenClaw watches the skills directory and picks up new SKILL.md files on the next session. No gateway restart needed for skill changes.

### Step 6: Verify the Integration

```bash
openclaw doctor          # Health check
openclaw gateway status  # "Runtime: running", "RPC probe: ok"
openclaw plugins list    # "MCP Adapter | mcp-adapter | loaded"
openclaw dashboard       # Opens web UI at http://127.0.0.1:18789/
```

Test in the dashboard:

```
You: What's in my knowledge graph?
  → OpenClaw calls domain-kg_kg_graph_info()
  → Shows schema with labels, relationships, counts

You: What quality issues are customers reporting about the Stockholm chair?
  → OpenClaw calls domain-kg_kg_chat(message="...", session_id="...")
  → Returns synthesized answer from cross-layer retrieval

You: Did they mention any other furniture?
  → Same session_id — tests follow-up reference resolution
  → QueryAgent resolves "they" from conversation context
```

### Step 7 (Optional): Configure Sub-Agent for Deep Research

For complex multi-query analysis tasks, restrict sub-agents to KG tools only:

```jsonc
// Add to ~/.openclaw/openclaw.json
{
  "tools": {
    "subagents": {
      "tools": {
        "allow": ["domain-kg_kg_chat", "domain-kg_kg_graph_info"],
        "deny": ["group:fs", "group:sessions", "exec"]
      }
    }
  }
}
```

This sandboxes sub-agents to only KG tools — they cannot read files, run commands, or spawn their own sub-agents. OpenClaw's main agent spawns these for tasks like "Analyze our supply chain risks based on the knowledge graph."

### Step 8 (Optional): Connect Chat Channels

Add bot tokens to `~/.openclaw/.env` to receive KG queries from messaging platforms:

```env
TELEGRAM_BOT_TOKEN=...
DISCORD_BOT_TOKEN=...
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

Channels are configured via the onboarding wizard (`openclaw onboard`) or directly in `openclaw.json`. Once connected, users can query the knowledge graph from WhatsApp, Telegram, Slack, Discord, etc. — the SKILL.md guides OpenClaw to route domain questions to `kg_chat`.

### Troubleshooting

| Problem | Solution |
|---------|----------|
| Tools not discovered | Verify `command` is the absolute path to the Python in your venv, not just `"python"` |
| `ModuleNotFoundError` | Add `PYTHONPATH` to the server's `env` pointing to the KG-Factory project root |
| MCP server hangs on Windows | Ensure the LangSmith pre-cache is in `query_server.py` (Windows stdin deadlock prevention, same pattern as `server.py`) |
| `OPENAI_API_KEY` not found | Verify the key is in `~/.openclaw/.env` and the `${OPENAI_API_KEY}` reference in `openclaw.json` matches exactly |
| Skills not showing | Skills load per-session. Start a new chat session after adding SKILL.md |
| Gateway won't restart | Run `openclaw doctor --fix` for automatic repair |
| Stdout pollution breaks MCP | Ensure no `print()` in the Python server. Use `sys.stderr.write()` or logging for debug output |
| Config changes not applied | `openclaw.json` changes require `openclaw gateway restart`. Skills are hot-reloaded. |
| Neo4j connection refused | Verify Neo4j is running and `NEO4J_URI` in `~/.openclaw/.env` is correct |
| Empty graph results | Build the knowledge graph first via the construction pipeline (Claude Code + `server.py`) |

### Architecture When Deployed

```
┌──────────────────────────────────────────────────────────────────┐
│  Host Machine                                                     │
│                                                                   │
│  OPTION A: Claude Cowork              OPTION B: OpenClaw          │
│                                                                   │
│  ┌──────────────────────┐            ┌──────────────────────┐    │
│  │  Claude Desktop      │            │  OpenClaw Gateway    │    │
│  │  (Cowork tab)        │            │  (Node.js daemon)    │    │
│  │  ├── kg-query plugin │            │  ├── mcp-adapter     │    │
│  │  │   .mcp.json       │            │  │   openclaw.json   │    │
│  │  │   SKILL.md        │            │  │   SKILL.md        │    │
│  │  └── Sub-agents      │            │  └── Channels        │    │
│  │      (auto-spawned)  │            │      (WhatsApp, etc) │    │
│  └──────────┬───────────┘            └──────────┬───────────┘    │
│             │                                   │                 │
│             │  stdio (MCP)                      │  stdio (MCP)    │
│             │                                   │                 │
│             └──────────────┬────────────────────┘                 │
│                            ▼                                      │
│  ┌────────────────────────────────────────────┐                   │
│  │  Python: query_server.py                   │                   │
│  │  (child process, spawned by MCP host)      │                   │
│  │  ├── kg_chat(message, session_id)          │                   │
│  │  │   └── QueryAgent.run()                  │                   │
│  │  │       ├── discover_graph                │                   │
│  │  │       ├── search_text / search_keywords │                   │
│  │  │       ├── search_entities               │                   │
│  │  │       └── run_cypher                    │                   │
│  │  └── kg_graph_info()                       │                   │
│  └────────────────────┬───────────────────────┘                   │
│                       │                                           │
│                       ▼                                           │
│  ┌────────────────────────┐                                       │
│  │  Neo4j                 │  (bolt://localhost:7687)              │
│  │  (Knowledge Graph)     │                                       │
│  └────────────────────────┘                                       │
│                                                                   │
│  ┌────────────────────────┐                                       │
│  │  LangSmith (optional)  │  (LANGSMITH_TRACING=true)            │
│  │  Trace hierarchy:      │                                       │
│  │  mcp.kg_chat           │                                       │
│  │   └── query_agent.run  │                                       │
│  │       ├── Claude API   │                                       │
│  │       └── tool.*       │                                       │
│  └────────────────────────┘                                       │
└──────────────────────────────────────────────────────────────────┘
```

**Both options use the same query_server.py** — the MCP server is platform-agnostic. The only difference is how it's configured and spawned (Cowork plugin vs OpenClaw mcp-adapter).

---

## Out of Scope

- LLM provider abstraction (future US016 — use Claude only for now)
- REST/gRPC API layer (MCP is sufficient for both Cowork and OpenClaw)
- Google A2A protocol support (future, ecosystem still maturing)
- Session persistence to disk (in-memory sessions only for now)
- Authentication/authorization on the query server
- Multi-user session isolation (single-user deployment assumed)
- Parallel retriever execution with RRF merge (Claude's sequential tool calling is sufficient)
- Embedding model abstraction (hardcoded to `text-embedding-3-large`)
- Custom retriever configurations per session
- Query result caching across sessions
- Claude Agent SDK automated testing pipeline (future, SDK is still maturing)
- Cowork plugin auto-update mechanism (manual copy for now)
- Remote MCP server deployment (both platforms use local stdio transport for now)
