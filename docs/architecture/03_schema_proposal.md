# Stage 3: Schema Proposal — Critic Pattern

## Purpose

Design the graph schema (node types, relationship types) based on approved files.
This stage uses a **multi-agent critic pattern** with automated refinement, faithfully
reproducing the Google ADK LoopAgent design in pure Python + Anthropic API.

## Architecture

Four components organized in a hierarchy:

```
USER (via MCP / interactive test)
  |
  v
SchemaProposalCoordinator          agents/schema_coordinator.py
  |  Tools: run_refinement_loop,
  |         get_proposed_construction_plan,
  |         approve_proposed_construction_plan
  |
  +---> run_refinement_loop()       pipelines/schema_loop.py
  |       |
  |       +---> SchemaProposalAgent  agents/schema_proposal.py
  |       |       (proposes nodes & relationships using 9 tools)
  |       |       (receives {feedback} injected into system prompt)
  |       |
  |       +---> SchemaCriticAgent    agents/schema_critic.py
  |       |       (validates with 5 read-only tools + submit_review)
  |       |       (calls submit_review with verdict "valid" or "retry")
  |       |
  |       +---> check_status         (if "valid" -> stop, else loop)
  |             (max 2 iterations)
  |
  +---> state["approved_construction_plan"]
```

### Component 1: Schema Proposal Agent

The inner agent that analyzes files and builds the construction plan. Receives critic
feedback injected into its system prompt via `{feedback}` placeholder. Uses a **fresh
conversation** each iteration (feedback comes through system prompt, not conversation history).

**System prompt** (from original Neo4j/Google ADK course):

```
You are an expert at knowledge graph modeling with property graphs. Propose an appropriate
schema by specifying construction rules which transform approved files into nodes or
relationships. The resulting schema should describe a knowledge graph based on the user goal.

Consider feedback if it is available:
<feedback>
{feedback}
</feedback>

HINTS FOR NODE VS RELATIONSHIP DETECTION:

Every file in the approved files list will become either a node or a relationship.
Determining whether a file likely represents a node or a relationship is based
on a hint from the filename (is it a single thing or two things) and the
identifiers found within the file.

Because unique identifiers are so important for determining the structure of the graph,
always verify the uniqueness of suspected unique identifiers using the 'search_file' tool.

General guidance for identifying a node or a relationship:
- If the file name is singular and has only 1 unique identifier it is likely a node
- If the file name is a combination of two things, it is likely a full relationship
- If the file name sounds like a node, but there are multiple unique identifiers,
  that is likely a node with reference relationships

Design rules for nodes:
- Nodes will have unique identifiers.
- Nodes _may_ have identifiers that are used as reference relationships.

Design rules for relationships:
- Relationships appear in two ways: full relationships and reference relationships.

Full relationships:
- Appear in dedicated relationship files, often having a filename that references
  two entities
- Typically have references to a source and destination node
- _Do not have_ unique identifiers, but instead have references to the primary
  keys of the source and destination nodes
- The absence of a single, unique identifier is a strong indicator that a file
  is a full relationship

Reference relationships:
- Appear as foreign key references in node files
- Foreign key column names often hint at the destination node and relationship type
- May be hierarchical container relationships (parent-child, "has", "contains")
- May be peer relationships (self-reference, "knows", "see also")

The resulting schema should be a connected graph, with no isolated components.

CHAIN OF THOUGHT DIRECTIONS:

Prepare for the task:
- get the user goal using the 'get_approved_user_goal' tool
- get the list of approved files using the 'get_approved_files' tool
- get the current construction plan using the 'get_proposed_construction_plan' tool

Think carefully, using tools to perform actions:
1. For each approved file, consider whether it represents a node or relationship.
   Check the content for potential unique identifiers using the 'sample_file' tool.
2. For each identifier, verify that it is unique by using the 'search_file' tool.
3. Use the node vs relationship guidance for deciding file type.
4. For a node file, propose a node construction using 'propose_node_construction'.
5. If the node contains a reference relationship, use 'propose_relationship_construction'.
6. For a relationship file, use 'propose_relationship_construction'.
7. If you need to remove a construction, use 'remove_node_construction' or
   'remove_relationship_construction'.
8. When done, use 'get_proposed_construction_plan' to present the plan.
```

**Tools (9):** get_approved_user_goal, get_approved_files, get_proposed_construction_plan,
sample_file, search_file, propose_node_construction, propose_relationship_construction,
remove_node_construction, remove_relationship_construction

**No approval tool** — only the coordinator can approve.

### Component 2: Schema Critic Agent

