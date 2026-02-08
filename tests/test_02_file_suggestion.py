"""Interactive test for File Suggestion Agent.

Usage:
    python -m tests.test_02_file_suggestion

Commands:
    - Type your message normally
    - 'state' - Show current state
    - 'quit' - Exit
"""

import json
import os
import sys
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agents import FileSuggestionAgent
from core import load_state, save_state, has_approved, get_approved


def main():
    agent = FileSuggestionAgent()
    conversation = None

    # Try to load state from Stage 1 output
    state_file = "state_after_user_intent.json"
    if os.path.exists(state_file):
        state = load_state(state_file)
        print(f"Loaded state from {state_file}")
    else:
        # Hardcoded fallback so the test can run standalone
        state = {
            "approved_user_goal": {
                "kind_of_graph": "furniture supply chain",
                "graph_description": (
                    "A knowledge graph for tracking furniture supply chains, "
                    "including suppliers, manufacturers, products, and components. "
                    "The graph should model supplier-product relationships, "
                    "bills of materials, pricing, and customer reviews for "
                    "supply chain risk analysis and product traceability."
                ),
            }
        }
        print("Using hardcoded fallback state (no state_after_user_intent.json found)")

    # Set data directory to example data if not already set
    if "KG_DATA_DIR" not in os.environ:
        example_data = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "examples", "furniture_supply_chain", "data"
        )
        if os.path.isdir(example_data):
            os.environ["KG_DATA_DIR"] = os.path.abspath(example_data)
            print(f"Set KG_DATA_DIR to {example_data}")
        else:
            print("WARNING: No KG_DATA_DIR set and example data not found.")
            print("Set KG_DATA_DIR environment variable to your data directory.")

    print("\n" + "=" * 70)
    print("FILE SUGGESTION AGENT - Interactive Test")
    print("=" * 70)
    print("\nThis agent will classify your data files for the KG pipeline.")
    print("\nCommands:")
    print("  - Type your message normally")
    print("  - 'state' - Show current state")
    print("  - 'quit' - Exit")
    print("\n" + "=" * 70 + "\n")

    while True:
        user_input = input("You: ").strip()

        if user_input.lower() == "quit":
            print("\nExiting...")
            break

        if user_input.lower() == "state":
            print("\nCurrent State:")
            print(json.dumps(state, indent=2))
            print()
            continue

        if not user_input:
            continue

        try:
            response, state, conversation = agent.run(user_input, state, conversation)

            print(f"\nAgent: {response}\n")

            if has_approved(state, "files"):
                print("=" * 70)
                print("SUCCESS: Files Approved!")
                print("=" * 70)
                approved = get_approved(state, "files")

                print("\nStructured files:")
                for f in approved["structured"]:
                    print(f"  - {f['path']}: {f['reason'][:80]}")

                print("\nUnstructured files:")
                for f in approved["unstructured"]:
                    print(f"  - {f['path']}: {f['reason'][:80]}")

                save_state(state, "state_after_file_suggestion.json")
                print("\n[OK] State saved to state_after_file_suggestion.json")
                print("\nReady for next agent (Schema Proposal Agent)!")
                print("\nType 'quit' to exit or continue conversation.")

        except Exception as e:
            print(f"\nError: {e}")
            print("Make sure ANTHROPIC_API_KEY is set in .env")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
