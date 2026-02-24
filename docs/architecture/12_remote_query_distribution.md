# Remote Query Distribution: Plug-and-Play Cowork Plugin

> **Status**: Proposal
> **Depends on**: US013 (Query Infrastructure), US015 (Query Agent)
> **Related**: `07_kg_query_mcp_server.md`, `08_query_agent_openclaw.md`
> **Goal**: Non-developer end users install a Cowork plugin and query a knowledge graph — no Python, no API keys, no configuration

---

## Problem Statement

The current `kg_query` distribution requires end users to:

1. Install Python + 4-9 packages on their machine
2. Clone the KG-Factory repository (or copy 16 files manually)
3. Edit `.mcp.json` with absolute paths to Python, state directory, and project root
4. Obtain and paste 3-4 API keys (Anthropic, OpenAI, Neo4j credentials)
5. Understand environment variables and MCP server configuration

This is acceptable for developers but **impossible for non-technical end users**. A business analyst who needs to query a knowledge graph should not need to install Python.

### Current Plugin State

The existing Cowork plugin (`plugins/cowork/`) has hardcoded absolute paths and
embedded credentials:

```json
{
  "mcpServers": {
    "domain-kg": {
      "command": "C:\\Users\\jprob\\anaconda3\\envs\\base1\\python.exe",
      "args": ["-m", "mcp_server.query_server"],
      "env": {
        "PYTHONPATH": "C:\\...\\KnowledgeGraphFactory",
        "KG_STATE_DIR": "C:\\...\\furniture_supply_chain\\state",
        "NEO4J_URI": "neo4j+s://...",
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

Not distributable. Not portable. Not plug-and-play.

---

## Solution: Remote MCP Server

Move the query server from a **local stdio process** to a **hosted HTTP service**.
The Cowork plugin becomes a thin pointer to a URL:

```
End User (Cowork)                    Hosted Infrastructure
┌─────────────────────┐             ┌──────────────────────────────┐
│  Cowork Plugin       │   HTTPS    │  Remote MCP Server           │
│  ┌────────────────┐ │ ─────────► │  (query_server.py)           │
│  │ .mcp.json      │ │ Streamable │    │                          │
│  │ url: https://… │ │ HTTP       │    ├─► Claude API (strategy)  │
│  │ SKILL.md       │ │ ◄───────── │    ├─► Neo4j (queries)       │
│  └────────────────┘ │            │    └─► OpenAI (embeddings)   │
└─────────────────────┘             └──────────────────────────────┘
                                          │
No Python on user machine.           All credentials server-side.
No API keys in plugin.               State file lives here.
Just install + use.
```

### What the Plugin Becomes

```
kg-query-plugin/
├── .claude-plugin/
│   └── plugin.json                  # 6 lines of metadata
├── .mcp.json                        # 1 URL, optionally 1 token
└── skills/
    └── knowledge-graph/
        └── SKILL.md                 # Usage guidance for Claude
