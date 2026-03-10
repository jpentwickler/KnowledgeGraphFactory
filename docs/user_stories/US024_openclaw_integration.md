# US024: OpenClaw Cloud Integration

## User Story

**As a** KG-Factory Developer
**I want** to connect a cloud-hosted OpenClaw instance to the remote KG-Query server via HTTP MCP transport
**So that** end users can query the knowledge graph from messaging channels (WhatsApp, Telegram, Slack, Discord) without installing anything locally

## Story Points: 3

## Status: Not Started

## Context

US021 deployed the query server as a remote HTTP service. US022 packaged a
Cowork plugin that connects to it. This story completes the second deployment
target: **OpenClaw** — an open-source headless AI assistant that runs as a
cloud daemon and connects to messaging channels.

OpenClaw can be deployed on Railway using a one-click template. The
`mcp-adapter` plugin supports HTTP transport, so OpenClaw connects to the
same KG-Query server instance that Cowork uses. No local installation of
OpenClaw or the query server is needed — the entire stack runs in the cloud.

```
User (WhatsApp / Telegram / Slack / Discord)
    |
    v
OpenClaw (Railway instance 1)
    |  HTTP/MCP (mcp-adapter)
    v
KG-Query Server (Railway instance 2 -- already deployed, US021/US022)
    |
    v
Neo4j AuraDB
```

See `docs/architecture/08_query_agent_openclaw.md` for the full design.

## Acceptance Criteria

### OpenClaw MCP Adapter Configuration (HTTP Transport)

- [ ] Configuration snippet for `openclaw.json` using `mcp-adapter` with HTTP transport:
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
                "url": "https://<KG_QUERY_URL>/mcp",
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
- [ ] `${KG_QUERY_TOKEN}` resolved from `~/.openclaw/.env` at runtime
- [ ] Tool prefix produces `domain-kg_kg_query` and `domain-kg_kg_graph_info`
- [ ] Configuration tested: OpenClaw discovers both tools on gateway startup

### SKILL.md Installation

- [ ] Existing `skills/knowledge-graph/SKILL.md` reused as-is (no OpenClaw-specific fork)
- [ ] SKILL.md already contains OpenClaw metadata in frontmatter:
  ```yaml
  metadata: {"openclaw":{"emoji":"graph","requires":{"env":["NEO4J_URI","ANTHROPIC_API_KEY","OPENAI_API_KEY"]}}}
  ```
- [ ] Skill installed to OpenClaw workspace: `$OPENCLAW_WORKSPACE_DIR/skills/knowledge-graph/SKILL.md`
- [ ] OpenClaw's selective injection activates the skill when user asks domain questions
- [ ] Skill does NOT activate for general knowledge questions

### Sub-Agent Configuration

- [ ] Tool restriction profile for deep research sub-agents documented:
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
- [ ] Sub-agents restricted to KG tools only (no filesystem, exec, or session spawning)

### Plugin Directory

- [ ] New directory: `plugins/openclaw-remote/`
- [ ] `openclaw.json.example` — mcp-adapter config snippet to merge into user's `openclaw.json`
- [ ] `skills/knowledge-graph/SKILL.md` — copy of the shared skill file
- [ ] `README.md` — installation instructions for OpenClaw on Railway

### Plugin Generation Script

- [ ] `scripts/generate_plugin.py` extended with `--platform` parameter:
  - `--platform cowork` (default, current behavior)
  - `--platform openclaw` generates `openclaw.json.example` instead of `.mcp.json` + `.claude-plugin/`
  - `--platform all` generates both
- [ ] OpenClaw output includes:
  - `openclaw.json.example` with the URL and token pre-configured
  - `skills/knowledge-graph/SKILL.md`
  - `README.md` with installation steps
- [ ] Example usage:
  ```bash
  python scripts/generate_plugin.py \
    --url https://kg-query-production.up.railway.app/mcp \
    --token my-token \
    --platform openclaw \
    --output dist/kg-query-openclaw
  ```

### Documentation

- [ ] `docs/guides/deploy_openclaw.md` — step-by-step deployment guide covering:
  - Deploy OpenClaw on Railway (one-click template)
  - Configure mcp-adapter for HTTP transport to KG-Query server
  - Install SKILL.md in the workspace
  - Connect a messaging channel (Telegram/WhatsApp)
  - Verify end-to-end query flow
- [ ] `plugins/README.md` updated with OpenClaw variant
- [ ] `docs/guides/README.md` updated with link to OpenClaw guide
- [ ] `docs/architecture/08_query_agent_openclaw.md` updated:
  - OpenClaw integration section rewritten for cloud-hosted (Railway) deployment
  - Stdio transport replaced with HTTP transport in all examples
  - Data flow examples updated for cloud architecture
- [ ] `docs/architecture/12_remote_query_distribution.md` updated:
  - OpenClaw added as second consumer alongside Cowork
  - Architecture diagram updated to show both platforms
- [ ] `docs/user_stories/README.md` updated with US024 in story index

### End-to-End Verification

- [ ] OpenClaw deployed on Railway (one-click template)
- [ ] mcp-adapter configured with HTTP transport pointing to KG-Query Railway URL
- [ ] SKILL.md installed in workspace skills directory
- [ ] `kg_graph_info()` returns graph schema via remote server
- [ ] `kg_query(question)` returns answer via remote server
- [ ] Auth token validation works (invalid token rejected by KG-Query server)
- [ ] Messaging channel connected (at least one: Telegram, WhatsApp, Slack, or Discord)
- [ ] User sends message via channel, receives KG answer

## Definition of Done

