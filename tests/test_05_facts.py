"""Interactive test for Fact Extraction Agent.

Usage:
    python -m tests.test_05_facts

Commands:
    - Type your message normally to chat with the agent
    - 'state' - Show current state (without conversation history)
    - 'facts' - Show just the proposed fact types
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

from agents import FactExtractionAgent
from core import load_state, save_state


def main():
    """Run interactive test for the Fact Extraction Agent."""
    agent = FactExtractionAgent()
    conversation = None

    # Try to load state from previous stage output
    state_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "state_after_ner_extraction.json",
    )
    if os.path.exists(state_file):
        state = load_state(state_file)
        print(f"Loaded state from {state_file}")
    else:
        # Hardcoded fallback with entity types
        state = {
            "approved_user_goal": {
                "kind": "furniture supply chain root cause analysis",
                "description": (
                    "Build a knowledge graph that combines structured supply chain "
                    "data with unstructured product reviews to enable root cause "
                    "analysis of quality issues."
                ),
            },
            "approved_files": {
                "structured": [
                    {"path": "products.csv", "reason": "Product entities"},
                    {"path": "suppliers.csv", "reason": "Supplier entities"},
                ],
                "unstructured": [
                    {
                        "path": "product_reviews/gothenburg_table_reviews.md",
                        "reason": "Customer feedback about products",
                    }
                ],
            },
            "approved_construction_plan": {
                "Product": {
                    "construction_type": "node",
                    "source_file": "products.csv",
                    "label": "Product",
                    "unique_column_name": "product_id",
                    "properties": ["product_name", "category"],
                },
                "Supplier": {
                    "construction_type": "node",
                    "source_file": "suppliers.csv",
                    "label": "Supplier",
                    "unique_column_name": "supplier_id",
                    "properties": ["supplier_name", "country"],
                },
            },
            "approved_entity_types": {
                "Product": {
                    "source": "well_known",
                    "description": "Products from the graph schema",
                },
                "Issue": {
                    "source": "discovered",
                    "description": "Quality issues reported by customers",
                },
                "Feature": {
                    "source": "discovered",
                    "description": "Product features mentioned in reviews",
                },
            },
        }
        print(
            "Using hardcoded fallback state (no state_after_ner_extraction.json found)"
        )

    # Set data directory
    if "KG_DATA_DIR" not in os.environ:
        data_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "examples",
            "furniture_supply_chain",
            "data",
        )
        os.environ["KG_DATA_DIR"] = os.path.abspath(data_dir)

    print("=" * 70)
    print("FACT EXTRACTION AGENT - Interactive Test")
    print("=" * 70)
    print(f"Data directory: {os.environ.get('KG_DATA_DIR')}")
    print(f"Entity types: {', '.join(sorted(state.get('approved_entity_types', {}).keys()))}")
    print("Commands: 'state', 'facts', 'quit'")
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

        if user_input.lower() == "facts":
            facts = state.get("proposed_fact_types", {})
            if not facts:
                print("No proposed fact types yet.")
            else:
                print(json.dumps(facts, indent=2))
            continue

        response, state, conversation = agent.run(user_input, state, conversation)
        print(f"\nAgent: {response}")

        if "approved_fact_types" in state:
            print("\n[SUCCESS] Fact types approved!")
            save_state(
                {k: v for k, v in state.items() if not k.startswith("_")},
                "state_after_fact_extraction.json",
            )
            print("[OK] State saved to state_after_fact_extraction.json")


if __name__ == "__main__":
    main()
