# US005: Schema Proposal Agent (Critic Pattern)

## User Story

**As a** KG-Factory Developer
**I want** a Schema Proposal Agent that uses a multi-agent critic pattern to design a knowledge graph schema
**So that** downstream agents have an approved construction plan for building nodes and relationships

## Story Points: 8

## Acceptance Criteria

- [ ] Schema Proposal Agent analyzes all approved CSV files and proposes node/relationship constructions
- [ ] Schema Proposal Agent uses `search_file` to validate column names before proposing
- [ ] Schema Proposal Agent receives critic feedback via `{feedback}` injection in system prompt
- [ ] Schema Critic Agent independently validates the proposal with read-only tools
- [ ] Schema Critic Agent uses `submit_review` tool with structured verdict ("valid"/"retry") and problems list
- [ ] Refinement loop checks `state["_critic_verdict"]` (not free text) to decide stop/iterate
- [ ] Refinement loop records each iteration in `state["_refinement_trace"]` for debugging
- [ ] Refinement loop runs proposal -> critic -> check for up to 2 iterations
- [ ] Refinement loop stops early when critic verdict is "valid"
- [ ] Refinement loop is callable directly (without coordinator) for tests and pipelines
- [ ] Schema Proposal Coordinator wraps the refinement loop as a tool
- [ ] Coordinator presents results to user and waits for explicit approval
- [ ] Coordinator iterates if user disapproves (re-runs refinement loop with feedback)
- [ ] Approved output is `state["approved_construction_plan"]` with node and relationship rules
- [ ] Agent exposed via MCP as `kg_schema_proposal` tool
- [ ] Multi-turn conversation works through MCP (conversation history persists for coordinator)

## Definition of Done

- [ ] Code implemented and working
- [ ] Unit tests for all tool handlers in `tools/schema_tools.py`
- [ ] Verification test simulates conversation programmatically (`test_03_verify.py`)
- [ ] Interactive test script works end-to-end (`test_03_schema_proposal.py`)
- [ ] Can complete full flow: refinement loop -> present -> iterate -> approve
- [ ] State correctly contains `approved_construction_plan` after approval
- [ ] MCP tool `kg_schema_proposal` works from Claude Code
- [ ] Agent instructions follow spec in `docs/architecture/03_schema_proposal.md`
- [ ] Code reviewed

## Technical Notes

### Architecture — Four Components

This stage faithfully reproduces the Google ADK LoopAgent design:

```
SchemaProposalCoordinator (user-facing, MCP path)
  |
  +-> run_refinement_loop (tool)        <-- also callable directly for tests
  |     +-> SchemaProposalAgent (proposes, 9 tools, no approval)
  |     +-> SchemaCriticAgent (validates, 5 read-only + submit_review)
  |     +-> check _critic_verdict (stop if "valid", else loop, max 2)
  |     +-> record to _refinement_trace (debugging)
  |
  +-> get_proposed_construction_plan (read-only)
  +-> approve_proposed_construction_plan (finalize)
```

### Files to Create/Update

```
tools/
  schema_tools.py                  # NEW: 9 tool schemas + handlers

agents/
  schema_proposal.py               # NEW: Inner proposal agent
  schema_critic.py                 # NEW: Inner critic agent
  schema_coordinator.py            # NEW: User-facing coordinator

pipelines/
  __init__.py                      # NEW: Package init
  schema_loop.py                   # NEW: run_refinement_loop()

agents/__init__.py                 # UPDATE: Add SchemaProposalCoordinator
tools/__init__.py                  # UPDATE: Add schema tool exports

mcp_server/
  server.py                        # UPDATE: Add kg_schema_proposal tool

tests/
  unit/
    test_schema_tools.py           # NEW: Unit tests for handlers
  test_03_verify.py                # NEW: Verification test
  test_03_schema_proposal.py       # NEW: Interactive test
```

### Tool Specifications

**Reused from Stage 2 (imported from `tools/file_tools.py`):**

- `get_approved_user_goal` — Retrieve approved goal from state
- `sample_file` — Read first N lines of a file

