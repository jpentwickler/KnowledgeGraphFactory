# US004: File Suggestion Agent

## User Story

**As a** KG-Factory Developer
**I want** a File Suggestion Agent that identifies relevant data files for knowledge graph construction
**So that** downstream agents know which structured and unstructured files to process

## Story Points: 5

## Acceptance Criteria

- [ ] Agent retrieves and understands the approved user goal before exploring files
- [ ] Agent uses `get_file_info` to collect metadata (columns for CSV, headings for markdown)
- [ ] Agent uses `sample_file` selectively for ambiguous files (100 lines default)
- [ ] Agent categorizes files into structured (CSV) and unstructured (markdown/text)
- [ ] Agent explains why each file is relevant to the user's goal
- [ ] Agent uses `set_proposed_files` to save categorized file proposal
- [ ] Agent waits for explicit user approval before finalizing
- [ ] Approved output contains both `structured` and `unstructured` file lists
- [ ] Agent exposed via MCP as `kg_file_suggestion` tool
- [ ] Multi-turn conversation works through MCP (conversation history persists)

## Definition of Done

- [ ] Code implemented and working
- [ ] Unit tests for tool handlers
- [ ] Verification test simulates conversation programmatically
- [ ] Interactive test script works end-to-end
- [ ] Can complete full flow: explore files → classify → propose → approve
- [ ] State correctly contains `approved_files` after approval
- [ ] MCP tool `kg_file_suggestion` works from Claude Code
- [ ] Agent instructions follow spec in `docs/architecture/02_file_suggestion.md`
- [ ] Code reviewed

## Technical Notes

### Files to Create/Update

```
tools/
└── file_tools.py            # NEW: Tool handlers for file suggestion

agents/
└── file_suggestion.py       # NEW: Agent definition

tests/
├── unit/
│   └── test_file_tools.py   # NEW: Unit tests for tool handlers
├── test_02_verify.py        # NEW: Verification test
└── test_02_file_suggestion.py  # NEW: Interactive test

mcp_server/
└── server.py                # UPDATE: Add kg_file_suggestion tool
```

### Tool Specifications

**get_approved_user_goal**
- Input: None
- Effect: Reads `state["approved_user_goal"]`
- Returns: The approved goal, or error if not found
- Purpose: Agent understands what kind of graph we're building

**list_available_files**
- Input: `file_type` (optional: "all", "csv", "markdown")
- Effect: Scans data directory
- Returns: List of file paths with types
- Note: Uses `KG_DATA_DIR` env var, defaults to `./data`

**get_file_info**
- Input: `file_path` (relative to data directory)
- Effect: Reads file metadata without full content
- Returns (CSV): `columns`, `row_count`, `size_kb`
- Returns (markdown): `headings`, `line_count`, `size_kb`
- Purpose: Cheap classification — column names and headings are usually enough

**sample_file**
- Input: `file_path`, `num_lines` (default: 100)
- Effect: Reads first N lines of a file
- Returns: File content sample, lines sampled
- Purpose: Fallback for ambiguous files where metadata isn't enough

**set_proposed_files**
- Input: `structured` (list of file paths), `unstructured` (list of file paths)
- Effect: Sets `state["proposed_files"]` with categorized lists
- Returns: Success confirmation with file counts

**approve_proposed_files**
- Input: None
- Precondition: `state["proposed_files"]` exists
- Effect: Copies proposed to `state["approved_files"]`
- Returns: Success with approved files

### Agent System Prompt (Key Points)

- Role: Data analyst identifying relevant files for KG construction
- First action: Always retrieve the approved user goal for context
- Workflow: List files → get metadata → classify relevance → propose → approve
- Use `get_file_info` for bulk classification (cheap)
- Use `sample_file` only for ambiguous files (targeted, 100 lines)
- Categorize files into structured and unstructured
- Explain relevance of each file to the user's goal
- Wait for explicit approval

### Example Output State

```json
{
  "approved_user_goal": {
    "kind_of_graph": "furniture supply chain",
    "graph_description": "..."
  },
  "proposed_files": {
    "structured": [
      "products.csv",
      "suppliers.csv"
    ],
    "unstructured": [
      "reviews/stockholm_chair_reviews.md"
    ]
  },
  "approved_files": {
    "structured": [
      "products.csv",
      "suppliers.csv"
    ],
    "unstructured": [
      "reviews/stockholm_chair_reviews.md"
    ]
  }
}
```

### MCP Integration

**kg_file_suggestion**
```json
{
  "name": "kg_file_suggestion",
  "description": "Send a message to the File Suggestion Agent. Pass the user's message exactly as written.",
  "input_schema": {
    "type": "object",
    "properties": {
      "message": {
        "type": "string",
        "description": "The user's message, passed through exactly as written."
      }
    },
    "required": ["message"]
  }
}
```

Return value includes status with `has_proposed_files` and `has_approved_files` flags, same pattern as `kg_user_intent`.

### Data Directory Resolution

Tools that access files use `KG_DATA_DIR` environment variable:
- Defaults to `./data` relative to working directory
- Can be set in `.mcp.json` env or `.env` file
- All file paths in proposals are relative to this directory

## Dependencies

- US001 (Core Agent Framework) must be complete
- US002 (User Intent Agent) must be complete
- US003 (MCP Server) must be complete
- `approved_user_goal` must exist in state

## Out of Scope

- Reading file contents for schema analysis (covered in US005 - Schema Proposal)
- Neo4j import directory configuration
- File format validation or data quality checks
- Supporting file types beyond CSV and markdown

## Validation Scenario

1. Load state with `approved_user_goal` from Stage 1
2. User: "What files should we use?"
3. Agent retrieves goal, lists available files
4. Agent gets metadata for each file (`get_file_info`)
5. Agent proposes categorized file list with explanations
6. User: "Approve"
7. `state["approved_files"]` contains structured and unstructured lists
8. Same flow works through Claude Code via `kg_file_suggestion` MCP tool