Validates the proposed schema with read-only tools plus a structured `submit_review` tool.
The verdict and problems are written to state by the tool, avoiding fragile text parsing.
The critic's full text response is also stored as `state["feedback"]` by the refinement
loop for injection into the proposal agent's next iteration.

**System prompt** (adapted from original course, updated for structured verdict):

```
You are an expert at knowledge graph modeling with property graphs.
Criticize the proposed schema for relevance to the user goal and approved files.

VALIDATION RULES:

- Are unique identifiers actually unique? Use 'search_file' to validate.
  Composite identifiers are not acceptable.
- Could any nodes be relationships instead? Double-check that unique identifiers
  are unique and not references to other nodes.
- Can you manually trace through the source data to find the necessary information
  for answering a hypothetical question?
- Is every node in the schema connected? What relationships could be missing?
  Every node should connect to at least one other node.
- Are hierarchical container relationships missing?
- Are any relationships redundant? A relationship between two nodes is redundant
  if it is semantically equivalent to or the inverse of another relationship.

CHAIN OF THOUGHT DIRECTIONS:

Prepare for the task:
- get the user goal using the 'get_approved_user_goal' tool
- get the list of approved files using the 'get_approved_files' tool
- get the construction plan using the 'get_proposed_construction_plan' tool
- use the 'sample_file' and 'search_file' tools to validate the schema design

Think carefully:
1. Analyze each construction rule in the proposed construction plan.
2. Use tools to validate the construction rules for relevance and correctness.
3. When you have completed your analysis, you MUST call the 'submit_review' tool:
   - If the schema is correct, call submit_review with verdict "valid" and an empty
     problems list.
   - If the schema has problems, call submit_review with verdict "retry" and a list
     of specific problems to fix.
```

**Tools (6):** get_approved_user_goal, get_approved_files,
get_proposed_construction_plan, sample_file, search_file, **submit_review**

The `submit_review` tool replaces the original free-text "valid"/"retry" convention
from the ADK version. This eliminates fragile string parsing in the refinement loop:

```python
# submit_review tool schema
submit_review:
  verdict: "valid" | "retry"     # enum, no ambiguity
  problems: ["problem 1", ...]   # empty list if valid

# handler stores structured result in state
def handle_submit_review(state, verdict, problems):
    state["_critic_verdict"] = verdict    # "valid" or "retry"
    state["_critic_problems"] = problems  # list of strings
```

**Why this departs from the original:** The ADK version relied on parsing the critic's
text response for the word "valid". With the Anthropic API, tool use gives us structured
output natively. The refinement loop checks `state["_critic_verdict"] == "valid"` instead
of guessing from free text.

### Component 3: Refinement Loop

Python function replacing the ADK `LoopAgent` + `CheckStatusAndEscalate`:

```python
def run_refinement_loop(state, message=..., max_iterations=2):
    state["feedback"] = state.get("feedback", "")
    state["_refinement_trace"] = []

    for iteration in range(max_iterations):
        # 1. Run proposal agent (fresh conversation, feedback in system prompt)
        response, state, _ = proposal_agent.run(message, state, conversation=None)

        # 2. Run critic agent (fresh conversation)
        critic_response, state, _ = critic_agent.run("Validate...", state, conversation=None)

        # 3. Read structured verdict from state (set by submit_review tool)
        verdict = state.get("_critic_verdict", "retry")
        problems = state.get("_critic_problems", [])

        # 4. Build feedback string for next iteration
        state["feedback"] = critic_response

        # 5. Record trace for debugging
        state["_refinement_trace"].append({
            "iteration": iteration + 1,
            "proposal_summary": response[:500],
            "critic_verdict": verdict,
            "critic_problems": problems,
            "critic_response": critic_response[:500],
        })

        # 6. Check status (equivalent to CheckStatusAndEscalate)
        if verdict == "valid":
            break

    return (summary, state)
```

Key behaviors:
- Each sub-agent gets a **fresh conversation** per iteration (no memory between loops)
- Proposal agent receives feedback through `{feedback}` in its system prompt
- Critic uses the `submit_review` tool to record a structured verdict (see Component 2)
- Loop checks `state["_critic_verdict"]` instead of parsing free text
- Every iteration is recorded in `state["_refinement_trace"]` for debugging
- Stops when verdict is `"valid"` or max iterations (2) reached

#### Refinement tracing

The loop stores a trace in `state["_refinement_trace"]` so that inner agent behavior
can be inspected after the loop completes. Each entry records:

