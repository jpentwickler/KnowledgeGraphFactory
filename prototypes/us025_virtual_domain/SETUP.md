# US025 Virtual Graph spike: setup record

Run on the owner's Mac on 2026-10-04 (OrbStack 2.2.3, Docker 29.4.0). The kit was built by a
cloud worker without Docker; the record below is from the first real run.

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
| Date run | 2026-10-04 |
| Neo4j image tag | `2026.09.0-enterprise` (default) |
| `dbms.components()` version / edition | Neo4j Kernel `2026.09.0` enterprise · Cypher `5`, `25` · **Virtual Graph `1.0-alpha-01`** |
| DuckDB JDBC driver | `1.5.3.0` (default) |
| Python `duckdb` that wrote `furniture.duckdb` | `1.5.6` (reads fine with JDBC 1.5.3.0) |
| Virtual graph database name (from `SHOW DATABASES`) | **`neo4j`**: the virtual graph takes over the default database (`type: "virtual graph"`) |
| Settings that differed from the kit | The JDBC jar mount must be writable: the image's entrypoint `chown`s `/var/lib/neo4j/lib` (fixed in `docker-compose.yml`). Native text graph in its own database, see below |
| Spike query result | As expected: S-1085 Drawer Rails → Shanghai Metal Corp 40.82 (26 days), Korean Metal Works 47.14 (17 days) |
| Did it boot first time? If not, the error | No. `chown: changing ownership of '/var/lib/neo4j/lib/duckdb_jdbc-1.5.3.0.jar': Read-only file system`. Booted after dropping `:ro` on the jar mount. Views (not tables), upper-case column names and the `:ro` mount of `furniture.duckdb` all worked as written |

### Native and virtual on one instance

Virtual Graph occupies the default database `neo4j`, but the instance still hosts ordinary
databases. `run_spike.sh` now creates a standard database `native` for the text graph and makes
it the default, so the Python scripts (which use the server's default database) write there:

```cypher
// on system
CREATE DATABASE native IF NOT EXISTS WAIT;
STOP DATABASE neo4j WAIT;                 // the old default must be stopped to change it
CALL dbms.setDefaultDatabase('native');
START DATABASE neo4j WAIT;
```

Result: `native` standard, default · `neo4j` virtual graph · the spike query still answers on
`neo4j`. So `VG_DATABASE=neo4j`, and `NEO4J_DATABASE=native` for `run_composite.sh`. These
databases live in the container: `docker compose down` deletes them.

**Caveat found after the run (2026-10-05):** with Virtual Graph enabled, the schema procedures
answer for the virtual graph on **every** database of the instance. On `native`, `db.labels()`,
`db.relationshipTypes()` and `db.schema.*` return `Product, Assembly, Part, Supplier` /
`HAS_ASSEMBLY, HAS_PART, SUPPLIED_BY` instead of the text graph's labels. Queries return the right
data, and the project's own schema introspection (`MATCH`-based) recorded the right text schema,
but Neo4j Browser's sidebar and Explore show the wrong schema on `native`. Not documented by Neo4j;
probably a preview bug. Workaround: a separate plain Neo4j instance for the text graph (`cq5.py`
already takes `VG_URI`). The virtual graph also rejects variable-length patterns (`[*1..3]`).

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
- **Read-only mounts.** `furniture.duckdb` mounted `:ro` works (Neo4j opens read connections
  only). The JDBC jar must **not** be `:ro`: the entrypoint `chown`s `/var/lib/neo4j/lib`.
- **Invalid config fails the boot.** `docker logs us025-neo4j` shows why.
- **Licence.** Enterprise with `NEO4J_ACCEPT_LICENSE_AGREEMENT=yes` is an evaluation licence.
  Check that it is acceptable for this use.