- [ ] OpenClaw configuration snippet created and tested
- [ ] Plugin directory `plugins/openclaw-remote/` created
- [ ] `generate_plugin.py` extended with `--platform openclaw` support
- [ ] Deployment guide complete (`docs/guides/deploy_openclaw.md`)
- [ ] Architecture docs updated (08, 12)
- [ ] `plugins/README.md` updated
- [ ] End-to-end verification: Railway OpenClaw -> HTTP MCP -> Railway KG-Query -> Neo4j -> answer via messaging channel
- [ ] All existing tests pass (no regressions)
- [ ] Code reviewed

## Technical Notes

### Architecture

```
                          Railway
                +--------------------------+
                |                          |
                |  OpenClaw Instance       |
                |  +-------------------+   |
                |  | Gateway           |   |
                |  |   |               |   |
                |  |   +-- mcp-adapter |   |
                |  |   |   (HTTP)  ----+---+---> KG-Query Instance
                |  |   |               |   |     (Railway, US021/US022)
                |  |   +-- SKILL.md    |   |         |
                |  |       (selective   |   |         v
                |  |        injection)  |   |     Neo4j AuraDB
                |  +-------------------+   |
                |          |               |
                +----------+---------------+
                           |
              +------------+------------+
              |            |            |
          WhatsApp    Telegram     Slack/Discord
              |            |            |
           End Users    End Users    End Users
```

### OpenClaw Configuration Merge

The `openclaw.json.example` is a **fragment** to merge into the user's existing
`openclaw.json`. OpenClaw's config is a single file, not a plugin directory like
Cowork. The user copies the `plugins.entries.mcp-adapter` section.

### SKILL.md Reuse

The same `SKILL.md` works for both Cowork and OpenClaw because:
- Cowork uses progressive disclosure (loads metadata first, full content when relevant)
- OpenClaw uses selective injection (loads based on `description` field match)
- Both read YAML frontmatter, both support `metadata.openclaw`
- Tool names (`kg_query`, `kg_graph_info`) are identical across platforms

### Environment Variables on Railway (OpenClaw instance)

| Variable | Where | Purpose |
|----------|-------|---------|
| `SETUP_PASSWORD` | Railway env | Setup wizard access |
| `PORT=8080` | Railway env | HTTP proxy port |
| `OPENCLAW_STATE_DIR=/data/.openclaw` | Railway env | Persistent state |
| `OPENCLAW_WORKSPACE_DIR=/data/workspace` | Railway env | Workspace + skills |
| `KG_QUERY_TOKEN` | `~/.openclaw/.env` | Bearer token for KG-Query server |

### Skill Installation on Railway

On a Railway-deployed OpenClaw, skills go to:
```
$OPENCLAW_WORKSPACE_DIR/skills/knowledge-graph/SKILL.md
```

Which resolves to:
```
/data/workspace/skills/knowledge-graph/SKILL.md
```

Install via the setup wizard or by copying the file into the volume.

### Plugin Generation Script Changes

```python
# New parameter
parser.add_argument(
    "--platform",
    choices=["cowork", "openclaw", "all"],
    default="cowork",
    help="Target platform (default: cowork)",
)

# OpenClaw output generates:
# - openclaw.json.example (mcp-adapter config)
# - skills/knowledge-graph/SKILL.md
# - README.md (installation instructions)
```

### Files to Create

```
plugins/openclaw-remote/                      # NEW: OpenClaw config directory
  openclaw.json.example                       # mcp-adapter config snippet
  skills/knowledge-graph/SKILL.md             # Copied from source
  README.md                                   # Installation instructions

docs/guides/deploy_openclaw.md                # NEW: Deployment guide
docs/user_stories/US024_openclaw_integration.md  # NEW: This user story
```

### Files to Modify

```
scripts/generate_plugin.py                    # ADD: --platform openclaw support
plugins/README.md                             # ADD: OpenClaw section
docs/guides/README.md                         # ADD: Link to OpenClaw guide
docs/user_stories/README.md                   # ADD: US024 to index
docs/architecture/08_query_agent_openclaw.md  # UPDATE: Cloud-hosted OpenClaw
docs/architecture/12_remote_query_distribution.md  # ADD: OpenClaw as consumer
```

### Files NOT Modified

```
mcp_server/query_server.py                   # Already supports HTTP + auth
Dockerfile.query                              # KG-Query already containerized
skills/knowledge-graph/SKILL.md              # Source of truth, reused as-is
railway.json                                  # KG-Query deployment config unchanged
```

## Dependencies

- **US021** (Remote Query Server) — KG-Query must be deployed and accessible via HTTP
- **US022** (Plugin Distribution) — Cowork plugin and deployment infrastructure
- Railway account (for OpenClaw deployment)
- Neo4j AuraDB instance (accessible from Railway)
- At least one messaging channel account (Telegram, WhatsApp, etc.)

## Out of Scope

- Local OpenClaw installation (stdio transport) — cloud-only deployment
- OAuth 2.1 authentication (Bearer token sufficient for MVP)
- Multi-tenant KG-Query server (single-tenant per architecture decision)
- Custom OpenClaw agent definitions (uses default main agent)
- LLM provider configuration (OpenClaw default provider is sufficient)
- OpenClaw marketplace / ClawHub skill publishing (future)
- Automated CI/CD for OpenClaw deployment (manual deploy for now)

## References

- [Deploy on Railway - OpenClaw](https://docs.openclaw.ai/install/railway)
- [OpenClaw MCP Adapter](https://github.com/androidStern-personal/openclaw-mcp-adapter)
- [OpenClaw Skills](https://docs.openclaw.ai/tools/skills)
- [OpenClaw Railway Templates](https://github.com/codetitlan/openclaw-railway-template)