```

**.mcp.json** — the entire configuration:
```json
{
  "mcpServers": {
    "domain-kg": {
      "type": "http",
      "url": "https://kg-query.example.com/mcp"
    }
  }
}
```

---

## Cowork Plugin System Context

### How Cowork Plugins Work

Cowork plugins and Claude Code plugins share the **same format** — a directory
of Markdown and JSON files. No compiled code, no build step.

**Installation paths:**
1. **Upload plugin** — User clicks "+" in Cowork Plugins dialog, selects a local directory
2. **Add a marketplace** — User adds a Git repo URL containing `marketplace.json`, then browses and installs plugins from it

**Plugin components** (all optional):
- `.claude-plugin/plugin.json` — manifest (only `name` required)
- `.mcp.json` — MCP server configurations
- `skills/` — SKILL.md files for domain-specific guidance
- `commands/` — slash commands
- `agents/` — custom subagent definitions
- `hooks/` — event handlers

**Key variable**: `${CLAUDE_PLUGIN_ROOT}` resolves to the plugin directory after
installation (plugins are copied to a cache).

### Cowork Plugins vs Desktop Extensions (DXT)

These are **two different systems** for two different products:

| Aspect | Cowork/Claude Code Plugins | Desktop Extensions (DXT) |
|--------|---------------------------|--------------------------|
| Product | Cowork + Claude Code | Claude Desktop app |
| Format | Directory (Markdown + JSON) | `.dxt` zip archive |
| Components | Skills, commands, agents, hooks, MCP | MCP server only |
| Manifest | `.claude-plugin/plugin.json` | `manifest.json` |
| Config UI | None (env vars or hardcoded) | `user_config` form |
| Installation | Upload dir or marketplace | Double-click `.dxt` |

**Important**: DXT extensions have a `user_config` UI that prompts for credentials
during install. Cowork plugins do **not** — credentials must be environment
variables, hardcoded, or handled server-side. This is a key reason the remote
server approach is necessary for non-developer users.

---

## Architecture Decision: Single-Tenant

Each deployed server instance serves **one knowledge graph**. A customer with
three graphs gets three server instances, each with its own URL.

**Why single-tenant:**
- Current `query_server.py` architecture already works this way (state loaded once)
- No session routing, no tenant isolation, no shared-state bugs
- Docker makes spinning up N instances trivial
- Multi-tenant is premature optimization

**Trade-off**: More instances to manage, but each is stateless and identical
except for environment variables.

---

## Work Packages

### WP1: Upgrade Transport — stdio to Streamable HTTP

**What**: Change the FastMCP transport from `sse` to `http` (Streamable HTTP,
the current MCP standard since spec revision 2025-03-26).

**Why**: Streamable HTTP uses a single endpoint, works through proxies and load
balancers, and is the transport that Claude Code and Cowork connect to for
remote servers.

**Current code** (`query_server.py` lines 255-265):
```python
if args.http:
    mcp.run(transport="sse", host="0.0.0.0", port=args.port)
else:
    mcp.run()
```

**Target code**:
```python
mcp = FastMCP("kg-query", stateless_http=True)

# Export ASGI app for production (uvicorn)
app = mcp.http_app()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.http:
        mcp.run(transport="http", host="0.0.0.0", port=args.port)
    else:
        mcp.run()  # stdio for local dev
```

**Key details**:
- `stateless_http=True` — each request is independent, no server-side session.
  This enables horizontal scaling and serverless deployment.
- `app = mcp.http_app()` — exports an ASGI app for uvicorn/gunicorn.
- Stdio mode preserved for local development and Claude Code.
- Requires `fastmcp>=2.3` (Streamable HTTP added in 2.3).

**Files**: `mcp_server/query_server.py`, `requirements.txt`
**Effort**: Small (1-2 hours)

---

### WP2: Authentication

**What**: Protect the remote endpoint so only authorized users can query.

**Decision**: Start with **Bearer token** authentication. Simple, sufficient for
personal and small-team use. Upgrade to OAuth 2.1 later if enterprise SSO is
needed.

**Implementation**:
```python
import os

AUTH_TOKENS = set(
    t.strip()
    for t in os.environ.get("KG_AUTH_TOKENS", "").split(",")
    if t.strip()
)

# If no tokens configured, server runs without auth (dev mode)
```

FastMCP supports auth providers natively. For the MVP, a lightweight check is
sufficient. For production, FastMCP's `BearerAuthProvider` or a reverse proxy
(Nginx, Caddy) can handle token validation.

**Plugin side** — user needs one token:
```json
{
  "mcpServers": {
    "domain-kg": {
      "type": "http",
      "url": "https://kg-query.example.com/mcp",
      "headers": {
        "Authorization": "Bearer ${KG_QUERY_TOKEN}"
      }
    }
  }
}
```

**Auth options comparison**:

| Approach | User Experience | Security | Implementation |
|----------|----------------|----------|----------------|
| No auth | Zero config | Anyone can query | None |
| Bearer token | Set 1 env var | Good enough for most | Small |
| OAuth 2.1 (GitHub) | Click "authorize" once | Best | Medium-Large |

**Upgrade path to OAuth**: FastMCP has built-in `GitHubProvider`. When ready,
swap the auth provider — the plugin `.mcp.json` changes from `headers` to
`oauth: { clientId }`, and users authenticate via browser redirect.

**Files**: `mcp_server/query_server.py`
**Effort**: Medium (3-5 hours)

---

### WP3: Production Hardening

**What**: Make the server robust enough for external use.

#### 3a. Environment Validation (fail fast)

```python
def _validate_env():
    required = ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "ANTHROPIC_API_KEY"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        raise SystemExit(f"Missing required env vars: {', '.join(missing)}")
