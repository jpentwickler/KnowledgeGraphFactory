# US023: Canonical Graph Schema for Query Generation

## User Story

**As a** KG-Factory User
**I want** the query system to have a single, unambiguous schema model that informs all Cypher generation
**So that** queries are correct on the first attempt, without retries or manual context injection, regardless of graph domain or complexity

## Story Points: 8

## Status: Not Started

## Context

The `kg_query` tool (US013) generates Cypher queries via an LLM that receives
graph schema information in its system prompt. This schema is currently
assembled ad-hoc from 5 state keys by 8 extraction functions, formatted by 4
helpers, and injected into 3 independent prompts. Each prompt constructs its
own schema view with its own notation.

This fragile architecture causes systemic Cypher generation failures:
- Relationship properties placed on wrong objects (NULL results)
- String values compared lexicographically instead of parsed numerically
- Relationship directions reversed
- Non-existent relationship types hallucinated

Observed during testing: **4 LLM calls needed to answer 1 cross-layer
question.** The final call only succeeded because the caller manually provided
schema details via the `context` parameter.

Every fix has been a patch to a specific prompt for a specific failure mode.
This story replaces the ad-hoc approach with a canonical schema model that
eliminates the class of "ambiguous schema communication" bugs.

See `docs/architecture/14_canonical_graph_schema.md` for the full design and
test catalog.

## Acceptance Criteria

### Phase 1: Schema Model and Cypher Renderer

#### GraphSchema Data Model

- [ ] New file `core/graph_schema.py` with dataclasses:
  - `PropertyInfo(name, sample, inferred_type, parse_hint)`
  - `NodeSchema(label, layer, properties: list[PropertyInfo])`
  - `RelationshipSchema(type, from_label, to_label, layer, properties: list[PropertyInfo])`
  - `GraphSchema(nodes, relationships, overlapping_labels)`
- [ ] `layer` field values: `"domain"` for structured data nodes/rels, `"text"` for text-extracted nodes/rels, `"bridge"` for CORRESPONDS_TO
- [ ] `PropertyInfo.inferred_type` values: `"string"`, `"integer"`, `"float"`, `"boolean"`
- [ ] `PropertyInfo.parse_hint` is a Cypher expression template with `x` as placeholder, or `None` if value can be used directly

#### Format Detection

- [ ] `_detect_format(sample)` function infers type and parse hint from sample values
- [ ] Handles currency strings: `"$36.06"` -> `("string", "toFloat(replace(x, '$', ''))")`
- [ ] Handles fraction strings: `"5/5"` -> `("string", "toFloat(split(x, '/')[0])")`
- [ ] Handles boolean strings: `"true"` / `"false"` -> `("boolean", None)`
- [ ] Handles integer strings: `"29"` -> `("integer", None)`
- [ ] Handles float strings: `"3.14"` -> `("float", None)`
- [ ] Handles plain strings: `"Stockholm"` -> `("string", None)`
- [ ] Handles `None` sample: -> `("string", None)`
- [ ] Extensible: new patterns added to one function, all renderers benefit

#### Schema Builder

- [ ] `build_graph_schema(state, driver)` constructs a `GraphSchema` from state + graph introspection
- [ ] Domain nodes built from `approved_construction_plan` (entries with `construction_type == "node"`)
- [ ] Domain relationships built from `approved_construction_plan` (entries with `construction_type == "relationship"`)
- [ ] Text entity nodes built from `approved_entity_types`
- [ ] Text relationships built from `approved_fact_types`
- [ ] Domain node property samples from `domain_node_schema` in state (or introspected if missing)
- [ ] Text entity property samples from `text_entity_schema` in state (or introspected if missing)
- [ ] Relationship property samples from NEW `_introspect_relationship_schema()` (see below)
- [ ] CORRESPONDS_TO bridge relationships added for overlapping labels between domain and text layers
- [ ] `overlapping_labels` computed as intersection of domain labels and text entity labels
- [ ] All `PropertyInfo` entries have `inferred_type` and `parse_hint` populated via `_detect_format()`

#### Relationship Property Introspection

