// US025: CQ5 as ONE Cypher statement spanning the native graph and the virtual graph.
// This is an attempt, not the main path. Neo4j lists native + virtual federation in a
// single statement as roadmap, so an error here is an expected, recordable result.
//
// run_composite.sh first creates the composite database `us025` with two aliases:
//   us025.native -> the native text graph (NEO4J_DATABASE, default `neo4j`)
//   us025.domain -> the virtual graph (VG_DATABASE)
// then runs this file against `us025`.
CALL () {
  USE us025.native
  MATCH (d:Defect:__Entity__)-[:OBSERVED_IN|observed_in]->(part:Part:__Entity__)
  WHERE part.part_id IS NOT NULL AND toLower(part.name) CONTAINS 'drawer'
  RETURN collect(DISTINCT part.part_id) AS part_ids
}
CALL (part_ids) {
  USE us025.domain
  MATCH (p:Part)-[s:SUPPLIED_BY]->(sup:Supplier)
  WHERE p.part_id IN part_ids
  RETURN p.part_id AS part_id, sup.name AS supplier, s.unit_cost AS unit_cost
}
RETURN part_id, supplier, unit_cost
ORDER BY part_id, supplier;
