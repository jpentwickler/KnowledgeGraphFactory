"""
Interactive test for US013: Query Infrastructure & kg_query Tool

Prerequisites:
- US008 domain graph built (CSV -> Neo4j)
- US009 text graph built (Markdown -> Neo4j)
- Both graphs built for comprehensive testing

Tests all 5 retrieval strategies:
1. schema - Graph structure exploration
2. cypher - Structured Cypher queries
3. vector - Semantic similarity search
4. hybrid - Vector + keyword search
5. cross_layer - Semantic search + domain entity traversal
"""

import asyncio
import json
from utils import get_neo4j_driver, close_driver
from core.state import load_state
from pipelines.query_builder import (
    _select_retrieval_strategy,
    _execute_schema_query,
    _execute_cypher,
    _execute_vector_search,
    _execute_hybrid_search,
    _execute_cross_layer_traversal,
)


# Test questions for each strategy
TEST_QUESTIONS = {
    "schema": [
        "What labels exist in the graph?",
        "Show me the graph structure",
        "What types of nodes are in the database?",
    ],
    "cypher": [
        "MATCH (n) RETURN labels(n) as label, count(n) as count",
        "MATCH (s:Supplier) RETURN s.name LIMIT 5",
        "MATCH ()-[r]->() RETURN type(r), count(*) ORDER BY count(*) DESC",
    ],
    "vector": [
        "Tell me about supply chain delays",
        "What are the quality issues mentioned?",
        "Information about logistics and shipping",
    ],
    "hybrid": [
        "Documents about quality control",
        "Supplier performance reviews",
        "Delivery time analysis",
    ],
    "cross_layer": [
        "Which suppliers are mentioned in quality reviews?",
        "What products are discussed in customer feedback?",
        "Which locations are mentioned in delivery reports?",
    ],
}


async def test_strategy_selection():
    """Test Claude-powered strategy selection."""
    print("\n" + "=" * 80)
    print("TEST 1: Strategy Selection")
    print("=" * 80)

    state = load_state()
    driver = get_neo4j_driver()

    try:
        for strategy_name, questions in TEST_QUESTIONS.items():
            print(f"\n--- Expected Strategy: {strategy_name.upper()} ---")
            for question in questions[:1]:  # Test one per strategy
                print(f"\nQuestion: {question}")

                result = await _select_retrieval_strategy(question, "", state)
                print(f"Selected: {result['strategy']}")
                print(f"Reasoning: {result['reasoning']}")

                if result["strategy"] == strategy_name:
                    print("[OK] Strategy matches expected")
                else:
                    print(f"[WARN] Expected {strategy_name}, got {result['strategy']}")

    finally:
        close_driver(driver)


async def test_schema_query():
    """Test schema query execution."""
    print("\n" + "=" * 80)
    print("TEST 2: Schema Query")
    print("=" * 80)

    state = load_state()
    driver = get_neo4j_driver()

    try:
        result = _execute_schema_query(driver, state)

        print("\n--- Schema Query Result ---")
        print(result["answer"])
        print(f"\nConfidence: {result['confidence']}")
        print(f"Strategy: {result['details']['strategy']}")
        print(f"Total labels: {result['details']['total_labels']}")

        if result["confidence"] == 1.0:
            print("[OK] Schema query confidence is 1.0 (deterministic)")
        else:
            print(f"[FAIL] Expected confidence 1.0, got {result['confidence']}")

    finally:
        close_driver(driver)


async def test_cypher_query():
    """Test Cypher query execution with safety validation."""
    print("\n" + "=" * 80)
    print("TEST 3: Cypher Query")
    print("=" * 80)

    driver = get_neo4j_driver()

    try:
        # Test safe query
        safe_query = "MATCH (n) RETURN labels(n) as label, count(*) as count LIMIT 5"
        print(f"\n--- Safe Query ---")
        print(f"Query: {safe_query}")

        result = _execute_cypher(driver, safe_query)
        print(result["answer"])
        print(f"\nConfidence: {result['confidence']}")
        print("[OK] Safe query executed successfully")

        # Test blocked mutation
        print(f"\n--- Blocked Mutation ---")
        mutation_query = "CREATE (n:TestNode {name: 'test'})"
        print(f"Query: {mutation_query}")

        try:
            result = _execute_cypher(driver, mutation_query)
            print("[FAIL] Mutation query should have been blocked")
        except ValueError as e:
            print(f"[OK] Mutation blocked: {str(e)[:80]}...")

    finally:
        close_driver(driver)


async def test_vector_search():
    """Test vector search (requires OPENAI_API_KEY and indexes)."""
    print("\n" + "=" * 80)
    print("TEST 4: Vector Search")
    print("=" * 80)

    import os
    if not os.environ.get("OPENAI_API_KEY"):
        print("[SKIP] OPENAI_API_KEY not set")
        return

    driver = get_neo4j_driver()

    try:
        question = "supply chain delays and logistics issues"
        print(f"\nQuestion: {question}")

        result = _execute_vector_search(driver, question, top_k=3)

        print(f"\n--- Vector Search Results ---")
        print(result["answer"])
        print(f"\nConfidence: {result['confidence']}")
        print(f"Results: {result['details']['result_count']}")
        print("[OK] Vector search executed successfully")

    except RuntimeError as e:
        print(f"[ERROR] {str(e)}")
    finally:
        close_driver(driver)


