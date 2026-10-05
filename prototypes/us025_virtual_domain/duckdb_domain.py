"""DuckDB views over the furniture CSVs: the virtual domain layer (US025).

Every domain table is a **view** over its CSV file. Nothing is imported, so each
query re-reads the file and an edited CSV is visible on the next query.

The same views back all three access paths in this prototype:
- Neo4j Virtual Graph reads them through the DuckDB JDBC driver (``furniture.duckdb``)
- the Python baseline queries them directly (``suppliers_for_parts``, ``parts_per_supplier``)
- Ontop maps them to RDF (optional comparison)
"""

from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "examples" / "furniture_supply_chain" / "data"
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "furniture.duckdb"

# One view per CSV. Columns are read as VARCHAR and cast explicitly, so the
# types do not depend on DuckDB's auto-detection (it reads "$47.14" as text
# and "yes"/"no" as BOOLEAN, which Virtual Graph may not map).
_VIEWS = {
    "products": """
        SELECT product_id,
               product_name,
               CAST(replace(price, '$', '') AS DOUBLE) AS price,
               description
        FROM read_csv('{dir}/products.csv', header = true, all_varchar = true)
    """,
    "assemblies": """
        SELECT assembly_id,
               assembly_name,
               CAST(quantity AS INTEGER) AS quantity,
               product_id
        FROM read_csv('{dir}/assemblies.csv', header = true, all_varchar = true)
    """,
    "parts": """
        SELECT part_id,
               part_name,
               CAST(quantity AS INTEGER) AS quantity,
               assembly_id
        FROM read_csv('{dir}/parts.csv', header = true, all_varchar = true)
    """,
    "suppliers": """
        SELECT supplier_id,
               name,
               specialty,
               city,
               country,
               website,
               contact_email
        FROM read_csv('{dir}/suppliers.csv', header = true, all_varchar = true)
    """,
    "part_supplier_mapping": """
        SELECT part_id,
               part_name,
               supplier_id,
               supplier_name,
               CAST(lead_time_days AS INTEGER) AS lead_time_days,
               CAST(replace(unit_cost, '$', '') AS DOUBLE) AS unit_cost,
               CAST(minimum_order_quantity AS INTEGER) AS minimum_order_quantity,
               preferred_supplier
        FROM read_csv('{dir}/part_supplier_mapping.csv', header = true, all_varchar = true)
    """,
}

VIEW_NAMES = tuple(_VIEWS)


def create_views(con: duckdb.DuckDBPyConnection, data_dir: Path | str = DEFAULT_DATA_DIR) -> None:
    """Create (or replace) one view per furniture CSV on ``con``.

    The CSV paths are stored as absolute paths inside the view definitions, so a
    database file built here only works where the CSVs sit at the same path.
    ``run_spike.sh`` mounts them at that path inside the Neo4j container.
    """
    data_dir = Path(data_dir).resolve()
    for name, select in _VIEWS.items():
        con.execute(f"CREATE OR REPLACE VIEW {name} AS {select.format(dir=data_dir.as_posix())}")


def connect(
    data_dir: Path | str = DEFAULT_DATA_DIR,
    db_path: Path | str | None = None,
) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection with the domain views in place.

    With ``db_path=None`` the views live in an in-memory database, which is all
    the Python baseline and the key stamping need.
    """
    con = duckdb.connect(str(db_path) if db_path else ":memory:")
    create_views(con, data_dir)
    return con


def suppliers_for_parts(con: duckdb.DuckDBPyConnection, part_ids: list[str]) -> list[dict]:
    """Supplier rows for the given part keys, read live from the CSV."""
    if not part_ids:
        return []
    rows = con.execute(
        """
        SELECT m.part_id, m.part_name, m.supplier_id, s.name AS supplier_name,
               m.unit_cost, m.lead_time_days, m.preferred_supplier
        FROM part_supplier_mapping m
        JOIN suppliers s USING (supplier_id)
        WHERE m.part_id IN (SELECT unnest(?))
        ORDER BY m.part_id, s.name
        """,
        [list(part_ids)],
    )
    columns = [d[0] for d in rows.description]
    return [dict(zip(columns, r)) for r in rows.fetchall()]


def parts_per_supplier(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Roll-up: how many distinct parts each supplier provides."""
    rows = con.execute(
        """
        SELECT s.supplier_id, s.name AS supplier_name, count(DISTINCT m.part_id) AS parts
        FROM suppliers s
        JOIN part_supplier_mapping m USING (supplier_id)
        GROUP BY s.supplier_id, s.name
        ORDER BY parts DESC, s.name
        """
    )
    columns = [d[0] for d in rows.description]
    return [dict(zip(columns, r)) for r in rows.fetchall()]
