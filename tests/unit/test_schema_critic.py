"""Unit tests for Schema Critic scope logic and helper functions."""

import csv
import os
import tempfile

from tools.schema_tools import build_file_context
from agents.schema_critic import _format_entity_types, _format_fact_types


def test_build_file_context_structured_scope():
    """Test that scope='structured' excludes markdown files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["KG_DATA_DIR"] = tmpdir

        # Create a CSV file
        csv_path = os.path.join(tmpdir, "products.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "name"])
            writer.writerow(["1", "Table"])

        # Create a markdown file
        md_path = os.path.join(tmpdir, "reviews.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# Product Reviews\nGreat table!\n")

        state = {
            "approved_files": {
                "structured": [{"path": "products.csv", "reason": "product data"}],
                "unstructured": [{"path": "reviews.md", "reason": "review data"}],
            }
        }

        result = build_file_context(state, scope="structured")

        assert "products.csv" in result, "CSV file should be included"
        assert "reviews.md" not in result, "Markdown file should be excluded"
        assert "id, name" in result, "CSV columns should appear"

    print("[OK] test_build_file_context_structured_scope passed")


def test_build_file_context_all_scope():
    """Test that scope='all' includes both file types (backward compat)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["KG_DATA_DIR"] = tmpdir

        csv_path = os.path.join(tmpdir, "products.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "name"])
            writer.writerow(["1", "Table"])

        md_path = os.path.join(tmpdir, "reviews.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# Product Reviews\nGreat table!\n")

        state = {
            "approved_files": {
                "structured": [{"path": "products.csv", "reason": "product data"}],
                "unstructured": [{"path": "reviews.md", "reason": "review data"}],
            }
        }

        result = build_file_context(state, scope="all")

        assert "products.csv" in result, "CSV file should be included"
        assert "reviews.md" in result, "Markdown file should be included"

    print("[OK] test_build_file_context_all_scope passed")


def test_build_file_context_default_scope():
    """Test that default scope is 'all' for backward compatibility."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["KG_DATA_DIR"] = tmpdir

        csv_path = os.path.join(tmpdir, "products.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "name"])
            writer.writerow(["1", "Table"])

        md_path = os.path.join(tmpdir, "reviews.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# Reviews\nContent\n")

        state = {
            "approved_files": {
                "structured": [{"path": "products.csv", "reason": "test"}],
                "unstructured": [{"path": "reviews.md", "reason": "test"}],
            }
        }

        # No scope argument -- should behave like "all"
        result = build_file_context(state)

        assert "products.csv" in result, "CSV should be included by default"
        assert "reviews.md" in result, "Markdown should be included by default"

    print("[OK] test_build_file_context_default_scope passed")


def test_format_entity_types_proposed_priority():
    """Test that proposed entity types take priority over approved."""
    state = {
        "proposed_entity_types": {
            "Product": {"source": "well_known", "description": "Products from text"},
        },
        "approved_entity_types": {
            "OldType": {"source": "discovered", "description": "Should not appear"},
        },
    }

    result = _format_entity_types(state)

    assert "Product" in result, "Proposed type should appear"
    assert "OldType" not in result, "Approved type should not appear when proposed exists"

    print("[OK] test_format_entity_types_proposed_priority passed")


def test_format_entity_types_fallback_to_approved():
    """Test fallback to approved when no proposed exists."""
    state = {
        "approved_entity_types": {
            "Product": {"source": "well_known", "description": "Products"},
            "Issue": {"source": "discovered", "description": "Issues found"},
        },
    }

    result = _format_entity_types(state)

    assert "Product" in result, "Approved Product should appear"
    assert "Issue" in result, "Approved Issue should appear"
    assert "well_known" in result, "Source should be included"

    print("[OK] test_format_entity_types_fallback_to_approved passed")


def test_format_entity_types_empty():
    """Test empty state returns '(none)'."""
    state = {}

    result = _format_entity_types(state)

    assert result == "(none)", f"Expected '(none)', got '{result}'"

    print("[OK] test_format_entity_types_empty passed")


def test_format_fact_types_formatting():
    """Test fact types are formatted as (Subject)-[predicate]->(Object)."""
    state = {
        "proposed_fact_types": {
            "has_issue": {
                "subject_label": "Product",
                "predicate_label": "has_issue",
                "object_label": "Issue",
            },
            "has_feature": {
                "subject_label": "Product",
                "predicate_label": "has_feature",
                "object_label": "Feature",
            },
        }
    }

    result = _format_fact_types(state)

    assert "(Product)-[has_issue]->(Issue)" in result, "has_issue triple not formatted correctly"
    assert "(Product)-[has_feature]->(Feature)" in result, "has_feature triple not formatted correctly"

    print("[OK] test_format_fact_types_formatting passed")


def test_format_fact_types_none():
    """Test empty state returns the 'none' message."""
    state = {}

    result = _format_fact_types(state)

    assert "none" in result, f"Expected 'none' in result, got '{result}'"

    print("[OK] test_format_fact_types_none passed")


def test_format_fact_types_fallback_to_approved():
    """Test fallback to approved when no proposed exists."""
    state = {
        "approved_fact_types": {
            "has_issue": {
                "subject_label": "Product",
                "predicate_label": "has_issue",
                "object_label": "Issue",
            },
        }
    }

    result = _format_fact_types(state)

    assert "(Product)-[has_issue]->(Issue)" in result, "Should use approved fact types"

    print("[OK] test_format_fact_types_fallback_to_approved passed")


if __name__ == "__main__":
    print("Running schema critic unit tests...\n")

    test_build_file_context_structured_scope()
    test_build_file_context_all_scope()
    test_build_file_context_default_scope()
    test_format_entity_types_proposed_priority()
    test_format_entity_types_fallback_to_approved()
    test_format_entity_types_empty()
    test_format_fact_types_formatting()
    test_format_fact_types_none()
    test_format_fact_types_fallback_to_approved()

    print("\n=== All tests passed! ===")
