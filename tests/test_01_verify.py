"""Non-interactive verification test for User Intent Agent.

This test simulates a conversation to verify the agent works correctly.
"""

import sys
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agents import UserIntentAgent
from core import save_state, has_approved, get_approved, has_proposed, get_proposed
import json


def test_conversation_flow():
    """Simulate a full conversation flow with the agent."""
    agent = UserIntentAgent()
    state = {}
    conversation = None

    print("=" * 70)
    print("USER INTENT AGENT - Verification Test")
    print("=" * 70)

    # Turn 1: Initial user message
    print("\n[Turn 1] User: I want to build a knowledge graph for furniture supply chains")
    response, state, conversation = agent.run(
        "I want to build a knowledge graph for furniture supply chains",
        state,
        conversation
    )
    print(f"Agent: {response}")
    assert not has_approved(state, "user_goal"), "Agent should not auto-approve"
    print("[OK] Agent did not auto-approve")

    # Turn 2: Provide more details
    print("\n[Turn 2] User: I want to track suppliers, manufacturers, products, and components...")
    response, state, conversation = agent.run(
        "I want to track suppliers, manufacturers, products, and components. "
        "The goal is to analyze supply chain dependencies and identify risks. "
        "I have CSV files with supplier data, product catalogs, and manufacturing BOMs.",
        state,
        conversation
    )
    print(f"Agent: {response}")

    # Check if agent has proposed a goal
    if has_proposed(state, "user_goal"):
        proposed = get_proposed(state, "user_goal")
        print(f"\n[OK] Agent proposed a goal:")
        print(f"  Kind: {proposed['kind_of_graph']}")
        print(f"  Description: {proposed['graph_description'][:100]}...")
    else:
        print("\n⚠ Agent has not yet proposed a goal (may need more conversation)")

    # Turn 3: Approve the goal
    print("\n[Turn 3] User: Yes, approve it")
    response, state, conversation = agent.run(
        "Yes, approve it",
        state,
        conversation
    )
    print(f"Agent: {response}")

    # Verify approval
    assert has_approved(state, "user_goal"), "Agent should have approved the goal"
    approved = get_approved(state, "user_goal")

    print("\n" + "=" * 70)
    print("SUCCESS: Goal Approved!")
    print("=" * 70)
    print(f"\nKind: {approved['kind_of_graph']}")
    print(f"Description: {approved['graph_description']}")

    # Verify structure
    assert "kind_of_graph" in approved, "Missing kind_of_graph field"
    assert "graph_description" in approved, "Missing graph_description field"
    assert len(approved["kind_of_graph"]) > 0, "kind_of_graph is empty"
    assert len(approved["graph_description"]) > 50, "graph_description is too short"

    print("\n[OK] All structure checks passed")

    # Save state
    save_state(state, "state_after_user_intent.json")
    print("\n[OK] State saved to state_after_user_intent.json")

    print("\n" + "=" * 70)
    print("VERIFICATION COMPLETE")
    print("=" * 70)

    return True


def test_edge_cases():
    """Test edge cases and error handling."""
    agent = UserIntentAgent()

    print("\n" + "=" * 70)
    print("EDGE CASE TESTS")
    print("=" * 70)

    # Test 1: Try to approve without a proposal
    print("\n[Test 1] Try to approve without a proposal")
    state = {}
    conversation = None

    response, state, conversation = agent.run(
        "approve",
        state,
        conversation
    )
    print(f"Agent response: {response}")

    # Agent should handle this gracefully (either by explaining or proposing first)
    assert not has_approved(state, "user_goal"), "Should not approve without a proposal"
    print("[OK] Correctly handled approval attempt without proposal")

    print("\n" + "=" * 70)
    print("EDGE CASE TESTS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        print("\nRunning main conversation flow test...")
        test_conversation_flow()

        print("\n\nRunning edge case tests...")
        test_edge_cases()

        print("\n\n" + "=" * 70)
        print("ALL TESTS PASSED [OK]")
        print("=" * 70)

    except Exception as e:
        print(f"\n\nERROR: {e}")
        print("\nMake sure ANTHROPIC_API_KEY is set in .env")
        import traceback
        traceback.print_exc()
        sys.exit(1)
