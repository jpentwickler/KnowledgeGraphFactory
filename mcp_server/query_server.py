"""Query MCP Server for KG-Factory.

Lightweight read-only server exposing stateless query tools for knowledge
graph retrieval. Ships alongside the built knowledge graph to Claude Cowork,
OpenClaw, or any MCP-compatible platform.

Two tools only:
- kg_query: Single-shot adaptive retrieval (1 Claude call + 1 Neo4j call)
- kg_graph_info: Quick schema check (no LLM call)

Supports both stdio (Claude Desktop) and HTTP (Docker/remote) transports.

Key differences from mcp_server/server.py:
- Read-only: never writes state to disk
- Single shared driver (lazy init, closed on shutdown)
- Stateless: no session memory; the outer platform handles conversation
- Only imports query_builder functions (no construction agents)
"""

import atexit
import json
import logging
import os
import signal
import sys
import time

# Add parent directory to path so we can import from kg-factory modules
_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root_dir)

# Load .env from project root (provides ANTHROPIC_API_KEY, etc.)
from dotenv import load_dotenv
load_dotenv(os.path.join(_root_dir, ".env"))

# Pre-cache langsmith runtime env BEFORE FastMCP takes over stdin/stdout.
# See mcp_server/server.py lines 22-38 for full explanation.
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
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from core import load_state
from core.tracing import mcp_traceable
from utils import get_neo4j_driver


# =============================================================================
# Logging
# =============================================================================

_logger = logging.getLogger("kg-query")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)


def _log_request(tool: str, question: str, latency_ms: float) -> None:
    """Emit a structured JSON log line for each request."""
    _logger.info(json.dumps({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": tool,
        "question": question[:200],
        "latency_ms": round(latency_ms, 1),
    }))


def _log_auth_failure(request: Request, reason: str) -> None:
    """Log an authentication failure (no token value logged)."""
    client = request.client
    _logger.warning(json.dumps({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": "auth_failure",
        "path": str(request.url.path),
        "client": client.host if client else "unknown",
        "reason": reason,
    }))


# =============================================================================
# Auth
# =============================================================================

_AUTH_TOKENS: set = set()
_raw = os.environ.get("KG_AUTH_TOKENS", "")
if _raw:
    _AUTH_TOKENS = {t.strip() for t in _raw.split(",") if t.strip()}


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """Validate Bearer tokens on all HTTP requests (except /health)."""

    async def dispatch(self, request: Request, call_next):
        # Always allow health checks
        if request.url.path == "/health":
            return await call_next(request)

        # Dev mode: no tokens configured, allow all
        if not _AUTH_TOKENS:
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            _log_auth_failure(request, "missing_bearer_header")
            return JSONResponse(
                {"error": "Missing or invalid Authorization header"},
                status_code=401,
            )

        token = auth_header[7:]  # Strip "Bearer "
        if token not in _AUTH_TOKENS:
            _log_auth_failure(request, "invalid_token")
            return JSONResponse(
                {"error": "Invalid authentication token"},
                status_code=401,
            )

        return await call_next(request)


# =============================================================================
# Environment validation
# =============================================================================

