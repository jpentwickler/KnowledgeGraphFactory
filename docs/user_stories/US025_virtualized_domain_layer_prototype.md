# US025: Virtualized Domain Layer Prototype

> A throwaway learning prototype that answers the Databricks migration question on a laptop:
> does the cross-layer bridge still work when the structured domain layer is not copied into
> Neo4j at all, but is reached by key, at query time, from the furniture CSVs through a
> virtual graph? And can that zero-copy design replace the selective materialization in
> `docs/architecture/13_multi_source_virtualization.md`?

Drafted by voice: vault note `projects/Ontology Pipeline/drafts/story-virtualized-domain-layer-prototype.md`

## User Story

**As a** KG-Factory Developer
**I want** to run the furniture traceability question (CQ5) against a graph whose domain layer
stays in the CSVs and is reached through Neo4j Virtual Graph over DuckDB
**So that** I know whether the `CORRESPONDS_TO` bridge, and the entity resolution that writes it,
survive a move to a virtualized (Databricks-style) domain layer, and what zero-copy costs
compared with selective materialization

## Story Points: 5

The risk is in Neo4j Virtual Graph (public preview, Enterprise-only when self-managed) and in
Ontop against DuckDB, neither of which the repo has used.

## Status: planned — plan revised after review on PR #1, awaiting go-ahead

## Context

Today the furniture example loads both layers into one Neo4j database. A text entity
(e.g. `Part:__Entity__ {name: "drawer rails"}`) reaches its domain node through
`CORRESPONDS_TO`, which `pipelines/entity_resolution.py` writes by fuzzy name match
(Jaro-Winkler). Both ends live in the same database.

`docs/architecture/13_multi_source_virtualization.md` §2.1 and `future_ideas.md` Idea 8
describe **selective materialization**: Neo4j stores IDs, relationships and match keys, and
detail rows are fetched from the source. This story tests the alternative: **zero-copy**.
No structured data is stored in Neo4j at all; the only domain information on the Neo4j side
is the `part_id` stamped on text entities, which is the bridge itself.

The narrow, new claim this story tests:

> Does the `CORRESPONDS_TO` bridge survive when the domain entity it points to lives in a
> file and is reached by key through a virtual graph, instead of being a native Neo4j node?

A relationship cannot span two graphs, so the bridge becomes a **key-join**: text entities
carry `part_id`; the query collects keys natively, then hands them to the virtual graph to
fetch the rows.

Architecture: CSVs → **DuckDB** (each file as a SQL view, no import) → **Neo4j Virtual
Graph** (Cypher → SQL, nothing materialized) → results. Ontop (SPARQL over the same DuckDB
views) is an optional comparison.

