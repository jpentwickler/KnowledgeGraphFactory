"""Extraction quality evaluation against golden reference.

Makes real Claude API calls. Run explicitly:
    pytest tests/eval/test_extraction_quality.py -v -s

Never run in CI — each run costs ~2 API calls.
"""

import json
import os
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from dotenv import load_dotenv
import pytest

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_EXAMPLE_DIR = _PROJECT_ROOT / "examples" / "furniture_supply_chain"
_GOLDEN_PATH = _EXAMPLE_DIR / "eval" / "golden_reference.json"
_STATE_PATH = _EXAMPLE_DIR / "state" / "current_state.json"
_DATA_DIR = _EXAMPLE_DIR / "data"
_RESULTS_DIR = _EXAMPLE_DIR / "eval" / "results"

# Set KG_DATA_DIR so build_file_content resolves paths correctly
os.environ["KG_DATA_DIR"] = str(_DATA_DIR)


class TestExtractionQuality:
    """Extraction quality evaluation against golden reference.

    Makes real Claude API calls. Run explicitly:
        pytest tests/eval/test_extraction_quality.py -v -s
    """

    # ------------------------------------------------------------------
    # Fixtures (class-scoped — run once, share across all test methods)
    # ------------------------------------------------------------------

    @pytest.fixture(scope="class")
    def golden(self):
        """Load golden reference JSON."""
        with open(_GOLDEN_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture(scope="class")
    def state(self):
        """Build minimal state from furniture supply chain.

        Loads current_state.json and keeps only the three keys needed
        for extraction: approved_user_goal, approved_files,
        approved_construction_plan.
        """
        with open(_STATE_PATH, "r", encoding="utf-8") as f:
            full_state = json.load(f)

        return {
            "approved_user_goal": full_state["approved_user_goal"],
            "approved_files": full_state["approved_files"],
            "approved_construction_plan": full_state["approved_construction_plan"],
        }

    @pytest.fixture(scope="class")
    def entity_proposal(self, state):
        """Run propose_entity_types() once, cache for all entity tests."""
        from tools.extraction_tools import build_file_content, propose_entity_types

        content, _ = build_file_content(state)
        return propose_entity_types(state, content=content)

    @pytest.fixture(scope="class")
    def entity_evidence(self, state, entity_proposal):
        """Run gather_evidence() on the proposal."""
        from tools.extraction_tools import gather_evidence

        import copy

        types_copy = copy.deepcopy(entity_proposal.get("entity_types", []))
        return gather_evidence(state, types_copy)

    @pytest.fixture(scope="class")
    def fact_proposal(self, state, entity_proposal):
        """Run propose_fact_types() once, cache for all fact tests.

        Builds approved_entity_types from the fresh entity_proposal so
        fact extraction uses the same types we just evaluated — not stale
        types from a previous Neo4j session.
        """
        from tools.extraction_tools import build_file_content, propose_fact_types

        # Convert entity_proposal list into the approved_entity_types dict
        approved_entities = {}
        for et in entity_proposal.get("entity_types", []):
            approved_entities[et["name"]] = {
                "source": et["source"],
                "description": et["description"],
            }

        fact_state = {
            **state,
            "approved_entity_types": approved_entities,
        }

        content, _ = build_file_content(fact_state)
        return propose_fact_types(fact_state, content=content)

    # ------------------------------------------------------------------
    # Matching helpers
    # ------------------------------------------------------------------

    def _matches_golden(self, proposed_name, golden_name, equivalences):
        """Fuzzy match: exact (case-insensitive), in equivalences list,
        or SequenceMatcher ratio indicating Levenshtein distance <= 2.

        Returns True if proposed_name matches golden_name.
        """
        p = proposed_name.lower()
        g = golden_name.lower()

        # Exact match (case-insensitive)
        if p == g:
            return True

        # Check name equivalences
        equiv_list = equivalences.get(golden_name, [])
        for equiv in equiv_list:
            if p == equiv.lower():
                return True

        # Levenshtein-like distance via SequenceMatcher
        # SequenceMatcher ratio >= 0.8 roughly corresponds to edit distance <= 2
        # for names of typical length (5-15 chars)
        ratio = SequenceMatcher(None, p, g).ratio()
        if ratio >= 0.8:
            return True

        return False

    def _matches_any_golden_entity(self, proposed_name, golden_types, equivalences):
        """Check if a proposed entity name matches any golden entity type."""
        for gt in golden_types:
            if self._matches_golden(proposed_name, gt["name"], equivalences):
                return True
        return False

    def _matches_predicate(self, proposed_pred, golden_pred, pred_equivalences):
        """Check if a proposed predicate matches a golden predicate.

        Checks: exact (normalized), predicate_equivalences, fuzzy ratio >= 0.7.
        """
        p = proposed_pred.lower().replace("_", "")
        g = golden_pred.lower().replace("_", "")

        if p == g:
            return True

        # Check predicate equivalences
        equiv_list = pred_equivalences.get(golden_pred, [])
        for equiv in equiv_list:
            if p == equiv.lower().replace("_", ""):
                return True

        ratio = SequenceMatcher(None, p, g).ratio()
        return ratio >= 0.7

    def _matches_golden_fact(self, proposed_fact, golden_fact, equivalences,
                             pred_equivalences=None):
        """Check if a proposed fact matches a golden fact type.

        Matches subject and object by entity name (with equivalences),
        and predicate by exact/equivalences/fuzzy match.
        Also tries the reversed direction (swap subject/object, keep predicate check).
        """
        if pred_equivalences is None:
            pred_equivalences = {}

        p_subj = proposed_fact.get("subject", "")
        p_obj = proposed_fact.get("object", "")
        p_pred = proposed_fact.get("predicate", "")
        g_subj = golden_fact["subject"]
        g_obj = golden_fact["object"]
        g_pred = golden_fact["predicate"]

        # Forward direction
        subj_match = self._matches_golden(p_subj, g_subj, equivalences)
        obj_match = self._matches_golden(p_obj, g_obj, equivalences)
        pred_match = self._matches_predicate(p_pred, g_pred, pred_equivalences)

        if subj_match and obj_match and pred_match:
            return True

        # Reversed direction: proposed has (Object)-[pred]->(Subject)
        rev_subj = self._matches_golden(p_subj, g_obj, equivalences)
        rev_obj = self._matches_golden(p_obj, g_subj, equivalences)
        if rev_subj and rev_obj and pred_match:
            return True

        return False

    # ------------------------------------------------------------------
    # Entity tests
    # ------------------------------------------------------------------

    def test_required_entity_recall(self, entity_proposal, golden):
        """Required entity recall >= 75% (>= 3 of 4)."""
        proposed = entity_proposal.get("entity_types", [])
        required = golden["entity_types"]["required"]
        equivalences = golden.get("name_equivalences", {})

        matched = 0
        for req in required:
            for prop in proposed:
                if self._matches_golden(prop["name"], req["name"], equivalences):
                    matched += 1
                    break

        recall = matched / len(required) if required else 0
        print(f"\n  Required entity recall: {matched}/{len(required)} = {recall:.0%}")
        for req in required:
            found = any(
                self._matches_golden(p["name"], req["name"], equivalences)
                for p in proposed
            )
            print(f"    {req['name']}: {'FOUND' if found else 'MISSING'}")

        assert recall >= 0.75, (
            f"Required entity recall {recall:.0%} < 75%. "
            f"Matched {matched}/{len(required)}."
        )

    def test_entity_precision(self, entity_proposal, golden):
        """Entity precision >= 60%."""
        proposed = entity_proposal.get("entity_types", [])
        all_golden = (
            golden["entity_types"]["required"] + golden["entity_types"]["bonus"]
        )
        equivalences = golden.get("name_equivalences", {})

        correct = 0
        for prop in proposed:
            if self._matches_any_golden_entity(
                prop["name"], all_golden, equivalences
            ):
                correct += 1

        precision = correct / len(proposed) if proposed else 0
        print(f"\n  Entity precision: {correct}/{len(proposed)} = {precision:.0%}")
        for prop in proposed:
            is_correct = self._matches_any_golden_entity(
                prop["name"], all_golden, equivalences
            )
            tag = "CORRECT" if is_correct else "EXTRA"
            print(f"    {prop['name']}: {tag}")

        assert precision >= 0.60, (
            f"Entity precision {precision:.0%} < 60%. "
            f"Correct: {correct}/{len(proposed)}."
        )

    def test_bonus_entity_recall(self, entity_proposal, golden):
        """Bonus recall (informational, no assertion)."""
        proposed = entity_proposal.get("entity_types", [])
        bonus = golden["entity_types"]["bonus"]
        equivalences = golden.get("name_equivalences", {})

        matched = 0
        for bon in bonus:
            for prop in proposed:
                if self._matches_golden(prop["name"], bon["name"], equivalences):
                    matched += 1
                    break

        recall = matched / len(bonus) if bonus else 0
        print(f"\n  Bonus entity recall: {matched}/{len(bonus)} = {recall:.0%}")
        for bon in bonus:
            found = any(
                self._matches_golden(p["name"], bon["name"], equivalences)
                for p in proposed
            )
            print(f"    {bon['name']}: {'FOUND' if found else 'MISSING'}")
        # Informational only — no assertion

    # ------------------------------------------------------------------
    # Evidence tests
    # ------------------------------------------------------------------

    def test_evidence_grounding_rate(self, entity_evidence):
        """Grounding rate >= 80% (types with total_mentions > 0)."""
        grounded = 0
        total = len(entity_evidence)

        for et in entity_evidence:
            ev = et.get("grounding_evidence", {})
            if ev.get("total_mentions", 0) > 0:
                grounded += 1
            elif et.get("source") == "well_known":
                # Well-known types don't get evidence gathered, count as grounded
                grounded += 1

        rate = grounded / total if total else 0
        print(f"\n  Grounding rate: {grounded}/{total} = {rate:.0%}")
        for et in entity_evidence:
            ev = et.get("grounding_evidence", {})
            mentions = ev.get("total_mentions", 0)
            if et.get("source") == "well_known":
                print(f"    {et['name']}: well_known (no evidence needed)")
            else:
                status = f"{mentions} mentions" if mentions > 0 else "NO EVIDENCE"
                print(f"    {et['name']}: {status}")

        assert rate >= 0.80, (
            f"Grounding rate {rate:.0%} < 80%. "
            f"Grounded: {grounded}/{total}."
        )

    def test_zero_evidence_count(self, entity_evidence):
        """Zero-evidence count <= 1."""
        zero_count = 0
        for et in entity_evidence:
            if et.get("source") == "well_known":
                continue
            ev = et.get("grounding_evidence", {})
            if ev.get("total_mentions", 0) == 0:
                zero_count += 1

        print(f"\n  Zero-evidence discovered types: {zero_count}")
        assert zero_count <= 1, (
            f"Zero-evidence count {zero_count} > 1."
        )

    # ------------------------------------------------------------------
    # Fact tests
    # ------------------------------------------------------------------

    def test_required_fact_recall(self, fact_proposal, golden):
        """Required fact recall >= 67% (>= 2 of 3)."""
        proposed = fact_proposal.get("fact_types", [])
        required = golden["fact_types"]["required"]
        equivalences = golden.get("name_equivalences", {})
        pred_eq = golden.get("predicate_equivalences", {})

        matched = 0
        for req in required:
            for prop in proposed:
                if self._matches_golden_fact(prop, req, equivalences, pred_eq):
                    matched += 1
                    break

        recall = matched / len(required) if required else 0
        print(f"\n  Required fact recall: {matched}/{len(required)} = {recall:.0%}")
        for req in required:
            found = any(
                self._matches_golden_fact(p, req, equivalences, pred_eq)
                for p in proposed
            )
            triple = f"({req['subject']})-[{req['predicate']}]->({req['object']})"
            print(f"    {triple}: {'FOUND' if found else 'MISSING'}")

        assert recall >= 0.67, (
            f"Required fact recall {recall:.0%} < 67%. "
            f"Matched {matched}/{len(required)}."
        )

    # ------------------------------------------------------------------
    # Scorecard (always passes — for human review)
    # ------------------------------------------------------------------

    def test_print_scorecard(
        self, entity_proposal, entity_evidence, fact_proposal, golden
    ):
        """Print full scorecard (always passes, for human review)."""
        proposed_entities = entity_proposal.get("entity_types", [])
        proposed_facts = fact_proposal.get("fact_types", [])
        equivalences = golden.get("name_equivalences", {})

        # Required entity recall
        req_ents = golden["entity_types"]["required"]
        req_ent_matched = sum(
            1
            for req in req_ents
            if any(
                self._matches_golden(p["name"], req["name"], equivalences)
                for p in proposed_entities
            )
        )

        # Bonus entity recall
        bonus_ents = golden["entity_types"]["bonus"]
        bonus_ent_matched = sum(
            1
            for bon in bonus_ents
            if any(
                self._matches_golden(p["name"], bon["name"], equivalences)
                for p in proposed_entities
            )
        )

        # Entity precision
        all_golden_ents = req_ents + bonus_ents
        ent_correct = sum(
            1
            for p in proposed_entities
            if self._matches_any_golden_entity(
                p["name"], all_golden_ents, equivalences
            )
        )

        # Grounding rate
        grounded = 0
        for et in entity_evidence:
            ev = et.get("grounding_evidence", {})
            if ev.get("total_mentions", 0) > 0 or et.get("source") == "well_known":
                grounded += 1

        # Zero-evidence count
        zero_ev = sum(
            1
            for et in entity_evidence
            if et.get("source") != "well_known"
            and et.get("grounding_evidence", {}).get("total_mentions", 0) == 0
        )

        # Evidence depth
        all_mentions = [
            et.get("grounding_evidence", {}).get("total_mentions", 0)
            for et in entity_evidence
            if et.get("source") != "well_known"
        ]
        avg_depth = sum(all_mentions) / len(all_mentions) if all_mentions else 0

        # Required fact recall
        pred_eq = golden.get("predicate_equivalences", {})
        req_facts = golden["fact_types"]["required"]
        req_fact_matched = sum(
            1
            for req in req_facts
            if any(
                self._matches_golden_fact(p, req, equivalences, pred_eq)
                for p in proposed_facts
            )
        )

        # Print scorecard
        n_ents = len(proposed_entities)
        n_facts = len(proposed_facts)
        n_ev = len(entity_evidence)

        print("\n" + "=" * 60)
        print("  EXTRACTION QUALITY SCORECARD")
        print("=" * 60)
        print(f"\n  Proposed: {n_ents} entity types, {n_facts} fact types")
        print(f"\n  {'Metric':<30} {'Value':>10} {'Threshold':>12} {'Status':>8}")
        print(f"  {'-'*30} {'-'*10} {'-'*12} {'-'*8}")

        def row(name, val, threshold_str, passing):
            status = "PASS" if passing else "FAIL"
            print(f"  {name:<30} {val:>10} {threshold_str:>12} {status:>8}")

        r_ent_recall = req_ent_matched / len(req_ents) if req_ents else 0
        row(
            "Required entity recall",
            f"{req_ent_matched}/{len(req_ents)} ({r_ent_recall:.0%})",
            ">= 75%",
            r_ent_recall >= 0.75,
        )

        ent_prec = ent_correct / n_ents if n_ents else 0
        row(
            "Entity precision",
            f"{ent_correct}/{n_ents} ({ent_prec:.0%})",
            ">= 60%",
            ent_prec >= 0.60,
        )

        ground_rate = grounded / n_ev if n_ev else 0
        row(
            "Grounding rate",
            f"{grounded}/{n_ev} ({ground_rate:.0%})",
            ">= 80%",
            ground_rate >= 0.80,
        )

        row(
            "Zero-evidence count",
            str(zero_ev),
            "<= 1",
            zero_ev <= 1,
        )

        r_fact_recall = req_fact_matched / len(req_facts) if req_facts else 0
        row(
            "Required fact recall",
            f"{req_fact_matched}/{len(req_facts)} ({r_fact_recall:.0%})",
            ">= 67%",
            r_fact_recall >= 0.67,
        )

        b_ent_recall = bonus_ent_matched / len(bonus_ents) if bonus_ents else 0
        row(
            "Bonus entity recall",
            f"{bonus_ent_matched}/{len(bonus_ents)} ({b_ent_recall:.0%})",
            "(info)",
            True,
        )

        row(
            "Evidence depth (avg mentions)",
            f"{avg_depth:.1f}",
            "(info)",
            True,
        )

        print("\n  Proposed entity types:")
        for et in proposed_entities:
            print(f"    - {et['name']} ({et.get('source', '?')})")

        print("\n  Proposed fact types:")
        for ft in proposed_facts:
            print(
                f"    - ({ft['subject']})-[{ft['predicate']}]->({ft['object']})"
            )

        # --- Save results ---
        from core.config import CLAUDE_MODEL, CLAUDE_MODEL_STRUCTURED

        run_result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "models": {
                "agent": CLAUDE_MODEL,
                "structured": CLAUDE_MODEL_STRUCTURED,
            },
            "metrics": {
                "required_entity_recall": round(r_ent_recall, 4),
                "entity_precision": round(ent_prec, 4),
                "grounding_rate": round(ground_rate, 4),
                "zero_evidence_count": zero_ev,
                "required_fact_recall": round(r_fact_recall, 4),
                "bonus_entity_recall": round(b_ent_recall, 4),
                "evidence_depth": round(avg_depth, 1),
            },
            "proposed_entities": [
                {"name": et["name"], "source": et.get("source", "?")}
                for et in proposed_entities
            ],
            "proposed_facts": [
                {
                    "subject": ft["subject"],
                    "predicate": ft["predicate"],
                    "object": ft["object"],
                }
                for ft in proposed_facts
            ],
        }

        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        result_path = _RESULTS_DIR / f"run_{ts}.json"
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(run_result, f, indent=2)
        print(f"\n  Results saved to: {result_path.relative_to(_PROJECT_ROOT)}")

        # --- Compare with previous run ---
        result_files = sorted(_RESULTS_DIR.glob("run_*.json"))
        if len(result_files) >= 2:
            prev_path = result_files[-2]
            with open(prev_path, "r", encoding="utf-8") as f:
                prev = json.load(f)
            prev_m = prev["metrics"]
            curr_m = run_result["metrics"]

            print(f"\n  Comparison with previous run ({prev_path.name}):")
            print(f"  {'Metric':<30} {'Previous':>10} {'Current':>10} {'Delta':>10}")
            print(f"  {'-'*30} {'-'*10} {'-'*10} {'-'*10}")

            for key in [
                "required_entity_recall",
                "entity_precision",
                "grounding_rate",
                "zero_evidence_count",
                "required_fact_recall",
                "bonus_entity_recall",
                "evidence_depth",
            ]:
                pv = prev_m.get(key, 0)
                cv = curr_m.get(key, 0)
                if key in ("zero_evidence_count", "evidence_depth"):
                    delta = cv - pv
                    sign = "+" if delta > 0 else ""
                    fmt = f"{sign}{delta:.1f}" if isinstance(cv, float) else f"{sign}{delta}"
                    print(f"  {key:<30} {pv:>10} {cv:>10} {fmt:>10}")
                else:
                    delta = cv - pv
                    sign = "+" if delta > 0 else ""
                    print(
                        f"  {key:<30} {pv:>9.0%} {cv:>9.0%} {sign}{delta:>8.0%}"
                    )

        print("\n" + "=" * 60)
        # Always passes — scorecard is for human review
