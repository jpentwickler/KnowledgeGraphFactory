"""Unit tests for Jaro-Winkler-based entity resolution.

Tests normalize_key, correlate_entity_and_domain_keys, and resolve_entities().
"""

from unittest.mock import MagicMock, patch

import pytest

from pipelines.entity_resolution import (
    JAROWINKLER_AUTO_RESOLVE,
    JAROWINKLER_CANDIDATE_LOW,
    correlate_entity_and_domain_keys,
    normalize_key,
    resolve_entities,
)


# ---------------------------------------------------------------------------
# normalize_key
# ---------------------------------------------------------------------------


class TestNormalizeKey:
    def test_strips_label_prefix(self):
        """Label prefix is removed from key."""
        assert normalize_key("Product", "product_name") == "name"

    def test_strips_label_prefix_with_space(self):
        """Label prefix with space separator is removed."""
        assert normalize_key("Product", "product name") == "name"

    def test_lowercase(self):
        """Output is always lowercase."""
        assert normalize_key("Product", "Name") == "name"

    def test_no_prefix_passthrough(self):
        """Key without label prefix is returned as-is (lowercased)."""
        assert normalize_key("Product", "price") == "price"

    def test_internal_space_to_underscore(self):
        """Spaces in key body become underscores."""
        assert normalize_key("Product", "unit price") == "unit_price"

    def test_strips_surrounding_whitespace(self):
        """Leading/trailing whitespace is stripped."""
        assert normalize_key("Product", "  name  ") == "name"

    def test_empty_key(self):
        """Empty key returns empty string."""
        assert normalize_key("Product", "") == ""


# ---------------------------------------------------------------------------
# correlate_entity_and_domain_keys
# ---------------------------------------------------------------------------


