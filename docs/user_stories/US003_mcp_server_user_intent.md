# US003: MCP Server with User Intent

## User Story

**As a** Knowledge Graph Developer
**I want** to interact with the User Intent Agent through Claude Code via MCP
**So that** I can define my knowledge graph goals through natural conversation in my familiar development environment

## Story Points: 5

## Acceptance Criteria

- [ ] MCP server starts and exposes tools to Claude Code
- [ ] `kg_get_state` tool returns current pipeline state
- [ ] `kg_user_intent` tool invokes the User Intent Agent
- [ ] State persists between MCP tool calls (within a session)
- [ ] State can be persisted to disk for session recovery
- [ ] Example project `.mcp.json` correctly configures server connection
- [ ] Example project `CLAUDE.md` guides Claude Code through the workflow
- [ ] End-to-end test: Claude Code can complete User Intent stage via MCP

## Definition of Done

- [ ] Code implemented and working
- [ ] MCP server starts without errors
- [ ] Tools appear in Claude Code when connected
- [ ] Can complete User Intent flow entirely through Claude Code
- [ ] State file created in example project after approval
- [ ] User CLAUDE.md provides clear workflow guidance
- [ ] Integration test script validates MCP protocol
- [ ] Code reviewed

## Technical Notes

### Files to Create/Update

```
mcp_server/
├── __init__.py
└── server.py            # MCP server implementation

examples/furniture_supply_chain/
├── CLAUDE.md            # User-facing workflow guidance
├── .mcp.json            # MCP server configuration
└── state/
    └── current_state.json  # Persisted state (created at runtime)
```

### MCP Tools to Expose

**kg_get_state**
```json
{
  "name": "kg_get_state",
  "description": "Get current KG-Factory pipeline state. Shows what has been proposed and approved.",
  "input_schema": {
    "type": "object",
    "properties": {},
    "required": []
  }
}
```

**kg_user_intent**
```json
{
  "name": "kg_user_intent",
  "description": "Interact with the User Intent Agent to define knowledge graph goals.",
  "input_schema": {
    "type": "object",
    "properties": {
      "message": {
        "type": "string",
        "description": "Your message to the agent (requirements, feedback, or 'approve')"
      }
    },
    "required": ["message"]
  }
}
```

### User CLAUDE.md Template (Key Sections)

```markdown
## Available Tools
- kg_get_state: Check pipeline progress
- kg_user_intent: Define what kind of knowledge graph to build

## Workflow
1. Start with kg_get_state to see current progress
2. Use kg_user_intent to describe your knowledge graph needs
3. Review the agent's proposal
4. Provide feedback or say "approve" to finalize

## Data Files
- data/*.csv - Your structured data
- data/**/*.md - Your unstructured text
```

### .mcp.json Configuration

```json
{
  "mcpServers": {
    "kg-factory": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "<path-to-kg-factory>"
    }
  }
}
```

### State Persistence Strategy

- State stored in `state/current_state.json` in user's project
- MCP server reads project path from environment or working directory
- State loaded on first tool call, saved after each modification

## Dependencies

- US001 (Core Agent Framework) must be complete
- US002 (User Intent Agent) must be complete

## Out of Scope

- Other agents exposed via MCP (future stories)
- Neo4j integration
- Multiple concurrent sessions

## Validation Scenario

1. Open Claude Code in `examples/furniture_supply_chain/`
2. Claude Code reads CLAUDE.md, understands available tools
3. User: "I want to build a supply chain knowledge graph"
4. Claude Code calls `kg_user_intent` with user's message
5. Agent proposes a goal, Claude Code presents it
6. User: "Looks good, approve it"
7. Claude Code calls `kg_user_intent` with "approve"
8. `state/current_state.json` contains `approved_user_goal`
