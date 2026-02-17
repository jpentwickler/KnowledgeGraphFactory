# US014: Competency Question Evaluation

## User Story

**As a** KG-Factory User
**I want** to evaluate my approved competency questions (individually or as a batch) to measure how well my knowledge graph covers my requirements
**So that** I can identify gaps in my graph, track coverage improvements over time, and validate that my graph meets its design goals

## Story Points: 5

## Status: Not Started

## Acceptance Criteria

### kg_evaluate_cqs MCP Tool

- [ ] Tool signature: `kg_evaluate_cqs(cq_id: str = "", cq_ids: list[str] = None)`
- [ ] Tool description clearly states it works ONLY with approved CQs (no ad-hoc questions)
- [ ] Three evaluation modes:
  - No parameters: Evaluate ALL approved CQs (full coverage report)
  - `cq_id` provided: Evaluate single approved CQ by ID
  - `cq_ids` provided: Evaluate specific subset of approved CQs
- [ ] Rejects ad-hoc questions with clear error: "This tool works with approved CQs only. For ad-hoc questions, use kg_query."
- [ ] Decorated with `@mcp.tool` and `@mcp_traceable(name="mcp.kg_evaluate_cqs")`

### Single CQ Evaluation

When evaluating a single CQ (via `cq_id`):

- [ ] Reads CQ from `state["approved_competency_questions"][cq_id]`
- [ ] Returns error if CQ ID not found in approved CQs
- [ ] Uses `kg_query` internally (calls `_select_retrieval_strategy` and executes)
- [ ] Gathers evidence WITHOUT synthesizing an answer (collects evidence only)
- [ ] Returns individual assessment:
  ```python
  {
    "cq_id": str,
    "question": str,
    "category": str,
    "priority": str,
    "evidence_found": bool,
    "strategies_tried": [str],
    "evidence_count": int,
    "has_cross_layer_bridge": bool,
    "assessment": {
      "status": "answerable" | "partial" | "not_answerable",
      "note": str
    }
  }
  ```
- [ ] Classification logic:
  - `answerable`: evidence_count > 2 AND has_cross_layer_bridge
  - `partial`: evidence_count > 0 but not enough for answerable
  - `not_answerable`: evidence_count == 0

### Batch CQ Evaluation

When evaluating multiple CQs (via `cq_ids` or no parameters):

- [ ] Iterates through each CQ, evaluating via single CQ logic
- [ ] Returns coverage scorecard:
  ```python
  {
    "total": int,
    "answerable": int,
    "partial": int,
    "not_answerable": int,
    "coverage_score": float,  # (answerable + 0.5*partial) / total
    "per_cq_results": [
      {
        "cq_id": str,
        "question": str,
        "category": str,
        "priority": str,
        "status": "answerable" | "partial" | "not_answerable",
        "evidence_count": int
      },
      ...
    ]
  }
  ```
- [ ] Coverage score formula: `(answerable + 0.5 * partial) / total`
- [ ] Results sorted by priority (high first), then by CQ ID

### State Persistence

- [ ] Stores full evaluation results in `state["cq_evaluation_results"]`
- [ ] Includes timestamp in ISO 8601 format (UTC)
- [ ] Persisted structure:
  ```python
  {
    "timestamp": "2026-02-16T10:30:00Z",
    "total": int,
    "answerable": int,
    "partial": int,
    "not_answerable": int,
    "coverage_score": float,
    "per_cq_results": [...]
  }
  ```
- [ ] Uses `_save_state()` to persist after evaluation
- [ ] Historical results are overwritten (not appended) - latest evaluation only

### Integration with kg_query

- [ ] Reuses `_select_retrieval_strategy()` from US013
- [ ] Reuses `_execute_*()` strategy functions from US013
- [ ] Does NOT call `kg_query` MCP tool directly (uses internal functions to avoid redundant state loads)
- [ ] Collects evidence from multiple strategies (tries auto strategy selection)
- [ ] Does NOT synthesize answers (evidence gathering only)

### Error Handling

