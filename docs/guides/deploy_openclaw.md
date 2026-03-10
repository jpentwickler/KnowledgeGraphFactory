# Deploy & Use KG-Query with OpenClaw on Railway

A step-by-step guide to deploying OpenClaw on Railway, connecting it to your
KG-Query server, and querying your knowledge graph from messaging channels.

---

## Prerequisites

Before you start you need:

- A **KG-Query server already deployed** on Railway (or Fly.io / Cloud Run)
  with a working health check. Follow [Part 1 of the Cowork guide](deploy_cowork_plugin.md)
  if you haven't done this yet.
- A **bearer token** matching one in the KG-Query server's `KG_AUTH_TOKENS`
- A **Railway account** (for hosting OpenClaw)
- An account on at least one messaging channel: Telegram, WhatsApp, Slack, or
  Discord

---

## Part 1 -- Deploy OpenClaw on Railway

### Step 1: Deploy with the one-click template

Go to the [OpenClaw Railway template](https://railway.com/deploy/openclaw)
and click **Deploy**. Railway creates a new project with an OpenClaw container.

### Step 2: Attach a volume

In the Railway dashboard for your new service, add a **Volume** mounted at
`/data`. This stores OpenClaw's configuration and workspace persistently.

### Step 3: Set environment variables

In the Railway service settings, add these variables:

| Variable | Value | Required |
|----------|-------|----------|
| `SETUP_PASSWORD` | A password for the setup wizard | Yes |
| `PORT` | `8080` | Yes |
| `OPENCLAW_STATE_DIR` | `/data/.openclaw` | Recommended |
| `OPENCLAW_WORKSPACE_DIR` | `/data/workspace` | Recommended |

### Step 4: Enable HTTP Proxy

In the Railway service networking settings, enable **HTTP Proxy** on port
`8080`. Railway generates a public domain for your service.

### Step 5: Run the setup wizard

Open `https://<your-railway-domain>/setup` in your browser. Enter your setup
password and configure:

- **LLM provider** (Claude, GPT-4, or other)
- **Messaging channel** (Telegram bot token, WhatsApp credentials, etc.)

After completing setup, OpenClaw starts the gateway automatically.

---

## Part 2 -- Connect to the KG-Query Server

### Step 1: Install the mcp-adapter plugin

If `mcp-adapter` is not already installed, add it via the OpenClaw setup
wizard or CLI:

```bash
openclaw plugins install mcp-adapter
```

### Step 2: Configure HTTP transport

Edit your `openclaw.json` (at `$OPENCLAW_STATE_DIR/openclaw.json` or
`/data/.openclaw/openclaw.json` on Railway) and merge in the mcp-adapter
configuration:

```json
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
              "transport": "http",
              "url": "https://kg-query-production.up.railway.app/mcp",
              "headers": {
                "Authorization": "Bearer ${KG_QUERY_TOKEN}"
              }
            }
          ]
        }
      }
    }
  }
}
```

Replace the URL with your actual KG-Query server endpoint.

### Step 3: Set the bearer token

Add your KG-Query token to the OpenClaw `.env` file
(`$OPENCLAW_STATE_DIR/.env` or `/data/.openclaw/.env`):

```
KG_QUERY_TOKEN=your-token-here
```

The `${KG_QUERY_TOKEN}` placeholder in the config is resolved from this file
at runtime.

### Step 4: Install the SKILL.md

Copy the skill file into the OpenClaw workspace skills directory:

```
/data/workspace/skills/knowledge-graph/SKILL.md
```

You can find the source file at `skills/knowledge-graph/SKILL.md` in the
KG-Factory repository, or in `plugins/openclaw-remote/skills/knowledge-graph/`.

The SKILL.md teaches OpenClaw **when** to use the KG tools (domain questions)
and **when not to** (general knowledge questions).

### Step 5: Restart the gateway

Restart the OpenClaw service in Railway so it picks up the new plugin
configuration and skill file.

---

## Part 3 -- Verify Everything Works

### Quick smoke test

Send these messages via your connected channel (Telegram, WhatsApp, etc.):

1. **"What's in the knowledge graph?"**
   -- OpenClaw calls `domain-kg_kg_graph_info` and returns node labels,
   relationship types, and counts.

2. **"List all [your main entity type]"**
   -- OpenClaw calls `domain-kg_kg_query` with a cypher strategy.

3. **"What documents mention [an entity you know exists]?"**
   -- OpenClaw calls `domain-kg_kg_query` with a cross-layer or hybrid
   strategy.

### Verify skill activation

Ask a general question like "What is the weather?" -- OpenClaw should NOT
call any KG tools. The skill's selective injection only activates for
domain-specific questions.

---

## Part 4 -- Optional: Sub-Agent Deep Research

For complex research tasks that need multiple queries, OpenClaw can spawn
sub-agents restricted to KG tools only.

Add this to your agent configuration in `openclaw.json`:

```json
{
  "tools": {
    "subagents": {
      "tools": {
        "allow": ["domain-kg_kg_query", "domain-kg_kg_graph_info"],
        "deny": ["group:fs", "group:sessions", "exec"]
      }
    }
  }
}
```

Now when you ask complex questions like "Analyze supply chain risks based on
the knowledge graph", OpenClaw can spawn a sub-agent that makes a series of
KG queries and compiles a research report.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Tools not discovered | mcp-adapter not installed/enabled | Check `openclaw.json` has mcp-adapter entry with `enabled: true` |
| "Connection refused" | KG-Query server not running | Check KG-Query Railway dashboard; verify `/health` returns healthy |
| 401 Unauthorized | Token mismatch | Verify `KG_QUERY_TOKEN` in `.env` matches a `KG_AUTH_TOKENS` entry on the KG-Query server |
| Empty results | Wrong state file on KG-Query | Redeploy KG-Query with the correct `current_state.json` |
| Skill not activating | SKILL.md not in workspace | Verify file exists at `$OPENCLAW_WORKSPACE_DIR/skills/knowledge-graph/SKILL.md` |
| No messages from channel | Channel not connected | Check messaging channel config in OpenClaw setup wizard |

---

## Updating the Graph

When you rebuild your knowledge graph:

1. Copy the new `current_state.json` to the KG-Query server's `state/`
2. Redeploy the KG-Query server: `railway up` (in the KG-Query project)
3. No changes needed on the OpenClaw side -- it connects to the same URL

---

## Architecture

```
User (WhatsApp / Telegram / Slack / Discord)
    |
    v
OpenClaw (Railway)
    |  mcp-adapter (HTTP transport)
    v
KG-Query Server (Railway)
    |  query_builder.py strategies
    v
Neo4j AuraDB
```

Both Railway instances are independent. The KG-Query server is the same
instance that serves Cowork plugins -- adding OpenClaw as a consumer requires
no server-side changes.

---

## Reference

- [OpenClaw Railway Deployment](https://docs.openclaw.ai/install/railway)
- [OpenClaw MCP Adapter](https://github.com/androidStern-personal/openclaw-mcp-adapter)
- [OpenClaw Skills](https://docs.openclaw.ai/tools/skills)
- [Plugin README](../../plugins/README.md) -- all plugin variants
- [Architecture: Query Agent & OpenClaw](../architecture/08_query_agent_openclaw.md)
- [Architecture: Remote Query Distribution](../architecture/12_remote_query_distribution.md)
- [SKILL.md](../../skills/knowledge-graph/SKILL.md) -- what OpenClaw sees