```python
{
    "iteration": 1,
    "proposal_summary": "First 500 chars of proposal agent response...",
    "critic_verdict": "valid" | "retry",
    "critic_problems": ["problem 1", "problem 2"],   # empty if valid
    "critic_response": "First 500 chars of critic agent response...",
}
```

This is essential for debugging since inner conversations are discarded each iteration.

#### Direct usage (without coordinator)

The refinement loop can be called directly for tests and pipeline scripts,
bypassing the coordinator:

```python
# Direct path (tests, pipelines) — no coordinator overhead:
from pipelines.schema_loop import run_refinement_loop
summary, state = run_refinement_loop(state)

# MCP path (user interaction) — coordinator manages conversation:
coordinator = SchemaProposalCoordinator()
response, state, conversation = coordinator.run(message, state, conversation)
```

This avoids an unnecessary Claude API call when the coordinator's decision is
deterministic (e.g., in automated tests or the full pipeline).

### Component 4: Schema Proposal Coordinator

User-facing agent that wraps the refinement loop as a tool:

```
You are a coordinator for the schema proposal process. Use tools to propose
a schema to the user.

WORKFLOW:
1. Use 'run_refinement_loop' to produce or update a proposed schema.
2. Use 'get_proposed_construction_plan' to get the construction rules.
3. Present the proposed schema and construction rules to the user for approval.
4. If the user disapproves, consider their feedback and run the loop again.
5. If the user approves, use 'approve_proposed_construction_plan' to record it.

GUIDANCE:
- Always run the refinement loop first before presenting results
- Present the schema clearly: nodes with labels, IDs, properties;
  relationships with types, source/target nodes, properties
- Ask the user explicitly if they approve the schema
- Only approve when user explicitly says 'approve', 'looks good', etc.
```

**Tools (3):** run_refinement_loop, get_proposed_construction_plan,
approve_proposed_construction_plan

Maintains conversation history across user turns (multi-turn via MCP sessions).

## Input

```python
state["approved_user_goal"] = {
    "kind_of_graph": "supply chain analysis",
    "graph_description": "A multi-level bill of materials for manufactured products..."
}
state["approved_files"] = {
    "structured": [
        {"path": "products.csv", "reason": "Product entities"},
        {"path": "suppliers.csv", "reason": "Supplier entities"},
        ...
    ],
    "unstructured": [...]
}
```

## Output

```python
state["approved_construction_plan"] = {
    "Product": {
        "construction_type": "node",
        "source_file": "products.csv",
        "label": "Product",
        "unique_column_name": "product_id",
        "properties": ["product_name", "price", "description"]
    },
    "Supplier": {
        "construction_type": "node",
        "source_file": "suppliers.csv",
        "label": "Supplier",
        "unique_column_name": "supplier_id",
        "properties": ["name", "specialty", "city", "country"]
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
}
```

## Tools Reference

### Reused from Stage 2

**get_approved_user_goal** — Retrieve the approved user goal from state.

**sample_file** — Read first N lines of a file to inspect content.

### New Tools

**get_approved_files**
- Input: None
- Effect: Reads `state["approved_files"]` and extracts file paths
- Returns: structured_files, unstructured_files, all_files lists

**search_file**
- Input: `file_path` (relative), `query` (string)
- Effect: Case-insensitive line-by-line search in text file
- Returns: Matching lines with line numbers, metadata
- Purpose: Validate column names exist, check data patterns
- Security: Path traversal prevention (same as sample_file)

**propose_node_construction**
- Input: `approved_file`, `proposed_label`, `unique_column_name`, `proposed_properties`
- Precondition: Validates `unique_column_name` exists in file via search_file
- Effect: Adds node rule to `state["proposed_construction_plan"][proposed_label]`
- Returns: The node construction rule

**propose_relationship_construction**
- Input: `approved_file`, `proposed_relationship_type`, `from_node_label`,
  `from_node_column`, `to_node_label`, `to_node_column`, `proposed_properties`
- Precondition: Validates both column names exist in file via search_file
- Effect: Adds relationship rule to `state["proposed_construction_plan"][proposed_relationship_type]`
- Returns: The relationship construction rule

**remove_node_construction**
- Input: `node_label`
- Effect: Removes node rule from proposed plan by label
- Returns: Success (idempotent if not found)

**remove_relationship_construction**
- Input: `relationship_type`
- Effect: Removes relationship rule from proposed plan by type
- Returns: Success (idempotent if not found)

**get_proposed_construction_plan**
- Input: None
- Effect: Reads `state["proposed_construction_plan"]`
- Returns: Full plan with node_count and relationship_count summary

