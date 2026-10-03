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


# ---------------------------------------------------------------------------
# Key stamping (step 3)
# ---------------------------------------------------------------------------


def _doc(product):
    return {"title": f"{product} Reviews", "path": f"/data/reviews/{product.lower()}.md"}


class TestProductForDocument:
    def test_title_minus_suffix(self):
        from prototypes.us025_virtual_domain.stamp_keys import product_for_document

        assert product_for_document(_doc("Helsingborg Dresser")) == "Helsingborg Dresser"

    def test_falls_back_to_file_heading(self):
        from prototypes.us025_virtual_domain.stamp_keys import product_for_document

        path = duckdb_domain.DEFAULT_DATA_DIR / "reviews" / "jonkoping_coffee_table_reviews.md"
        assert product_for_document({"title": None, "path": str(path)}) == "Jönköping Coffee Table"

    def test_every_review_document_names_one_product(self, con):
        """All 10 review titles map to exactly one product in products.csv."""
        from prototypes.us025_virtual_domain.stamp_keys import product_for_document

        names = {r[0] for r in con.execute("SELECT product_name FROM products").fetchall()}
        reviews = sorted((duckdb_domain.DEFAULT_DATA_DIR / "reviews").glob("*.md"))
        assert len(reviews) == 10
        for path in reviews:
            assert product_for_document({"title": None, "path": str(path)}) in names, path.name


class TestResolve:
    def test_helsingborg_drawer_rails_is_s1085(self, con):
        """The product narrows "drawer rails" to S-1085, not S-1078 (Malmö Desk)."""
        from prototypes.us025_virtual_domain.stamp_keys import part_ids_for, resolve

        assert part_ids_for(con, "Malmö Desk", "Drawer Rails") == ["S-1078"]
        [result] = resolve(con, [{"id": "e1", "name": "drawer rails",
                                  "documents": [_doc("Helsingborg Dresser")]}])
        assert (result["status"], result["part_id"]) == ("stamped", "S-1085")

    def test_part_from_two_products_is_ambiguous(self, con):
        from prototypes.us025_virtual_domain.stamp_keys import resolve

        [result] = resolve(con, [{"id": "e1", "name": "drawer rails",
                                  "documents": [_doc("Helsingborg Dresser"), _doc("Malmö Desk")]}])
        assert result["status"] == "ambiguous"
        assert result["part_id"] is None
        assert result["products"] == ["Helsingborg Dresser", "Malmö Desk"]

    def test_unknown_part_name_is_unmatched(self, con):
        from prototypes.us025_virtual_domain.stamp_keys import resolve

        [result] = resolve(con, [{"id": "e1", "name": "flux capacitor",
                                  "documents": [_doc("Helsingborg Dresser")]}])
        assert (result["status"], result["part_id"]) == ("unmatched", None)

    def test_no_name_similarity_fallback(self, con):
        """A near-miss name is unmatched, not fuzzy-matched."""
        from prototypes.us025_virtual_domain.stamp_keys import resolve

        [result] = resolve(con, [{"id": "e1", "name": "drawer rail",
                                  "documents": [_doc("Helsingborg Dresser")]}])
        assert result["status"] == "unmatched"

    def test_stamp_writes_only_resolved_keys(self, con):
        from unittest.mock import MagicMock

        from prototypes.us025_virtual_domain.stamp_keys import STAMP, UNSTAMP, stamp

        session = MagicMock()
        session.run.side_effect = lambda q, **p: (
            [{"id": "e1", "name": "drawer rails", "documents": [_doc("Helsingborg Dresser")]},
             {"id": "e2", "name": "flux capacitor", "documents": [_doc("Helsingborg Dresser")]}]
            if not p else None
        )
        driver = MagicMock()
        driver.session.return_value.__enter__.return_value = session

        stamp(driver, con)
        calls = {c.args[0]: c.kwargs for c in session.run.call_args_list[1:]}
        assert calls[STAMP] == {"rows": [{"id": "e1", "part_id": "S-1085"}]}
        assert calls[UNSTAMP] == {"ids": ["e2"]}


# ---------------------------------------------------------------------------
# CQ5 join and Virtual Graph hop 2 (step 4)
# ---------------------------------------------------------------------------

# What hop 1 returns for the drawer-rails complaint once keys are stamped.
HELSINGBORG_HITS = [
    {"chunk": "The drawer rails were the worst part, they were defective.", "score": 0.91,
     "strict": [{"defect": "defective drawer rails", "part": "drawer rails", "part_id": "S-1085"}],
     "loose": [{"part": "drawer rails", "part_id": "S-1085"}]},
    {"chunk": "Drawers stick after a month.", "score": 0.74, "strict": [],
     "loose": [{"part": None, "part_id": None}]},
]