```

#### 3b. Health Check Endpoint

Cloud platforms need a liveness/readiness probe:

```python
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    try:
        driver = _get_driver()
        driver.verify_connectivity()
        return JSONResponse({"status": "healthy", "neo4j": "connected"})
    except Exception as e:
        return JSONResponse({"status": "unhealthy", "error": str(e)}, status_code=503)
```

#### 3c. Input Validation

Cap input sizes to prevent abuse:

| Parameter | Max Length | Rationale |
|-----------|-----------|-----------|
| `question` | 5,000 chars | Prevents token-bombing Claude API |
| `context` | 10,000 chars | Context is optional, can be long for follow-ups |

#### 3d. Graceful Shutdown

```python
import signal

def _shutdown(signum, frame):
    global _driver
    if _driver:
        _driver.close()
    sys.exit(0)

signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT, _shutdown)
```

#### 3e. Connection Timeouts

```python
# In neo4j_utils.py
driver = GraphDatabase.driver(
    uri,
    auth=(user, password),
    max_connection_pool_size=int(os.environ.get("NEO4J_POOL_SIZE", "50")),
    connection_timeout=30.0,
)
```

#### 3f. Request Logging

Structured JSON logs for audit trail:
```
{"ts": "2026-02-22T14:30:00Z", "tool": "kg_query", "question": "...", "strategy": "hybrid", "latency_ms": 1200}
```

**Files**: `mcp_server/query_server.py`, `utils/neo4j_utils.py`
**Effort**: Medium (3-4 hours)

---

### WP4: Containerization

**What**: Package the query server as a Docker image so deployment is a
`docker run` away.

**Dockerfile** (query-only, minimal):
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements-query.txt .
RUN pip install --no-cache-dir -r requirements-query.txt

# Copy ONLY query-related code (not construction pipeline)
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

**requirements-query.txt** (minimal dependencies):
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

**Files included in image** (16 files, ~50KB total code):

| File | Purpose |
|------|---------|
| `mcp_server/query_server.py` | MCP server, 2 tools |
| `pipelines/query_builder.py` | 5 retrieval strategies |
| `tools/query_tools.py` | Query helper functions |
| `core/state.py` | State loading |
| `core/tracing.py` | Optional LangSmith |
| `utils/neo4j_utils.py` | Neo4j driver factory |

**State file**: Mount as volume or bake into image at build time:
```bash
# Option A: Mount at runtime
docker run -v /path/to/state:/app/state -e KG_STATE_DIR=/app/state ...

# Option B: Copy into image during build (simpler for single-graph deploys)
COPY state/current_state.json /app/state/current_state.json
```

**Files**: new `Dockerfile.query`, new `requirements-query.txt`
**Effort**: Small (2-3 hours)

---

### WP5: Hosting & Deployment

**What**: Deploy the containerized server to a cloud platform.

#### Recommended: Railway (simplest)

```bash
railway login
railway init
railway variables set NEO4J_URI=neo4j+s://xxx.databases.neo4j.io
railway variables set NEO4J_USER=neo4j
railway variables set NEO4J_PASSWORD=xxx
railway variables set ANTHROPIC_API_KEY=sk-ant-xxx
railway variables set OPENAI_API_KEY=sk-xxx
railway variables set KG_AUTH_TOKENS=token-for-user-1,token-for-user-2
railway up
# → https://kg-query-production.up.railway.app/mcp
```

#### Alternative: Fly.io (cheapest)

```bash
fly launch --image ghcr.io/kg-factory/kg-query:latest
fly secrets set NEO4J_URI=... ANTHROPIC_API_KEY=... KG_AUTH_TOKENS=...
fly deploy
# → https://kg-query.fly.dev/mcp
```

#### Alternative: Google Cloud Run (auto-scales to zero)

```bash
gcloud run deploy kg-query \
  --image ghcr.io/kg-factory/kg-query:latest \
  --port 8000 \
  --set-env-vars NEO4J_URI=...,ANTHROPIC_API_KEY=...
