"""Interactive test for User Intent Agent.

Usage:
    python -m tests.test_01_user_intent

Commands:
    - Type your message normally
    - 'state' - Show current state
    - 'quit' - Exit
"""

import sys
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agents import UserIntentAgent
from core import save_state, has_approved, get_approved
import json


def main():
    agent = UserIntentAgent()
    state = {}
    conversation = None

    print("=" * 70)
    print("USER INTENT AGENT - Interactive Test")
    print("=" * 70)
    print("\nThis agent will help you define your knowledge graph goal.")
    print("\nCommands:")
    print("  - Type your message normally")
    print("  - 'state' - Show current state")
    print("  - 'quit' - Exit")
    print("\n" + "=" * 70 + "\n")

    while True:
        user_input = input("You: ").strip()

        if user_input.lower() == 'quit':
            print("\nExiting...")
            break

        if user_input.lower() == 'state':
            print("\nCurrent State:")
            print(json.dumps(state, indent=2))
            print()
            continue

        if not user_input:
            continue

        try:
            # Run agent
            response, state, conversation = agent.run(user_input, state, conversation)

            print(f"\nAgent: {response}\n")

            # Check if goal was approved
            if has_approved(state, "user_goal"):
                print("=" * 70)
                print("SUCCESS: Goal Approved!")
                print("=" * 70)
                approved = get_approved(state, "user_goal")
                print(f"\nKind: {approved['kind_of_graph']}")
                print(f"Description: {approved['graph_description']}")

                # Save to file
                save_state(state, "state_after_user_intent.json")
                print("\n[OK] State saved to state_after_user_intent.json")
                print("\nReady for next agent (File Suggestion Agent)!")
                print("\nType 'quit' to exit or continue conversation.")

        except Exception as e:
            print(f"\nError: {e}")
            print("Make sure ANTHROPIC_API_KEY is set in .env")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
