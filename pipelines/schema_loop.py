"""Schema refinement loop — orchestrates proposal and critic agents.

Equivalent to the Google ADK LoopAgent pattern:
    schema_proposal_agent -> schema_critic_agent -> check_status

Loops until critic returns verdict "valid" or max_iterations reached.
"""

import logging

from agents.schema_proposal import SchemaProposalAgent
from agents.schema_critic import SchemaCriticAgent

logger = logging.getLogger(__name__)


def run_refinement_loop(
    state: dict,
    message: str = "How can these files be imported to construct the knowledge graph?",
    max_iterations: int = 2,
) -> tuple[str, dict]:
    """Run the schema proposal-critic refinement loop.

    Args:
        state: Shared state dict. Must contain approved_user_goal and approved_files.
            state["feedback"] is initialized to "" if not present.
        message: The initial prompt to the proposal agent.
        max_iterations: Maximum number of proposal-critic cycles.

    Returns:
        Tuple of (summary_string, updated_state).
        The state is mutated in place (same dict object).
    """
    proposal_agent = SchemaProposalAgent()
    critic_agent = SchemaCriticAgent()

    # Initialize feedback and trace
    if "feedback" not in state:
        state["feedback"] = ""
    state["_refinement_trace"] = []

    for iteration in range(max_iterations):
        print(f"\n{'='*70}")
        print(f"REFINEMENT LOOP - Iteration {iteration + 1}/{max_iterations}")
        print(f"{'='*70}")
        logger.info(
            "Refinement loop iteration %d/%d", iteration + 1, max_iterations
        )

        # Step 1: Run proposal agent (fresh conversation each time)
        print("\n[1/3] Running schema proposal agent...")
        logger.info("Running schema proposal agent...")
        proposal_response, state, _ = proposal_agent.run(
            message=message,
            state=state,
            conversation=None,
        )
        plan_size = len(state.get("proposed_construction_plan", {}))
        print(f"[OK] Proposal agent done. Plan has {plan_size} rules.")
        logger.info(
            "Proposal agent done. Plan has %d rules.",
            plan_size,
        )

        # Step 2: Run critic agent (fresh conversation each time)
        print("\n[2/3] Running schema critic agent...")
        logger.info("Running schema critic agent...")
        critic_response, state, _ = critic_agent.run(
            message="Validate the proposed construction plan.",
            state=state,
            conversation=None,
        )
        print("[OK] Critic agent done.")
        logger.info("Critic agent done.")

        # Step 3: Read structured verdict from state (set by submit_review tool)
        verdict = state.get("_critic_verdict", "retry")
        problems = state.get("_critic_problems", [])
        print(f"\n[3/3] Critic verdict: {verdict}")
        if problems:
            print(f"Problems identified: {len(problems)}")
            for i, problem in enumerate(problems[:3], 1):
                print(f"  {i}. {problem}")

        # Step 4: Store critic response as feedback for next iteration
        state["feedback"] = critic_response

        # Step 5: Record trace for debugging
        state["_refinement_trace"].append({
            "iteration": iteration + 1,
            "proposal_summary": proposal_response[:500],
            "critic_verdict": verdict,
            "critic_problems": problems,
            "critic_response": critic_response[:500],
        })

        # Step 6: Check status (equivalent to CheckStatusAndEscalate)
        if verdict == "valid":
            print(f"\n[SUCCESS] Schema validated after {iteration + 1} iteration(s)!")
            logger.info(
                "Schema validated by critic after %d iteration(s).",
                iteration + 1,
            )
            plan = state.get("proposed_construction_plan", {})
            node_count = sum(
                1 for v in plan.values()
                if v.get("construction_type") == "node"
            )
            rel_count = sum(
                1 for v in plan.values()
                if v.get("construction_type") == "relationship"
            )
            return (
                f"Schema validated after {iteration + 1} iteration(s). "
                f"{node_count} nodes, {rel_count} relationships proposed.",
                state,
            )

    # Max iterations reached without validation
    logger.warning(
        "Max iterations (%d) reached without critic validation.",
        max_iterations,
    )
    plan = state.get("proposed_construction_plan", {})
    node_count = sum(
        1 for v in plan.values() if v.get("construction_type") == "node"
    )
    rel_count = sum(
        1 for v in plan.values() if v.get("construction_type") == "relationship"
    )
    return (
        f"Refinement completed after {max_iterations} iterations "
        f"(critic did not fully validate). "
        f"{node_count} nodes, {rel_count} relationships proposed. "
        f"Last feedback: {state.get('feedback', 'N/A')[:200]}",
        state,
    )
