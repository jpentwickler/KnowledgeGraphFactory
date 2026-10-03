#!/usr/bin/env bash
# US025 Virtual Graph spike: start Neo4j Enterprise with Virtual Graph over the
# furniture DuckDB views, then run spike.cypher against every user database.
#
# Usage (from anywhere):  prototypes/us025_virtual_domain/run_spike.sh
# Stop:                   docker compose -f prototypes/us025_virtual_domain/docker-compose.yml down
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
cd "$HERE"

export FURNITURE_DATA_DIR="${FURNITURE_DATA_DIR:-$REPO/examples/furniture_supply_chain/data}"
export DUCKDB_JDBC_VERSION="${DUCKDB_JDBC_VERSION:-1.5.3.0}"
export SPIKE_PASSWORD="${SPIKE_PASSWORD:-us025password}"

echo "== 1/4 Build furniture.duckdb (views over $FURNITURE_DATA_DIR)"
(cd "$REPO" && python -m prototypes.us025_virtual_domain.build_duckdb --data-dir "$FURNITURE_DATA_DIR")

echo "== 2/4 DuckDB JDBC driver $DUCKDB_JDBC_VERSION"
mkdir -p jdbc
JAR="jdbc/duckdb_jdbc-$DUCKDB_JDBC_VERSION.jar"
if [ ! -f "$JAR" ]; then
  curl -fL -o "$JAR" \
    "https://repo1.maven.org/maven2/org/duckdb/duckdb_jdbc/$DUCKDB_JDBC_VERSION/duckdb_jdbc-$DUCKDB_JDBC_VERSION.jar"
fi

echo "== 3/4 Start Neo4j Enterprise with Virtual Graph"
docker compose up -d
for i in $(seq 1 60); do
  if docker exec us025-neo4j cypher-shell -u neo4j -p "$SPIKE_PASSWORD" "RETURN 1" >/dev/null 2>&1; then
    break
  fi
  if [ "$i" = 60 ]; then
    echo "Neo4j did not come up. Last log lines:"; docker logs --tail 60 us025-neo4j; exit 1
  fi
  sleep 3
done

CS=(docker exec -i us025-neo4j cypher-shell -u neo4j -p "$SPIKE_PASSWORD")

echo "== 4/4 Spike query"
echo "-- Neo4j version and edition"
"${CS[@]}" "CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition"
echo "-- Databases"
"${CS[@]}" "SHOW DATABASES YIELD name, type, currentStatus RETURN name, type, currentStatus"

# The virtual graph's database name is not documented for self-managed preview,
# so try the spike query against every user database and report where it answers.
for db in $("${CS[@]}" --format plain "SHOW DATABASES YIELD name WHERE name <> 'system' RETURN name" | tail -n +2 | tr -d '"'); do
  echo "-- spike.cypher on database '$db'"
  if "${CS[@]}" -d "$db" < spike.cypher; then :; else echo "   (failed on '$db')"; fi
done

echo
echo "Record the version, edition, settings and result in SETUP.md."
echo "Virtual Graph log lines:"; docker logs us025-neo4j 2>&1 | grep -i "virtual" | tail -20 || true
