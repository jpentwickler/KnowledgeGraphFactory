"""Unit tests for extraction tool handlers (NER & Fact Extraction)."""

import copy
import os
import tempfile

from tools.extraction_tools import (
    handle_set_proposed_entities,
    handle_get_proposed_entities,
    handle_approve_proposed_entities,
    build_structured_preview,
    build_markdown_context,
    build_well_known_types,
)


def test_set_proposed_entities_success():
    """Test setting proposed entities with valid PascalCase names."""
    state = {}
    entity_types = [
        {
            "name": "Product",
            "source": "well_known",
            "description": "Products mentioned in reviews",
        },
        {
            "name": "Issue",
            "source": "discovered",
            "description": "Problems reported by reviewers",
        },
    ]

    result = handle_set_proposed_entities(state, entity_types)

    assert result["status"] == "success", f"Expected success, got {result}"
    assert "proposed_entity_types" in state, "State missing proposed_entity_types"
    assert len(state["proposed_entity_types"]) == 2, "Expected 2 entity types"
    assert "Product" in state["proposed_entity_types"], "Product not found"
    assert "Issue" in state["proposed_entity_types"], "Issue not found"
    assert (
        state["proposed_entity_types"]["Product"]["source"] == "well_known"
    ), "Product source incorrect"
    print("[OK] test_set_proposed_entities_success passed")


def test_set_proposed_entities_invalid_case():
    """Test rejecting lowercase entity names."""
    state = {}
    entity_types = [
        {
            "name": "product",  # lowercase - should fail
            "source": "well_known",
            "description": "Products",
        }
    ]

    result = handle_set_proposed_entities(state, entity_types)

    assert result["status"] == "error", "Expected error for lowercase name"
    assert "PascalCase" in result["message"], "Error message should mention PascalCase"
    assert "proposed_entity_types" not in state, "State should not be modified"
    print("[OK] test_set_proposed_entities_invalid_case passed")


def test_set_proposed_entities_invalid_source():
    """Test rejecting invalid source values."""
    state = {}
    entity_types = [
        {
            "name": "Product",
            "source": "invalid_source",  # not well_known or discovered
            "description": "Products",
        }
    ]

    result = handle_set_proposed_entities(state, entity_types)

    assert result["status"] == "error", "Expected error for invalid source"
    assert "well_known" in result["message"], "Error should mention valid sources"
    assert "proposed_entity_types" not in state, "State should not be modified"
    print("[OK] test_set_proposed_entities_invalid_source passed")


def test_get_proposed_entities_empty():
    """Test getting entities from empty state."""
    state = {}

    result = handle_get_proposed_entities(state)

    assert result["status"] == "success", f"Expected success, got {result}"
    assert result["proposed_entity_types"] == {}, "Expected empty dict"
    print("[OK] test_get_proposed_entities_empty passed")


def test_get_proposed_entities_exists():
    """Test getting existing proposed entities."""
    state = {
        "proposed_entity_types": {
            "Product": {"source": "well_known", "description": "Products"}
        }
    }

    result = handle_get_proposed_entities(state)

    assert result["status"] == "success", f"Expected success, got {result}"
    assert "Product" in result["proposed_entity_types"], "Product not found"
    print("[OK] test_get_proposed_entities_exists passed")


def test_approve_without_proposal():
    """Test approving when no proposal exists."""
    state = {}

    result = handle_approve_proposed_entities(state)

    assert result["status"] == "error", "Expected error when no proposal"
    assert "approved_entity_types" not in state, "State should not be modified"
    print("[OK] test_approve_without_proposal passed")


