"""Unit tests for the US025 virtualized domain layer prototype.

Covers the parts that run without Neo4j: the DuckDB views, the Virtual Graph
schema mapping, the state copy, key resolution and the CQ5 join logic.
"""

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("duckdb", reason="US025 prototype needs prototypes/us025_virtual_domain/requirements.txt")

from prototypes.us025_virtual_domain import duckdb_domain
from prototypes.us025_virtual_domain.build_duckdb import build

PROTOTYPE_DIR = Path(duckdb_domain.__file__).parent


@pytest.fixture
def data_dir(tmp_path):
    """A private copy of the furniture CSVs that a test may edit."""
    target = tmp_path / "data"
    shutil.copytree(duckdb_domain.DEFAULT_DATA_DIR, target, ignore=shutil.ignore_patterns("reviews"))
    return target


@pytest.fixture
def con(data_dir):
    connection = duckdb_domain.connect(data_dir)
    yield connection
    connection.close()


# ---------------------------------------------------------------------------
# DuckDB views (step 1)
# ---------------------------------------------------------------------------


class TestDomainViews:
    def test_s1085_suppliers_and_prices(self, con):
        """The complaint's part returns its two suppliers with prices from the CSV."""
        rows = duckdb_domain.suppliers_for_parts(con, ["S-1085"])
        assert [(r["supplier_name"], r["unit_cost"]) for r in rows] == [
            ("Korean Metal Works", 47.14),
            ("Shanghai Metal Corp", 40.82),
        ]

    def test_unknown_and_empty_keys(self, con):
        assert duckdb_domain.suppliers_for_parts(con, []) == []
        assert duckdb_domain.suppliers_for_parts(con, ["S-0000"]) == []

    def test_csv_edit_visible_without_rebuild(self, con, data_dir):
        """Views re-read the file: an edited price shows up on the next query."""
        csv = data_dir / "part_supplier_mapping.csv"
        csv.write_text(csv.read_text().replace("S-1085,Drawer Rails,SUP-002,Shanghai Metal Corp,26,$40.82",
                                               "S-1085,Drawer Rails,SUP-002,Shanghai Metal Corp,26,$99.99"))
        prices = {r["supplier_name"]: r["unit_cost"] for r in duckdb_domain.suppliers_for_parts(con, ["S-1085"])}
        assert prices["Shanghai Metal Corp"] == 99.99

    def test_parts_per_supplier_rollup(self, con):
        rollup = duckdb_domain.parts_per_supplier(con)
        assert sum(r["parts"] for r in rollup) == 176  # one row per part-supplier pair
        assert {"supplier_id", "supplier_name", "parts"} == set(rollup[0])

    def test_build_writes_views_only(self, data_dir, tmp_path):
        """The DuckDB file holds view definitions, no tables."""
        db_path = tmp_path / "furniture.duckdb"
        counts = build(data_dir, db_path)
        assert counts == {
            "products": 10,
            "assemblies": 64,
            "parts": 88,
            "suppliers": 20,
            "part_supplier_mapping": 176,
        }
        import duckdb

        with duckdb.connect(str(db_path), read_only=True) as c:
            kinds = c.execute(
                "SELECT table_type, count(*) FROM information_schema.tables "
                "WHERE table_schema = 'main' GROUP BY table_type"
            ).fetchall()
        assert kinds == [("VIEW", 5)]


# ---------------------------------------------------------------------------
# Virtual Graph mapping (step 1)
# ---------------------------------------------------------------------------


class TestVirtualGraphSchema:
    @pytest.fixture
    def schema(self):
        return json.loads((PROTOTYPE_DIR / "virtual_graph" / "schema.json").read_text())

    def test_catalog_matches_duckdb_file(self, schema):
        datasource = json.loads((PROTOTYPE_DIR / "virtual_graph" / "datasource.json").read_text())
        assert datasource["type"] == "duckdb"
        assert Path(datasource["path"]).stem == schema["catalog"]

    def test_every_mapped_column_exists(self, schema, con):
        """Every table and column named in schema.json exists in the views (case-insensitive)."""
        columns = {}
        for view in duckdb_domain.VIEW_NAMES:
            columns[view] = {r[0].lower() for r in con.execute(f"DESCRIBE {view}").fetchall()}

        entities = schema["entities"]
        for entity in entities["nodes"] + entities["relationships"]:
            table = entity["table"]
            assert table in columns, table
            named = [p["column"] for p in entity["properties"]] + [k["column"] for k in entity["key"]]
            for end in ("start", "end"):
                if end in entity:
                    named += [k["relationshipColumn"] for k in entity[end]["keys"]]
            for column in named:
                assert column.lower() in columns[table], f"{table}.{column}"

    def test_spike_pattern_is_mapped(self, schema):
        """spike.cypher's (:Part {part_id})-[:SUPPLIED_BY]->(:Supplier) is in the mapping."""
        nodes = {n["label"]: n for n in schema["entities"]["nodes"]}
        assert "part_id" in {p["name"] for p in nodes["Part"]["properties"]}
        rel = next(r for r in schema["entities"]["relationships"] if r["label"] == "SUPPLIED_BY")
        assert (rel["start"]["targetEntity"], rel["end"]["targetEntity"]) == ("Part", "Supplier")
        assert {"unit_cost", "lead_time_days"} <= {p["name"] for p in rel["properties"]}


