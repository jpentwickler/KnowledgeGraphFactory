"""
Unit tests for US014: Competency Question Evaluation

Tests:
- Single CQ evaluation logic (7 tests)
- Batch CQ classification (6 tests)
- Batch evaluation & coverage score (4 tests)
- Classification logic (5 tests)
- State persistence (3 tests)
- Error handling (5 tests)
- Priority sorting (3 tests)
- Response formatting (4 tests)
"""

import json
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def _bypass_project_guard():
    """Bypass _check_project_active for all tests in this module."""
    with patch("mcp_server.server._check_project_active", return_value=None):
        yield


# =============================================================================
# Fixtures
# =============================================================================

SAMPLE_CQS = {
    "CQ1": {
        "question": "What products would be affected if supplier X has disruptions?",
        "category": "supply_chain_impact",
        "priority": "high",
    },
    "CQ2": {
        "question": "Which suppliers provide the most components across product lines?",
        "category": "sourcing_optimization",
        "priority": "high",
    },
    "CQ3": {
        "question": "What is the average customer sentiment for products from supplier X?",
        "category": "cross_analysis",
        "priority": "medium",
    },
    "CQ4": {
        "question": "Which locations have the highest delivery delays?",
        "category": "logistics",
        "priority": "low",
    },
}


def _make_state(**overrides):
    """Build a state dict with approved CQs and optional overrides."""
    state = {"approved_competency_questions": dict(SAMPLE_CQS)}
    state.update(overrides)
    return state


def _mock_evidence(count, has_domain=False):
    """Build fake evidence items as returned by _execute_* strategies."""
    items = []
    for i in range(count):
        metadata = {"score": 0.9 - i * 0.1, "source_file": f"doc{i}.md"}
        if has_domain:
            metadata["domain_entity"] = {
                "labels": ["Product"],
                "properties": {"name": f"Product{i}"},
            }
            metadata["domain_label"] = "Product"
        else:
            metadata["domain_entity"] = None
            metadata["domain_label"] = None
        items.append({
            "content": f"Unique evidence content chunk number {i} with enough text to be distinct",
            "score": 0.9 - i * 0.1,
            "metadata": metadata,
        })
    return items


# =============================================================================
# Single CQ Evaluation Logic (6 tests)
# =============================================================================