- [ ] New function `_introspect_relationship_schema(driver, state)` in `tools/query_tools.py`
- [ ] For each relationship type in `approved_construction_plan` (where `construction_type == "relationship"`):
  - Queries one instance: `MATCH ()-[r:REL_TYPE]->() RETURN keys(r), r LIMIT 1`
  - Extracts property names and sample values
  - Filters out internal properties (`__`-prefixed)
  - Truncates sample values to 100 characters
- [ ] For each relationship type in `approved_fact_types`:
  - Queries one instance with `__Entity__` filter on start node
  - Records properties (typically empty for text relationships)
- [ ] Returns `dict[str, dict[str, dict]]` mapping relationship type to property samples
- [ ] Stored in `state["relationship_schema"]` for caching
- [ ] Graceful failure: logs warning and returns empty dict on Neo4j errors

#### Cypher Notation Renderer

- [ ] `GraphSchema.cypher_notation()` returns a schema block using Cypher CREATE-like syntax
- [ ] Domain layer section:
  - Node definitions: `(:Label {prop1: "sample1", prop2: "sample2"})`
  - Relationship definitions: `(:From)-[:TYPE {prop: "sample"}]->(:To)`
- [ ] Text layer section:
  - Node definitions include `__Entity__` label: `(:Label:__Entity__ {prop: "sample"})`
  - Relationship definitions between text entities
- [ ] Cross-layer bridge section:
  - `(:Label:__Entity__)-[:CORRESPONDS_TO]->(:Label)` for each overlapping label
- [ ] Data format notes section:
  - One line per property with non-trivial `parse_hint`
  - Format: `// prop_name (e.g. "sample"): parse with <parse_hint>`
- [ ] Properties are structurally inside their owner (node or relationship) -- no ambiguity
- [ ] Sample values show actual format (the LLM sees `"$36.06"`, not just `unit_cost`)
- [ ] Output fits within ~800 tokens for typical graphs (4-6 node types, 5-8 relationship types)

#### Compact Summary Renderer

- [ ] `GraphSchema.compact_summary()` returns a minimal schema overview
- [ ] Lists domain labels (no properties): `Domain layer: Product, Supplier, Assembly, Part`
- [ ] Lists domain relationships (no properties): `Domain relationships: HAS_ASSEMBLY (Product->Assembly), ...`
- [ ] Lists text entity labels: `Text layer: Review, Reviewer, Defect, ... (all :__Entity__)`
- [ ] Lists text relationships: `Text relationships: AUTHORED (Reviewer->Review), ...`
- [ ] Lists cross-layer bridges: `Cross-layer bridges: Product, Part (via CORRESPONDS_TO)`
- [ ] Lists queryable features: `Queryable features: structured properties, text embeddings, fulltext index`
- [ ] No property names, no samples, no parse hints
- [ ] Output fits within ~200 tokens

#### Unit Tests

- [ ] `tests/unit/test_graph_schema.py` created
- [ ] Test `_detect_format()` for all pattern types (currency, fraction, boolean, integer, float, plain, None)
- [ ] Test `build_graph_schema()` with furniture supply chain state fixture
- [ ] Test `build_graph_schema()` with minimal state (domain only, text only, both layers)
- [ ] Test `build_graph_schema()` with empty state (no construction plan)
- [ ] Test `cypher_notation()` output contains relationship properties inside relationship syntax
- [ ] Test `cypher_notation()` output contains `__Entity__` label on text nodes
- [ ] Test `cypher_notation()` output contains CORRESPONDS_TO bridges for overlapping labels
- [ ] Test `cypher_notation()` output contains DATA FORMAT NOTES for non-trivial formats
- [ ] Test `compact_summary()` contains no property names or sample values
- [ ] Test `compact_summary()` lists all labels and relationship types
- [ ] Test `_introspect_relationship_schema()` with mock Neo4j driver
- [ ] Test property ownership: `lead_time_days` appears inside SUPPLIES, not inside Supplier or Part

---

### Phase 2: Separated Query Flow

#### Strategy Selection (Lightweight)

- [ ] `_select_retrieval_strategy()` in `query_builder.py` modified to use `schema.compact_summary()`
- [ ] Strategy selector prompt receives only compact summary (~200 tokens of schema)
- [ ] Strategy selector returns strategy name only -- no Cypher query generated in this call
- [ ] Strategy selector prompt simplified: classification task only, no Cypher generation instructions
- [ ] Fallback to `"schema"` strategy on any error (existing behavior preserved)

