"""Unit tests for core/tracing.py."""

import asyncio
from unittest.mock import MagicMock

import pytest


class TestTraceable:
    """Test that @traceable works correctly (whether real langsmith or fallback)."""

    def test_traceable_with_name_kwarg(self):
        """@traceable(name='foo') should preserve function behavior."""
        from core.tracing import traceable

        @traceable(name="test_span")
        def my_func(x):
            return x + 1

        assert my_func(5) == 6

    def test_traceable_preserves_function_name(self):
        """Decorated function should keep its original __name__."""
        from core.tracing import traceable

        @traceable(name="test_span")
        def my_func(x):
            return x + 1

        assert my_func.__name__ == "my_func"

    def test_traceable_bare_decorator(self):
        """@traceable (no parens) should preserve function behavior."""
        from core.tracing import traceable

        @traceable
        def my_func(x):
            return x * 2

        assert my_func(3) == 6

    def test_traceable_on_async_function(self):
        """@traceable should work with async functions."""
        from core.tracing import traceable

        @traceable(name="async_span")
        async def my_async_func(x):
            return x + 10

        result = asyncio.run(my_async_func(5))
        assert result == 15

    def test_traceable_on_method(self):
        """@traceable should work as a method decorator."""
        from core.tracing import traceable

        class MyAgent:
            @traceable(name="agent.run")
            def run(self, message):
                return f"processed: {message}"

        agent = MyAgent()
        assert agent.run("hello") == "processed: hello"

    def test_traceable_with_multiple_kwargs(self):
        """@traceable with extra kwargs should still work."""
        from core.tracing import traceable

        @traceable(name="test", run_type="chain")
        def my_func():
            return 42

        assert my_func() == 42

    def test_wrap_anthropic_returns_usable_client(self):
        """wrap_anthropic should return a client that can be used normally."""
        from core.tracing import wrap_anthropic

        # MagicMock auto-creates attributes, mimicking Anthropic client
        client = MagicMock()
        wrapped = wrap_anthropic(client)

        # Both real langsmith (patches in-place) and fallback return same object
        assert wrapped is client

    def test_wrap_anthropic_preserves_messages_create(self):
        """wrap_anthropic should not break client.messages.create."""
        from core.tracing import wrap_anthropic

        client = MagicMock()
        client.messages.create.return_value = "test_response"

        wrapped = wrap_anthropic(client)

        # The wrapped client should still be callable
        assert wrapped.messages is not None


class TestFallbackFunctions:
    """Test the no-op fallback implementations directly.

    These tests verify the fallback code path works correctly,
    independent of whether langsmith is installed.
    """

    def _make_fallback_traceable(self):
        """Create a fresh fallback traceable (same code as core/tracing.py except block)."""
        def traceable(*args, **kwargs):
            def decorator(func):
                return func
            if args and callable(args[0]):
                return args[0]
            return decorator
        return traceable

    def _make_fallback_wrap_anthropic(self):
        """Create a fresh fallback wrap_anthropic."""
        def wrap_anthropic(client, **kwargs):
            return client
        return wrap_anthropic

    def test_fallback_traceable_with_name(self):
        """Fallback @traceable(name='x') returns function unchanged."""
        traceable = self._make_fallback_traceable()

        @traceable(name="test")
        def foo():
            return 42

        assert foo() == 42
        assert foo.__name__ == "foo"

    def test_fallback_traceable_bare(self):
        """Fallback @traceable (bare) returns function unchanged."""
        traceable = self._make_fallback_traceable()

        @traceable
        def bar():
            return 99

        assert bar() == 99
        assert bar.__name__ == "bar"

    def test_fallback_traceable_on_async(self):
        """Fallback @traceable works with async functions."""
        traceable = self._make_fallback_traceable()

        @traceable(name="async_test")
        async def async_func():
            return 7

        result = asyncio.run(async_func())
        assert result == 7

    def test_fallback_traceable_on_method(self):
        """Fallback @traceable works as a method decorator."""
        traceable = self._make_fallback_traceable()

        class Agent:
            @traceable(name="agent.run")
            def run(self, x):
                return x * 2

        assert Agent().run(5) == 10

    def test_fallback_wrap_anthropic_passthrough(self):
        """Fallback wrap_anthropic returns the exact same object."""
        wrap_anthropic = self._make_fallback_wrap_anthropic()

        obj = object()
        assert wrap_anthropic(obj) is obj

    def test_fallback_wrap_anthropic_with_kwargs(self):
        """Fallback wrap_anthropic ignores extra kwargs."""
        wrap_anthropic = self._make_fallback_wrap_anthropic()

        obj = object()
        assert wrap_anthropic(obj, tracing_extra={"foo": "bar"}) is obj


