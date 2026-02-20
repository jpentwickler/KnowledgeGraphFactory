"""Tests for async background execution infrastructure.

Tests the _is_async_mode, _start_background, _async_capable decorator,
and _run_kg_get_result function used for Cowork timeout avoidance.
"""

import asyncio
import inspect
import os
import time
import threading
from unittest.mock import patch

import pytest

# Import the functions under test
from mcp_server.server import (
    _is_async_mode,
    _start_background,
    _async_capable,
    _run_kg_get_result,
    _background_results,
    _background_lock,
)


# ---------------------------------------------------------------------------
# TestIsAsyncMode
# ---------------------------------------------------------------------------

class TestIsAsyncMode:
    """Tests for _is_async_mode()."""

    def test_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("KG_ASYNC_TOOLS", None)
            assert _is_async_mode() is False

    def test_set_true(self):
        with patch.dict(os.environ, {"KG_ASYNC_TOOLS": "true"}):
            assert _is_async_mode() is True

    def test_set_True_capitalized(self):
        with patch.dict(os.environ, {"KG_ASYNC_TOOLS": "True"}):
            assert _is_async_mode() is True

    def test_set_TRUE_uppercase(self):
        with patch.dict(os.environ, {"KG_ASYNC_TOOLS": "TRUE"}):
            assert _is_async_mode() is True

    def test_set_false(self):
        with patch.dict(os.environ, {"KG_ASYNC_TOOLS": "false"}):
            assert _is_async_mode() is False

    def test_set_empty_string(self):
        with patch.dict(os.environ, {"KG_ASYNC_TOOLS": ""}):
            assert _is_async_mode() is False

    def test_set_arbitrary_value(self):
        with patch.dict(os.environ, {"KG_ASYNC_TOOLS": "yes"}):
            assert _is_async_mode() is False


# ---------------------------------------------------------------------------
# TestStartBackground
# ---------------------------------------------------------------------------

class TestStartBackground:
    """Tests for _start_background()."""

    def setup_method(self):
        """Clean up background results before each test."""
        with _background_lock:
            _background_results.clear()

    def test_sync_function_completes(self):
        def my_sync_func():
            return {"result": "hello"}

        _start_background(my_sync_func, "test_sync_1")
        time.sleep(0.5)

        with _background_lock:
            assert "test_sync_1" in _background_results
            assert _background_results["test_sync_1"] == {"result": "hello"}

    def test_async_function_completes(self):
        async def my_async_func():
            await asyncio.sleep(0.05)
            return {"result": "async_hello"}

        _start_background(my_async_func, "test_async_1")
        time.sleep(1.0)

        with _background_lock:
            assert "test_async_1" in _background_results
            assert _background_results["test_async_1"] == {"result": "async_hello"}

    def test_sync_function_with_args(self):
        def add(a, b):
            return {"sum": a + b}

        _start_background(add, "test_args_1", 3, 4)
        time.sleep(0.5)

        with _background_lock:
            assert _background_results["test_args_1"] == {"sum": 7}

    def test_sync_function_with_kwargs(self):
        def greet(name="world"):
            return {"greeting": f"hello {name}"}

        _start_background(greet, "test_kwargs_1", name="alice")
        time.sleep(0.5)

        with _background_lock:
            assert _background_results["test_kwargs_1"] == {"greeting": "hello alice"}

    def test_exception_captured(self):
        def failing_func():
            raise ValueError("something went wrong")

        _start_background(failing_func, "test_fail_1")
        time.sleep(0.5)

        with _background_lock:
            result = _background_results["test_fail_1"]
            assert "Background task failed" in result["agent_response"]
            assert "something went wrong" in result["status"]["error"]

    def test_async_exception_captured(self):
        async def async_failing():
            raise RuntimeError("async error")

        _start_background(async_failing, "test_async_fail_1")
        time.sleep(1.0)

        with _background_lock:
            result = _background_results["test_async_fail_1"]
            assert "Background task failed" in result["agent_response"]
            assert "async error" in result["status"]["error"]


# ---------------------------------------------------------------------------
# TestAsyncCapableSync - decorator transparent when KG_ASYNC_TOOLS not set
# ---------------------------------------------------------------------------

