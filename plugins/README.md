# KG-Factory Plugins

Plugins for querying knowledge graphs built with KG-Factory across different
platforms.

## Plugin Variants

| Plugin | Platform | Transport | For | Requirements |
|--------|----------|-----------|-----|-------------|
| `cowork-local/` | Claude Cowork | stdio | Developers | Python, env vars, local Neo4j access |
| `cowork-remote/` | Claude Cowork | HTTP | End users (desktop) | Just a URL (+ optional token) |
| `openclaw-remote/` | OpenClaw | HTTP | End users (messaging channels) | OpenClaw on Railway + URL + token |

## cowork-local/

Local stdio plugin for developers who have the KG-Factory repo and Python
environment set up. The query server runs as a subprocess.

**Setup:**
1. Set environment variables: `KG_FACTORY_DIR`, `KG_STATE_DIR`, `NEO4J_URI`,
   `NEO4J_USER`, `NEO4J_PASSWORD`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
2. Install the plugin in Cowork: Plugins > "+" > select `plugins/cowork-local/`

## cowork-remote/

HTTP plugin for end users. Points to a hosted query server — no Python,
no API keys, no configuration beyond a URL and optional token.

**Setup:**
1. Edit `.mcp.json` — replace `YOUR-DEPLOYMENT-URL` with the actual server URL
2. Optionally set `KG_QUERY_TOKEN` env var (or bake token directly)
3. Install in Cowork: Plugins > "+" > select `plugins/cowork-remote/`

## openclaw-remote/

HTTP configuration for OpenClaw deployed on Railway. Connects to the same
KG-Query server as the Cowork plugins via `mcp-adapter` with HTTP transport.
End users query the knowledge graph from messaging channels (WhatsApp,
Telegram, Slack, Discord).

**Setup:**
1. Deploy OpenClaw on Railway ([guide](../docs/guides/deploy_openclaw.md))
2. Merge `openclaw.json.example` into your OpenClaw's `openclaw.json`
3. Replace `YOUR-KG-QUERY-URL` with the actual KG-Query server URL
4. Set `KG_QUERY_TOKEN` in `~/.openclaw/.env`
5. Copy `skills/knowledge-graph/SKILL.md` to `$OPENCLAW_WORKSPACE_DIR/skills/knowledge-graph/`
6. Restart the OpenClaw gateway

## Deploying the Remote Server

### Railway (recommended)

```bash
# 1. Install Railway CLI and log in
railway login

# 2. Create a new project
railway init

# 3. Set environment variables
railway variables set NEO4J_URI=neo4j+s://xxx.databases.neo4j.io
railway variables set NEO4J_USER=neo4j
railway variables set NEO4J_PASSWORD=your-password
railway variables set ANTHROPIC_API_KEY=sk-ant-xxx
railway variables set OPENAI_API_KEY=sk-xxx
railway variables set KG_AUTH_TOKENS=token-for-user-1,token-for-user-2

# 4. Deploy
railway up
# -> https://kg-query-production.up.railway.app
```

The health check at `/health` verifies Neo4j connectivity.

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NEO4J_URI` | Yes | Neo4j connection URI |
| `NEO4J_USER` | Yes | Neo4j username |
| `NEO4J_PASSWORD` | Yes | Neo4j password |
| `ANTHROPIC_API_KEY` | Yes | Claude API key (strategy selection) |
| `OPENAI_API_KEY` | No | For vector/hybrid/cross_layer strategies |
| `KG_AUTH_TOKENS` | No | Comma-separated bearer tokens |
| `KG_STATE_DIR` | No | State directory (default: `/app/state`) |

### Fly.io (alternative)

```bash
fly launch --dockerfile Dockerfile.query
fly secrets set NEO4J_URI=... ANTHROPIC_API_KEY=... KG_AUTH_TOKENS=...
fly deploy
# -> https://kg-query.fly.dev
```

### Docker (manual)

```bash
docker build -f Dockerfile.query -t kg-query .
docker run -p 8000:8000 --env-file .env kg-query
```

## Generating a Plugin

Use `scripts/generate_plugin.py` to create a ready-to-distribute plugin
with a specific server URL pre-configured:

```bash
# Cowork plugin (default)
python scripts/generate_plugin.py --url https://my-server.up.railway.app/mcp

# Cowork plugin with baked-in token
python scripts/generate_plugin.py --url https://my-server.up.railway.app/mcp --token secret123

# OpenClaw configuration
python scripts/generate_plugin.py --url https://my-server.up.railway.app/mcp --platform openclaw

# Both platforms at once
python scripts/generate_plugin.py --url https://my-server.up.railway.app/mcp --platform all

# Custom output directory
python scripts/generate_plugin.py --url https://my-server.up.railway.app/mcp --output dist/my-plugin
```

The generated Cowork plugin directory can be zipped and sent to end users.
The generated OpenClaw configuration contains an `openclaw.json.example`
to merge into the OpenClaw instance's config.

## Marketplace

The `marketplace/` directory contains a `marketplace.json` for Cowork
marketplace distribution. To use it:

1. Host the `plugins/` directory in a GitHub repo
2. In Cowork: Plugins > Add marketplace > paste the GitHub repo URL
3. Users can then browse and install `kg-query` from the marketplace

## End User Installation

1. Receive the plugin directory (zip or folder) from the developer
2. Open Cowork
3. Go to Plugins > "+" button
4. Select the plugin folder
5. Start querying: "What suppliers provide oak lumber?"
