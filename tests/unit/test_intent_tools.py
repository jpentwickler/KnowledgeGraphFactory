"""Unit tests for User Intent Agent tool handlers."""

import sys
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.intent_tools import (
    handle_set_proposed_goal,
    handle_approve_proposed_goal,
)


def test_set_proposed_goal():
    """Test that set_proposed_goal correctly stores the proposal in state."""
    state = {}

    result = handle_set_proposed_goal(
        state,
        kind_of_graph="test graph",
        graph_description="A test description for the knowledge graph"
    )

    # Check result
    assert result["status"] == "proposed"
    assert result["message"] == "Proposed goal saved: test graph"
    assert "proposal" in result
    assert result["proposal"]["kind_of_graph"] == "test graph"
    assert result["proposal"]["graph_description"] == "A test description for the knowledge graph"

    # Check state
    assert "proposed_user_goal" in state
    assert state["proposed_user_goal"]["kind_of_graph"] == "test graph"
    assert state["proposed_user_goal"]["graph_description"] == "A test description for the knowledge graph"

    print("[OK] test_set_proposed_goal passed")


def test_approve_without_proposal():
    """Test that approve fails gracefully when no proposal exists."""
    state = {}

    result = handle_approve_proposed_goal(state)

    # Should return error
    assert result["status"] == "error"
    assert "No proposed goal" in result["message"]

    # State should not have approved_user_goal
    assert "approved_user_goal" not in state

    print("[OK] test_approve_without_proposal passed")


def test_approve_with_proposal():
    """Test that approve works when a proposal exists."""
    state = {
        "proposed_user_goal": {
            "kind_of_graph": "test graph",
            "graph_description": "test description"
        }
    }

    result = handle_approve_proposed_goal(state)

    # Check result
    assert result["status"] == "approved"
    assert "approved" in result["message"].lower()
    assert "approved_goal" in result
    assert result["approved_goal"]["kind_of_graph"] == "test graph"
    assert result["approved_goal"]["graph_description"] == "test description"

    # Check state
    assert "approved_user_goal" in state
    assert state["approved_user_goal"]["kind_of_graph"] == "test graph"
    assert state["approved_user_goal"]["graph_description"] == "test description"

    print("[OK] test_approve_with_proposal passed")


def test_update_proposal():
    """Test that set_proposed_goal can update an existing proposal."""
    state = {
        "proposed_user_goal": {
            "kind_of_graph": "old graph",
            "graph_description": "old description"
        }
    }

    result = handle_set_proposed_goal(
        state,
        kind_of_graph="new graph",
        graph_description="new description"
    )

    # Should overwrite the old proposal
    assert result["status"] == "proposed"
    assert state["proposed_user_goal"]["kind_of_graph"] == "new graph"
    assert state["proposed_user_goal"]["graph_description"] == "new description"

    print("[OK] test_update_proposal passed")


if __name__ == "__main__":
    print("=" * 70)
    print("UNIT TESTS - User Intent Tool Handlers")
    print("=" * 70)

    try:
        test_set_proposed_goal()
        test_approve_without_proposal()
        test_approve_with_proposal()
        test_update_proposal()

        print("\n" + "=" * 70)
        print("ALL UNIT TESTS PASSED [OK]")
        print("=" * 70)

    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
