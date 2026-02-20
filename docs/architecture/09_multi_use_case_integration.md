# Multi-Use-Case Integration

## Purpose

Enable incremental knowledge graph growth by building one use case at a time and merging them through shared concepts. Each use case follows the full KG-Factory pipeline independently. Integration happens explicitly when the user decides to connect two use cases.

## Design Principle

**Build independently, integrate later.** Each use case produces a self-contained knowledge graph with its own schema, entities, and competency questions. The existing graph is always the base. New use cases merge into it sequentially.

```
Time 0:   Build KG for Use Case 1          --> Graph contains UC1 data
Time N:   Build KG for Use Case 2          --> Graph contains UC1 + UC2 (isolated)
Time N+1: Merge UC2 into UC1               --> Graph is unified
Time M:   Build KG for Use Case 3          --> Graph contains unified + UC3 (isolated)
Time M+1: Merge UC3 into unified graph     --> Graph grows
```

## Target Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            UNIFIED KNOWLEDGE GRAPH                         │
│                                                                             │
│   USE CASE 1                    USE CASE 2                USE CASE 3       │
│   (supply_chain)                (customer_exp)            (procurement)    │
│                                                                             │
│   ┌──────────┐                  ┌──────────┐              ┌──────────┐    │
│   │ Domain   │                  │ Domain   │              │ Domain   │    │
│   │ Graph    │                  │ Graph    │              │ Graph    │    │
│   └────┬─────┘                  └────┬─────┘              └────┬─────┘    │
│        │                              │                         │          │
│        │ CORRESPONDS_TO               │ CORRESPONDS_TO          │          │
│        │                              │                         │          │
│   ┌────┴─────┐                  ┌────┴─────┐              ┌────┴─────┐    │
│   │ Subject  │                  │ Subject  │              │ Subject  │    │
│   │ Graph    │                  │ Graph    │              │ Graph    │    │
│   └────┬─────┘                  └────┬─────┘              └────┴─────┘    │
│        │ MENTIONS                     │ MENTIONS                           │
│   ┌────┴─────┐                  ┌────┴─────┐                              │
│   │ Lexical  │                  │ Lexical  │                              │
│   │ Graph    │                  │ Graph    │                              │
│   └──────────┘                  └──────────┘                              │
│                                                                             │
│                     CROSS-USE-CASE LINKS                                   │
│                                                                             │
│   (Product:supply_chain) ──SAME_AS──> (Product:customer_exp)              │
│   (Supplier:supply_chain) ──SAME_AS──> (Vendor:procurement)               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Provenance Model

Every node in Neo4j carries a `_use_case` property that identifies which use case created it. This enables:

- Querying a single use case in isolation
- Identifying shared concepts across use cases
- Tracing data lineage after merges

```cypher
(:Product {product_id: "P-1000", name: "Stockholm Chair", _use_case: "supply_chain"})
(:Customer {name: "@scandi_lover", _use_case: "customer_experience"})
```

## Directory Structure

Each use case gets its own workspace with independent state and data. A top-level `merged/` directory holds the unified state that results from merging use cases:

```
project/
├── merged/                     <-- unified state (the "base")
│   ├── .mcp.json              <-- KG_STATE_DIR=./state (for querying the unified graph)
│   └── state/
│       └── current_state.json <-- result of all merges, used for kg_query
│
├── use_cases/
│   ├── supply_chain/           <-- UC1 (original state preserved)
│   │   ├── .mcp.json          <-- KG_STATE_DIR=./state, KG_DATA_DIR=./data
│   │   ├── CLAUDE.md
│   │   ├── data/
│   │   │   ├── products.csv
│   │   │   ├── suppliers.csv
│   │   │   └── reviews/*.md
│   │   └── state/
│   │       └── current_state.json
│   │
│   ├── customer_experience/    <-- UC2 (original state preserved)
│   │   ├── .mcp.json          <-- KG_STATE_DIR=./state, KG_DATA_DIR=./data
│   │   ├── CLAUDE.md
│   │   ├── data/
│   │   │   ├── returns.csv
│   │   │   └── feedback/*.md
│   │   └── state/
│   │       └── current_state.json
│   │
│   └── procurement/            <-- UC3 (original state preserved)
│       ├── .mcp.json
│       ├── CLAUDE.md
│       ├── data/
│       │   └── purchase_orders.csv
│       └── state/
│           └── current_state.json
│
└── neo4j/                      <-- single shared instance
```