- [ ] No approved CQs: Clear error with guidance to use `kg_user_intent` or `kg_competency_questions`
- [ ] CQ ID not found: Error with list of valid CQ IDs
- [ ] Empty `cq_ids` list: Treats as "evaluate all"
- [ ] Neo4j connection failures: Actionable error messages
- [ ] Missing indexes: Warns but attempts evaluation (some strategies may fail gracefully)

### Response Formatting

For batch evaluation, format response as:

```
Competency Question Evaluation: 8 questions

Answerable: 5
Partial: 2
Not Answerable: 1
Coverage Score: 75.0%

Per-CQ Results:
  [OK] CQ1: Which suppliers provide parts for the Stockholm Chair? (12 evidence)
  [OK] CQ2: What quality issues have been reported for products? (8 evidence)
  [PARTIAL] CQ3: Which supplier's parts are most mentioned in negative reviews? (3 evidence)
  [FAIL] CQ4: What is the average lead time for international suppliers? (0 evidence)
  ...
```

### Integration Patterns

- [ ] Follows existing MCP tool pattern (same as `kg_build_graph`, `kg_user_intent`)
- [ ] Uses `_load_clean_state()` and `_save_state()` from mcp_server
- [ ] Uses `utils.get_neo4j_driver()` and `utils.close_driver()` (existing pattern)
- [ ] Uses `core.tracing.mcp_traceable` for observability (US011 pattern)
- [ ] Loads state once, evaluates all CQs, saves once (efficient)

## Definition of Done

- [ ] Code implemented and working
- [ ] Unit tests for single CQ evaluation logic
- [ ] Unit tests for batch evaluation logic
- [ ] Unit tests for coverage score calculation
- [ ] Unit tests for state persistence
- [ ] Integration test: `test_09_cq_evaluation.py` demonstrates all modes
- [ ] All existing tests still pass (including US013 tests)
- [ ] MCP tool works from Claude Code
- [ ] State persistence verified (results persist across tool calls)
- [ ] Observability verified (traces visible in LangSmith if enabled)
- [ ] Code reviewed
- [ ] Documentation in code (docstrings for all functions)

## Technical Notes

### Architecture

```
kg_evaluate_cqs(cq_id?, cq_ids?)
  |
  +-> _load_clean_state()                      # Get approved CQs
  |
  +-> Determine which CQs to evaluate:
  |     - cq_id provided?     -> Single CQ
  |     - cq_ids provided?    -> Specific subset
  |     - Neither provided?   -> All approved CQs
  |
  +-> get_neo4j_driver()
  |
  +-> For each CQ:
  |     +-> _evaluate_single_cq(driver, question)
  |           |
  |           +-> _select_retrieval_strategy()    # From US013
  |           +-> _execute_*(driver, question)    # From US013
  |           +-> Collect evidence (no answer synthesis)
  |           +-> Classify: answerable/partial/not_answerable
  |
  +-> close_driver()                           # Always in finally
  |
  +-> Calculate metrics:
  |     - Total, answerable, partial, not_answerable
  |     - Coverage score: (answerable + 0.5*partial) / total
  |
  +-> Store in state["cq_evaluation_results"]
  +-> _save_state()
  |
  +-> Return: Single assessment OR coverage scorecard
```

### Files to Create

```
tests/
  test_09_cq_evaluation.py        # NEW: Interactive integration test
  unit/
    test_cq_evaluation.py         # NEW: Unit tests for evaluation logic
```

### Files to Modify

```
mcp_server/server.py              # UPDATE: Add kg_evaluate_cqs MCP tool
                                  #         Add _evaluate_single_cq() helper

pipelines/query_builder.py       # UPDATE: Add evaluate_single_cq() function
                                  #         (or keep as helper in mcp_server)
```

### Component Specifications

#### 1. kg_evaluate_cqs Tool (in `mcp_server/server.py`)

