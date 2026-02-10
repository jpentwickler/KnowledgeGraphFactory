# US007: Fact Extraction Agent

## User Story

**As a** KG-Factory Developer
**I want** a Fact Extraction Agent that proposes fact types (subject-predicate-object triples) based on approved entity types
**So that** downstream agents know how to extract relationships from unstructured text

## Story Points: 5

## Acceptance Criteria

- [ ] Fact Agent analyzes structure-aware file previews and approved entity types from the system prompt
- [ ] Fact Agent can use `sample_file` to read deeper (agent-initiated when preview is insufficient, or user-directed)
- [ ] Fact Agent proposes fact types as (subject, predicate, object) triples using `add_proposed_fact`
- [ ] Fact Agent validates subject and object are approved entity types (tool-level validation)
- [ ] Fact Agent validates predicate format is lowercase_with_underscores (tool-level validation)
- [ ] Fact Agent can remove proposed facts using `remove_proposed_fact`
- [ ] Fact Agent explains each proposed fact type with directionality reasoning and text examples
- [ ] Fact Agent avoids vague predicates ("related_to", "associated_with")
- [ ] Fact Agent distinguishes fact types (templates) from specific facts (instances)
- [ ] Fact Agent is transparent: summarizes what it analyzed (files, sections, relationship patterns, exclusions, directionality reasoning) before presenting proposal
- [ ] Fact Agent iterates based on user feedback before approving
- [ ] Fact Agent only calls `approve_proposed_facts` when user explicitly approves
- [ ] Approved output is `state["approved_fact_types"]` as a dict of triples
- [ ] Agent exposed via MCP as `kg_fact_extraction` tool
- [ ] Multi-turn conversation works through MCP (conversation history persists)
- [ ] MCP response includes pre-computation summary (files analyzed, sections found, entity types used)

## Definition of Done

- [ ] Code implemented and working
- [ ] Unit tests for all tool handlers in `tools/extraction_tools.py` (Fact portion)
- [ ] Interactive test script works end-to-end (`test_05_facts.py`)
- [ ] Can complete full flow: analyze -> propose facts -> iterate -> approve
- [ ] State correctly contains `approved_fact_types` after approval
- [ ] MCP tool `kg_fact_extraction` works from Claude Code
- [ ] Agent instructions follow spec in `docs/architecture/05_fact_extraction.md`
- [ ] Code reviewed

## Technical Notes

### Architecture

The Fact Extraction agent follows the same pre-computation pattern as NER (US006).
It receives approved entity types, user goal, and structure-aware file previews in the system prompt.

```
FactExtractionAgent (user-facing, MCP path)
  |
  +-> Pre-computed system prompt contains:
  |     +-> User goal (from state)
  |     +-> Approved entity types (from NER stage)
  |     +-> Structure-aware file previews (headings + first lines per section)
  |
  +-> Tools (5 total):
        +-> sample_file (collaborative: agent or user can trigger deeper reading)
        +-> add_proposed_fact (add a triple to the proposal)
        +-> remove_proposed_fact (remove a triple from the proposal)
        +-> get_proposed_facts (retrieve current proposal)
        +-> approve_proposed_facts (finalize after user approval)
```

The agent starts with all context pre-computed in the system prompt. Structure-aware
previews show the heading hierarchy and first lines of every section, giving visibility
into the full document structure. The `sample_file` tool is available for reading
deeper into specific sections when the preview is insufficient.

### Files to Create/Update

```
tools/
  extraction_tools.py              # UPDATE: Add fact extraction tool schemas + handlers

agents/
  fact_extraction.py               # NEW: Fact Extraction Agent

agents/__init__.py                 # UPDATE: Add FactExtractionAgent
tools/__init__.py                  # UPDATE: Add fact extraction tool exports

mcp_server/
  server.py                        # UPDATE: Add kg_fact_extraction tool

tests/
  unit/
    test_extraction_tools.py       # UPDATE: Add fact extraction unit tests
  test_05_facts.py                 # NEW: Interactive test
```

### Tool Specifications

All tools live in `tools/extraction_tools.py` (shared with NER tools from US006).

**Pre-computation functions (not tools — called from agent constructor):**

