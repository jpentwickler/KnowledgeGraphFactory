"""
Unit tests for Remote Query Server features (US021).

Tests:
- Environment validation (3 tests)
- Bearer token auth middleware (5 tests)
- Health check endpoint (3 tests)
- Input validation (4 tests)
- ASGI app export (2 tests)
- Connection timeouts (2 tests)
- Request logging (3 tests)
- Graceful shutdown (2 tests)
"""

import json
import os

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from starlette.requests import Request


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
# TestEnvironmentValidation (3 tests)
# =============================================================================

class TestEnvironmentValidation:
    """Tests for _validate_env()."""

    @patch.dict(os.environ, {
        "NEO4J_URI": "",
        "NEO4J_USER": "",
        "NEO4J_PASSWORD": "",
        "ANTHROPIC_API_KEY": "",
    })
    def test_missing_required_raises_system_exit(self):
        """SystemExit(1) when required env vars are missing."""
        from mcp_server.query_server import _validate_env

        with pytest.raises(SystemExit) as exc_info:
            _validate_env()
        assert exc_info.value.code == 1

    @patch.dict(os.environ, {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "password",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "OPENAI_API_KEY": "sk-test",
    })
    def test_all_present_passes(self):
        """No error when all required env vars are set."""
        from mcp_server.query_server import _validate_env

        _validate_env()  # Should not raise

    @patch.dict(os.environ, {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "password",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "OPENAI_API_KEY": "",
    })
    def test_missing_openai_logs_warning(self, capsys):
        """Warning printed to stderr when OPENAI_API_KEY is missing."""
        from mcp_server.query_server import _validate_env

        _validate_env()  # Should not raise
        captured = capsys.readouterr()
        assert "OPENAI_API_KEY" in captured.err


# =============================================================================
# TestBearerTokenAuth (5 tests)
# =============================================================================

class TestBearerTokenAuth:
    """Tests for BearerTokenMiddleware."""

    @pytest.mark.asyncio
    async def test_valid_token_passes(self):
        """Request with valid token proceeds to handler."""
        import mcp_server.query_server as qs
        from mcp_server.query_server import BearerTokenMiddleware

        original_tokens = qs._AUTH_TOKENS
        try:
            qs._AUTH_TOKENS = {"valid-token-123"}

            middleware = BearerTokenMiddleware(app=None)

            mock_request = MagicMock()
            mock_request.url.path = "/mcp"
            mock_request.headers = {"authorization": "Bearer valid-token-123"}
            mock_request.client = MagicMock(host="127.0.0.1")

            mock_response = MagicMock()
            mock_call_next = AsyncMock(return_value=mock_response)

            result = await middleware.dispatch(mock_request, mock_call_next)

            mock_call_next.assert_called_once_with(mock_request)
            assert result is mock_response
        finally:
            qs._AUTH_TOKENS = original_tokens

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self):
        """Request with invalid token gets 401."""
        import mcp_server.query_server as qs
        from mcp_server.query_server import BearerTokenMiddleware

        original_tokens = qs._AUTH_TOKENS
        try:
            qs._AUTH_TOKENS = {"valid-token-123"}

            middleware = BearerTokenMiddleware(app=None)

            mock_request = MagicMock()
            mock_request.url.path = "/mcp"
            mock_request.headers = {"authorization": "Bearer wrong-token"}
            mock_request.client = MagicMock(host="127.0.0.1")

            mock_call_next = AsyncMock()

            with patch("mcp_server.query_server._log_auth_failure"):
                result = await middleware.dispatch(mock_request, mock_call_next)

            mock_call_next.assert_not_called()
            assert result.status_code == 401
        finally:
            qs._AUTH_TOKENS = original_tokens

    @pytest.mark.asyncio
    async def test_missing_header_returns_401(self):
        """Request without Authorization header gets 401."""
        import mcp_server.query_server as qs
        from mcp_server.query_server import BearerTokenMiddleware

        original_tokens = qs._AUTH_TOKENS
        try:
            qs._AUTH_TOKENS = {"valid-token-123"}

            middleware = BearerTokenMiddleware(app=None)

            mock_request = MagicMock()
            mock_request.url.path = "/mcp"
            mock_request.headers = {}
            mock_request.client = MagicMock(host="127.0.0.1")

            mock_call_next = AsyncMock()

            with patch("mcp_server.query_server._log_auth_failure"):
                result = await middleware.dispatch(mock_request, mock_call_next)

            mock_call_next.assert_not_called()
            assert result.status_code == 401
        finally:
            qs._AUTH_TOKENS = original_tokens

    @pytest.mark.asyncio
    async def test_no_tokens_configured_passes_all(self):
        """When no tokens are configured (dev mode), all requests pass."""
        import mcp_server.query_server as qs
        from mcp_server.query_server import BearerTokenMiddleware

        original_tokens = qs._AUTH_TOKENS
        try:
            qs._AUTH_TOKENS = set()

            middleware = BearerTokenMiddleware(app=None)

            mock_request = MagicMock()
            mock_request.url.path = "/mcp"
            mock_request.headers = {}
            mock_request.client = MagicMock(host="127.0.0.1")

            mock_response = MagicMock()
            mock_call_next = AsyncMock(return_value=mock_response)

            result = await middleware.dispatch(mock_request, mock_call_next)

            mock_call_next.assert_called_once_with(mock_request)
            assert result is mock_response
        finally:
            qs._AUTH_TOKENS = original_tokens

    @pytest.mark.asyncio
    async def test_health_skips_auth(self):
        """Health endpoint is always accessible, even with tokens configured."""
        import mcp_server.query_server as qs
        from mcp_server.query_server import BearerTokenMiddleware

        original_tokens = qs._AUTH_TOKENS
        try:
            qs._AUTH_TOKENS = {"valid-token-123"}

            middleware = BearerTokenMiddleware(app=None)

            mock_request = MagicMock()
            mock_request.url.path = "/health"
            mock_request.headers = {}  # No auth header
            mock_request.client = MagicMock(host="127.0.0.1")

            mock_response = MagicMock()
            mock_call_next = AsyncMock(return_value=mock_response)

            result = await middleware.dispatch(mock_request, mock_call_next)

            mock_call_next.assert_called_once_with(mock_request)
            assert result is mock_response
        finally:
            qs._AUTH_TOKENS = original_tokens


