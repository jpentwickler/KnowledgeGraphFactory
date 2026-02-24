"""Unit tests for entity resolution with key name pre-filtering.

Tests that resolve_entities() pre-filters keys by name similarity,
uses the best key pair, and collects candidates for human review.
"""

from unittest.mock import MagicMock, patch

import pytest

from pipelines.entity_resolution import resolve_entities


@pytest.fixture
def mock_driver():
    """Create a mock Neo4j driver."""
    return MagicMock()


class TestPreFilteredResolution:
    """Test that resolve_entities pre-filters keys and uses best pair."""

    @patch("pipelines.entity_resolution.find_candidate_matches", return_value=[])
    @patch("pipelines.entity_resolution.correlate_subject_and_domain_nodes")
    @patch("pipelines.entity_resolution.find_unique_domain_keys")
    @patch("pipelines.entity_resolution.find_unique_entity_keys")
    @patch("pipelines.entity_resolution.find_unique_entity_labels")
    def test_uses_best_key_pair_only(
        self,
        mock_labels,
        mock_entity_keys,
        mock_domain_keys,
        mock_correlate,
        mock_candidates,
        mock_driver,
    ):
        """Only the best correlated key pair triggers a Cypher query."""
        mock_labels.return_value = ["Product"]
        mock_entity_keys.return_value = ["id", "name"]
        mock_domain_keys.return_value = ["product_id", "product_name", "price"]
        mock_correlate.return_value = {"label": "Product", "relationships_created": 5}

        state = {}
        results = resolve_entities(state, mock_driver)

        # Only 1 call — the best pair (id <-> product_id normalizes to id <-> id)
        assert mock_correlate.call_count == 1
        call_args = mock_correlate.call_args
        entity_key = call_args.args[2] if len(call_args.args) > 2 else call_args.kwargs["entity_key"]
        domain_key = call_args.args[3] if len(call_args.args) > 3 else call_args.kwargs["domain_key"]
        # After normalization, id <-> product_id scores 1.0 (both become "id")
        assert entity_key == "id"
        assert domain_key == "product_id"

    @patch("pipelines.entity_resolution.find_candidate_matches", return_value=[])
    @patch("pipelines.entity_resolution.correlate_subject_and_domain_nodes")
    @patch("pipelines.entity_resolution.find_unique_domain_keys")
    @patch("pipelines.entity_resolution.find_unique_entity_keys")
    @patch("pipelines.entity_resolution.find_unique_entity_labels")
    def test_skips_label_when_no_keys_correlate(
        self,
        mock_labels,
        mock_entity_keys,
        mock_domain_keys,
        mock_correlate,
        mock_candidates,
        mock_driver,
    ):
        """Labels with no correlated keys are skipped without Cypher queries."""
        mock_labels.return_value = ["Product"]
        mock_entity_keys.return_value = ["xyz", "abc"]
        mock_domain_keys.return_value = ["quantity", "weight"]

        state = {}
        results = resolve_entities(state, mock_driver)

        # No Cypher queries — keys don't correlate
        assert mock_correlate.call_count == 0
        label_result = results["per_label_results"][0]
        assert label_result["status"] == "no_key_correlation"

    @patch("pipelines.entity_resolution.find_candidate_matches", return_value=[])
    @patch("pipelines.entity_resolution.correlate_subject_and_domain_nodes")
    @patch("pipelines.entity_resolution.find_unique_domain_keys")
    @patch("pipelines.entity_resolution.find_unique_entity_keys")
    @patch("pipelines.entity_resolution.find_unique_entity_labels")
    def test_resolved_result_has_key_info(
        self,
        mock_labels,
        mock_entity_keys,
        mock_domain_keys,
        mock_correlate,
        mock_candidates,
        mock_driver,
    ):
        """Resolved per_label_result includes entity_key, domain_key, and score."""
        mock_labels.return_value = ["Product"]
        mock_entity_keys.return_value = ["name"]
        mock_domain_keys.return_value = ["product_name"]
        mock_correlate.return_value = {"label": "Product", "relationships_created": 10}

        state = {}
        results = resolve_entities(state, mock_driver)

        assert results["total_correspondences"] == 10
        assert "Product" in results["labels_resolved"]

        label_result = results["per_label_results"][0]
        assert label_result["status"] == "resolved"
        assert label_result["entity_key"] == "name"
        assert label_result["domain_key"] == "product_name"
        assert label_result["key_similarity"] > 0.5
        assert label_result["relationships_created"] == 10

    @patch("pipelines.entity_resolution.find_candidate_matches")
    @patch("pipelines.entity_resolution.correlate_subject_and_domain_nodes")
    @patch("pipelines.entity_resolution.find_unique_domain_keys")
    @patch("pipelines.entity_resolution.find_unique_entity_keys")
    @patch("pipelines.entity_resolution.find_unique_entity_labels")
    def test_collects_candidates_from_best_pair(
        self,
        mock_labels,
        mock_entity_keys,
        mock_domain_keys,
        mock_correlate,
        mock_find_candidates,
        mock_driver,
    ):
        """Candidates are collected from the best key pair for human review."""
        mock_labels.return_value = ["Product"]
        mock_entity_keys.return_value = ["name"]
        mock_domain_keys.return_value = ["product_name"]
        mock_correlate.return_value = {"label": "Product", "relationships_created": 8}
        mock_find_candidates.return_value = [
            {"entity_name": "Stokholm Chair", "domain_name": "Stockholm Chair",
             "distance": 0.15, "label": "Product",
             "entity_key": "name", "domain_key": "product_name"},
        ]

        state = {}
        results = resolve_entities(state, mock_driver)

        assert len(results["candidates"]) == 1
        assert results["candidates"][0]["entity_name"] == "Stokholm Chair"
        # Candidates called exactly once (best pair only)
        assert mock_find_candidates.call_count == 1