#### Cypher Generation (Dedicated)

- [ ] New function `_generate_cypher_query(question, schema, context)` in `query_builder.py`
- [ ] Receives `schema.cypher_notation()` as full schema context
- [ ] System prompt includes:
  - Complete Cypher notation schema block
  - Data format notes with parse hints
  - Cross-layer bridging rules
  - Read-only constraint (no CREATE, DELETE, SET, REMOVE, MERGE)
  - Cypher aggregation note (no GROUP BY -- implicit in WITH/RETURN)
- [ ] Returns Cypher query string
- [ ] Uses `CLAUDE_MODEL` from `core.config` (same model as strategy selector)
- [ ] Decorated with `@traceable(name="query.generate_cypher")`

#### Updated Query Flow

- [ ] `_run_kg_query()` in `query_server.py` uses `GraphSchema` built at startup
- [ ] Flow: `select_strategy(compact)` -> if cypher: `generate_cypher(full schema)` -> `validate` -> `execute`
- [ ] For non-cypher strategies (vector, hybrid, cross_layer, schema): flow unchanged
- [ ] Total LLM calls for Cypher queries: 2 (strategy + generation) vs current 1-4

#### Cross-Layer Repair Updated

- [ ] `_regenerate_cross_layer_cypher()` uses `schema.for_repair(violation)` instead of ad-hoc formatting
- [ ] `for_repair()` includes relationship properties (currently omitted in repair prompt)
- [ ] `for_repair()` includes data format parse hints
- [ ] `for_repair()` is focused on violation-relevant schema elements (not full schema)

#### Unit Tests

- [ ] Test strategy selection uses compact summary (mock Claude call, verify prompt content)
- [ ] Test Cypher generation uses full cypher notation (mock Claude call, verify prompt content)
- [ ] Test end-to-end flow: strategy + generation + execution with mock driver
- [ ] Test non-cypher strategies bypass Cypher generation (no second LLM call)
- [ ] Test repair prompt includes relationship properties

---

### Phase 3: Enhanced Cypher Validation

#### Property Access Validation

- [ ] `GraphSchema.validate_cypher(cypher)` method returns `list[ValidationIssue]`
- [ ] `ValidationIssue` dataclass: `(issue_type, message, suggestion)`
- [ ] Detects property accessed on wrong object type:
  - Example: `s.lead_time_days` when `lead_time_days` is on SUPPLIES relationship
  - Suggestion: "Use a relationship variable: `(s)-[sup:SUPPLIES]->(p)` then `sup.lead_time_days`"
- [ ] Uses regex to extract `variable.property` patterns from Cypher
- [ ] Cross-references against schema: which properties belong to which nodes/relationships

#### Relationship Existence Validation

- [ ] Detects relationship types not in schema
  - Example: `[:MENTIONED_IN]` when only `[:MENTIONS_DEFECT_IN]` exists
  - Suggestion: "Did you mean MENTIONS_DEFECT_IN?"
- [ ] Uses Levenshtein distance or substring matching for suggestions
- [ ] Extracts relationship types from `[:TYPE]` patterns in Cypher

#### Direction Validation

- [ ] Detects reversed relationship directions
  - Example: `(p:Part)-[:SUPPLIES]->(s:Supplier)` when schema defines `(Supplier)-[:SUPPLIES]->(Part)`
  - Suggestion: "SUPPLIES direction is (Supplier)-[:SUPPLIES]->(Part)"
- [ ] Extracts `(label)-[:TYPE]->(label)` patterns from Cypher
- [ ] Compares against `RelationshipSchema.from_label` and `to_label`

#### Cross-Layer Validation (Existing, Enhanced)

- [ ] Existing `_detect_cross_layer_violation()` refactored to use `GraphSchema` instead of raw state
- [ ] `GraphSchema.relationships` provides layer classification directly (no re-extraction needed)

#### Integration with Query Flow

- [ ] `validate_cypher()` called after Cypher generation, before execution
- [ ] If issues found: included in repair prompt context for targeted correction
- [ ] If no issues: execute directly
- [ ] Validation is deterministic -- no LLM call needed

#### Unit Tests

