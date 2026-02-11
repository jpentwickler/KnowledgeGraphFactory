"""Unit tests for conversation persistence helpers in the MCP server."""

import sys
import os

# Add project root to path (same pattern as server.py)
_root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _root_dir)

import pytest

from mcp_server.server import (
    _is_conversation_key,
    _should_persist,
    _serialize_conversation,
    _trim_conversation,
    MAX_CONVERSATION_MESSAGES,
)


class TestIsConversationKey:
    """Tests for _is_conversation_key()."""

    def test_valid_conversation_keys(self):
        assert _is_conversation_key("_user_intent_conversation") is True
        assert _is_conversation_key("_ner_extraction_conversation") is True
        assert _is_conversation_key("_file_suggestion_conversation") is True

    def test_ephemeral_keys_rejected(self):
        assert _is_conversation_key("_critic_verdict") is False
        assert _is_conversation_key("_critic_problems") is False

    def test_artifact_keys_rejected(self):
        assert _is_conversation_key("approved_user_goal") is False
        assert _is_conversation_key("proposed_files") is False

    def test_no_underscore_prefix_rejected(self):
        assert _is_conversation_key("conversation") is False
        assert _is_conversation_key("my_conversation") is False


class TestShouldPersist:
    """Tests for _should_persist()."""

    def test_artifact_keys_persist(self):
        assert _should_persist("approved_user_goal") is True
        assert _should_persist("proposed_files") is True

    def test_conversation_keys_persist(self):
        assert _should_persist("_user_intent_conversation") is True

    def test_ephemeral_keys_do_not_persist(self):
        assert _should_persist("_critic_verdict") is False
        assert _should_persist("_critic_problems") is False


class TestSerializeConversation:
    """Tests for _serialize_conversation()."""

    def test_empty_conversation(self):
        assert _serialize_conversation([]) == []

    def test_plain_user_text_unchanged(self):
        conv = [{"role": "user", "content": "hello"}]
        result = _serialize_conversation(conv)
        assert result == conv

    def test_tool_result_unchanged(self):
        conv = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_123", "content": "ok"}
            ]}
        ]
        result = _serialize_conversation(conv)
        assert result == conv

    def test_assistant_sdk_objects_serialized(self):
        """SDK objects with model_dump() are converted to dicts."""
        class FakeTextBlock:
            def model_dump(self):
                return {"type": "text", "text": "Hello", "citations": None}

        conv = [{"role": "assistant", "content": [FakeTextBlock()]}]
        result = _serialize_conversation(conv)
        assert isinstance(result[0]["content"][0], dict)
        assert result[0]["content"][0]["type"] == "text"
        assert result[0]["content"][0]["text"] == "Hello"

    def test_assistant_dict_content_unchanged(self):
        """Already-serialized assistant content passes through."""
        conv = [{"role": "assistant", "content": [
            {"type": "text", "text": "hi"}
        ]}]
        result = _serialize_conversation(conv)
        assert result == conv

    def test_mixed_conversation(self):
        """Full conversation with user, assistant SDK, and tool results."""
        class FakeBlock:
            def __init__(self, data):
                self._data = data
            def model_dump(self):
                return self._data

        conv = [
            {"role": "user", "content": "start"},
            {"role": "assistant", "content": [
                FakeBlock({"type": "text", "text": "thinking"}),
                FakeBlock({"type": "tool_use", "id": "t1", "name": "x", "input": {}}),
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "done"}
            ]},
            {"role": "assistant", "content": [
                FakeBlock({"type": "text", "text": "final answer"}),
            ]},
        ]
        result = _serialize_conversation(conv)
        assert len(result) == 4
        assert result[0]["content"] == "start"
        assert result[1]["content"][0]["type"] == "text"
        assert result[1]["content"][1]["type"] == "tool_use"
        assert result[2]["content"][0]["type"] == "tool_result"
        assert result[3]["content"][0]["text"] == "final answer"


