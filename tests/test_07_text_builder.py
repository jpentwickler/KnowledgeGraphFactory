"""Text Graph Builder test.

Tests the Markdown -> Neo4j (Subject + Lexical) pipeline and entity resolution.

Usage:
    python -m tests.test_07_text_builder

Requirements:
    - Stages 1-5 must be completed (all approved artifacts in state)
    - Neo4j instance must be running and accessible
    - Environment variables set (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, OPENAI_API_KEY)
    - APOC plugin installed in Neo4j (for entity resolution)
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from core import load_state
from pipelines.entity_resolution import resolve_entities
from pipelines.text_builder import build_entity_schema, build_text_graph
from utils.neo4j_utils import close_driver, get_neo4j_driver, test_connection


def main():
    """Run text graph builder test."""
    # Find state file
    possible_state_files = [
        "state_after_fact_extraction.json",
        "examples/furniture_supply_chain/state/current_state.json",
        "examples/furniture_supply_chain/state_after_fact_extraction.json",
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
        print("\nPlease run Stages 1-5 first to generate a state file")
        print("with all approved artifacts.")
        return 1

    print("=" * 70)
    print("TEXT GRAPH BUILDER - Stage 7 Test")
    print("=" * 70)

    print(f"\n[Config] Loading state from: {state_file}")
    state = load_state(state_file)

    # Check prerequisites
    missing = []
    if "approved_entity_types" not in state:
        missing.append("approved_entity_types (Stage 4)")
    if "approved_fact_types" not in state:
        missing.append("approved_fact_types (Stage 5)")
    if not state.get("approved_files", {}).get("unstructured", []):
        missing.append("unstructured files in approved_files (Stage 2)")

    if missing:
        print("\n[ERROR] Missing prerequisites:")
        for m in missing:
            print(f"  - {m}")
        return 1

    # Show entity schema
    schema = build_entity_schema(state)
    print(f"\n[Config] Entity schema:")
    print(f"  Node types: {schema['node_types']}")
    print(f"  Relationship types: {schema['relationship_types']}")
    print(f"  Patterns: {schema['patterns']}")

    # Show files
    unstructured = state["approved_files"]["unstructured"]
    print(f"\n[Config] Unstructured files: {len(unstructured)}")
    for f in unstructured:
        print(f"  - {f['path']}")

    # Check environment
    if not os.environ.get("OPENAI_API_KEY"):
        print("\n[ERROR] OPENAI_API_KEY not set.")
        print("Required for entity extraction and embeddings.")
        return 1

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
        print("  2. Environment variables are set")
        print("  3. Credentials are correct")
        return 1

    # Optional: Clear existing text graph nodes
    print("\n[Optional] Clear existing __Entity__ and __Chunk__ nodes? (y/n): ", end="")
    response = input().strip().lower()

    if response == "y":
        print("  Clearing text graph nodes...")
        with driver.session() as session:
            session.run("MATCH (n) WHERE n:`__Entity__` OR n:`__Chunk__` DETACH DELETE n")
        print("  Text graph nodes cleared.")
    else:
        print("  Skipping clear.")

    # Phase 1: Process first file only
    print("\n" + "=" * 70)
    print("PHASE 1: Process first markdown file")
    print("=" * 70)

    first_file = unstructured[0]["path"]
    print(f"\nProcessing: {first_file}")

    try:
        results = asyncio.run(build_text_graph(state, driver, message=first_file))
    except Exception as exc:
        print(f"\n[ERROR] Text graph build failed: {exc}")
        close_driver(driver)
        return 1

    print("\nResults:")
    print(f"  Files processed: {results['files_processed']}")
    print(f"  Errors: {results['errors']}")
    print(f"  Progress: {results['progress']['total_processed']} processed, "
          f"{results['progress']['total_pending']} pending")

    if results["errors"]:
        print("\n[WARNING] Errors occurred during processing.")
        for err in results["errors"]:
            print(f"  - {err}")

    # Ask to continue
    if results["progress"]["total_pending"] > 0:
        print(f"\n[Optional] Process remaining {results['progress']['total_pending']} files? (y/n): ", end="")
        response = input().strip().lower()

        if response == "y":
            print("\n" + "=" * 70)
            print("PHASE 2: Process remaining files")
            print("=" * 70)

            try:
                remaining_results = asyncio.run(build_text_graph(state, driver, message="all"))
            except Exception as exc:
                print(f"\n[ERROR] Text graph build failed: {exc}")
                close_driver(driver)
                return 1

            print("\nResults:")
            print(f"  Files processed: {remaining_results['files_processed']}")
            print(f"  Errors: {remaining_results['errors']}")
            print(f"  Progress: {remaining_results['progress']['total_processed']} processed, "
                  f"{remaining_results['progress']['total_pending']} pending")

    # Phase 3: Entity Resolution
    print("\n" + "=" * 70)
    print("PHASE 3: Entity Resolution")
    print("=" * 70)

    print("\nRun entity resolution to connect subject graph to domain graph? (y/n): ", end="")
    response = input().strip().lower()

    if response == "y":
        try:
            resolution = resolve_entities(state, driver)
        except Exception as exc:
            print(f"\n[ERROR] Entity resolution failed: {exc}")
            if "apoc" in str(exc).lower() or "unknown function" in str(exc).lower():
                print("\nHINT: APOC plugin may not be installed in your Neo4j instance.")
                print("Entity resolution requires apoc.text.jaroWinklerDistance.")
            close_driver(driver)
            return 1

        print("\nResults:")
        print(f"  Labels checked: {resolution['labels_checked']}")
        print(f"  Labels resolved: {resolution['labels_resolved']}")
        print(f"  Total CORRESPONDS_TO: {resolution['total_correspondences']}")

        print("\n  Per-label details:")
        for result in resolution["per_label_results"]:
            label = result["label"]
            status = result["status"]
            if status == "resolved":
                print(
                    f"    [OK] {label}: {result['entity_key']} <-> {result['domain_key']} "
                    f"({result['relationships_created']} correspondences)"
                )
            elif status == "error":
                print(f"    [FAIL] {label}: {result['error']}")
            else:
                print(f"    [SKIP] {label}: {result.get('message', status)}")

    # Verification queries
    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)

    with driver.session() as session:
        # Entity counts
        result = session.run(
            "MATCH (n:`__Entity__`) "
            "WITH labels(n) as lbls "
            "UNWIND lbls as lbl "
            "WITH lbl WHERE NOT lbl STARTS WITH '__' "
            "RETURN lbl as label, count(*) as count "
            "ORDER BY count DESC"
        )
        print("\nEntity counts by label:")
        for record in result:
            print(f"  {record['label']}: {record['count']}")

        # Chunk count
        result = session.run("MATCH (n:`__Chunk__`) RETURN count(n) as count")
        record = result.single()
        print(f"\nChunk nodes: {record['count'] if record else 0}")

        # CORRESPONDS_TO count
        result = session.run(
            "MATCH ()-[r:CORRESPONDS_TO]->() RETURN count(r) as count"
        )
        record = result.single()
        print(f"CORRESPONDS_TO relationships: {record['count'] if record else 0}")

    # Success
    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)
    print("\nYou can explore the graph in Neo4j Browser:")
    print("  // View entities")
    print("  MATCH (n:`__Entity__`) RETURN n LIMIT 25")
    print("  // View chunks")
    print("  MATCH (n:`__Chunk__`) RETURN n LIMIT 10")
    print("  // View CORRESPONDS_TO")
    print("  MATCH (e)-[r:CORRESPONDS_TO]->(d) RETURN e, r, d LIMIT 25")
    print("  // Full schema")
    print("  CALL db.schema.visualization()")

    # Cleanup
    close_driver(driver)

    # Save state with progress
    state_out = state_file.replace(".json", "_with_text_graph.json")
    print(f"\n[Config] Saving state to: {state_out}")
    with open(state_out, "w") as f:
        json.dump(state, f, indent=2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
