# US021: Remote Query Server

## User Story

**As a** KG-Factory Developer
**I want** the query server to run as a remote HTTP service with authentication, health checks, and containerization
**So that** I can deploy it to cloud platforms and expose knowledge graph queries to end users without requiring Python on their machines

## Story Points: 5

## Status: Not Started

## Context

The current `query_server.py` runs only as a local stdio process, requiring
Python, dependencies, and credentials on the end user's machine. To enable
plug-and-play distribution (US022), the server must first be deployable as a
remote HTTP service.

This story makes the server production-ready. US022 (next story) handles the
actual deployment and plugin packaging for end users.

See `docs/architecture/12_remote_query_distribution.md` for the full design.

## Acceptance Criteria

### Streamable HTTP Transport

- [ ] `query_server.py` supports Streamable HTTP transport via `mcp.run(transport="http", ...)`
- [ ] `stateless_http=True` flag set on `FastMCP` — each request is independent, no server-side session state
- [ ] ASGI app exported as module-level `app` variable for uvicorn: `app = mcp.http_app()`
- [ ] Stdio mode preserved as default — `mcp.run()` without args still uses stdio for local dev / Claude Code
- [ ] `--http` flag switches to HTTP transport, `--port` configurable (default 8000)
- [ ] `fastmcp>=2.3` in `requirements.txt` (Streamable HTTP support)
- [ ] `uvicorn>=0.30.0` added to `requirements.txt`
- [ ] Existing `kg_query` and `kg_graph_info` tools work identically over HTTP as over stdio
- [ ] Unit test: ASGI app is importable and is a valid ASGI application

### Bearer Token Authentication

- [ ] Server reads `KG_AUTH_TOKENS` env var (comma-separated list of valid tokens)
- [ ] When `KG_AUTH_TOKENS` is set, every MCP request must include `Authorization: Bearer <token>` header
- [ ] Requests with missing or invalid tokens receive HTTP 401 Unauthorized
- [ ] When `KG_AUTH_TOKENS` is empty or unset, server runs without auth (dev mode)
- [ ] Auth check happens before tool execution (no Claude API / Neo4j calls on invalid token)
- [ ] Unit test: valid token passes, invalid token returns 401, no-token-configured passes all requests

### Environment Validation

- [ ] New function `_validate_env()` checks required env vars at startup
- [ ] Required vars: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `ANTHROPIC_API_KEY`
- [ ] Missing vars cause immediate `SystemExit` with clear error listing which vars are missing
- [ ] Validation runs before FastMCP starts (fail fast)
- [ ] `OPENAI_API_KEY` logged as warning if missing (optional — needed only for vector/hybrid strategies)
- [ ] Unit test: missing required var raises SystemExit, optional var logs warning

### Health Check Endpoint

- [ ] `GET /health` endpoint returns JSON with server status
- [ ] Healthy response: `{"status": "healthy", "neo4j": "connected"}` with HTTP 200
- [ ] Unhealthy response: `{"status": "unhealthy", "error": "<message>"}` with HTTP 503
- [ ] Health check verifies Neo4j connectivity via `driver.verify_connectivity()`
- [ ] Health check does NOT call Claude API or OpenAI (no cost, no latency)
- [ ] Works with cloud platform liveness/readiness probes (Railway, Fly.io, Cloud Run, Kubernetes)
- [ ] Unit test: healthy when Neo4j connected, unhealthy when Neo4j down (mock driver)

### Input Validation

- [ ] `question` parameter capped at 5,000 characters — longer inputs return error
- [ ] `context` parameter capped at 10,000 characters — longer inputs return error
- [ ] Validation happens before Claude API call (no token waste on oversized inputs)
- [ ] Error response includes which parameter exceeded the limit and by how much
- [ ] Unit test: within-limit passes, over-limit returns error with details

### Graceful Shutdown