# =============================================================================
# TestHealthCheck (3 tests)
# =============================================================================

class TestHealthCheck:
    """Tests for the /health endpoint."""

    def setup_method(self):
        _reset_module_state()

    @pytest.mark.asyncio
    @patch("mcp_server.query_server._get_driver")
    async def test_healthy_response(self, mock_get_driver):
        """Returns 200 with healthy status when Neo4j is connected."""
        from mcp_server.query_server import health_check

        mock_driver = MagicMock()
        mock_driver.verify_connectivity.return_value = None
        mock_get_driver.return_value = mock_driver

        mock_request = MagicMock(spec=Request)
        response = await health_check(mock_request)

        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["status"] == "healthy"
        assert body["neo4j"] == "connected"

    @pytest.mark.asyncio
    @patch("mcp_server.query_server._get_driver")
    async def test_unhealthy_response(self, mock_get_driver):
        """Returns 503 with unhealthy status when Neo4j is unreachable."""
        from mcp_server.query_server import health_check

        mock_driver = MagicMock()
        mock_driver.verify_connectivity.side_effect = Exception("Connection refused")
        mock_get_driver.return_value = mock_driver

        mock_request = MagicMock(spec=Request)
        response = await health_check(mock_request)

        assert response.status_code == 503
        body = json.loads(response.body)
        assert body["status"] == "unhealthy"
        assert "Connection refused" in body["error"]

    @pytest.mark.asyncio
    @patch("mcp_server.query_server._get_driver")
    async def test_json_content_type(self, mock_get_driver):
        """Response has application/json content type."""
        from mcp_server.query_server import health_check

        mock_driver = MagicMock()
        mock_driver.verify_connectivity.return_value = None
        mock_get_driver.return_value = mock_driver

        mock_request = MagicMock(spec=Request)
        response = await health_check(mock_request)

        assert response.media_type == "application/json"


# =============================================================================
# TestInputValidation (4 tests)
# =============================================================================

class TestInputValidation:
    """Tests for input length validation in _run_kg_query."""

    def setup_method(self):
        _reset_module_state()

    @pytest.mark.asyncio
    @patch("mcp_server.query_server._load_state_once")
    @patch("mcp_server.query_server._get_driver")
    @patch("pipelines.query_builder._select_retrieval_strategy", new_callable=AsyncMock)
    @patch("pipelines.query_builder._execute_schema_query")
    async def test_question_within_limit(self, mock_schema, mock_strategy, mock_driver, mock_state):
        """Normal-length question proceeds to strategy selection."""
        from mcp_server.query_server import _run_kg_query

        mock_driver.return_value = MagicMock()
        mock_state.return_value = {}
        mock_strategy.return_value = {
            "strategy": "schema",
            "parameters": {},
            "reasoning": "test",
        }
        mock_schema.return_value = {
            "answer": "Schema info",
            "evidence": [],
            "confidence": 1.0,
            "details": {},
        }

        result = await _run_kg_query("What labels exist?")

        assert result["status"]["success"] is True
        mock_strategy.assert_called_once()

    @pytest.mark.asyncio
    async def test_question_over_limit(self):
        """Question exceeding 5,000 chars returns error without calling strategy."""
        from mcp_server.query_server import _run_kg_query

        long_question = "x" * 5_001

        result = await _run_kg_query(long_question)

        assert result["status"]["success"] is False
        assert "5000" in result["status"]["error"]
        assert "5001" in result["status"]["error"]

    @pytest.mark.asyncio
    async def test_context_over_limit(self):
        """Context exceeding 10,000 chars returns error without calling strategy."""
        from mcp_server.query_server import _run_kg_query

        long_context = "y" * 10_001

        result = await _run_kg_query("Short question", context=long_context)

        assert result["status"]["success"] is False
        assert "10000" in result["status"]["error"]
        assert "10001" in result["status"]["error"]

    @pytest.mark.asyncio
    async def test_error_includes_char_counts(self):
        """Error message includes both the limit and the actual char count."""
        from mcp_server.query_server import _run_kg_query

        long_question = "a" * 6_000

        result = await _run_kg_query(long_question)

        error = result["status"]["error"]
        assert "5000" in error
        assert "6000" in error