# → https://kg-query-xxx.run.app/mcp
```

#### Cost Comparison

| Platform | Min Cost | Auto-Scale | Cold Start |
|----------|----------|-----------|------------|
| Railway | ~$5/month | No (always on) | None |
| Fly.io | ~$2-4/month | Yes | ~1-2s |
| Cloud Run | Free tier (2M req) | Yes (to zero) | ~3-5s |
| AWS Lambda | Free tier (1M req) | Yes (to zero) | ~5-10s |

**Recommendation**: Railway for MVP (no cold starts, simple). Cloud Run for
production (free tier, auto-scaling).

**Files**: new `railway.json` or `fly.toml`, new `Procfile`
**Effort**: Small (1-2 hours)

---

### WP6: Plugin Packaging

**What**: Create the distributable Cowork plugin directory.

**plugin.json**:
```json
{
  "name": "kg-query",
  "version": "1.0.0",
  "description": "Query knowledge graphs built with KG-Factory",
  "author": {
    "name": "KG-Factory",
    "url": "https://github.com/your-org/kg-factory"
  },
  "keywords": ["knowledge-graph", "neo4j", "query"]
}
```

**.mcp.json** (per-deployment — the URL changes per graph):
```json
{
  "mcpServers": {
    "domain-kg": {
      "type": "http",
      "url": "https://kg-query-production.up.railway.app/mcp",
      "headers": {
        "Authorization": "Bearer ${KG_QUERY_TOKEN}"
      }
    }
  }
}
```

**SKILL.md** — reuse existing `skills/knowledge-graph/SKILL.md` as-is.

**Distribution methods**:

1. **Direct upload** — User downloads the plugin folder (from GitHub release or
   zip), uploads in Cowork via Plugins > "+" button
2. **Git marketplace** — Host a `marketplace.json` in a GitHub repo. User adds
   the marketplace URL once, then installs kg-query from the browse dialog.
3. **Per-customer zip** — For each deployment, generate a plugin folder with the
   customer's specific server URL pre-configured, zip it, send it to them.
   They unzip and upload. Zero config.

#### Marketplace Distribution

For option 2, create a separate GitHub repo:

```
kg-factory-plugins/
├── .claude-plugin/
│   └── marketplace.json
├── plugins/
│   └── kg-query/
│       ├── .claude-plugin/plugin.json
│       ├── .mcp.json
│       └── skills/knowledge-graph/SKILL.md
└── README.md
```

**marketplace.json**:
```json
{
  "name": "kg-factory-plugins",
  "owner": { "name": "KG-Factory" },
  "metadata": {
    "description": "Knowledge graph tools for Claude",
    "pluginRoot": "./plugins"
  },
  "plugins": [
    {
      "name": "kg-query",
      "source": "./plugins/kg-query",
      "description": "Query knowledge graphs with adaptive retrieval",
      "version": "1.0.0",
      "category": "data",
      "tags": ["knowledge-graph", "neo4j", "query"]
    }
  ]
}
```

User installs with: **Plugins > Add marketplace > paste GitHub URL > Install kg-query**

**Files**: restructure `plugins/cowork/`, optionally new marketplace repo
**Effort**: Small (1-2 hours)

---

## End-to-End User Journey

### For the KG Developer (you)

```
1. Build knowledge graph with KG-Factory (existing pipeline)
2. Deploy query server:
   docker build -f Dockerfile.query -t kg-query .
   docker push ghcr.io/kg-factory/kg-query:latest
   railway up  (or fly deploy, or gcloud run deploy)
3. Generate auth token for the end user
4. Send user:  plugin zip + token
   (or: marketplace URL + token)
