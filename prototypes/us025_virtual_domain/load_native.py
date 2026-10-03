"""Build the native text side for US025 through the existing build path.

Calls ``_build_unstructured`` from ``mcp_server/server.py`` (the
``kg_build_graph(scope="unstructured")`` route), which runs the text builder and
creates the ``chunk-embeddings`` and ``chunk-fulltext`` indexes that hop 1's
hybrid search needs. ``scope="structured"`` and ``scope="resolve"`` are never run:
no domain node and no ``CORRESPONDS_TO`` may exist in Neo4j.

Needs NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD and OPENAI_API_KEY.

Usage (from the repo root):
    prototypes/us025_virtual_domain/py.sh -m prototypes.us025_virtual_domain.load_native
    prototypes/us025_virtual_domain/py.sh -m prototypes.us025_virtual_domain.load_native --allow-nonempty
"""

import argparse
import asyncio
import os
import sys

from prototypes.us025_virtual_domain.duckdb_domain import DEFAULT_DATA_DIR
from prototypes.us025_virtual_domain.prepare_state import PROTOTYPE_STATE_DIR, prepare

TEXT_INDEXES = ("chunk-embeddings", "chunk-fulltext")

# Anything that is not text-side infrastructure or an extracted entity is domain
# data, which this story forbids in Neo4j.
NON_TEXT_NODES = """
MATCH (n) WHERE NOT n:__Entity__ AND NOT n:Chunk AND NOT n:Document
RETURN labels(n) AS labels, count(*) AS count
"""


def check_native_graph(driver) -> dict:
    """Post-build checks: indexes online, no domain nodes, no CORRESPONDS_TO."""
    with driver.session() as session:
        indexes = {
            r["name"]: r["state"]
            for r in session.run("SHOW INDEXES YIELD name, state WHERE name IN $names RETURN name, state",
                                 names=list(TEXT_INDEXES))
        }
        non_text = [dict(r) for r in session.run(NON_TEXT_NODES)]
        corresponds_to = session.run("MATCH ()-[r:CORRESPONDS_TO]->() RETURN count(r) AS c").single()["c"]
        counts = {
            r["label"]: r["count"]
            for r in session.run("MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS count")
        }
    ok = (
        all(indexes.get(name) == "ONLINE" for name in TEXT_INDEXES)
        and not non_text
        and corresponds_to == 0
    )
    return {
        "ok": ok,
        "indexes": indexes,
        "non_text_nodes": non_text,
        "corresponds_to": corresponds_to,
        "label_counts": counts,
    }


async def run(allow_nonempty: bool) -> int:
    # Import first: the server loads .env on import, which must not override
    # the prototype's state and data directories set below.
    from core import load_state
    from mcp_server import server
    from utils import get_neo4j_driver

    os.environ.pop("KG_BASE_DIR", None)  # use KG_STATE_DIR, not a managed project
    os.environ["KG_STATE_DIR"] = str(PROTOTYPE_STATE_DIR)
    os.environ["KG_DATA_DIR"] = str(DEFAULT_DATA_DIR)

    state_file = PROTOTYPE_STATE_DIR / "current_state.json"
    if not state_file.exists():
        print(f"No prototype state yet; writing {prepare()}")
    if server._get_state_file() != str(state_file):
        print(f"State would be written to {server._get_state_file()}, expected {state_file}")
        return 2

    driver = get_neo4j_driver()
    try:
        with driver.session() as session:
            existing = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        if existing and not allow_nonempty:
            print(f"The native database is not empty ({existing} nodes). US025 builds from an empty "
                  "database; clear it or pass --allow-nonempty to continue a partial build.")
            return 2

        result = await server._build_unstructured(load_state(str(state_file)), driver, "all")
        print(result["agent_response"])
        if not result["status"].get("success"):
            return 1

        checks = check_native_graph(driver)
        print("\nPost-build checks")
        print(f"  indexes: {checks['indexes']}")
        print(f"  non-text nodes: {checks['non_text_nodes'] or 'none'}")
        print(f"  CORRESPONDS_TO: {checks['corresponds_to']}")
        print(f"  label counts: {checks['label_counts']}")
        print("  OK" if checks["ok"] else "  FAILED")
        return 0 if checks["ok"] else 1
    finally:
        driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--allow-nonempty", action="store_true",
                        help="continue on a database that already has nodes (e.g. a partial build)")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.allow_nonempty)))


if __name__ == "__main__":
    main()