All use cases write to the **same Neo4j database**. Isolation is logical (via `_use_case` property), not physical.

Individual use case directories **preserve their original state files** unchanged. This serves as an audit trail: you can always see what each use case contributed before merging.

## Operational Workflow

### Phase A: Use Case 1 (Already Complete)

The first use case is built using the standard pipeline. No special steps required.

One-time retroactive tagging of existing nodes:

```cypher
MATCH (n) WHERE n._use_case IS NULL SET n._use_case = "supply_chain"
```

### Phase B: Build New Use Case

Open Claude Code in the new use case directory. The `.mcp.json` points to the same MCP server with different state/data paths:

```json
{
  "mcpServers": {
    "kg-factory": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "env": {
        "KG_STATE_DIR": "./state",
        "KG_DATA_DIR": "./data"
      }
    }
  }
}
```

Run the full pipeline as normal:

```
1. kg_user_intent       --> approved_user_goal + use_case identifier
2. kg_file_suggestion   --> approved_files
3. kg_schema_proposal   --> approved_construction_plan
4. kg_critic            --> validation
5. kg_ner_extraction    --> approved_entity_types
6. kg_fact_extraction   --> approved_fact_types
7. kg_competency_questions --> approved_competency_questions
8. kg_build_graph       --> nodes written to Neo4j with _use_case tag
```

After build, Neo4j contains both use cases side by side. No connections between them. Each is queryable in isolation by filtering on `_use_case`.

### Phase C: Merge

Triggered explicitly by the user when ready to integrate.

**Step C1 -- Detect concept overlaps**

Load both state files and compare `approved_entity_types` and `approved_construction_plan`. Concepts fall into three buckets:

| Bucket | Example | Action |
|--------|---------|--------|
| Same label, both use cases | `Product` in UC1 and UC2 | Merge candidate |
| Different label, same meaning | `Supplier` (UC1) vs `Vendor` (UC3) | User confirms match |
| Unique to new use case | `ReturnRequest` in UC2 only | Keep as-is |

**Step C2 -- User decides merge strategy per shared concept**

For each shared concept, the user specifies:
- **Match key**: which property to join on (e.g., `product_id`)
- **Property merge**: which properties to copy from new to base
- **Conflict resolution**: what to do when both have the same property with different values

**Step C3 -- Execute merge**

For matched instances (same concept, same entity):

```cypher
// Copy new properties onto base node
MATCH (base:Product {_use_case: "supply_chain"})
MATCH (new:Product {_use_case: "customer_experience"})
WHERE base.product_id = new.product_id
SET base.return_rate = new.return_rate,
    base.satisfaction_score = new.satisfaction_score

// Move relationships from new node to base node
// (relationships now connect to the unified entity)

// Remove duplicate node
DETACH DELETE new
```

For unmatched instances (exist only in new use case): keep them, they expand the graph.

**Step C4 -- Merge state files**

Combine approved artifacts from both state files into a unified state and save to `merged/state/current_state.json`:

```python
merged_state = {
    "use_cases": ["supply_chain", "customer_experience"],
    "approved_construction_plan": {**plan_1, **plan_2},
    "approved_entity_types": {**types_1, **types_2},
    "approved_fact_types": {**facts_1, **facts_2},
    "approved_competency_questions": {**cqs_1, **cqs_2},
}
# Save to merged/state/current_state.json
```

The original use case state files remain untouched in their directories.

### Phase D: Query Unified Graph

After merge, open Claude Code in the `merged/` directory. Its `.mcp.json` points to the merged state:

```json
{
  "mcpServers": {
    "kg-factory": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "env": {
        "KG_STATE_DIR": "./state"
      }
    }
  }
}
```

All query strategies work across use cases seamlessly because the merged state contains the combined schema:

```
"Which suppliers provide parts for products with the highest return rates?"

Path: Product -[HAS_ASSEMBLY]-> Assembly -[HAS_PART]-> Part -[SUPPLIED_BY]-> Supplier
      (supply_chain relationships)     (supply_chain)     (supply_chain)
      Product.return_rate              (from customer_experience, merged onto same node)
```