- [ ] Test property access validation: `s.lead_time_days` detected when property is on SUPPLIES rel
- [ ] Test relationship existence: `MENTIONED_IN` flagged, `MENTIONS_DEFECT_IN` suggested
- [ ] Test direction validation: reversed SUPPLIES detected
- [ ] Test valid Cypher passes with empty issue list
- [ ] Test cross-layer violation detection via `GraphSchema`

---

### Phase 4: Remaining Renderers and Integration

#### Markdown Renderer

- [ ] `GraphSchema.markdown()` renderer replaces formatting in `_execute_schema_query()`
- [ ] Includes node counts (queried from driver at render time or cached)
- [ ] Classified by layer: Domain, Text, Other sections
- [ ] Relationship endpoints with properties listed

#### For-Repair Renderer

- [ ] `GraphSchema.for_repair(violation)` returns focused schema for repair prompts
- [ ] Includes only schema elements relevant to the violation (relationships used, overlapping labels)
- [ ] Includes relationship properties (currently omitted)
- [ ] Includes data format parse hints
- [ ] Includes bridge pattern

#### Dual-Server Integration: Build Once, Deliver Twice

The `GraphSchema` model and builder live in `core/graph_schema.py`, shared by
both MCP servers. Each server manages its own instance with lifecycle
appropriate to its use case.

**Query Server (`query_server.py`) -- stable state:**

- [ ] `_get_schema()` function added (lazy init, same pattern as `_get_driver()` and `_load_state_once()`)
- [ ] `GraphSchema` built once on first query, cached as module-level `_schema`
- [ ] No invalidation needed -- state and graph are static for the server lifetime
- [ ] Schema includes full introspection (node samples, relationship samples, format hints)
- [ ] Passed to `_run_kg_query()` and `_run_kg_graph_info()`

**Construction Server (`server.py`) -- evolving state:**

- [ ] `_get_schema()` function added (lazy init with invalidation support)
- [ ] `_invalidate_schema()` function added (sets cached schema to `None`)
- [ ] `_invalidate_schema()` called after each state-changing build operation:
  - After `_build_structured()` (domain nodes/relationships created, `_introspect_domain_schema()` called)
  - After `_build_unstructured()` (text entities/chunks created, `_introspect_text_schema()` called)
  - After `_build_resolve()` (CORRESPONDS_TO bridges created, `_introspect_text_schema()` called)
- [ ] Schema rebuilt on next `kg_query` call after invalidation
- [ ] Driver created per-build (follows existing construction server pattern -- no shared driver)
- [ ] Schema passed to `kg_query` tool implementation (replaces current inline state reads)

**Shared components (both servers import from same source):**

- [ ] `GraphSchema` dataclasses in `core/graph_schema.py`
- [ ] `build_graph_schema(state, driver)` in `core/graph_schema.py`
- [ ] `_detect_format()` in `core/graph_schema.py`
- [ ] All renderers (`.cypher_notation()`, `.compact_summary()`, `.markdown()`, `.for_repair()`)
- [ ] `_introspect_relationship_schema()` in `tools/query_tools.py`
- [ ] One builder function, one set of renderers, one set of tests -- two server-specific lifecycles

#### Unit Tests

- [ ] Test `markdown()` output matches expected format
- [ ] Test `for_repair()` includes relationship properties
- [ ] Test schema caching: built once, reused across calls

---

### Phase 5: Refactoring and Cleanup

This is a refactoring story. The codebase must be **simpler** after
implementation, not just bigger. Every old code path that the GraphSchema
replaces must be removed or consolidated. No parallel paths.

#### Remove Replaced Formatters from `pipelines/query_builder.py`

- [ ] Delete `_format_text_entity_props_block()` (lines 87-108) -- replaced by `cypher_notation()` and `for_repair()`
- [ ] Delete `_format_domain_node_props_block()` (lines 111-132) -- replaced by `cypher_notation()` and `for_repair()`
- [ ] Remove their imports if any exist elsewhere (search codebase)

#### Remove Inline Schema Assembly from `_select_retrieval_strategy()`