async def test_hybrid_search():
    """Test hybrid search (requires OPENAI_API_KEY and indexes)."""
    print("\n" + "=" * 80)
    print("TEST 5: Hybrid Search")
    print("=" * 80)

    import os
    if not os.environ.get("OPENAI_API_KEY"):
        print("[SKIP] OPENAI_API_KEY not set")
        return

    driver = get_neo4j_driver()

    try:
        question = "quality control supplier"
        print(f"\nQuestion: {question}")

        result = _execute_hybrid_search(driver, question, top_k=3)

        print(f"\n--- Hybrid Search Results ---")
        print(result["answer"])
        print(f"\nConfidence: {result['confidence']}")
        print(f"Results: {result['details']['result_count']}")
        print("[OK] Hybrid search executed successfully")

    except RuntimeError as e:
        print(f"[ERROR] {str(e)}")
    finally:
        close_driver(driver)


async def test_cross_layer_traversal():
    """Test cross-layer traversal (requires both graph layers)."""
    print("\n" + "=" * 80)
    print("TEST 6: Cross-Layer Traversal")
    print("=" * 80)

    import os
    if not os.environ.get("OPENAI_API_KEY"):
        print("[SKIP] OPENAI_API_KEY not set")
        return

    state = load_state()
    driver = get_neo4j_driver()

    try:
        question = "which suppliers are mentioned in reviews"
        print(f"\nQuestion: {question}")

        result = _execute_cross_layer_traversal(driver, question, top_k=3, state=state)

        print(f"\n--- Cross-Layer Traversal Results ---")
        print(result["answer"])
        print(f"\nConfidence: {result['confidence']}")
        print(f"Results: {result['details']['result_count']}")
        print(f"Domain labels: {result['details']['domain_labels']}")
        print("[OK] Cross-layer traversal executed successfully")

    except RuntimeError as e:
        print(f"[ERROR] {str(e)}")
    finally:
        close_driver(driver)


async def interactive_mode():
    """Interactive query testing."""
    print("\n" + "=" * 80)
    print("INTERACTIVE MODE")
    print("=" * 80)
    print("Enter questions to test adaptive retrieval.")
    print("Commands: 'quit' to exit, 'state' to show state")
    print("=" * 80)

    state = load_state()

    while True:
        question = input("\nQuestion: ").strip()

        if question.lower() == 'quit':
            break

        if question.lower() == 'state':
            print(json.dumps({
                "domain_graph": "approved_construction_plan" in state,
                "text_graph": "text_graph_progress" in state,
                "entity_types": list(state.get("approved_entity_types", {}).keys())[:5],
            }, indent=2))
            continue

        if not question:
            continue

        driver = get_neo4j_driver()
        try:
            # Select strategy
            strategy_data = await _select_retrieval_strategy(question, "", state)
            print(f"\nStrategy: {strategy_data['strategy']}")
            print(f"Reasoning: {strategy_data['reasoning']}")

            # Execute strategy
            strategy = strategy_data["strategy"]
            params = strategy_data.get("parameters", {})

            if strategy == "schema":
                result = _execute_schema_query(driver, state)
            elif strategy == "cypher":
                result = _execute_cypher(driver, params["cypher_query"])
            elif strategy == "vector":
                result = _execute_vector_search(driver, question, params.get("top_k", 5))
            elif strategy == "hybrid":
                result = _execute_hybrid_search(driver, question, params.get("top_k", 5))
            elif strategy == "cross_layer":
                result = _execute_cross_layer_traversal(driver, question, params.get("top_k", 5), state)

            print(f"\n{result['answer']}")
            print(f"\nConfidence: {result['confidence']}")

        except Exception as e:
            print(f"\n[ERROR] {str(e)}")
        finally:
            close_driver(driver)


async def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("US013: Query Infrastructure & kg_query Tool - Interactive Test")
    print("=" * 80)

    choice = input("\nRun mode:\n  1. All tests\n  2. Interactive only\n  3. Strategy selection only\n\nChoice: ").strip()

    if choice == "1":
        await test_strategy_selection()
        await test_schema_query()
        await test_cypher_query()
        await test_vector_search()
        await test_hybrid_search()
        await test_cross_layer_traversal()
        print("\n" + "=" * 80)
        print("All tests complete!")
        print("=" * 80)
    elif choice == "2":
        await interactive_mode()
    elif choice == "3":
        await test_strategy_selection()
    else:
        print("Invalid choice. Exiting.")


if __name__ == "__main__":
    asyncio.run(main())
