"""Domain Graph Builder test.

Tests the CSV → Neo4j import pipeline with three-layer validation.

Usage:
    python -m tests.test_06_domain_builder

Requirements:
    - Stage 3 must be completed (approved_construction_plan in state)
    - Neo4j instance must be running and accessible
    - Environment variables set (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
"""

import json
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from pipelines.domain_builder import build_domain_graph
from utils.neo4j_utils import get_neo4j_driver, test_connection, close_driver
from core import load_state


def main():
    """Run domain graph builder test."""
    # Configuration
    # Try to find a state file from Stage 3
    possible_state_files = [
        "state_after_schema_proposal.json",
        "examples/furniture_supply_chain/state_after_schema_proposal.json",
        "state.json",
    ]

    state_file = None
    for path in possible_state_files:
        if os.path.exists(path):
            state_file = path
            break

    if not state_file:
        print("=" * 70)
        print("ERROR: No state file found")
        print("=" * 70)
        print("\nSearched for:")
        for path in possible_state_files:
            print(f"  - {path}")
        print("\nPlease run Stage 3 (Schema Proposal) first to generate a state file")
        print("with approved_construction_plan.")
        return 1

    print("=" * 70)
    print("DOMAIN GRAPH BUILDER - Stage 6 Test")
    print("=" * 70)

    print(f"\n[Config] Loading state from: {state_file}")
    state = load_state(state_file)

    if "approved_construction_plan" not in state:
        print("\n[ERROR] No approved_construction_plan in state.")
        print("Please complete Stage 3 (Schema Proposal) first.")
        return 1

    plan = state["approved_construction_plan"]
    print(f"[Config] Found construction plan with {len(plan)} items")

    # Display plan summary
    node_specs = [
        spec for spec in plan.values() if spec["construction_type"] == "node"
    ]
    rel_specs = [
        spec for spec in plan.values() if spec["construction_type"] == "relationship"
    ]
    print(f"  - Node types: {len(node_specs)}")
    print(f"  - Relationship types: {len(rel_specs)}")

    # Connect to Neo4j
    print("\n[Pre-flight] Testing Neo4j connection...")
    try:
        driver = get_neo4j_driver()
        conn_info = test_connection(driver)
        print(f"  Connected to Neo4j {conn_info['neo4j_version']}")
        print(f"  Edition: {conn_info['edition']}")
        print(f"  Database: {conn_info['database']}")
    except Exception as exc:
        print(f"\n[ERROR] Failed to connect to Neo4j: {exc}")
        print("\nMake sure:")
        print("  1. Neo4j is running")
        print("  2. Environment variables are set (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)")
        print("  3. Credentials are correct")
        return 1

    # Optional: Clear graph for clean test
    print("\n[Optional] Clear existing graph before import?")
    print("  Type 'yes' to clear, or press Enter to skip: ", end="")
    response = input().strip().lower()

    if response == "yes":
        print("  Clearing graph...")
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        print("  Graph cleared.")
    else:
        print("  Skipping clear - will merge into existing graph.")

    # Build domain graph
    print("\n" + "=" * 70)
    print("BUILDING DOMAIN GRAPH")
    print("=" * 70)

    try:
        results = build_domain_graph(state, driver)
    except Exception as exc:
        print(f"\n[ERROR] Domain graph build failed: {exc}")
        close_driver(driver)
        return 1

    # Display results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    print("\nNodes Imported:")
    if results["nodes"]:
        for node_result in results["nodes"]:
            status = "[OK]" if not node_result["errors"] else "[FAIL]"
            print(f"  {status} {node_result['label']}: {node_result['count']} nodes")
            for error in node_result["errors"]:
                print(f"      Error: {error}")
    else:
        print("  (none)")

    print("\nRelationships Imported:")
    if results["relationships"]:
        for rel_result in results["relationships"]:
            status = "[OK]" if not rel_result["errors"] else "[FAIL]"
            orphan_note = ""
            if rel_result.get("orphans", 0) > 0:
                orphan_note = f" (WARNING: {rel_result['orphans']} orphans)"

            print(
                f"  {status} {rel_result['type']}: {rel_result['count']} relationships{orphan_note}"
            )
            for error in rel_result["errors"]:
                print(f"      Error: {error}")
    else:
        print("  (none)")

    print("\nVerification:")
    verification = results["verification"]
    print(f"  Total nodes: {verification['total_nodes']}")
    print(f"  Total relationships: {verification['total_relationships']}")
    print(f"  Orphan nodes (no relationships): {verification['orphan_nodes']}")

    print("\n  Node counts by label:")
    for label, count in verification["node_counts"].items():
        print(f"    {label}: {count}")

    print("\n  Relationship counts by type:")
    for rel_type, count in verification["relationship_counts"].items():
        print(f"    {rel_type}: {count}")

    # Check for errors
    if results["errors"]:
        print("\n" + "=" * 70)
        print("ERRORS ENCOUNTERED")
        print("=" * 70)
        for error in results["errors"]:
            print(f"  - {error}")
        print("\n[FAIL] Domain graph build completed with errors.")
        close_driver(driver)
        return 1

    # Success!
    print("\n" + "=" * 70)
    print("SUCCESS - Domain Graph Built!")
    print("=" * 70)
    print("\nYou can now explore the graph in Neo4j Browser:")
    print("  - Check node counts: MATCH (n) RETURN labels(n), count(*)")
    print("  - Check relationships: MATCH ()-[r]->() RETURN type(r), count(*)")
    print("  - View sample: MATCH (n) RETURN n LIMIT 25")

    # Cleanup
    close_driver(driver)
    return 0


if __name__ == "__main__":
    sys.exit(main())
