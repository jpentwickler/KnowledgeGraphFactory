"""Unit tests for Schema Proposal tool handlers."""

import csv
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.schema_tools import (
    handle_get_approved_files,
    handle_search_file,
    handle_propose_node_construction,
    handle_propose_relationship_construction,
    handle_remove_node_construction,
    handle_remove_relationship_construction,
    handle_get_proposed_construction_plan,
    handle_approve_proposed_construction_plan,
    handle_submit_review,
    build_file_context,
)


def _create_test_data(tmp_dir):
    """Create test CSV files in a temp directory."""
    # products.csv
    products_path = os.path.join(tmp_dir, "products.csv")
    with open(products_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["product_id", "product_name", "price", "description"])
        writer.writerow(["P-1000", "Stockholm Chair", "246", "Ergonomic design"])
        writer.writerow(["P-1001", "Gothenburg Table", "599", "Solid oak"])
        writer.writerow(["P-1002", "Malmo Desk", "349", "Modern workspace"])

    # suppliers.csv
    suppliers_path = os.path.join(tmp_dir, "suppliers.csv")
    with open(suppliers_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["supplier_id", "name", "specialty", "city"])
        writer.writerow(["SUP-001", "Nordic Wood", "Wood", "Stockholm"])
        writer.writerow(["SUP-002", "Steel Works", "Metal", "Gothenburg"])

    # part_supplier_mapping.csv (relationship file)
    mapping_path = os.path.join(tmp_dir, "part_supplier_mapping.csv")
    with open(mapping_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["part_id", "part_name", "supplier_id", "supplier_name", "lead_time_days", "unit_cost"])
        writer.writerow(["S-1074", "Drawer Front", "SUP-001", "Nordic Wood", "8", "42.73"])
        writer.writerow(["S-1074", "Drawer Front", "SUP-002", "Steel Works", "12", "38.50"])
        writer.writerow(["S-1075", "Drawer Slide", "SUP-001", "Nordic Wood", "5", "15.20"])

    return products_path, suppliers_path, mapping_path


# ---------------------------------------------------------------------------
# Setup / teardown helpers
# ---------------------------------------------------------------------------

_tmp_dir = None
_old_env = None


def setup_module():
    """Create temp data directory and set KG_DATA_DIR."""
    global _tmp_dir, _old_env
    _tmp_dir = tempfile.mkdtemp()
    _old_env = os.environ.get("KG_DATA_DIR")
    os.environ["KG_DATA_DIR"] = _tmp_dir
    _create_test_data(_tmp_dir)


def teardown_module():
    """Remove temp directory and restore env."""
    global _tmp_dir, _old_env
    if _tmp_dir and os.path.exists(_tmp_dir):
        shutil.rmtree(_tmp_dir)
    if _old_env is not None:
        os.environ["KG_DATA_DIR"] = _old_env
    elif "KG_DATA_DIR" in os.environ:
        del os.environ["KG_DATA_DIR"]


# ---------------------------------------------------------------------------
# Tests: get_approved_files
# ---------------------------------------------------------------------------

def test_get_approved_files_missing():
    state = {}
    result = handle_get_approved_files(state)
    assert result["status"] == "error"
    assert "Stage 2" in result["message"]
    print("[OK] test_get_approved_files_missing")


def test_get_approved_files_present():
    state = {
        "approved_files": {
            "structured": [
                {"path": "products.csv", "reason": "Product data"},
                {"path": "suppliers.csv", "reason": "Supplier data"},
            ],
            "unstructured": [
                {"path": "reviews/notes.md", "reason": "Review text"},
            ],
        }
    }
    result = handle_get_approved_files(state)
    assert result["status"] == "success"
    assert result["structured_files"] == ["products.csv", "suppliers.csv"]
    assert result["unstructured_files"] == ["reviews/notes.md"]
    assert len(result["all_files"]) == 3
    print("[OK] test_get_approved_files_present")


# ---------------------------------------------------------------------------
# Tests: search_file
# ---------------------------------------------------------------------------

def test_search_file_found():
    state = {}
    result = handle_search_file(state, "products.csv", "product_id")
    assert result["status"] == "success"
    assert result["lines_found"] > 0
    assert any("product_id" in m["content"] for m in result["matching_lines"])
    print("[OK] test_search_file_found")


def test_search_file_not_found():
    state = {}
    result = handle_search_file(state, "products.csv", "nonexistent_column_xyz")
    assert result["status"] == "success"
    assert result["lines_found"] == 0
    print("[OK] test_search_file_not_found")


def test_search_file_missing_file():
    state = {}
    result = handle_search_file(state, "does_not_exist.csv", "anything")
    assert result["status"] == "error"
    assert "not found" in result["message"].lower()
    print("[OK] test_search_file_missing_file")


def test_search_file_case_insensitive():
    state = {}
    result = handle_search_file(state, "products.csv", "PRODUCT_ID")
    assert result["status"] == "success"
    assert result["lines_found"] > 0
    print("[OK] test_search_file_case_insensitive")


