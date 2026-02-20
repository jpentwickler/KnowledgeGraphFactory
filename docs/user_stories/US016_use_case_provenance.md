# US016: Use Case Provenance

## User Story

**As a** KG-Factory User
**I want** every node in my knowledge graph to carry a `_use_case` identifier and entity resolution to be scoped to the current use case
**So that** I can build multiple use cases into the same Neo4j database without collision and have the foundation for future cross-use-case integration

## Story Points: 2

## Status: Not Started

## Context

This user story implements the **foundation layer** described in `docs/architecture/09_multi_use_case_integration.md`. It does NOT implement the merge workflow, the `kg_merge` tool, or the `merged/` directory structure. Those are deferred until the first actual merge is needed.

The goal is to lay minimal groundwork so that:
- Every node can be traced to the use case that created it
- Multiple use cases can coexist in the same Neo4j database without interfering
- Entity resolution does not create false matches across use cases
- No existing functionality is broken

## Acceptance Criteria

### Use Case Identifier in State

- [ ] User Intent agent captures a `use_case` identifier as part of the proposed goal
- [ ] `use_case` is a short, snake_case string (e.g., `"supply_chain"`, `"customer_experience"`)
- [ ] Stored in `state["approved_user_goal"]["use_case"]` after approval
- [ ] Also accessible as `state["use_case"]` (convenience alias set on approval)
- [ ] Tool schema for `set_proposed_goal` includes `use_case` as a required property
- [ ] Agent system prompt includes guidance for generating the identifier

### Domain Graph Provenance

- [ ] `import_nodes()` in `domain_builder.py` adds `_use_case` to every node
- [ ] Property set via Cypher parameter (not string interpolation)
- [ ] Reads use case from `state["use_case"]`
- [ ] `import_relationships()` does NOT tag relationships (only nodes carry provenance)
- [ ] Existing graphs built without `_use_case` continue to work (property is additive)

### Text Graph Provenance

- [ ] After `SimpleKGPipeline.run_async()` completes for a file, a post-processing Cypher query tags all newly created nodes that lack `_use_case`
- [ ] Tags Chunk nodes, Entity nodes (`__Entity__`), and Document nodes
- [ ] Uses `WHERE n._use_case IS NULL` to avoid retagging existing nodes
- [ ] Reads use case from `state["use_case"]`

### Scoped Entity Resolution

- [ ] `correlate_subject_and_domain_nodes()` in `entity_resolution.py` adds `_use_case` scoping to its WHERE clause
- [ ] Only matches entities and domain nodes with the same `_use_case` value
- [ ] Prevents false CORRESPONDS_TO links across use cases
- [ ] Works correctly when `_use_case` is NULL (backward compatibility with pre-US016 graphs)

### Backward Compatibility

- [ ] All existing unit tests pass without modification
- [ ] Graphs built before US016 (nodes without `_use_case`) continue to work
- [ ] Entity resolution with NULL `_use_case` on both sides still matches (NULL = NULL)
- [ ] `kg_query` strategies work regardless of whether `_use_case` is present

## Definition of Done

- [ ] Code implemented and working
- [ ] Unit tests for use_case propagation in domain builder
- [ ] Unit tests for use_case tagging in text builder post-processing
- [ ] Unit tests for scoped entity resolution (same use case matches, different use case does not)
- [ ] Unit tests for backward compatibility (NULL _use_case)
- [ ] All existing tests still pass
- [ ] Interactive test demonstrates two use cases coexisting in same Neo4j
- [ ] Code reviewed
- [ ] Documentation in code (docstrings for modified functions)

## Technical Notes

### Architecture

```
kg_user_intent(message)
  |
  +-> UserIntentAgent.run()
  |     +-> set_proposed_goal(kind_of_graph, graph_description, use_case)
  |           +-> state["proposed_user_goal"] = {..., "use_case": "supply_chain"}
  |
  +-> User approves
        +-> state["approved_user_goal"]["use_case"] = "supply_chain"
        +-> state["use_case"] = "supply_chain"   (convenience alias)

kg_build_graph(scope="structured")
  |
  +-> build_domain_graph(state, driver)
        +-> import_nodes(driver, spec, data_dir, use_case=state["use_case"])
              +-> UNWIND $rows AS row
                  MERGE (n:Label {...})
                  SET n += row, n._use_case = $use_case

kg_build_graph(scope="unstructured")
  |
  +-> build_text_graph(state, driver)
        +-> _process_single_file(driver, state, file_path, data_dir)
              +-> pipeline.run_async(file_path=...)
              +-> _tag_use_case(driver, state["use_case"])   <-- NEW post-processing
                    +-> MATCH (n) WHERE n._use_case IS NULL
                        SET n._use_case = $use_case

kg_build_graph(scope="resolve")
  |
  +-> resolve_entities(state, driver)
        +-> correlate_subject_and_domain_nodes(driver, ...)
              +-> MATCH (entity:Label:__Entity__), (domain:Label)
                  WHERE NOT domain:__Entity__
                    AND entity._use_case = domain._use_case   <-- NEW filter
                    AND apoc.text.jaroWinklerDistance(...) < $distance
                  MERGE (entity)-[:CORRESPONDS_TO]->(domain)
```

### Files to Modify

```
tools/intent_tools.py         # Add use_case to set_proposed_goal schema and handler
agents/user_intent.py         # Add use_case guidance to system prompt
pipelines/domain_builder.py   # Add _use_case to UNWIND import query
pipelines/text_builder.py     # Add post-processing _use_case tagging
pipelines/entity_resolution.py # Scope WHERE clause to same _use_case
```