class TestEvaluateSingleCQ:
    """Tests for the _evaluate_single_cq helper function.

    strategy_result is passed directly as a kwarg — no mocking of
    strategy selection needed. Execution functions in pipelines.query_builder
    are patched because _evaluate_single_cq imports them locally.
    """

    @patch("pipelines.query_builder._execute_cross_layer_traversal")
    def test_primary_strategy_used_when_successful(self, mock_cross):
        """Primary strategy is used and recorded when it returns evidence."""
        from mcp_server.server import _evaluate_single_cq

        mock_cross.return_value = {"evidence": _mock_evidence(3, has_domain=True)}

        result = _evaluate_single_cq(
            MagicMock(), "test question", _make_state(),
            strategy_result={"strategy": "cross_layer", "cypher_query": None},
        )

        assert result["strategies_tried"] == ["cross_layer"]
        assert result["strategy_used"] == "cross_layer"

    @patch("pipelines.query_builder._execute_cross_layer_traversal")
    @patch("pipelines.query_builder._execute_hybrid_search")
    @patch("pipelines.query_builder._execute_vector_search")
    @patch("pipelines.query_builder._execute_cypher")
    def test_fallback_when_primary_fails(
        self, mock_cypher, mock_vector, mock_hybrid, mock_cross
    ):
        """Falls back to semantic strategies when primary strategy fails."""
        from mcp_server.server import _evaluate_single_cq

        mock_cypher.side_effect = RuntimeError("Cypher failed")
        mock_vector.return_value = {"evidence": _mock_evidence(3)}
        mock_hybrid.return_value = {"evidence": []}
        mock_cross.return_value = {"evidence": []}

        result = _evaluate_single_cq(
            MagicMock(), "test question", _make_state(),
            strategy_result={
                "strategy": "cypher",
                "cypher_query": "MATCH (n) RETURN n",
            },
        )

        assert "vector" in result["strategies_tried"]
        assert result["strategy_used"] == "vector"
        assert result["evidence_count"] == 3

    @patch("pipelines.query_builder._execute_cross_layer_traversal")
    @patch("pipelines.query_builder._execute_hybrid_search")
    @patch("pipelines.query_builder._execute_vector_search")
    def test_all_fallbacks_fail_gracefully(
        self, mock_vector, mock_hybrid, mock_cross
    ):
        """All strategies failing returns empty result without error."""
        from mcp_server.server import _evaluate_single_cq

        mock_vector.side_effect = RuntimeError("No OPENAI_API_KEY")
        mock_hybrid.side_effect = RuntimeError("Index not found")
        mock_cross.side_effect = RuntimeError("No domain graph")

        result = _evaluate_single_cq(
            MagicMock(), "test question", _make_state(),
            strategy_result={"strategy": "vector", "cypher_query": None},
        )

        assert result["strategies_tried"] == []
        assert result["evidence_count"] == 0
        assert result["has_cross_layer_bridge"] is False

    @patch("pipelines.query_builder._execute_cross_layer_traversal")
    def test_cross_layer_bridge_detected(self, mock_cross):
        """Cross-layer bridge is detected when domain_entity is present."""
        from mcp_server.server import _evaluate_single_cq

        mock_cross.return_value = {"evidence": _mock_evidence(3, has_domain=True)}

        result = _evaluate_single_cq(
            MagicMock(), "test question", _make_state(),
            strategy_result={"strategy": "cross_layer", "cypher_query": None},
        )

        assert result["has_cross_layer_bridge"] is True

    @patch("pipelines.query_builder._execute_cross_layer_traversal")
    def test_no_cross_layer_bridge_when_no_domain(self, mock_cross):
        """No bridge when cross_layer returns evidence without domain entities."""
        from mcp_server.server import _evaluate_single_cq

        mock_cross.return_value = {"evidence": _mock_evidence(3, has_domain=False)}

        result = _evaluate_single_cq(
            MagicMock(), "test question", _make_state(),
            strategy_result={"strategy": "cross_layer", "cypher_query": None},
        )

        assert result["has_cross_layer_bridge"] is False

    @patch("pipelines.query_builder._execute_cross_layer_traversal")
    @patch("pipelines.query_builder._execute_hybrid_search")
    @patch("pipelines.query_builder._execute_vector_search")
    def test_evidence_deduplication(self, mock_vector, mock_hybrid, mock_cross):
        """Duplicate evidence (same first 100 chars) is deduplicated."""
        from mcp_server.server import _evaluate_single_cq

        # Primary (vector) succeeds; fallbacks not tried
        shared_evidence = _mock_evidence(3)
        mock_vector.return_value = {"evidence": list(shared_evidence)}
        mock_hybrid.return_value = {"evidence": list(shared_evidence)}
        mock_cross.return_value = {"evidence": []}

        result = _evaluate_single_cq(
            MagicMock(), "test question", _make_state(),
            strategy_result={"strategy": "vector", "cypher_query": None},
        )

        assert result["evidence_count"] == 3

    @patch("pipelines.query_builder._execute_cross_layer_traversal")
    @patch("pipelines.query_builder._execute_hybrid_search")
    @patch("pipelines.query_builder._execute_vector_search")
    def test_evidence_capped_at_ten(self, mock_vector, mock_hybrid, mock_cross):
        """Evidence list is capped at 10 items for storage."""
        from mcp_server.server import _evaluate_single_cq

        many_items = [
            {
                "content": f"Completely unique evidence item {i} different from all others",
                "score": 0.9,
                "metadata": {"domain_entity": None},
            }
            for i in range(20)
        ]
        mock_vector.return_value = {"evidence": []}
        mock_hybrid.return_value = {"evidence": many_items[:10]}
        mock_cross.return_value = {"evidence": many_items[10:]}

        result = _evaluate_single_cq(
            MagicMock(), "test question", _make_state(),
            strategy_result={"strategy": "vector", "cypher_query": None},
        )

        assert result["evidence_count"] == 20
        assert len(result["evidence"]) == 10


