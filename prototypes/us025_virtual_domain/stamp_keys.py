"""Stamp domain keys on text part entities by querying the virtual side (US025).

This replaces ``CORRESPONDS_TO`` for the prototype. There are no domain nodes in
Neo4j to fuzzy-match against, so each ``Part:__Entity__`` gets a ``part_id``
property resolved through the DuckDB views:

    part entity -[:FROM_CHUNK]-> chunk -[:FROM_DOCUMENT]- document
    document title "Helsingborg Dresser Reviews"  -> product "Helsingborg Dresser"
    (product name, part name) -> products -> assemblies -> parts -> part_id

It still matches on the part *name*. What narrows "drawer rails" to S-1085 rather
than S-1078 is the product, looked up in the source at build time. A part whose
chunks come from more than one product's reviews, or whose name matches more than
one part of that product, is reported as ambiguous and gets no key.

Usage (from the repo root):
    python -m prototypes.us025_virtual_domain.stamp_keys
"""

import re
from pathlib import Path

import duckdb

from prototypes.us025_virtual_domain import duckdb_domain

TITLE_SUFFIX = " Reviews"

PARTS_WITH_DOCUMENTS = """
MATCH (p:Part:__Entity__)-[:FROM_CHUNK]->(:Chunk)-[:FROM_DOCUMENT]-(d:Document)
RETURN elementId(p) AS id, p.name AS name,
       collect(DISTINCT {title: d.title, path: d.path}) AS documents
"""

STAMP = """
UNWIND $rows AS row
MATCH (p) WHERE elementId(p) = row.id
SET p.part_id = row.part_id
"""

UNSTAMP = """
UNWIND $ids AS id
MATCH (p) WHERE elementId(p) = id
REMOVE p.part_id
"""


def product_for_document(document: dict) -> str | None:
    """The product a review document is about: its title minus " Reviews".

    Falls back to the file's first H1 when the Document node has no title.
    """
    title = document.get("title")
    if not title and document.get("path") and Path(document["path"]).exists():
        match = re.search(r"^# (.+)$", Path(document["path"]).read_text(encoding="utf-8"), re.MULTILINE)
        title = match.group(1) if match else None
    if not title:
        return None
    title = title.strip()
    return title[: -len(TITLE_SUFFIX)] if title.endswith(TITLE_SUFFIX) else title


def part_ids_for(con: duckdb.DuckDBPyConnection, product_name: str, part_name: str) -> list[str]:
    """Part keys named ``part_name`` in ``product_name``'s assemblies (case-insensitive)."""
    rows = con.execute(
        """
        SELECT DISTINCT pt.part_id
        FROM products pr
        JOIN assemblies a USING (product_id)
        JOIN parts pt USING (assembly_id)
        WHERE lower(trim(pr.product_name)) = lower(trim(?))
          AND lower(trim(pt.part_name)) = lower(trim(?))
        ORDER BY pt.part_id
        """,
        [product_name, part_name],
    )
    return [r[0] for r in rows.fetchall()]


def resolve(con: duckdb.DuckDBPyConnection, parts: list[dict]) -> list[dict]:
    """Resolve each ``{"id", "name", "documents"}`` to a key, or say why not.

    Returns one dict per part with ``status`` in {"stamped", "ambiguous",
    "unmatched"}; ``part_id`` is set only when stamped.
    """
    results = []
    for part in parts:
        products = sorted({p for d in part["documents"] if (p := product_for_document(d))})
        result = {"id": part["id"], "name": part["name"], "products": products, "part_id": None}

        if not products:
            result.update(status="unmatched", reason="no source document with a product title")
        elif len(products) > 1:
            result.update(status="ambiguous", reason=f"mentioned in reviews of {len(products)} products")
        else:
            keys = part_ids_for(con, products[0], part["name"])
            if not keys:
                result.update(status="unmatched", reason=f"no part named {part['name']!r} in {products[0]}")
            elif len(keys) > 1:
                result.update(status="ambiguous", reason=f"{products[0]} has {len(keys)} such parts: {keys}")
            else:
                result.update(status="stamped", part_id=keys[0], reason=f"{products[0]} -> {keys[0]}")
        results.append(result)
    return results


def stamp(driver, con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Read part entities from Neo4j, resolve them via DuckDB, write ``part_id``."""
    with driver.session() as session:
        parts = [dict(r) for r in session.run(PARTS_WITH_DOCUMENTS)]
        results = resolve(con, parts)
        stamped = [{"id": r["id"], "part_id": r["part_id"]} for r in results if r["status"] == "stamped"]
        others = [r["id"] for r in results if r["status"] != "stamped"]
        session.run(STAMP, rows=stamped)
        session.run(UNSTAMP, ids=others)  # a re-run must not leave stale keys
    return results


def main() -> None:
    from utils import get_neo4j_driver

    driver = get_neo4j_driver()
    con = duckdb_domain.connect()
    try:
        results = stamp(driver, con)
    finally:
        driver.close()
        con.close()

    for status in ("stamped", "ambiguous", "unmatched"):
        group = [r for r in results if r["status"] == status]
        print(f"{status}: {len(group)}")
        for r in group:
            print(f"  {r['name']!r}: {r['reason']}")


if __name__ == "__main__":
    main()