# ---------------------------------------------------------------------------
# State copy and native build (step 2)
# ---------------------------------------------------------------------------


class TestPrepareState:
    def test_copy_leaves_all_review_files_pending(self, tmp_path):
        """The tracked state has every file processed; the copy has all 10 pending."""
        from pipelines.text_builder import _resolve_files_to_process
        from prototypes.us025_virtual_domain.prepare_state import SOURCE_STATE, prepare

        source = json.loads(SOURCE_STATE.read_text())
        assert _resolve_files_to_process(source, "all") == []  # why the copy is needed

        copy = json.loads(prepare(SOURCE_STATE, tmp_path).read_text())
        pending = _resolve_files_to_process(copy, "all")
        assert len(pending) == 10
        assert "reviews/helsingborg_dresser_reviews.md" in pending

    def test_copy_keeps_only_build_inputs(self, tmp_path):
        from prototypes.us025_virtual_domain.prepare_state import KEEP_KEYS, SOURCE_STATE, prepare

        copy = json.loads(prepare(SOURCE_STATE, tmp_path).read_text())
        assert tuple(copy) == KEEP_KEYS
        for dropped in ("text_graph_progress", "proposed_resolution_candidates",
                        "approved_resolution_candidates", "domain_node_schema"):
            assert dropped not in copy

    def test_shared_state_untouched(self, tmp_path):
        from prototypes.us025_virtual_domain.prepare_state import SOURCE_STATE, prepare

        before = SOURCE_STATE.read_bytes()
        prepare(SOURCE_STATE, tmp_path)
        assert SOURCE_STATE.read_bytes() == before

    def test_missing_inputs_rejected(self):
        from prototypes.us025_virtual_domain.prepare_state import filtered_state

        with pytest.raises(KeyError):
            filtered_state({"approved_files": {}})


class TestNativeGraphChecks:
    @staticmethod
    def _driver(indexes, non_text, corresponds_to):
        from unittest.mock import MagicMock

        def run(query, **params):
            result = MagicMock()
            if "SHOW INDEXES" in query:
                result.__iter__.return_value = [{"name": n, "state": s} for n, s in indexes.items()]
            elif "NOT n:__Entity__" in query:
                result.__iter__.return_value = non_text
            elif "CORRESPONDS_TO" in query:
                result.single.return_value = {"c": corresponds_to}
            else:
                result.__iter__.return_value = [{"label": "Chunk", "count": 40}]
            return result

        driver = MagicMock()
        driver.session.return_value.__enter__.return_value.run.side_effect = run
        return driver

    def test_clean_text_graph_passes(self):
        from prototypes.us025_virtual_domain.load_native import check_native_graph

        driver = self._driver({"chunk-embeddings": "ONLINE", "chunk-fulltext": "ONLINE"}, [], 0)
        assert check_native_graph(driver)["ok"]

    @pytest.mark.parametrize("indexes, non_text, corresponds_to", [
        ({"chunk-embeddings": "ONLINE"}, [], 0),                                     # fulltext missing
        ({"chunk-embeddings": "POPULATING", "chunk-fulltext": "ONLINE"}, [], 0),     # not online yet
        ({"chunk-embeddings": "ONLINE", "chunk-fulltext": "ONLINE"},
         [{"labels": ["Supplier"], "count": 20}], 0),                                # domain nodes
        ({"chunk-embeddings": "ONLINE", "chunk-fulltext": "ONLINE"}, [], 12),        # resolution ran
    ])
    def test_violations_fail(self, indexes, non_text, corresponds_to):
        from prototypes.us025_virtual_domain.load_native import check_native_graph

        assert not check_native_graph(self._driver(indexes, non_text, corresponds_to))["ok"]
