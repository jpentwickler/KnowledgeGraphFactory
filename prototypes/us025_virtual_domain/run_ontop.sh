#!/usr/bin/env bash
# US025 optional comparison: the same DuckDB views through Ontop (SPARQL), with
# the SQL that Ontop generates for each query.
#
# Usage: prototypes/us025_virtual_domain/run_ontop.sh
# Stop:  docker rm -f us025-ontop
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
cd "$HERE"

FURNITURE_DATA_DIR="${FURNITURE_DATA_DIR:-$REPO/examples/furniture_supply_chain/data}"
DUCKDB_JDBC_VERSION="${DUCKDB_JDBC_VERSION:-1.5.3.0}"
ONTOP_IMAGE="${ONTOP_IMAGE:-ontop/ontop}"

echo "== Private views file for Ontop (avoids DuckDB's single-writer lock with Virtual Graph)"
("$HERE/py.sh" -m prototypes.us025_virtual_domain.build_duckdb \
   --data-dir "$FURNITURE_DATA_DIR" --db-path "$HERE/furniture_ontop.duckdb")

mkdir -p jdbc
JAR="jdbc/duckdb_jdbc-$DUCKDB_JDBC_VERSION.jar"
[ -f "$JAR" ] || curl -fL -o "$JAR" \
  "https://repo1.maven.org/maven2/org/duckdb/duckdb_jdbc/$DUCKDB_JDBC_VERSION/duckdb_jdbc-$DUCKDB_JDBC_VERSION.jar"

echo "== Start Ontop endpoint ($ONTOP_IMAGE) in dev mode"
docker rm -f us025-ontop >/dev/null 2>&1 || true
docker run -d --name us025-ontop -p 8080:8080 \
  -v "$HERE/ontop:/opt/ontop/input:ro" \
  -v "$HERE/jdbc:/opt/ontop/jdbc:ro" \
  -v "$HERE/furniture_ontop.duckdb:/duckdb-data/furniture_ontop.duckdb" \
  -v "$FURNITURE_DATA_DIR:$FURNITURE_DATA_DIR:ro" \
  -e ONTOP_MAPPING_FILE=/opt/ontop/input/furniture.obda \
  -e ONTOP_PROPERTIES_FILE=/opt/ontop/input/furniture.properties \
  -e ONTOP_DEV_MODE=true \
  "$ONTOP_IMAGE" >/dev/null

for i in $(seq 1 40); do
  curl -fs -o /dev/null "http://localhost:8080/" && break
  [ "$i" = 40 ] && { echo "Ontop did not come up:"; docker logs --tail 60 us025-ontop; exit 1; }
  sleep 3
done

for q in ontop/hop2_suppliers.rq ontop/parts_per_supplier.rq; do
  echo; echo "== $q: generated SQL (/ontop/reformulate)"
  curl -fsS --data-urlencode "query@$q" "http://localhost:8080/ontop/reformulate"; echo
  echo "== $q: results"
  curl -fsS -H "Accept: text/csv" --data-urlencode "query@$q" "http://localhost:8080/sparql"
done
echo; echo "Record the generated SQL and timings in FINDINGS.md."
