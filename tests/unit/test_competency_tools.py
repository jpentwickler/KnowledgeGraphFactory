"""Unit tests for Competency Questions tool handlers."""

import copy
import sys
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.competency_tools import (
    handle_set_proposed_cqs,
    handle_approve_proposed_cqs,
    handle_add_cq,
    handle_modify_cq,
    handle_delete_cq,
    handle_get_cqs,
    handle_approve_cq_changes,
    format_competency_questions,
    _ensure_working_copy,
)


# ---------------------------------------------------------------------------
# Tests: _ensure_working_copy
# ---------------------------------------------------------------------------


def test_ensure_working_copy_from_empty():
    state = {}
    result = _ensure_working_copy(state)
    assert result == {}
    assert state["proposed_competency_questions"] == {}


def test_ensure_working_copy_from_approved():
    state = {
        "approved_competency_questions": {
            "CQ1": {"question": "Q1?", "category": "cat", "priority": "high"}
        }
    }
    result = _ensure_working_copy(state)
    assert "CQ1" in result
    assert result["CQ1"]["question"] == "Q1?"
    # Verify deep copy (not same reference)
    result["CQ1"]["question"] = "modified"
    assert state["approved_competency_questions"]["CQ1"]["question"] == "Q1?"


def test_ensure_working_copy_noop_when_proposed_exists():
    proposed = {"CQ1": {"question": "Q1?", "category": "cat", "priority": "high"}}
    state = {"proposed_competency_questions": proposed}
    result = _ensure_working_copy(state)
    assert result is proposed  # Same object reference


# ---------------------------------------------------------------------------
# Tests: handle_set_proposed_cqs
# ---------------------------------------------------------------------------


def test_set_proposed_cqs_valid():
    state = {}
    cqs = [
        {"id": "CQ1", "question": "What products are most affected?", "category": "quality", "priority": "high"},
        {"id": "CQ2", "question": "Which suppliers are reliable?", "category": "supply_chain", "priority": "medium"},
    ]
    result = handle_set_proposed_cqs(state, cqs)
    assert result["status"] == "success"
    assert len(state["proposed_competency_questions"]) == 2
    assert "CQ1" in state["proposed_competency_questions"]
    assert state["proposed_competency_questions"]["CQ1"]["priority"] == "high"


def test_set_proposed_cqs_empty_list():
    state = {}
    result = handle_set_proposed_cqs(state, [])
    assert result["status"] == "error"
    assert "empty" in result["message"]


def test_set_proposed_cqs_duplicate_ids():
    state = {}
    cqs = [
        {"id": "CQ1", "question": "Q1?", "category": "cat", "priority": "high"},
        {"id": "CQ1", "question": "Q2?", "category": "cat", "priority": "low"},
    ]
    result = handle_set_proposed_cqs(state, cqs)
    assert result["status"] == "error"
    assert "Duplicate" in result["message"]


def test_set_proposed_cqs_missing_question():
    state = {}
    cqs = [{"id": "CQ1", "question": "", "category": "cat", "priority": "high"}]
    result = handle_set_proposed_cqs(state, cqs)
    assert result["status"] == "error"
    assert "missing" in result["message"].lower() or "question" in result["message"]


def test_set_proposed_cqs_invalid_priority():
    state = {}
    cqs = [{"id": "CQ1", "question": "Q?", "category": "cat", "priority": "critical"}]
    result = handle_set_proposed_cqs(state, cqs)
    assert result["status"] == "error"
    assert "priority" in result["message"].lower()


def test_set_proposed_cqs_overwrites_existing():
    state = {"proposed_competency_questions": {"OLD": {"question": "old?", "category": "x", "priority": "low"}}}
    cqs = [{"id": "CQ1", "question": "New?", "category": "cat", "priority": "high"}]
    result = handle_set_proposed_cqs(state, cqs)
    assert result["status"] == "success"
    assert "OLD" not in state["proposed_competency_questions"]
    assert "CQ1" in state["proposed_competency_questions"]


def test_set_proposed_cqs_missing_category():
    state = {}
    cqs = [{"id": "CQ1", "question": "Q?", "category": "", "priority": "high"}]
    result = handle_set_proposed_cqs(state, cqs)
    assert result["status"] == "error"
    assert "category" in result["message"].lower()


def test_set_proposed_cqs_missing_id():
    state = {}
    cqs = [{"id": "", "question": "Q?", "category": "cat", "priority": "high"}]
    result = handle_set_proposed_cqs(state, cqs)
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# Tests: handle_approve_proposed_cqs
# ---------------------------------------------------------------------------


def test_approve_proposed_cqs_no_proposal():
    state = {}
    result = handle_approve_proposed_cqs(state)
    assert result["status"] == "error"
    assert "No proposed" in result["message"]