- [ ] Server handles `SIGTERM` and `SIGINT` signals
- [ ] On shutdown, closes Neo4j driver cleanly (`_driver.close()`)
- [ ] No hanging connections after container stop
- [ ] Works with Docker's stop sequence (SIGTERM → 10s grace → SIGKILL)

### Connection Timeouts

- [ ] Neo4j driver connection timeout configurable via `NEO4J_CONNECTION_TIMEOUT` env var (default: 30s)
- [ ] Neo4j connection pool size configurable via `NEO4J_POOL_SIZE` env var (default: 50)
- [ ] Changes applied in `utils/neo4j_utils.py` `get_neo4j_driver()` function
- [ ] Unit test: env vars are read and passed to driver constructor (mock `GraphDatabase.driver`)

### Request Logging

- [ ] Each tool invocation logs: timestamp, tool name, question (truncated to 200 chars), latency in ms
- [ ] Logs go to stderr (not stdout — stdout reserved for MCP protocol in stdio mode)
- [ ] Structured format: `{"ts": "...", "tool": "kg_query", "question": "...", "latency_ms": 1200}`
- [ ] Auth failures logged with client info (no token value logged)
- [ ] Logging does not break stdio transport (stderr only)

### Containerization

- [ ] New `Dockerfile.query` builds a minimal query-only image
- [ ] Image based on `python:3.11-slim`
- [ ] Only query-related files copied (not construction pipeline):
  - `mcp_server/__init__.py`, `mcp_server/query_server.py`
  - `pipelines/__init__.py`, `pipelines/query_builder.py`
  - `tools/__init__.py`, `tools/query_tools.py`
  - `core/__init__.py`, `core/state.py`, `core/tracing.py`
  - `utils/__init__.py`, `utils/neo4j_utils.py`
- [ ] New `requirements-query.txt` with minimal dependencies (no pandas, rapidfuzz, etc.)
- [ ] `HEALTHCHECK` instruction in Dockerfile pointing to `/health` endpoint
- [ ] Default `CMD`: `uvicorn mcp_server.query_server:app --host 0.0.0.0 --port 8000`
- [ ] `EXPOSE 8000`
- [ ] State file mountable as volume: `-v /path/to/state:/app/state`
- [ ] Image builds successfully: `docker build -f Dockerfile.query -t kg-query .`
- [ ] Container starts and responds to health check: `curl http://localhost:8000/health`
- [ ] Container responds to MCP requests over HTTP

### Backwards Compatibility

- [ ] Stdio mode unchanged — existing Claude Code integration works without modification
- [ ] Existing `.mcp.json` configs (root and examples/) work without changes
- [ ] Construction server (`mcp_server/server.py`) unmodified
- [ ] All existing unit tests pass without modification
- [ ] `query_server.py` still runnable as `python -m mcp_server.query_server` (stdio)

## Definition of Done

- [ ] Code implemented and working
- [ ] Unit tests for HTTP transport (ASGI app importable)
- [ ] Unit tests for auth middleware (valid/invalid/no-auth modes)
- [ ] Unit tests for environment validation (missing required/optional vars)
- [ ] Unit tests for health check (healthy/unhealthy responses)
- [ ] Unit tests for input validation (within/over limits)
- [ ] Unit tests for connection timeout configuration
- [ ] Docker image builds successfully
- [ ] Container starts, passes health check, responds to MCP tool calls
- [ ] Stdio mode still works (manual verification with `python -m mcp_server.query_server`)
- [ ] All existing tests pass (496+ unit tests)
- [ ] LangSmith traces work over HTTP transport when enabled
- [ ] Code reviewed
- [ ] Documentation: `docs/architecture/12_remote_query_distribution.md` updated with implementation details

## Technical Notes

### Architecture