class TestAsyncCapableSync:
    """Tests for @_async_capable on sync functions in sync mode (no env var)."""

    def setup_method(self):
        with _background_lock:
            _background_results.clear()

    def test_sync_passthrough(self):
        """Without KG_ASYNC_TOOLS, decorator is transparent."""
        @_async_capable("test_tool")
        def my_tool(message: str) -> dict:
            return {"echo": message}

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("KG_ASYNC_TOOLS", None)
            result = my_tool("hello")
            assert result == {"echo": "hello"}

    def test_sync_passthrough_with_false(self):
        """With KG_ASYNC_TOOLS=false, decorator is transparent."""
        @_async_capable("test_tool")
        def my_tool(message: str) -> dict:
            return {"echo": message}

        with patch.dict(os.environ, {"KG_ASYNC_TOOLS": "false"}):
            result = my_tool("hello")
            assert result == {"echo": "hello"}

    def test_sync_returns_task_id_when_async(self):
        """With KG_ASYNC_TOOLS=true, returns processing response."""
        @_async_capable("my_tool")
        def my_tool(message: str) -> dict:
            return {"echo": message}

        with patch.dict(os.environ, {"KG_ASYNC_TOOLS": "true"}):
            result = my_tool("hello")
            assert result["processing"] is True
            assert result["task_id"].startswith("my_tool_")
            assert "kg_get_result" in result["message"]

    def test_sync_background_eventually_completes(self):
        """Background task eventually stores its result."""
        @_async_capable("my_tool")
        def my_tool(message: str) -> dict:
            return {"echo": message}

        with patch.dict(os.environ, {"KG_ASYNC_TOOLS": "true"}):
            result = my_tool("world")
            task_id = result["task_id"]

        time.sleep(0.5)

        with _background_lock:
            assert task_id in _background_results
            assert _background_results[task_id] == {"echo": "world"}


# ---------------------------------------------------------------------------
# TestAsyncCapableAsync - decorator on async functions
# ---------------------------------------------------------------------------

class TestAsyncCapableAsync:
    """Tests for @_async_capable on async functions."""

    def setup_method(self):
        with _background_lock:
            _background_results.clear()

    def test_async_passthrough(self):
        """Without KG_ASYNC_TOOLS, async function runs normally."""
        @_async_capable("test_async_tool")
        async def my_async_tool(question: str) -> dict:
            return {"answer": question}

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("KG_ASYNC_TOOLS", None)
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(my_async_tool("test?"))
            finally:
                loop.close()
            assert result == {"answer": "test?"}

    def test_async_returns_task_id_when_async_mode(self):
        """With KG_ASYNC_TOOLS=true, returns processing response."""
        @_async_capable("async_tool")
        async def my_async_tool(question: str) -> dict:
            return {"answer": question}

        with patch.dict(os.environ, {"KG_ASYNC_TOOLS": "true"}):
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(my_async_tool("test?"))
            finally:
                loop.close()
            assert result["processing"] is True
            assert result["task_id"].startswith("async_tool_")

    def test_async_background_eventually_completes(self):
        """Async background task eventually stores its result."""
        @_async_capable("async_tool")
        async def my_async_tool(question: str) -> dict:
            await asyncio.sleep(0.05)
            return {"answer": question}

        with patch.dict(os.environ, {"KG_ASYNC_TOOLS": "true"}):
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(my_async_tool("hello?"))
            finally:
                loop.close()
            task_id = result["task_id"]

        time.sleep(1.0)

        with _background_lock:
            assert task_id in _background_results
            assert _background_results[task_id] == {"answer": "hello?"}

    def test_async_exception_in_background(self):
        """Async exception in background is captured properly."""
        @_async_capable("fail_tool")
        async def failing_tool(msg: str) -> dict:
            raise ValueError("async boom")

        with patch.dict(os.environ, {"KG_ASYNC_TOOLS": "true"}):
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(failing_tool("x"))
            finally:
                loop.close()
            task_id = result["task_id"]

        time.sleep(1.0)

        with _background_lock:
            stored = _background_results[task_id]
            assert "Background task failed" in stored["agent_response"]
            assert "async boom" in stored["status"]["error"]


# ---------------------------------------------------------------------------
# TestRunKgGetResult
# ---------------------------------------------------------------------------