- [ ] Delete the ~80 lines of `graph_context` assembly (lines 164-258) that manually call `_get_domain_labels()`, `_get_domain_node_properties()`, `_get_domain_node_schema()`, `_get_domain_relationships()`, `_get_text_entities()`, `_get_text_entity_properties()`, `_get_text_relationships()`
- [ ] Delete the inline `architecture_block` construction (lines 240-258) -- replaced by `compact_summary()` which handles dual-layer context
- [ ] Replace with single call to `schema.compact_summary()`
- [ ] Verify the system prompt is now focused on strategy classification only (no Cypher generation instructions, no schema detail)

#### Remove Inline Schema Assembly from `_regenerate_cross_layer_cypher()`

- [ ] Delete the ~20 lines that manually build `domain_schema` and `text_schema` strings (lines 564-573)
- [ ] Delete the calls to `_format_domain_node_props_block(state)` and `_format_text_entity_props_block(state)` (lines 593, 598)
- [ ] Delete the manual `overlapping` labels extraction (line 576)
- [ ] Replace with single call to `schema.for_repair(violation)`

#### Remove Schema Formatting from `_execute_schema_query()`

- [ ] Delete the ~50 lines of manual schema formatting (lines 389-484) that build the markdown answer by querying `db.labels()`, `db.relationshipTypes()`, counting nodes, and classifying labels
- [ ] Replace with `schema.markdown()` (which uses the same canonical model)
- [ ] Node counts: either cached in `GraphSchema` at build time or queried by the markdown renderer
- [ ] `rel_endpoint_map` construction (lines 417-421) no longer needed -- `GraphSchema.relationships` already has endpoints

#### Consolidate Extraction Functions in `tools/query_tools.py`

The 8 extraction functions currently serve two consumers: the query pipeline
(being refactored) and other code (CQ evaluation, construction agents). After
refactoring:

- [ ] Audit each `_get_*` function for remaining callers outside of `query_builder.py`:
  - `_get_domain_labels()` -- used in `_execute_schema_query()`, `_execute_cross_layer_traversal()`, `_detect_cross_layer_violation()`, `query_agent_tools.py`. **Keep** (still used by cross-layer traversal and query agent tools)
  - `_get_domain_node_properties()` -- used only in `_select_retrieval_strategy()`. **Remove** after Phase 2 (only consumer eliminated)
  - `_get_domain_node_schema()` -- used only in `_select_retrieval_strategy()` and `_format_domain_node_props_block()`. **Remove** after Phase 2
  - `_get_domain_relationships()` -- used in `_select_retrieval_strategy()`, `_execute_schema_query()`, `_regenerate_cross_layer_cypher()`, `_detect_cross_layer_violation()`. **Keep** if `_detect_cross_layer_violation()` remains separate; **internalize** into `GraphSchema` if validation moves there
  - `_get_text_entities()` -- used in `_select_retrieval_strategy()`, `_execute_schema_query()`, `_execute_cross_layer_traversal()`. **Keep** (still used by cross-layer traversal)
  - `_get_text_entity_properties()` -- used only in `_select_retrieval_strategy()` and `_format_text_entity_props_block()`. **Remove** after Phase 2
  - `_get_text_relationships()` -- used in `_select_retrieval_strategy()`, `_execute_schema_query()`, `_detect_cross_layer_violation()`. **Keep** if validation remains separate
  - `_get_layer_classification()` -- used only in `_detect_cross_layer_violation()`. **Internalize** into `GraphSchema.validate_cypher()` in Phase 3
- [ ] Functions marked **Remove**: delete from `query_tools.py`, remove from imports in `query_builder.py`
- [ ] Functions marked **Keep**: add docstring noting they remain for non-query consumers
- [ ] Functions marked **Internalize**: move logic into `GraphSchema` methods, delete originals if no other callers

#### Consolidate Cross-Layer Violation Detection

- [ ] `_detect_cross_layer_violation()` in `query_tools.py` -- logic moves into `GraphSchema.validate_cypher()` (Phase 3)
- [ ] `_get_layer_classification()` in `query_tools.py` -- no longer needed as separate function; `GraphSchema` already classifies layers structurally
- [ ] Remove both after Phase 3, once `validate_cypher()` handles all validation
- [ ] Update imports in `query_builder.py` to use `schema.validate_cypher()` instead

#### Clean Up Imports in `pipelines/query_builder.py`