class TestJoinCq5:
    def test_strict_path_keys_reach_hop2(self):
        from prototypes.us025_virtual_domain.cq5 import join_cq5

        seen = []
        result = join_cq5(HELSINGBORG_HITS, lambda keys: seen.append(keys) or [{"part_id": "S-1085"}])
        assert seen == [["S-1085"]]
        assert result["key_path"] == "strict"
        assert result["suppliers"] == [{"part_id": "S-1085"}]

    def test_loose_path_only_without_strict_keys(self):
        from prototypes.us025_virtual_domain.cq5 import keys_from_hop1

        hits = [{"strict": [], "loose": [{"part": "drawer rails", "part_id": "S-1085"}]}]
        assert keys_from_hop1(hits) == {
            "path": "loose", "part_ids": ["S-1085"],
            "evidence": [{"part": "drawer rails", "part_id": "S-1085"}],
        }

    def test_no_keys_skips_hop2(self):
        from prototypes.us025_virtual_domain.cq5 import join_cq5

        def fail(keys):
            raise AssertionError("hop 2 must not run without keys")

        result = join_cq5([{"strict": [], "loose": [{"part_id": None}]}], fail)
        assert (result["key_path"], result["part_ids"], result["suppliers"]) == ("none", [], [])


class TestVirtualGraphBackend:
    def test_one_lookup_per_key_on_vg_database(self, monkeypatch):
        from unittest.mock import MagicMock

        from prototypes.us025_virtual_domain import cq5

        session = MagicMock()
        session.run.side_effect = lambda q, part_id=None: [
            {"part_id": part_id, "supplier_name": "Shanghai Metal Corp"},
            {"part_id": part_id, "supplier_name": "Korean Metal Works"},
        ]
        driver = MagicMock()
        driver.session.return_value.__enter__.return_value = session
        monkeypatch.setenv("VG_DATABASE", "furniture")
        monkeypatch.setattr("utils.get_neo4j_driver", lambda **kw: driver)

        fetch, _, _ = cq5.virtual_graph_backend()
        rows = fetch(["S-1085", "S-1078"])

        driver.session.assert_called_with(database="furniture")
        assert [c.kwargs["part_id"] for c in session.run.call_args_list] == ["S-1085", "S-1078"]
        assert [(r["part_id"], r["supplier_name"]) for r in rows][:2] == [
            ("S-1078", "Korean Metal Works"), ("S-1078", "Shanghai Metal Corp")]

    def test_requires_vg_database(self, monkeypatch):
        from prototypes.us025_virtual_domain import cq5

        monkeypatch.delenv("VG_DATABASE", raising=False)
        with pytest.raises(SystemExit):
            cq5.virtual_graph_backend()

    def test_composite_attempt_uses_both_aliases(self):
        text = (PROTOTYPE_DIR / "cq5_composite.cypher").read_text()
        assert "USE us025.native" in text and "USE us025.domain" in text


# ---------------------------------------------------------------------------
# Python/DuckDB baseline hop 2 (step 5)
# ---------------------------------------------------------------------------


class TestDuckdbBaseline:
    def test_cq5_answer_from_the_csv(self):
        """Stubbed hop 1 + real DuckDB hop 2 gives the two suppliers with prices."""
        from prototypes.us025_virtual_domain.cq5 import duckdb_backend, join_cq5

        fetch, rollup, close = duckdb_backend()
        try:
            result = join_cq5(HELSINGBORG_HITS, fetch)
            roll = rollup()
        finally:
            close()
        assert [(s["supplier_name"], s["unit_cost"], s["lead_time_days"]) for s in result["suppliers"]] == [
            ("Korean Metal Works", 47.14, 17),
            ("Shanghai Metal Corp", 40.82, 26),
        ]
        assert sum(r["parts"] for r in roll) == 176

    def test_live_price_through_the_join(self, data_dir, monkeypatch):
        """Editing the CSV changes the CQ5 answer with no rebuild step in between."""
        from prototypes.us025_virtual_domain import cq5

        monkeypatch.setattr(duckdb_domain, "DEFAULT_DATA_DIR", data_dir)
        monkeypatch.setattr(duckdb_domain.connect, "__defaults__", (data_dir, None))
        fetch, _, close = cq5.duckdb_backend()
        try:
            before = {s["supplier_name"]: s["unit_cost"] for s in cq5.join_cq5(HELSINGBORG_HITS, fetch)["suppliers"]}
            csv = data_dir / "part_supplier_mapping.csv"
            csv.write_text(csv.read_text().replace(",$47.14,", ",$12.34,"))
            after = {s["supplier_name"]: s["unit_cost"] for s in cq5.join_cq5(HELSINGBORG_HITS, fetch)["suppliers"]}
        finally:
            close()
        assert (before["Korean Metal Works"], after["Korean Metal Works"]) == (47.14, 12.34)
