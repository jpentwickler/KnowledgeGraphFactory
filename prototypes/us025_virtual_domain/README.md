# US025: Virtualized domain layer prototype

A throwaway prototype for one question: can the furniture traceability question (CQ5) cross
from the native text graph to a domain layer that stays in the CSVs, with **no structured data
in Neo4j**, through Neo4j Virtual Graph over DuckDB? Story:
[`docs/user_stories/US025_virtualized_domain_layer_prototype.md`](../../docs/user_stories/US025_virtualized_domain_layer_prototype.md).
Results go in [`FINDINGS.md`](FINDINGS.md), and the Virtual Graph setup in [`SETUP.md`](SETUP.md).

```
review chunks ── hybrid search ──> Chunk <-FROM_CHUNK- Defect -OBSERVED_IN-> Part:__Entity__ {part_id}
   (native Neo4j: text layer + embeddings, built by the existing pipeline)          │
══════════════════════════════ only part_id keys cross ═════════════════════════════│═══
   (virtual: nothing copied)                                                        v
CSV files ── DuckDB views ── Virtual Graph (Cypher)  /  Python (SQL)  /  Ontop (SPARQL)
                             (:Part)-[:SUPPLIED_BY {unit_cost}]->(:Supplier)
```

## Files

| File | What it does |
|---|---|
| `duckdb_domain.py` | One DuckDB **view** per CSV, plus the Python lookups (baseline hop 2, roll-up) |
| `build_duckdb.py` | Writes `furniture.duckdb` (views only) for Virtual Graph |
| `virtual_graph/` | `datasource.json`, `secret.json`, `schema.json`, read by Neo4j at boot |
| `docker-compose.yml`, `run_spike.sh`, `spike.cypher` | The Virtual Graph spike on Neo4j Enterprise |
| `prepare_state.py` | Copies only the approved entity/fact types and files from `state/current_state.json`, so all 10 reviews are pending |
| `load_native.py` | Builds the text side through `_build_unstructured` (both text indexes), then checks there are no domain nodes and no `CORRESPONDS_TO` |
| `stamp_keys.py` | Sets `part_id` on `Part:__Entity__`, resolved through DuckDB from the source document's product |
| `cq5.py` | CQ5: native hop 1, then hop 2 `--via virtual-graph` or `--via duckdb`, joined in Python, with timings |
| `cq5_composite.cypher`, `run_composite.sh` | The single-statement attempt over a composite database |
| `ontop/`, `run_ontop.sh` | Optional: the same views through Ontop, with the generated SQL |

## Environment

| Variable | Used by | Notes |
|---|---|---|
| `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` | `load_native`, `stamp_keys`, `cq5` | The **native** text graph. With the spike container: `bolt://localhost:7687`, `neo4j`, `us025password` |
| `NEO4J_DATABASE` | `run_composite.sh` | Native database name for the composite alias (default `neo4j`). The Python scripts use the server's default database, as the existing build does |
| `OPENAI_API_KEY` | `load_native`, `cq5` | GPT-4o extraction and `text-embedding-3-large` embeddings; hop 1 embeds the question with the same model |
| `VG_DATABASE` | `cq5 --via virtual-graph`, `run_composite.sh` | The virtual graph's database name; `run_spike.sh` lists the databases |
| `VG_URI`, `VG_USER`, `VG_PASSWORD` | `cq5 --via virtual-graph` | Default to the `NEO4J_*` values (same container) |
| `SPIKE_PASSWORD` | `run_spike.sh`, `run_composite.sh` | Neo4j password for the spike container (default `us025password`) |
| `FURNITURE_DATA_DIR`, `DUCKDB_JDBC_VERSION`, `NEO4J_IMAGE_TAG` | `run_spike.sh`, `run_ontop.sh` | Optional overrides |

Python extras: `pip install -r prototypes/us025_virtual_domain/requirements.txt` (DuckDB,
plus rdflib for one test).

## Run order (owner's machine; needs Docker, Python and an OpenAI key)

All commands run from the repo root.

```bash
# 1. Spike: Neo4j Enterprise + Virtual Graph over the DuckDB views. Note the VG database name.
prototypes/us025_virtual_domain/run_spike.sh
export NEO4J_URI=bolt://localhost:7687 NEO4J_USER=neo4j NEO4J_PASSWORD=us025password
export VG_DATABASE=<name printed by run_spike.sh>

# 2. Native text side, from an empty database
python -m prototypes.us025_virtual_domain.prepare_state
python -m prototypes.us025_virtual_domain.load_native

# 3. Keys
python -m prototypes.us025_virtual_domain.stamp_keys

# 4-5. CQ5, main path and baseline
python -m prototypes.us025_virtual_domain.cq5 --via virtual-graph
python -m prototypes.us025_virtual_domain.cq5 --via duckdb
prototypes/us025_virtual_domain/run_composite.sh

# 6. Optional: Ontop
prototypes/us025_virtual_domain/run_ontop.sh
```

The native graph can also live on another Neo4j (Desktop, Aura). Point `NEO4J_*` at it and
`VG_*` at the spike container. The composite attempt needs both on the spike container.

## Tests (no Neo4j needed)

```bash
pytest tests/unit/test_us025_virtual_domain.py
```

They cover the views (S-1085's suppliers and prices, a CSV edit visible without a rebuild),
the `schema.json` columns against the views, the state copy (all 10 reviews pending), key
resolution (Helsingborg Dresser + "drawer rails" → S-1085, ambiguous and unmatched cases),
the CQ5 join with stubbed hops, the DuckDB baseline, and the Ontop mapping + SPARQL
(materialized with rdflib as a stand-in for Ontop).