class TestRunKgGetResult:
    """Tests for _run_kg_get_result()."""

    def setup_method(self):
        with _background_lock:
            _background_results.clear()

    def test_task_complete_returns_and_removes(self):
        with _background_lock:
            _background_results["task_abc"] = {"agent_response": "done", "status": {}}

        result = _run_kg_get_result("task_abc")
        assert result == {"agent_response": "done", "status": {}}

        # Should be removed after retrieval
        with _background_lock:
            assert "task_abc" not in _background_results

    def test_task_pending(self):
        # No result stored yet
        result = _run_kg_get_result("task_xyz")
        assert result["processing"] is True
        assert result["task_id"] == "task_xyz"
        assert "Still processing" in result["message"]

    def test_unknown_task_id(self):
        result = _run_kg_get_result("nonexistent_task_12345")
        assert result["processing"] is True
        assert result["task_id"] == "nonexistent_task_12345"

    def test_result_retrieved_only_once(self):
        """Once retrieved, the result is removed -- second call returns pending."""
        with _background_lock:
            _background_results["one_shot"] = {"data": "value"}

        first = _run_kg_get_result("one_shot")
        assert first == {"data": "value"}

        second = _run_kg_get_result("one_shot")
        assert second["processing"] is True


# ---------------------------------------------------------------------------
# TestSignaturePreservation
# ---------------------------------------------------------------------------

class TestSignaturePreservation:
    """Tests that @_async_capable preserves __signature__ for FastMCP."""

    def test_sync_signature_preserved(self):
        @_async_capable("sig_tool")
        def my_tool(message: str, scope: str = "default") -> dict:
            return {}

        sig = inspect.signature(my_tool)
        params = list(sig.parameters.keys())
        assert params == ["message", "scope"]
        assert sig.parameters["scope"].default == "default"

    def test_async_signature_preserved(self):
        @_async_capable("async_sig_tool")
        async def my_async_tool(question: str, context: str = "") -> dict:
            return {}

        sig = inspect.signature(my_async_tool)
        params = list(sig.parameters.keys())
        assert params == ["question", "context"]
        assert sig.parameters["context"].default == ""

    def test_name_preserved(self):
        @_async_capable("name_tool")
        def my_named_tool(msg: str) -> dict:
            """My docstring."""
            return {}

        assert my_named_tool.__name__ == "my_named_tool"
        assert my_named_tool.__doc__ == "My docstring."

    def test_async_name_preserved(self):
        @_async_capable("async_name_tool")
        async def my_async_named_tool(msg: str) -> dict:
            """Async docstring."""
            return {}

        assert my_async_named_tool.__name__ == "my_async_named_tool"
        assert my_async_named_tool.__doc__ == "Async docstring."


# ---------------------------------------------------------------------------
# TestTaskIdFormat
# ---------------------------------------------------------------------------

class TestTaskIdFormat:
    """Tests that task IDs follow expected format."""

    def setup_method(self):
        with _background_lock:
            _background_results.clear()

    def test_task_id_contains_tool_name(self):
        @_async_capable("kg_build_graph")
        def build(msg: str = "build") -> dict:
            return {}

        with patch.dict(os.environ, {"KG_ASYNC_TOOLS": "true"}):
            result = build()
            assert result["task_id"].startswith("kg_build_graph_")
            # 8 hex chars after the underscore
            suffix = result["task_id"].split("kg_build_graph_")[1]
            assert len(suffix) == 8

    def test_unique_task_ids(self):
        @_async_capable("unique_tool")
        def tool(msg: str = "") -> dict:
            return {}

        with patch.dict(os.environ, {"KG_ASYNC_TOOLS": "true"}):
            ids = set()
            for _ in range(20):
                result = tool()
                ids.add(result["task_id"])
            assert len(ids) == 20  # All unique


# ---------------------------------------------------------------------------
# TestEndToEndFlow
# ---------------------------------------------------------------------------

class TestEndToEndFlow:
    """Integration test: start tool -> poll -> get result."""

    def setup_method(self):
        with _background_lock:
            _background_results.clear()

    def test_full_start_poll_complete_cycle(self):
        @_async_capable("e2e_tool")
        def slow_tool(message: str) -> dict:
            time.sleep(0.2)
            return {"agent_response": f"Processed: {message}", "status": {"ok": True}}

        with patch.dict(os.environ, {"KG_ASYNC_TOOLS": "true"}):
            # Start
            start_result = slow_tool("test input")
            assert start_result["processing"] is True
            task_id = start_result["task_id"]

            # Poll immediately -- should be processing
            poll1 = _run_kg_get_result(task_id)
            assert poll1["processing"] is True

            # Wait for completion
            time.sleep(0.5)

            # Poll again -- should have result
            poll2 = _run_kg_get_result(task_id)
            assert poll2["agent_response"] == "Processed: test input"
            assert poll2["status"]["ok"] is True

            # Third poll -- result already consumed
            poll3 = _run_kg_get_result(task_id)
            assert poll3["processing"] is True
