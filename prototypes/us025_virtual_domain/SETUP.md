# US025 Virtual Graph spike: setup record

Fill this in after running `./run_spike.sh` on the owner's machine. The cloud worker
that built the kit had no Docker daemon and could not reach neo4j.com, so nothing below has
been run yet.

## What the kit does

1. `build_duckdb.py` writes `furniture.duckdb`, which holds **views only**, one per CSV in
   `examples/furniture_supply_chain/data/`. The view definitions contain absolute CSV paths.
2. Downloads the DuckDB JDBC driver from Maven Central into `jdbc/`.
3. `docker compose up` starts Neo4j Enterprise (`docker-compose.yml`) with:
   - `NEO4J_internal_virtual__graph_enabled=true`
   - `NEO4J_internal_virtual__graph_home=/nvg_home`, mounted from `virtual_graph/`
     (`secret.json`, `datasource.json`, `schema.json`, all read at boot)
   - the JDBC jar in `/var/lib/neo4j/lib/`
   - `furniture.duckdb` at `/duckdb-data/furniture.duckdb` (matches `datasource.json`)
   - the CSV directory at **the same absolute path** as on the host, so the views resolve
   - APOC, for the native text build in step 2 (this instance also hosts the native graph)
4. Prints the version, edition and databases, then runs `spike.cypher` on every user database.

The setup follows the DuckDB ("lakegraph") configuration in
[ikwattro/neo4j-virtual-graph-playground](https://github.com/ikwattro/neo4j-virtual-graph-playground)
and Neo4j's self-managed docs:
[enabling Virtual Graph](https://neo4j.com/docs/virtual-graph/self-managed/enabling-virtual-graph/),
[DuckDB driver](https://neo4j.com/docs/virtual-graph/self-managed/jdbc-drivers/duckdb/).

## Expected result

```
part_id  | part         | supplier            | unit_cost | lead_time_days
"S-1085" | "Drawer Rails" | "Korean Metal Works"  | 47.14 | 17
"S-1085" | "Drawer Rails" | "Shanghai Metal Corp" | 40.82 | 26
```

## Record

| Item | Value |
|---|---|
| Date run | |
| Neo4j image tag | `2026.09.0-enterprise` (default) |
| `dbms.components()` version / edition | |
| DuckDB JDBC driver | `1.5.3.0` (default) |
| Python `duckdb` that wrote `furniture.duckdb` | |
| Virtual graph database name (from `SHOW DATABASES`) | |
| Settings that differed from the kit | |
| Spike query result | |
| Did it boot first time? If not, the error | |

## Known risks to check first if it fails

- **Views vs tables.** The playground materializes DuckDB **tables** "so JDBC reads need no
  httpfs". This kit uses **views** over local CSVs, which need no extension, but Virtual Graph
  may not introspect views. If boot fails on schema validation, that is the first suspect.
  Materializing tables in DuckDB would still keep Neo4j zero-copy, but the data would no
  longer be live from the CSV. Record it as a finding rather than switching silently.
- **Column-name case.** `schema.json` uses upper-case column names, as the playground does
  against DuckDB, while the views' columns are lower-case.
- **DuckDB file version.** The JDBC driver must read the file the Python `duckdb` wrote. Keep
  both on the same minor version (1.5.x), or set `DUCKDB_JDBC_VERSION` to match.
- **Invalid config fails the boot.** `docker logs us025-neo4j` shows why.
- **Licence.** Enterprise with `NEO4J_ACCEPT_LICENSE_AGREEMENT=yes` is an evaluation licence.
  Check that it is acceptable for this use.
