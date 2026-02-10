# US006: NER Extraction Agent

## User Story

**As a** KG-Factory Developer
**I want** a Named Entity Recognition Agent that proposes entity types to extract from unstructured text
**So that** downstream agents know what categories of things to look for when processing markdown files

## Story Points: 5

## Status: ✅ Complete

## Acceptance Criteria

- [x] NER Agent analyzes structure-aware file previews and well-known types from the system prompt
- [x] NER Agent can use `sample_file` to read deeper (agent-initiated when preview is insufficient, or user-directed)
- [x] NER Agent identifies well-known entity types from the approved construction plan
- [x] NER Agent discovers new entity types from markdown file content
- [x] NER Agent proposes entity types using `set_proposed_entities` tool
- [x] NER Agent validates entity types are in PascalCase (tool-level validation)
- [x] NER Agent explains each proposed type (well-known vs discovered, reasoning, text example)
- [x] NER Agent handles disambiguation (e.g., "Assembly" as component vs process)
- [x] NER Agent is transparent: summarizes what it analyzed (files, sections, patterns found, exclusions) before presenting proposal
- [x] NER Agent iterates based on user feedback before approving
- [x] NER Agent only calls `approve_proposed_entities` when user explicitly approves
- [x] Approved output is `state["approved_entity_types"]` as a dict with source and description per type
- [x] Agent exposed via MCP as `kg_ner_extraction` tool
- [x] Multi-turn conversation works through MCP (conversation history persists)
- [x] MCP response includes pre-computation summary (files analyzed, sections found, well-known types detected)

## Definition of Done

- [x] Code implemented and working
- [x] Unit tests for all tool handlers in `tools/extraction_tools.py` (NER portion) - 10/10 passing
- [x] Interactive test script works end-to-end (`test_04_ner_extraction.py`)
- [x] Can complete full flow: analyze -> propose -> iterate -> approve
- [x] State correctly contains `approved_entity_types` after approval
- [x] MCP tool `kg_ner_extraction` works from Claude Code
- [x] Agent instructions follow spec in `docs/architecture/04_ner_extraction.md`
- [x] Code reviewed

## Technical Notes

### Architecture

The NER agent follows the same pattern as Schema Proposal (US005): pre-computed
context injected into the system prompt, with a small set of proposal/approval tools.

```
NerExtractionAgent (user-facing, MCP path)
  |
  +-> Pre-computed system prompt contains:
  |     +-> User goal (from state)
  |     +-> Well-known types (extracted from construction plan)
  |     +-> Structure-aware file previews (headings + first lines per section)
  |
  +-> Tools (4 total):
        +-> sample_file (collaborative: agent or user can trigger deeper reading)
        +-> set_proposed_entities (propose entity type list)
        +-> get_proposed_entities (retrieve current proposal)
        +-> approve_proposed_entities (finalize after user approval)
```

The agent starts with all context pre-computed in the system prompt. Structure-aware
previews show the heading hierarchy and first lines of every section, giving visibility
into the full document structure. The `sample_file` tool is available for reading
deeper into specific sections when the preview is insufficient.

### Files to Create/Update

```
tools/
  extraction_tools.py              # NEW: Tool schemas + handlers for Stages 4-5

agents/
  ner_extraction.py                # NEW: NER Extraction Agent

agents/__init__.py                 # UPDATE: Add NerExtractionAgent
tools/__init__.py                  # UPDATE: Add extraction tool exports

mcp_server/
  server.py                        # UPDATE: Add kg_ner_extraction tool

tests/
  unit/
    test_extraction_tools.py       # NEW: Unit tests for extraction handlers
  test_04_ner.py                   # NEW: Interactive test
```

### Tool Specifications

All tools live in `tools/extraction_tools.py`.

**Pre-computation functions (not tools — called from agent constructor):**

**build_markdown_context(state)** (calls `build_structured_preview` per file)
- Input: State dict with `approved_files`
- Effect: Parses markdown heading structure of each unstructured file, extracts
  first ~5 lines per section. Produces heading hierarchy with section previews
  and line numbers.
