# US022: Plug-and-Play Cowork Plugin Distribution

## User Story

**As a** KG-Factory Developer
**I want** to deploy the remote query server to a cloud platform and package a Cowork plugin that points to it
**So that** non-developer end users can install the plugin and query a knowledge graph without any technical setup

## Story Points: 3

## Status: Not Started

## Context

US021 makes the query server deployable as a remote HTTP service. This story
completes the distribution chain: deploy the server, package the Cowork plugin,
and optionally set up a marketplace for discovery.

The end user experience after this story:
1. Open Cowork
2. Install the plugin (upload folder or install from marketplace)
3. Start querying: "What suppliers provide oak lumber?"

No Python. No API keys. No JSON editing. No terminal.

See `docs/architecture/12_remote_query_distribution.md` for the full design.

## Acceptance Criteria

### Cloud Deployment Configuration

- [ ] Deployment config file for at least one cloud platform (Railway, Fly.io, or Cloud Run)
- [ ] Config specifies: Docker image source, port (8000), health check endpoint (`/health`)
- [ ] Environment variables documented: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `KG_AUTH_TOKENS`
- [ ] State file strategy documented: volume mount for dynamic state, or baked into image for static deployments
- [ ] Deployment produces a public HTTPS URL (e.g., `https://kg-query-xxx.up.railway.app/mcp`)
- [ ] Deployed server passes health check: `curl https://<url>/health` returns `{"status": "healthy"}`
- [ ] Deployed server responds to MCP tool calls over Streamable HTTP

#### Railway (primary)

- [ ] `railway.json` or `Procfile` in project root
- [ ] Dockerfile reference points to `Dockerfile.query` (from US021)
- [ ] Documentation: step-by-step deploy commands (`railway login`, `railway init`, `railway variables set`, `railway up`)

#### Alternative Configs (at least one)

- [ ] `fly.toml` for Fly.io OR Cloud Run deploy command documented
- [ ] Platform-specific health check configuration

### Cowork Plugin (Remote)

- [ ] New plugin directory: `plugins/cowork-remote/` (separate from existing local plugin)
- [ ] `.claude-plugin/plugin.json` with updated manifest (current format, no `claude_plugin_version`):
  ```json
  {
    "name": "kg-query",
    "version": "1.0.0",
    "description": "Query knowledge graphs built with KG-Factory",
    "author": {
      "name": "KG-Factory"
    },
    "keywords": ["knowledge-graph", "neo4j", "query"]
  }
  ```
- [ ] `.mcp.json` using HTTP transport pointing to remote server:
  ```json
  {
    "mcpServers": {
      "domain-kg": {
        "type": "http",
        "url": "https://<deployed-url>/mcp",
        "headers": {
          "Authorization": "Bearer ${KG_QUERY_TOKEN}"
        }
      }
    }
  }
  ```
- [ ] `skills/knowledge-graph/SKILL.md` — reuse existing skill file (copy, not symlink for portability)
- [ ] SKILL.md references `kg_query` and `kg_graph_info` tools (same as existing)
- [ ] Plugin directory is self-contained — no references to files outside the directory
- [ ] Plugin uploads successfully in Cowork via Plugins > "+" > select directory
- [ ] After install, `kg_query` and `kg_graph_info` tools are discoverable in Cowork

### Plugin Generation Script

- [ ] New script: `scripts/generate_plugin.py` (or shell script)
- [ ] Takes parameters: `--url` (server URL), `--token` (optional auth token), `--output` (output directory)
- [ ] Generates a ready-to-upload plugin directory with the URL and token pre-configured
- [ ] If `--token` is provided, bakes it into `.mcp.json` headers (zero-config for internal use)
- [ ] If `--token` is omitted, uses `${KG_QUERY_TOKEN}` placeholder (user sets env var)
- [ ] Example usage:
  ```bash
  python scripts/generate_plugin.py \
    --url https://kg-query-production.up.railway.app/mcp \
    --token my-secret-token \
    --output dist/kg-query-plugin
  ```
