"""Unit tests for File Suggestion Agent tool handlers."""

import csv
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.file_tools import (
    handle_get_approved_user_goal,
    handle_list_available_files,
    handle_get_file_info,
    handle_sample_file,
    handle_set_proposed_files,
    handle_approve_proposed_files,
)


def _create_test_data(tmp_dir):
    """Create test CSV and markdown files in a temp directory."""
    # CSV file
    csv_path = os.path.join(tmp_dir, "products.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "price", "category"])
        writer.writerow(["1", "Chair", "199.99", "Furniture"])
        writer.writerow(["2", "Table", "499.99", "Furniture"])
        writer.writerow(["3", "Lamp", "79.99", "Lighting"])

    # Markdown file
    md_dir = os.path.join(tmp_dir, "reviews")
    os.makedirs(md_dir, exist_ok=True)
    md_path = os.path.join(md_dir, "notes.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Product Notes\n")
        f.write("\n")
        f.write("## Chair Review\n")
        f.write("Great quality chair.\n")
        f.write("\n")
        f.write("## Table Review\n")
        f.write("Sturdy construction.\n")

    return csv_path, md_path


def test_get_approved_user_goal_missing():
    """Test get_approved_user_goal when no goal exists."""
    state = {}
    result = handle_get_approved_user_goal(state)

    assert result["status"] == "error"
    assert "Stage 1" in result["message"] or "No approved" in result["message"]

    print("[OK] test_get_approved_user_goal_missing passed")


def test_get_approved_user_goal_present():
    """Test get_approved_user_goal when goal exists."""
    state = {
        "approved_user_goal": {
            "kind_of_graph": "supply chain",
            "graph_description": "A supply chain knowledge graph."
        }
    }
    result = handle_get_approved_user_goal(state)

    assert result["status"] == "success"
    assert result["approved_goal"]["kind_of_graph"] == "supply chain"

    print("[OK] test_get_approved_user_goal_present passed")


def test_list_available_files_all():
    """Test listing all files."""
    tmp_dir = tempfile.mkdtemp()
    old_env = os.environ.get("KG_DATA_DIR")
    try:
        os.environ["KG_DATA_DIR"] = tmp_dir
        _create_test_data(tmp_dir)

        result = handle_list_available_files({})

        assert result["status"] == "success"
        assert result["count"] == 2
        assert "products.csv" in result["files"]
        assert "reviews/notes.md" in result["files"]

        print("[OK] test_list_available_files_all passed")
    finally:
        if old_env is None:
            os.environ.pop("KG_DATA_DIR", None)
        else:
            os.environ["KG_DATA_DIR"] = old_env
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_list_available_files_csv_only():
    """Test listing only CSV files."""
    tmp_dir = tempfile.mkdtemp()
    old_env = os.environ.get("KG_DATA_DIR")
    try:
        os.environ["KG_DATA_DIR"] = tmp_dir
        _create_test_data(tmp_dir)

        result = handle_list_available_files({}, file_type="csv")

        assert result["status"] == "success"
        assert result["count"] == 1
        assert "products.csv" in result["files"]

        print("[OK] test_list_available_files_csv_only passed")
    finally:
        if old_env is None:
            os.environ.pop("KG_DATA_DIR", None)
        else:
            os.environ["KG_DATA_DIR"] = old_env
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_list_available_files_markdown_only():
    """Test listing only markdown files."""
    tmp_dir = tempfile.mkdtemp()
    old_env = os.environ.get("KG_DATA_DIR")
    try:
        os.environ["KG_DATA_DIR"] = tmp_dir
        _create_test_data(tmp_dir)

        result = handle_list_available_files({}, file_type="markdown")

        assert result["status"] == "success"
        assert result["count"] == 1
        assert "reviews/notes.md" in result["files"]

        print("[OK] test_list_available_files_markdown_only passed")
    finally:
        if old_env is None:
            os.environ.pop("KG_DATA_DIR", None)
        else:
            os.environ["KG_DATA_DIR"] = old_env
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_get_file_info_csv():
    """Test getting info for a CSV file."""
    tmp_dir = tempfile.mkdtemp()
    old_env = os.environ.get("KG_DATA_DIR")
    try:
        os.environ["KG_DATA_DIR"] = tmp_dir
        _create_test_data(tmp_dir)

        result = handle_get_file_info({}, file_path="products.csv")

        assert result["status"] == "success"
        assert result["file_type"] == "csv"
        assert result["columns"] == ["id", "name", "price", "category"]
        assert result["row_count"] == 3
        assert result["size_kb"] > 0

        print("[OK] test_get_file_info_csv passed")
    finally:
        if old_env is None:
            os.environ.pop("KG_DATA_DIR", None)
        else:
            os.environ["KG_DATA_DIR"] = old_env
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_get_file_info_markdown():
    """Test getting info for a markdown file."""
    tmp_dir = tempfile.mkdtemp()
    old_env = os.environ.get("KG_DATA_DIR")
    try:
        os.environ["KG_DATA_DIR"] = tmp_dir
        _create_test_data(tmp_dir)

        result = handle_get_file_info({}, file_path="reviews/notes.md")

        assert result["status"] == "success"
        assert result["file_type"] == "markdown"
        assert len(result["headings"]) == 3  # #, ##, ##
        assert result["line_count"] == 7
        assert result["size_kb"] > 0

        print("[OK] test_get_file_info_markdown passed")
    finally:
        if old_env is None:
            os.environ.pop("KG_DATA_DIR", None)
        else:
            os.environ["KG_DATA_DIR"] = old_env
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_get_file_info_not_found():
    """Test getting info for a nonexistent file."""
    tmp_dir = tempfile.mkdtemp()
    old_env = os.environ.get("KG_DATA_DIR")
    try:
        os.environ["KG_DATA_DIR"] = tmp_dir

        result = handle_get_file_info({}, file_path="nonexistent.csv")

        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

        print("[OK] test_get_file_info_not_found passed")
    finally:
        if old_env is None:
            os.environ.pop("KG_DATA_DIR", None)
        else:
            os.environ["KG_DATA_DIR"] = old_env
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_sample_file():
    """Test sampling lines from a file."""
    tmp_dir = tempfile.mkdtemp()
    old_env = os.environ.get("KG_DATA_DIR")
    try:
        os.environ["KG_DATA_DIR"] = tmp_dir
        _create_test_data(tmp_dir)

        result = handle_sample_file({}, file_path="products.csv", num_lines=2)

        assert result["status"] == "success"
        assert result["num_lines"] == 2
        assert "id,name,price,category" in result["content"]

        print("[OK] test_sample_file passed")
    finally:
        if old_env is None:
            os.environ.pop("KG_DATA_DIR", None)
        else:
            os.environ["KG_DATA_DIR"] = old_env
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_sample_file_not_found():
    """Test sampling a nonexistent file."""
    tmp_dir = tempfile.mkdtemp()
    old_env = os.environ.get("KG_DATA_DIR")
    try:
        os.environ["KG_DATA_DIR"] = tmp_dir

        result = handle_sample_file({}, file_path="missing.csv")

        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

        print("[OK] test_sample_file_not_found passed")
    finally:
        if old_env is None:
            os.environ.pop("KG_DATA_DIR", None)
        else:
            os.environ["KG_DATA_DIR"] = old_env
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_set_proposed_files():
    """Test setting the proposed files."""
    state = {}

    result = handle_set_proposed_files(
        state,
        structured=[
            {"path": "products.csv", "reason": "Contains product data"},
        ],
        unstructured=[
            {"path": "reviews/notes.md", "reason": "Contains product reviews"},
        ],
    )

    assert result["status"] == "proposed"
    assert "1 structured" in result["message"]
    assert "1 unstructured" in result["message"]

    assert "proposed_files" in state
    assert len(state["proposed_files"]["structured"]) == 1
    assert len(state["proposed_files"]["unstructured"]) == 1

    print("[OK] test_set_proposed_files passed")


def test_approve_without_proposal():
    """Test approving when no proposal exists."""
    state = {}

    result = handle_approve_proposed_files(state)

    assert result["status"] == "error"
    assert "No proposed files" in result["message"]
    assert "approved_files" not in state

    print("[OK] test_approve_without_proposal passed")


def test_approve_with_proposal():
    """Test approving an existing proposal."""
    state = {
        "proposed_files": {
            "structured": [
                {"path": "products.csv", "reason": "Product data"},
            ],
            "unstructured": [
                {"path": "reviews/notes.md", "reason": "Reviews"},
            ],
        }
    }

    result = handle_approve_proposed_files(state)

    assert result["status"] == "approved"
    assert "approved_files" in result
    assert "approved_files" in state
    assert len(state["approved_files"]["structured"]) == 1
    assert len(state["approved_files"]["unstructured"]) == 1

    print("[OK] test_approve_with_proposal passed")


def test_path_traversal_blocked():
    """Test that path traversal outside data dir is blocked."""
    tmp_dir = tempfile.mkdtemp()
    old_env = os.environ.get("KG_DATA_DIR")
    try:
        os.environ["KG_DATA_DIR"] = tmp_dir

        result = handle_get_file_info({}, file_path="../../etc/passwd")

        assert result["status"] == "error"

        print("[OK] test_path_traversal_blocked passed")
    finally:
        if old_env is None:
            os.environ.pop("KG_DATA_DIR", None)
        else:
            os.environ["KG_DATA_DIR"] = old_env
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    print("=" * 70)
    print("UNIT TESTS - File Suggestion Tool Handlers")
    print("=" * 70)

    tests = [
        test_get_approved_user_goal_missing,
        test_get_approved_user_goal_present,
        test_list_available_files_all,
        test_list_available_files_csv_only,
        test_list_available_files_markdown_only,
        test_get_file_info_csv,
        test_get_file_info_markdown,
        test_get_file_info_not_found,
        test_sample_file,
        test_sample_file_not_found,
        test_set_proposed_files,
        test_approve_without_proposal,
        test_approve_with_proposal,
        test_path_traversal_blocked,
    ]

    passed = 0
    failed = 0

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test_fn.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
        except Exception as e:
            print(f"[ERROR] {test_fn.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 70)
    if failed == 0:
        print(f"ALL {passed} UNIT TESTS PASSED [OK]")
    else:
        print(f"{passed} passed, {failed} failed [FAIL]")
    print("=" * 70)

    if failed > 0:
        sys.exit(1)