class TestCorrelateEntityAndDomainKeys:
    def test_exact_match_after_normalization(self):
        """Identical keys after normalization score 1.0."""
        result = correlate_entity_and_domain_keys(
            "Product", ["product_name"], ["name"], similarity=0.9
        )
        assert len(result) == 1
        entity_key, domain_key, score = result[0]
        assert entity_key == "product_name"
        assert domain_key == "name"
        assert score == pytest.approx(1.0)

    def test_no_match_below_threshold(self):
        """Pairs below threshold are excluded."""
        result = correlate_entity_and_domain_keys(
            "Product", ["completely_different"], ["name"], similarity=0.9
        )
        assert result == []

    def test_sorted_by_score_descending(self):
        """Results are sorted highest score first."""
        result = correlate_entity_and_domain_keys(
            "Product",
            ["product_name", "product_title"],
            ["name"],
            similarity=0.5,
        )
        assert len(result) >= 1
        scores = [r[2] for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_multiple_keys_best_pair_first(self):
        """With multiple entity keys, the best-matching pair appears first."""
        result = correlate_entity_and_domain_keys(
            "Product",
            ["product_name", "product_category"],
            ["name"],
            similarity=0.5,
        )
        # "product_name" normalizes to "name" — perfect match; should be first
        assert result[0][0] == "product_name"


# ---------------------------------------------------------------------------
# resolve_entities
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_driver():
    return MagicMock()


class TestResolveEntities:
    def test_no_entity_labels_returns_empty(self, mock_driver):
        """If no entity labels found, return empty results."""
        with patch("pipelines.entity_resolution.find_unique_entity_labels", return_value=[]):
            results = resolve_entities({}, mock_driver)
        assert results["labels_checked"] == []
        assert results["total_correspondences"] == 0

    def test_no_domain_nodes_skips_label(self, mock_driver):
        """Label with no domain nodes gets status 'no_domain_match'."""
        with patch("pipelines.entity_resolution.find_unique_entity_labels", return_value=["Widget"]), \
             patch("pipelines.entity_resolution.find_unique_entity_keys", return_value=["name"]), \
             patch("pipelines.entity_resolution.find_unique_domain_keys", return_value=[]):
            results = resolve_entities({}, mock_driver)

        assert results["per_label_results"][0]["status"] == "no_domain_match"
        assert results["total_correspondences"] == 0

    def test_no_entity_keys_skips_label(self, mock_driver):
        """Label with no entity property keys gets status 'no_entity_nodes'."""
        with patch("pipelines.entity_resolution.find_unique_entity_labels", return_value=["Widget"]), \
             patch("pipelines.entity_resolution.find_unique_domain_keys", return_value=["name"]), \
             patch("pipelines.entity_resolution.find_unique_entity_keys", return_value=[]):
            results = resolve_entities({}, mock_driver)

        assert results["per_label_results"][0]["status"] == "no_entity_nodes"

    def test_no_key_correlation_skips_label(self, mock_driver):
        """Label with no matching keys gets status 'no_key_match'."""
        with patch("pipelines.entity_resolution.find_unique_entity_labels", return_value=["Product"]), \
             patch("pipelines.entity_resolution.find_unique_entity_keys", return_value=["completely_different"]), \
             patch("pipelines.entity_resolution.find_unique_domain_keys", return_value=["sku"]), \
             patch("pipelines.entity_resolution.correlate_entity_and_domain_keys", return_value=[]):
            results = resolve_entities({}, mock_driver)

        assert results["per_label_results"][0]["status"] == "no_key_match"

    def test_resolved_label_counts_correspondences(self, mock_driver):
        """Resolved labels increment total_correspondences."""
        with patch("pipelines.entity_resolution.find_unique_entity_labels", return_value=["Product"]), \
             patch("pipelines.entity_resolution.find_unique_entity_keys", return_value=["name"]), \
             patch("pipelines.entity_resolution.find_unique_domain_keys", return_value=["name"]), \
             patch("pipelines.entity_resolution.correlate_entity_and_domain_keys", return_value=[("name", "name", 1.0)]), \
             patch("pipelines.entity_resolution.correlate_subject_and_domain_nodes", return_value={"label": "Product", "relationships_created": 8}), \
             patch("pipelines.entity_resolution.find_candidate_matches", return_value=[]):
            results = resolve_entities({}, mock_driver)

        assert results["total_correspondences"] == 8
        assert "Product" in results["labels_resolved"]
        lr = results["per_label_results"][0]
        assert lr["status"] == "resolved"
        assert lr["entity_key"] == "name"
        assert lr["domain_key"] == "name"

    def test_candidates_stored_in_state(self, mock_driver):
        """Candidate matches are saved to state['proposed_resolution_candidates']."""
        candidate = {
            "entity_name": "slide",
            "domain_name": "Rail",
            "distance": 0.15,
            "label": "Part",
            "entity_key": "name",
            "domain_key": "name",
        }
        with patch("pipelines.entity_resolution.find_unique_entity_labels", return_value=["Part"]), \
             patch("pipelines.entity_resolution.find_unique_entity_keys", return_value=["name"]), \
             patch("pipelines.entity_resolution.find_unique_domain_keys", return_value=["name"]), \
             patch("pipelines.entity_resolution.correlate_entity_and_domain_keys", return_value=[("name", "name", 1.0)]), \
             patch("pipelines.entity_resolution.correlate_subject_and_domain_nodes", return_value={"label": "Part", "relationships_created": 0}), \
             patch("pipelines.entity_resolution.find_candidate_matches", return_value=[candidate]):
            state = {}
            results = resolve_entities(state, mock_driver)

        assert "proposed_resolution_candidates" in state
        assert state["proposed_resolution_candidates"][0]["entity_name"] == "slide"

    def test_state_updated_on_completion(self, mock_driver):
        """resolve_entities updates text_graph_progress after processing."""
        with patch("pipelines.entity_resolution.find_unique_entity_labels", return_value=["Product"]), \
             patch("pipelines.entity_resolution.find_unique_entity_keys", return_value=["name"]), \
             patch("pipelines.entity_resolution.find_unique_domain_keys", return_value=["name"]), \
             patch("pipelines.entity_resolution.correlate_entity_and_domain_keys", return_value=[("name", "name", 1.0)]), \
             patch("pipelines.entity_resolution.correlate_subject_and_domain_nodes", return_value={"label": "Product", "relationships_created": 5}), \
             patch("pipelines.entity_resolution.find_candidate_matches", return_value=[]):
            state = {}
            resolve_entities(state, mock_driver)

        assert "text_graph_progress" in state
        assert state["text_graph_progress"]["entity_resolution"]["status"] == "completed"
        assert state["text_graph_progress"]["entity_resolution"]["total_correspondences"] == 5

    def test_zero_correspondences_no_match_status(self, mock_driver):
        """Label with 0 CORRESPONDS_TO created gets 'no_matches' status."""
        with patch("pipelines.entity_resolution.find_unique_entity_labels", return_value=["Product"]), \
             patch("pipelines.entity_resolution.find_unique_entity_keys", return_value=["name"]), \
             patch("pipelines.entity_resolution.find_unique_domain_keys", return_value=["name"]), \
             patch("pipelines.entity_resolution.correlate_entity_and_domain_keys", return_value=[("name", "name", 1.0)]), \
             patch("pipelines.entity_resolution.correlate_subject_and_domain_nodes", return_value={"label": "Product", "relationships_created": 0}), \
             patch("pipelines.entity_resolution.find_candidate_matches", return_value=[]):
            results = resolve_entities({}, mock_driver)

        assert results["per_label_results"][0]["status"] == "no_matches"
        assert "Product" not in results["labels_resolved"]