### Files to Create

```
tests/unit/test_use_case_provenance.py  # Unit tests for all 4 changes
```

### Component Specifications

#### 1. Tool Schema Change (in `tools/intent_tools.py`)

Add `use_case` property to `TOOL_SET_PROPOSED_GOAL`:

```python
TOOL_SET_PROPOSED_GOAL = create_tool_schema(
    name="set_proposed_goal",
    properties={
        "kind_of_graph": {
            "type": "string",
            "description": "Short label for the type of graph"
        },
        "graph_description": {
            "type": "string",
            "description": "Detailed description of the graph's purpose"
        },
        "use_case": {                                          # NEW
            "type": "string",
            "description": "Short snake_case identifier for this use case "
                "(e.g., 'supply_chain', 'customer_experience', 'procurement'). "
                "Used to tag all graph nodes for multi-use-case support."
        }
    },
    required=["kind_of_graph", "graph_description", "use_case"]
)
```

Update handler to include `use_case` in the stored dict.

#### 2. State Convenience Alias (in `mcp_server/server.py`)

When user goal is approved, also set top-level alias:

```python
# After approval of user_goal
if "approved_user_goal" in state and "use_case" in state["approved_user_goal"]:
    state["use_case"] = state["approved_user_goal"]["use_case"]
```

#### 3. Domain Builder Change (in `pipelines/domain_builder.py`)

Modify the UNWIND query in `import_nodes()`:

```python
# Current
query = f"""
UNWIND $rows AS row
MERGE (n:{label} {{{unique_col}: trim(toString(row.{unique_col}))}})
SET n += row
RETURN count(n) as created
"""

# Updated
query = f"""
UNWIND $rows AS row
MERGE (n:{label} {{{unique_col}: trim(toString(row.{unique_col}))}})
SET n += row, n._use_case = $use_case
RETURN count(n) as created
"""
```

Pass `use_case` as a query parameter alongside `rows`.

#### 4. Text Builder Post-Processing (in `pipelines/text_builder.py`)

Add helper function called after `pipeline.run_async()`:

```python
def _tag_use_case(driver, use_case: str):
    """Tag all nodes without _use_case with the current use case."""
    if not use_case:
        return
    driver.execute_query(
        "MATCH (n) WHERE n._use_case IS NULL SET n._use_case = $use_case",
        {"use_case": use_case}
    )
```

Call in `_process_single_file()` after the pipeline completes.

#### 5. Entity Resolution Scoping (in `pipelines/entity_resolution.py`)

Extend the WHERE clause in `correlate_subject_and_domain_nodes()`:

```cypher
-- Current
MATCH (entity:{label}:`__Entity__`), (domain:{label})
WHERE NOT domain:`__Entity__`
  AND apoc.text.jaroWinklerDistance(entity[$entityKey], domain[$domainKey]) < $distance

-- Updated
MATCH (entity:{label}:`__Entity__`), (domain:{label})
WHERE NOT domain:`__Entity__`
  AND (entity._use_case = domain._use_case OR
       (entity._use_case IS NULL AND domain._use_case IS NULL))
  AND apoc.text.jaroWinklerDistance(entity[$entityKey], domain[$domainKey]) < $distance
```

The `OR (... IS NULL AND ... IS NULL)` clause ensures backward compatibility with graphs built before US016.

## Dependencies

- US001: Core Agent Framework (state management)
- US002: User Intent Agent (goal schema)
- US008: Domain Graph Builder (import_nodes)
- US009: Text Graph Builder (SimpleKGPipeline)
- US009: Entity Resolution (correlate functions)

## Out of Scope

- `kg_merge` MCP tool (deferred to first merge)
- Merged state directory (`merged/`) (deferred to first merge)
- Cross-use-case concept matching (deferred to first merge)
- Retroactive tagging of existing graphs (manual one-time Cypher, not automated)
- Use case as a Neo4j label (only a property, not a label)
- Filtering `kg_query` results by use case (queries span all use cases by default)

## Validation Scenarios

### Scenario 1: Single Use Case (Regression)

1. Run standard pipeline with furniture supply chain data
2. Verify `state["use_case"]` = `"supply_chain"` after goal approval
3. Build domain graph, verify all nodes have `_use_case: "supply_chain"`
4. Build text graph, verify chunks and entities have `_use_case: "supply_chain"`
5. Run entity resolution, verify CORRESPONDS_TO links created as before
6. Run `kg_query`, verify results include `_use_case` in node properties

### Scenario 2: Two Use Cases in Same Neo4j

1. Build supply chain use case (use_case = "supply_chain")
2. Switch to new state directory, build customer experience use case (use_case = "customer_experience")
3. Both use cases create `:Product` nodes
4. Verify supply chain Products have `_use_case: "supply_chain"`
5. Verify customer experience Products have `_use_case: "customer_experience"`
6. Run entity resolution for customer experience -- verify it only creates CORRESPONDS_TO links within customer_experience nodes, not across to supply_chain nodes
7. Query `MATCH (n:Product) RETURN n._use_case, count(*)` -- verify both groups exist

### Scenario 3: Backward Compatibility

1. Load a Neo4j database with nodes that have no `_use_case` property
2. Run entity resolution -- verify it still works (NULL = NULL matches)
3. Run `kg_query` -- verify strategies return results normally
4. Build a new use case into the same database -- new nodes get `_use_case`, old ones remain NULL