def _validate_env():
    """Check required env vars. Called in __main__ only, not at import time."""
    required = ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "ANTHROPIC_API_KEY"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(
            f"FATAL: Missing required environment variables: {', '.join(missing)}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if not os.environ.get("OPENAI_API_KEY"):
        print(
            "WARNING: OPENAI_API_KEY not set. Vector/hybrid/cross_layer strategies unavailable.",
            file=sys.stderr,
        )


# =============================================================================
# MCP Server
# =============================================================================

mcp = FastMCP(
    "KG-Query",
    instructions="""\
KG-Query provides adaptive retrieval over a domain knowledge graph.

## Tools

- kg_query: Ask questions about the knowledge graph. Automatically selects
  the best retrieval strategy (schema, cypher, vector, hybrid, cross_layer).
  Pass an optional `context` string to guide strategy selection.
- kg_graph_info: Quick check of what's in the graph (labels, relationships,
  node counts). No conversation needed. Call first if unsure whether the
  graph has relevant data.

## Usage

1. Call kg_graph_info() to see what data is available
2. Call kg_query(question) for single-shot adaptive retrieval
3. For follow-ups, pass relevant prior context via the `context` parameter
"""
)


def _get_state_file() -> str:
    """Resolve the state file path, supporting KG_BASE_DIR project layout.

    Reads the _last_active_project marker written by the construction server
    to determine which project's state to load.
    """
    base_dir = os.environ.get("KG_BASE_DIR")
    if base_dir:
        marker = os.path.join(base_dir, "_last_active_project")
        if os.path.isfile(marker):
            with open(marker, "r", encoding="utf-8") as f:
                project = f.read().strip()
            if project:
                return os.path.join(base_dir, project, "state", "current_state.json")
    state_dir = os.environ.get("KG_STATE_DIR", "state")
    return os.path.join(state_dir, "current_state.json")


# Module-level state
_driver = None
_state: dict = {}
_state_loaded = False


def _get_driver():
    """Lazy-init shared Neo4j driver."""
    global _driver
    if _driver is None:
        _driver = get_neo4j_driver()
    return _driver


def _load_state_once() -> dict:
    """Load state file once, cache in module. Returns shallow copy per call."""
    global _state, _state_loaded
    if not _state_loaded:
        _state = load_state(_get_state_file())
        _state_loaded = True
    return dict(_state)


# =============================================================================
# Input validation constants
# =============================================================================

_MAX_QUESTION_CHARS = 5_000
_MAX_CONTEXT_CHARS = 10_000


# =============================================================================
# Core implementations (testable without MCP decoration)
# =============================================================================

async def _run_kg_query(question: str, context: str = "") -> dict:
    """Core implementation of kg_query (testable without MCP decoration).

    Args:
        question: Natural language question or Cypher query
        context: Optional context to guide strategy selection

    Returns:
        {
            "answer": str,
            "evidence": list,
            "confidence": float,
            "details": dict,
            "status": {"success": bool, "selected_strategy": str, "reasoning": str}
        }
    """
    # Input validation
    if len(question) > _MAX_QUESTION_CHARS:
        return {
            "answer": "Question too long",
            "evidence": [],
            "confidence": 0.0,
            "details": {},
            "status": {
                "success": False,
                "error": f"Question exceeds {_MAX_QUESTION_CHARS} character limit ({len(question)} chars)",
            },
        }

    if len(context) > _MAX_CONTEXT_CHARS:
        return {
            "answer": "Context too long",
            "evidence": [],
            "confidence": 0.0,
            "details": {},
            "status": {
                "success": False,
                "error": f"Context exceeds {_MAX_CONTEXT_CHARS} character limit ({len(context)} chars)",
            },
        }

    from pipelines.query_builder import (
        _select_retrieval_strategy,
        _execute_schema_query,
        _execute_cypher,
        _execute_validated_cypher,
        _execute_vector_search,
        _execute_hybrid_search,
        _execute_cross_layer_traversal,
    )

    try:
        driver = _get_driver()
        state = _load_state_once()

        # Select strategy via Claude
        strategy_data = await _select_retrieval_strategy(question, context, state)
        strategy = strategy_data["strategy"]
        params = strategy_data.get("parameters", {})
        reasoning = strategy_data.get("reasoning", "")

        # Execute selected strategy
        if strategy == "schema":
            result = _execute_schema_query(driver, state)
        elif strategy == "cypher":
            result, correction_note = await _execute_validated_cypher(
                driver, params["cypher_query"], question, state
            )
            if correction_note:
                reasoning += f" [{correction_note}]"
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
            "reasoning": reasoning,
        }

        return result

    except Exception as e:
        error_msg = str(e)
        return {
            "answer": f"Query failed: {error_msg}",
            "evidence": [],
            "confidence": 0.0,
            "details": {},
            "status": {
                "success": False,
                "error": error_msg,
            },
        }


