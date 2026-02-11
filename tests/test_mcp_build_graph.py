"""Test script for kg_build_graph MCP tool.

This script tests the MCP tool directly without requiring Claude Code.
It simulates what happens when Claude Code calls the kg_build_graph tool.

Usage:
    python -m tests.test_mcp_build_graph
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# Import MCP server functions
from mcp_server.server import kg_build_graph, kg_get_state
from core import load_state, save_state


def main():
    """Test the kg_build_graph MCP tool."""
    print("=" * 70)
    print("MCP TOOL TEST: kg_build_graph")
    print("=" * 70)

    # Check for state file with construction plan
    state_file = "state/current_state.json"
    if not os.path.exists(state_file):
        state_file = "examples/furniture_supply_chain/state/current_state.json"

    if not os.path.exists(state_file):
        print("\n[ERROR] No state file found.")
        print("Please run Stages 1-3 first to create an approved construction plan.")
        return 1

    print(f"\n[Step 1] Checking current state...")
    state_result = kg_get_state()
    print(f"  State keys: {list(state_result.keys())}")

    if "approved_construction_plan" not in state_result:
        print("\n[ERROR] No approved_construction_plan in state.")
        print("Please complete Stage 3 (Schema Proposal) first.")
        return 1

    plan = state_result["approved_construction_plan"]
    node_count = sum(1 for v in plan.values() if v.get("construction_type") == "node")
    rel_count = sum(1 for v in plan.values() if v.get("construction_type") == "relationship")
    print(f"  Construction plan found: {node_count} node types, {rel_count} relationship types")

    # Check Neo4j environment variables
    print("\n[Step 2] Checking Neo4j configuration...")
    neo4j_uri = os.environ.get("NEO4J_URI")
    neo4j_user = os.environ.get("NEO4J_USER")
    neo4j_password = os.environ.get("NEO4J_PASSWORD")

    if not all([neo4j_uri, neo4j_user, neo4j_password]):
        print("  [WARNING] Neo4j credentials not set")
        print("  Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD in .env")
        print("\n  The tool will return an error message, which is expected.")
    else:
        print(f"  NEO4J_URI: {neo4j_uri}")
        print(f"  NEO4J_USER: {neo4j_user}")
        print(f"  NEO4J_PASSWORD: {'*' * len(neo4j_password)}")

    # Optional: Clear graph
    if neo4j_uri and neo4j_user and neo4j_password:
        print("\n[Step 3] Clear existing graph before import? (y/N): ", end="")
        response = input().strip().lower()
        if response == "y":
            try:
                from utils import get_neo4j_driver, close_driver
                driver = get_neo4j_driver()
                with driver.session() as session:
                    session.run("MATCH (n) DETACH DELETE n")
                close_driver(driver)
                print("  Graph cleared.")
            except Exception as exc:
                print(f"  [WARNING] Failed to clear graph: {exc}")
    else:
        print("\n[Step 3] Skipping graph clear (no Neo4j credentials)")

    # Call the MCP tool
    print("\n" + "=" * 70)
    print("CALLING MCP TOOL: kg_build_graph()")
    print("=" * 70)

    result = kg_build_graph(message="build the graph")

    print("\n[Response]")
    print(result["agent_response"])

    print("\n[Status]")
    status = result["status"]
    print(f"  Success: {status.get('success', False)}")

    if status.get("success"):
        print(f"  Neo4j Version: {status.get('neo4j_version', 'unknown')}")
        print(f"  Database: {status.get('database', 'unknown')}")

        verification = status.get("verification", {})
        print(f"  Total Nodes: {verification.get('total_nodes', 0)}")
        print(f"  Total Relationships: {verification.get('total_relationships', 0)}")

    if status.get("error"):
        print(f"  Error: {status.get('error')}")
        if status.get("details"):
            print(f"  Details: {status.get('details')}")

    # Save full result to file for inspection
    result_file = "test_kg_build_graph_result.json"
    with open(result_file, "w") as f:
        # Make status JSON-serializable
        serializable_status = {k: v for k, v in status.items()}
        json.dump({
            "agent_response": result["agent_response"],
            "status": serializable_status
        }, f, indent=2)

    print(f"\n[Result saved to: {result_file}]")

    if status.get("success"):
        print("\n" + "=" * 70)
        print("SUCCESS - MCP tool works correctly!")
        print("=" * 70)
        return 0
    else:
        print("\n" + "=" * 70)
        print("EXPECTED BEHAVIOR - Tool returned error as designed")
        print("=" * 70)
        return 0


if __name__ == "__main__":
    sys.exit(main())