## State Lifecycle Across Multiple Merges

The merged state is always the **base** for the next merge. Individual use case states are inputs, the merged state is the accumulator.

```
UC1 state ─────────────┐
                        ├──> Merge ──> merged/state/current_state.json (v1)
UC2 state ─────────────┘                        │
                                                 │
UC3 state ─────────────┐                        │
                        ├──> Merge ──> merged/state/current_state.json (v2)
         merged state (v1) ────────────┘         │
                                                 │
UC4 state ─────────────┐                        │
                        ├──> Merge ──> merged/state/current_state.json (v3)
         merged state (v2) ────────────┘
```

**When UC3 arrives, the process is:**

1. Build UC3 in `use_cases/procurement/` using the standard pipeline (Phase B)
2. Run `kg_merge` loading two state files:
   - **Base**: `merged/state/current_state.json` (result of UC1 + UC2 merge)
   - **New**: `use_cases/procurement/state/current_state.json`
3. The merge tool compares UC3's entity types against the **unified** schema (which already contains UC1 + UC2 types)
4. Save result back to `merged/state/current_state.json`

The merged state always contains the complete picture: all construction plans, all entity types, all fact types, and all competency questions from every use case merged so far. This is the only state file needed for querying.

**What happens to use case directories after merge?**

They stay as they are. They serve two purposes:
- **Audit trail**: see exactly what each use case contributed
- **Rebuild capability**: if you need to rebuild a use case's graph (e.g., after data correction), you have its original state and data

You never need to go back to an individual use case state file for querying — the merged state has everything.

## Scaling Considerations

### Entity Resolution Scoping

Entity resolution (`scope="resolve"`) must be scoped to the current use case during build. Without scoping, the Cartesian product match runs against all entities in the graph, including those from other use cases:

```cypher
-- Current (graph-wide, becomes expensive with multiple use cases)
MATCH (entity:Product:__Entity__), (domain:Product)
WHERE NOT domain:__Entity__

-- Scoped (only within same use case)
MATCH (entity:Product:__Entity__), (domain:Product)
WHERE NOT domain:__Entity__
  AND entity._use_case = domain._use_case
```

### State File as Portable Artifact

Each use case's `current_state.json` is a complete, self-contained description of its schema. It contains all approved artifacts and can be loaded independently. This makes state files the natural unit for concept comparison during merge -- no separate catalog is needed.

After merge, `merged/state/current_state.json` becomes the authoritative state for querying. It accumulates schema information from all merged use cases. The `kg_merge` tool always loads this file as the base when integrating a new use case.

### Query Strategy Awareness

After merge, the query strategy selector should include merged use case context:

```
Graph contains data from 2 use cases: supply_chain, customer_experience
Domain layer: 7 node types (Product, Assembly, Part, Supplier, Customer, ReturnRequest, SupportTicket)
Text layer: 5 entity types (QualityIssue, AssemblyExperience, Sentiment, ProductDefect, FeatureRequest)
```

## Next Steps

### Foundation (minimal changes to current codebase)

1. **Add `_use_case` property to all nodes during graph build**
   - `domain_builder.py`: add `n._use_case = $use_case` to the UNWIND import query
   - `text_builder.py`: post-processing step to tag chunks and entities
   - Read from `state["use_case"]`

2. **Add `use_case` key to state during `kg_user_intent`**
   - User Intent agent extracts or generates a short identifier
   - Stored as `state["use_case"]`

3. **Scope entity resolution to same `_use_case`**
   - Add `AND entity._use_case = domain._use_case` filter to resolution queries

4. **Tag existing graph data retroactively**
   - One-time Cypher query for graphs built before this change

### Integration tooling (build when first merge is needed)

5. **`kg_merge` MCP tool**
   - Loads base state (merged/) and new use case state
   - Compares entity types and construction plans
   - Presents overlap report to user
   - Executes merge in Neo4j based on user decisions
   - Saves merged state to `merged/state/current_state.json`

6. **Merge conflict detection**
   - Same property name with different values across use cases
   - Same label with different schema (different property sets)
   - Relationship type collisions
