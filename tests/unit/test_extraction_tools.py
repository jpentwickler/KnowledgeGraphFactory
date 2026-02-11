"""Unit tests for extraction tool handlers (NER & Fact Extraction)."""

import copy
import os
import tempfile

from tools.extraction_tools import (
    handle_set_proposed_entities,
    handle_get_proposed_entities,
    handle_approve_proposed_entities,
    handle_search_files,
    handle_add_proposed_fact,
    handle_remove_proposed_fact,
    handle_get_proposed_facts,
    handle_approve_proposed_facts,
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
            "grounding_evidence": {
                "search_patterns": ["issue", "problem"],
                "total_mentions": 14,
                "example_excerpts": ["The issue was obvious"],
                "files_with_evidence": 2,
            },
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
    assert (
        "grounding_evidence" in state["proposed_entity_types"]["Issue"]
    ), "Issue should have grounding_evidence"
    assert (
        state["proposed_entity_types"]["Issue"]["grounding_evidence"]["total_mentions"] == 14
    ), "Issue evidence total_mentions incorrect"
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


def test_search_files_basic():
    """Test basic pattern search returns matches with context."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["KG_DATA_DIR"] = tmpdir

        file1 = os.path.join(tmpdir, "reviews.md")
        with open(file1, "w", encoding="utf-8") as f:
            f.write("# Product Reviews\n")
            f.write("The KALLAX shelf is great.\n")
            f.write("However the warranty is unclear.\n")
            f.write("I contacted support about it.\n")

        state = {
            "approved_files": {
                "unstructured": [
                    {"path": "reviews.md", "reason": "Product reviews"},
                ]
            }
        }

        result = handle_search_files(state, pattern="warranty")

        assert result["status"] == "success", f"Expected success, got {result}"
        assert result["match_count"] == 1, f"Expected 1 match, got {result['match_count']}"
        assert result["matches"][0]["file"] == "reviews.md"
        assert result["matches"][0]["line_number"] == 3
        assert "warranty" in result["matches"][0]["context"].lower()
    print("[OK] test_search_files_basic passed")


def test_search_files_no_matches():
    """Test search with no results returns empty list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["KG_DATA_DIR"] = tmpdir

        file1 = os.path.join(tmpdir, "reviews.md")
        with open(file1, "w", encoding="utf-8") as f:
            f.write("# Product Reviews\n")
            f.write("The shelf is great.\n")

        state = {
            "approved_files": {
                "unstructured": [
                    {"path": "reviews.md", "reason": "Reviews"},
                ]
            }
        }

        result = handle_search_files(state, pattern="nonexistent_term_xyz")

        assert result["status"] == "success", f"Expected success, got {result}"
        assert result["match_count"] == 0, f"Expected 0 matches, got {result['match_count']}"
        assert result["matches"] == []
    print("[OK] test_search_files_no_matches passed")


def test_search_files_specific_file():
    """Test file_path filters to a single file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["KG_DATA_DIR"] = tmpdir

        with open(os.path.join(tmpdir, "file1.md"), "w", encoding="utf-8") as f:
            f.write("warranty info here\n")
        with open(os.path.join(tmpdir, "file2.md"), "w", encoding="utf-8") as f:
            f.write("warranty info there\n")

        state = {
            "approved_files": {
                "unstructured": [
                    {"path": "file1.md", "reason": "File 1"},
                    {"path": "file2.md", "reason": "File 2"},
                ]
            }
        }

        result = handle_search_files(state, pattern="warranty", file_path="file1.md")

        assert result["status"] == "success"
        assert result["files_searched"] == ["file1.md"]
        assert result["match_count"] == 1
        assert result["matches"][0]["file"] == "file1.md"
    print("[OK] test_search_files_specific_file passed")


def test_search_files_case_insensitive():
    """Test case-insensitive matching."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["KG_DATA_DIR"] = tmpdir

        file1 = os.path.join(tmpdir, "reviews.md")
        with open(file1, "w", encoding="utf-8") as f:
            f.write("The Product is excellent.\n")
            f.write("Another PRODUCT arrived.\n")
            f.write("This product works fine.\n")

        state = {
            "approved_files": {
                "unstructured": [
                    {"path": "reviews.md", "reason": "Reviews"},
                ]
            }
        }

        result = handle_search_files(state, pattern="product")

        assert result["status"] == "success"
        assert result["match_count"] == 3, f"Expected 3 matches, got {result['match_count']}"
    print("[OK] test_search_files_case_insensitive passed")


def test_search_files_max_matches():
    """Test that matches are capped at 20."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["KG_DATA_DIR"] = tmpdir

        file1 = os.path.join(tmpdir, "big.md")
        with open(file1, "w", encoding="utf-8") as f:
            for i in range(100):
                f.write(f"Line {i} mentions warranty\n")

        state = {
            "approved_files": {
                "unstructured": [
                    {"path": "big.md", "reason": "Big file"},
                ]
            }
        }

        result = handle_search_files(state, pattern="warranty")

        assert result["status"] == "success"
        assert result["match_count"] == 20, f"Expected 20 (cap), got {result['match_count']}"
    print("[OK] test_search_files_max_matches passed")


def test_set_proposed_entities_with_evidence():
    """Test that grounding evidence fields are stored correctly."""
    state = {}
    evidence = {
        "search_patterns": ["defect", "defective", "flaw"],
        "total_mentions": 23,
        "example_excerpts": [
            "The defect was obvious upon opening",
            "Manufacturing defect caused the leg to crack",
            "Multiple defects in a single order",
        ],
        "files_with_evidence": 2,
    }
    entity_types = [
        {
            "name": "Defect",
            "source": "discovered",
            "description": "Product defects reported by customers",
            "grounding_evidence": evidence,
        },
    ]

    result = handle_set_proposed_entities(state, entity_types)

    assert result["status"] == "success", f"Expected success, got {result}"
    stored = state["proposed_entity_types"]["Defect"]
    assert "grounding_evidence" in stored, "Evidence not stored"
    ev = stored["grounding_evidence"]
    assert ev["search_patterns"] == ["defect", "defective", "flaw"]
    assert ev["total_mentions"] == 23
    assert len(ev["example_excerpts"]) == 3
    assert ev["files_with_evidence"] == 2
    print("[OK] test_set_proposed_entities_with_evidence passed")


def test_set_proposed_entities_without_evidence():
    """Test that grounding evidence is optional (well-known types don't need it)."""
    state = {}
    entity_types = [
        {
            "name": "Product",
            "source": "well_known",
            "description": "Products from the graph schema",
        },
        {
            "name": "Supplier",
            "source": "well_known",
            "description": "Suppliers from the graph schema",
        },
    ]

    result = handle_set_proposed_entities(state, entity_types)

    assert result["status"] == "success", f"Expected success, got {result}"
    assert len(state["proposed_entity_types"]) == 2
    assert "grounding_evidence" not in state["proposed_entity_types"]["Product"]
    assert "grounding_evidence" not in state["proposed_entity_types"]["Supplier"]
    print("[OK] test_set_proposed_entities_without_evidence passed")


# ---------------------------------------------------------------------------
# Fact Type Handler Tests
# ---------------------------------------------------------------------------


def _make_fact_state():
    """Create a state with approved entity types for fact tests."""
    return {
        "approved_entity_types": {
            "Product": {"source": "well_known", "description": "Products"},
            "Issue": {"source": "discovered", "description": "Quality issues"},
            "Customer": {"source": "discovered", "description": "Customers"},
        }
    }


def test_add_proposed_fact_success():
    """Test adding a valid fact type."""
    state = _make_fact_state()

    result = handle_add_proposed_fact(
        state,
        subject_label="Product",
        predicate_label="has_issue",
        object_label="Issue",
    )

    assert result["status"] == "success", f"Expected success, got {result}"
    assert "proposed_fact_types" in state, "State missing proposed_fact_types"
    fact = state["proposed_fact_types"]["has_issue"]
    assert fact["subject_label"] == "Product"
    assert fact["predicate_label"] == "has_issue"
    assert fact["object_label"] == "Issue"
    print("[OK] test_add_proposed_fact_success passed")


def test_add_proposed_fact_invalid_subject():
    """Test rejecting a subject not in approved entity types."""
    state = _make_fact_state()

    result = handle_add_proposed_fact(
        state,
        subject_label="UnknownType",
        predicate_label="has_issue",
        object_label="Issue",
    )

    assert result["status"] == "error", "Expected error for invalid subject"
    assert "UnknownType" in result["message"], "Error should mention the invalid type"
    assert "proposed_fact_types" not in state, "State should not be modified"
    print("[OK] test_add_proposed_fact_invalid_subject passed")


def test_add_proposed_fact_invalid_object():
    """Test rejecting an object not in approved entity types."""
    state = _make_fact_state()

    result = handle_add_proposed_fact(
        state,
        subject_label="Product",
        predicate_label="has_issue",
        object_label="NonExistent",
    )

    assert result["status"] == "error", "Expected error for invalid object"
    assert "NonExistent" in result["message"], "Error should mention the invalid type"
    assert "proposed_fact_types" not in state, "State should not be modified"
    print("[OK] test_add_proposed_fact_invalid_object passed")


def test_add_proposed_fact_invalid_predicate():
    """Test rejecting predicates with uppercase or spaces."""
    state = _make_fact_state()

    # Uppercase
    result = handle_add_proposed_fact(
        state,
        subject_label="Product",
        predicate_label="HasIssue",
        object_label="Issue",
    )
    assert result["status"] == "error", "Expected error for uppercase predicate"
    assert "lowercase" in result["message"].lower(), "Error should mention lowercase"

    # Spaces
    result = handle_add_proposed_fact(
        state,
        subject_label="Product",
        predicate_label="has issue",
        object_label="Issue",
    )
    assert result["status"] == "error", "Expected error for predicate with spaces"

    assert "proposed_fact_types" not in state, "State should not be modified"
    print("[OK] test_add_proposed_fact_invalid_predicate passed")


def test_remove_proposed_fact_success():
    """Test removing an existing proposed fact type."""
    state = _make_fact_state()
    state["proposed_fact_types"] = {
        "has_issue": {
            "subject_label": "Product",
            "predicate_label": "has_issue",
            "object_label": "Issue",
        },
        "reported_by": {
            "subject_label": "Issue",
            "predicate_label": "reported_by",
            "object_label": "Customer",
        },
    }

    result = handle_remove_proposed_fact(state, predicate_label="has_issue")

    assert result["status"] == "success", f"Expected success, got {result}"
    assert "has_issue" not in state["proposed_fact_types"], "Fact should be removed"
    assert len(state["proposed_fact_types"]) == 1, "Should have 1 remaining"
    print("[OK] test_remove_proposed_fact_success passed")


def test_remove_proposed_fact_not_found():
    """Test removing a non-existent predicate returns error."""
    state = _make_fact_state()
    state["proposed_fact_types"] = {}

    result = handle_remove_proposed_fact(state, predicate_label="nonexistent")

    assert result["status"] == "error", "Expected error for missing predicate"
    assert "nonexistent" in result["message"], "Error should mention the predicate"
    print("[OK] test_remove_proposed_fact_not_found passed")


def test_get_proposed_facts_empty():
    """Test getting facts from empty state returns empty dict."""
    state = _make_fact_state()

    result = handle_get_proposed_facts(state)

    assert result["status"] == "success", f"Expected success, got {result}"
    assert result["proposed_fact_types"] == {}, "Expected empty dict"
    assert result["count"] == 0, "Expected count 0"
    print("[OK] test_get_proposed_facts_empty passed")


def test_approve_proposed_facts_success():
    """Test successful approval deep copies proposed to approved."""
    state = _make_fact_state()
    state["proposed_fact_types"] = {
        "has_issue": {
            "subject_label": "Product",
            "predicate_label": "has_issue",
            "object_label": "Issue",
        },
    }

    result = handle_approve_proposed_facts(state)

    assert result["status"] == "success", f"Expected success, got {result}"
    assert "approved_fact_types" in state, "approved_fact_types missing"
    assert "has_issue" in state["approved_fact_types"], "Fact not in approved"

    # Verify deep copy (not shared reference)
    state["proposed_fact_types"]["new_fact"] = {"subject_label": "X"}
    assert "new_fact" not in state["approved_fact_types"], "Should be independent"
    print("[OK] test_approve_proposed_facts_success passed")


def test_approve_proposed_facts_no_proposal():
    """Test approving when no proposal exists returns error."""
    state = _make_fact_state()

    result = handle_approve_proposed_facts(state)

    assert result["status"] == "error", "Expected error when no proposal"
    assert "approved_fact_types" not in state, "State should not be modified"
    print("[OK] test_approve_proposed_facts_no_proposal passed")


if __name__ == "__main__":
    print("Running extraction tools unit tests...\n")

    # NER tests
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
    test_search_files_basic()
    test_search_files_no_matches()
    test_search_files_specific_file()
    test_search_files_case_insensitive()
    test_search_files_max_matches()
    test_set_proposed_entities_with_evidence()
    test_set_proposed_entities_without_evidence()

    # Fact type tests
    test_add_proposed_fact_success()
    test_add_proposed_fact_invalid_subject()
    test_add_proposed_fact_invalid_object()
    test_add_proposed_fact_invalid_predicate()
    test_remove_proposed_fact_success()
    test_remove_proposed_fact_not_found()
    test_get_proposed_facts_empty()
    test_approve_proposed_facts_success()
    test_approve_proposed_facts_no_proposal()

    print("\n=== All tests passed! ===")
