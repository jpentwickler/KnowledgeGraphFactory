# US025: Virtualized Domain Layer Prototype

> A throwaway learning prototype that answers the Databricks migration question on a laptop:
> does the cross-layer bridge still work when the structured domain layer is not copied into
> Neo4j, but is reached by key, at query time, from the furniture CSVs through a virtual graph?

Drafted by voice: vault note `projects/Ontology Pipeline/drafts/story-virtualized-domain-layer-prototype.md`

## User Story

**As a** KG-Factory Developer
**I want** to run the furniture traceability question (CQ5) against a graph whose domain layer
stays in the CSVs and is reached through a virtual graph over DuckDB
**So that** I know whether the `CORRESPONDS_TO` bridge, and the entity resolution that writes it,
survive a move to a virtualized (Databricks-style) domain layer

## Story Points: ?

**Open question:** points. The risk is in the virtualization engine (Ontop or self-managed
Neo4j Virtual Graph against DuckDB), which the repo has never used.

## Status: TODO — picked up from a voice draft, not yet planned

## Context

Today the furniture example loads both layers into one Neo4j database. A text entity
(e.g. `Part:__Entity__ {name: "drawer rails"}`) reaches its domain node through
`CORRESPONDS_TO`, which `pipelines/entity_resolution.py` writes by fuzzy name match
(Jaro-Winkler). Both ends live in the same database.

The narrow, new claim this story tests:

> Does the `CORRESPONDS_TO` bridge survive when the domain entity it points to lives in a
> file and is reached by key through a virtual graph, instead of being a native Neo4j node?

A relationship cannot span two graphs, so the bridge has to change shape:

1. **Preferred, key-join:** the bridge resolves through a shared key. The composite query
   collects keys natively, then hands them to the virtual graph to fetch the rows.
2. **Fallback, proxy node:** `CORRESPONDS_TO` stays a stored edge to a proxy node that holds
   only the key, and the proxy resolves to the CSV row through the virtual layer.

Architecture: CSVs → **DuckDB** (each file as a SQL view, no import) → **virtualization
engine** (graph query → SQL with pushdown, nothing materialized) → results.

| Engine | Why |
|---|---|
| **Ontop** (R2RML/Ontop mapping → SPARQL; DuckDB since 5.0.2; Apache 2.0) | Standards-based, prints the generated SQL. Good first step. |
| **Neo4j Virtual Graph, self-managed** (DuckDB via JDBC; `schema.json` + Cypher) | Closest rehearsal for Databricks; enables composite queries. |

Related design: `docs/architecture/13_multi_source_virtualization.md` (Neo4j as topology
index, detail fetched from source) and `docs/architecture/15_adaptive_retrieval_architecture.md`.

## Acceptance Criteria

### What stays native, what goes virtual

- [ ] ⚑ The domain layer (products, assemblies, parts, suppliers, part–supplier mapping) is
  **not** loaded into Neo4j; it is read from `examples/furniture_supply_chain/data/*.csv`
  through DuckDB views
- [ ] The text side stays native in Neo4j: review chunks with embeddings, reviews, defects
  and the other text entities. Vector/hybrid search runs natively
- [ ] ⚑ Every text entity that bridges to the domain carries the **domain key** (e.g. part
  `S-1085`), identical to the key in the CSV, so the seam tests virtualization and not
  entity resolution
- [ ] **Open question:** the draft also lists a native Subject layer (defect observations) and
  a Concept layer (SKOS concepts), and says the bridge carries "the concept it was classified
  as". Neither layer exists in the code yet (SKOS appears only in
  `docs/architecture/target_architecture_ontology_enhanced_knowledge_graphs.md`; defects are
  `Defect:__Entity__`). Build them for this prototype, or use the existing text layer?

### The bridge

- [ ] ⚑ `CORRESPONDS_TO` is resolved by key across the boundary, as a key-join (preferred) or
  through a key-only proxy node (fallback). The chosen variant is recorded with the reason

### CQ5 traceability, end to end

- [ ] ⚑ CQ5 runs: drawer-rails complaint → review chunk → defect → (concept?) → **cross on part
  key** → supplier rows still in the CSV
- [ ] ⚑ The result returns **Shanghai Metal Corp** and **Korean Metal Works** with their two
  prices, read live from `part_supplier_mapping.csv`
- [ ] Primary path: a composite query (native traversal collects part keys, the virtual graph
  fetches rows) through Neo4j Virtual Graph + DuckDB
- [ ] Fallback path, if the primary does not work: two explicit hops in application code
  (Neo4j for defects + part keys, then Ontop/DuckDB for those keys)
- [ ] One parts-per-supplier roll-up answered through the virtual layer

### Design probe findings

- [ ] A short write-up records:
  - why key-based resolution survives virtualization and fuzzy name matching does not
    (there is no domain node to fuzzy-match at build time)
  - which half of the query pushes down to SQL and which must stay native
- [ ] **Open question:** where the prototype code and write-up live (e.g. a new `prototypes/`
  directory, or an `examples/` folder)

### Out of scope

- [ ] Scale and latency: seconds, not milliseconds, is accepted
- [ ] Virtualizing any layer other than the domain layer
- [ ] Changing the production pipelines (`entity_resolution.py`, query builder, MCP tools);
  this is a throwaway prototype
- [ ] Parquet / lakehouse tables (DuckDB reads Parquet, so that is a later small step)
- [ ] Regenerating our own CSVs. The furniture dataset comes from the Neo4j/DeepLearning.AI
  course, which is fine for a learning prototype but must be replaced before any shippable demo

## Human Verification Guide

1. Confirm Neo4j holds no domain nodes: `MATCH (n:Supplier) WHERE NOT n:__Entity__ RETURN count(n)` returns 0.
2. Run the CQ5 query (or the two-hop fallback) and see Shanghai Metal Corp and Korean Metal
   Works with their prices for the drawer rails.
3. Edit one of those prices in `part_supplier_mapping.csv`, re-run, and see the new price,
   which proves the row is read live and was not copied.
4. Read the write-up and check it answers the thesis question with a yes/no and the variant used.

## Notes

- "Drawer Rails" is two parts in the CSV, `S-1078` and `S-1085`, and both are supplied by
  the same two suppliers. A fuzzy name match on "drawer rails" cannot tell them apart, which is
  exactly the case where key resolution matters.
- **Open question:** the draft says the cross-layer traversal "has already been proven
  Neo4j-to-Neo4j". Which run or story is that (US015 / US023 evaluation)?