**build_markdown_context(state)** (reused from US006)
- Same as NER agent — shared function. Parses markdown heading structure,
  extracts first ~5 lines per section with line numbers for targeted sampling.

**build_entity_types_context(state)**
- Input: State dict with `approved_entity_types` (dict with source/description metadata)
- Effect: Formats entity types with their source and description for system prompt injection
- Returns: Formatted string showing each type with its provenance and description

**Agent tools:**

**sample_file** (imported from `tools/file_tools.py`)
- Input: `file_path` (relative), `num_lines` (optional, default 100)
- Effect: Reads the first N lines of a file
- Returns: File content preview
- Note: Collaborative tool — the agent can call it when a section preview is
  insufficient, and the user can direct the agent to look at sections it missed.
  Reuses existing implementation from Stage 2 — no new code needed.

**add_proposed_fact**
- Input: `subject_label` (string), `predicate_label` (string), `object_label` (string)
- Precondition: Subject and object must be keys in `state["approved_entity_types"]` dict
- Precondition: Predicate must be lowercase with no spaces
- Effect: Adds triple to `state["proposed_fact_types"][predicate_label]`
- Returns: Success with triple, or error with validation message
- Note: Predicate is used as dict key; calling again with same predicate overwrites

**remove_proposed_fact**
- Input: `predicate_label` (string)
- Precondition: Predicate must exist in `state["proposed_fact_types"]`
- Effect: Removes the triple from proposed facts
- Returns: Success confirmation, or error if not found

**get_proposed_facts**
- Input: None
- Effect: Reads `state["proposed_fact_types"]`
- Returns: Dict of proposed fact types and count

**approve_proposed_facts**
- Input: None
- Precondition: `proposed_fact_types` must exist and be non-empty
- Effect: Copies proposed to `state["approved_fact_types"]`
- Returns: Success with approved facts, or error if no proposal exists

### Pre-computation Pattern

```python
class FactExtractionAgent:
    def __init__(self):
        self.tools = [TOOL_ADD_PROPOSED_FACT, ...]
        self.tool_handlers = {...}

    def run(self, message, state, conversation=None):
        # Pre-compute context for system prompt
        user_goal = format_user_goal(state)
        entity_types = build_entity_types_context(state)
        file_context = build_markdown_context(state)

        system_prompt = FACT_SYSTEM_PROMPT.format(
            user_goal=user_goal,
            approved_entity_types=entity_types,
            file_context=file_context,
        )

        return run_agent_sync(message, state, system_prompt,
                              self.tools, self.tool_handlers, conversation)
```

### Key Design Decisions

**Incremental fact proposal**: Unlike NER (which sets all entities at once with
`set_proposed_entities`), fact types are added one at a time with `add_proposed_fact`.
This matches the course design and allows the agent to explain each triple as it
proposes it.

**Predicate as dict key**: The `proposed_fact_types` dict uses the predicate label
as key. This means each predicate must be unique. If the agent calls `add_proposed_fact`
with the same predicate but different subject/object, it overwrites. This is intentional
— one predicate label should map to one relationship pattern.

**Tool-level validation**: Both entity type membership and predicate format are validated
in the tool handlers. The agent gets immediate error feedback and can self-correct.
This is a guardrail the course implementation lacks.

**Shared pre-computation**: `build_markdown_context` (with `build_structured_preview`)
is the same function used by NER. No duplication — both agents import from
`extraction_tools.py`.

**sample_file as collaborative fallback**: Like NER, the agent starts with
structure-aware previews. The `sample_file` tool is available for deeper reading
in two ways: the agent can call it when a section preview is truncated, and the
user can direct the agent to look at sections it missed. This is collaborative —
the agent does its best, and the user fills gaps.

**Remove support**: The `remove_proposed_fact` tool (not in the course) gives the
agent the ability to respond to user feedback like "drop the has_feature relationship"
without rebuilding the entire proposal.

### Agent System Prompt (Key Points)