```
query_server.py (updated)
  │
  ├── FastMCP("kg-query", stateless_http=True)
  │     │
  │     ├── app = mcp.http_app()           # ASGI export for uvicorn
  │     │
  │     ├── /health                         # Custom route (GET)
  │     │     └── verify Neo4j connectivity
  │     │
  │     ├── /mcp                            # Streamable HTTP (auto)
  │     │     ├── Auth middleware (Bearer token check)
  │     │     ├── Input validation
  │     │     ├── kg_query(question, context)
  │     │     └── kg_graph_info()
  │     │
  │     └── stdio                           # Default (unchanged)
  │           ├── kg_query(question, context)
  │           └── kg_graph_info()
  │
  └── Logging (stderr, structured JSON)
```

### Transport Modes

```python
mcp = FastMCP("kg-query", stateless_http=True)

# ASGI app for production deployment
app = mcp.http_app()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true",
                        help="Run as HTTP server (Streamable HTTP)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.http:
        mcp.run(transport="http", host="0.0.0.0", port=args.port)
    else:
        mcp.run()  # stdio for local dev
```

### Auth Middleware

```python
AUTH_TOKENS = set(
    t.strip()
    for t in os.environ.get("KG_AUTH_TOKENS", "").split(",")
    if t.strip()
)

def _check_auth(headers: dict) -> bool:
    """Returns True if request is authorized."""
    if not AUTH_TOKENS:
        return True  # No tokens configured = dev mode
    token = headers.get("authorization", "").replace("Bearer ", "")
    return token in AUTH_TOKENS
```

### Dockerfile.query

```dockerfile
FROM python:3.11-slim
WORKDIR /app

COPY requirements-query.txt .
RUN pip install --no-cache-dir -r requirements-query.txt

COPY core/__init__.py core/state.py core/tracing.py core/
COPY utils/__init__.py utils/neo4j_utils.py utils/
COPY tools/__init__.py tools/query_tools.py tools/
COPY pipelines/__init__.py pipelines/query_builder.py pipelines/
COPY mcp_server/__init__.py mcp_server/query_server.py mcp_server/

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "mcp_server.query_server:app", "--host", "0.0.0.0", "--port", "8000"]
```

### requirements-query.txt

```
anthropic>=0.40.0
neo4j>=5.0.0
fastmcp>=2.3
python-dotenv>=1.0.0
uvicorn>=0.30.0
# Optional (vector/hybrid/cross_layer strategies):
neo4j-graphrag>=1.0.0
openai>=1.0.0
```

### Files to Create

```
Dockerfile.query                    # NEW: Query-only Docker image
requirements-query.txt              # NEW: Minimal dependencies
tests/unit/test_remote_query.py     # NEW: Unit tests for HTTP, auth, health, validation
```

### Files to Modify

```
mcp_server/query_server.py          # UPDATE: HTTP transport, auth, health, validation,
                                    #         graceful shutdown, logging, ASGI export
utils/neo4j_utils.py                # UPDATE: Configurable pool size + connection timeout
requirements.txt                    # UPDATE: fastmcp>=2.3, add uvicorn
```

### Files NOT Modified

```
mcp_server/server.py                # UNCHANGED: construction server
pipelines/query_builder.py          # UNCHANGED: query strategies
tools/query_tools.py                # UNCHANGED: query helpers
core/agent.py                       # UNCHANGED: agent runner
core/state.py                       # UNCHANGED: state management
core/tracing.py                     # UNCHANGED: observability
```

## Dependencies

- US013: Query Infrastructure (provides `_execute_*` strategy functions)
- US015: Query Agent (provides `query_server.py` baseline)
- FastMCP >= 2.3 (Streamable HTTP support)
- uvicorn (ASGI server for production)

## Out of Scope

- Cloud deployment (handled in US022)
- Cowork plugin packaging (handled in US022)
- Marketplace setup (handled in US022)
- OAuth 2.1 authentication (future — Bearer token sufficient for MVP)
- Multi-tenant support (single-tenant per architecture decision)
- Session persistence to external store (Redis, etc.)
- Rate limiting (can be added via reverse proxy)
- CORS headers (not needed until browser clients are supported)
- Metrics/Prometheus endpoint (future observability enhancement)
