# US002: User Intent Agent

## User Story

**As a** KG-Factory Developer
**I want** a User Intent Agent that captures knowledge graph requirements through conversation
**So that** downstream agents have a clear, approved goal to work from

## Story Points: 3

## Acceptance Criteria

- [ ] Agent asks clarifying questions to understand the user's domain and goals
- [ ] Agent uses `set_proposed_goal` tool to save proposals to state
- [ ] Agent presents proposals clearly and waits for user feedback
- [ ] Agent iterates on proposals based on user feedback
- [ ] Agent only calls `approve_proposed_goal` after explicit user approval
- [ ] Approved goal contains `kind_of_graph` and `graph_description` fields
- [ ] Interactive test script allows manual testing of the full conversation flow

## Definition of Done

- [ ] Code implemented and working
- [ ] Unit tests for tool handlers
- [ ] Interactive test script (`tests/test_01_user_intent.py`) works end-to-end
- [ ] Can complete full flow: clarify → propose → iterate → approve
- [ ] State correctly contains `approved_user_goal` after approval
- [ ] Agent instructions follow spec in `docs/architecture/01_user_intent.md`
- [ ] Code reviewed

## Technical Notes

### Files to Create

```
agents/
├── __init__.py
└── user_intent.py       # Agent definition

tools/
├── __init__.py
└── intent_tools.py      # set_proposed_goal, approve_proposed_goal

tests/
├── __init__.py
└── test_01_user_intent.py  # Interactive test
```

### Tool Specifications

**set_proposed_goal**
- Input: `kind_of_graph` (string), `graph_description` (string)
- Effect: Sets `state["proposed_user_goal"]`
- Returns: Success confirmation

**approve_proposed_goal**
- Input: None
- Precondition: `state["proposed_user_goal"]` exists
- Effect: Copies proposed to `state["approved_user_goal"]`
- Returns: Success with approved goal

### Agent System Prompt (Key Points)

- Role: Knowledge graph design consultant
- Goal: Understand user's domain and requirements
- Behavior: Ask questions first, then propose, wait for approval
- Quality: Descriptions should be detailed enough for downstream agents

### Example Output State

```json
{
  "proposed_user_goal": {
    "kind_of_graph": "supply chain analysis",
    "graph_description": "A multi-level bill of materials for furniture manufacturing..."
  },
  "approved_user_goal": {
    "kind_of_graph": "supply chain analysis",
    "graph_description": "A multi-level bill of materials for furniture manufacturing..."
  }
}
```

## Dependencies

- US001 (Core Agent Framework) must be complete

## Out of Scope

- MCP exposure (covered in US003)
- File system access (covered in US004 - File Suggestion Agent)