**New tools in `tools/schema_tools.py`:**

**get_approved_files**
- Input: None
- Effect: Reads `state["approved_files"]` and extracts file paths
- Returns: structured_files, unstructured_files, all_files

**search_file**
- Input: `file_path` (relative), `query` (string)
- Effect: Case-insensitive line search in text file
- Returns: Matching lines with line numbers, metadata
- Security: Path traversal prevention

**propose_node_construction**
- Input: `approved_file`, `proposed_label`, `unique_column_name`, `proposed_properties`
- Precondition: Validates `unique_column_name` exists in file via search_file
- Effect: Adds node rule to `state["proposed_construction_plan"][proposed_label]`
- Returns: The node construction rule

**propose_relationship_construction**
- Input: `approved_file`, `proposed_relationship_type`, `from_node_label`, `from_node_column`, `to_node_label`, `to_node_column`, `proposed_properties`
- Precondition: Validates both column names exist in file
- Effect: Adds relationship rule to `state["proposed_construction_plan"][type]`
- Returns: The relationship construction rule

**remove_node_construction**
- Input: `node_label`
- Effect: Removes node rule from proposed plan (idempotent)

**remove_relationship_construction**
- Input: `relationship_type`
- Effect: Removes relationship rule from proposed plan (idempotent)

**get_proposed_construction_plan**
- Input: None
- Returns: Full plan with node_count and relationship_count

**approve_proposed_construction_plan**
- Input: None
- Precondition: Proposed plan exists and is non-empty
- Effect: Copies proposed to `state["approved_construction_plan"]`

**Critic-only tool:**

**submit_review**
- Input: `verdict` (enum: "valid" or "retry"), `problems` (array of strings)
- Effect: Stores `state["_critic_verdict"]` and `state["_critic_problems"]`
- Returns: Confirmation of recorded verdict
- Note: Replaces fragile free-text "valid" parsing from original ADK design

**Coordinator-only tool:**

**run_refinement_loop**
- Input: `user_feedback` (optional)
- Effect: Runs proposal-critic loop (max 2 iterations)
- Returns: Summary, node/relationship counts

### Key Design Decisions

**Feedback injection**: The proposal agent's system prompt contains `{feedback}` which
is replaced with `state["feedback"]` at run time using Python string formatting. This
is equivalent to the ADK's automatic state variable replacement.

**Fresh conversations per loop iteration**: Each sub-agent starts with `conversation=None`
every iteration. Feedback flows through state, not conversation history. This matches
the ADK LoopAgent behavior.

**Refinement loop as tool**: The coordinator calls `run_refinement_loop` as a tool handler,
which internally runs 2-4 Claude API calls. This is equivalent to the ADK `AgentTool`
wrapper around the LoopAgent.

**Construction plan built incrementally**: Unlike `set_proposed` (which sets the whole
value at once), the construction plan is built rule-by-rule using `propose_*` tools.
The `approve_proposed_construction_plan` handler copies the entire plan at once.

### Design Improvements Over Original ADK

Three improvements over the original Google ADK implementation:

**1. Refinement tracing** (`state["_refinement_trace"]`): The loop records each
iteration's proposal summary, critic verdict, and problems. Since inner conversations
are discarded each iteration, this trace is essential for debugging. Without it,
failures inside the loop are completely opaque.

**2. Coordinator is optional**: The refinement loop is a standalone function that
can be called directly (`run_refinement_loop(state)`) without the coordinator wrapper.
Tests and pipeline scripts skip the coordinator to avoid an unnecessary Claude API
call for a deterministic decision. The coordinator is used only for MCP/user interaction.

**3. Structured critic verdict** (`submit_review` tool): Instead of parsing the
critic's free text for the word "valid" (fragile — could match "not valid", "validation
failed", etc.), the critic calls a `submit_review` tool with an enum verdict
(`"valid"` or `"retry"`) and a structured problems list. The loop reads
`state["_critic_verdict"]` — no string parsing needed.

### Agent System Prompts (Key Points)

