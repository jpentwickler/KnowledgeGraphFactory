"""
Interactive test for US014: Competency Question Evaluation

Prerequisites:
- US008 domain graph built (CSV -> Neo4j)
- US009 text graph built (Markdown -> Neo4j)
- Approved competency questions in state

Demonstrates all evaluation modes:
1. Evaluate all approved CQs (coverage scorecard)
2. Evaluate a single CQ by ID
3. Evaluate a subset of CQs
"""

import json
from core.state import load_state
from utils import get_neo4j_driver, close_driver


# Fallback CQs for testing when state has none
FALLBACK_CQS = {
    "CQ1": {
        "question": "What products would be affected if supplier X has disruptions?",
        "category": "supply_chain_impact",
        "priority": "high",
    },
    "CQ2": {
        "question": "Which suppliers provide the most components across all product lines?",
        "category": "sourcing_optimization",
        "priority": "high",
    },
    "CQ3": {
        "question": "What is the average customer sentiment for products from supplier X?",
        "category": "cross_analysis",
        "priority": "medium",
    },
    "CQ4": {
        "question": "Which locations have the highest delivery delays?",
        "category": "logistics",
        "priority": "low",
    },
    "CQ5": {
        "question": "What quality issues are most frequently reported for specific product categories?",
        "category": "quality_analysis",
        "priority": "high",
    },
}


def evaluate_all(state, driver):
    """Evaluate all approved CQs and show coverage scorecard."""
    from mcp_server.server import _evaluate_single_cq, _PRIORITY_ORDER

    cqs = state.get("approved_competency_questions", {})
    if not cqs:
        print("[ERROR] No approved competency questions in state.")
        return

    print(f"\nEvaluating {len(cqs)} competency questions...\n")

    results = []
    answerable = 0
    partial = 0
    not_answerable = 0

    for cq_id, cq_data in cqs.items():
        question = cq_data["question"]
        priority = cq_data.get("priority", "medium")

        print(f"  Evaluating {cq_id}...", end=" ", flush=True)
        eval_result = _evaluate_single_cq(driver, question, state)

        evidence_count = eval_result["evidence_count"]
        has_bridge = eval_result["has_cross_layer_bridge"]

        if evidence_count > 2 and has_bridge:
            status = "answerable"
            answerable += 1
            print(f"[OK] {evidence_count} evidence, bridge=True")
        elif evidence_count > 0:
            status = "partial"
            partial += 1
            print(f"[PARTIAL] {evidence_count} evidence, bridge={has_bridge}")
        else:
            status = "not_answerable"
            not_answerable += 1
            print(f"[FAIL] 0 evidence")

        results.append({
            "cq_id": cq_id,
            "question": question,
            "priority": priority,
            "status": status,
            "evidence_count": evidence_count,
            "has_cross_layer_bridge": has_bridge,
            "strategies_tried": eval_result["strategies_tried"],
        })

    # Sort by priority, then CQ ID
    results.sort(key=lambda r: (_PRIORITY_ORDER.get(r["priority"], 99), r["cq_id"]))

    total = len(results)
    coverage = (answerable + 0.5 * partial) / total if total > 0 else 0

    print(f"\n{'=' * 60}")
    print(f"Coverage Scorecard")
    print(f"{'=' * 60}")
    print(f"Total: {total}")
    print(f"Answerable: {answerable}")
    print(f"Partial: {partial}")
    print(f"Not Answerable: {not_answerable}")
    print(f"Coverage Score: {coverage:.1%}")
    print(f"\nPer-CQ Results:")
    for r in results:
        icon = {"answerable": "[OK]", "partial": "[PARTIAL]", "not_answerable": "[FAIL]"}[r["status"]]
        q = r["question"][:55] + "..." if len(r["question"]) > 55 else r["question"]
        print(f"  {icon} {r['cq_id']} ({r['priority']}): {q} ({r['evidence_count']} evidence)")