# =============================================================================
# Batch CQ Classification (6 tests)
# =============================================================================

class TestBatchClassification:
    """Tests for _classify_cqs_batch — the single Claude call that classifies
    all CQs before the evaluation loop."""

    def _mock_api_response(self, payload: dict) -> MagicMock:
        """Build a mock Anthropic API response returning JSON payload."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(payload))]
        return mock_response

    def _make_plan_state(self):
        """Build a state dict with a realistic construction plan including properties."""
        return {
            "approved_construction_plan": {
                "Product": {
                    "construction_type": "node",
                    "label": "Product",
                    "unique_column_name": "product_id",
                    "properties": ["product_name", "price", "description"],
                    "source_file": "products.csv",
                },
                "Supplier": {
                    "construction_type": "node",
                    "label": "Supplier",
                    "unique_column_name": "supplier_id",
                    "properties": ["name", "specialty", "city", "country"],
                    "source_file": "suppliers.csv",
                },
                "SUPPLIES": {
                    "construction_type": "relationship",
                    "relationship_type": "SUPPLIES",
                    "from_node_label": "Supplier",
                    "to_node_label": "Product",
                    "properties": ["lead_time_days"],
                    "source_file": "supplies.csv",
                },
            }
        }

    @patch("anthropic.Anthropic")
    def test_successful_batch_cross_layer(self, mock_anthropic_class):
        """All cross_layer strategies returned correctly."""
        from mcp_server.server import _classify_cqs_batch

        cqs = {
            "CQ1": {"question": "What sentiment do reviews express?"},
            "CQ2": {"question": "Which reviews mention quality issues?"},
        }
        payload = {
            "CQ1": {"strategy": "cross_layer", "cypher_query": None, "reasoning": "semantic"},
            "CQ2": {"strategy": "cross_layer", "cypher_query": None, "reasoning": "semantic"},
        }
        mock_anthropic_class.return_value.messages.create.return_value = (
            self._mock_api_response(payload)
        )

        result = _classify_cqs_batch(cqs, self._make_plan_state())

        assert result["CQ1"]["strategy"] == "cross_layer"
        assert result["CQ2"]["strategy"] == "cross_layer"
        assert result["CQ1"]["cypher_query"] is None

    @patch("anthropic.Anthropic")
    def test_cypher_query_generated_for_structural_cq(self, mock_anthropic_class):
        """Cypher strategy with valid query is preserved."""
        from mcp_server.server import _classify_cqs_batch

        cqs = {"CQ1": {"question": "Which products have the most parts?"}}
        cypher = "MATCH (p:Product)-[:HAS_ASSEMBLY]->(a)-[:HAS_PART]->(pt) WITH p, count(DISTINCT pt) AS n RETURN p.product_name, n ORDER BY n DESC"
        payload = {
            "CQ1": {"strategy": "cypher", "cypher_query": cypher, "reasoning": "aggregation"}
        }
        mock_anthropic_class.return_value.messages.create.return_value = (
            self._mock_api_response(payload)
        )

        result = _classify_cqs_batch(cqs, self._make_plan_state())

        assert result["CQ1"]["strategy"] == "cypher"
        assert result["CQ1"]["cypher_query"] == cypher

    @patch("anthropic.Anthropic")
    def test_unsafe_cypher_downgraded_to_cross_layer(self, mock_anthropic_class):
        """Cypher with mutation keywords is downgraded to cross_layer."""
        from mcp_server.server import _classify_cqs_batch

        cqs = {"CQ1": {"question": "Count suppliers"}}
        payload = {
            "CQ1": {
                "strategy": "cypher",
                "cypher_query": "CREATE (n:Supplier) RETURN n",
                "reasoning": "structural",
            }
        }
        mock_anthropic_class.return_value.messages.create.return_value = (
            self._mock_api_response(payload)
        )

        result = _classify_cqs_batch(cqs, {})

        assert result["CQ1"]["strategy"] == "cross_layer"
        assert result["CQ1"]["cypher_query"] is None

    @patch("anthropic.Anthropic")
    def test_fallback_on_api_error(self, mock_anthropic_class):
        """Returns all cross_layer when Claude API call fails."""
        from mcp_server.server import _classify_cqs_batch

        cqs = {
            "CQ1": {"question": "Q1"},
            "CQ2": {"question": "Q2"},
        }
        mock_anthropic_class.return_value.messages.create.side_effect = (
            Exception("API timeout")
        )

        result = _classify_cqs_batch(cqs, {})

        assert result["CQ1"]["strategy"] == "cross_layer"
        assert result["CQ2"]["strategy"] == "cross_layer"
        assert result["CQ1"]["cypher_query"] is None

    @patch("anthropic.Anthropic")
    def test_fallback_on_json_parse_failure(self, mock_anthropic_class):
        """Returns all cross_layer when response is not valid JSON."""
        from mcp_server.server import _classify_cqs_batch

        cqs = {"CQ1": {"question": "Q1"}, "CQ2": {"question": "Q2"}}
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not JSON at all")]
        mock_anthropic_class.return_value.messages.create.return_value = mock_response

        result = _classify_cqs_batch(cqs, {})

        assert all(v["strategy"] == "cross_layer" for v in result.values())

    @patch("anthropic.Anthropic")
    def test_missing_cq_in_response_gets_fallback(self, mock_anthropic_class):
        """CQ IDs absent from Claude's response receive cross_layer default."""
        from mcp_server.server import _classify_cqs_batch

        cqs = {"CQ1": {"question": "Q1"}, "CQ2": {"question": "Q2"}}
        # Claude only returned CQ1
        payload = {"CQ1": {"strategy": "cross_layer", "cypher_query": None, "reasoning": "ok"}}
        mock_anthropic_class.return_value.messages.create.return_value = (
            self._mock_api_response(payload)
        )

        result = _classify_cqs_batch(cqs, {})

        assert "CQ2" in result
        assert result["CQ2"]["strategy"] == "cross_layer"


