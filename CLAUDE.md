# KG-Factory: Knowledge Graph Construction Agents

## Project Intent

Accelerate the creation of production-ready, high-quality knowledge graphs using Claude Code as the development workflow.

KG-Factory provides tools (not a framework) that integrate with Claude Code, enabling developers to build knowledge graphs through natural conversation while maintaining full control over schema design, entity extraction, and graph construction.

## Project Purpose

Build a multi-agent system that automates knowledge graph construction in Neo4j.
Uses pure Python + Claude API (Anthropic SDK). No frameworks like LangChain or Google ADK.

## Workflow

Voice saves story drafts, cloud **workers** build one story each on its own branch and PR, and
the **hub** (Claude Code on the owner's machine, where `CLAUDE_CODE_REMOTE` is unset) reviews
through PR review comments, merges, runs the Neo4j/Docker checks and closes. The roles, stages and
phrases are in `WORKFLOW.md` in `jpentwickler/claude-skills`, not here. What the shared skills read
from this project:

| | |
|---|---|
| Stories | `docs/user_stories/USNNN_*.md` (from US025 on, branch `us-0nn-short-slug`, PR `US-0NN: <title>`). The `## Status:` line starts with a stage word (`docs/user_stories/README.md`) |
| Health command | `uv run --no-project --python 3.13 --with-requirements requirements.txt python -m pytest tests/unit -q` (no Neo4j or API keys needed). The repo has no `pyproject.toml`, so Python always runs through `uv` like this |
| Vault | Yes. The vault project is **Ontology Pipeline** (`repo: KnowledgeGraphFactory`). Drafts are notes tagged `story-draft` with `project: '[[KnowledgeGraphFactory]]'`, under `projects/Ontology Pipeline/drafts/`, found with `search_notes("story-draft")` |

## Integration Approach

**Decision**: Hybrid MCP + CLAUDE.md

The platform integrates with Claude Code via:

1. **MCP Server** (`mcp_server/`) - Exposes each agent as a tool
2. **User CLAUDE.md** - Provides workflow guidance for Claude Code orchestration

```
User's Project/
├── CLAUDE.md        ← Tells Claude Code how to use KG-Factory
├── .mcp.json        ← Connects to KG-Factory MCP server
├── data/            ← CSV and markdown files
└── state/           ← Agent state persistence
```

**Why hybrid**:
- MCP provides structured tool invocation and state management
- CLAUDE.md provides domain knowledge and workflow flexibility
- Claude Code orchestrates intelligently, user approves at each stage

**Test projects**: `examples/furniture_supply_chain/`, `examples/social_network/`

## Architecture Overview

```
User Intent → File Suggestion → Schema Proposal → NER Extraction → Fact Extraction → Graph Build
     │              │                  │                │                │              │
     ▼              ▼                  ▼                ▼                ▼              ▼
approved_     approved_        approved_         approved_        approved_       Neo4j
user_goal     files           construction_     entity_types     fact_types      Graph
                              plan
```

## Core Design Patterns

### 1. Simple Agent Pattern
Every agent is a function that:
- Takes a message and shared state
- Calls Claude with instructions + tools
- Returns response and updated state

```python
async def run_agent(message: str, state: dict) -> tuple[str, dict]:
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        system=INSTRUCTIONS,
        messages=conversation,
        tools=TOOLS
    )
    # Process tool calls, update state
    return assistant_response, state
```

### 2. Propose → Approve Pattern
All agents follow this flow:
1. Agent proposes output → `state["proposed_X"]`
2. Human reviews and may iterate
3. Human says "approve" → `state["approved_X"] = state["proposed_X"]`
4. Downstream agents read `state["approved_X"]`

### 3. Tool Design
Tools are dictionaries with schema + handler function:
```python
TOOL_SCHEMA = {
    "name": "set_proposed_goal",
    "description": "Save the proposed user goal",
    "input_schema": {...}
}

def handle_set_proposed_goal(state: dict, **params) -> dict:
    state["proposed_user_goal"] = params
    return {"status": "success", "saved": params}
```

## Development Stages

Build and test each agent before moving to the next:

| Stage | Agent | Input State | Output State | Test File |
|-------|-------|-------------|--------------|-----------|
| 1 | User Intent | (none) | approved_user_goal | test_01_user_intent.py |
| 2 | File Suggestion | approved_user_goal | approved_files | test_02_file_suggestion.py |
| 3 | Schema Proposal | + approved_files | approved_construction_plan | test_03_schema_proposal.py |
| 4 | NER Extraction | + approved_construction_plan | approved_entity_types | test_04_ner.py |
| 5 | Fact Extraction | + approved_entity_types | approved_fact_types | test_05_facts.py |
| 6 | Graph Builder | all approved_* | Neo4j graph | test_06_build.py |

## File Structure

```
kg-factory/
├── CLAUDE.md              # This file - read first
├── README.md              # User documentation
├── requirements.txt       # Dependencies
├── .env.example           # Environment template
│
├── core/                  # Framework (build first)
│   ├── __init__.py
│   ├── agent.py           # Base agent runner
│   ├── state.py           # State management
│   └── tools.py           # Tool execution utilities
│
├── agents/                # Agent definitions (build second)
│   ├── __init__.py
│   ├── user_intent.py     # Stage 1
│   ├── file_suggestion.py # Stage 2
│   ├── schema_proposal.py # Stage 3a
│   ├── schema_critic.py   # Stage 3b
│   ├── ner_extraction.py  # Stage 4
│   └── fact_extraction.py # Stage 5
│
├── tools/                 # Tool implementations
│   ├── __init__.py
│   ├── intent_tools.py    # Tools for Stage 1
│   ├── file_tools.py      # Tools for Stage 2
│   ├── schema_tools.py    # Tools for Stage 3
│   └── extraction_tools.py # Tools for Stages 4-5
│
├── pipelines/             # Multi-agent workflows
│   ├── __init__.py
│   └── full_pipeline.py   # End-to-end orchestration
│
├── tests/                 # Interactive tests
│   ├── __init__.py
│   ├── test_01_user_intent.py
│   ├── test_02_file_suggestion.py
│   ├── test_03_schema_proposal.py
│   ├── test_04_ner.py
│   ├── test_05_facts.py
│   └── test_06_build.py
│
├── docs/
│   ├── architecture/      # Agent specs and architecture: 00_architecture.md, 01_user_intent.md … 15_*.md
│   └── user_stories/      # USNNN_*.md stories + README.md (template, stage words, Story Index)
│
├── mcp_server/            # MCP server exposing agents as tools
│   └── server.py
│
├── examples/              # Test projects for hybrid MCP + CLAUDE.md
│   ├── furniture_supply_chain/
│   │   ├── CLAUDE.md      # User-facing workflow guidance
│   │   ├── .mcp.json      # MCP server connection
│   │   ├── data/          # Sample CSV and markdown
│   │   └── state/         # Agent state persistence
│   └── social_network/    # Second test domain
│
├── templates/             # For users starting new projects
│   ├── CLAUDE.md.template
│   └── .mcp.json.template
│
└── data/                  # Test data
    ├── csv/               # Structured data samples
    └── markdown/          # Unstructured data samples
```

## Key Implementation Details

### Claude API Usage
```python
import anthropic

client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    system="Your instructions here",
    messages=[{"role": "user", "content": "message"}],
    tools=[TOOL_SCHEMA_1, TOOL_SCHEMA_2]
)
```

### Tool Call Handling
```python
for block in response.content:
    if block.type == "tool_use":
        tool_name = block.name
        tool_input = block.input
        tool_id = block.id
        
        # Execute tool
        result = tool_handlers[tool_name](state, **tool_input)
        
        # Send result back
        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user", 
            "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": json.dumps(result)}]
        })
```

### State Persistence
State is a simple dictionary. For tests, save/load with JSON:
```python
import json

def save_state(state: dict, path: str):
    with open(path, 'w') as f:
        json.dump(state, f, indent=2)

def load_state(path: str) -> dict:
    with open(path) as f:
        return json.load(f)
```

## Environment Variables

Required:
- `ANTHROPIC_API_KEY` - Claude API key
- `NEO4J_URI` - Neo4j connection URI (bolt://localhost:7687)
- `NEO4J_USER` - Neo4j username
- `NEO4J_PASSWORD` - Neo4j password
- `NEO4J_IMPORT_DIR` - Path to Neo4j import directory (for CSV/markdown files)

## Testing Approach

Each test file is an interactive session:
```python
# test_01_user_intent.py
async def main():
    state = {}
    agent = UserIntentAgent()
    
    print("=== User Intent Agent Test ===")
    print("Type your messages. Type 'quit' to exit, 'state' to see current state.")
    
    while True:
        user_input = input("\nYou: ")
        if user_input == 'quit':
            break
        if user_input == 'state':
            print(json.dumps(state, indent=2))
            continue
            
        response, state = await agent.run(user_input, state)
        print(f"\nAgent: {response}")
        
        if "approved_user_goal" in state:
            print("\n✅ Goal approved! Ready for next stage.")

if __name__ == "__main__":
    asyncio.run(main())
```

## Common Commands

```bash
# Install dependencies
pip install -e .

# Run a specific test
python -m tests.test_01_user_intent

# Run with debug logging
DEBUG=1 python -m tests.test_01_user_intent
```

## Neo4j Queries Reference

Check graph state:
```cypher
// Count all nodes by label
MATCH (n) RETURN labels(n) as label, count(*) as count

// Show schema
CALL db.schema.visualization()

// Clear everything (careful!)
MATCH (n) DETACH DELETE n
```

## Next Steps for Claude Code

The original build order (core framework → one agent per stage) is complete: US001–US024 are
`DONE` except US016 (see the Story Index in `docs/user_stories/README.md`). New work starts from a
story, as the **Workflow** section above describes.

Agent specs live in `docs/architecture/` (`00_architecture.md`, `01_user_intent.md` …
`15_adaptive_retrieval_architecture.md`). Read the one for an agent before changing it.
