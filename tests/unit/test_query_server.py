"""
Unit tests for Query MCP Server (mcp_server/query_server.py)

Tests:
- kg_query implementation (5 tests)
- kg_graph_info implementation (2 tests)
- Driver lifecycle (2 tests)
- State loading (2 tests)
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# =============================================================================
# Fixtures
# =============================================================================

def _reset_module_state():
    """Reset module-level state in query_server between tests."""
    import mcp_server.query_server as qs
    qs._driver = None
    qs._state = {}
    qs._state_loaded = False


# =============================================================================
# TestRunKgQuery (5 tests)
# =============================================================================

class TestRunKgQuery:
    """Tests for _run_kg_query implementation."""

    def setup_method(self):
        _reset_module_state()

    @pytest.mark.asyncio
    @patch("mcp_server.query_server._load_state_once")
    @patch("mcp_server.query_server._get_driver")
    @patch("pipelines.query_builder._select_retrieval_strategy", new_callable=AsyncMock)
    @patch("pipelines.query_builder._execute_schema_query")
    async def test_schema_strategy(self, mock_schema, mock_strategy, mock_driver, mock_state):
        """Routes to _execute_schema_query when strategy is 'schema'."""
        from mcp_server.query_server import _run_kg_query

        mock_driver.return_value = MagicMock()
        mock_state.return_value = {}
        mock_strategy.return_value = {
            "strategy": "schema",
            "parameters": {},
            "reasoning": "User asked about graph structure",
        }
        mock_schema.return_value = {
            "answer": "# Schema\n  - Supplier: 10 nodes",
            "evidence": [{"type": "schema"}],
            "confidence": 1.0,
            "details": {},
        }

        result = await _run_kg_query("What labels exist?")

        assert result["status"]["success"] is True
        assert result["status"]["selected_strategy"] == "schema"
        mock_schema.assert_called_once()

    @pytest.mark.asyncio
    @patch("mcp_server.query_server._load_state_once")
    @patch("mcp_server.query_server._get_driver")
    @patch("pipelines.query_builder._select_retrieval_strategy", new_callable=AsyncMock)
    @patch("pipelines.query_builder._execute_validated_cypher", new_callable=AsyncMock)
    async def test_cypher_strategy(self, mock_validated, mock_strategy, mock_driver, mock_state):
        """Routes to _execute_validated_cypher with generated query."""
        from mcp_server.query_server import _run_kg_query

        mock_driver.return_value = MagicMock()
        mock_state.return_value = {}
        mock_strategy.return_value = {
            "strategy": "cypher",
            "parameters": {"cypher_query": "MATCH (s:Supplier) RETURN s.name LIMIT 5"},
            "reasoning": "Structured query needed",
        }
        mock_validated.return_value = (
            {
                "answer": "Found 5 suppliers",
                "evidence": [{"name": "Supplier A"}],
                "confidence": 0.9,
                "details": {},
            },
            "",  # no correction
        )

        result = await _run_kg_query("List 5 suppliers")

        assert result["status"]["success"] is True
        assert result["status"]["selected_strategy"] == "cypher"
        mock_validated.assert_called_once_with(
            mock_driver.return_value,
            "MATCH (s:Supplier) RETURN s.name LIMIT 5",
            "List 5 suppliers",
            {},
        )

    @pytest.mark.asyncio
    @patch("mcp_server.query_server._load_state_once")
    @patch("mcp_server.query_server._get_driver")
    @patch("pipelines.query_builder._select_retrieval_strategy", new_callable=AsyncMock)
    @patch("pipelines.query_builder._execute_vector_search")
    async def test_vector_strategy(self, mock_vector, mock_strategy, mock_driver, mock_state):
        """Routes to _execute_vector_search for semantic queries."""
        from mcp_server.query_server import _run_kg_query

        mock_driver.return_value = MagicMock()
        mock_state.return_value = {}
        mock_strategy.return_value = {
            "strategy": "vector",
            "parameters": {"top_k": 3},
            "reasoning": "Semantic search best for this question",
        }
        mock_vector.return_value = {
            "answer": "Found relevant chunks",
            "evidence": [{"content": "chunk1"}],
            "confidence": 0.7,
            "details": {},
        }

        result = await _run_kg_query("Tell me about supply chain delays")

        assert result["status"]["success"] is True
        assert result["status"]["selected_strategy"] == "vector"
        mock_vector.assert_called_once_with(
            mock_driver.return_value,
            "Tell me about supply chain delays",
            3,
        )

    @pytest.mark.asyncio
    @patch("mcp_server.query_server._load_state_once")
    @patch("mcp_server.query_server._get_driver")
    @patch("pipelines.query_builder._select_retrieval_strategy", new_callable=AsyncMock)
    async def test_error_returns_failure_status(self, mock_strategy, mock_driver, mock_state):
        """Exception during query returns success=False status."""
        from mcp_server.query_server import _run_kg_query

        mock_driver.return_value = MagicMock()
        mock_state.return_value = {}
        mock_strategy.side_effect = RuntimeError("API timeout")

        result = await _run_kg_query("Some question")

        assert result["status"]["success"] is False
        assert "API timeout" in result["status"]["error"]
        assert result["confidence"] == 0.0
        assert result["evidence"] == []

    @pytest.mark.asyncio
    @patch("mcp_server.query_server._load_state_once")
    @patch("mcp_server.query_server._get_driver")
    @patch("pipelines.query_builder._select_retrieval_strategy", new_callable=AsyncMock)
    @patch("pipelines.query_builder._execute_hybrid_search")
    async def test_context_passed_to_strategy(self, mock_hybrid, mock_strategy, mock_driver, mock_state):
        """Context parameter is forwarded to _select_retrieval_strategy."""
        from mcp_server.query_server import _run_kg_query

        mock_driver.return_value = MagicMock()
        mock_state.return_value = {"some": "state"}
        mock_strategy.return_value = {
            "strategy": "hybrid",
            "parameters": {"top_k": 5},
            "reasoning": "Hybrid best with context",
        }
        mock_hybrid.return_value = {
            "answer": "Results",
            "evidence": [],
            "confidence": 0.6,
            "details": {},
        }

        await _run_kg_query("What about delivery?", context="Previous answer mentioned Supplier A")

        mock_strategy.assert_called_once_with(
            "What about delivery?",
            "Previous answer mentioned Supplier A",
            {"some": "state"},
        )

    @pytest.mark.asyncio
    @patch("mcp_server.query_server._load_state_once")
    @patch("mcp_server.query_server._get_driver")
    @patch("pipelines.query_builder._select_retrieval_strategy", new_callable=AsyncMock)
    @patch("pipelines.query_builder._execute_validated_cypher", new_callable=AsyncMock)
    async def test_cypher_no_violation(self, mock_validated, mock_strategy, mock_driver, mock_state):
        """No violation: result returned without reasoning annotation."""
        from mcp_server.query_server import _run_kg_query

        mock_driver.return_value = MagicMock()
        mock_state.return_value = {}
        mock_strategy.return_value = {
            "strategy": "cypher",
            "parameters": {"cypher_query": "MATCH (s:Supplier) RETURN s.name"},
            "reasoning": "Structured query",
        }
        mock_validated.return_value = (
            {"answer": "OK", "evidence": [], "confidence": 0.8, "details": {}},
            "",  # no correction
        )

        result = await _run_kg_query("List suppliers")

        assert result["status"]["reasoning"] == "Structured query"

    @pytest.mark.asyncio
    @patch("mcp_server.query_server._load_state_once")
    @patch("mcp_server.query_server._get_driver")
    @patch("pipelines.query_builder._select_retrieval_strategy", new_callable=AsyncMock)
    @patch("pipelines.query_builder._execute_validated_cypher", new_callable=AsyncMock)
    async def test_cypher_violation_detected(self, mock_validated, mock_strategy, mock_driver, mock_state):
        """Violation detected: reasoning annotated with correction note."""
        from mcp_server.query_server import _run_kg_query

        mock_driver.return_value = MagicMock()
        mock_state.return_value = {}
        mock_strategy.return_value = {
            "strategy": "cypher",
            "parameters": {"cypher_query": "MATCH ..."},
            "reasoning": "Cypher needed",
        }
        mock_validated.return_value = (
            {"answer": "Corrected results", "evidence": [], "confidence": 0.8, "details": {}},
            "Cross-layer Cypher uses domain rels ['SUPPLIES'] and text rels ['EVALUATES'] without CORRESPONDS_TO bridge",
        )

        result = await _run_kg_query("Which suppliers have complaints?")

        assert "CORRESPONDS_TO" in result["status"]["reasoning"]
        assert "Cypher needed" in result["status"]["reasoning"]

    @pytest.mark.asyncio
    @patch("mcp_server.query_server._load_state_once")
    @patch("mcp_server.query_server._get_driver")
    @patch("pipelines.query_builder._select_retrieval_strategy", new_callable=AsyncMock)
    @patch("pipelines.query_builder._execute_validated_cypher", new_callable=AsyncMock)
    async def test_cypher_regeneration_fails_gracefully(self, mock_validated, mock_strategy, mock_driver, mock_state):
        """Regeneration failure still returns original query result."""
        from mcp_server.query_server import _run_kg_query

        mock_driver.return_value = MagicMock()
        mock_state.return_value = {}
        mock_strategy.return_value = {
            "strategy": "cypher",
            "parameters": {"cypher_query": "MATCH (n)-[:REL]->(m) RETURN n"},
            "reasoning": "Cypher",
        }
        # Empty correction_note means regeneration failed and original was used
        mock_validated.return_value = (
            {"answer": "No results found.", "evidence": [], "confidence": 0.2, "details": {}},
            "",
        )

        result = await _run_kg_query("Some cross-layer question")

        assert result["status"]["success"] is True
        assert result["status"]["reasoning"] == "Cypher"

    @pytest.mark.asyncio
    @patch("mcp_server.query_server._load_state_once")
    @patch("mcp_server.query_server._get_driver")
    @patch("pipelines.query_builder._select_retrieval_strategy", new_callable=AsyncMock)
    @patch("pipelines.query_builder._execute_vector_search")
    async def test_non_cypher_skips_validation(self, mock_vector, mock_strategy, mock_driver, mock_state):
        """Non-cypher strategies skip cross-layer validation entirely."""
        from mcp_server.query_server import _run_kg_query

        mock_driver.return_value = MagicMock()
        mock_state.return_value = {}
        mock_strategy.return_value = {
            "strategy": "vector",
            "parameters": {"top_k": 5},
            "reasoning": "Semantic search",
        }
        mock_vector.return_value = {
            "answer": "Results",
            "evidence": [],
            "confidence": 0.7,
            "details": {},
        }

        result = await _run_kg_query("Tell me about delays")

        assert result["status"]["selected_strategy"] == "vector"
        mock_vector.assert_called_once()


# =============================================================================
# TestRunKgGraphInfo (2 tests)
# =============================================================================

class TestRunKgGraphInfo:
    """Tests for _run_kg_graph_info implementation."""

    def setup_method(self):
        _reset_module_state()

    @patch("mcp_server.query_server._load_state_once")
    @patch("mcp_server.query_server._get_driver")
    @patch("pipelines.query_builder._execute_schema_query")
    def test_returns_schema(self, mock_schema, mock_driver, mock_state):
        """kg_graph_info returns schema summary."""
        from mcp_server.query_server import _run_kg_graph_info

        mock_driver.return_value = MagicMock()
        mock_state.return_value = {}
        mock_schema.return_value = {
            "answer": "# Schema\n  - Supplier: 10 nodes",
            "evidence": [{"type": "schema"}],
            "confidence": 1.0,
            "details": {},
        }

        result = _run_kg_graph_info()

        assert "schema" in result
        assert "evidence" in result
        assert "Schema" in result["schema"]

    @patch("mcp_server.query_server._load_state_once")
    @patch("mcp_server.query_server._get_driver")
    @patch("pipelines.query_builder._execute_schema_query")
    def test_uses_shared_driver(self, mock_schema, mock_driver, mock_state):
        """kg_graph_info uses the shared driver."""
        from mcp_server.query_server import _run_kg_graph_info

        driver = MagicMock()
        mock_driver.return_value = driver
        mock_state.return_value = {"some": "state"}
        mock_schema.return_value = {
            "answer": "Schema",
            "evidence": [],
            "confidence": 1.0,
            "details": {},
        }

        _run_kg_graph_info()

        mock_schema.assert_called_once()
        assert mock_schema.call_args[0][0] == driver


# =============================================================================
# TestDriverLifecycle (2 tests)
# =============================================================================

class TestDriverLifecycle:
    """Tests for lazy driver initialization."""

    def setup_method(self):
        _reset_module_state()

    @patch("mcp_server.query_server.get_neo4j_driver")
    def test_lazy_init(self, mock_factory):
        """Driver is created on first call, not at import time."""
        from mcp_server.query_server import _get_driver
        import mcp_server.query_server as qs

        driver = MagicMock()
        mock_factory.return_value = driver

        assert qs._driver is None
        result = _get_driver()
        assert result == driver
        mock_factory.assert_called_once()

    @patch("mcp_server.query_server.get_neo4j_driver")
    def test_reused_across_calls(self, mock_factory):
        """Driver is created once and reused across calls."""
        from mcp_server.query_server import _get_driver

        driver = MagicMock()
        mock_factory.return_value = driver

        result1 = _get_driver()
        result2 = _get_driver()

        assert result1 is result2
        mock_factory.assert_called_once()


# =============================================================================
# TestStateLoading (2 tests)
# =============================================================================

class TestStateLoading:
    """Tests for _load_state_once."""

    def setup_method(self):
        _reset_module_state()

    @patch("mcp_server.query_server.load_state")
    def test_loads_once(self, mock_load):
        """State file is loaded only once, then cached."""
        from mcp_server.query_server import _load_state_once

        mock_load.return_value = {"approved_construction_plan": {"Supplier": {}}}

        result1 = _load_state_once()
        result2 = _load_state_once()

        mock_load.assert_called_once()
        assert result1 == result2

    @patch("mcp_server.query_server.load_state")
    def test_returns_shallow_copy(self, mock_load):
        """Each call returns a shallow copy so mutations don't affect cache."""
        from mcp_server.query_server import _load_state_once

        mock_load.return_value = {"key": "value"}

        result1 = _load_state_once()
        result1["mutated"] = True

        result2 = _load_state_once()
        assert "mutated" not in result2