def _run_kg_graph_info() -> dict:
    """Core implementation of kg_graph_info (testable without MCP decoration).

    Returns:
        {"schema": str, "evidence": list}
    """
    from pipelines.query_builder import _execute_schema_query

    driver = _get_driver()
    state = _load_state_once()

    result = _execute_schema_query(driver, state)

    return {
        "schema": result["answer"],
        "evidence": result["evidence"],
    }


# =============================================================================
# MCP Tools
# =============================================================================

@mcp.tool
@mcp_traceable(name="mcp.kg_query")
async def kg_query(question: str, context: str = "") -> dict:
    """Query the knowledge graph with adaptive retrieval.

    Automatically selects optimal strategy based on question type and
    available graph layers:
    - schema: Graph structure exploration
    - cypher: Structured traversal queries
    - vector: Semantic similarity search
    - hybrid: Vector + keyword search
    - cross_layer: Hybrid search + domain entity traversal

    Args:
        question: Natural language question or Cypher query.
        context: Optional context to guide strategy selection
                 (default: ""). Include relevant details from previous
                 answers when asking follow-up questions.

    Returns:
        Dictionary with answer, evidence, confidence, and strategy details.

    Examples:
        kg_query("What labels exist in the graph?")
        kg_query("Which suppliers provide oak lumber?")
        kg_query("Tell me about supply chain delays")
        kg_query("What about delivery times?",
                 context="Previous answer mentioned Supplier A and B")
    """
    t0 = time.time()
    result = await _run_kg_query(question, context)
    _log_request("kg_query", question, (time.time() - t0) * 1000)
    return result


@mcp.tool
@mcp_traceable(name="mcp.kg_graph_info")
def kg_graph_info() -> dict:
    """Get knowledge graph structure and statistics.

    Returns labels, relationship types, node counts, and layer
    classification (domain vs text). No conversation needed.

    Call this first to check what data is available before starting
    to query.

    Returns:
        Dictionary with schema summary and structured evidence.
    """
    t0 = time.time()
    result = _run_kg_graph_info()
    _log_request("kg_graph_info", "(schema)", (time.time() - t0) * 1000)
    return result


# =============================================================================
# Health check
# =============================================================================

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> Response:
    """Neo4j connectivity check. No auth required."""
    try:
        driver = _get_driver()
        driver.verify_connectivity()
        return JSONResponse({"status": "healthy", "neo4j": "connected"})
    except Exception as e:
        return JSONResponse(
            {"status": "unhealthy", "error": str(e)},
            status_code=503,
        )


# =============================================================================
# Graceful shutdown
# =============================================================================

def _shutdown_handler(signum=None, frame=None):
    """Close Neo4j driver on shutdown."""
    global _driver
    if _driver is not None:
        try:
            _driver.close()
        except Exception:
            pass
        _driver = None


atexit.register(_shutdown_handler)


# =============================================================================
# ASGI app export (for uvicorn deployment)
# =============================================================================

_auth_middleware = [Middleware(BearerTokenMiddleware)] if _AUTH_TOKENS else []

app = mcp.http_app(
    transport="streamable-http",
    stateless_http=True,
    middleware=_auth_middleware,
)


# =============================================================================
# CLI entry point
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="KG-Query MCP Server")
    parser.add_argument(
        "--http", action="store_true",
        help="Run as HTTP server (default: stdio for Claude Desktop)",
    )
    parser.add_argument(
        "--port", type=int, default=8000,
        help="Port for HTTP mode (default: 8000)",
    )
    args = parser.parse_args()

    _validate_env()

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    if args.http:
        mcp.run(
            transport="streamable-http",
            host="0.0.0.0",
            port=args.port,
            stateless_http=True,
            middleware=_auth_middleware,
        )
    else:
        mcp.run()  # stdio unchanged
