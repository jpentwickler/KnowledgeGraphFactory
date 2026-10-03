"""Write furniture.duckdb: the DuckDB file Neo4j Virtual Graph reads (US025).

The file holds view definitions only. Every query through it re-reads the CSVs,
so nothing from the domain layer is copied anywhere.

Usage (from the repo root):
    python -m prototypes.us025_virtual_domain.build_duckdb
    python -m prototypes.us025_virtual_domain.build_duckdb --data-dir /abs/path/to/data
"""

import argparse
from pathlib import Path

import duckdb

from prototypes.us025_virtual_domain.duckdb_domain import (
    DEFAULT_DATA_DIR,
    DEFAULT_DB_PATH,
    VIEW_NAMES,
    create_views,
)


def build(data_dir: Path | str = DEFAULT_DATA_DIR, db_path: Path | str = DEFAULT_DB_PATH) -> dict:
    """Create or refresh the view definitions in ``db_path``. Returns row counts per view."""
    with duckdb.connect(str(db_path)) as con:
        create_views(con, data_dir)
        return {name: con.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in VIEW_NAMES}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()

    counts = build(args.data_dir, args.db_path)
    print(f"Wrote {args.db_path} (views over {Path(args.data_dir).resolve()})")
    for name, n in counts.items():
        print(f"  {name}: {n} rows")


if __name__ == "__main__":
    main()