- Role: Knowledge extraction specialist for knowledge graphs
- Pre-computed sections: User goal, approved entity types, structure-aware file previews
- Fact type vs specific fact distinction (with "ABK likes coffee" anti-example)
- Design rules: Approved entities only, text-grounded, lowercase_with_underscores
- Anti-patterns: Vague predicates ("related_to"), guessing relationships
- Directionality: Explicit guidance with contrasting examples
- Workflow: Analyze -> add facts -> present -> iterate -> approve on explicit request

Full prompt in `docs/architecture/05_fact_extraction.md`.

### Example Output State

```json
{
  "approved_user_goal": {
    "kind_of_graph": "supply chain analysis",
    "description": "A multi-level bill of materials, useful for root cause analysis."
  },
  "approved_files": {
    "structured": [...],
    "unstructured": [...]
  },
  "approved_construction_plan": {...},
  "approved_entity_types": {
    "Product": {"source": "well_known", "description": "Products mentioned in reviews"},
    "Issue": {"source": "discovered", "description": "Problems reported by reviewers"},
    "Feature": {"source": "discovered", "description": "Product characteristics mentioned in reviews"}
  },
  "proposed_fact_types": {
    "has_issue": {
      "subject_label": "Product",
      "predicate_label": "has_issue",
      "object_label": "Issue"
    },
    "has_feature": {
      "subject_label": "Product",
      "predicate_label": "has_feature",
      "object_label": "Feature"
    },
    "affects_feature": {
      "subject_label": "Issue",
      "predicate_label": "affects_feature",
      "object_label": "Feature"
    }
  },
  "approved_fact_types": {
    "has_issue": {
      "subject_label": "Product",
      "predicate_label": "has_issue",
      "object_label": "Issue"
    },
    "has_feature": {
      "subject_label": "Product",
      "predicate_label": "has_feature",
      "object_label": "Feature"
    },
    "affects_feature": {
      "subject_label": "Issue",
      "predicate_label": "affects_feature",
      "object_label": "Feature"
    }
  }
}
```

### MCP Integration

**kg_fact_extraction**
```json
{
  "name": "kg_fact_extraction",
  "description": "Send a message to the Fact Extraction Agent. Pass the user's message exactly as written.",
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

Conversation key: `_fact_extraction_conversation`

Return value includes:
- Status with `has_proposed_fact_types` and `has_approved_fact_types` flags
- Summary of proposed/approved triples
- `pre_computation_summary`: What the agent was given before the conversation started
  - `files_analyzed`: Number and names of markdown files previewed
  - `total_sections`: Total sections found across all files
  - `entity_types_available`: Approved entity types used for validation

### Data Directory Resolution

Same as previous stages: tools use `KG_DATA_DIR` environment variable, falling back to `NEO4J_IMPORT_DIR` or `./data`.

## Dependencies

- US001 (Core Agent Framework) must be complete
- US006 (NER Extraction Agent) must be complete — provides `approved_entity_types`
- `approved_user_goal` must exist in state
- `approved_files` must exist in state (with unstructured files)
- `approved_construction_plan` must exist in state
- `approved_entity_types` must exist in state

## Out of Scope

- NER entity type extraction (covered in US006)
- Actual fact instance extraction from text (covered in later stages)
- Graph construction (covered in later stages)
- Processing non-markdown unstructured files
- Fact validation against Neo4j schema constraints

## Validation Scenario

### Scenario: Interactive fact extraction via MCP

1. Load state with all approved artifacts from Stages 1-4 (including `approved_entity_types`)
2. User: "Propose fact types that can be found in the product reviews"
3. Fact agent reviews pre-computed context (goal, entity types, file previews)
4. Agent proposes fact types with explanations:
   - Calls `add_proposed_fact("Product", "has_issue", "Issue")`
   - Calls `add_proposed_fact("Product", "has_feature", "Feature")`
5. Agent presents proposal with directionality reasoning and text examples
6. User: "Can you add one connecting issues to features?"
7. Agent calls `add_proposed_fact("Issue", "affects_feature", "Feature")`
8. Agent explains the new triple and directionality choice
9. User: "Approve"
10. Agent calls `approve_proposed_facts`
11. `state["approved_fact_types"]` contains 3 fact type triples
12. Same flow works through Claude Code via `kg_fact_extraction` MCP tool
