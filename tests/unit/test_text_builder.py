"""Unit tests for Text Graph Builder and Entity Resolution utilities.

Tests pure functions that don't require Neo4j or OpenAI connections.
"""

import os
import sys
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipelines.text_builder import build_entity_schema, _resolve_files_to_process
from pipelines.entity_resolution import normalize_key, correlate_entity_and_domain_keys


# -- Fixtures --


def _make_state(
    entity_types=None,
    fact_types=None,
    unstructured_files=None,
    processed_files=None,
):
    """Build a test state dict."""
    state = {}
    if entity_types is not None:
        state["approved_entity_types"] = entity_types
    if fact_types is not None:
        state["approved_fact_types"] = fact_types
    if unstructured_files is not None:
        state["approved_files"] = {
            "unstructured": [{"path": f} for f in unstructured_files]
        }
    if processed_files is not None:
        state["text_graph_progress"] = {
            "processed_files": [{"file": f} for f in processed_files],
            "pending_files": [],
        }
    return state


# -- build_entity_schema tests --


class TestBuildEntitySchema:
    def test_basic_schema(self):
        """Build schema from entity types and fact types."""
        state = _make_state(
            entity_types={
                "Product": {"source": "well_known"},
                "Issue": {"source": "discovered"},
                "Feature": {"source": "discovered"},
            },
            fact_types={
                "has_issue": {
                    "subject_label": "Product",
                    "predicate_label": "has_issue",
                    "object_label": "Issue",
                },
                "includes_feature": {
                    "subject_label": "Product",
                    "predicate_label": "includes_feature",
                    "object_label": "Feature",
                },
            },
        )
        schema = build_entity_schema(state)

        assert schema["node_types"] == ["Feature", "Issue", "Product"]
        assert schema["relationship_types"] == ["HAS_ISSUE", "INCLUDES_FEATURE"]
        assert ["Product", "HAS_ISSUE", "Issue"] in schema["patterns"]
        assert ["Product", "INCLUDES_FEATURE", "Feature"] in schema["patterns"]
        assert schema["additional_node_types"] is False

    def test_empty_facts(self):
        """Schema with entities but no fact types."""
        state = _make_state(
            entity_types={"Product": {}, "Location": {}},
            fact_types={},
        )
        schema = build_entity_schema(state)

        assert schema["node_types"] == ["Location", "Product"]
        assert schema["relationship_types"] == []
        assert schema["patterns"] == []

    def test_missing_state_keys(self):
        """Schema from empty state returns empty lists."""
        schema = build_entity_schema({})
        assert schema["node_types"] == []
        assert schema["relationship_types"] == []
        assert schema["patterns"] == []
        assert schema["additional_node_types"] is False


# -- _resolve_files_to_process tests --


