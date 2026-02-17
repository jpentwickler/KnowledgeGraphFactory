# US012: Competency Questions

## User Story

**As a** knowledge graph designer using KG-Factory
**I want** to define, review, and manage competency questions as part of the knowledge graph design
**So that** the graph has clear, testable requirements that scope its design, guide downstream agents, and serve as the basis for later evaluation

## Story Points: 5

## Background

Competency questions (CQs) are detailed business questions that the final knowledge graph must be able to answer. They function as requirements that:

- **Define scope**: determine which concepts, entities, and relationships are relevant
- **Guide design**: help downstream agents (schema, NER, fact extraction) identify what to model
- **Enable evaluation**: act as test cases to verify correctness and completeness of the built graph

CQs are a living artifact. They are established early (during intent definition) but can be revisited, refined, added to, or pruned at any point during the knowledge graph construction process.

## Acceptance Criteria

### CQ Creation (within User Intent Agent)

- [ ] User Intent Agent elicits competency questions as part of the goal-definition conversation
- [ ] Agent proposes CQs based on the domain and use cases discussed with the user
- [ ] User can add, modify, or reject individual proposed CQs in dialogue with the agent
- [ ] Agent uses `set_proposed_competency_questions` tool to save CQ proposals to state
- [ ] Agent only calls `approve_proposed_competency_questions` after explicit user approval
- [ ] CQs are stored as a separate first-class artifact (`approved_competency_questions`), not nested inside `approved_user_goal`
- [ ] Each CQ has: question text, category, and priority
- [ ] Agent uses plain language ("What questions should your graph answer?") rather than jargon

### CQ Management (dedicated MCP tool, anytime)

- [ ] `kg_competency_questions(message)` MCP tool allows CQ management at any pipeline stage
- [ ] Supports adding new CQs, modifying existing CQs, and deleting CQs
- [ ] Agent reads current pipeline state to provide context-aware suggestions (e.g., "based on your schema, you might also want to ask...")
- [ ] Changes follow propose/approve pattern: modifications are proposed, user approves
- [ ] Management tool works independently of User Intent conversation history

### CQ Critic (new scope on existing critic)

- [ ] `kg_critic(scope="competency")` validates CQs against current pipeline artifacts
- [ ] After schema proposal: checks whether the schema can support each CQ
- [ ] After NER/fact extraction: checks whether entity and fact types cover CQ requirements
- [ ] Critic identifies gaps (CQs that cannot be answered with current design) and surfeit (modeled elements not tied to any CQ)
- [ ] Critic does NOT approve or modify CQs, only reports findings

### Downstream Agent Integration

- [ ] File Suggestion Agent reads `approved_competency_questions` to assess file relevance
- [ ] Schema Proposal Agent references CQs when designing the construction plan
- [ ] NER Extraction Agent considers CQs when proposing entity types
- [ ] Fact Extraction Agent considers CQs when proposing fact types

## Definition of Done

- [ ] Code implemented and working
- [ ] Unit tests for CQ tool handlers (intent_tools.py extensions)
- [ ] Unit tests for CQ management tool handlers
- [ ] Unit tests for competency critic scope
- [ ] Interactive test verifies full flow: elicit CQs during intent → approve → revisit later → critic validates
- [ ] Existing User Intent tests still pass (backward compatible)
- [ ] Downstream agent system prompts updated to reference CQs
- [ ] MCP server exposes `kg_competency_questions` tool
- [ ] State correctly contains `approved_competency_questions` after approval
- [ ] Code reviewed

## Technical Notes

### Design Decision: Born in Intent, Managed Independently

CQs are **created** during the User Intent conversation because "what do you want to build?" and "what should it answer?" are the same mental activity for the user. However, CQs are stored as a **separate artifact** and can be **managed independently** via a dedicated MCP tool, because they are a living artifact that evolves throughout the pipeline.

### Files to Modify