- Returns: Formatted string with structure-aware previews for all files
- Note: Shared with Fact Extraction Agent (US007). For a 380-line file with
  10 sections, produces ~60 lines of preview covering every section.

**build_well_known_types(state)**
- Input: State dict with `approved_construction_plan`
- Effect: Extracts node labels from construction plan entries
- Returns: Comma-separated string of labels (e.g., "Product, Assembly, Part, Supplier")

**Agent tools:**

**sample_file** (imported from `tools/file_tools.py`)
- Input: `file_path` (relative), `num_lines` (optional, default 100)
- Effect: Reads the first N lines of a file
- Returns: File content preview
- Note: Collaborative tool — the agent can call it when a section preview is
  insufficient, and the user can direct the agent to look at sections it missed.
  Reuses existing implementation from Stage 2 — no new code needed.

**set_proposed_entities**
- Input: `entity_types` (array of objects with `name`, `source`, `description`)
  - `name`: Entity type name in PascalCase
  - `source`: `"well_known"` or `"discovered"`
  - `description`: What this entity type represents and why it's relevant
- Precondition: Each name must start with uppercase (PascalCase validation)
- Precondition: Source must be `"well_known"` or `"discovered"`
- Effect: Sets `state["proposed_entity_types"]` to a dict keyed by name
- Returns: Success with proposed dict, or error with validation message

**get_proposed_entities**
- Input: None
- Effect: Reads `state["proposed_entity_types"]`
- Returns: Current proposed entity types dict (may be empty)

**approve_proposed_entities**
- Input: None
- Precondition: `proposed_entity_types` must exist and be non-empty
- Effect: Deep copies proposed to `state["approved_entity_types"]`
- Returns: Success with approved dict, or error if no proposal exists

### Pre-computation Pattern

Follows the `build_file_context` pattern from Schema Proposal (US005):

```python
class NerExtractionAgent:
    def __init__(self):
        self.tools = [TOOL_SET_PROPOSED_ENTITIES, ...]
        self.tool_handlers = {...}

    def run(self, message, state, conversation=None):
        # Pre-compute context for system prompt
        user_goal = format_user_goal(state)
        well_known_types = build_well_known_types(state)
        file_context = build_markdown_context(state)

        system_prompt = NER_SYSTEM_PROMPT.format(
            user_goal=user_goal,
            well_known_types=well_known_types,
            file_context=file_context,
        )

        return run_agent_sync(message, state, system_prompt,
                              self.tools, self.tool_handlers, conversation)
```

### Key Design Decisions

**Structure-aware previews as primary, sample_file as collaborative fallback**:
Unlike the course implementation (which starts blind and uses tools to gather all
context), the agent receives structure-aware previews in the system prompt. These
previews parse the markdown heading hierarchy and extract the first lines of every
section, giving the agent visibility into the full document structure regardless of
file length. The `sample_file` tool is available for deeper reading in two ways:
the agent can call it when a section preview is truncated or insufficient, and the
user can direct the agent to look at files or sections it missed. This is a
collaborative approach — the agent does its best, and the user fills gaps.
Line numbers in the preview allow targeted reads from either side.

**Structure-aware preview sizing**: ~5 lines per section means a file with 10
sections produces ~60 lines of preview. For 10 files with similar structure, that's
~600 lines of preview context — well within context window limits. Scales better
than flat line limits because the preview size scales with document complexity
(more sections), not document length.

**PascalCase validation in tool**: The `set_proposed_entities` handler validates
that each entity type starts with an uppercase letter. This catches common mistakes
before the agent presents results to the user.

**Shared tools file**: `extraction_tools.py` contains tools for both NER (US006) and
Fact Extraction (US007). The `build_markdown_context` function is shared. This matches
the CLAUDE.md file structure specification.

### Agent System Prompt (Key Points)