class TestResolveFiles:
    FILES = [
        "reviews/gothenburg_table_reviews.md",
        "reviews/malmo_desk_reviews.md",
        "reviews/stockholm_chair_reviews.md",
    ]

    def test_all_files(self):
        """Message='all' returns all unprocessed files."""
        state = _make_state(unstructured_files=self.FILES)
        result = _resolve_files_to_process(state, "all")
        assert result == self.FILES

    def test_remaining_files(self):
        """Message='remaining' returns all pending files."""
        state = _make_state(unstructured_files=self.FILES)
        result = _resolve_files_to_process(state, "remaining")
        assert result == self.FILES

    def test_specific_file(self):
        """Message with filename returns just that file."""
        state = _make_state(unstructured_files=self.FILES)
        result = _resolve_files_to_process(state, "process gothenburg_table_reviews.md")
        assert result == ["reviews/gothenburg_table_reviews.md"]

    def test_specific_file_no_extension(self):
        """Message with filename without extension."""
        state = _make_state(unstructured_files=self.FILES)
        result = _resolve_files_to_process(state, "process gothenburg_table_reviews")
        assert result == ["reviews/gothenburg_table_reviews.md"]

    def test_next_file(self):
        """Message='next' returns the first unprocessed file."""
        state = _make_state(
            unstructured_files=self.FILES,
            processed_files=["reviews/gothenburg_table_reviews.md"],
        )
        result = _resolve_files_to_process(state, "next")
        assert result == ["reviews/malmo_desk_reviews.md"]

    def test_next_file_none_processed(self):
        """Message='next' with nothing processed returns first file."""
        state = _make_state(unstructured_files=self.FILES)
        result = _resolve_files_to_process(state, "next")
        assert result == ["reviews/gothenburg_table_reviews.md"]

    def test_all_already_processed(self):
        """All files already processed returns empty list."""
        state = _make_state(
            unstructured_files=self.FILES,
            processed_files=self.FILES,
        )
        result = _resolve_files_to_process(state, "all")
        assert result == []

    def test_specific_already_processed(self):
        """Specific file already processed returns empty list."""
        state = _make_state(
            unstructured_files=self.FILES,
            processed_files=["reviews/gothenburg_table_reviews.md"],
        )
        result = _resolve_files_to_process(
            state, "process gothenburg_table_reviews.md"
        )
        assert result == []

    def test_no_unstructured_files(self):
        """No unstructured files returns empty list."""
        state = _make_state(unstructured_files=[])
        result = _resolve_files_to_process(state, "all")
        assert result == []

    def test_empty_message(self):
        """Empty message returns all pending (default behavior)."""
        state = _make_state(unstructured_files=self.FILES)
        result = _resolve_files_to_process(state, "")
        assert result == self.FILES


# -- normalize_key tests --


class TestNormalizeKey:
    def test_strip_label_prefix_underscore(self):
        assert normalize_key("Product", "Product_name") == "name"

    def test_strip_label_prefix_space(self):
        assert normalize_key("Product", "Product Name") == "name"

    def test_lowercase_prefix(self):
        assert normalize_key("Product", "product name") == "name"

    def test_no_prefix(self):
        assert normalize_key("Product", "price") == "price"

    def test_preserve_non_prefix(self):
        assert normalize_key("Product", "description") == "description"

    def test_whitespace_handling(self):
        assert normalize_key("Product", "  price  ") == "price"


# -- correlate_entity_and_domain_keys tests --


class TestCorrelateKeys:
    def test_exact_match_after_normalization(self):
        """Keys that normalize to the same string should match."""
        result = correlate_entity_and_domain_keys(
            "Product",
            entity_keys=["name"],
            domain_keys=["product_name"],
            similarity=0.9,
        )
        assert len(result) == 1
        assert result[0][0] == "name"
        assert result[0][1] == "product_name"
        assert result[0][2] == 1.0  # Exact match after normalization

    def test_no_match_below_threshold(self):
        """Unrelated keys should not match at high threshold."""
        result = correlate_entity_and_domain_keys(
            "Product",
            entity_keys=["name"],
            domain_keys=["supplier_id"],
            similarity=0.9,
        )
        assert len(result) == 0

    def test_multiple_matches_sorted(self):
        """Multiple matches sorted by score descending."""
        result = correlate_entity_and_domain_keys(
            "Product",
            entity_keys=["name", "description"],
            domain_keys=["product_name", "description", "price"],
            similarity=0.5,
        )
        # Should find name<->product_name and description<->description
        assert len(result) >= 2
        # Best match first
        assert result[0][2] >= result[1][2]

    def test_low_threshold_matches_more(self):
        """Lower threshold finds more matches."""
        result_high = correlate_entity_and_domain_keys(
            "Product",
            entity_keys=["name", "price"],
            domain_keys=["product_name", "unit_price"],
            similarity=0.9,
        )
        result_low = correlate_entity_and_domain_keys(
            "Product",
            entity_keys=["name", "price"],
            domain_keys=["product_name", "unit_price"],
            similarity=0.3,
        )
        assert len(result_low) >= len(result_high)
