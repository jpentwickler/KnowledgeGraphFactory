# US001: Core Agent Framework

## User Story

**As a** KG-Factory Developer
**I want** a core framework for running agents with tool execution and state management
**So that** I can build consistent agents that follow the propose-approve pattern

## Story Points: 5

## Acceptance Criteria

- [ ] Base agent runner executes Claude API calls with system instructions and tools
- [ ] Tool execution utility handles tool calls and returns results to Claude
- [ ] State management supports read/write of proposed and approved artifacts
- [ ] State can be persisted to and loaded from JSON files
- [ ] Agent runner supports multi-turn conversations (tool call → result → continue)
- [ ] Minimal example project structure exists (`examples/furniture_supply_chain/`)
- [ ] Example project contains sample data files (at least 2 CSVs, 1 markdown)

## Definition of Done

- [ ] Code implemented and working
- [ ] Unit tests for agent runner, tool executor, and state manager
- [ ] Example project created with sample data
- [ ] Can run a simple test agent that uses tools and modifies state
- [ ] CLAUDE.md updated if needed
- [ ] Code reviewed

## Technical Notes

### Files to Create

```
core/
├── __init__.py
├── agent.py          # Base agent runner
├── state.py          # State management (load, save, get, set)
└── tools.py          # Tool execution utilities

examples/
└── furniture_supply_chain/
    ├── CLAUDE.md     # User-facing workflow guidance (minimal)
    ├── .mcp.json     # MCP config (placeholder)
    ├── data/
    │   ├── products.csv
    │   ├── suppliers.csv
    │   └── reviews/
    │       └── sample_review.md
    └── state/
        └── .gitkeep
```

### Key Patterns

```python
# Agent runner signature
async def run_agent(
    message: str,
    state: dict,
    system_prompt: str,
    tools: list[dict],
    tool_handlers: dict[str, Callable]
) -> tuple[str, dict]:
    """Run one turn of agent conversation."""
    pass

# Tool handler signature
def handle_tool(state: dict, **params) -> dict:
    """Execute tool, may modify state, returns result."""
    pass
```

### Dependencies

- `anthropic` - Claude API client
- No external frameworks

## Out of Scope

- Specific agent implementations (covered in US002+)
- MCP server integration (covered in US003)
- Neo4j integration (later stories)