- [ ] Remove imports for deleted functions: `_get_domain_node_properties`, `_get_domain_node_schema`, `_get_text_entity_properties`, `_get_layer_classification`
- [ ] Remove imports for deleted formatters: `_format_text_entity_props_block`, `_format_domain_node_props_block` (if they were importable)
- [ ] After Phase 3: remove imports for `_detect_cross_layer_violation`
- [ ] Verify no unused imports remain

#### Update Unit Tests

- [ ] Remove or update tests in `tests/unit/test_query_tools.py` that test deleted functions
- [ ] Tests for **kept** functions (`_get_domain_labels`, `_get_text_entities`, etc.) remain unchanged
- [ ] Tests for **removed** functions: delete test cases, verify total test count is still healthy
- [ ] Tests for `_detect_cross_layer_violation` move to `test_graph_schema.py` (testing `validate_cypher()` instead)
- [ ] No test should import a deleted function

#### Final Verification

- [ ] `grep` for all deleted function names across the codebase -- zero hits outside of git history
- [ ] No function in `query_builder.py` manually assembles schema context from multiple `_get_*` calls
- [ ] No prompt in the query pipeline constructs its own schema view -- all use `GraphSchema` renderers
- [ ] `query_tools.py` is smaller after refactoring (fewer functions, fewer lines)
- [ ] `query_builder.py` prompt construction is shorter and clearer (schema comes from one renderer call, not inline assembly)

---

## Definition of Done

### Functional

- [ ] `core/graph_schema.py` implemented with all dataclasses and renderers
- [ ] `_introspect_relationship_schema()` added to `tools/query_tools.py`
- [ ] `_detect_format()` handles all documented sample patterns
- [ ] Strategy selection and Cypher generation are separate LLM calls
- [ ] Cross-layer validation enhanced with property access, direction, and existence checks
- [ ] All renderers produce correct output for the furniture supply chain graph
- [ ] **Must-pass test questions** (see architecture doc appendix) produce correct Cypher on first generation call
- [ ] MCP tools (`kg_query`, `kg_graph_info`) work from Claude Code without regression

### Refactoring

- [ ] Deleted functions: `_format_text_entity_props_block`, `_format_domain_node_props_block`, `_get_domain_node_properties`, `_get_domain_node_schema`, `_get_text_entity_properties`, `_get_layer_classification`
- [ ] Internalized functions: `_detect_cross_layer_violation` logic moved into `GraphSchema.validate_cypher()`
- [ ] No query pipeline function manually assembles schema from multiple `_get_*` calls
- [ ] No prompt constructs its own schema view -- all use `GraphSchema` renderers
- [ ] `query_tools.py` has fewer functions and fewer lines than before
- [ ] `query_builder.py` prompt construction is shorter (schema from one renderer call, not inline assembly)
- [ ] Zero references to deleted functions across the codebase (verified via grep)

### Testing

- [ ] Unit tests: `tests/unit/test_graph_schema.py` covering all phases
- [ ] Tests for deleted functions removed or migrated to `test_graph_schema.py`
- [ ] All remaining unit tests still pass (target: 540+ after test cleanup)
- [ ] Interactive validation: `test_08_kg_query.py` demonstrates improved query quality

### Quality

- [ ] Observability: traces visible in LangSmith if enabled (existing `@traceable` pattern)
- [ ] Code reviewed
- [ ] Documentation in code (docstrings for all public functions)

## Technical Notes

### Architecture

**Shared model, two server lifecycles:**

