# Deploy & Use the KG-Query Plugin in Claude Cowork

A step-by-step guide to deploying the remote query server and installing the
Cowork plugin so end users can query your knowledge graph with zero technical
setup.

---

## Prerequisites

Before you start you need:

- A **built knowledge graph** in Neo4j (AuraDB or self-hosted)
- The KG-Factory repo cloned locally
- A `state/current_state.json` file from your most recent pipeline run
  (copy it from your project's `state/` directory into the repo root `state/`)
- Accounts / CLI tools for your chosen hosting platform (Railway recommended)

---

## Part 1 — Deploy the Remote Query Server

### Step 1: Copy your state file

The Docker image needs the pipeline state so the query server knows your graph
schema. Copy your project state into the repo root:

```bash
cp examples/furniture_supply_chain/state/current_state.json state/current_state.json
```

### Step 2: Install the Railway CLI

```bash
npm install -g @railway/cli
railway login
```

### Step 3: Create a Railway project

```bash
railway init
```

Choose "Empty project" when prompted.

### Step 4: Set environment variables

```bash
railway variables set NEO4J_URI=neo4j+s://xxxx.databases.neo4j.io
railway variables set NEO4J_USER=neo4j
railway variables set NEO4J_PASSWORD=your-password
railway variables set ANTHROPIC_API_KEY=sk-ant-xxx
railway variables set OPENAI_API_KEY=sk-xxx
```

If you want to protect the endpoint with bearer tokens:

```bash
railway variables set KG_AUTH_TOKENS=token-for-alice,token-for-bob
```

Each comma-separated value becomes a valid bearer token. If you skip this,
the server runs without authentication (fine for private networks / testing).

### Step 5: Deploy

```bash
railway up
```

Railway detects `Dockerfile.query` via `railway.json` and builds the image.
Wait for the deploy to complete — you will see a URL like:

```
https://kg-query-production.up.railway.app
```

### Step 6: Verify the health check

```bash
curl https://kg-query-production.up.railway.app/health
```

Expected response:

```json
{"status": "healthy", "neo4j": "connected"}
```

If you see `unhealthy`, double-check your `NEO4J_*` environment variables.

---

## Part 2 — Generate the Plugin

Use the included script to create a plugin folder pre-configured with your
server URL.

### Option A: Token as environment variable (recommended)

The end user sets `KG_QUERY_TOKEN` in their environment. Safer because the
token never lives in a file.

```bash
python scripts/generate_plugin.py \
  --url https://kg-query-production.up.railway.app/mcp
```

### Option B: Baked-in token (zero-config for the user)

The token is written directly into `.mcp.json`. Convenient for internal teams
where credential rotation is not a concern.

```bash
python scripts/generate_plugin.py \
  --url https://kg-query-production.up.railway.app/mcp \
  --token token-for-alice
```

### Option C: Custom output path

```bash
python scripts/generate_plugin.py \
  --url https://kg-query-production.up.railway.app/mcp \
  --output dist/alice-plugin
```

The script creates:

```
dist/kg-query-plugin/
├── .claude-plugin/
│   └── plugin.json
├── .mcp.json
└── skills/
    └── knowledge-graph/
        └── SKILL.md
```

---

## Part 3 — Install the Plugin in Cowork

### For the developer distributing the plugin

1. Zip the generated plugin folder
2. Send the zip to the end user along with their token (if using Option A)

### For the end user receiving the plugin

#### Step 1: Unzip the plugin

Unzip the folder to any location on your computer (e.g. Desktop, Documents).

#### Step 2: Set your token (Option A only)

If the developer gave you a token separately, set it as an environment variable:

**macOS / Linux:**
```bash
export KG_QUERY_TOKEN=your-token-here
```

Add the line to your `~/.zshrc` or `~/.bashrc` to make it permanent.

**Windows (PowerShell):**
```powershell
[System.Environment]::SetEnvironmentVariable("KG_QUERY_TOKEN", "your-token-here", "User")
```

Restart Cowork after setting the variable.

#### Step 3: Install in Cowork

1. Open **Cowork**
2. Open the **Plugins** panel (sidebar or menu)
3. Click the **"+"** button
4. Browse to and select the unzipped plugin folder
5. Cowork confirms the plugin is installed

#### Step 4: Start querying

Type natural language questions in the chat:

```
What suppliers provide oak lumber?
```

```
Show me all products with defect rates above 5%
```

```
Which documents mention quality certifications?
```

Claude will automatically use the `kg_query` tool when your question is about
the knowledge graph.

---

## Part 4 — Verify Everything Works

### Quick smoke test

After installing the plugin, try this sequence in Cowork:

1. **"What's in the knowledge graph?"**
   — Claude calls `kg_graph_info()` and shows node labels, relationship types,
   and counts.

2. **"List all [your main entity type]"**
   — Claude calls `kg_query` with a cypher strategy.

3. **"What documents mention [an entity you know exists]?"**
   — Claude calls `kg_query` with a cross-layer or hybrid strategy.

If any query fails, check:
- The server health endpoint returns `healthy`
- The token matches one of the values in `KG_AUTH_TOKENS`
- The `KG_QUERY_TOKEN` env var is set (if using placeholder mode)

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Connection refused" | Server not running | Check Railway dashboard for deploy status |
| 401 Unauthorized | Token mismatch | Verify token matches a `KG_AUTH_TOKENS` entry |
| "unhealthy" on /health | Neo4j unreachable | Check `NEO4J_URI` and that AuraDB instance is running |
| Empty results | Wrong state file | Redeploy with the correct `current_state.json` |
| Plugin not appearing | Folder structure wrong | Ensure `.claude-plugin/plugin.json` exists at the root |
| "Tool not found" | SKILL.md missing | Verify `skills/knowledge-graph/SKILL.md` is in the plugin |

---

## Alternative: Fly.io Deployment

If you prefer Fly.io over Railway:

```bash
fly launch --dockerfile Dockerfile.query
fly secrets set NEO4J_URI=neo4j+s://xxx \
               NEO4J_USER=neo4j \
               NEO4J_PASSWORD=xxx \
               ANTHROPIC_API_KEY=sk-ant-xxx \
               OPENAI_API_KEY=sk-xxx \
               KG_AUTH_TOKENS=token1,token2
fly deploy
```

Your MCP endpoint will be at `https://kg-query.fly.dev/mcp`.

---

## Alternative: Local Plugin (for developers)

If you prefer running the query server locally instead of deploying it:

1. Use `plugins/cowork-local/` instead of generating a remote plugin
2. Set the required environment variables on your machine
3. Install the plugin folder in Cowork — it runs the query server as a
   local subprocess via stdio

This is useful during development but requires Python and all dependencies
installed on the user's machine.

---

## Updating the Graph

When you rebuild your knowledge graph:

1. Copy the new `current_state.json` to `state/`
2. Redeploy: `railway up`
3. No changes needed on the user side — the plugin points to the same URL

---

## Reference

- [Plugin README](../../plugins/README.md) — plugin variants and structure
- [Architecture: Remote Query Distribution](../architecture/12_remote_query_distribution.md) — design decisions
- [SKILL.md](../../skills/knowledge-graph/SKILL.md) — what Claude sees when using the plugin
