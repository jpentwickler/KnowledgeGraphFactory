# KG-Query for OpenClaw (Remote)

Connect a cloud-hosted OpenClaw instance to a KG-Factory query server via HTTP.

## Prerequisites

- OpenClaw deployed on Railway (see [deployment guide](../../docs/guides/deploy_openclaw.md))
- KG-Query server deployed and accessible (see [Cowork deployment guide](../../docs/guides/deploy_cowork_plugin.md), Part 1)
- A bearer token matching one in the KG-Query server's `KG_AUTH_TOKENS`

## Installation

### 1. Configure mcp-adapter

Merge the contents of `openclaw.json.example` into your OpenClaw instance's
`openclaw.json` (at `$OPENCLAW_STATE_DIR/openclaw.json` or via the setup
wizard).

Replace `YOUR-KG-QUERY-URL` with your actual KG-Query server URL.

### 2. Set the bearer token

Add to your OpenClaw `.env` file (`$OPENCLAW_STATE_DIR/.env`):

```
KG_QUERY_TOKEN=your-token-here
```

### 3. Install the SKILL.md

Copy `skills/knowledge-graph/SKILL.md` to your OpenClaw workspace:

```
$OPENCLAW_WORKSPACE_DIR/skills/knowledge-graph/SKILL.md
```

On Railway this maps to `/data/workspace/skills/knowledge-graph/SKILL.md`.

### 4. Restart the gateway

Restart the OpenClaw gateway so it picks up the new mcp-adapter configuration
and skill file.

## Verify

Send a message via your connected channel (Telegram, WhatsApp, etc.):

```
What's in the knowledge graph?
```

OpenClaw should call `domain-kg_kg_graph_info` and return the graph schema.

## Sub-Agent Deep Research

For complex multi-query tasks, OpenClaw can spawn sub-agents restricted to
KG tools only. Add this to your agent configuration:

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