```
core/graph_schema.py                      <-- Shared: model + builder + renderers
         |
    +----+----+
    |         |
    v         v
server.py   query_server.py
(kg-factory) (kg-query)
  |              |
  | evolving     | stable state
  | state:       | build once,
  | invalidate   | cache forever
  | after build  |
  v              v
_get_schema()  _get_schema()                 <-- Server-specific lifecycle
    |              |
    +------+-------+
           |
           v
    kg_query(question, context)              <-- Same query flow in both servers
      |
      +-> select_strategy()                  # Claude call 1 (lightweight)
      |     +-> schema.compact_summary()     #   ~200 tokens of schema
      |     +-> Return: strategy name        #   No Cypher generated here
      |
      +-> if strategy == "cypher":
      |     +-> generate_cypher()            # Claude call 2 (dedicated)
      |     |     +-> schema.cypher_notation()   ~800 tokens of schema
      |     |     +-> Return: Cypher query       Full schema + format hints
      |     |
      |     +-> schema.validate_cypher(query)    # Deterministic validation
      |     |     +-> Property access check      #   No LLM call
      |     |     +-> Relationship existence     #
      |     |     +-> Direction check            #
      |     |     +-> Cross-layer check          #
      |     |
      |     +-> if issues:
      |     |     +-> repair_cypher()            # Claude call 3 (only if needed)
      |     |           +-> schema.for_repair()  #   Focused context
      |     |
      |     +-> execute_cypher(driver, query)
      |
      +-> elif strategy in ("vector", "hybrid", "cross_layer"):
      |     +-> existing strategy functions      # Unchanged
      |
      +-> elif strategy == "schema":
      |     +-> schema.markdown()                # Uses GraphSchema renderer
      |
      +-> Return: {answer, evidence, confidence, strategy, details}
```

**Construction server invalidation points:**

```
kg_build_graph(scope="structured")
  +-> _build_structured()
  +-> _introspect_domain_schema()   # existing
  +-> _introspect_relationship_schema()  # NEW
  +-> _save_state()                 # existing
  +-> _invalidate_schema()          # NEW -- next kg_query rebuilds

kg_build_graph(scope="unstructured")
  +-> _build_unstructured()
  +-> _introspect_text_schema()     # existing
  +-> _save_state()                 # existing
  +-> _invalidate_schema()          # NEW

kg_build_graph(scope="resolve")
  +-> _build_resolve()
  +-> _introspect_text_schema()     # existing
  +-> _save_state()                 # existing
  +-> _invalidate_schema()          # NEW
```

### Files to Create

```
core/
  graph_schema.py                 # NEW: GraphSchema model + builder + renderers

tests/unit/
  test_graph_schema.py            # NEW: Unit tests for schema model
```

### Files to Modify

```
tools/query_tools.py              # ADD: _introspect_relationship_schema()
                                  # REMOVE: _get_domain_node_properties() (internalized into builder)
                                  # REMOVE: _get_domain_node_schema() (internalized into builder)
                                  # REMOVE: _get_text_entity_properties() (internalized into builder)
                                  # REMOVE: _get_layer_classification() (internalized into GraphSchema)
                                  # REMOVE: _detect_cross_layer_violation() (moved to GraphSchema.validate_cypher)
                                  # KEEP: _get_domain_labels() (used by cross-layer traversal, query agent)
                                  # KEEP: _get_text_entities() (used by cross-layer traversal)
                                  # KEEP: _get_domain_relationships() (used by query agent tools)
                                  # KEEP: _get_text_relationships() (used by query agent tools)
                                  # KEEP: format_cypher_results(), format_retriever_results(),
                                  #       calculate_confidence(), _validate_read_only_cypher(),
                                  #       _escape_lucene() (unchanged utilities)
                                  # NET EFFECT: 5 functions removed, 1 added, file is smaller

pipelines/query_builder.py        # ADD: _generate_cypher_query() (dedicated Cypher generation)
                                  # MODIFY: _select_retrieval_strategy() (compact summary only, ~80 lines of
                                  #         inline schema assembly deleted, replaced with schema.compact_summary())
                                  # MODIFY: _regenerate_cross_layer_cypher() (~20 lines of inline schema
                                  #         assembly deleted, replaced with schema.for_repair())
                                  # MODIFY: _execute_schema_query() (~50 lines of manual formatting
                                  #         deleted, replaced with schema.markdown())
                                  # MODIFY: _execute_validated_cypher() (add schema.validate_cypher() call)
                                  # REMOVE: _format_text_entity_props_block() (replaced by renderers)
                                  # REMOVE: _format_domain_node_props_block() (replaced by renderers)
                                  # REMOVE: imports for deleted query_tools functions
                                  # NET EFFECT: 2 functions removed, 1 added, ~150 lines of inline
                                  #             schema assembly replaced with renderer calls

mcp_server/query_server.py        # MODIFY: Build GraphSchema at startup, pass to queries
                                  # ADD: _get_schema() lazy initializer (same pattern as _get_driver())

mcp_server/server.py              # ADD: _get_schema() lazy initializer with invalidation
                                  # ADD: _invalidate_schema() cache reset
                                  # MODIFY: kg_query() to use GraphSchema instead of inline state reads
                                  # MODIFY: _build_structured() to call _invalidate_schema() after build
                                  # MODIFY: _build_unstructured() to call _invalidate_schema() after build
                                  # MODIFY: _build_resolve() to call _invalidate_schema() after resolve

tests/unit/test_query_tools.py    # REMOVE: tests for deleted functions (_get_domain_node_properties,
                                  #         _get_domain_node_schema, _get_text_entity_properties,
                                  #         _get_layer_classification, _detect_cross_layer_violation)
                                  # KEEP: tests for retained functions
                                  # MIGRATE: cross-layer violation tests -> test_graph_schema.py
```