```python
@mcp.tool
@mcp_traceable(name="mcp.kg_evaluate_cqs")
def kg_evaluate_cqs(cq_id: str = "", cq_ids: list[str] = None) -> dict:
    """Evaluate approved competency questions from state.

    Tests if approved CQs are answerable by gathering evidence from the graph.
    Returns assessment metrics (not answers).

    Works with approved CQs only. For ad-hoc questions, use kg_query.

    Args:
        cq_id: Single approved CQ ID to evaluate (e.g., "CQ3")
        cq_ids: List of approved CQ IDs to evaluate (e.g., ["CQ1", "CQ3"])
                If neither provided: evaluates ALL approved CQs

    Returns:
        Single CQ: Individual assessment with evidence
        Multiple CQs: Coverage scorecard + per-CQ results
    """
    from datetime import datetime, timezone

    state = _load_clean_state()

    cqs = state.get("approved_competency_questions", {})
    if not cqs:
        return {
            "agent_response": "No approved competency questions to evaluate.\n\n"
                "Use kg_user_intent or kg_competency_questions first.",
            "status": {"error": "no_approved_cqs"},
        }

    # Determine which CQs to evaluate
    if cq_id:
        # Single CQ by ID
        if cq_id not in cqs:
            return {
                "agent_response": f"CQ ID '{cq_id}' not found in approved CQs.\n"
                    f"Available CQ IDs: {', '.join(cqs.keys())}",
                "status": {"error": "cq_not_found"},
            }
        cqs_to_evaluate = {cq_id: cqs[cq_id]}
        is_single = True
    elif cq_ids:
        # Specific subset of CQs
        cqs_to_evaluate = {cq_id: cqs[cq_id] for cq_id in cq_ids if cq_id in cqs}
        if not cqs_to_evaluate:
            return {
                "agent_response": "None of the provided CQ IDs found in approved CQs.\n"
                    f"Available CQ IDs: {', '.join(cqs.keys())}",
                "status": {"error": "cqs_not_found"},
            }
        is_single = False
    else:
        # All approved CQs
        cqs_to_evaluate = cqs
        is_single = False

    driver = get_neo4j_driver()
    try:
        results = []
        answerable = 0
        partial = 0
        not_answerable = 0

        for cq_id_iter, cq_data in cqs_to_evaluate.items():
            question = cq_data["question"]
            category = cq_data.get("category", "unknown")
            priority = cq_data.get("priority", "medium")

            # Evaluate this CQ
            eval_result = _evaluate_single_cq(driver, question, state)

            evidence_count = eval_result["evidence_count"]
            has_bridge = eval_result["has_cross_layer_bridge"]

            # Classify answerability
            if has_bridge and evidence_count > 2:
                status = "answerable"
                answerable += 1
            elif evidence_count > 0:
                status = "partial"
                partial += 1
            else:
                status = "not_answerable"
                not_answerable += 1

            results.append({
                "cq_id": cq_id_iter,
                "question": question,
                "category": category,
                "priority": priority,
                "status": status,
                "evidence_count": evidence_count,
                "has_cross_layer_bridge": has_bridge,
                "strategies_tried": eval_result.get("strategies_tried", []),
            })

        # Calculate metrics
        total = len(cqs_to_evaluate)
        coverage_score = (answerable + 0.5 * partial) / total if total > 0 else 0

        # Store results in state
        state["cq_evaluation_results"] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total": total,
            "answerable": answerable,
            "partial": partial,
            "not_answerable": not_answerable,
            "coverage_score": round(coverage_score, 3),
            "per_cq_results": results,
        }
        _save_state(state)

        # Return single assessment or coverage scorecard
        if is_single:
            # Single CQ assessment
            result = results[0]
            return {
                "agent_response": f"CQ Assessment: {result['cq_id']}\n\n"
                    f"Question: {result['question']}\n"
                    f"Status: {result['status'].upper()}\n"
                    f"Evidence: {result['evidence_count']} items\n"
                    f"Cross-layer bridge: {'Yes' if result['has_cross_layer_bridge'] else 'No'}",
                "status": {
                    "success": True,
                    **result
                }
            }
        else:
            # Coverage scorecard
            lines = [f"Competency Question Evaluation: {total} questions\n"]
            lines.append(f"Answerable: {answerable}")
            lines.append(f"Partial: {partial}")
            lines.append(f"Not Answerable: {not_answerable}")
            lines.append(f"Coverage Score: {coverage_score:.1%}\n")

            lines.append("Per-CQ Results:")
            for r in results:
                icon = "[OK]" if r["status"] == "answerable" else \
                       "[PARTIAL]" if r["status"] == "partial" else "[FAIL]"
                lines.append(
                    f"  {icon} {r['cq_id']}: {r['question'][:60]}... "
                    f"({r['evidence_count']} evidence)"
                )

            return {
                "agent_response": "\n".join(lines),
                "status": {
                    "success": True,
                    "total": total,
                    "answerable": answerable,
                    "partial": partial,
                    "not_answerable": not_answerable,
                    "coverage_score": coverage_score,
                },
                "results": results,
            }

    finally:
        close_driver(driver)
```

