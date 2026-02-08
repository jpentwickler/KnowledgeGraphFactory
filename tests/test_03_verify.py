"""Non-interactive verification test for Schema Proposal (Stage 3).

This test uses the refinement loop directly (without coordinator) to verify
that the proposal and critic agents work together correctly.

Requires ANTHROPIC_API_KEY and data files in examples/furniture_supply_chain/data/.
"""

import json
import os
import sys
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from pipelines.schema_loop import run_refinement_loop
from tools.schema_tools import handle_approve_proposed_construction_plan
from core import has_approved, get_approved, save_state


def test_refinement_loop():
    """Run the refinement loop directly and verify the construction plan."""

    # Point at the example data directory
    data_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "examples", "furniture_supply_chain", "data"
    )
    os.environ["KG_DATA_DIR"] = os.path.abspath(data_dir)

    # Pre-load state with approved goal + approved files (from Stages 1-2)
    state = {
        "approved_user_goal": {
            "kind_of_graph": "furniture supply chain",
            "graph_description": (
                "A knowledge graph for tracking furniture supply chains, "
                "including suppliers, manufacturers, products, and components. "
                "The graph should model a multi-level bill of materials: "
                "products contain assemblies, assemblies contain parts, "
                "and parts are supplied by suppliers. It will support "
                "supply chain risk analysis, root cause traceability, "
                "and product composition queries."
            ),
        },
        "approved_files": {
            "structured": [
                {"path": "products.csv", "reason": "Product entities with IDs and attributes"},
                {"path": "suppliers.csv", "reason": "Supplier entities with IDs and attributes"},
                {"path": "part_supplier_mapping.csv", "reason": "Part-supplier relationships"},
            ],
            "unstructured": [],
        },
    }

    print("=" * 70)
    print("SCHEMA PROPOSAL - Verification Test (Direct Loop)")
    print("=" * 70)
    print(f"Data directory: {data_dir}")
    print(f"Approved files: {[f['path'] for f in state['approved_files']['structured']]}")

    # Run the refinement loop directly (1 iteration to keep test fast)
    print("\n[Running refinement loop (1 iteration)...]")
    print("(This may take 1-3 minutes due to multiple Claude API calls)")
    summary, state = run_refinement_loop(state, max_iterations=1)
    print(f"\nLoop result: {summary}")

    # Check the trace
    trace = state.get("_refinement_trace", [])
    print(f"\nRefinement trace: {len(trace)} iteration(s)")
    for entry in trace:
        print(f"  Iteration {entry['iteration']}: verdict={entry['critic_verdict']}, "
              f"problems={len(entry['critic_problems'])}")

    # Verify we have a construction plan
    assert "proposed_construction_plan" in state, "No proposed_construction_plan in state"
    plan = state["proposed_construction_plan"]

    node_count = sum(1 for v in plan.values() if v["construction_type"] == "node")
    rel_count = sum(1 for v in plan.values() if v["construction_type"] == "relationship")

    print(f"\nProposed plan: {node_count} nodes, {rel_count} relationships")
    assert node_count >= 2, f"Expected at least 2 nodes, got {node_count}"
    assert rel_count >= 1, f"Expected at least 1 relationship, got {rel_count}"

    # Print the plan
    print("\nNodes:")
    for key, rule in plan.items():
        if rule["construction_type"] == "node":
            print(f"  {rule['label']} (from {rule['source_file']}, key: {rule['unique_column_name']})")

    print("\nRelationships:")
    for key, rule in plan.items():
        if rule["construction_type"] == "relationship":
            print(f"  ({rule['from_node_label']})-[{rule['relationship_type']}]->({rule['to_node_label']})"
                  f" (from {rule['source_file']})")

    # Now approve
    print("\n[Approving construction plan...]")
    result = handle_approve_proposed_construction_plan(state)
    assert result["status"] == "approved", f"Approval failed: {result}"

    assert has_approved(state, "construction_plan"), "No approved_construction_plan in state"
    approved = get_approved(state, "construction_plan")

    print("\n" + "=" * 70)
    print("SUCCESS: Construction Plan Approved!")
    print("=" * 70)

    # Structure checks
    for key, rule in approved.items():
        assert "construction_type" in rule, f"Missing construction_type in {key}"
        assert "source_file" in rule, f"Missing source_file in {key}"

        if rule["construction_type"] == "node":
            assert "label" in rule, f"Missing label in {key}"
            assert "unique_column_name" in rule, f"Missing unique_column_name in {key}"
            assert "properties" in rule, f"Missing properties in {key}"
        elif rule["construction_type"] == "relationship":
            assert "relationship_type" in rule, f"Missing relationship_type in {key}"
            assert "from_node_label" in rule, f"Missing from_node_label in {key}"
            assert "to_node_label" in rule, f"Missing to_node_label in {key}"

    print("[OK] All structure checks passed")

    # Save state for downstream agents
    # Filter out internal keys for the saved snapshot
    save_state_clean = {
        k: v for k, v in state.items() if not k.startswith("_")
    }
    save_state(save_state_clean, "state_after_schema_proposal.json")
    print("[OK] State saved to state_after_schema_proposal.json")

    print("\n" + "=" * 70)
    print("VERIFICATION COMPLETE")
    print("=" * 70)

    return True


if __name__ == "__main__":
    try:
        test_refinement_loop()

        print("\n\n" + "=" * 70)
        print("ALL TESTS PASSED [OK]")
        print("=" * 70)

    except Exception as e:
        print(f"\n\nERROR: {e}")
        print("\nMake sure ANTHROPIC_API_KEY is set in .env")
        import traceback
        traceback.print_exc()
        sys.exit(1)