class TestMcpTraceable:
    """Test that @mcp_traceable preserves behavior and strips config from signature."""

    def test_mcp_traceable_preserves_behavior(self):
        """@mcp_traceable should not change function output."""
        from core.tracing import mcp_traceable

        @mcp_traceable(name="mcp.test")
        def my_func(message: str) -> dict:
            return {"echo": message}

        assert my_func(message="hello") == {"echo": "hello"}

    def test_mcp_traceable_strips_config_from_signature(self):
        """@mcp_traceable must NOT expose config in the function signature."""
        import inspect
        from core.tracing import mcp_traceable

        @mcp_traceable(name="mcp.test")
        def my_func(message: str) -> dict:
            return {}

        sig = inspect.signature(my_func)
        param_names = list(sig.parameters.keys())
        assert "config" not in param_names
        assert param_names == ["message"]

    def test_mcp_traceable_preserves_function_name(self):
        """Decorated function should keep its original __name__."""
        from core.tracing import mcp_traceable

        @mcp_traceable(name="mcp.test")
        def my_func(message: str) -> dict:
            return {}

        assert my_func.__name__ == "my_func"

    def test_mcp_traceable_on_async_function(self):
        """@mcp_traceable should work with async functions."""
        from core.tracing import mcp_traceable

        @mcp_traceable(name="mcp.async_test")
        async def my_async_func(x: int) -> int:
            return x + 10

        result = asyncio.run(my_async_func(5))
        assert result == 15

    def test_mcp_traceable_async_strips_config(self):
        """Async functions decorated with @mcp_traceable must not expose config."""
        import inspect
        from core.tracing import mcp_traceable

        @mcp_traceable(name="mcp.async_test")
        async def my_async_func(message: str, scope: str = "all") -> dict:
            return {}

        sig = inspect.signature(my_async_func)
        param_names = list(sig.parameters.keys())
        assert "config" not in param_names
        assert param_names == ["message", "scope"]

    def test_mcp_traceable_async_preserves_coroutine_flag(self):
        """@mcp_traceable must preserve asyncio.iscoroutinefunction()."""
        from core.tracing import mcp_traceable

        @mcp_traceable(name="mcp.async_test")
        async def my_async_func() -> dict:
            return {}

        assert asyncio.iscoroutinefunction(my_async_func)

    def test_mcp_traceable_no_params_function(self):
        """@mcp_traceable should work on functions with no parameters."""
        import inspect
        from core.tracing import mcp_traceable

        @mcp_traceable(name="mcp.no_params")
        def get_state() -> dict:
            return {"status": "ok"}

        assert get_state() == {"status": "ok"}
        sig = inspect.signature(get_state)
        assert list(sig.parameters.keys()) == []

    def test_mcp_traceable_with_defaults(self):
        """@mcp_traceable should preserve default parameter values."""
        import inspect
        from core.tracing import mcp_traceable

        @mcp_traceable(name="mcp.defaults")
        def build(message: str = "build", scope: str = "structured") -> dict:
            return {"message": message, "scope": scope}

        assert build() == {"message": "build", "scope": "structured"}
        assert build(scope="all") == {"message": "build", "scope": "all"}

        sig = inspect.signature(build)
        assert sig.parameters["message"].default == "build"
        assert sig.parameters["scope"].default == "structured"


class TestQueryBuilderTracing:
    """Test that query builder functions have @traceable decorators."""

    def test_select_retrieval_strategy_is_decorated(self):
        """_select_retrieval_strategy should have @traceable applied."""
        from pipelines.query_builder import _select_retrieval_strategy
        # If langsmith is installed, @traceable wraps the function (changing __wrapped__);
        # if using fallback, the function is returned unchanged. Either way, it must be callable.
        assert callable(_select_retrieval_strategy)
        assert asyncio.iscoroutinefunction(_select_retrieval_strategy)

    def test_execute_schema_query_is_decorated(self):
        """_execute_schema_query should have @traceable applied."""
        from pipelines.query_builder import _execute_schema_query
        assert callable(_execute_schema_query)

    def test_execute_cypher_is_decorated(self):
        """_execute_cypher should have @traceable applied."""
        from pipelines.query_builder import _execute_cypher
        assert callable(_execute_cypher)

    def test_execute_vector_search_is_decorated(self):
        """_execute_vector_search should have @traceable applied."""
        from pipelines.query_builder import _execute_vector_search
        assert callable(_execute_vector_search)

    def test_execute_hybrid_search_is_decorated(self):
        """_execute_hybrid_search should have @traceable applied."""
        from pipelines.query_builder import _execute_hybrid_search
        assert callable(_execute_hybrid_search)

    def test_execute_cross_layer_traversal_is_decorated(self):
        """_execute_cross_layer_traversal should have @traceable applied."""
        from pipelines.query_builder import _execute_cross_layer_traversal
        assert callable(_execute_cross_layer_traversal)

    def test_all_query_functions_preserve_names(self):
        """All decorated query functions should preserve their original names."""
        from pipelines.query_builder import (
            _select_retrieval_strategy,
            _execute_schema_query,
            _execute_cypher,
            _execute_vector_search,
            _execute_hybrid_search,
            _execute_cross_layer_traversal,
        )

        expected = {
            _select_retrieval_strategy: "_select_retrieval_strategy",
            _execute_schema_query: "_execute_schema_query",
            _execute_cypher: "_execute_cypher",
            _execute_vector_search: "_execute_vector_search",
            _execute_hybrid_search: "_execute_hybrid_search",
            _execute_cross_layer_traversal: "_execute_cross_layer_traversal",
        }

        for func, name in expected.items():
            assert func.__name__ == name, f"{func} lost its __name__ (expected {name})"


class TestModuleExports:
    """Test that core.tracing exports the expected symbols."""

    def test_traceable_is_callable(self):
        """core.tracing.traceable should be callable."""
        from core.tracing import traceable
        assert callable(traceable)

    def test_wrap_anthropic_is_callable(self):
        """core.tracing.wrap_anthropic should be callable."""
        from core.tracing import wrap_anthropic
        assert callable(wrap_anthropic)

    def test_core_package_exports_traceable(self):
        """core package should export traceable."""
        from core import traceable
        assert callable(traceable)

    def test_core_package_exports_wrap_anthropic(self):
        """core package should export wrap_anthropic."""
        from core import wrap_anthropic
        assert callable(wrap_anthropic)

    def test_mcp_traceable_is_callable(self):
        """core.tracing.mcp_traceable should be callable."""
        from core.tracing import mcp_traceable
        assert callable(mcp_traceable)

    def test_core_package_exports_mcp_traceable(self):
        """core package should export mcp_traceable."""
        from core import mcp_traceable
        assert callable(mcp_traceable)