# =============================================================================
# TestAsgiApp (2 tests)
# =============================================================================

class TestAsgiApp:
    """Tests for the exported ASGI app."""

    def test_app_is_importable(self):
        """The `app` object is importable from query_server."""
        from mcp_server.query_server import app

        assert app is not None

    def test_app_is_callable(self):
        """The app object is an ASGI callable (has __call__)."""
        from mcp_server.query_server import app

        assert callable(app)


# =============================================================================
# TestConnectionTimeouts (2 tests)
# =============================================================================

class TestConnectionTimeouts:
    """Tests for configurable Neo4j pool size and connection timeout."""

    @patch("utils.neo4j_utils.GraphDatabase")
    @patch.dict(os.environ, {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "password",
        "NEO4J_POOL_SIZE": "100",
    })
    def test_pool_size_from_env(self, mock_gdb):
        """NEO4J_POOL_SIZE env var is passed to driver constructor."""
        from utils.neo4j_utils import get_neo4j_driver

        mock_driver = MagicMock()
        mock_gdb.driver.return_value = mock_driver

        get_neo4j_driver()

        call_kwargs = mock_gdb.driver.call_args[1]
        assert call_kwargs["max_connection_pool_size"] == 100

    @patch("utils.neo4j_utils.GraphDatabase")
    @patch.dict(os.environ, {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "password",
        "NEO4J_CONNECTION_TIMEOUT": "60",
    })
    def test_connection_timeout_from_env(self, mock_gdb):
        """NEO4J_CONNECTION_TIMEOUT env var is passed to driver constructor."""
        from utils.neo4j_utils import get_neo4j_driver

        mock_driver = MagicMock()
        mock_gdb.driver.return_value = mock_driver

        get_neo4j_driver()

        call_kwargs = mock_gdb.driver.call_args[1]
        assert call_kwargs["connection_timeout"] == 60.0


# =============================================================================
# TestRequestLogging (3 tests)
# =============================================================================

class TestRequestLogging:
    """Tests for structured request logging."""

    def test_json_format(self):
        """Log output is valid JSON with required fields."""
        from mcp_server.query_server import _log_request

        with patch("mcp_server.query_server._logger") as mock_logger:
            _log_request("kg_query", "What labels exist?", 42.5)

            mock_logger.info.assert_called_once()
            log_line = mock_logger.info.call_args[0][0]
            data = json.loads(log_line)

            assert data["tool"] == "kg_query"
            assert data["question"] == "What labels exist?"
            assert data["latency_ms"] == 42.5
            assert "ts" in data

    def test_question_truncated_at_200(self):
        """Questions longer than 200 chars are truncated in log output."""
        from mcp_server.query_server import _log_request

        long_question = "a" * 300

        with patch("mcp_server.query_server._logger") as mock_logger:
            _log_request("kg_query", long_question, 10.0)

            log_line = mock_logger.info.call_args[0][0]
            data = json.loads(log_line)

            assert len(data["question"]) == 200

    def test_auth_failure_logged(self):
        """Auth failure log includes path and client, not token."""
        from mcp_server.query_server import _log_auth_failure

        mock_request = MagicMock()
        mock_request.url.path = "/mcp"
        mock_request.client = MagicMock(host="192.168.1.1")

        with patch("mcp_server.query_server._logger") as mock_logger:
            _log_auth_failure(mock_request, "invalid_token")

            mock_logger.warning.assert_called_once()
            log_line = mock_logger.warning.call_args[0][0]
            data = json.loads(log_line)

            assert data["event"] == "auth_failure"
            assert data["path"] == "/mcp"
            assert data["client"] == "192.168.1.1"
            assert data["reason"] == "invalid_token"


# =============================================================================
# TestGracefulShutdown (2 tests)
# =============================================================================

class TestGracefulShutdown:
    """Tests for _shutdown_handler."""

    def test_handler_closes_driver(self):
        """Shutdown handler closes the shared driver."""
        import mcp_server.query_server as qs

        mock_driver = MagicMock()
        qs._driver = mock_driver

        qs._shutdown_handler()

        mock_driver.close.assert_called_once()
        assert qs._driver is None

    def test_handler_tolerates_none_driver(self):
        """Shutdown handler does not fail when driver is None."""
        import mcp_server.query_server as qs

        qs._driver = None

        qs._shutdown_handler()  # Should not raise

        assert qs._driver is None