# ---------------------------------------------------------------------------
# Tests: propose_node_construction
# ---------------------------------------------------------------------------

def test_propose_node_success():
    state = {}
    result = handle_propose_node_construction(
        state,
        approved_file="products.csv",
        proposed_label="Product",
        unique_column_name="product_id",
        proposed_properties=["product_name", "price", "description"],
    )
    assert result["status"] == "success"
    assert "Product" in state["proposed_construction_plan"]
    rule = state["proposed_construction_plan"]["Product"]
    assert rule["construction_type"] == "node"
    assert rule["label"] == "Product"
    assert rule["unique_column_name"] == "product_id"
    print("[OK] test_propose_node_success")


def test_propose_node_bad_column():
    state = {}
    result = handle_propose_node_construction(
        state,
        approved_file="products.csv",
        proposed_label="Product",
        unique_column_name="bogus_column",
        proposed_properties=["product_name"],
    )
    assert result["status"] == "error"
    assert "bogus_column" in result["message"]
    assert "proposed_construction_plan" not in state
    print("[OK] test_propose_node_bad_column")


def test_propose_node_incremental():
    state = {}
    handle_propose_node_construction(
        state,
        approved_file="products.csv",
        proposed_label="Product",
        unique_column_name="product_id",
        proposed_properties=["product_name"],
    )
    handle_propose_node_construction(
        state,
        approved_file="suppliers.csv",
        proposed_label="Supplier",
        unique_column_name="supplier_id",
        proposed_properties=["name", "specialty"],
    )
    assert len(state["proposed_construction_plan"]) == 2
    assert "Product" in state["proposed_construction_plan"]
    assert "Supplier" in state["proposed_construction_plan"]
    print("[OK] test_propose_node_incremental")


# ---------------------------------------------------------------------------
# Tests: propose_relationship_construction
# ---------------------------------------------------------------------------

def test_propose_relationship_success():
    state = {}
    result = handle_propose_relationship_construction(
        state,
        approved_file="part_supplier_mapping.csv",
        proposed_relationship_type="SUPPLIED_BY",
        from_node_label="Part",
        from_node_column="part_id",
        to_node_label="Supplier",
        to_node_column="supplier_id",
        proposed_properties=["lead_time_days", "unit_cost"],
    )
    assert result["status"] == "success"
    assert "SUPPLIED_BY" in state["proposed_construction_plan"]
    rule = state["proposed_construction_plan"]["SUPPLIED_BY"]
    assert rule["construction_type"] == "relationship"
    assert rule["from_node_label"] == "Part"
    assert rule["to_node_label"] == "Supplier"
    print("[OK] test_propose_relationship_success")


def test_propose_relationship_bad_from_column():
    state = {}
    result = handle_propose_relationship_construction(
        state,
        approved_file="part_supplier_mapping.csv",
        proposed_relationship_type="SUPPLIED_BY",
        from_node_label="Part",
        from_node_column="bogus_from",
        to_node_label="Supplier",
        to_node_column="supplier_id",
    )
    assert result["status"] == "error"
    assert "from_node_column" in result["message"]
    print("[OK] test_propose_relationship_bad_from_column")


def test_propose_relationship_bad_to_column():
    state = {}
    result = handle_propose_relationship_construction(
        state,
        approved_file="part_supplier_mapping.csv",
        proposed_relationship_type="SUPPLIED_BY",
        from_node_label="Part",
        from_node_column="part_id",
        to_node_label="Supplier",
        to_node_column="bogus_to",
    )
    assert result["status"] == "error"
    assert "to_node_column" in result["message"]
    print("[OK] test_propose_relationship_bad_to_column")


# ---------------------------------------------------------------------------
# Tests: remove constructions
# ---------------------------------------------------------------------------

def test_remove_node_exists():
    state = {"proposed_construction_plan": {"Product": {"construction_type": "node"}}}
    result = handle_remove_node_construction(state, "Product")
    assert result["status"] == "success"
    assert "Product" not in state["proposed_construction_plan"]
    print("[OK] test_remove_node_exists")


def test_remove_node_missing():
    state = {"proposed_construction_plan": {}}
    result = handle_remove_node_construction(state, "NonExistent")
    assert result["status"] == "success"  # idempotent
    print("[OK] test_remove_node_missing")


def test_remove_relationship_exists():
    state = {"proposed_construction_plan": {"SUPPLIED_BY": {"construction_type": "relationship"}}}
    result = handle_remove_relationship_construction(state, "SUPPLIED_BY")
    assert result["status"] == "success"
    assert "SUPPLIED_BY" not in state["proposed_construction_plan"]
    print("[OK] test_remove_relationship_exists")


def test_remove_relationship_missing():
    state = {"proposed_construction_plan": {}}
    result = handle_remove_relationship_construction(state, "NONEXISTENT")
    assert result["status"] == "success"  # idempotent
    print("[OK] test_remove_relationship_missing")


# ---------------------------------------------------------------------------
# Tests: get_proposed_construction_plan
# ---------------------------------------------------------------------------