**approve_proposed_construction_plan**
- Input: None
- Precondition: `state["proposed_construction_plan"]` exists and is non-empty
- Effect: Copies proposed to `state["approved_construction_plan"]`
- Returns: Success with the approved plan

### Critic-Only Tool

**submit_review**
- Input: `verdict` (enum: "valid" or "retry"), `problems` (array of strings)
- Effect: Stores `state["_critic_verdict"]` and `state["_critic_problems"]`
- Returns: Confirmation of recorded verdict
- Note: The refinement loop reads these state keys to decide whether to stop or iterate

### Coordinator-Only Tool

**run_refinement_loop**
- Input: `user_feedback` (optional string)
- Effect: Runs the proposal-critic loop (2 iterations max), populates
  `state["proposed_construction_plan"]`
- Returns: Summary of loop result, node/relationship counts

## Example Conversation

```
User: Design the schema for our supply chain knowledge graph

Coordinator: [Calls run_refinement_loop]
  |
  +-> Proposal Agent:
  |     [Calls get_approved_user_goal]
  |     [Calls get_approved_files]
  |     [Calls sample_file("products.csv")]  -- sees product_id, product_name, price
  |     [Calls search_file("products.csv", "product_id")]  -- verifies uniqueness
  |     [Calls propose_node_construction("products.csv", "Product", "product_id", [...])]
  |     ... (analyzes all 5 files) ...
  |     [Calls get_proposed_construction_plan]  -- presents result
  |
  +-> Critic Agent:
  |     [Calls get_proposed_construction_plan]
  |     [Calls search_file to validate identifiers]
  |     [Calls submit_review(verdict="valid", problems=[])]
  |
  +-> Loop exits

Coordinator: [Calls get_proposed_construction_plan]

Here's the proposed schema:

**Nodes:**
1. Product (from products.csv) - key: product_id
2. Assembly (from assemblies.csv) - key: assembly_id
3. Part (from parts.csv) - key: part_id
4. Supplier (from suppliers.csv) - key: supplier_id

**Relationships:**
1. Assembly -[PART_OF]-> Product (from assemblies.csv, via product_id)
2. Part -[COMPONENT_OF]-> Assembly (from parts.csv, via assembly_id)
3. Part -[SUPPLIED_BY]-> Supplier (from part_supplier_mapping.csv)

Would you like to approve this schema?

User: Yes, approve it

Coordinator: [Calls approve_proposed_construction_plan]

Construction plan approved! 4 node types, 3 relationship types.
Ready for entity extraction.
```

## File Structure

```
tools/
  schema_tools.py              # NEW: 9 tool schemas + handlers

agents/
  schema_proposal.py           # NEW: Inner proposal agent (9 tools, no approval)
  schema_critic.py             # NEW: Inner critic agent (5 read-only tools)
  schema_coordinator.py        # NEW: User-facing coordinator (3 tools)

pipelines/
  __init__.py                  # NEW: Package init
  schema_loop.py               # NEW: run_refinement_loop()

mcp_server/
  server.py                    # UPDATE: Add kg_schema_proposal tool

tests/
  unit/
    test_schema_tools.py       # NEW: Unit tests for handlers
  test_03_verify.py            # NEW: Automated verification test
  test_03_schema_proposal.py   # NEW: Interactive test
```

## Naming Conventions

- **Node labels:** PascalCase — `Product`, `Supplier`, `Part`, `Assembly`
- **Relationship types:** SCREAMING_SNAKE_CASE — `SUPPLIED_BY`, `PART_OF`, `COMPONENT_OF`
- **Unique identifiers:** Every node type must have exactly one unique column
- **Connected graph:** No isolated nodes; every node connects to at least one other

## Success Criteria

1. Proposal agent analyzes ALL approved CSV files
2. Proposal agent validates column names via search_file before proposing
3. Critic agent independently validates the proposal
4. Refinement loop converges within 2 iterations
5. Schema follows naming conventions
6. Every node type has a unique identifier
7. Relationships correctly reference existing node types
8. Coordinator presents results clearly and handles user feedback
9. Final approved plan is logically complete for the stated goal

## Common Issues

1. **Missing relationships** — Proposal hints emphasize detecting reference relationships in node files (foreign keys like `product_id` in `assemblies.csv`)
2. **Wrong relationship direction** — Critic validates by tracing through source data
3. **Column name typos** — Both agents use search_file to validate columns exist
4. **Composite identifiers** — Critic explicitly rejects these as unacceptable
5. **Isolated nodes** — Both agents check for graph connectivity
6. **Redundant relationships** — Critic checks for semantically equivalent or inverse relationships