- Role: Named entity recognition specialist for knowledge graphs
- Pre-computed sections: User goal, well-known types, structure-aware file previews
- Two-approach guidance: Well-known entities (always include) + discovered entities
- Anti-patterns: Quantities as entities, overly specific types, goal-irrelevant types
- Disambiguation: "Assembly" component vs process warning
- Quality: PascalCase, 3-6 types, explain each with reasoning and text examples
- Workflow: Analyze -> propose -> present -> iterate -> approve on explicit user request

Full prompt in `docs/architecture/04_ner_extraction.md`.

### Example Output State

```json
{
  "approved_user_goal": {
    "kind_of_graph": "supply chain analysis",
    "description": "A multi-level bill of materials for manufactured products, useful for root cause analysis."
  },
  "approved_files": {
    "structured": [...],
    "unstructured": [
      {"path": "product_reviews/gothenburg_table_reviews.md", "reason": "..."},
      {"path": "product_reviews/stockholm_chair_reviews.md", "reason": "..."}
    ]
  },
  "approved_construction_plan": {
    "Product": {"construction_type": "node", "label": "Product", ...},
    "Assembly": {"construction_type": "node", "label": "Assembly", ...}
  },
  "proposed_entity_types": {
    "Product": {"source": "well_known", "description": "Products mentioned in reviews, bridges to existing Product nodes"},
    "Issue": {"source": "discovered", "description": "Problems reported by reviewers that support root cause analysis"},
    "Feature": {"source": "discovered", "description": "Product characteristics, useful for tracing which features cause issues"}
  },
  "approved_entity_types": {
    "Product": {"source": "well_known", "description": "Products mentioned in reviews, bridges to existing Product nodes"},
    "Issue": {"source": "discovered", "description": "Problems reported by reviewers that support root cause analysis"},
    "Feature": {"source": "discovered", "description": "Product characteristics, useful for tracing which features cause issues"}
  }
}
```

### MCP Integration

**kg_ner_extraction**
```json
{
  "name": "kg_ner_extraction",
  "description": "Send a message to the NER Extraction Agent. Pass the user's message exactly as written.",
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

Conversation key: `_ner_extraction_conversation`

Return value includes:
- Status with `has_proposed_entity_types` and `has_approved_entity_types` flags
- `pre_computation_summary`: What the agent was given before the conversation started
  - `files_analyzed`: Number and names of markdown files previewed
  - `total_sections`: Total sections found across all files
  - `well_known_types`: Entity types detected from the construction plan

### Data Directory Resolution

Same as previous stages: tools use `KG_DATA_DIR` environment variable, falling back to `NEO4J_IMPORT_DIR` or `./data`.

## Dependencies

- US001 (Core Agent Framework) must be complete
- US004 (File Suggestion Agent) must be complete — provides `approved_files`
- US005 (Schema Proposal Agent) must be complete — provides `approved_construction_plan`
- `approved_user_goal` must exist in state
- `approved_files` must exist in state (with unstructured files)
- `approved_construction_plan` must exist in state

## Out of Scope

- Fact type extraction (covered in US007)
- Actual entity instance extraction from text (covered in later stages)
- Graph construction (covered in later stages)
- Processing non-markdown unstructured files
- NLP-based entity detection (the agent uses LLM reasoning, not NLP libraries)

## Validation Scenario

### Scenario: Interactive NER extraction via MCP

1. Load state with `approved_user_goal`, `approved_files` (with unstructured), and `approved_construction_plan` from Stages 1-3
2. User: "Analyze the product reviews and propose entity types for extraction"
3. NER agent reviews pre-computed context (goal, well-known types, file previews)
4. Agent proposes entity types with explanations (well-known vs discovered)
5. Agent calls `set_proposed_entities(["Product", "Issue", "Feature"])`
6. Agent presents proposal to user with reasoning
7. User: "Approve"
8. Agent calls `approve_proposed_entities`
9. `state["approved_entity_types"]` contains `["Product", "Issue", "Feature"]`
10. Same flow works through Claude Code via `kg_ner_extraction` MCP tool