class TestTrimConversation:
    """Tests for _trim_conversation()."""

    def test_empty_conversation(self):
        assert _trim_conversation([]) == []

    def test_under_limit_unchanged(self):
        conv = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
        ]
        assert _trim_conversation(conv, max_messages=10) == conv

    def test_exactly_at_limit_unchanged(self):
        conv = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": [{"type": "text", "text": "r1"}]},
        ]
        assert _trim_conversation(conv, max_messages=2) == conv

    def test_basic_trim(self):
        conv = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": [{"type": "text", "text": "r1"}]},
            {"role": "user", "content": "msg2"},
            {"role": "assistant", "content": [{"type": "text", "text": "r2"}]},
            {"role": "user", "content": "msg3"},
            {"role": "assistant", "content": [{"type": "text", "text": "r3"}]},
        ]
        result = _trim_conversation(conv, max_messages=4)
        # Last 4 starts at index 2: "msg2" which is a clean user text boundary
        assert len(result) == 4
        assert result[0]["content"] == "msg2"
        assert result[-1]["content"][0]["text"] == "r3"

    def test_skips_tool_result_boundary(self):
        """Trim point landing on tool_result scans forward to clean boundary."""
        conv = [
            {"role": "user", "content": "msg1"},                             # 0
            {"role": "assistant", "content": [                               # 1
                {"type": "text", "text": "r1"},
                {"type": "tool_use", "id": "t1", "name": "x", "input": {}},
            ]},
            {"role": "user", "content": [                                    # 2
                {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}
            ]},
            {"role": "assistant", "content": [{"type": "text", "text": "r2"}]},  # 3
            {"role": "user", "content": "msg3"},                             # 4
            {"role": "assistant", "content": [{"type": "text", "text": "r3"}]},  # 5
        ]
        # max_messages=4 -> start_idx = 6-4 = 2 (tool_result, not clean)
        # Scans forward: idx 2 is tool_result, idx 3 is assistant, idx 4 is clean user text
        result = _trim_conversation(conv, max_messages=4)
        assert len(result) == 2  # messages 4 and 5
        assert result[0]["content"] == "msg3"

    def test_skips_assistant_at_boundary(self):
        """Trim point landing on assistant message scans forward."""
        conv = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": [{"type": "text", "text": "r1"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "r2"}]},
            {"role": "user", "content": "msg2"},
            {"role": "assistant", "content": [{"type": "text", "text": "r3"}]},
        ]
        # max_messages=3 -> start_idx = 5-3 = 2 (assistant, not clean)
        # Scans: idx 2 is assistant, idx 3 is user text (clean)
        result = _trim_conversation(conv, max_messages=3)
        assert len(result) == 2
        assert result[0]["content"] == "msg2"

    def test_no_clean_boundary_returns_empty(self):
        """If no clean boundary exists after trim point, return empty."""
        conv = [
            {"role": "user", "content": "msg1"},                             # 0
            {"role": "assistant", "content": [                               # 1
                {"type": "tool_use", "id": "t1", "name": "x", "input": {}},
            ]},
            {"role": "user", "content": [                                    # 2
                {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}
            ]},
            {"role": "assistant", "content": [                               # 3
                {"type": "tool_use", "id": "t2", "name": "y", "input": {}},
            ]},
            {"role": "user", "content": [                                    # 4
                {"type": "tool_result", "tool_use_id": "t2", "content": "ok"}
            ]},
            {"role": "assistant", "content": [{"type": "text", "text": "done"}]},  # 5
        ]
        # max_messages=3 -> start_idx = 6-3 = 3
        # Scan: 3=assistant, 4=tool_result user, 5=assistant. No plain user text.
        result = _trim_conversation(conv, max_messages=3)
        assert result == []

    def test_trim_preserves_message_content(self):
        """Trimmed messages retain their full content."""
        conv = [
            {"role": "user", "content": "old message"},
            {"role": "assistant", "content": [{"type": "text", "text": "old reply"}]},
            {"role": "user", "content": "new message with details"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "detailed reply"},
                {"type": "tool_use", "id": "t1", "name": "tool", "input": {"k": "v"}},
            ]},
        ]
        result = _trim_conversation(conv, max_messages=2)
        assert result[0]["content"] == "new message with details"
        assert len(result[1]["content"]) == 2
        assert result[1]["content"][1]["input"] == {"k": "v"}
