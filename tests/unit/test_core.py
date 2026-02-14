"""Unit tests for core framework modules."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.state import (
    load_state,
    save_state,
    get_approved,
    get_proposed,
    set_proposed,
    approve,
    has_approved,
    has_proposed,
)
from core.tools import (
    create_tool_schema,
    execute_tool,
    format_tool_result,
    format_tool_error,
)


class TestStateManagement:
    """Tests for state.py functions."""

    def test_save_and_load_state_roundtrip(self):
        """Test that state can be saved and loaded correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            original_state = {
                "proposed_goal": {"text": "Build a knowledge graph"},
                "approved_goal": {"text": "Build a knowledge graph"},
                "some_data": [1, 2, 3]
            }

            save_state(original_state, str(state_path))
            loaded_state = load_state(str(state_path))

            assert loaded_state == original_state

    def test_load_nonexistent_state_returns_empty_dict(self):
        """Test that loading a nonexistent file returns empty dict."""
        state = load_state("/nonexistent/path/state.json")
        assert state == {}

    def test_save_state_creates_parent_directories(self):
        """Test that save_state creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = Path(tmpdir) / "a" / "b" / "c" / "state.json"

            save_state({"test": "value"}, str(nested_path))

            assert nested_path.exists()
            loaded = load_state(str(nested_path))
            assert loaded == {"test": "value"}

    def test_set_proposed(self):
        """Test setting a proposed artifact."""
        state = {}
        set_proposed(state, "goal", {"text": "my goal"})

        assert state["proposed_goal"] == {"text": "my goal"}

    def test_get_proposed(self):
        """Test getting a proposed artifact."""
        state = {"proposed_goal": {"text": "my goal"}}

        result = get_proposed(state, "goal")

        assert result == {"text": "my goal"}

    def test_get_proposed_returns_none_if_missing(self):
        """Test that get_proposed returns None for missing keys."""
        state = {}

        result = get_proposed(state, "goal")

        assert result is None

    def test_approve_copies_proposed_to_approved(self):
        """Test that approve copies proposed value to approved."""
        state = {"proposed_goal": {"text": "my goal"}}

        approve(state, "goal")

        assert state["approved_goal"] == {"text": "my goal"}
        assert state["proposed_goal"] == {"text": "my goal"}  # Original still exists

    def test_approve_raises_if_no_proposed(self):
        """Test that approve raises KeyError if no proposed value."""
        state = {}

        with pytest.raises(KeyError, match="No proposed artifact"):
            approve(state, "goal")

    def test_get_approved(self):
        """Test getting an approved artifact."""
        state = {"approved_goal": {"text": "my goal"}}

        result = get_approved(state, "goal")

        assert result == {"text": "my goal"}

    def test_get_approved_returns_none_if_missing(self):
        """Test that get_approved returns None for missing keys."""
        state = {}

        result = get_approved(state, "goal")

        assert result is None

    def test_has_approved(self):
        """Test checking if approved artifact exists."""
        state = {"approved_goal": {"text": "my goal"}}

        assert has_approved(state, "goal") is True
        assert has_approved(state, "other") is False

    def test_has_proposed(self):
        """Test checking if proposed artifact exists."""
        state = {"proposed_goal": {"text": "my goal"}}

        assert has_proposed(state, "goal") is True
        assert has_proposed(state, "other") is False


class TestToolUtilities:
    """Tests for tools.py functions."""

    def test_create_tool_schema(self):
        """Test creating a tool schema."""
        schema = create_tool_schema(
            name="test_tool",
            description="A test tool",
            properties={
                "param1": {"type": "string", "description": "First param"},
                "param2": {"type": "integer"}
            },
            required=["param1"]
        )

        assert schema["name"] == "test_tool"
        assert schema["description"] == "A test tool"
        assert schema["input_schema"]["type"] == "object"
        assert schema["input_schema"]["properties"]["param1"]["type"] == "string"
        assert schema["input_schema"]["required"] == ["param1"]

    def test_create_tool_schema_default_required(self):
        """Test that required defaults to empty list."""
        schema = create_tool_schema(
            name="test_tool",
            description="A test tool",
            properties={"param1": {"type": "string"}}
        )

        assert schema["input_schema"]["required"] == []

    def test_execute_tool(self):
        """Test executing a tool handler."""
        state = {}

        def my_handler(state, value):
            state["result"] = value
            return {"status": "success", "value": value}

        handlers = {"my_tool": my_handler}

        result = execute_tool(handlers, "my_tool", {"value": "test"}, state)

        assert result == {"status": "success", "value": "test"}
        assert state["result"] == "test"

    def test_execute_tool_unknown_raises(self):
        """Test that executing unknown tool raises KeyError."""
        handlers = {}

        with pytest.raises(KeyError, match="Unknown tool"):
            execute_tool(handlers, "unknown", {}, {})

    def test_format_tool_result_with_dict(self):
        """Test formatting a dict tool result."""
        result = format_tool_result("tool-123", {"status": "success"})

        assert result["type"] == "tool_result"
        assert result["tool_use_id"] == "tool-123"
        assert result["content"] == '{"status": "success"}'

    def test_format_tool_result_with_string(self):
        """Test formatting a string tool result."""
        result = format_tool_result("tool-123", "plain text result")

        assert result["content"] == "plain text result"

    def test_format_tool_error(self):
        """Test formatting a tool error."""
        result = format_tool_error("tool-123", "Something went wrong")

        assert result["type"] == "tool_result"
        assert result["tool_use_id"] == "tool-123"
        assert result["is_error"] is True
        assert "Something went wrong" in result["content"]


class TestAgentRunner:
    """Tests for agent.py functions."""

    def test_run_agent_sync_simple_response(self):
        """Test agent returns text response when no tool calls."""
        from core.agent import run_agent_sync

        # Create mock response
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Hello, user!"

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        mock_response.stop_reason = "end_turn"

        with patch('core.agent.anthropic.Anthropic') as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.return_value = mock_response

            response, state, conversation = run_agent_sync(
                message="Hello",
                state={},
                system_prompt="You are a test agent.",
                tools=[],
                tool_handlers={}
            )

            assert response == "Hello, user!"
            assert len(conversation) == 2  # user message + assistant response

    def test_run_agent_sync_with_tool_call(self):
        """Test agent handles tool calls correctly."""
        from anthropic.types import ToolUseBlock
        from core.agent import run_agent_sync

        # First response: tool call (use spec to prevent phantom .text attribute)
        mock_tool_block = MagicMock(spec=ToolUseBlock)
        mock_tool_block.type = "tool_use"
        mock_tool_block.name = "echo"
        mock_tool_block.input = {"text": "hello"}
        mock_tool_block.id = "tool-123"

        mock_response1 = MagicMock()
        mock_response1.content = [mock_tool_block]
        mock_response1.stop_reason = "tool_use"

        # Second response: text
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "I echoed: hello"

        mock_response2 = MagicMock()
        mock_response2.content = [mock_text_block]
        mock_response2.stop_reason = "end_turn"

        with patch('core.agent.wrap_anthropic', side_effect=lambda c: c), \
             patch('core.agent.anthropic.Anthropic') as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.side_effect = [mock_response1, mock_response2]

            tools = [create_tool_schema(
                "echo",
                "Echo the input",
                {"text": {"type": "string"}},
                ["text"]
            )]

            def echo_handler(state, text):
                state["echoed"] = text
                return {"echoed": text}

            handlers = {"echo": echo_handler}

            response, state, conversation = run_agent_sync(
                message="Please echo hello",
                state={},
                system_prompt="You are a test agent.",
                tools=tools,
                tool_handlers=handlers
            )

            assert response == "I echoed: hello"
            assert state["echoed"] == "hello"
            # Conversation: user, assistant (tool), user (result), assistant (text)
            assert len(conversation) == 4

    def test_run_agent_sync_tool_error_handling(self):
        """Test agent handles tool errors gracefully."""
        from anthropic.types import ToolUseBlock
        from core.agent import run_agent_sync

        # First response: tool call (use spec to prevent phantom .text attribute)
        mock_tool_block = MagicMock(spec=ToolUseBlock)
        mock_tool_block.type = "tool_use"
        mock_tool_block.name = "failing_tool"
        mock_tool_block.input = {}
        mock_tool_block.id = "tool-456"

        mock_response1 = MagicMock()
        mock_response1.content = [mock_tool_block]
        mock_response1.stop_reason = "tool_use"

        # Second response: text after error
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "The tool failed."

        mock_response2 = MagicMock()
        mock_response2.content = [mock_text_block]
        mock_response2.stop_reason = "end_turn"

        with patch('core.agent.wrap_anthropic', side_effect=lambda c: c), \
             patch('core.agent.anthropic.Anthropic') as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.side_effect = [mock_response1, mock_response2]

            tools = [create_tool_schema(
                "failing_tool",
                "A tool that fails",
                {},
                []
            )]

            def failing_handler(state):
                raise ValueError("Intentional failure")

            handlers = {"failing_tool": failing_handler}

            response, state, conversation = run_agent_sync(
                message="Call the failing tool",
                state={},
                system_prompt="You are a test agent.",
                tools=tools,
                tool_handlers=handlers
            )

            # Should complete without raising
            assert response == "The tool failed."

            # Check that error was sent back
            tool_result_msg = conversation[2]  # Third message is tool result
            assert tool_result_msg["role"] == "user"
            assert tool_result_msg["content"][0]["is_error"] is True


class TestProposedApprovedWorkflow:
    """Integration tests for the propose → approve workflow."""

    def test_full_propose_approve_workflow(self):
        """Test a complete propose → approve cycle."""
        state = {}

        # Agent proposes a goal
        set_proposed(state, "user_goal", {
            "goal": "Build a supply chain knowledge graph",
            "domain": "furniture manufacturing"
        })

        assert has_proposed(state, "user_goal")
        assert not has_approved(state, "user_goal")

        # User reviews and approves
        approve(state, "user_goal")

        assert has_approved(state, "user_goal")
        assert get_approved(state, "user_goal") == {
            "goal": "Build a supply chain knowledge graph",
            "domain": "furniture manufacturing"
        }

    def test_propose_approve_persist(self):
        """Test that proposed/approved state persists correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"

            # First session: propose and approve
            state = {}
            set_proposed(state, "goal", {"text": "my goal"})
            approve(state, "goal")
            save_state(state, str(state_path))

            # Second session: load and verify
            loaded_state = load_state(str(state_path))
            assert get_approved(loaded_state, "goal") == {"text": "my goal"}
