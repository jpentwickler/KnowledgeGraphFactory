// US025 spike: one part, its suppliers and prices, read through Virtual Graph from the CSV.
// Expected: Korean Metal Works 47.14, Shanghai Metal Corp 40.82.
MATCH (p:Part {part_id: 'S-1085'})-[s:SUPPLIED_BY]->(sup:Supplier)
RETURN p.part_id AS part_id, p.name AS part, sup.name AS supplier,
       s.unit_cost AS unit_cost, s.lead_time_days AS lead_time_days;
