# Canonical Graph Schema: Unified Schema Model for Query Generation

> **Status**: Proposal
> **Depends on**: US013 (Query Infrastructure), US015 (Query Agent), US021 (Remote Query Server)
> **Related**: `07_kg_query_mcp_server.md`, `future_ideas.md` (Idea 2: SHACL Validation)
> **Goal**: Eliminate fragile, ad-hoc schema formatting in query prompts by introducing a single canonical schema model with purpose-specific renderers

---

## Problem Statement

The `kg_query` tool generates Cypher queries via an LLM that receives graph schema
information in its system prompt. This schema information is currently assembled
from 5 state keys by 8 extraction functions, formatted by 4 helper functions,
and injected into 3 independent system prompts. Each prompt constructs its own
schema view with its own notation, leading to systemic quality issues in
generated Cypher.

### Observed Failures

These failures were observed during a cross-layer query session ("For parts
mentioned in negative reviews, what are the lead times and unit costs from
their suppliers?"):

| Attempt | Failure | Root Cause |
|---------|---------|-----------|
| 1 | `s.lead_time_days` returned NULL | LLM put relationship properties on the Supplier node |
| 2 | Zero results | LLM reversed relationship direction and hallucinated a relationship name |
| 3 | Diagnostic query needed | Had to verify data existed before retrying |
| 4 | Correct (after detailed context) | Manual context parameter compensated for prompt gaps |

**4 LLM calls to answer 1 question.** The final call only succeeded because
the caller manually provided schema details that the prompt should have
contained.

### Why Patching Doesn't Scale

Each failure suggests a targeted fix: "add a note about relationship
properties", "add parsing hints for string formats." But these are symptoms
of a structural problem:

1. **No canonical schema model** -- schema knowledge is scattered across 5
   state keys, extracted by 8 functions, formatted by 4 helpers, assembled
   into 3 prompts. Each assembly makes independent decisions about what to
   include and how to format it.

2. **Ambiguous notation** -- the same `[prop1, prop2]` bracket syntax is used
   for both node properties and relationship properties. The LLM cannot
   distinguish where properties live.

3. **Conflated concerns** -- strategy selection and Cypher generation happen
   in a single LLM call, forcing the prompt to serve two competing purposes:
   concise for classification, detailed for code generation.

4. **Incomplete introspection** -- node properties have sample values from
   graph introspection, but relationship properties have none. The LLM sees
   `lead_time_days` as a name without knowing it's an integer `29` or that
   `unit_cost` looks like `"$36.06"`.

Adding more prose to existing prompts treats each symptom individually and
creates a maintenance burden that grows with every new graph domain.

---

## Solution: Canonical Graph Schema

Introduce a single intermediate model -- `GraphSchema` -- that is built once
from state and graph introspection, then rendered into purpose-specific
formats for each consumer.

```
                        +---------------------+
State Sources           |   GraphSchema       |         Consumers
-------------           |   (canonical model) |         ---------
                        |                     |
construction_plan --+   |  nodes: [           |   +--> .cypher_notation()     --> Cypher generator prompt
entity_types -------+   |    NodeSchema(...)  |   |
fact_types ---------+-->|  ]                  |---+--> .compact_summary()     --> Strategy selector prompt
domain_node_schema -+   |  relationships: [   |   |
text_entity_schema -+   |    RelSchema(...)   |   +--> .markdown()            --> kg_graph_info display
rel_schema (NEW) ---+   |  ]                  |   |
                        |  overlapping_labels |   +--> .for_repair(violation) --> Cross-layer repair prompt
                        |  format_hints       |   |
                        +---------------------+   +--> .shacl_shapes()        --> Validation (future)
                           Built once, cached
```

### Design Principles

1. **Single source of truth** -- one model captures everything about the graph
   schema. All consumers derive their view from it.

2. **Properties are located** -- every property is attached to its owner (node
   or relationship). There is no ambiguity about where `lead_time_days` lives.

3. **Samples are universal** -- every property (node and relationship) carries
   a sample value from graph introspection.

4. **Format awareness is automatic** -- sample values are analyzed to detect
   patterns (currency strings, fractions, dates) and generate parse hints
   without manual configuration.

5. **Renderers are purpose-built** -- each consumer gets exactly the schema
   view it needs: compact for strategy selection, detailed for Cypher
   generation, formal for validation.

---

## Data Model

### Core Types

```python
# core/graph_schema.py

@dataclass
class PropertyInfo:
    """A single property on a node or relationship."""
    name: str
    sample: str | None         # e.g. "$36.06", "5/5", "Nordic Wood Industries"
    inferred_type: str         # "string" | "integer" | "float" | "boolean"
    parse_hint: str | None     # e.g. "toFloat(replace(x, '$', ''))" or None

@dataclass
class NodeSchema:
    """Schema for one node label in one layer."""
    label: str
    layer: str                 # "domain" | "text"
    properties: list[PropertyInfo]

@dataclass
class RelationshipSchema:
    """Schema for one relationship type."""
    type: str
    from_label: str
    to_label: str
    layer: str                 # "domain" | "text" | "bridge"
    properties: list[PropertyInfo]

@dataclass
class GraphSchema:
    """Complete graph schema with renderers."""
    nodes: list[NodeSchema]
    relationships: list[RelationshipSchema]
    overlapping_labels: set[str]

    def cypher_notation(self) -> str: ...
    def compact_summary(self) -> str: ...
    def markdown(self) -> str: ...
    def for_repair(self, violation: dict) -> str: ...
```

### Property Ownership

The critical design choice: properties are **inside** their owner, not
listed separately.

```
Current (ambiguous):
  Supplier [supplier_id, name, specialty, city, country]
  SUPPLIES (Supplier -> Part [lead_time_days, unit_cost])

  --> Are lead_time_days and unit_cost on the Supplier node,
      the Part node, or the SUPPLIES relationship?

Proposed (unambiguous):
  NodeSchema(label="Supplier", properties=[supplier_id, name, ...])
  RelationshipSchema(type="SUPPLIES", properties=[lead_time_days, unit_cost, ...])

  --> Properties are structurally attached to their owner.
      The renderer makes this visible in every output format.
```

---

## Building the Schema

### Constructor

```python
def build_graph_schema(state: dict, driver: Driver) -> GraphSchema:
    """Build canonical schema from state + graph introspection.

    Merges structural information from state (construction plan,
    entity types, fact types) with sample values from graph
    introspection (node properties, relationship properties).

    Called once at server startup. Result is cached for the
    server lifetime.
    """
```

### Data Sources

The builder consolidates work currently spread across 8 extraction functions:

| Current Function | Extracts | Maps To |
|-----------------|----------|---------|
| `_get_domain_labels(state)` | Node label names | `NodeSchema.label` (layer="domain") |
| `_get_domain_node_properties(state)` | Property name lists | `NodeSchema.properties[].name` |
| `_get_domain_node_schema(state)` | Node property samples | `NodeSchema.properties[].sample` |
| `_get_domain_relationships(state)` | Rel type/from/to/property names | `RelationshipSchema` (structure) |
| `_get_text_entities(state)` | Entity label names | `NodeSchema.label` (layer="text") |
| `_get_text_entity_properties(state)` | Entity property samples | `NodeSchema.properties[].sample` |
| `_get_text_relationships(state)` | Rel type/from/to | `RelationshipSchema` (structure) |
| **NEW: introspect rel properties** | **Rel property samples** | **`RelationshipSchema.properties[].sample`** |

The existing `_get_*` functions remain available for other consumers (construction
agents, extraction tools) but the query pipeline uses only `GraphSchema`.

### Relationship Property Introspection

This fills the critical gap -- relationship properties currently have no
sample values anywhere in the system.

```python
def _introspect_relationship_schema(
    driver: Driver, state: dict
) -> dict[str, dict]:
    """Sample one instance of each relationship type for property values.

    For domain relationships (from construction_plan):
      MATCH ()-[r:SUPPLIES]->() RETURN keys(r), r LIMIT 1
      --> {lead_time_days: 29, unit_cost: "$36.06", ...}

    For text relationships (from fact_types):
      MATCH ()-[r:EVALUATES]->() WHERE startNode(r):__Entity__
      RETURN keys(r), r LIMIT 1
      --> {} (text relationships typically have no properties)

    Returns:
        {"SUPPLIES": {"lead_time_days": {"sample": "29"},
                      "unit_cost": {"sample": "$36.06"}, ...},
         "EVALUATES": {}, ...}
    """
```

### Format Detection

When building `PropertyInfo`, sample values are analyzed to auto-generate
parse hints:

```python
def _detect_format(sample: str | None) -> tuple[str, str | None]:
    """Infer type and Cypher parse expression from a sample value.

    Returns:
        (inferred_type, parse_hint) where parse_hint is a Cypher
        expression template with 'x' as placeholder, or None if
        the value can be used directly.

    Examples:
        "$36.06"   -> ("string",  "toFloat(replace(x, '$', ''))")
        "5/5"      -> ("string",  "toFloat(split(x, '/')[0])")
        "29"       -> ("integer", None)
        "true"     -> ("boolean", None)
        "Stockholm"-> ("string",  None)
    """
```

Detection rules (ordered by specificity):

| Pattern | Sample | Inferred Type | Parse Hint |
|---------|--------|--------------|------------|
| Starts with `$`, rest is numeric | `"$36.06"` | string | `toFloat(replace(x, '$', ''))` |
| Matches `digits/digits` | `"5/5"` | string | `toFloat(split(x, '/')[0])` |
| `true` or `false` (case-insensitive) | `"true"` | boolean | None |
| Pure integer string | `"29"` | integer | None |
| Decimal number string | `"3.14"` | float | None |
| ISO date pattern | `"2024-01-15"` | string | `date(x)` |
| Everything else | `"Stockholm"` | string | None |

This is extensible: new patterns are added to `_detect_format()` once, and
every graph in every domain benefits automatically.

---

## Renderers

### 1. Cypher Notation (for Cypher generation prompts)

The primary renderer. Produces a schema block that mirrors Cypher `CREATE`
syntax, making it natural for the LLM to pattern-match when generating queries.

```python
def cypher_notation(self) -> str:
```

Output for the furniture supply chain graph:

```
// DOMAIN LAYER
// Nodes
(:Product {product_id: "P-1008", product_name: "Jonkoping Coffee Table", price: "$212", description: "Centerpiece for your living room..."})
(:Supplier {supplier_id: "SUP-001", name: "Nordic Wood Industries", specialty: "Wood", country: "Sweden", city: "Stockholm"})
(:Assembly {assembly_id: "A-1010", assembly_name: "Seat Cushion", quantity: 3})
(:Part {part_id: "S-1074", part_name: "Drawer Front", quantity: 1})

// Relationships
(:Product)-[:HAS_ASSEMBLY {quantity: 3}]->(:Assembly)
(:Assembly)-[:CONTAINS_PART {quantity: 1}]->(:Part)
(:Supplier)-[:SUPPLIES {lead_time_days: 29, unit_cost: "$36.06", minimum_order_quantity: 100, preferred_supplier: true}]->(:Part)

// TEXT LAYER (all nodes carry :__Entity__ label)
// Nodes
(:Review:__Entity__ {rating: "5/5", content: "I absolutely love my Stockholm Chair!..."})
(:Reviewer:__Entity__ {name: "@scandi_lover", location: "Minneapolis"})
(:Defect:__Entity__ {description: "squeaking when leaning back"})
(:Product:__Entity__ {name: "Stockholm Chair"})
(:Part:__Entity__ {description: "replacement part"})

// Relationships
(:Reviewer)-[:AUTHORED]->(:Review)
(:Review)-[:EVALUATES]->(:Product)
(:Review)-[:REPORTS]->(:Defect)
(:Review)-[:MENTIONS_DEFECT_IN]->(:Part)
(:Defect)-[:OBSERVED_IN]->(:Part)

// CROSS-LAYER BRIDGES
(:Product:__Entity__)-[:CORRESPONDS_TO]->(:Product)
(:Part:__Entity__)-[:CORRESPONDS_TO]->(:Part)

// DATA FORMAT NOTES (non-trivial formats requiring Cypher parsing)
// price (e.g. "$212"): parse with toFloat(replace(x, '$', ''))
// rating (e.g. "5/5"): parse with toFloat(split(x, '/')[0])
// unit_cost (e.g. "$36.06"): parse with toFloat(replace(x, '$', ''))
```

**Why this works:**

- **Properties are inside their owner** -- `lead_time_days: 29` appears inside
  `[:SUPPLIES {...}]`, not next to the `Supplier` node. The LLM will naturally
  generate `MATCH (s:Supplier)-[sup:SUPPLIES]->(p:Part) RETURN sup.lead_time_days`.

- **Looks like Cypher** -- the LLM already knows `CREATE` syntax. Using the
  same notation for schema documentation means the LLM can directly
  pattern-match from schema to query.

- **Sample values encode format** -- `"$36.06"` and `"5/5"` make format
  visible without separate explanation. The DATA FORMAT NOTES section provides
  explicit parse expressions for non-trivial cases.

- **Layer separation is structural** -- domain nodes appear without
  `__Entity__`, text nodes appear with it, bridges are in their own section.
  The LLM can see which labels belong to which layer.

### 2. Compact Summary (for strategy selection prompts)

A minimal representation with no property details. Sufficient for choosing
between schema/cypher/vector/hybrid/cross_layer strategies.

```python
def compact_summary(self) -> str:
```

Output:

```
Domain layer: Product, Supplier, Assembly, Part
Domain relationships: HAS_ASSEMBLY (Product->Assembly), CONTAINS_PART (Assembly->Part), SUPPLIES (Supplier->Part)
Text layer: Review, Reviewer, Defect, Product, Part (all :__Entity__)
Text relationships: AUTHORED (Reviewer->Review), EVALUATES (Review->Product), REPORTS (Review->Defect), MENTIONS_DEFECT_IN (Review->Part), OBSERVED_IN (Defect->Part)
Cross-layer bridges: Product, Part (via CORRESPONDS_TO)
Queryable features: structured properties, text embeddings, fulltext index
```

No property names, no samples, no parse hints. Strategy selection only needs
to know what's available, not the details.

### 3. Markdown (for kg_graph_info display)

Replaces the current `_execute_schema_query()` formatting with a renderer
that uses the same canonical model. Includes node counts (queried at render
time or cached).

```python
def markdown(self) -> str:
```

Output:

```markdown
# Knowledge Graph Schema

## Domain Layer (from structured data)
  - Product: 20 nodes [product_id, product_name, price, description]
  - Supplier: 22 nodes [supplier_id, name, specialty, city, country, website, contact_email]
  - Assembly: 64 nodes [assembly_id, assembly_name, quantity]
  - Part: 92 nodes [part_id, part_name, quantity]

## Text Layer (from unstructured data)
  - Review: 70 nodes [rating, content]
  - Reviewer: 33 nodes [name, location]
  - Defect: 29 nodes [description]

## Relationships
  - HAS_ASSEMBLY: Product -> Assembly [quantity]
  - CONTAINS_PART: Assembly -> Part [quantity]
  - SUPPLIES: Supplier -> Part [lead_time_days, unit_cost, minimum_order_quantity, preferred_supplier]
  - AUTHORED: Reviewer -> Review
  - EVALUATES: Review -> Product
  - REPORTS: Review -> Defect
  - MENTIONS_DEFECT_IN: Review -> Part
  - OBSERVED_IN: Defect -> Part
  - CORRESPONDS_TO: (text entity) -> (domain entity)
```

### 4. For Repair (for cross-layer violation repair prompts)

Focused view showing only the schema elements relevant to a specific
violation, plus the bridge pattern.

```python
def for_repair(self, violation: dict) -> str:
```

Output (for a violation using EVALUATES + SUPPLIES without bridge):

```
DOMAIN LAYER:
  (:Supplier)-[:SUPPLIES {lead_time_days: 29, unit_cost: "$36.06"}]->(:Part)

TEXT LAYER (all nodes carry :__Entity__ label):
  (:Review:__Entity__)-[:EVALUATES]->(:Product:__Entity__)

BRIDGE PATTERN:
  (:Product:__Entity__)-[:CORRESPONDS_TO]->(:Product)
  (:Part:__Entity__)-[:CORRESPONDS_TO]->(:Part)

Data formats: price "$212" -> toFloat(replace(x, '$', '')), rating "5/5" -> toFloat(split(x, '/')[0])
```

Unlike the current repair prompt (which shows `(Supplier)-[:SUPPLIES]->(Part)`
with no properties), this includes relationship properties and format hints.

---

## Separated Query Flow

### Current: Single LLM Call

```
Question --> _select_retrieval_strategy()
                |-- calls 8 _get_* functions
                |-- calls 2 _format_* functions
                |-- assembles prompt inline
                |-- Claude call (strategy + Cypher in one shot)
                +-- returns {strategy, cypher_query}
          --> _execute_validated_cypher()
                |-- _detect_cross_layer_violation()
                |-- if violation: _regenerate_cross_layer_cypher()
                |     |-- calls 4 _get_* functions
                |     |-- calls 2 _format_* functions
                |     |-- assembles repair prompt inline
                |     +-- Claude call (repair)
                +-- _execute_cypher()
```

Problems:
- Strategy prompt is bloated with property details irrelevant to classification
- Cypher generation is starved of format details it needs
- The two tasks have competing prompt design requirements

### Proposed: Separated Concerns

```
Question --> select_strategy()
                |-- schema.compact_summary() (~200 tokens)
                |-- Claude call (classification only)
                +-- returns strategy name

          --> if strategy == "cypher":
                generate_cypher()
                   |-- schema.cypher_notation() (~800 tokens)
                   |-- Claude call (code generation)
                   +-- returns Cypher query

          --> validate_cypher()
                |-- schema.overlapping_labels
                |-- schema.relationships
                |-- cross-layer check
                |-- property access check (NEW)
                |-- direction check (NEW)
                +-- if violation:
                      repair_cypher()
                         |-- schema.for_repair(violation)
                         |-- Claude call (focused repair)
                         +-- returns corrected Cypher

          --> execute_cypher(driver, query)
```

### Comparison

| Aspect | Current (1 call) | Proposed (2 calls) |
|--------|-----------------|-------------------|
| Strategy prompt size | ~800 tokens (schema + instructions) | ~200 tokens (compact + instructions) |
| Cypher prompt schema detail | Incomplete (no rel samples, no parse hints) | Complete (full cypher_notation) |
| Cost per Cypher query | 1 LLM call | 2 LLM calls (but smaller prompts) |
| Accuracy | Requires retry + manual context | Schema is unambiguous by construction |
| Net LLM calls (with retries) | 2-4 calls (initial + retries) | 2 calls (strategy + generation) |

The total cost is likely **lower** because correct-first-time queries
eliminate the retry loop that currently consumes 2-3 extra calls.

---

## Cross-Layer Validation (Enhanced)

### Current Capabilities

`_detect_cross_layer_violation()` checks whether a Cypher query uses
relationship types from both layers without a `CORRESPONDS_TO` bridge.
It works by:

1. Classifying relationship types into domain vs text sets (from state)
2. Extracting relationship types from the Cypher query via regex
3. Checking if both sets are represented without the bridge

This catches: queries that mix `SUPPLIES` (domain) with `EVALUATES` (text)
without `CORRESPONDS_TO`.

### Current Gaps

| Check | Current | Impact |
|-------|---------|--------|
| Cross-layer without bridge | Detected | Triggers repair |
| Property on wrong object | Not detected | NULL results (`s.lead_time_days` vs `sup.lead_time_days`) |
| Reversed relationship direction | Not detected | Empty results |
| Hallucinated relationship type | Not detected | Neo4j error or empty results |
| Wrong label for layer | Not detected | Matches wrong node population |

### Enhanced Validation with GraphSchema

With the canonical schema model, validation can check structural correctness
without an LLM call:

```python
def validate_cypher(self, cypher: str) -> list[ValidationIssue]:
    """Validate generated Cypher against the canonical schema.

    Returns a list of issues found, or empty list if valid.
    Each issue includes the problem description and suggested fix.
    """
```

**Property access validation:**
```python
# Schema knows: lead_time_days is on SUPPLIES relationship
# Query has: MATCH (s:Supplier)-[:SUPPLIES]->(p:Part) RETURN s.lead_time_days
# Issue: "lead_time_days is a property of the SUPPLIES relationship,
#         not the Supplier node. Use a relationship variable:
#         MATCH (s:Supplier)-[sup:SUPPLIES]->(p:Part) RETURN sup.lead_time_days"
```

**Relationship existence validation:**
```python
# Schema knows: valid relationships are {SUPPLIES, HAS_ASSEMBLY, EVALUATES, ...}
# Query has: MATCH (r:Review)-[:MENTIONED_IN]->(p:Part)
# Issue: "Relationship type MENTIONED_IN does not exist in the schema.
#         Did you mean MENTIONS_DEFECT_IN?"
```

**Direction validation:**
```python
# Schema knows: SUPPLIES goes (Supplier)-[:SUPPLIES]->(Part)
# Query has: MATCH (p:Part)-[:SUPPLIES]->(s:Supplier)
# Issue: "SUPPLIES direction is reversed. Schema defines:
#         (Supplier)-[:SUPPLIES]->(Part)"
```

These checks are **deterministic** (no LLM call needed) and can be run
before execution to catch errors early. When issues are found, they are
included in the repair prompt context for targeted correction.

---

## Implementation Plan

### Phase 1: Schema Model + Cypher Renderer

**New file**: `core/graph_schema.py`

- `PropertyInfo`, `NodeSchema`, `RelationshipSchema`, `GraphSchema` dataclasses
- `build_graph_schema(state, driver)` constructor
- `_detect_format(sample)` format hint detection
- `GraphSchema.cypher_notation()` renderer
- `GraphSchema.compact_summary()` renderer

**Modified file**: `tools/query_tools.py`

- Add `_introspect_relationship_schema(driver, state)` -- sample relationship
  property values from the graph

**Unit tests**: `tests/unit/test_graph_schema.py`

- Schema building from state fixtures
- Format detection for all known patterns
- Cypher notation output correctness
- Compact summary output correctness

### Phase 2: Separated Query Flow

**Modified file**: `pipelines/query_builder.py`

- New `_generate_cypher_query(question, schema, context)` function --
  dedicated Cypher generation with full schema
- Modify `_select_retrieval_strategy()` to use `schema.compact_summary()`
  and return strategy only (no Cypher)
- Modify `_execute_validated_cypher()` to call `_generate_cypher_query()`
  then validate and execute
- Update `_regenerate_cross_layer_cypher()` to use `schema.for_repair()`

**Modified file**: `mcp_server/query_server.py`

- Build `GraphSchema` once at startup (alongside state loading)
- Pass schema through to query functions

**Unit tests**: Update `tests/unit/test_query_tools.py`

### Phase 3: Enhanced Validation

**Modified file**: `core/graph_schema.py`

- Add `GraphSchema.validate_cypher(cypher)` method
- Property access checking
- Relationship existence checking
- Direction checking

**Modified file**: `pipelines/query_builder.py`

- Call `schema.validate_cypher()` before execution
- Include validation issues in repair context

**Unit tests**: Validation-specific test cases

### Phase 4: Remaining Renderers

- `GraphSchema.markdown()` -- replace `_execute_schema_query()` formatting
- `GraphSchema.for_repair(violation)` -- focused repair context

---

## File Changes Summary

```
NEW:
  core/graph_schema.py              <-- GraphSchema model + builder + renderers
  tests/unit/test_graph_schema.py   <-- Unit tests

MODIFIED:
  tools/query_tools.py              <-- Add _introspect_relationship_schema(), remove replaced functions
  pipelines/query_builder.py        <-- Use GraphSchema, separate strategy/generation, remove inline assembly
  mcp_server/query_server.py        <-- Build schema once at startup (stable state)
  mcp_server/server.py              <-- Build schema on demand, invalidate after build steps (evolving state)

UNCHANGED:
  agents/*                          <-- Construction agents unaffected
  tools/extraction_tools.py         <-- Extraction tools unaffected
  tools/query_agent_tools.py        <-- Query agent tools (consume query_builder)
```

---

## Dual-Server Integration: Build Once, Deliver Twice

The `GraphSchema` model is consumed by two MCP servers with fundamentally
different lifecycles. The model and builder live in `core/graph_schema.py`,
shared by both. Each server manages its own schema instance.

```
core/graph_schema.py                 <-- Shared model + builder + renderers
         |
    +----+----+
    |         |
    v         v
server.py   query_server.py
(kg-factory) (kg-query)
```

### Server 1: `query_server.py` (kg-query) -- Stable State

The standalone query server serves a **finished** knowledge graph. State is
loaded once at startup, the graph doesn't change, and the schema is static.

```python
# query_server.py -- build once, cache forever
_schema: GraphSchema | None = None

def _get_schema() -> GraphSchema:
    global _schema
    if _schema is None:
        state = _load_state_once()
        driver = _get_driver()
        _schema = build_graph_schema(state, driver)
    return _schema
```

Schema lifecycle:
- Built once on first query (lazy init, same pattern as `_driver` and `_state`)
- Includes full introspection (node samples, relationship samples, format hints)
- Cached for server lifetime
- No invalidation needed -- state never changes

### Server 2: `server.py` (kg-factory) -- Evolving State

The construction server builds the graph interactively. State evolves as the
user approves schemas, builds graph layers, and resolves entities. The schema
must be rebuilt when the graph changes.

```python
# server.py -- build on demand, invalidate after build steps
_schema_cache: GraphSchema | None = None

def _get_schema() -> GraphSchema:
    global _schema_cache
    if _schema_cache is None:
        state = _load_clean_state()
        driver = get_neo4j_driver()
        try:
            _schema_cache = build_graph_schema(state, driver)
        finally:
            close_driver(driver)
    return _schema_cache

def _invalidate_schema():
    global _schema_cache
    _schema_cache = None
```

Schema lifecycle:
- Built lazily on first `kg_query` call
- Invalidated (set to `None`) after state-changing operations:
  - `_build_structured()` -- domain nodes and relationships created
  - `_build_unstructured()` -- text entities and chunks created
  - `_build_resolve()` -- CORRESPONDS_TO bridges created
  - Introspection calls (`_introspect_domain_schema`, `_introspect_text_schema`)
- Rebuilt on next `kg_query` call after invalidation
- Driver created per-build (construction server pattern: no shared driver)

Invalidation points (existing code already calls `_save_state()` at these
locations -- `_invalidate_schema()` is added alongside):

```
_build_structured()       line ~1463  _introspect_domain_schema() + _save_state()
_build_unstructured()     line ~1555  _introspect_text_schema() + _save_state()
_build_resolve()          line ~1655  _introspect_text_schema() + _save_state()
```

### What's Shared vs What's Server-Specific

| Component | Location | Shared? |
|-----------|----------|---------|
| `GraphSchema` dataclasses | `core/graph_schema.py` | Shared by both servers |
| `build_graph_schema()` | `core/graph_schema.py` | Shared by both servers |
| `_detect_format()` | `core/graph_schema.py` | Shared by both servers |
| Renderers (`.cypher_notation()`, etc.) | `core/graph_schema.py` | Shared by both servers |
| `_introspect_relationship_schema()` | `tools/query_tools.py` | Called by builder, shared |
| `_get_schema()` | Each server's own code | Server-specific lifecycle |
| `_invalidate_schema()` | `server.py` only | Construction server only |
| Schema caching strategy | Each server's own code | Different per server |

### Why Not a Single Shared Cache?

The two servers run in separate processes (different MCP connections). They
cannot share in-memory state. Even if they could, their invalidation semantics
differ: the query server never invalidates, the construction server invalidates
on every build step. A shared cache would add complexity without benefit.

The "build once" principle applies to the **code**, not the instance: one
`build_graph_schema()` function, one set of renderers, one set of tests.
Each server calls the same builder with its own state and driver.

---

## How This Addresses Each Observed Failure

| Failure | Root Cause | How GraphSchema Prevents It |
|---------|-----------|---------------------------|
| `s.lead_time_days` returned NULL | Properties shown ambiguously, LLM guessed wrong object | Cypher notation shows `[:SUPPLIES {lead_time_days: 29}]` -- property is structurally inside the relationship |
| Reversed relationship direction | Prompt didn't enforce direction | Cypher notation shows `(:Supplier)-[:SUPPLIES]->(:Part)` -- direction is visible. Enhanced validation catches reversals |
| Hallucinated `MENTIONED_IN` | No validation of relationship names | Enhanced validation checks against schema's known relationship types |
| String comparison `r.rating < '3'` | No guidance on parsing string formats | DATA FORMAT NOTES section shows `rating "5/5" -> toFloat(split(x, '/')[0])` |
| Required 4 calls for 1 answer | Prompt gaps required manual context + retries | Complete schema eliminates the information gap that causes retries |

---

## Sustainability Test

The key measure of a sustainable architecture: **what happens when a new
failure mode appears?**

| Scenario | Current (patch each prompt) | Proposed (schema model) |
|----------|---------------------------|------------------------|
| New property format (e.g. dates) | Add parsing hint to strategy prompt AND repair prompt | Add date pattern to `_detect_format()`. All renderers emit it automatically |
| New relationship type with properties | Hope the notation isn't ambiguous | Properties shown inside `[:REL_TYPE {...}]` -- unambiguous by construction |
| New graph layer (e.g. API-sourced) | Add extraction function, add formatter, update 3 prompts | Add to schema model. All renderers pick it up |
| Property accessed on wrong object | Patch prompt wording for that specific case | Cannot happen -- notation makes ownership structural. Enhanced validation catches errors |
| Schema grows to 50+ node types | Prompts become enormous and noisy | Compact summary stays small (no properties). Cypher notation scales linearly |

---

## Relationship to SHACL Validation (Future)

The `GraphSchema` model captures the same structural information that SHACL
shapes would formalize: node types, relationship types, property ownership,
data types, and cardinality. If SHACL validation (future_ideas.md, Idea 2) is
implemented, it becomes another renderer from the same model:

```python
class GraphSchema:
    def cypher_notation(self) -> str: ...    # For query LLM (this proposal)
    def compact_summary(self) -> str: ...    # For strategy selection (this proposal)
    def markdown(self) -> str: ...           # For display (this proposal)
    def shacl_shapes(self) -> str: ...       # For pySHACL validation (future)
```

The investment in building the canonical model pays forward: the same model
serves query generation today and formal validation tomorrow, without
restructuring.

---

## Appendix: Validation Test Catalog

A comprehensive set of questions designed to stress-test the GraphSchema
architecture. Each question targets a specific weakness in the current system.
The new architecture must handle all **must-pass** questions correctly on the
first LLM call, without retries or manual context injection.

### Category 1: Relationship Property Access

The core gap -- properties live on relationships, not nodes. The current
system has no sample values for relationship properties, and the prompt
notation makes their location ambiguous.

| ID | Question | Challenge | History |
|----|----------|-----------|---------|
| 1.1 | For parts mentioned in negative reviews, what are the lead times and unit costs from their suppliers? | `lead_time_days`, `unit_cost` are on SUPPLIES relationship, not on Supplier node | **Failed 3 times.** LLM generated `s.lead_time_days` (on Supplier node) instead of `sup.lead_time_days` (on SUPPLIES rel). Only succeeded on attempt 4 with manual context. |
| 1.2 | Which suppliers are the preferred supplier for parts with the most defects? | `preferred_supplier` (boolean) on SUPPLIES relationship | New. Tests boolean relationship property access + cross-layer defect aggregation. |
| 1.3 | What is the minimum order quantity for parts supplied to the Stockholm Chair? | `minimum_order_quantity` on SUPPLIES relationship + multi-hop traversal to Product | New. Tests integer relationship property + 4-hop domain traversal. |
| 1.4 | Compare the unit costs between different suppliers providing the same part | Aggregation (GROUP BY part) on SUPPLIES relationship properties | New. Tests relationship property in aggregation context. |
| 1.5 | How many parts does each assembly contain? | `quantity` exists on BOTH the CONTAINS_PART relationship AND the Part node | New. **Same property name on relationship and node.** The LLM must choose the correct source. |

### Category 2: Data Format Parsing

String-encoded values that require Cypher parsing functions. The current
system shows sample values but provides no parsing guidance.

| ID | Question | Challenge | History |
|----|----------|-----------|---------|
| 2.1 | What quality issues and defects are reported for products that cost more than $300? | `price` stored as `"$212"` string, needs `toFloat(replace(x, '$', ''))` | Worked after retry. First attempt used correct parsing but had other issues. |
| 2.2 | Which products are rated below 3 out of 5? | `rating` stored as `"5/5"` string, needs `toFloat(split(x, '/')[0])` | **Failed.** First attempt used string comparison `r.rating < '3'` which is lexicographic, not numeric. |
| 2.3 | Which suppliers offer parts with unit cost under $40? | `unit_cost` is `"$36.06"` on SUPPLIES relationship -- **double challenge**: format parsing + relationship property location | New. Combines two independent failure modes. |
| 2.4 | Rank products from cheapest to most expensive | `ORDER BY` on parsed `price` string | New. Tests format parsing in sort context. |
| 2.5 | What is the average price of products that have defects reported? | `AVG(toFloat(replace(price, '$', '')))` across layers | New. Format parsing + aggregation + cross-layer bridging. |

### Category 3: Cross-Layer Bridging

Must traverse from text layer to domain layer (or vice versa) via
CORRESPONDS_TO. The current system explains the bridge pattern in the prompt,
but the LLM inconsistently applies it.

| ID | Question | Challenge | History |
|----|----------|-----------|---------|
| 3.1 | Which suppliers are involved in the products with the best customer ratings? | Review (text) -> Product (text) -> CORRESPONDS_TO -> Product (domain) -> Assembly -> Part -> Supplier | **Returned only 1 result initially.** Premature LIMIT in generated Cypher cut off aggregation. Required second attempt. |
| 3.2 | Which suppliers are associated with the most negative customer sentiment for a specific product? | Approved CQ1. Sentiment from text layer, suppliers from domain layer. | From approved competency questions. |
| 3.3 | What is the complete traceability path from a customer complaint about product functionality to the specific supplier and part responsible? | Approved CQ5. Full 5+ hop traversal across both layers: Review -> Product (text) -> CORRESPONDS_TO -> Product (domain) -> Assembly -> Part -> Supplier. | From approved CQs. Hardest traceability question. |
| 3.4 | Which specific components consistently receive negative customer feedback across multiple products? | Approved CQ4. Aggregation (COUNT reviews per part) across layers with consistency filter (multiple products). | From approved competency questions. |
| 3.5 | For products reviewed by @scandi_lover, which countries do their suppliers come from? | Reviewer -> AUTHORED -> Review -> EVALUATES -> Product (text) -> CORRESPONDS_TO -> Product (domain) -> HAS_ASSEMBLY -> Assembly -> CONTAINS_PART -> Part <- SUPPLIES <- Supplier.country. 7 hops. | New. Maximum traversal length across both layers. |

### Category 4: Overlapping Labels

Product and Part exist in BOTH layers as separate node populations. The LLM
must distinguish between them and bridge correctly.

| ID | Question | Challenge | History |
|----|----------|-----------|---------|
| 4.1 | How many products have reviews? | Which Product nodes? Text-layer (connected to Review) or domain-layer? Must bridge to avoid double-counting. | New. Tests layer-aware counting. |
| 4.2 | Show all product names with their review counts | Text-layer Product has property `name`. Domain-layer Product has `product_name`. Different property names for the "same" entity. | New. Tests property name mismatch across layers. |
| 4.3 | Which parts are mentioned in reviews but don't exist in the parts catalog? | Text-layer Part WITHOUT a CORRESPONDS_TO link to domain-layer Part. Tests bridge absence detection. | New. Tests `WHERE NOT EXISTS` pattern on cross-layer bridge. |
| 4.4 | List all products with their price and average rating | `price` on domain Product, `rating` on text Review via text Product. Must bridge and combine properties from both layers. | New. Forces correct layer selection for each property. |

### Category 5: Direction Sensitivity

Relationship direction matters for correct results. The current system does
not validate direction in generated Cypher.

| ID | Question | Challenge | History |
|----|----------|-----------|---------|
| 5.1 | Which parts does each supplier provide? | SUPPLIES direction: `(Supplier)-[:SUPPLIES]->(Part)`. Tempting to write `(Part)-[:SUPPLIES]->(Supplier)`. | **Reversed in attempt 2** of this session. LLM also hallucinated `MENTIONED_IN` alongside the correct `MENTIONS_DEFECT_IN`. |
| 5.2 | What reviews evaluate the Uppsala Sofa? | EVALUATES direction: `(Review)-[:EVALUATES]->(Product)`. Semantically one might expect Product to be the subject. | New. Tests direction with counter-intuitive semantics. |
| 5.3 | Who authored the 1-star reviews? | AUTHORED direction: `(Reviewer)-[:AUTHORED]->(Review)`. Must traverse correctly to reach Reviewer. | New. |
| 5.4 | Which defects are observed in drawer rails? | OBSERVED_IN direction: `(Defect)-[:OBSERVED_IN]->(Part)`. "Observed in" suggests Part contains Defect, but the arrow goes from Defect to Part. | New. Semantically confusing direction. |

### Category 6: Hallucination-Prone

Questions that tempt the LLM to invent non-existent relationship types or
assume connections that don't exist in the schema.

| ID | Question | Challenge | History |
|----|----------|-----------|---------|
| 6.1 | Which reviewers are from the same city as a supplier? | No direct relationship between Reviewer and Supplier. Must compare `Reviewer.location` with `Supplier.city` via property matching, not a relationship. | New. Tests property-based joins without relationships. |
| 6.2 | Do any reviewers mention specific suppliers by name in their review text? | No direct Reviewer->Supplier relationship. Requires text search within `Review.content`, not graph traversal. | New. May require vector/hybrid strategy instead of Cypher. |
| 6.3 | What products does each reviewer recommend? | No `RECOMMENDS` relationship exists in the schema. LLM might hallucinate one. | **Hallucinated `MENTIONED_IN`** (non-existent) in this session when the correct relationship was `MENTIONS_DEFECT_IN`. |
| 6.4 | Which suppliers compete for the same parts? | No `COMPETES_WITH` relationship. Must find via shared SUPPLIES target: two Suppliers both `SUPPLIES` the same Part. | New. Tests relationship inference via shared targets. |

### Category 7: Aggregation Across Layers

COUNT, AVG, ranking, and comparison that spans the CORRESPONDS_TO bridge.
These require correct aggregation semantics in Cypher (no GROUP BY -- implicit
in WITH/RETURN).

| ID | Question | Challenge | History |
|----|----------|-----------|---------|
| 7.1 | Rank suppliers by the average rating of products containing their parts | Supplier <- SUPPLIES -> Part <- CONTAINS_PART <- Assembly <- HAS_ASSEMBLY <- Product (domain) <- CORRESPONDS_TO <- Product (text) <- EVALUATES <- Review.rating. Then AVG + ORDER. Most complex aggregation possible. | New. 8-hop traversal + aggregation + format parsing. |
| 7.2 | Which suppliers provide the most components across all product lines? | Approved CQ2. COUNT DISTINCT parts per supplier, grouped by product. | From approved competency questions. |
| 7.3 | For a given part type, which suppliers offer the best combination of quality metrics and pricing? | Approved CQ3. Multi-criteria ranking: defect count (text layer) + unit_cost (SUPPLIES rel property) + rating (text layer). | From approved CQs. Tests multi-metric ranking. |
| 7.4 | How many defects are reported per supplier? | Defect -> OBSERVED_IN -> Part <- SUPPLIES <- Supplier, then COUNT per supplier. | New. Cross-layer aggregation with grouping. |

### Category 8: Absence and Negation

"Which X don't have Y" patterns require NOT EXISTS, optional match filtering,
or count-based exclusion.

| ID | Question | Challenge | History |
|----|----------|-----------|---------|
| 8.1 | Which suppliers have no defects reported for any of their parts? | Negation: Supplier whose parts have no OBSERVED_IN defects. Requires NOT EXISTS or OPTIONAL MATCH + WHERE IS NULL across layers. | New. Cross-layer negation. |
| 8.2 | Which products have no negative reviews? | Absence: Product with no Review where `toFloat(split(rating, '/')[0]) < 3`. Combines negation + format parsing. | New. |
| 8.3 | Which parts are not supplied by any preferred supplier? | Negation on relationship property: no SUPPLIES relationship with `preferred_supplier = true`. | New. Negation + relationship property access. |
| 8.4 | Which assemblies contain parts from only one supplier? | COUNT DISTINCT suppliers per assembly = 1. Not negation per se, but exclusion via aggregation constraint. | New. |

### Category 9: Approved Competency Questions

The real-world benchmark. These are the questions the furniture supply chain
knowledge graph was built to answer. They combine multiple challenge
categories and represent the complexity level users will actually encounter.

| CQ | Question | Key Challenges |
|----|----------|---------------|
| CQ1 | Which suppliers are associated with the most negative customer sentiment for a specific product? | Cross-layer bridging, sentiment aggregation, supplier traversal |
| CQ2 | What is the correlation between defect rates from Supplier X and customer satisfaction scores for products containing their parts? | Multi-metric correlation, cross-layer aggregation, relationship properties |
| CQ3 | For a given part type, which suppliers offer the best combination of quality metrics, delivery performance, and pricing? | Multi-criteria ranking, relationship properties (`unit_cost`, `lead_time_days`), cross-layer quality data |
| CQ4 | Which specific components or materials consistently receive negative customer feedback across multiple products? | Cross-layer aggregation, consistency filter (multiple products), CORRESPONDS_TO bridging |
| CQ5 | What is the complete traceability path from a customer complaint about product functionality to the specific supplier and part responsible? | Full 5+ hop cross-layer traversal, most complex graph navigation |
| CQ6 | How has supplier performance (quality, delivery, cost) changed over the last 12 months for suppliers of a specific part type? | Temporal analysis (may not have time data), relationship properties, cross-layer quality metrics |
| CQ7 | Which alternative suppliers are available for parts currently sourced from underperforming suppliers? | Negation (underperforming), cross-layer quality assessment, alternative discovery |

### Test Priority Matrix

**Must-pass (directly caused failures in current system):**

| ID | Question (abbreviated) | Failure Mode |
|----|----------------------|-------------|
| 1.1 | Lead times and unit costs from suppliers for defective parts | Relationship property on wrong object (NULL results) |
| 2.2 | Products rated below 3 out of 5 | String comparison instead of numeric parsing |
| 2.3 | Suppliers with unit cost under $40 | Format parsing + relationship property (combined) |
| 3.1 | Suppliers involved in best-rated products | Premature aggregation cutoff |
| 5.1 | Parts each supplier provides | Reversed direction + hallucinated relationship |
| 6.3 | Products each reviewer recommends | Hallucinated non-existent relationship |
| 1.5 | Parts per assembly (quantity ambiguity) | Same property name on node and relationship |

**High-value (combines multiple challenge categories):**

| ID | Question (abbreviated) | Categories Combined |
|----|----------------------|-------------------|
| 2.5 | Average price of products with defects | Format parsing + aggregation + cross-layer |
| 3.5 | Supplier countries for @scandi_lover's products | 7-hop traversal across both layers |
| 4.4 | Products with price and average rating | Overlapping labels + format parsing + bridging |
| 7.1 | Rank suppliers by average product rating | 8-hop traversal + aggregation + format parsing |
| 7.4 | Defects reported per supplier | Cross-layer aggregation with grouping |
| 8.3 | Parts without preferred supplier | Negation + relationship property |

**Approved CQs (production benchmark):**

| CQ | Priority | Categories Tested |
|----|----------|------------------|
| CQ1 | High | Cross-layer, aggregation, sentiment |
| CQ3 | High | Relationship properties, multi-criteria, cross-layer |
| CQ5 | High | Full cross-layer traversal, traceability |

### Success Criteria

The GraphSchema architecture is validated when:

1. **Must-pass questions** produce correct Cypher on the first generation
   call, without retries or manual context in the `context` parameter.

2. **High-value questions** produce correct results in at most 2 LLM calls
   (strategy selection + Cypher generation), with no more than 1 repair
   cycle if cross-layer validation catches an issue.

3. **Approved CQs** (CQ1, CQ3, CQ5) produce evidence-backed answers via
   the Cypher strategy without falling back to vector or hybrid search
   as a workaround for Cypher generation failure.

4. **No question in any category** triggers a hallucinated relationship
   type that could have been caught by schema validation.