### Files Unchanged

```
agents/*                          # Construction agents unaffected
tools/extraction_tools.py         # Extraction tools unaffected
tools/query_agent_tools.py        # Query agent tools (consume query_builder, no direct schema access)
core/state.py                     # State management unaffected
core/agent.py                     # Agent framework unaffected
```

### Test Fixtures

The unit tests should use a state fixture based on the furniture supply chain
state, containing:

```python
FIXTURE_STATE = {
    "approved_construction_plan": {
        "Product": {"construction_type": "node", "label": "Product",
                    "properties": ["product_id", "product_name", "price", "description"]},
        "Supplier": {"construction_type": "node", "label": "Supplier",
                     "properties": ["supplier_id", "name", "specialty", "city", "country"]},
        "SUPPLIES": {"construction_type": "relationship", "relationship_type": "SUPPLIES",
                     "from_node_label": "Supplier", "to_node_label": "Part",
                     "properties": ["lead_time_days", "unit_cost", "minimum_order_quantity",
                                    "preferred_supplier"]},
        # ... other nodes and relationships
    },
    "approved_entity_types": {
        "Review": {"source": "discovered", "description": "..."},
        "Defect": {"source": "discovered", "description": "..."},
        "Product": {"source": "well_known", "description": "..."},
        # ...
    },
    "approved_fact_types": {
        "evaluates": {"predicate_label": "evaluates", "subject_label": "Review",
                      "object_label": "Product"},
        "mentions_defect_in": {"predicate_label": "mentions_defect_in",
                               "subject_label": "Review", "object_label": "Part"},
        # ...
    },
    "domain_node_schema": {
        "Product": {"properties": {"price": {"sample": "$212"},
                                   "product_name": {"sample": "Jonkoping Coffee Table"}}},
        # ...
    },
    "text_entity_schema": {
        "Review": {"properties": {"rating": {"sample": "5/5"},
                                  "content": {"sample": "I absolutely love..."}}},
        # ...
    },
}
```

### Validation Test Questions

The architecture doc (`14_canonical_graph_schema.md`) contains a full test
catalog with 39 questions across 9 categories. The **must-pass** set for this
story:

| ID | Question | Failure Mode Prevented |
|----|----------|----------------------|
| 1.1 | Lead times and unit costs for defective parts | Relationship property on wrong object |
| 1.5 | Parts per assembly (quantity) | Same property name on node and relationship |
| 2.2 | Products rated below 3/5 | String comparison instead of numeric |
| 2.3 | Suppliers with unit cost under $40 | Format parsing + relationship property |
| 3.1 | Suppliers for best-rated products | Premature aggregation cutoff |
| 5.1 | Parts each supplier provides | Reversed direction |
| 6.3 | Products each reviewer recommends | Hallucinated relationship |

These questions should be validated interactively against the live furniture
supply chain graph after implementation.

### Backward Compatibility

- Existing `_get_*` functions in `query_tools.py` remain available for other
  consumers (construction agents, extraction tools, CQ evaluation)
- `kg_query` and `kg_graph_info` MCP tool signatures unchanged
- `context` parameter on `kg_query` still works (additional context merged
  with schema in Cypher generation prompt)
- Non-cypher strategies (vector, hybrid, cross_layer) unchanged
- State file format unchanged (new `relationship_schema` key added alongside
  existing `domain_node_schema` and `text_entity_schema`)