```
agents/
└── user_intent.py          # Extended system prompt to elicit CQs

tools/
└── intent_tools.py         # New tools: set/approve competency questions

mcp_server/
└── server.py               # New tool: kg_competency_questions

agents/
├── file_suggestion.py      # System prompt: reference CQs
├── schema_proposal.py      # System prompt: reference CQs
├── ner_extraction.py       # System prompt: reference CQs
└── fact_extraction.py      # System prompt: reference CQs

agents/
└── schema_critic.py        # New scope: "competency"
```

### Files to Create

```
tools/
└── competency_tools.py     # CQ management tool handlers (add/modify/delete)

agents/
└── competency_questions.py # Lightweight agent for CQ management
```

### Tool Specifications

**set_proposed_competency_questions** (User Intent Agent)
- Input: `questions` (list of {question, category, priority})
- Effect: Sets `state["proposed_competency_questions"]`
- Returns: Success confirmation with question count

**approve_proposed_competency_questions** (User Intent Agent)
- Input: None
- Precondition: `state["proposed_competency_questions"]` exists
- Effect: Copies proposed to `state["approved_competency_questions"]`
- Returns: Success with approved questions

**add_competency_question** (CQ Management Agent)
- Input: `question` (string), `category` (string), `priority` (string)
- Effect: Adds to `state["proposed_competency_questions"]`
- Returns: Success with updated list

**modify_competency_question** (CQ Management Agent)
- Input: `question_id` (string), updated fields
- Effect: Updates specific CQ in `state["proposed_competency_questions"]`
- Returns: Success with updated question

**delete_competency_question** (CQ Management Agent)
- Input: `question_id` (string)
- Effect: Removes CQ from `state["proposed_competency_questions"]`
- Returns: Success confirmation

**approve_competency_question_changes** (CQ Management Agent)
- Input: None
- Precondition: Proposed changes exist
- Effect: Copies proposed to `state["approved_competency_questions"]`
- Returns: Success with approved questions

### CQ Data Structure

```json
{
  "proposed_competency_questions": {
    "CQ1": {
      "question": "What products would be affected if supplier X experiences supply disruptions?",
      "category": "supply_chain_impact",
      "priority": "high"
    },
    "CQ2": {
      "question": "Which suppliers provide the most components across all product lines?",
      "category": "sourcing_optimization",
      "priority": "high"
    },
    "CQ3": {
      "question": "What is the average customer sentiment for products that use components from supplier X?",
      "category": "cross_analysis",
      "priority": "medium"
    }
  },
  "approved_competency_questions": { }
}
```

### Critic Scope: "competency"

The competency critic reads `approved_competency_questions` and validates against available artifacts:

- If `approved_construction_plan` exists: check schema coverage per CQ
- If `approved_entity_types` exists: check entity type coverage per CQ
- If `approved_fact_types` exists: check fact type coverage per CQ
- Reports per-CQ status: covered / partially covered / not covered
- Identifies modeled elements not linked to any CQ (potential over-engineering)

### MCP Tool: kg_competency_questions

```python
@mcp.tool
@mcp_traceable(name="mcp.kg_competency_questions")
def kg_competency_questions(message: str) -> dict:
    """Manage competency questions for the knowledge graph.

    Competency questions define what the knowledge graph must be able to
    answer. Use this tool to add, modify, delete, or review questions
    at any point in the pipeline.

    Call this after Stage 1 (User Intent) to refine questions, or at
    any later stage as your understanding of the domain evolves.

    Args:
        message: Your message about competency questions.

    Returns:
        Dictionary with agent response and current CQ status.
    """
```

## Dependencies

- US001 (Core Agent Framework) must be complete
- US002 (User Intent Agent) must be complete
- US003 (MCP Server) must be complete
- US005 (Schema Proposal + Critic) must be complete (for critic scope extension)

## Out of Scope

- Automated Cypher generation from CQs (future evaluation feature)
- Running CQs against the built graph as validation (future evaluation feature)
- CQ coverage metrics or dashboards
- Automated CQ suggestion from data file analysis (could be a future enhancement)
