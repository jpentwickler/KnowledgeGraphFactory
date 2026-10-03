"""CQ5 traceability across the native/virtual boundary (US025).

    customer complaint
      -> hybrid search over review chunks         (native Neo4j)
      -> chunk <-FROM_CHUNK- Defect -OBSERVED_IN-> Part:__Entity__ {part_id}
      == boundary: only part_id keys cross ==
      -> Part -SUPPLIED_BY-> Supplier             (virtual: Virtual Graph or DuckDB)

Hop 1 is one Cypher query on the native database. Hop 2 is a second query on the
virtual side, so the two are joined here, in app code. A single statement that
spans both is attempted separately (``cq5_composite.cypher``), because Neo4j does
not support native + virtual federation in one statement yet.

Usage (from the repo root):
    python -m prototypes.us025_virtual_domain.cq5 --via virtual-graph
    python -m prototypes.us025_virtual_domain.cq5 --via duckdb
    python -m prototypes.us025_virtual_domain.cq5 --via duckdb --question "..." --json

Native side: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD (+ NEO4J_DATABASE, optional),
OPENAI_API_KEY (the query is embedded with text-embedding-3-large, as at build time).
Virtual Graph: VG_URI, VG_USER, VG_PASSWORD (default to the NEO4J_* values) and
VG_DATABASE (the virtual graph's database name, from run_spike.sh).
"""

import argparse
import json
import os
import sys
import time
from typing import Callable

DEFAULT_QUESTION = "customer complaint about defective drawer rails"

# Runs once per hybrid-search hit; `node` is the chunk, `score` its rank score.
# Strict path: a defect extracted from this chunk, observed in a stamped part.
# Loose path: any stamped part extracted from this chunk. The loose keys are used
# only when the strict path finds none, and the result says which one was used.
HOP1_RETRIEVAL_QUERY = """
OPTIONAL MATCH (defect:Defect:__Entity__)-[:FROM_CHUNK]->(node)
OPTIONAL MATCH (defect)-[:OBSERVED_IN|observed_in]->(dpart:Part:__Entity__)
WHERE dpart.part_id IS NOT NULL
WITH node, score,
     collect(DISTINCT CASE WHEN dpart IS NOT NULL
                           THEN {defect: defect.name, part: dpart.name, part_id: dpart.part_id} END) AS strict
OPTIONAL MATCH (cpart:Part:__Entity__)-[:FROM_CHUNK]->(node)
WHERE cpart.part_id IS NOT NULL
RETURN node.text AS chunk, score, strict,
       collect(DISTINCT {part: cpart.name, part_id: cpart.part_id}) AS loose
"""

VG_SUPPLIERS = """
MATCH (p:Part {part_id: $part_id})-[s:SUPPLIED_BY]->(sup:Supplier)
RETURN p.part_id AS part_id, p.name AS part_name, sup.supplier_id AS supplier_id,
       sup.name AS supplier_name, s.unit_cost AS unit_cost,
       s.lead_time_days AS lead_time_days, s.preferred_supplier AS preferred_supplier
"""

VG_PARTS_PER_SUPPLIER = """
MATCH (p:Part)-[:SUPPLIED_BY]->(s:Supplier)
RETURN s.supplier_id AS supplier_id, s.name AS supplier_name, count(DISTINCT p) AS parts
ORDER BY parts DESC, supplier_name
"""


# ---------------------------------------------------------------------------
# Join logic (pure; unit-tested with stubbed hops)
# ---------------------------------------------------------------------------


def keys_from_hop1(hits: list[dict]) -> dict:
    """Collect part keys from hop-1 hits: strict path first, loose only as fallback."""
    strict = [s for h in hits for s in h.get("strict", []) if s and s.get("part_id")]
    loose = [l for h in hits for l in h.get("loose", []) if l and l.get("part_id")]
    chosen, path = (strict, "strict") if strict else (loose, "loose")
    return {
        "path": path if chosen else "none",
        "part_ids": sorted({c["part_id"] for c in chosen}),
        "evidence": chosen,
    }


def join_cq5(hits: list[dict], fetch_suppliers: Callable[[list[str]], list[dict]]) -> dict:
    """Hop 1 hits + a hop-2 fetcher -> the CQ5 answer, with per-hop timing."""
    keys = keys_from_hop1(hits)
    started = time.perf_counter()
    suppliers = fetch_suppliers(keys["part_ids"]) if keys["part_ids"] else []
    return {
        "chunks": [{"score": h.get("score"), "text": (h.get("chunk") or "")[:160]} for h in hits],
        "key_path": keys["path"],
        "part_ids": keys["part_ids"],
        "evidence": keys["evidence"],
        "suppliers": suppliers,
        "hop2_seconds": round(time.perf_counter() - started, 3),
    }


# ---------------------------------------------------------------------------
# Hop 1: native Neo4j
# ---------------------------------------------------------------------------


