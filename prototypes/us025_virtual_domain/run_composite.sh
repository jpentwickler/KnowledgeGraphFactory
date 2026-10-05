#!/usr/bin/env bash
# US025: attempt CQ5 as a single statement over a composite database.
# Needs the spike container (run_spike.sh) with the native text graph built and
# keys stamped. Prints the result or the error; record either in FINDINGS.md.
#
# Usage: VG_DATABASE=<virtual graph db> prototypes/us025_virtual_domain/run_composite.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${VG_DATABASE:?Set VG_DATABASE to the virtual graph database name (run_spike.sh lists it)}"
NATIVE_DATABASE="${NEO4J_DATABASE:-neo4j}"
CS=(docker exec -i us025-neo4j cypher-shell -u neo4j -p "${SPIKE_PASSWORD:-us025password}")

echo "== Composite database us025: native=$NATIVE_DATABASE, domain=$VG_DATABASE"
"${CS[@]}" -d system <<CYPHER
CREATE COMPOSITE DATABASE us025 IF NOT EXISTS WAIT;
CREATE ALIAS us025.native IF NOT EXISTS FOR DATABASE \`$NATIVE_DATABASE\`;
CREATE ALIAS us025.domain IF NOT EXISTS FOR DATABASE \`$VG_DATABASE\`;
CYPHER

echo "== cq5_composite.cypher"
if "${CS[@]}" -d us025 < "$HERE/cq5_composite.cypher"; then
  echo "== Composite query ran. Record the rows above in FINDINGS.md."
else
  echo "== Composite query failed. Record the error above in FINDINGS.md."
fi