#### 2. Single CQ Evaluation Helper

```python
def _evaluate_single_cq(driver, question: str, state: dict) -> dict:
    """Evaluate a single CQ by gathering evidence from multiple strategies.

    Internal helper for kg_evaluate_cqs.

    Args:
        driver: Neo4j driver instance
        question: CQ question text
        state: Pipeline state (for schema context)

    Returns:
        Evidence summary with strategies_tried, evidence_count,
        has_cross_layer_bridge fields.
    """
    from pipelines.query_builder import (
        _select_retrieval_strategy,
        _execute_vector_search,
        _execute_hybrid_search,
        _execute_cross_layer_traversal,
    )

    # Try multiple strategies to gather evidence
    strategies_tried = []
    all_evidence = []
    has_cross_layer_bridge = False

    # Strategy 1: Vector search
    try:
        result = _execute_vector_search(driver, question, top_k=5)
        if result.get("evidence"):
            strategies_tried.append("vector")
            all_evidence.extend(result["evidence"])
    except Exception:
        pass

    # Strategy 2: Hybrid search
    try:
        result = _execute_hybrid_search(driver, question, top_k=5)
        if result.get("evidence"):
            strategies_tried.append("hybrid")
            all_evidence.extend(result["evidence"])
    except Exception:
        pass

    # Strategy 3: Cross-layer traversal
    try:
        result = _execute_cross_layer_traversal(driver, question, top_k=5)
        if result.get("evidence"):
            strategies_tried.append("cross_layer")
            all_evidence.extend(result["evidence"])
            # Check if cross-layer bridge exists
            has_cross_layer_bridge = any(
                "domain_node" in str(e) for e in result["evidence"]
            )
    except Exception:
        pass

    # Deduplicate evidence (by text content)
    seen = set()
    unique_evidence = []
    for e in all_evidence:
        text = e.get("text", "")[:100]  # First 100 chars as key
        if text and text not in seen:
            seen.add(text)
            unique_evidence.append(e)

    return {
        "strategies_tried": strategies_tried,
        "evidence_count": len(unique_evidence),
        "has_cross_layer_bridge": has_cross_layer_bridge,
        "evidence": unique_evidence[:10],  # Cap at 10 for storage
    }
```

### Integration with kg_query

The evaluation tool reuses US013's internal strategy functions but:
- Does NOT synthesize answers (only collects evidence)
- Tries multiple strategies for comprehensive assessment
- Classifies answerability based on evidence quality

This is distinct from `kg_query` which:
- Returns a synthesized answer
- Uses only ONE strategy (selected by Claude)
- Optimized for speed (single strategy call)

## Dependencies

- **US012**: Competency Questions Agent (provides `approved_competency_questions` in state)
- **US013**: Query Infrastructure (provides internal strategy functions, `_select_retrieval_strategy`)
- Existing `core/state.py` (state management)
- Existing `utils/neo4j_utils.py` (driver management)

## Out of Scope

- Answering CQs (use `kg_query` for that - this tool only assesses answerability)
- Historical evaluation tracking (only stores latest evaluation)
- CQ comparison over time (future enhancement)
- Automated graph improvement suggestions (future enhancement)
- Per-strategy confidence scores (simple binary: has evidence or not)
- Custom answerability thresholds (hardcoded: >2 evidence + cross-layer = answerable)