def test_get_plan_empty():
    state = {}
    result = handle_get_proposed_construction_plan(state)
    assert result["status"] == "success"
    assert result["node_count"] == 0
    assert result["relationship_count"] == 0
    print("[OK] test_get_plan_empty")


def test_get_plan_populated():
    state = {
        "proposed_construction_plan": {
            "Product": {"construction_type": "node"},
            "Supplier": {"construction_type": "node"},
            "SUPPLIED_BY": {"construction_type": "relationship"},
        }
    }
    result = handle_get_proposed_construction_plan(state)
    assert result["status"] == "success"
    assert result["node_count"] == 2
    assert result["relationship_count"] == 1
    assert result["total_rules"] == 3
    print("[OK] test_get_plan_populated")


# ---------------------------------------------------------------------------
# Tests: approve_proposed_construction_plan
# ---------------------------------------------------------------------------

def test_approve_no_plan():
    state = {}
    result = handle_approve_proposed_construction_plan(state)
    assert result["status"] == "error"
    print("[OK] test_approve_no_plan")


def test_approve_empty_plan():
    state = {"proposed_construction_plan": {}}
    result = handle_approve_proposed_construction_plan(state)
    assert result["status"] == "error"
    print("[OK] test_approve_empty_plan")


def test_approve_with_plan():
    state = {
        "proposed_construction_plan": {
            "Product": {
                "construction_type": "node",
                "source_file": "products.csv",
                "label": "Product",
                "unique_column_name": "product_id",
                "properties": ["product_name", "price"],
            }
        }
    }
    result = handle_approve_proposed_construction_plan(state)
    assert result["status"] == "approved"
    assert "approved_construction_plan" in state
    assert "Product" in state["approved_construction_plan"]
    print("[OK] test_approve_with_plan")


# ---------------------------------------------------------------------------
# Tests: submit_review
# ---------------------------------------------------------------------------

def test_submit_review_valid():
    state = {}
    result = handle_submit_review(state, verdict="valid", problems=[])
    assert result["status"] == "success"
    assert state["_critic_verdict"] == "valid"
    assert state["_critic_problems"] == []
    print("[OK] test_submit_review_valid")


def test_submit_review_retry():
    state = {}
    problems = ["Missing connectivity", "Redundant relationship"]
    result = handle_submit_review(state, verdict="retry", problems=problems)
    assert result["status"] == "success"
    assert state["_critic_verdict"] == "retry"
    assert len(state["_critic_problems"]) == 2
    print("[OK] test_submit_review_retry")


# ---------------------------------------------------------------------------
# Tests: build_file_context
# ---------------------------------------------------------------------------

def test_build_file_context_no_approved_files():
    state = {}
    result = build_file_context(state)
    assert result == ""
    print("[OK] test_build_file_context_no_approved_files")


def test_build_file_context_with_files():
    state = {
        "approved_files": {
            "structured": [
                {"path": "products.csv", "reason": "Product data"},
                {"path": "suppliers.csv", "reason": "Supplier data"},
            ],
            "unstructured": [],
        }
    }
    result = build_file_context(state)
    assert "=== products.csv ===" in result
    assert "=== suppliers.csv ===" in result
    assert "Columns:" in result
    assert "product_id" in result
    assert "supplier_id" in result
    assert "Row count:" in result
    assert "Sample rows" in result
    print("[OK] test_build_file_context_with_files")


def test_build_file_context_missing_file():
    state = {
        "approved_files": {
            "structured": [
                {"path": "nonexistent_file.csv", "reason": "Does not exist"},
            ],
            "unstructured": [],
        }
    }
    result = build_file_context(state)
    assert "=== nonexistent_file.csv ===" in result
    assert "[ERROR: File not found]" in result
    print("[OK] test_build_file_context_missing_file")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    setup()
    try:
        # get_approved_files
        test_get_approved_files_missing()
        test_get_approved_files_present()

        # search_file
        test_search_file_found()
        test_search_file_not_found()
        test_search_file_missing_file()
        test_search_file_case_insensitive()

        # propose_node_construction
        test_propose_node_success()
        test_propose_node_bad_column()
        test_propose_node_incremental()

        # propose_relationship_construction
        test_propose_relationship_success()
        test_propose_relationship_bad_from_column()
        test_propose_relationship_bad_to_column()

        # remove constructions
        test_remove_node_exists()
        test_remove_node_missing()
        test_remove_relationship_exists()
        test_remove_relationship_missing()

        # get_proposed_construction_plan
        test_get_plan_empty()
        test_get_plan_populated()

        # approve
        test_approve_no_plan()
        test_approve_empty_plan()
        test_approve_with_plan()

        # submit_review
        test_submit_review_valid()
        test_submit_review_retry()

        # build_file_context
        test_build_file_context_no_approved_files()
        test_build_file_context_with_files()
        test_build_file_context_missing_file()

        print("\n" + "=" * 50)
        print("ALL UNIT TESTS PASSED [OK]")
        print("=" * 50)
    finally:
        teardown()