def test_approve_proposed_cqs_success():
    state = {
        "proposed_competency_questions": {
            "CQ1": {"question": "Q1?", "category": "cat", "priority": "high"}
        }
    }
    result = handle_approve_proposed_cqs(state)
    assert result["status"] == "success"
    assert "approved_competency_questions" in state
    assert "CQ1" in state["approved_competency_questions"]


def test_approve_proposed_cqs_deep_copy():
    proposed = {
        "CQ1": {"question": "Q1?", "category": "cat", "priority": "high"}
    }
    state = {"proposed_competency_questions": proposed}
    handle_approve_proposed_cqs(state)

    # Modify proposed, approved should be unaffected
    state["proposed_competency_questions"]["CQ1"]["question"] = "modified"
    assert state["approved_competency_questions"]["CQ1"]["question"] == "Q1?"


# ---------------------------------------------------------------------------
# Tests: handle_add_cq
# ---------------------------------------------------------------------------


def test_add_cq_fresh_state():
    state = {}
    result = handle_add_cq(state, id="CQ1", question="Q?", category="cat", priority="high")
    assert result["status"] == "success"
    assert "CQ1" in state["proposed_competency_questions"]
    assert result["overwritten"] is False


def test_add_cq_working_copy_from_approved():
    state = {
        "approved_competency_questions": {
            "CQ1": {"question": "Old Q?", "category": "cat", "priority": "low"}
        }
    }
    result = handle_add_cq(state, id="CQ2", question="New Q?", category="new", priority="high")
    assert result["status"] == "success"
    proposed = state["proposed_competency_questions"]
    assert "CQ1" in proposed  # Copied from approved
    assert "CQ2" in proposed  # Newly added


def test_add_cq_overwrite_existing():
    state = {
        "proposed_competency_questions": {
            "CQ1": {"question": "Old?", "category": "cat", "priority": "low"}
        }
    }
    result = handle_add_cq(state, id="CQ1", question="New?", category="new_cat", priority="high")
    assert result["status"] == "success"
    assert result["overwritten"] is True
    assert state["proposed_competency_questions"]["CQ1"]["question"] == "New?"


def test_add_cq_invalid_priority():
    state = {}
    result = handle_add_cq(state, id="CQ1", question="Q?", category="cat", priority="urgent")
    assert result["status"] == "error"
    assert "priority" in result["message"].lower()


# ---------------------------------------------------------------------------
# Tests: handle_modify_cq
# ---------------------------------------------------------------------------


def test_modify_cq_question_only():
    state = {
        "proposed_competency_questions": {
            "CQ1": {"question": "Old?", "category": "cat", "priority": "high"}
        }
    }
    result = handle_modify_cq(state, id="CQ1", question="Updated?")
    assert result["status"] == "success"
    assert state["proposed_competency_questions"]["CQ1"]["question"] == "Updated?"
    assert state["proposed_competency_questions"]["CQ1"]["priority"] == "high"  # Unchanged


def test_modify_cq_priority_only():
    state = {
        "proposed_competency_questions": {
            "CQ1": {"question": "Q?", "category": "cat", "priority": "high"}
        }
    }
    result = handle_modify_cq(state, id="CQ1", priority="low")
    assert result["status"] == "success"
    assert state["proposed_competency_questions"]["CQ1"]["priority"] == "low"
    assert state["proposed_competency_questions"]["CQ1"]["question"] == "Q?"  # Unchanged


def test_modify_cq_nonexistent():
    state = {"proposed_competency_questions": {}}
    result = handle_modify_cq(state, id="CQ99")
    assert result["status"] == "error"
    assert "not found" in result["message"]


def test_modify_cq_working_copy():
    state = {
        "approved_competency_questions": {
            "CQ1": {"question": "Approved?", "category": "cat", "priority": "high"}
        }
    }
    result = handle_modify_cq(state, id="CQ1", question="Modified?")
    assert result["status"] == "success"
    # Working copy created from approved
    assert state["proposed_competency_questions"]["CQ1"]["question"] == "Modified?"
    # Approved unchanged
    assert state["approved_competency_questions"]["CQ1"]["question"] == "Approved?"


def test_modify_cq_invalid_priority():
    state = {
        "proposed_competency_questions": {
            "CQ1": {"question": "Q?", "category": "cat", "priority": "high"}
        }
    }
    result = handle_modify_cq(state, id="CQ1", priority="critical")
    assert result["status"] == "error"
    assert "priority" in result["message"].lower()


# ---------------------------------------------------------------------------
# Tests: handle_delete_cq
# ---------------------------------------------------------------------------