Facts about Virtual Graph, checked on 2026-10-03 (review on PR #1):
- Public preview since 2026-07-23. Self-managed needs **Neo4j Enterprise**, is enabled with
  `internal.virtual_graph.enabled` / `internal.virtual_graph.home`, and reads `secret.json`,
  `datasource.json` and `schema.json` **at boot** (a schema change needs a restart; an invalid
  config fails the boot). DuckDB has a documented driver.
- A single Cypher statement spanning a native and a virtual graph is on Neo4j's roadmap, not
  available. So the main CQ5 path is **two Cypher queries joined in app code**.

References: [enabling Virtual Graph](https://neo4j.com/docs/virtual-graph/self-managed/enabling-virtual-graph/),
[DuckDB driver](https://neo4j.com/docs/virtual-graph/self-managed/jdbc-drivers/duckdb/),
[public preview](https://neo4j.com/blog/auradb/neo4j-virtual-graph-is-now-in-public-preview/),
[community playground](https://github.com/ikwattro/neo4j-virtual-graph-playground).

## Acceptance Criteria

### What stays native, what goes virtual

- [ ] ⚑ **No structured data is materialized in Neo4j**: no domain rows, no keys-only domain
  nodes, no thin topology layer, no proxy nodes. The only domain information on the Neo4j side
  is `part_id` on text entities
- [ ] ⚑ The domain layer (products, assemblies, parts, suppliers, part–supplier mapping) is read
  from `examples/furniture_supply_chain/data/*.csv` through DuckDB views
- [ ] The text side is the layer the pipeline builds today (review chunks with embeddings,
  `Review`, `Defect:__Entity__`, `Part:__Entity__`), built from an empty database through the
  existing `kg_build_graph(scope="unstructured")` path, so both `chunk-embeddings` and
  `chunk-fulltext` exist. `scope="structured"` and `scope="resolve"` are never run
- [ ] The draft's Subject (defect observation) and Concept (SKOS) layers are not built; the
  concept hop is dropped from CQ5

### The bridge

- [ ] ⚑ Every bridging `Part:__Entity__` carries a `part_id` identical to the CSV key
  (e.g. `S-1085`). The product it belongs to comes from its source document; a part linked to
  more than one product is reported as ambiguous and gets no key

### Virtual Graph spike

- [ ] ⚑ Self-managed Virtual Graph runs on Neo4j Enterprise against the DuckDB views and answers
  `(:Part {part_id:'S-1085'})-[:SUPPLIED_BY]->(:Supplier)` with prices from the CSV. Version,
  edition and settings are recorded in `SETUP.md`. If it cannot run, the reason is recorded

### CQ5 traceability, end to end

- [ ] ⚑ CQ5 runs as two Cypher queries joined in app code: native Neo4j (hybrid search →
  chunk → defect → part entity → `part_id`s), then the virtual graph (parts → suppliers with
  prices)
- [ ] ⚑ The result returns **Shanghai Metal Corp** and **Korean Metal Works** with their two
  prices, read live from `part_supplier_mapping.csv`
- [ ] A single-statement composite query is attempted; whether it works on the version used, or
  the error it gives, is recorded
- [ ] Baseline: the same second hop through plain Python + DuckDB (also zero-copy). This is the
  zero-copy proof if Virtual Graph cannot run
- [ ] One parts-per-supplier roll-up answered through the virtual layer
- [ ] Optional: the second hop through Ontop over DuckDB (SPARQL), with the generated SQL shown

### Findings

- [ ] `FINDINGS.md` answers directly: **can zero-copy through Neo4j Virtual Graph replace
  selective materialization, and what does it cost?** It compares against doc 13 on traversal
  latency, freshness/sync, maturity, and what pushes down to SQL
- [ ] It states the resolution finding without overclaiming: `stamp_keys.py` still matches on
  part *name*, narrowed to one product by querying the virtual side at build time. Resolution
  has to query the source; it does not depend on materialized domain nodes
- [ ] Prototype code and write-up live in `prototypes/us025_virtual_domain/`

### Out of scope

- [ ] Scale and latency targets: seconds, not milliseconds, is accepted (latency is measured,
  not optimized)
- [ ] Virtualizing any layer other than the domain layer
- [ ] Building Subject (defect observation) or Concept (SKOS) layers
- [ ] Changing the production pipelines (`entity_resolution.py`, query builder, MCP tools) or
  the shared `state/current_state.json`; this is a throwaway prototype
- [ ] Editing doc 13 or `future_ideas.md` Idea 8. If the answer is yes, a follow-up story
  updates them
- [ ] Parquet / lakehouse tables (DuckDB reads Parquet, so that is a later small step)
- [ ] Regenerating our own CSVs. The furniture dataset comes from the Neo4j/DeepLearning.AI
  course, which is fine for a learning prototype but must be replaced before any shippable demo

## Human Verification Guide

On the owner's machine, with the env vars in `prototypes/us025_virtual_domain/README.md`:

1. **Spike:** `./run_spike.sh` starts Neo4j Enterprise with Virtual Graph; `spike.cypher`
   returns Korean Metal Works $47.14 and Shanghai Metal Corp $40.82 for `S-1085`. `SETUP.md`
   has the version, edition and settings filled in.
2. **Empty database:** `MATCH (n) RETURN count(n)` returns 0 on the native database.
3. **Build:** `python load_native.py` processes all 10 review files. `SHOW INDEXES` shows
   `chunk-embeddings` and `chunk-fulltext` as `ONLINE`.
4. **No domain nodes:** `MATCH (n) WHERE NOT n:__Entity__ AND NOT n:Chunk AND NOT n:Document
   RETURN labels(n), count(*)` returns nothing, and no `CORRESPONDS_TO` exists.
5. **Keys:** `python stamp_keys.py` stamps `part_id = 'S-1085'` on the drawer-rails part
   entity and lists any ambiguous or unmatched parts.
6. **CQ5:** `python cq5.py --via virtual-graph` (main), then `--via duckdb` (baseline), each
   returns the two suppliers with prices. The composite attempt's result is in `FINDINGS.md`.
7. **Live:** edit one of those prices in `part_supplier_mapping.csv`, re-run step 6, and see
   the new price without any rebuild.
8. Read `FINDINGS.md` and check it answers the zero-copy question against doc 13.

## Notes

- "Drawer Rails" is two parts in the CSV, `S-1078` and `S-1085`, and both are supplied by
  the same two suppliers. A fuzzy name match on "drawer rails" cannot tell them apart, which is
  exactly the case where narrowing by product matters.
- The complaint resolves to **S-1085**: Helsingborg Dresser (`P-1007`) → Drawers (`A-1070`) →
  Drawer Rails (`S-1085`) → Korean Metal Works $47.14, Shanghai Metal Corp $40.82.
- All 10 review documents are titled `<product name> Reviews`, and each prefix matches exactly
  one `product_name` in `products.csv` (checked 2026-10-03).
- The draft says the cross-layer traversal "has already been proven Neo4j-to-Neo4j". No CQ5
  run is recorded in the repo (`examples/furniture_supply_chain/eval/results/` holds only
  extraction metrics); CQ5 is listed as approved in
  `docs/architecture/14_canonical_graph_schema.md`. Not blocking for this story.

## Plan

### Decisions

| Question | Decision |
|---|---|
| Text side | Existing text layer only; no Subject/Concept layers, no concept hop (planning) |
| Code location | `prototypes/us025_virtual_domain/` (planning) |
| Points | 5 (planning) |
| Materialization | **None.** No structured data in Neo4j; proxy-node fallback dropped (review) |
| Bridge | Key-join: `part_id` on `Part:__Entity__`; no stored edge crosses the boundary (review) |
| Engine order | Virtual Graph spike → CQ5 with Virtual Graph → Python/DuckDB baseline → Ontop, optional (review) |
| CQ5 shape | Two Cypher queries joined in app code; single-statement composite is an attempt only (review) |
| Product for a part | From its source document: `Part:__Entity__ <-[:FROM_CHUNK]- Chunk -[:FROM_DOCUMENT]-> Document`, title minus ` Reviews`. Always present, unlike the LLM-extracted `belongs_to` edge (review, chosen by worker) |
| Native build | Through `_build_unstructured` in `mcp_server/server.py` (creates both text indexes), on a filtered copy of `state/current_state.json` (review) |

### Build order

Each step is a commit on `us-025-virtualized-domain-layer`. All paths are under
`prototypes/us025_virtual_domain/`.

1. **Virtual Graph spike kit.**
   - `build_duckdb.py` creates `furniture.duckdb` with one **view** per CSV (`read_csv`,
     nothing imported) and `unit_cost` parsed from `$47.14` to a decimal. Unit tests: the view
     returns S-1085's two suppliers and prices; editing a temp copy of the CSV changes the
     result without a rebuild.
   - `virtual_graph/` holds `secret.json`, `datasource.json` (type `duckdb`, path to
     `furniture.duckdb`) and `schema.json`, mapping `Product`, `Assembly`, `Part` and
     `Supplier` with keys `product_id`, `assembly_id`, `part_id` and `supplier_id`, and
     `SUPPLIED_BY` carrying `unit_cost` and `lead_time_days`.
   - `run_spike.sh` starts `neo4j:2026.09.0-enterprise` (following the community playground),
     mounts the config, the DuckDB file and the CSVs at the same paths, and sets the
     `internal.virtual_graph.*` settings.
   - `spike.cypher` holds the S-1085 query.
   - `SETUP.md` has blanks for version, edition, settings and the result.
   - Runs on the owner's machine; this cloud session has no Docker daemon and no access to
     neo4j.com.
2. **State copy and native build.**
   - `prepare_state.py` writes `state/current_state.json` inside the prototype, keeping only
     `approved_entity_types`, `approved_fact_types` and `approved_files` from the tracked
     `state/current_state.json`. That drops `text_graph_progress`, the `*resolution_candidates`
     keys and the old schema and index keys. The shared file is only read.
   - Unit test: `_resolve_files_to_process(copy, "all")` returns all 10 review files, and the
     copy has none of the dropped keys.
   - `load_native.py` sets `KG_STATE_DIR` to the prototype's `state/` and `KG_DATA_DIR` to the
     furniture data, then calls `_build_unstructured`. Afterwards it checks that both indexes
     are `ONLINE` and that no non-text nodes exist. It never calls the structured or resolve
     scopes.
3. **Key stamping** (`stamp_keys.py`).
   - Cypher collects, for each `Part:__Entity__`, the products of its source documents
     (document title minus ` Reviews`; if `title` is absent on `Document`, its `path` maps to
     the file in `approved_files`).
   - A pure function resolves `(part name, product)` → `part_id` through the DuckDB views:
     product name → `product_id` → assemblies → parts with that part name, case-insensitive.
   - Exactly one product and one match → set `part_id`. More than one product → `ambiguous`.
     No match → `unmatched`. Both are reported, never guessed.
   - Unit tests: Helsingborg Dresser + "drawer rails" → S-1085, not S-1078; a part linked to
     two products → ambiguous; an unknown name → unmatched.
4. **CQ5 through Virtual Graph** (`cq5.py --via virtual-graph`, `cq5_composite.cypher`).
   - Hop 1 is native Cypher: hybrid search over `chunk-embeddings` + `chunk-fulltext`, with the
     question embedded by `text-embedding-3-large` (the build's model), then chunk →
     `FROM_CHUNK` → `Defect` → `observed_in` → `Part:__Entity__` → distinct `part_id`s.
   - Hop 2 is Cypher against the virtual graph: parts → `SUPPLIED_BY` → suppliers with prices.
   - The parts-per-supplier roll-up also runs on the virtual graph.
   - Each hop's time is measured.
   - `cq5_composite.cypher` is the single-statement attempt; its result goes into `FINDINGS.md`.
   - Unit test: the join logic with both hops stubbed.
5. **Python/DuckDB baseline** (`cq5.py --via duckdb`). Hop 2 and the roll-up go straight to the
   DuckDB views from Python. Unit-tested here with the same stubbed hop 1.
6. **Ontop, optional** (`ontop/furniture.obda`, `ontop/furniture.properties`, `ontop/*.rq`,
   `run_ontop.sh`). Mapping over the DuckDB views; SPARQL for hop 2 and the roll-up; the script
   prints Ontop's generated SQL. Done only if steps 1–5 are in.
7. **Write-up and wrap-up.**
   - `README.md` lists the env vars: `NEO4J_URI`, `NEO4J_USER` and `NEO4J_PASSWORD` for the
     native database, the Virtual Graph connection, and `OPENAI_API_KEY` (GPT-4o extraction and
     `text-embedding-3-large` embeddings).
   - `FINDINGS.md` answers the zero-copy question against doc 13 on latency, freshness/sync,
     maturity and pushdown, and states the resolution finding as worded above.
   - Tick the criteria, move the status to `built, awaiting review`, update the index row.

### Where each step can run

This cloud session has Python and DuckDB, but **no Neo4j, no Docker daemon, and no access to
neo4j.com or GitHub releases**. Steps that need them are prepared here and run on the owner's
machine.

| Step | Built here | Verified here | Verified on the owner's machine |
|---|---|---|---|
| 1 VG spike kit | ✓ | DuckDB view tests | spike query, `SETUP.md` |
| 2 State + native build | ✓ | state-copy test | empty DB → build → indexes `ONLINE` |
| 3 Key stamping | ✓ | resolution tests | stamped `part_id` on the graph |
| 4 CQ5 via VG | ✓ | stubbed join test | full CQ5, composite attempt |
| 5 DuckDB baseline | ✓ | stubbed hop-1 test | full CQ5 |
| 6 Ontop (optional) | files + script | — | generated SQL |
| 7 Write-up | ✓ | — | laptop results filled in |

### Verification

- `pytest tests/unit/test_us025_virtual_domain.py` passes, and the existing unit suite still
  passes (no production code changes).
- On the owner's machine: the Human Verification Guide above. `FINDINGS.md` records results and
  any path that could not run.