def hop1(driver, question: str, top_k: int = 5, database: str | None = None) -> list[dict]:
    """Hybrid search over review chunks, then chunk -> defect -> stamped part."""
    from neo4j_graphrag.embeddings import OpenAIEmbeddings
    from neo4j_graphrag.retrievers import HybridCypherRetriever

    from tools.query_tools import _escape_lucene

    retriever = HybridCypherRetriever(
        driver=driver,
        vector_index_name="chunk-embeddings",
        fulltext_index_name="chunk-fulltext",
        retrieval_query=HOP1_RETRIEVAL_QUERY,
        embedder=OpenAIEmbeddings(model="text-embedding-3-large"),
        neo4j_database=database,
    )
    # get_search_results keeps the raw records (search() would format them to text)
    result = retriever.get_search_results(query_text=_escape_lucene(question), top_k=top_k)
    return [dict(r) for r in result.records]


# ---------------------------------------------------------------------------
# Hop 2 backends
# ---------------------------------------------------------------------------


def virtual_graph_backend():
    """Hop 2 against Neo4j Virtual Graph. Returns (fetch_suppliers, rollup, close)."""
    from utils import get_neo4j_driver

    database = os.environ.get("VG_DATABASE")
    if not database:
        raise SystemExit("Set VG_DATABASE to the virtual graph's database name (run_spike.sh lists it).")
    driver = get_neo4j_driver(
        uri=os.environ.get("VG_URI", os.environ.get("NEO4J_URI")),
        user=os.environ.get("VG_USER", os.environ.get("NEO4J_USER")),
        password=os.environ.get("VG_PASSWORD", os.environ.get("NEO4J_PASSWORD")),
    )

    def fetch(part_ids: list[str]) -> list[dict]:
        # One equality lookup per key: the same shape as the spike query, and
        # the simplest pattern for Virtual Graph to push down to SQL.
        rows = []
        with driver.session(database=database) as session:
            for part_id in part_ids:
                rows += [dict(r) for r in session.run(VG_SUPPLIERS, part_id=part_id)]
        return sorted(rows, key=lambda r: (r["part_id"], r["supplier_name"]))

    def rollup() -> list[dict]:
        with driver.session(database=database) as session:
            return [dict(r) for r in session.run(VG_PARTS_PER_SUPPLIER)]

    return fetch, rollup, driver.close


def duckdb_backend():
    """Hop 2 straight from Python to the DuckDB views (the zero-copy baseline)."""
    from prototypes.us025_virtual_domain import duckdb_domain

    con = duckdb_domain.connect()
    return (
        lambda part_ids: duckdb_domain.suppliers_for_parts(con, part_ids),
        lambda: duckdb_domain.parts_per_supplier(con),
        con.close,
    )


BACKENDS = {"virtual-graph": virtual_graph_backend, "duckdb": duckdb_backend}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def run(via: str, question: str, top_k: int) -> dict:
    from utils import get_neo4j_driver

    fetch, rollup, close = BACKENDS[via]()
    native = get_neo4j_driver()
    try:
        started = time.perf_counter()
        hits = hop1(native, question, top_k, database=os.environ.get("NEO4J_DATABASE"))
        hop1_seconds = round(time.perf_counter() - started, 3)

        answer = join_cq5(hits, fetch)

        started = time.perf_counter()
        roll = rollup()
        rollup_seconds = round(time.perf_counter() - started, 3)
    finally:
        native.close()
        close()
    return {"via": via, "question": question, "hop1_seconds": hop1_seconds, **answer,
            "parts_per_supplier": roll, "rollup_seconds": rollup_seconds}


def print_report(result: dict) -> None:
    print(f"CQ5 via {result['via']}: {result['question']!r}")
    print(f"\nHop 1 (native, {result['hop1_seconds']}s): {len(result['chunks'])} chunks, "
          f"keys via {result['key_path']} path: {result['part_ids'] or 'none'}")
    for e in result["evidence"]:
        print(f"  {e.get('defect', '(part in chunk)')} -> {e['part']} [{e['part_id']}]")
    print(f"\nHop 2 ({result['via']}, {result['hop2_seconds']}s):")
    for s in result["suppliers"]:
        print(f"  {s['part_id']} {s['part_name']}: {s['supplier_name']} "
              f"${s['unit_cost']:.2f}, {s['lead_time_days']} days")
    if not result["suppliers"]:
        print("  no supplier rows")
    print(f"\nParts per supplier ({result['rollup_seconds']}s), top 5:")
    for r in result["parts_per_supplier"][:5]:
        print(f"  {r['supplier_name']}: {r['parts']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--via", choices=sorted(BACKENDS), default="virtual-graph")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="print the raw result as JSON")
    args = parser.parse_args()

    result = run(args.via, args.question, args.top_k)
    if args.json:
        json.dump(result, sys.stdout, indent=2, default=str)
        print()
    else:
        print_report(result)
    sys.exit(0 if result["suppliers"] else 1)


if __name__ == "__main__":
    main()
