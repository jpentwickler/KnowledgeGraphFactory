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

## Story Points: 5

The risk is in the virtualization engines (Ontop and self-managed Neo4j Virtual Graph
against DuckDB), which the repo has never used.

## Status: planned — plan below, awaiting go-ahead

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
- [ ] The text side is the layer the pipeline builds today (review chunks, `Review`,
  `Defect:__Entity__`, `Part:__Entity__`). The draft's Subject (defect observation) and Concept
  (SKOS) layers are **not** built here; the concept hop is dropped from CQ5 (decided in planning)

### The bridge

- [ ] ⚑ `CORRESPONDS_TO` is resolved by key across the boundary, as a key-join (preferred) or
  through a key-only proxy node (fallback). The chosen variant is recorded with the reason

### CQ5 traceability, end to end

- [ ] ⚑ CQ5 runs: drawer-rails complaint → review chunk → defect → part entity → **cross on part
  key** → supplier rows still in the CSV
- [ ] ⚑ The result returns **Shanghai Metal Corp** and **Korean Metal Works** with their two
  prices, read live from `part_supplier_mapping.csv`
- [ ] Two explicit hops in application code: Neo4j for defects + part keys, then DuckDB for
  those keys (built first: it proves the seam with the fewest moving parts)
- [ ] The second hop also runs through Ontop over DuckDB (SPARQL), with the generated SQL shown
- [ ] Composite query (native traversal collects part keys, the virtual graph fetches rows)
  through self-managed Neo4j Virtual Graph + DuckDB. If its setup does not work, the reason is
  recorded and the two-hop result stands as the proof
- [ ] One parts-per-supplier roll-up answered through the virtual layer

### Design probe findings

- [ ] A short write-up records:
  - why key-based resolution survives virtualization and fuzzy name matching does not
    (there is no domain node to fuzzy-match at build time)
  - which half of the query pushes down to SQL and which must stay native
- [ ] Prototype code and write-up live in `prototypes/us025_virtual_domain/`

### Out of scope

- [ ] Scale and latency: seconds, not milliseconds, is accepted
- [ ] Virtualizing any layer other than the domain layer
- [ ] Building Subject (defect observation) or Concept (SKOS) layers
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
- The draft says the cross-layer traversal "has already been proven Neo4j-to-Neo4j". No CQ5
  run is recorded in the repo (`examples/furniture_supply_chain/eval/results/` holds only
  extraction metrics); CQ5 is listed as approved in
  `docs/architecture/14_canonical_graph_schema.md`. Not blocking for this story.
- The complaint resolves to **S-1085**: Helsingborg Dresser (`P-1007`) → Drawers (`A-1070`) →
  Drawer Rails (`S-1085`) → Korean Metal Works $47.14, Shanghai Metal Corp $40.82.

## Plan

### Decisions taken in planning (2026-10-03)

| Question | Decision |
|---|---|
| Text side | Existing text layer only; no Subject/Concept layers, no concept hop |
| Engine order | Two-hop (Python → DuckDB) → Ontop over DuckDB → Neo4j Virtual Graph |
| Code location | `prototypes/us025_virtual_domain/` |
| Points | 5 |
| Bridge variant | Key-join: text entities carry `part_id`; no stored edge crosses the boundary. Proxy node only if Virtual Graph needs it |

### Build order

Each step is a commit on `us-025-virtualized-domain-layer`.

1. **DuckDB domain views** (`duckdb_domain.py`, `build_duckdb.py`). `build_duckdb.py`
   creates `furniture.duckdb` with one **view** per CSV (`read_csv`, nothing imported) and
   parses `unit_cost` (`$47.14`) to a decimal. Lookup functions: `suppliers_for_parts(keys)`
   and `parts_per_supplier()`. Unit tests: S-1085 returns the two suppliers and prices, and
   editing a temp copy of the CSV changes the result without a rebuild (proves "live").
2. **Key resolution against the virtual side** (`stamp_keys.py`). For each
   `Part:__Entity__` mentioned in a review of a product, resolve product name → `product_id`
   → assemblies → parts with the same part name, **through DuckDB**, and set `part_id` on the
   entity. Ambiguous or unmatched → no key, reported. Unit test: Helsingborg Dresser +
   "drawer rails" → S-1085, not S-1078.
3. **Native side + CQ5 two-hop** (`load_native.py`, `cq5_two_hop.py`). `load_native.py`
   runs the existing text builder (`pipelines/text_builder.py`) on the furniture reviews with
   **no** domain build and no `CORRESPONDS_TO` resolution, then runs step 2. `cq5_two_hop.py`:
   hop 1 hybrid search + `FROM_CHUNK` → `Defect` → `Part:__Entity__` collects `part_id`s in
   Neo4j; hop 2 fetches supplier rows from DuckDB; plus the parts-per-supplier roll-up. Unit
   test with a stubbed hop 1. Needs Neo4j + API keys, so runs on the laptop.
4. **Ontop** (`ontop/furniture.obda`, `ontop/furniture.properties`, `ontop/*.rq`,
   `run_ontop.sh`). Mapping from the DuckDB views to RDF classes Part, Supplier, Product,
   Assembly; SPARQL for the hop-2 supplier lookup and the roll-up; the script runs Ontop CLI
   and prints the generated SQL. `cq5_two_hop.py --via ontop` uses the SPARQL endpoint for hop 2.
5. **Neo4j Virtual Graph** (`virtual_graph/datasource.json`, `schema.json`, `cq5_composite.cypher`,
   `SETUP.md`). DuckDB datasource; schema maps the domain tables to labels keyed on
   `part_id`/`supplier_id`; composite Cypher collects keys natively and fetches rows from the
   virtual graph. Setup steps written from Neo4j's self-managed docs; it appears to need
   `internal.virtual_graph.*` settings, so it may be preview/Enterprise-only. If it can't run,
   `SETUP.md` records why.
6. **Write-up and wrap-up** (`FINDINGS.md`, `README.md`). Thesis answer (yes/no + variant),
   why key resolution survives and fuzzy name matching doesn't (the S-1078/S-1085 case),
   what pushed down to SQL vs stayed native, Ontop's generated SQL. Tick the criteria, move
   the status to `built, awaiting review`, update the index row.

### Where each step can run

This cloud session has Python + DuckDB but **no Neo4j, no Docker daemon, and no access to
GitHub releases or neo4j.com**, so Ontop and Virtual Graph cannot be downloaded here.

| Step | Built here | Verified here | Verified on the laptop |
|---|---|---|---|
| 1 DuckDB views | ✓ | unit tests | — |
| 2 Key resolution | ✓ | unit tests (DuckDB side) | against Neo4j |
| 3 Native + two-hop | ✓ | stubbed unit test | full CQ5 run |
| 4 Ontop | files + script | — | run Ontop, see SQL |
| 5 Virtual Graph | config + Cypher | — | enable VG, run composite query |
| 6 Write-up | ✓ | — | fill in laptop results |

### Verification

- `pytest tests/unit/test_us025_virtual_domain.py` passes, and the existing unit suite still
  passes (no production code changes).
- On the laptop: the Human Verification Guide above, run once per path (two-hop, Ontop, Virtual
  Graph). `FINDINGS.md` records results and any path that could not run.