# =============================================================================
# Batch Evaluation & Coverage Score (4 tests)
#
# Tests use _run_cq_evaluation (testable implementation without MCP decoration).
# =============================================================================

@patch("mcp_server.server._classify_cqs_batch")
class TestBatchEvaluation:
    """Tests for batch CQ evaluation and coverage score calculation."""

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_all_answerable_coverage_100(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """100% coverage when all CQs are answerable."""
        from mcp_server.server import _run_cq_evaluation

        state = _make_state()
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        mock_eval.return_value = {
            "strategy_used": "cross_layer",
            "strategies_tried": ["cross_layer"],
            "evidence_count": 5,
            "has_cross_layer_bridge": True,
            "evidence": _mock_evidence(5, has_domain=True),
        }

        result = _run_cq_evaluation()

        assert result["status"]["success"] is True
        assert result["status"]["answerable"] == 4
        assert result["status"]["coverage_score"] == 1.0

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_mixed_coverage_score(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """Coverage score with mix of answerable/partial/not_answerable."""
        from mcp_server.server import _run_cq_evaluation

        state = {"approved_competency_questions": {
            "CQ1": {"question": "Q1", "category": "c", "priority": "high"},
            "CQ2": {"question": "Q2", "category": "c", "priority": "high"},
            "CQ3": {"question": "Q3", "category": "c", "priority": "medium"},
            "CQ4": {"question": "Q4", "category": "c", "priority": "low"},
        }}
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        # CQ1: answerable (5 evidence + bridge)
        # CQ2: partial (2 evidence, no bridge)
        # CQ3: partial (1 evidence, no bridge)
        # CQ4: not_answerable (0 evidence)
        call_count = [0]
        results_sequence = [
            {"strategy_used": "cross_layer", "strategies_tried": ["cross_layer"], "evidence_count": 5, "has_cross_layer_bridge": True, "evidence": []},
            {"strategy_used": "vector", "strategies_tried": ["vector"], "evidence_count": 2, "has_cross_layer_bridge": False, "evidence": []},
            {"strategy_used": "hybrid", "strategies_tried": ["hybrid"], "evidence_count": 1, "has_cross_layer_bridge": False, "evidence": []},
            {"strategy_used": "vector", "strategies_tried": [], "evidence_count": 0, "has_cross_layer_bridge": False, "evidence": []},
        ]

        def side_effect(*args, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            return results_sequence[idx]

        mock_eval.side_effect = side_effect

        result = _run_cq_evaluation()

        assert result["status"]["answerable"] == 1
        assert result["status"]["partial"] == 2
        assert result["status"]["not_answerable"] == 1
        # (1 + 0.5*2) / 4 = 2/4 = 0.5
        assert result["status"]["coverage_score"] == 0.5

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_all_not_answerable_coverage_0(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """0% coverage when no CQs have evidence."""
        from mcp_server.server import _run_cq_evaluation

        state = _make_state()
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        mock_eval.return_value = {
            "strategy_used": "vector",
            "strategies_tried": [],
            "evidence_count": 0,
            "has_cross_layer_bridge": False,
            "evidence": [],
        }

        result = _run_cq_evaluation()

        assert result["status"]["not_answerable"] == 4
        assert result["status"]["coverage_score"] == 0.0

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_subset_evaluation(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """Subset evaluation only evaluates specified CQs."""
        from mcp_server.server import _run_cq_evaluation

        state = _make_state()
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        mock_eval.return_value = {
            "strategy_used": "vector",
            "strategies_tried": ["vector"],
            "evidence_count": 3,
            "has_cross_layer_bridge": True,
            "evidence": [],
        }

        result = _run_cq_evaluation(cq_ids=["CQ1", "CQ3"])

        assert result["status"]["total"] == 2
        assert mock_eval.call_count == 2


# =============================================================================
# Classification Logic (4 tests)
# =============================================================================

@patch("mcp_server.server._classify_cqs_batch")
class TestClassificationLogic:
    """Tests for answerable/partial/not_answerable classification."""

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_answerable_requires_both_conditions(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """Answerable requires evidence_count > 2 AND has_cross_layer_bridge."""
        from mcp_server.server import _run_cq_evaluation

        state = {"approved_competency_questions": {
            "CQ1": {"question": "Q1", "category": "c", "priority": "high"},
        }}
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        mock_eval.return_value = {
            "strategy_used": "cross_layer",
            "strategies_tried": ["cross_layer"],
            "evidence_count": 5,
            "has_cross_layer_bridge": True,
            "evidence": [],
        }

        result = _run_cq_evaluation(cq_id="CQ1")

        assert result["status"]["assessment"]["status"] == "answerable"

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_partial_when_evidence_but_no_bridge(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """Partial when evidence > 0 but no cross-layer bridge."""
        from mcp_server.server import _run_cq_evaluation

        state = {"approved_competency_questions": {
            "CQ1": {"question": "Q1", "category": "c", "priority": "high"},
        }}
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        mock_eval.return_value = {
            "strategy_used": "vector",
            "strategies_tried": ["vector"],
            "evidence_count": 5,
            "has_cross_layer_bridge": False,
            "evidence": [],
        }

        result = _run_cq_evaluation(cq_id="CQ1")

        assert result["status"]["assessment"]["status"] == "partial"

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_partial_when_bridge_but_low_evidence(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """Partial when evidence_count <= 2 even with cross-layer bridge."""
        from mcp_server.server import _run_cq_evaluation

        state = {"approved_competency_questions": {
            "CQ1": {"question": "Q1", "category": "c", "priority": "high"},
        }}
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        mock_eval.return_value = {
            "strategy_used": "cross_layer",
            "strategies_tried": ["cross_layer"],
            "evidence_count": 2,
            "has_cross_layer_bridge": True,
            "evidence": [],
        }

        result = _run_cq_evaluation(cq_id="CQ1")

        assert result["status"]["assessment"]["status"] == "partial"

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_not_answerable_when_zero_evidence(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """Not answerable when evidence_count == 0."""
        from mcp_server.server import _run_cq_evaluation

        state = {"approved_competency_questions": {
            "CQ1": {"question": "Q1", "category": "c", "priority": "high"},
        }}
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        mock_eval.return_value = {
            "strategy_used": "vector",
            "strategies_tried": [],
            "evidence_count": 0,
            "has_cross_layer_bridge": False,
            "evidence": [],
        }

        result = _run_cq_evaluation(cq_id="CQ1")

        assert result["status"]["assessment"]["status"] == "not_answerable"

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_cypher_answerable_without_bridge(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """Cypher strategy with evidence is answerable even without cross-layer bridge."""
        from mcp_server.server import _run_cq_evaluation

        state = {"approved_competency_questions": {
            "CQ1": {"question": "Which products have the most parts?", "category": "c", "priority": "high"},
        }}
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        mock_eval.return_value = {
            "strategy_used": "cypher",
            "strategies_tried": ["cypher"],
            "evidence_count": 7,
            "has_cross_layer_bridge": False,
            "evidence": [{"product_name": "Bed", "part_count": 35}],
        }

        result = _run_cq_evaluation(cq_id="CQ1")

        assert result["status"]["assessment"]["status"] == "answerable"


# =============================================================================
# State Persistence (3 tests)
# =============================================================================

@patch("mcp_server.server._classify_cqs_batch")
class TestStatePersistence:
    """Tests for cq_evaluation_results state structure."""

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_results_stored_in_state(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """Evaluation results are stored in state['cq_evaluation_results']."""
        from mcp_server.server import _run_cq_evaluation

        state = _make_state()
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        mock_eval.return_value = {
            "strategies_tried": ["vector"],
            "evidence_count": 3,
            "has_cross_layer_bridge": True,
            "evidence": [],
        }

        _run_cq_evaluation()

        mock_save.assert_called_once()
        saved_state = mock_save.call_args[0][0]
        assert "cq_evaluation_results" in saved_state

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_results_structure_has_required_fields(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """Stored results have timestamp, totals, coverage_score, per_cq_results."""
        from mcp_server.server import _run_cq_evaluation

        state = _make_state()
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        mock_eval.return_value = {
            "strategies_tried": ["vector"],
            "evidence_count": 1,
            "has_cross_layer_bridge": False,
            "evidence": [],
        }

        _run_cq_evaluation()

        saved_state = mock_save.call_args[0][0]
        results = saved_state["cq_evaluation_results"]

        assert "timestamp" in results
        assert "total" in results
        assert "answerable" in results
        assert "partial" in results
        assert "not_answerable" in results
        assert "coverage_score" in results
        assert "per_cq_results" in results
        assert isinstance(results["per_cq_results"], list)

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_timestamp_is_iso8601(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """Timestamp is in ISO 8601 format."""
        from datetime import datetime
        from mcp_server.server import _run_cq_evaluation

        state = _make_state()
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        mock_eval.return_value = {
            "strategies_tried": [],
            "evidence_count": 0,
            "has_cross_layer_bridge": False,
            "evidence": [],
        }

        _run_cq_evaluation()

        saved_state = mock_save.call_args[0][0]
        ts = saved_state["cq_evaluation_results"]["timestamp"]

        # Should parse as ISO 8601
        parsed = datetime.fromisoformat(ts)
        assert parsed is not None


# =============================================================================
# Error Handling (5 tests)
# =============================================================================

class TestErrorHandling:
    """Tests for error conditions."""

    @patch("mcp_server.server._load_clean_state")
    def test_no_approved_cqs(self, mock_load):
        """Error when no approved competency questions exist."""
        from mcp_server.server import _run_cq_evaluation

        mock_load.return_value = {}

        result = _run_cq_evaluation()

        assert result["status"]["error"] == "no_approved_cqs"
        assert "kg_user_intent" in result["agent_response"]

    @patch("mcp_server.server._load_clean_state")
    def test_cq_id_not_found(self, mock_load):
        """Error when specified CQ ID doesn't exist."""
        from mcp_server.server import _run_cq_evaluation

        mock_load.return_value = _make_state()

        result = _run_cq_evaluation(cq_id="CQ99")

        assert result["status"]["error"] == "cq_not_found"
        assert "CQ99" in result["agent_response"]
        assert "CQ1" in result["agent_response"]

    @patch("mcp_server.server._load_clean_state")
    def test_no_matching_cq_ids(self, mock_load):
        """Error when none of the provided CQ IDs match."""
        from mcp_server.server import _run_cq_evaluation

        mock_load.return_value = _make_state()

        result = _run_cq_evaluation(cq_ids=["CQ98", "CQ99"])

        assert result["status"]["error"] == "cqs_not_found"

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._classify_cqs_batch")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_empty_cq_ids_evaluates_all(
        self, mock_eval, mock_classify, mock_load, mock_save, mock_driver, mock_close
    ):
        """Empty cq_ids list evaluates all CQs."""
        from mcp_server.server import _run_cq_evaluation

        state = _make_state()
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        mock_eval.return_value = {
            "strategies_tried": ["vector"],
            "evidence_count": 1,
            "has_cross_layer_bridge": False,
            "evidence": [],
        }

        # Empty list should be falsy, evaluates all
        result = _run_cq_evaluation(cq_ids=[])

        assert result["status"]["total"] == 4  # All 4 CQs

    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._load_clean_state")
    def test_neo4j_connection_failure(self, mock_load, mock_driver):
        """Actionable error on Neo4j connection failure."""
        from mcp_server.server import _run_cq_evaluation

        mock_load.return_value = _make_state()
        mock_driver.side_effect = Exception("Connection refused")

        result = _run_cq_evaluation()

        assert result["status"]["error"] == "neo4j_connection_failed"
        assert "Neo4j" in result["agent_response"]


# =============================================================================
# Priority Sorting (3 tests)
# =============================================================================

@patch("mcp_server.server._classify_cqs_batch")
class TestPrioritySorting:
    """Tests for result sorting by priority then CQ ID."""

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_results_sorted_by_priority(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """Results are sorted: high > medium > low."""
        from mcp_server.server import _run_cq_evaluation

        state = {"approved_competency_questions": {
            "CQ1": {"question": "Q1", "category": "c", "priority": "low"},
            "CQ2": {"question": "Q2", "category": "c", "priority": "high"},
            "CQ3": {"question": "Q3", "category": "c", "priority": "medium"},
        }}
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        mock_eval.return_value = {
            "strategies_tried": ["vector"],
            "evidence_count": 1,
            "has_cross_layer_bridge": False,
            "evidence": [],
        }

        result = _run_cq_evaluation()

        priorities = [r["priority"] for r in result["results"]]
        assert priorities == ["high", "medium", "low"]

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_same_priority_sorted_by_id(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """CQs with same priority are sorted by ID."""
        from mcp_server.server import _run_cq_evaluation

        state = {"approved_competency_questions": {
            "CQ3": {"question": "Q3", "category": "c", "priority": "high"},
            "CQ1": {"question": "Q1", "category": "c", "priority": "high"},
            "CQ2": {"question": "Q2", "category": "c", "priority": "high"},
        }}
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        mock_eval.return_value = {
            "strategies_tried": [],
            "evidence_count": 0,
            "has_cross_layer_bridge": False,
            "evidence": [],
        }

        result = _run_cq_evaluation()

        cq_ids = [r["cq_id"] for r in result["results"]]
        assert cq_ids == ["CQ1", "CQ2", "CQ3"]

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_full_sort_order(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """Full sort: priority first, then CQ ID within same priority."""
        from mcp_server.server import _run_cq_evaluation

        state = {"approved_competency_questions": {
            "CQ4": {"question": "Q4", "category": "c", "priority": "low"},
            "CQ2": {"question": "Q2", "category": "c", "priority": "high"},
            "CQ3": {"question": "Q3", "category": "c", "priority": "medium"},
            "CQ1": {"question": "Q1", "category": "c", "priority": "high"},
            "CQ5": {"question": "Q5", "category": "c", "priority": "medium"},
        }}
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        mock_eval.return_value = {
            "strategies_tried": [],
            "evidence_count": 0,
            "has_cross_layer_bridge": False,
            "evidence": [],
        }

        result = _run_cq_evaluation()

        cq_ids = [r["cq_id"] for r in result["results"]]
        assert cq_ids == ["CQ1", "CQ2", "CQ3", "CQ5", "CQ4"]


# =============================================================================
# Response Formatting (4 tests)
# =============================================================================

@patch("mcp_server.server._classify_cqs_batch")
class TestResponseFormatting:
    """Tests for response formatting."""

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_single_cq_response_format(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """Single CQ returns detailed assessment."""
        from mcp_server.server import _run_cq_evaluation

        state = _make_state()
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        mock_eval.return_value = {
            "strategies_tried": ["vector", "cross_layer"],
            "evidence_count": 5,
            "has_cross_layer_bridge": True,
            "evidence": [],
        }

        result = _run_cq_evaluation(cq_id="CQ1")

        assert "CQ Assessment: CQ1" in result["agent_response"]
        assert "Status: ANSWERABLE" in result["agent_response"]
        assert "Evidence: 5 items" in result["agent_response"]
        assert "Cross-layer bridge: Yes" in result["agent_response"]
        assert result["status"]["assessment"]["status"] == "answerable"

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_batch_response_has_scorecard(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """Batch evaluation returns coverage scorecard."""
        from mcp_server.server import _run_cq_evaluation

        state = _make_state()
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        mock_eval.return_value = {
            "strategies_tried": ["vector"],
            "evidence_count": 1,
            "has_cross_layer_bridge": False,
            "evidence": [],
        }

        result = _run_cq_evaluation()

        response = result["agent_response"]
        assert "Competency Question Evaluation: 4 questions" in response
        assert "Coverage Score:" in response
        assert "Per-CQ Results:" in response

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_batch_response_uses_icons(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """Batch response uses [OK], [PARTIAL], [FAIL] icons."""
        from mcp_server.server import _run_cq_evaluation

        state = {"approved_competency_questions": {
            "CQ1": {"question": "Answerable question here", "category": "c", "priority": "high"},
            "CQ2": {"question": "Partial question here", "category": "c", "priority": "medium"},
            "CQ3": {"question": "Not answerable question", "category": "c", "priority": "low"},
        }}
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        call_count = [0]
        results_seq = [
            {"strategies_tried": ["vector", "cross_layer"], "evidence_count": 5, "has_cross_layer_bridge": True, "evidence": []},
            {"strategies_tried": ["vector"], "evidence_count": 1, "has_cross_layer_bridge": False, "evidence": []},
            {"strategies_tried": [], "evidence_count": 0, "has_cross_layer_bridge": False, "evidence": []},
        ]

        def side_effect(*args, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            return results_seq[idx]

        mock_eval.side_effect = side_effect

        result = _run_cq_evaluation()

        response = result["agent_response"]
        assert "[OK]" in response
        assert "[PARTIAL]" in response
        assert "[FAIL]" in response

    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server._evaluate_single_cq")
    def test_long_questions_truncated_in_batch(
        self, mock_eval, mock_load, mock_save, mock_driver, mock_close, mock_classify
    ):
        """Long questions are truncated to 60 chars in batch output."""
        from mcp_server.server import _run_cq_evaluation

        long_q = "A" * 100
        state = {"approved_competency_questions": {
            "CQ1": {"question": long_q, "category": "c", "priority": "high"},
        }}
        mock_load.return_value = state
        mock_driver.return_value = MagicMock()

        mock_eval.return_value = {
            "strategies_tried": [],
            "evidence_count": 0,
            "has_cross_layer_bridge": False,
            "evidence": [],
        }

        result = _run_cq_evaluation()

        response = result["agent_response"]
        assert "..." in response
        # Should NOT have the full 100-char question
        assert long_q not in response