**Schema Proposal Agent:**
- Role: Knowledge graph modeling expert
- Receives critic feedback via `{feedback}` in system prompt
- Follows Neo4j best practices for node vs relationship detection
- Validates column uniqueness via search_file before proposing
- No approval tool (only proposes)

**Schema Critic Agent:**
- Role: Schema validation expert
- Read-only tools (cannot modify the plan) + `submit_review` for structured verdict
- Calls `submit_review(verdict="valid"|"retry", problems=[...])` — no free-text parsing
- Checks: unique identifiers, connectivity, redundancy, correctness

**Schema Proposal Coordinator:**
- Role: User interaction coordinator
- Wraps refinement loop as a tool
- Presents results, handles feedback/approval
- Multi-turn conversation with the user

### Example Output State

```json
{
  "approved_user_goal": {
    "kind_of_graph": "supply chain analysis",
    "graph_description": "..."
  },
  "approved_files": {
    "structured": [
      {"path": "products.csv", "reason": "..."},
      {"path": "suppliers.csv", "reason": "..."}
    ],
    "unstructured": []
  },
  "proposed_construction_plan": {
    "Product": {
      "construction_type": "node",
      "source_file": "products.csv",
      "label": "Product",
      "unique_column_name": "product_id",
      "properties": ["product_name", "price", "description"]
    },
    "SUPPLIED_BY": {
      "construction_type": "relationship",
      "source_file": "part_supplier_mapping.csv",
      "relationship_type": "SUPPLIED_BY",
      "from_node_label": "Part",
      "from_node_column": "part_id",
      "to_node_label": "Supplier",
      "to_node_column": "supplier_id",
      "properties": ["lead_time_days", "unit_cost"]
    }
  },
  "approved_construction_plan": {
    "...same as proposed..."
  }
}
```

### MCP Integration

**kg_schema_proposal**
```json
{
  "name": "kg_schema_proposal",
  "description": "Send a message to the Schema Proposal Coordinator. Pass the user's message exactly as written.",
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

Conversation key: `_schema_proposal_conversation`

Return value includes status with `has_proposed_construction_plan` and `has_approved_construction_plan` flags.

### Data Directory Resolution

Same as Stage 2: tools use `KG_DATA_DIR` environment variable, falling back to `NEO4J_IMPORT_DIR` or `./data`.

## Dependencies

- US001 (Core Agent Framework) must be complete
- US002 (User Intent Agent) must be complete
- US003 (MCP Server) must be complete
- US004 (File Suggestion Agent) must be complete
- `approved_user_goal` must exist in state
- `approved_files` must exist in state

## Out of Scope

- Entity/NER extraction (covered in US006)
- Neo4j graph construction (covered in later stages)
- Supporting non-CSV file types for schema proposal
- Automated schema migration or versioning
- Schema validation against Neo4j constraints

## Validation Scenario

### Scenario A: Via Coordinator (MCP / interactive test)

1. Load state with `approved_user_goal` and `approved_files` from Stages 1-2
2. User: "Design the schema for our supply chain knowledge graph"
3. Coordinator runs refinement loop:
   a. Proposal agent analyzes 5 CSV files, proposes nodes + relationships
   b. Critic agent validates, calls `submit_review(verdict="valid"|"retry", problems=[...])`
   c. Loop checks `_critic_verdict`, converges (max 2 iterations)
   d. `_refinement_trace` records each iteration for inspection
4. Coordinator presents schema to user
5. User: "Approve"
6. `state["approved_construction_plan"]` contains node + relationship rules
7. Same flow works through Claude Code via `kg_schema_proposal` MCP tool

### Scenario B: Direct loop (verification test)

1. Load state with `approved_user_goal` and `approved_files`
2. Call `run_refinement_loop(state)` directly (no coordinator)
3. Verify `proposed_construction_plan` has nodes (>=3) and relationships (>=1)
4. Verify `_refinement_trace` has at least 1 entry with `critic_verdict`
5. Call `handle_approve_proposed_construction_plan(state)` directly
6. Verify `approved_construction_plan` exists
7. Save to `state_after_schema_proposal.json`