- [ ] Generated plugin passes the same validation as hand-crafted plugin

### Marketplace (Optional but Recommended)

- [ ] `marketplace.json` file created (can live in KG-Factory repo or separate repo)
- [ ] Format follows Cowork marketplace spec:
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
- [ ] Marketplace installable in Cowork via Plugins > Add marketplace > paste repo URL
- [ ] Plugin appears in the "Personal" tab after marketplace is added

### Existing Local Plugin Update

- [ ] Existing `plugins/cowork/` renamed or kept as `plugins/cowork-local/` for clarity
- [ ] `.claude-plugin/plugin.json` updated to current manifest format (remove `claude_plugin_version`)
- [ ] Hardcoded credentials removed from `.mcp.json` — replaced with `${VAR}` placeholders
- [ ] README added explaining this is the local (stdio) variant for developers

### Documentation

- [ ] `plugins/README.md` explaining:
  - Difference between `cowork-local/` (developers, stdio) and `cowork-remote/` (end users, HTTP)
  - How to deploy the remote server (reference US021 + deployment configs)
  - How to generate a plugin for a specific deployment
  - How to set up the marketplace
  - End user installation instructions (with screenshots if possible)
- [ ] `docs/architecture/12_remote_query_distribution.md` updated with actual deployment URL pattern and final plugin structure

### End-to-End Verification

- [ ] Server deployed to at least one cloud platform
- [ ] Health check passes from external network
- [ ] Generated plugin installs in Cowork
- [ ] `kg_graph_info()` returns graph schema via remote server
- [ ] `kg_query(question)` returns answer via remote server
- [ ] Auth token validation works (invalid token rejected)
- [ ] Full round-trip latency documented (expected: 2-8s per query depending on strategy)

## Definition of Done

- [ ] Cloud deployment config files created and tested
- [ ] Remote Cowork plugin directory created and validated
- [ ] Plugin generation script working
- [ ] Marketplace JSON created
- [ ] Existing local plugin cleaned up (no hardcoded credentials)
- [ ] Documentation complete (`plugins/README.md`)
- [ ] End-to-end verification: deploy → generate plugin → install in Cowork → query
- [ ] All existing tests pass (no regressions)
- [ ] Code reviewed

## Technical Notes

### Plugin Directory Structure

```
plugins/
├── README.md                          # NEW: explains both variants
├── cowork-local/                      # RENAMED from cowork/ (developer variant)
│   ├── .claude-plugin/plugin.json     # Updated manifest format
│   ├── .mcp.json                      # ${VAR} placeholders, no hardcoded creds
│   └── skills/knowledge-graph/SKILL.md
├── cowork-remote/                     # NEW (end-user variant)
│   ├── .claude-plugin/plugin.json
│   ├── .mcp.json                      # type: http, URL to remote server
│   └── skills/knowledge-graph/SKILL.md
└── marketplace/                       # NEW (optional)
    └── .claude-plugin/marketplace.json
```

### Plugin Generation Script

```python
#!/usr/bin/env python3
"""Generate a Cowork plugin pre-configured for a specific deployment."""

import argparse
import json
import os
import shutil

def generate_plugin(url: str, token: str | None, output: str):
    """Generate a ready-to-upload Cowork plugin directory."""
    os.makedirs(os.path.join(output, ".claude-plugin"), exist_ok=True)
    os.makedirs(os.path.join(output, "skills", "knowledge-graph"), exist_ok=True)

    # plugin.json
    plugin_json = {
        "name": "kg-query",
        "version": "1.0.0",
        "description": "Query knowledge graphs built with KG-Factory",
        "author": {"name": "KG-Factory"},
        "keywords": ["knowledge-graph", "neo4j", "query"],
    }
    with open(os.path.join(output, ".claude-plugin", "plugin.json"), "w") as f:
        json.dump(plugin_json, f, indent=2)

    # .mcp.json
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        headers["Authorization"] = "Bearer ${KG_QUERY_TOKEN}"

    mcp_json = {
        "mcpServers": {
            "domain-kg": {
                "type": "http",
                "url": url,
                "headers": headers,
            }
        }
    }
    with open(os.path.join(output, ".mcp.json"), "w") as f:
        json.dump(mcp_json, f, indent=2)

    # Copy SKILL.md from project
    skill_src = os.path.join(
        os.path.dirname(__file__), "..", "skills",
        "knowledge-graph", "SKILL.md"
    )
    skill_dst = os.path.join(output, "skills", "knowledge-graph", "SKILL.md")
    shutil.copy2(skill_src, skill_dst)

    print(f"Plugin generated at: {output}")
    if token:
        print("Auth token baked in (zero-config for end user)")
    else:
        print("User must set KG_QUERY_TOKEN env var")
```