```

### For the End User (non-developer)

```
1. Open Cowork
2. Set environment variable: KG_QUERY_TOKEN=<token from developer>
3. Plugins > "+" > Upload plugin directory  (or: Add marketplace > URL)
4. Start chatting:
   "What suppliers provide oak lumber?"
   "Show me the defect trends for Q3"
   "Which products are affected by the recall?"
```

**Zero Python. Zero API keys. Zero configuration beyond one token.**

### Fully Zero-Config Variant

If the developer bakes the token into the plugin (acceptable for internal use):

```json
{
  "mcpServers": {
    "domain-kg": {
      "type": "http",
      "url": "https://kg-query.fly.dev/mcp",
      "headers": {
        "Authorization": "Bearer hardcoded-internal-token"
      }
    }
  }
}
```

User experience: **Upload plugin. Done.** Literally two clicks.

---

## Implementation Sequence

```
WP1  Transport upgrade    ██░░░░░░░░  1-2h   prerequisite
 │
 ├──► WP2  Authentication  ████░░░░░░  3-5h   blocks external use
 │
 └──► WP4  Docker image    ███░░░░░░░  2-3h   blocks deployment
       │
       ├──► WP3  Hardening ████░░░░░░  3-4h   incremental
       │
       └──► WP5  Deploy    ██░░░░░░░░  1-2h   needs WP1+WP4
             │
             └──► WP6  Plugin  ██░░░░░░░░  1-2h   final step

Critical path: WP1 → WP4 → WP5 → WP6      (~6h minimum viable)
Full path:     WP1 → WP2 → WP3 → WP4 → WP5 → WP6  (~15h with auth + hardening)
```

---

## Cost Model

### Per-Deployment Costs

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| MCP server hosting | $2-10 | Fly.io / Railway / Cloud Run |
| Neo4j AuraDB | $0-65 | Free tier (200K nodes) or Professional |
| Claude API | ~$0.01-0.10/query | Sonnet for strategy selection |
| OpenAI API | ~$0.001/query | Embeddings for vector/hybrid |
| **Total (small)** | **$2-15/month** | Free Neo4j tier + Fly.io |
| **Total (production)** | **$70-100/month** | AuraDB Pro + Railway |

### Per-Query Costs

| Component | Cost | When |
|-----------|------|------|
| Strategy selection | ~$0.005 | Every query (1 Claude call) |
| Cypher execution | $0 | Schema/cypher strategies |
| Vector search | ~$0.001 | Vector/hybrid/cross-layer |
| **Total per query** | **~$0.006** | |

---

## Open Questions

1. **State file lifecycle**: When the graph is rebuilt, how does the remote
   server pick up the new state? Options: redeploy container, hot-reload on
   file change, fetch from S3/GCS on startup.

2. **Per-customer isolation**: For SaaS-style distribution, do we need
   multi-tenant support eventually? Or is one-instance-per-graph sufficient?

3. **OAuth timeline**: When (if ever) do we need OAuth instead of Bearer
   tokens? Depends on whether Claude Desktop Connectors are a target.

4. **Neo4j connection strategy**: The current shared driver with 50-connection
   pool works for single-user. For 50+ concurrent users, pool size needs
   tuning and monitoring.

---

## References

- [MCP Streamable HTTP Spec (2025-03-26)](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [FastMCP HTTP Deployment](https://gofastmcp.com/deployment/http)
- [Cowork Plugin Docs](https://code.claude.com/docs/en/plugins)
- [Plugin Marketplace Docs](https://code.claude.com/docs/en/plugin-marketplaces)
- [Claude Code MCP Remote Servers](https://code.claude.com/docs/en/mcp)
- [Anthropic Knowledge Work Plugins](https://github.com/anthropics/knowledge-work-plugins)
- [Railway FastMCP Template](https://railway.com/deploy/fastmcp)
- [Fly.io MCP Blueprints](https://fly.io/docs/blueprints/remote-mcp-servers/)
- [Cloud Run MCP Hosting](https://docs.google.com/run/docs/host-mcp-servers)