def evaluate_single(state, driver, cq_id):
    """Evaluate a single CQ by ID."""
    from mcp_server.server import _evaluate_single_cq

    cqs = state.get("approved_competency_questions", {})
    if cq_id not in cqs:
        print(f"[ERROR] CQ ID '{cq_id}' not found. Available: {', '.join(sorted(cqs.keys()))}")
        return

    cq_data = cqs[cq_id]
    print(f"\nEvaluating {cq_id}: {cq_data['question']}")
    print(f"Category: {cq_data.get('category', 'unknown')}, Priority: {cq_data.get('priority', 'medium')}")

    result = _evaluate_single_cq(driver, cq_data["question"], state)

    print(f"\nStrategies tried: {', '.join(result['strategies_tried']) or 'none'}")
    print(f"Evidence count: {result['evidence_count']}")
    print(f"Cross-layer bridge: {'Yes' if result['has_cross_layer_bridge'] else 'No'}")

    if result["evidence_count"] > 2 and result["has_cross_layer_bridge"]:
        print(f"Status: ANSWERABLE")
    elif result["evidence_count"] > 0:
        print(f"Status: PARTIAL")
    else:
        print(f"Status: NOT ANSWERABLE")

    if result["evidence"]:
        print(f"\nSample evidence ({len(result['evidence'])} items):")
        for i, e in enumerate(result["evidence"][:3]):
            content = str(e.get("content", ""))[:100]
            score = e.get("score", 0)
            print(f"  [{i+1}] Score: {score:.3f} - {content}...")


def evaluate_subset(state, driver, cq_ids_str):
    """Evaluate a subset of CQs."""
    cq_ids = [cid.strip() for cid in cq_ids_str.split(",")]
    cqs = state.get("approved_competency_questions", {})

    valid_ids = [cid for cid in cq_ids if cid in cqs]
    if not valid_ids:
        print(f"[ERROR] No valid CQ IDs found. Available: {', '.join(sorted(cqs.keys()))}")
        return

    print(f"\nEvaluating subset: {', '.join(valid_ids)}")
    for cq_id in valid_ids:
        evaluate_single(state, driver, cq_id)
        print()


def main():
    """Run interactive CQ evaluation test."""
    print("\n" + "=" * 60)
    print("US014: Competency Question Evaluation - Interactive Test")
    print("=" * 60)

    # Load state
    state = load_state()

    # Check for approved CQs, use fallback if none
    if "approved_competency_questions" not in state:
        print("\nNo approved CQs in state. Using fallback CQs for testing.")
        state["approved_competency_questions"] = FALLBACK_CQS

    cqs = state["approved_competency_questions"]
    print(f"\nApproved CQs ({len(cqs)}):")
    for cq_id, cq_data in sorted(cqs.items()):
        print(f"  {cq_id} ({cq_data.get('priority', '?')}): {cq_data['question'][:60]}...")

    print("\nCommands:")
    print("  all              - Evaluate all approved CQs")
    print("  single CQ1       - Evaluate single CQ by ID")
    print("  subset CQ1,CQ3   - Evaluate specific CQs")
    print("  state            - Show current state summary")
    print("  quit             - Exit")

    driver = None
    try:
        driver = get_neo4j_driver()
        print("\n[OK] Connected to Neo4j")
    except Exception as e:
        print(f"\n[ERROR] Neo4j connection failed: {e}")
        print("Some tests will fail without Neo4j.")
        return

    try:
        while True:
            cmd = input("\n> ").strip()

            if not cmd:
                continue

            if cmd.lower() == "quit":
                break

            if cmd.lower() == "state":
                print(json.dumps({
                    "approved_cqs": len(state.get("approved_competency_questions", {})),
                    "domain_graph": "approved_construction_plan" in state,
                    "text_graph": "text_graph_progress" in state,
                    "entity_types": list(state.get("approved_entity_types", {}).keys())[:5],
                    "cq_evaluation_results": bool(state.get("cq_evaluation_results")),
                }, indent=2))
                continue

            if cmd.lower() == "all":
                evaluate_all(state, driver)
                continue

            if cmd.lower().startswith("single "):
                cq_id = cmd.split(" ", 1)[1].strip()
                evaluate_single(state, driver, cq_id)
                continue

            if cmd.lower().startswith("subset "):
                cq_ids_str = cmd.split(" ", 1)[1].strip()
                evaluate_subset(state, driver, cq_ids_str)
                continue

            print(f"Unknown command: {cmd}")
            print("Use: all, single CQ1, subset CQ1,CQ3, state, quit")

    finally:
        if driver:
            close_driver(driver)
            print("\n[OK] Neo4j connection closed")


if __name__ == "__main__":
    main()