def test_approve_with_proposal():
    """Test successful approval."""
    state = {
        "proposed_entity_types": {
            "Product": {"source": "well_known", "description": "Products"},
            "Issue": {"source": "discovered", "description": "Issues"},
        }
    }

    result = handle_approve_proposed_entities(state)

    assert result["status"] == "success", f"Expected success, got {result}"
    assert "approved_entity_types" in state, "approved_entity_types missing"
    assert len(state["approved_entity_types"]) == 2, "Expected 2 entity types"

    # Verify deep copy (not shared reference)
    state["proposed_entity_types"]["NewType"] = {
        "source": "discovered",
        "description": "New",
    }
    assert (
        "NewType" not in state["approved_entity_types"]
    ), "Approved should be independent"
    print("[OK] test_approve_with_proposal passed")


def test_build_structured_preview():
    """Test structure-aware markdown preview."""
    # Create a temporary markdown file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write("# First Section\n")
        f.write("Line 1 of first section\n")
        f.write("Line 2 of first section\n")
        f.write("Line 3 of first section\n")
        f.write("Line 4 of first section\n")
        f.write("Line 5 of first section\n")
        f.write("Line 6 of first section (should be truncated)\n")
        f.write("\n")
        f.write("## Second Section\n")
        f.write("Line 1 of second section\n")
        f.write("Line 2 of second section\n")
        temp_path = f.name

    try:
        preview = build_structured_preview(temp_path, lines_per_section=5)

        assert "First Section" in preview, "First heading not found"
        assert "Second Section" in preview, "Second heading not found"
        assert "[line 1]" in preview, "Line numbers not included"
        assert "Line 1 of first section" in preview, "Content not extracted"
        assert (
            "should be truncated" not in preview
        ), "Preview should limit to 5 lines per section"
    finally:
        os.unlink(temp_path)

    print("[OK] test_build_structured_preview passed")


def test_build_markdown_context():
    """Test building context from multiple markdown files."""
    # Create temp markdown files
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set KG_DATA_DIR to temp directory
        os.environ["KG_DATA_DIR"] = tmpdir

        file1 = os.path.join(tmpdir, "file1.md")
        file2 = os.path.join(tmpdir, "file2.md")

        with open(file1, "w", encoding="utf-8") as f:
            f.write("# File 1 Heading\n")
            f.write("Content of file 1\n")

        with open(file2, "w", encoding="utf-8") as f:
            f.write("# File 2 Heading\n")
            f.write("Content of file 2\n")

        state = {
            "approved_files": {
                "unstructured": [
                    {"path": "file1.md", "reason": "Test file 1"},
                    {"path": "file2.md", "reason": "Test file 2"},
                ]
            }
        }

        context = build_markdown_context(state)

        assert "File 1 Heading" in context, "File 1 heading not found"
        assert "File 2 Heading" in context, "File 2 heading not found"
        assert "Content of file 1" in context, "File 1 content not found"
        assert "Content of file 2" in context, "File 2 content not found"

    print("[OK] test_build_markdown_context passed")


def test_build_well_known_types():
    """Test extracting node labels from construction plan."""
    state = {
        "approved_construction_plan": {
            "Product": {"construction_type": "node", "label": "Product"},
            "Supplier": {"construction_type": "node", "label": "Supplier"},
            "SUPPLIED_BY": {
                "construction_type": "relationship",
                "relationship_type": "SUPPLIED_BY",
            },
        }
    }

    result = build_well_known_types(state)

    assert "Product" in result, "Product not found"
    assert "Supplier" in result, "Supplier not found"
    assert "SUPPLIED_BY" not in result, "Relationship should not be included"
    print("[OK] test_build_well_known_types passed")


if __name__ == "__main__":
    print("Running extraction tools unit tests...\n")

    test_set_proposed_entities_success()
    test_set_proposed_entities_invalid_case()
    test_set_proposed_entities_invalid_source()
    test_get_proposed_entities_empty()
    test_get_proposed_entities_exists()
    test_approve_without_proposal()
    test_approve_with_proposal()
    test_build_structured_preview()
    test_build_markdown_context()
    test_build_well_known_types()

    print("\n=== All tests passed! ===")