### Deployment Configs

**railway.json**:
```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": {
    "dockerfilePath": "Dockerfile.query"
  },
  "deploy": {
    "healthcheckPath": "/health",
    "healthcheckTimeout": 30,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

**fly.toml**:
```toml
app = "kg-query"
primary_region = "ams"

[build]
  dockerfile = "Dockerfile.query"

[http_service]
  internal_port = 8000
  force_https = true

  [[http_service.checks]]
    grace_period = "10s"
    interval = "30s"
    method = "GET"
    path = "/health"
    timeout = "5s"
```

### End User Journey (Final)

```
Developer:
  1. Build knowledge graph (existing pipeline)
  2. Deploy: railway up (or fly deploy)
  3. Generate plugin: python scripts/generate_plugin.py --url https://... --token ...
  4. Send plugin folder to end user (zip, email, share drive)

End User:
  1. Unzip plugin folder
  2. Open Cowork → Plugins → "+" → select folder
  3. Ask: "What suppliers provide oak lumber?"
  → Done. No Python, no API keys, no terminal.
```

### Files to Create

```
plugins/cowork-remote/                       # NEW: remote plugin directory
  .claude-plugin/plugin.json
  .mcp.json
  skills/knowledge-graph/SKILL.md

plugins/marketplace/                         # NEW: marketplace config
  .claude-plugin/marketplace.json

plugins/README.md                            # NEW: plugin documentation

scripts/generate_plugin.py                   # NEW: plugin generation script

railway.json                                 # NEW: Railway deployment config
fly.toml                                     # NEW: Fly.io deployment config (alternative)
```

### Files to Modify

```
plugins/cowork/                              # RENAME to plugins/cowork-local/
  .claude-plugin/plugin.json                 # UPDATE: remove claude_plugin_version
  .mcp.json                                  # UPDATE: remove hardcoded credentials

docs/architecture/12_remote_query_distribution.md  # UPDATE: implementation details
```

### Files NOT Modified

```
mcp_server/query_server.py                   # Modified in US021, not here
mcp_server/server.py                         # UNCHANGED: construction server
skills/knowledge-graph/SKILL.md              # UNCHANGED: source of truth
skills/knowledge-graph-builder/SKILL.md      # UNCHANGED
```

## Dependencies

- **US021** (Remote Query Server) — the server must be deployable before packaging the plugin
- US013 (Query Infrastructure) — query strategies
- US015 (Query Agent) — query_server.py baseline
- Cloud platform account (Railway, Fly.io, or Cloud Run)
- Neo4j instance accessible from the cloud (e.g., Neo4j AuraDB)

## Out of Scope

- OAuth 2.1 authentication (Bearer token sufficient for MVP)
- Multi-tenant server (single-tenant per architecture decision)
- Automated CI/CD pipeline for deployment (manual deploy for now)
- Plugin auto-update mechanism (manual re-upload for now)
- Claude Desktop Extension (DXT) packaging (different product, different format)
- Plugin store / public marketplace submission (future)
- Custom domain for deployed server (platform default URL is fine)
- Monitoring/alerting setup (future ops concern)
