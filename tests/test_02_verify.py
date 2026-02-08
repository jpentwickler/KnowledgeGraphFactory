"""Non-interactive verification test for File Suggestion Agent.

This test simulates a conversation to verify the agent works correctly.
Requires ANTHROPIC_API_KEY and data files in examples/furniture_supply_chain/data/.
"""

import os
import sys
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agents import FileSuggestionAgent
from core import has_approved, get_approved, has_proposed, get_proposed, save_state


def test_conversation_flow():
    """Simulate a full conversation flow with the File Suggestion Agent."""

    # Point at the example data directory
    data_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "examples", "furniture_supply_chain", "data"
    )
    os.environ["KG_DATA_DIR"] = os.path.abspath(data_dir)

    agent = FileSuggestionAgent()
    conversation = None

    # Pre-load state with an approved user goal (from Stage 1)
    state = {
        "approved_user_goal": {
            "kind_of_graph": "furniture supply chain",
            "graph_description": (
                "A knowledge graph for tracking furniture supply chains, "
                "including suppliers, manufacturers, products, and components. "
                "The graph should model relationships between suppliers and "
                "products, bills of materials, pricing, and product reviews. "
                "It will support supply chain risk analysis and product "
                "traceability queries."
            ),
        }
    }

    print("=" * 70)
    print("FILE SUGGESTION AGENT - Verification Test")
    print("=" * 70)
    print(f"Data directory: {data_dir}")

    # Turn 1: Ask agent to classify files
    print("\n[Turn 1] User: What files should we use for the knowledge graph?")
    response, state, conversation = agent.run(
        "What files should we use for the knowledge graph?",
        state,
        conversation,
    )
    print(f"Agent: {response[:500]}...")

    # After turn 1, agent should have explored files and proposed
    if has_proposed(state, "files"):
        proposed = get_proposed(state, "files")
        print(f"\n[OK] Agent proposed files:")
        print(f"  Structured: {len(proposed['structured'])} files")
        print(f"  Unstructured: {len(proposed['unstructured'])} files")
    else:
        print("\n[INFO] Agent has not yet proposed files (may need another turn)")
        # Give it another turn
        print("\n[Turn 1b] User: Please classify the files you found.")
        response, state, conversation = agent.run(
            "Please classify the files you found and propose which ones to use.",
            state,
            conversation,
        )
        print(f"Agent: {response[:500]}...")
        assert has_proposed(state, "files"), "Agent should have proposed files by now"
        proposed = get_proposed(state, "files")
        print(f"\n[OK] Agent proposed files:")
        print(f"  Structured: {len(proposed['structured'])} files")
        print(f"  Unstructured: {len(proposed['unstructured'])} files")

    # Turn 2: Approve the proposal
    print("\n[Turn 2] User: Looks good, approve it")
    response, state, conversation = agent.run(
        "Looks good, approve it",
        state,
        conversation,
    )
    print(f"Agent: {response}")

    # Verify approval
    assert has_approved(state, "files"), "Agent should have approved the files"
    approved = get_approved(state, "files")

    print("\n" + "=" * 70)
    print("SUCCESS: Files Approved!")
    print("=" * 70)

    # Structure checks
    assert "structured" in approved, "Missing 'structured' key"
    assert "unstructured" in approved, "Missing 'unstructured' key"
    assert isinstance(approved["structured"], list), "structured should be a list"
    assert isinstance(approved["unstructured"], list), "unstructured should be a list"

    # Should have found at least the CSV files
    assert len(approved["structured"]) > 0, "Should have at least one structured file"

    print("\nApproved structured files:")
    for f in approved["structured"]:
        print(f"  - {f['path']}: {f['reason'][:80]}")

    print("\nApproved unstructured files:")
    for f in approved["unstructured"]:
        print(f"  - {f['path']}: {f['reason'][:80]}")

    print("\n[OK] All structure checks passed")

    # Save state for downstream agents
    save_state(state, "state_after_file_suggestion.json")
    print("[OK] State saved to state_after_file_suggestion.json")

    print("\n" + "=" * 70)
    print("VERIFICATION COMPLETE")
    print("=" * 70)

    return True


def test_no_approved_goal():
    """Test that agent handles missing approved goal gracefully."""
    data_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "examples", "furniture_supply_chain", "data"
    )
    os.environ["KG_DATA_DIR"] = os.path.abspath(data_dir)

    print("\n" + "=" * 70)
    print("EDGE CASE: No approved goal")
    print("=" * 70)

    agent = FileSuggestionAgent()
    state = {}  # No approved goal
    conversation = None

    response, state, conversation = agent.run(
        "What files should we use?",
        state,
        conversation,
    )
    print(f"Agent: {response}")

    # Agent should mention that Stage 1 is needed
    assert not has_approved(state, "files"), "Should not approve without a goal"
    print("[OK] Agent correctly handled missing goal")

    print("\n" + "=" * 70)
    print("EDGE CASE TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        print("\nRunning main conversation flow test...")
        test_conversation_flow()

        print("\n\nRunning edge case tests...")
        test_no_approved_goal()

        print("\n\n" + "=" * 70)
        print("ALL TESTS PASSED [OK]")
        print("=" * 70)

    except Exception as e:
        print(f"\n\nERROR: {e}")
        print("\nMake sure ANTHROPIC_API_KEY is set in .env")
        import traceback
        traceback.print_exc()
        sys.exit(1)
