"""Interactive test for Interactive Schema Proposal Agent.

Usage:
    python -m tests.test_03_schema_proposal

Commands:
    - Type your message normally to chat with the agent
    - 'state' - Show current state (without conversation history)
    - 'plan'  - Show just the proposed construction plan
    - 'validate' - Run the critic agent to validate the current plan
    - 'quit'  - Exit
"""

import json
import os
import sys
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agents import SchemaProposalAgent, SchemaCriticAgent
from core import load_state, save_state


def main():
    """Run interactive test for the Interactive Schema Proposal Agent."""
    agent = SchemaProposalAgent()
    conversation = None

    # Try to load state from previous stage output
    state_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "state_after_file_suggestion.json",
    )
    if os.path.exists(state_file):
        state = load_state(state_file)
        print(f"Loaded state from {state_file}")
    else:
        # Hardcoded fallback
        state = {
            "approved_user_goal": {
                "kind_of_graph": "furniture supply chain",
                "graph_description": (
                    "A knowledge graph for tracking furniture supply chains, "
                    "including products, assemblies, parts, and suppliers. "
                    "Supports supply chain risk analysis and product traceability."
                ),
            },
            "approved_files": {
                "structured": [
                    {"path": "products.csv", "reason": "Product entities"},
                    {"path": "suppliers.csv", "reason": "Supplier entities"},
                    {"path": "assemblies.csv", "reason": "Assembly components"},
                    {"path": "parts.csv", "reason": "Part entities"},
                    {"path": "part_supplier_mapping.csv", "reason": "Part-supplier relationships"},
                ],
                "unstructured": [],
            },
        }
        print("Using hardcoded fallback state (no state_after_file_suggestion.json found)")

    # Set data directory
    if "KG_DATA_DIR" not in os.environ:
        data_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "examples", "furniture_supply_chain", "data",
        )
        os.environ["KG_DATA_DIR"] = os.path.abspath(data_dir)

    print("=" * 70)
    print("INTERACTIVE SCHEMA PROPOSAL AGENT - Interactive Test")
    print("=" * 70)
    print(f"Data directory: {os.environ.get('KG_DATA_DIR')}")
    print("Commands: 'state', 'plan', 'validate', 'quit'")
    print("=" * 70)

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not user_input:
            continue

        if user_input.lower() == "quit":
            break

        if user_input.lower() == "state":
            clean = {k: v for k, v in state.items() if not k.startswith("_")}
            print(json.dumps(clean, indent=2))
            continue

        if user_input.lower() == "plan":
            plan = state.get("proposed_construction_plan", {})
            if not plan:
                print("No proposed construction plan yet.")
            else:
                print(json.dumps(plan, indent=2))
            continue

        if user_input.lower() == "validate":
            if "proposed_construction_plan" not in state:
                print("No proposed construction plan to validate.")
                continue
            print("\n[Validating with critic agent...]")
            critic = SchemaCriticAgent()
            critic_response, state = critic.run(state)
            print(f"\nCritic: {critic_response}")
            verdict = state.get("_critic_verdict", "unknown")
            problems = state.get("_critic_problems", [])
            print(f"\nVerdict: {verdict}")
            if problems:
                print("Problems:")
                for p in problems:
                    print(f"  - {p}")
            continue

        response, state, conversation = agent.run(
            user_input, state, conversation
        )
        print(f"\nAgent: {response}")

        if "approved_construction_plan" in state:
            print("\n[SUCCESS] Construction plan approved!")
            save_state(
                {k: v for k, v in state.items() if not k.startswith("_")},
                "state_after_schema_proposal.json",
            )
            print("[OK] State saved to state_after_schema_proposal.json")


if __name__ == "__main__":
    main()
