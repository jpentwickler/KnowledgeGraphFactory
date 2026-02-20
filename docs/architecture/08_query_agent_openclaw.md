# Standalone Query Agent & Platform Integration — Design

> **Status**: Proposal
> **Depends on**: US013 (Query Infrastructure), US014 (CQ Evaluation)
> **Related**: `07_kg_query_mcp_server.md` (existing MCP query tools)
> **Deployment targets**: Claude Cowork (plugin), OpenClaw (MCP + skill)

---

## Motivation

The existing `kg_query` MCP tool (US013) is a **one-shot retrieval tool** designed for Claude Code. It selects a single strategy, executes it, and returns raw evidence. This works well during knowledge graph development, where Claude Code orchestrates the workflow.

However, once a knowledge graph is built, it needs a **conversational interface** for end users — one that can handle follow-up questions, combine evidence from multiple retrievers, and synthesize natural language answers. This is the Query Agent.

The Query Agent ships alongside the built knowledge graph to **any MCP-compatible platform** — currently **Claude Cowork** (Anthropic's desktop agent) and **OpenClaw** (open-source personal assistant). Both give a general-purpose assistant deep access to domain-specific knowledge captured in the graph.

---

## Architecture Overview

Three components serve different purposes in different environments:

```
DEVELOPMENT ENVIRONMENT                    DEPLOYMENT ENVIRONMENT(S)
(Developer + Claude Code)                  (End User + Cowork or OpenClaw)

┌──────────────────────────────┐           ┌──────────────────────────────┐
│  Claude Code                 │           │  Claude Cowork     OR       │
│                              │           │  OpenClaw Gateway            │
│  MCP Client                  │           │                              │
│  ├── kg_user_intent          │           │  MCP Client                  │
│  ├── kg_file_suggestion      │           │  ├── kg_chat                 │
│  ├── kg_schema_proposal      │           │  └── kg_graph_info           │
│  ├── kg_build_graph          │           │                              │
│  ├── kg_query (one-shot)     │           │  SKILL.md (usage guidance)   │
│  ├── kg_evaluate_cqs         │           │  Sub-agents (deep research)  │
│  └── ...12 tools total       │           │                              │
│                              │           │                              │
│  Construction MCP Server     │           │  Query MCP Server            │
│  mcp_server/server.py        │           │  mcp_server/query_server.py  │
└──────────────┬───────────────┘           └──────────────┬───────────────┘
               │                                          │
               │  shares retriever functions               │
               └──────────────┬───────────────────────────┘
                              │
                              ▼
               ┌──────────────────────────────┐
               │  pipelines/query_builder.py   │
               │                               │
               │  _execute_schema_query()      │
               │  _execute_cypher()            │
               │  _execute_vector_search()     │
               │  _execute_hybrid_search()     │
               │  _execute_cross_layer_trav()  │
               └──────────────┬────────────────┘
                              │
                              ▼
                        ┌───────────┐
                        │  Neo4j    │
                        │  (KG)     │
                        └───────────┘
```

**Key separation**:
- The **Construction MCP Server** (12 tools) stays with the developer. It can build, modify, and reset the graph.
- The **Query MCP Server** (2 tools) ships to Cowork or OpenClaw. It can only read the graph.
- Both import from the same `pipelines/query_builder.py`. Retriever improvements flow to all consumers automatically.

**Platform-agnostic design**: The Query MCP Server speaks standard MCP over stdio. It works with any MCP client — Claude Cowork, OpenClaw, Claude Code, or any future platform that supports MCP.

---

## The Query Agent

### Why an Agent, Not a Pipeline

The current `kg_query` is a pipeline:

```
question --> Claude (select strategy) --> execute --> return evidence
```

Two LLM calls (strategy selection + the MCP host synthesizing from evidence), no follow-up capability, no result evaluation.

The Query Agent is a conversational agent loop:

```
question --> Claude (IS the strategist) --> calls retriever tool -->
  sees results --> decides: enough? --> yes: synthesize answer
                                    --> no: try another tool, refine query
```

Claude doesn't need a separate LLM call to select a strategy. The agent's system prompt teaches Claude about the retrievers, and Claude calls the right tool directly. This is cheaper (one LLM context, not two) and more powerful (Claude reacts to results before responding).

### Agent Structure

Follows the established KG-Factory agent pattern (`run_agent_sync` + system prompt + tools + handlers):

```
agents/query_agent.py
├── SYSTEM_PROMPT        # Strategy knowledge, synthesis guidelines
├── TOOLS                # 5 tool schemas
├── TOOL_HANDLERS        # Handlers wrapping _execute_* functions
└── QueryAgent
    └── run()            # @traceable, calls run_agent_sync()
```

### Tools

Five tools, each wrapping an existing `_execute_*` function from `query_builder.py`. Named by **intent**, not implementation:

| Tool | Wraps | When Claude Should Call It |
|------|-------|---------------------------|
| `discover_graph` | `_execute_schema_query` + live Neo4j query | "What's in the graph?" / first call in a session |
| `search_text(query, top_k)` | `_execute_vector_search` | Broad content questions, thematic exploration |
| `search_keywords(query, top_k)` | `_execute_hybrid_search` | Questions with specific terms + semantic meaning |
| `search_entities(query, top_k)` | `_execute_cross_layer_traversal` | Questions linking text to domain entities |
| `run_cypher(query)` | `_execute_cypher` | Precise structural queries, counting, aggregation |

**Why intent-based names**: Claude reasons better with `search_entities` than `cross_layer_traversal`. The tool descriptions guide strategy selection without a separate classifier call.

### System Prompt Design

The system prompt replaces `_select_retrieval_strategy()` from US013. Instead of a separate LLM call returning JSON, the agent's prompt teaches Claude when to use each tool:

```
You are a Knowledge Graph Query Agent. You answer questions by querying
a knowledge graph that has two layers:

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
```

~250 tokens of system prompt vs a full 1024-token LLM call for strategy classification.

### Conversational Follow-Up

Follow-up resolution happens naturally through the agent's conversation history. No separate question-rewriting module is needed — Claude resolves references from context:

```
Turn 1: User asks "Which suppliers provide oak lumber?"
        Claude calls run_cypher → finds Supplier A, Supplier B
        Claude responds with synthesized answer

Turn 2: User asks "What about their delivery times?"
        Claude sees conversation history, resolves "their" = Supplier A, B
        Claude calls search_entities("delivery times Supplier A Supplier B")
        Claude synthesizes answer comparing both suppliers
```

This works because `run_agent_sync()` maintains the full conversation in its message loop. The Query Agent reuses this mechanism with rolling-window trimming for long sessions.

### State Dependency: Runtime Discovery

**Problem**: The current retrievers read `state` (from the construction pipeline) to get domain labels and entity types. When shipping to OpenClaw, the state JSON may be stale or missing.

**Solution**: The `discover_graph` tool queries Neo4j directly and caches results in runtime state:

```python
def handle_discover_graph(state: dict) -> dict:
    driver = state["_driver"]
    schema = _execute_schema_query(driver, state)

    # Query Neo4j for live labels (not from state file)
    with driver.session() as session:
        result = session.run("""
            MATCH (n)
            WHERE NOT any(l IN labels(n) WHERE l STARTS WITH '__')
              AND NOT any(l IN labels(n) WHERE l IN ['Chunk', 'Document'])
            RETURN DISTINCT [l IN labels(n)
                   WHERE NOT l STARTS WITH '__'] AS labels,
                   count(n) AS count
        """)
        discovered = [dict(r) for r in result]

    # Cache for search_entities to use
    state["_discovered_labels"] = [
        label for row in discovered for label in row["labels"]
    ]

    return {"status": "success", "schema": schema["answer"]}
```

The `search_entities` handler checks `state["_discovered_labels"]` first, falls back to `_get_domain_labels(state)`. This means:
- **With state file** (development/testing): rich context from construction plan
- **Without state file** (shipped to OpenClaw): discovers structure from Neo4j directly

---

## Query MCP Server

A separate, lightweight MCP server that ships alongside the built knowledge graph. Exposes only query capabilities — no construction, modification, or reset tools.

### File: `mcp_server/query_server.py`

Two tools:

```
kg_chat(message, session_id)     # Conversational query
kg_graph_info()                  # Quick schema check
```

### `kg_chat(message, session_id)`

The primary tool. Wraps the Query Agent with per-session conversation management.

```
Input:  {
    message: str,         # Natural language question or follow-up
    session_id: str       # Session identifier for conversation continuity
                          # (default: "default")
}

Output: {
    answer: str,          # Synthesized natural language answer
    sources: list[str],   # Source files referenced in evidence
    confidence: float,    # Overall confidence (0.0-1.0)
    strategies_used: list # Which retriever tools were called
}
```

**Session management** reuses the existing rolling-window pattern from `server.py`:
- `_serialize_conversation()` / `_trim_conversation()` per session
- 20-message window (configurable)
- Sessions stored in memory (or optionally persisted to disk)

**Driver lifecycle**: One driver created at server startup, shared across calls (unlike the construction server which creates per-call). The query server is long-lived and read-only, so connection pooling is safe.

### `kg_graph_info()`

Lightweight schema check. Returns labels, relationship types, node counts, and index status. No conversation state required. OpenClaw's agent calls this to decide whether the KG has relevant data before starting a `kg_chat` session.

### Why a Separate Server

| Concern | Construction Server | Query Server |
|---------|-------------------|--------------|
| **Security** | Can reset, rebuild, delete | Read-only |
| **Dependencies** | All 7 agent classes, pandas | Only QueryAgent, query_builder |
| **Deployment** | Developer environment | Alongside KG in production |
| **Tool count** | 12 tools | 2 tools |
| **Audience** | Developer via Claude Code | End user via OpenClaw |

Exposing construction tools (`kg_reset_state`, `kg_build_graph`) to OpenClaw's general-purpose agent would be a security risk. The query server is a restricted surface.

---

## Platform Integration

The Query MCP Server is platform-agnostic. It can be deployed to any MCP-compatible host. This document covers two deployment targets:

1. **Claude Cowork** — Anthropic's desktop agent (plugin-based, sandboxed)
2. **OpenClaw** — Open-source personal assistant (daemon-based, multi-channel)

### Platform Comparison

| Aspect | Claude Cowork | OpenClaw |
|--------|--------------|----------|
| **Type** | Desktop agent (Claude Desktop) | Headless daemon (Node.js) |
| **MCP format** | `.mcp.json` (same as Claude Code) | `openclaw.json` (mcp-adapter) |
| **Skill format** | `SKILL.md` (progressive disclosure) | `SKILL.md` (selective injection) |
| **Packaging** | Plugin (`.claude-plugin/plugin.json`) | Manual config |
| **Sub-agents** | Native (parallel spawning) | Native (`sessions_spawn`) |
| **Sandboxing** | Full Linux VM (VZVirtualMachine) | Tool-level allow/deny lists |
| **Chat channels** | None (desktop only) | WhatsApp, Telegram, Slack, Discord |
| **LLM** | Claude only | Any (Claude, GPT-4, Gemini, local) |
| **Status** | Research preview (Jan 2026) | Stable |
| **Cost** | Claude Pro $20/mo+ (includes Cowork) | Free (self-hosted) + LLM API costs |
| **Audience** | Knowledge workers (non-developers) | Power users, developers |
| **Deployment** | Desktop app required | Runs as background service |
| **Audit/compliance** | No audit logs (research preview) | Self-hosted, full control |

### When to Choose Which

- **Cowork**: Desktop users who already have Claude Desktop. Zero-install (just load the plugin). Best for individual knowledge workers exploring the KG interactively.
- **OpenClaw**: Teams needing multi-channel access (query the KG from Slack/WhatsApp). Headless deployment on servers. LLM flexibility. Best for always-on KG access across platforms.
- **Both**: The same MCP server powers both. Ship one plugin for Cowork and one skill for OpenClaw. Improvements flow to both automatically.

---

## Claude Cowork Integration

### Plugin Architecture

Cowork uses a plugin system that bundles MCP servers, skills, sub-agents, and commands into a single installable package. The KG Query plugin:

```
plugins/cowork/
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest
├── .mcp.json                    # MCP server connection (query_server.py)
└── skills/
    └── knowledge-graph/
        └── SKILL.md             # Same skill used by OpenClaw
```

### Plugin Manifest

```json
{
  "name": "kg-query",
  "version": "0.1.0",
  "description": "Query a domain knowledge graph built with KG-Factory. Provides conversational access to structured and unstructured data through semantic search, keyword matching, entity traversal, and Cypher queries.",
  "author": "KG-Factory",
  "homepage": "https://github.com/your-org/kg-factory",
  "claude_plugin_version": "1"
}
```

### MCP Configuration

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

### How It Works

1. User installs the plugin (drops folder into `~/.claude/plugins/` or loads via SDK)
2. Cowork reads `.claude-plugin/plugin.json` → registers the plugin
3. Cowork reads `.mcp.json` → spawns `query_server.py` as a child process
4. Cowork calls `listTools()` → discovers `kg_chat` and `kg_graph_info`
5. Cowork reads `skills/knowledge-graph/SKILL.md` → progressive disclosure:
   - Metadata loads always (~100 tokens): description drives relevance matching
   - Full instructions load when user asks a domain question (<5k tokens)
6. User asks a domain question → Cowork's Claude calls `kg_chat` → QueryAgent runs → answer returned

### Sub-Agent Deep Research

Cowork natively spawns sub-agents for complex tasks. No configuration needed — Cowork's Claude decides when to parallelize:

```
User: "Compare quality issues across all product categories in my knowledge graph"

Cowork's Claude:
  → Spawns sub-agent 1: "Use kg_chat to find quality issues for furniture"
  → Spawns sub-agent 2: "Use kg_chat to find quality issues for textiles"
  → Spawns sub-agent 3: "Use kg_chat to find quality issues for lighting"
  → Aggregates results → Synthesized comparison report
```

Each sub-agent gets its own context window and `session_id`, so QueryAgent maintains separate conversation state per sub-agent.

### Double-LLM Cost

Cowork's Claude orchestrates the session (LLM call 1), then `kg_chat` invokes the QueryAgent which makes its own Claude API calls (LLM call 2+). This is inherent to the MCP architecture — the host LLM and the tool's internal LLM are separate.

Mitigation:
- `kg_graph_info()` is cheap (no LLM call, just a Neo4j schema query). Cowork calls this first to check relevance.
- The QueryAgent uses `claude-sonnet-4-20250514` (fast, cheaper than Opus) for tool-calling reasoning.

---

## OpenClaw Integration

### Three Integration Tiers

OpenClaw provides three mechanisms for consuming external tools. They work together, not as alternatives:

```
┌──────────────────────────────────────────────────────────┐
│                     OpenClaw Gateway                      │
│                                                           │
│   Tier 1: MCP Connection        Tier 2: Skill            │
│   (transport layer)             (judgment layer)          │
│   ┌──────────────────┐         ┌──────────────────┐      │
│   │ mcp-adapter or   │         │ SKILL.md         │      │
│   │ native mcp.srv   │         │ "when to use     │      │
│   │                  │         │  the KG"         │      │
│   │ kg_chat          │         │                  │      │
│   │ kg_graph_info    │         │ Injected when    │      │
│   │                  │         │ question matches │      │
│   └────────┬─────────┘         └──────────────────┘      │
│            │                                              │
│   Tier 3: Sub-Agent                                      │
│   (deep research)                                        │
│   ┌──────────────────┐                                   │
│   │ Spawned for      │                                   │
│   │ complex multi-   │                                   │
│   │ query analysis   │                                   │
│   │ tasks            │                                   │
│   └──────────────────┘                                   │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

### Tier 1: MCP Connection (Transport)

Gives OpenClaw's agent access to `kg_chat` and `kg_graph_info` as callable tools.

**Option A — `mcp-adapter` plugin** (recommended, most stable):

```jsonc
// ~/.openclaw/openclaw.json
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

With `toolPrefix: true`, tools appear as `domain-kg_kg_chat` and `domain-kg_kg_graph_info`.

**Option B — Native `mcp.servers`** (per-agent, may still be maturing):

```jsonc
// ~/.openclaw/openclaw.json
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

**What happens at startup**: OpenClaw spawns `python -m mcp_server.query_server` as a child process, communicates over stdio (JSON-RPC 2.0), calls `listTools()` to discover `kg_chat` and `kg_graph_info` with their descriptions and JSON schemas, and registers them as first-class tools.

### Tier 2: Skill (Judgment)

MCP gives OpenClaw access to tools. A Skill teaches it **when** to use them and **how** to interpret results.

**File**: `~/.openclaw/skills/knowledge-graph/SKILL.md`

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

**How OpenClaw uses Skills**: OpenClaw loads SKILL.md files at startup. The `description` field drives **selective injection** — the skill content is only added to the system prompt when the user's message matches the description semantically. "What furniture has quality issues?" injects the knowledge-graph skill; "set a timer for 5 minutes" does not. This keeps the prompt lean.

### Tier 3: Sub-Agent (Deep Research)

For complex research tasks that require multiple queries, comparison, and synthesis — not just one question.

OpenClaw's main agent recognizes a complex KG task and spawns a sub-agent:

```
User: "Analyze our supply chain risks based on the knowledge graph"

Main agent calls sessions_spawn:
  task: "Analyze supply chain risks using the knowledge graph.
         Use kg_graph_info to understand the data, then use kg_chat
         to explore supplier dependencies, quality issues, and
         single-source risks. Compile a risk report with findings."
  label: "supply-chain-risk-analysis"
  runTimeoutSeconds: 300
```

The sub-agent runs in an isolated session with its own context window. It makes a series of `kg_chat` calls with a consistent `session_id`, compiles findings, and posts results back via the "announce step."

**Sub-agent tool restrictions**:

```jsonc
{
  "tools": {
    "subagents": {
      "tools": {
        "allow": [
          "domain-kg_kg_chat",
          "domain-kg_kg_graph_info"
        ],
        "deny": ["group:fs", "group:sessions", "exec"]
      }
    }
  }
}
```

This restricts the sub-agent to ONLY the KG tools — it cannot read files, run commands, or spawn its own sub-agents. It is a sandboxed KG researcher.

---

## Concrete Data Flow Examples

### Example A: Claude Cowork (Desktop)

```
1. User opens Claude Desktop, switches to Cowork tab.
   Types: "What did @home_chef say about the Stockholm chair?"

2. Cowork loads knowledge-graph skill (description matches domain question)

3. Cowork's Claude decides to call kg_chat:
   kg_chat(
     message="What did @home_chef say about the Stockholm chair?",
     session_id="cowork-session-42"
   )

4. Plugin's .mcp.json routes to query_server.py (child process)

5-9. Same as OpenClaw flow below (QueryAgent runs, synthesizes answer)

10. Cowork displays answer in the desktop UI
    User can follow up directly in the same session
```

### Example B: OpenClaw (WhatsApp)

End-to-end flow showing all layers:

```
1. User sends WhatsApp message to OpenClaw:
   "What did @home_chef say about the Stockholm chair?"

2. OpenClaw Gateway receives via WhatsApp channel plugin

3. Main agent processes the message:
   - Sees "knowledge-graph" skill is relevant (description match)
   - SKILL.md injected into system prompt
   - Agent decides to call kg_chat

4. Agent calls:
   kg_chat(
     message="What did @home_chef say about the Stockholm chair?",
     session_id="whatsapp-user-789"
   )

5. Query MCP Server receives the call:
   - Loads/creates session "whatsapp-user-789"
   - Pops conversation history for this session
   - Passes message + conversation to QueryAgent.run()

6. QueryAgent (Claude) processes:
   - System prompt describes 5 tools
   - Recognizes: specific @mention + product -> search_entities
   - Calls tool: search_entities("@home_chef Stockholm chair review")

7. Tool handler executes:
   - Calls _execute_cross_layer_traversal(driver, query, top_k=5, state)
   - HybridCypherRetriever: fulltext matches "@home_chef", vector matches
     semantics
   - FROM_CHUNK traversal finds entities
   - CORRESPONDS_TO links to Product:Stockholm
   - Returns 3 chunks with entity context

8. Claude sees results, synthesizes:
   "@home_chef posted two reviews about the Stockholm chair:
    - Praised the Scandinavian design and wood quality
    - Complained about assembly taking over 2 hours
    - Rated it 3/5 stars overall"

9. QueryAgent returns (response, state, conversation)

10. Query MCP Server:
    - Stores updated conversation for session "whatsapp-user-789"
    - Returns {answer, sources, confidence, strategies_used}

11. Main agent relays the answer to the user via WhatsApp
```

**Follow-up (same session)**:

```
12. User: "Did they review any other furniture?"

13. Same flow, same session_id
    -> QueryAgent sees conversation history
    -> Resolves "they" = @home_chef from turn context
    -> Calls search_entities("@home_chef reviews furniture")
    -> Synthesizes: "Yes, @home_chef also reviewed the Ektorp sofa..."
```

---

## Multi-Strategy Retrieval

### When Single Strategy Fails

The agent can try multiple tools sequentially when results are insufficient:

```
User: "What are the main quality concerns with our furniture?"

Claude thinks: Broad question about quality. Start with search_text.

Claude calls: search_text("quality concerns furniture")
Result: 5 chunks, confidence 0.5 -- some relevant but vague

Claude thinks: Results are partial. Let me also check entities.

Claude calls: search_entities("quality issues products customer reviews")
Result: 4 chunks with entity context -- QualityIssue linked to Product nodes

Claude synthesizes from BOTH result sets:
  "Based on customer reviews, the main quality concerns are:
   1. Stockholm chair: wobbling legs, fabric pilling
   2. Ektorp sofa: fabric wear after 6 months
   3. Poang chair: creaking noise

   The Stockholm chair has the most complaints (12 mentions across
   4 review documents)."
```

This is more powerful than RRF merging because Claude:
- Sees the actual results before deciding to try another tool
- Can reformulate the query based on what it learned
- Synthesizes intelligently rather than rank-fusing

### When to Combine vs When to Be Precise

The agent loop naturally handles this:
- "Reviews mentioning @home_chef" → single tool (`search_entities`), precise
- "Summarize all quality themes" → multiple tools, combine results
- "How many suppliers?" → single tool (`run_cypher`), precise

Claude decides based on result quality, not a predetermined merge strategy.

---

## What Ships vs What Stays

```
Stays with developer (KG-Factory dev environment):
├── mcp_server/server.py           # 12-tool construction server
├── agents/user_intent.py          # Construction agents
├── agents/file_suggestion.py
├── agents/schema_proposal.py
├── agents/schema_critic.py
├── agents/ner_extraction.py
├── agents/fact_extraction.py
├── agents/competency_questions.py
└── tests/

Ships with the knowledge graph (to Cowork and/or OpenClaw):
├── mcp_server/query_server.py     # 2-tool query server        (NEW)
├── agents/query_agent.py          # Conversational query agent  (NEW)
├── tools/query_agent_tools.py     # Tool schemas + handlers     (NEW)
├── pipelines/query_builder.py     # Retriever functions         (SHARED)
├── tools/query_tools.py           # Helper functions            (SHARED)
├── core/agent.py                  # Agent runner                (SHARED)
├── core/state.py                  # State utilities             (SHARED)
├── core/tools.py                  # Tool execution              (SHARED)
├── core/tracing.py                # Optional LangSmith          (SHARED)
├── utils/neo4j_utils.py           # Driver utilities            (SHARED)
├── state/current_state.json       # Built graph metadata        (OPTIONAL)
├── skills/
│   └── knowledge-graph/
│       └── SKILL.md               # Shared skill definition     (NEW)
└── plugins/
    └── cowork/                    # Cowork plugin packaging      (NEW)
        ├── .claude-plugin/
        │   └── plugin.json
        └── .mcp.json

Platform-specific configuration (not in repo, user creates):
├── Cowork:   Plugin installed to ~/.claude/plugins/ or loaded via SDK
└── OpenClaw: openclaw.json + ~/.openclaw/skills/ (see installation guide)
```

**SHARED** files are the same source files, not copies. If you improve `_execute_cross_layer_traversal`, the improvement flows to:
- `kg_query` (MCP tool, one-shot, for Claude Code)
- `kg_evaluate_cqs` (MCP tool, batch evaluation)
- `QueryAgent` (conversational, for Cowork and OpenClaw)

---

## Retriever Sharing Model

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
         +-- used by: QueryAgent       (conversational, OpenClaw)
```

---

## Project Structure (New Files)

```
kg-factory/
├── agents/
│   └── query_agent.py              # NEW: QueryAgent class
│
├── tools/
│   └── query_agent_tools.py        # NEW: Tool schemas + handlers
│
├── mcp_server/
│   ├── server.py                   # UNCHANGED: construction server
│   └── query_server.py             # NEW: query-only MCP server
│
├── skills/
│   └── knowledge-graph/
│       └── SKILL.md                # NEW: Shared skill (Cowork + OpenClaw)
│
├── plugins/
│   └── cowork/                     # NEW: Cowork plugin packaging
│       ├── .claude-plugin/
│       │   └── plugin.json         # Plugin manifest
│       └── .mcp.json               # MCP server connection
│
├── tests/
│   ├── unit/
│   │   └── test_query_agent.py     # NEW: unit tests
│   └── test_10_query_agent.py      # NEW: interactive test
│
├── pipelines/
│   └── query_builder.py            # UNCHANGED: shared retrievers
│
├── tools/
│   └── query_tools.py              # UNCHANGED: shared helpers
│
└── core/
    ├── agent.py                    # UNCHANGED: run_agent_sync
    ├── state.py                    # UNCHANGED: state utilities
    └── tracing.py                  # UNCHANGED: @traceable
```

---

## Architectural Decisions

### 1. Separate Query Server vs Extending Existing Server

**Decision**: Separate `mcp_server/query_server.py`
**Rationale**: Security (no construction/reset tools exposed to OpenClaw), minimal dependencies (no agent imports except QueryAgent), clear deployment boundary
**Alternative Rejected**: Adding `kg_chat` to existing `server.py` (exposes 12 tools including `kg_reset_state` to OpenClaw)

### 2. Agent with Tool Calls vs Pipeline with Strategy Selector

**Decision**: Query Agent uses Claude's own tool-calling to select and execute retrieval strategies
**Rationale**: Eliminates the separate `_select_retrieval_strategy()` LLM call, enables reactive multi-tool usage (try one, evaluate, try another), natural conversation without a question-rewriting module
**Alternative Rejected**: Keep pipeline pattern with separate strategy selection call (extra latency, no reactivity, no follow-up)

### 3. Intent-Based Tool Names vs Implementation-Based

**Decision**: `search_text`, `search_keywords`, `search_entities`, `run_cypher`, `discover_graph`
**Rationale**: Claude reasons better with semantic names; tool descriptions guide strategy selection without a classifier
**Alternative Rejected**: `vector_search`, `hybrid_search`, `cross_layer_traversal` (implementation details that don't help Claude decide)

### 4. Runtime Graph Discovery vs State File Dependency

**Decision**: `discover_graph` queries Neo4j directly, caches results in `state["_discovered_labels"]`; falls back to state file when available
**Rationale**: Works even if state JSON is stale or missing; the graph itself is the source of truth
**Alternative Rejected**: Require state file at runtime (fragile coupling to build artifacts)

### 5. Answer Synthesis in Agent vs Evidence Return

**Decision**: The Query Agent synthesizes natural language answers from evidence
**Rationale**: End users (via OpenClaw) need answers, not formatted evidence dumps; synthesis is where conversational quality lives
**Alternative Rejected**: Return raw evidence like `kg_query` does (appropriate for Claude Code developer workflow, not for end users)

### 6. Sequential Multi-Tool vs RRF Merge

**Decision**: Claude calls tools sequentially, evaluates results, decides whether to call more
**Rationale**: More powerful than blind merge — Claude sees results before deciding; prevents diluting precise results with noise from less relevant strategies; handles all 5 strategies uniformly (schema and cypher are not merge-compatible with vector-based strategies)
**Alternative Rejected**: Run 2-3 strategies in parallel with Reciprocal Rank Fusion (only works for vector/hybrid/cross_layer; can dilute precision; adds latency from slowest strategy)

### 7. Driver Lifecycle

**Decision**: Query server creates one driver at startup, shared across calls
**Rationale**: The query server is long-lived and read-only; connection pooling is safe and reduces latency
**Alternative Rejected**: Per-call driver creation (existing pattern in construction server, but adds ~100ms per call for connection setup)

### 8. Dual-Platform Deployment (Cowork + OpenClaw)

**Decision**: Support both Claude Cowork and OpenClaw as deployment targets with shared core and platform-specific packaging
**Rationale**: The Query MCP Server is platform-agnostic (standard MCP over stdio). The only platform-specific artifacts are packaging (plugin.json for Cowork, openclaw.json for OpenClaw) and skill installation paths. Sharing one SKILL.md across both platforms minimizes maintenance.
**Trade-off**: Cowork is desktop-only (no chat channels); OpenClaw is headless with multi-channel support. Users choose based on their deployment needs, or use both.
**Alternative Rejected**: Picking one platform exclusively (loses users on the other platform; the marginal cost of supporting both is low since MCP is the shared transport)

### 9. No LangChain Dependency

**Decision**: Use existing KG-Factory patterns (Anthropic SDK + neo4j-graphrag + run_agent_sync)
**Rationale**: Retrievers already work via neo4j-graphrag; LangChain would duplicate retriever abstractions without adding capability; conversation management is already implemented; debugging stays direct (no framework abstraction layers)
**Alternative Rejected**: LangChain/LangGraph (abstraction tax without proportional value; EnsembleRetriever only works for retriever-shaped operations; API instability across versions)

---

## Environment Variables

The Query MCP Server requires:

```
ANTHROPIC_API_KEY    # Claude API (query agent reasoning)
NEO4J_URI            # Neo4j connection
NEO4J_USER           # Neo4j auth
NEO4J_PASSWORD       # Neo4j auth
OPENAI_API_KEY       # text-embedding-3-large (vector-based strategies)
```

Optional:
```
LANGSMITH_TRACING    # Enable LangSmith observability (true/false)
KG_DATA_DIR          # Data directory override (for state file location)
```

---

## Testing Plan

### Unit Tests (`tests/unit/test_query_agent.py`)

- Tool handlers return correct format
- `discover_graph` caches labels in state
- `search_entities` uses discovered labels when state file is absent
- Session management (create, retrieve, trim, independent sessions)
- Driver shared across calls (not re-created)

### Interactive Test (`tests/test_10_query_agent.py`)

Multi-turn conversation test:
1. Ask about graph structure
2. Ask a domain question
3. Ask a follow-up (tests reference resolution)
4. Ask a cross-layer question
5. Ask a Cypher question

### Integration Test (manual, with Neo4j)

1. Build graph using construction pipeline (furniture supply chain)
2. Start query server
3. Run multi-turn conversation
4. Verify: follow-ups resolve correctly, multiple strategies used, answers synthesized

---

## Future Considerations

### Claude Agent SDK Integration (Cowork)

The Claude Agent SDK (TypeScript and Python) provides programmatic access to the same plugin architecture that powers Cowork. This enables:
- Automated testing of the Cowork plugin without Claude Desktop
- CI/CD pipeline integration for plugin validation
- Programmatic loading of the KG Query plugin in custom applications

```python
from claude_agent_sdk import query

async for message in query(
    prompt="What quality issues exist in the knowledge graph?",
    options={
        "plugins": [
            {"type": "local", "path": "./plugins/cowork"}
        ]
    }
):
    print(message)
```

### LLM Provider Abstraction (Deferred)

Currently the Query Agent uses Claude via Anthropic SDK. To support other providers:
- Create `core/llm.py` with `LLMProvider` protocol
- Implement `AnthropicProvider`, `OpenAIProvider`, `OllamaProvider`
- Refactor `core/agent.py` to accept provider
- Embedding model abstraction needed too (`text-embedding-3-large` is OpenAI-specific)

Deferred because: single-provider works, prompt tuning is provider-specific anyway, and the embedding model is currently hardcoded in multiple retriever functions.

### Google A2A Protocol

Agent-to-Agent protocol (launched April 2025) for agent discovery and collaboration. Complementary to MCP: MCP gives agents tools (vertical), A2A lets agents discover and talk to each other (horizontal). Worth monitoring as the ecosystem matures.

### Parallel File Processing

Currently text graph building is sequential (one markdown file at a time). Parallel processing would speed up initial graph construction, which indirectly affects query agent deployment timelines.