def test_delete_cq_exists():
    state = {
        "proposed_competency_questions": {
            "CQ1": {"question": "Q?", "category": "cat", "priority": "high"},
            "CQ2": {"question": "Q2?", "category": "cat", "priority": "low"},
        }
    }
    result = handle_delete_cq(state, id="CQ1")
    assert result["status"] == "success"
    assert "CQ1" not in state["proposed_competency_questions"]
    assert "CQ2" in state["proposed_competency_questions"]


def test_delete_cq_nonexistent():
    state = {"proposed_competency_questions": {}}
    result = handle_delete_cq(state, id="CQ99")
    assert result["status"] == "error"
    assert "not found" in result["message"]


def test_delete_cq_working_copy():
    state = {
        "approved_competency_questions": {
            "CQ1": {"question": "Q?", "category": "cat", "priority": "high"},
            "CQ2": {"question": "Q2?", "category": "cat", "priority": "low"},
        }
    }
    result = handle_delete_cq(state, id="CQ1")
    assert result["status"] == "success"
    # Working copy should have CQ2 but not CQ1
    assert "CQ1" not in state["proposed_competency_questions"]
    assert "CQ2" in state["proposed_competency_questions"]
    # Approved should be untouched
    assert "CQ1" in state["approved_competency_questions"]


# ---------------------------------------------------------------------------
# Tests: handle_get_cqs
# ---------------------------------------------------------------------------


def test_get_cqs_empty():
    state = {}
    result = handle_get_cqs(state)
    assert result["status"] == "success"
    assert result["proposed_count"] == 0
    assert result["approved_count"] == 0


def test_get_cqs_proposed_only():
    state = {
        "proposed_competency_questions": {
            "CQ1": {"question": "Q?", "category": "cat", "priority": "high"}
        }
    }
    result = handle_get_cqs(state)
    assert result["proposed_count"] == 1
    assert result["approved_count"] == 0


def test_get_cqs_approved_only():
    state = {
        "approved_competency_questions": {
            "CQ1": {"question": "Q?", "category": "cat", "priority": "high"}
        }
    }
    result = handle_get_cqs(state)
    assert result["proposed_count"] == 0
    assert result["approved_count"] == 1


def test_get_cqs_both():
    state = {
        "proposed_competency_questions": {
            "CQ1": {"question": "Proposed?", "category": "cat", "priority": "high"},
            "CQ2": {"question": "Also proposed?", "category": "cat", "priority": "low"},
        },
        "approved_competency_questions": {
            "CQ1": {"question": "Approved?", "category": "cat", "priority": "high"}
        },
    }
    result = handle_get_cqs(state)
    assert result["proposed_count"] == 2
    assert result["approved_count"] == 1


# ---------------------------------------------------------------------------
# Tests: handle_approve_cq_changes
# ---------------------------------------------------------------------------


def test_approve_cq_changes_success():
    state = {
        "proposed_competency_questions": {
            "CQ1": {"question": "Q1?", "category": "cat", "priority": "high"},
            "CQ2": {"question": "Q2?", "category": "cat", "priority": "low"},
        }
    }
    result = handle_approve_cq_changes(state)
    assert result["status"] == "success"
    assert len(state["approved_competency_questions"]) == 2


def test_approve_cq_changes_no_proposal():
    state = {}
    result = handle_approve_cq_changes(state)
    assert result["status"] == "error"
    assert "No proposed" in result["message"]


# ---------------------------------------------------------------------------
# Tests: format_competency_questions
# ---------------------------------------------------------------------------


def test_format_cqs_empty():
    state = {}
    result = format_competency_questions(state)
    assert result == "(none)"


def test_format_cqs_no_approved():
    state = {
        "proposed_competency_questions": {
            "CQ1": {"question": "Q?", "category": "cat", "priority": "high"}
        }
    }
    result = format_competency_questions(state)
    assert result == "(none)"  # Only looks at approved


def test_format_cqs_sorted_by_priority():
    state = {
        "approved_competency_questions": {
            "CQ1": {"question": "Low Q?", "category": "cat", "priority": "low"},
            "CQ2": {"question": "High Q?", "category": "cat", "priority": "high"},
            "CQ3": {"question": "Med Q?", "category": "cat", "priority": "medium"},
        }
    }
    result = format_competency_questions(state)
    lines = result.strip().split("\n")
    assert len(lines) == 3
    assert "CQ2" in lines[0]  # High first
    assert "CQ3" in lines[1]  # Medium second
    assert "CQ1" in lines[2]  # Low last


def test_format_cqs_all_fields_present():
    state = {
        "approved_competency_questions": {
            "CQ1": {"question": "What products?", "category": "quality", "priority": "high"},
        }
    }
    result = format_competency_questions(state)
    assert "[CQ1]" in result
    assert "high" in result
    assert "quality" in result
    assert "What products?" in result
