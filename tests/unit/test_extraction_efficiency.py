"""Tests for US020: Extraction Efficiency — Structured Output for NER & Fact Discovery.

Tests the new structured-output functions that replace multi-turn agent loops
for the initial proposal: build_file_content, propose_entity_types,
propose_fact_types, gather_evidence, merge functions, and first-call detection.
"""

import json
import os
import re
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# TestBuildFileContent
# ---------------------------------------------------------------------------


class TestBuildFileContent:
    """Tests for build_file_content()."""

    def _make_state(self, files):
        return {
            "approved_files": {
                "unstructured": [{"path": f} for f in files],
            }
        }

    def test_no_approved_files(self):
        from tools.extraction_tools import build_file_content

        content, fits = build_file_content({})
        assert content == ""
        assert fits is True

    def test_empty_unstructured_list(self):
        from tools.extraction_tools import build_file_content

        state = {"approved_files": {"unstructured": []}}
        content, fits = build_file_content(state)
        assert content == ""
        assert fits is True

    def test_small_file_fits_in_one_call(self, tmp_path):
        from tools.extraction_tools import build_file_content

        md = tmp_path / "test.md"
        md.write_text("# Title\nLine 1\nLine 2\n", encoding="utf-8")

        state = self._make_state(["test.md"])
        with patch("tools.extraction_tools._get_data_dir", return_value=str(tmp_path)):
            content, fits = build_file_content(state, max_chars=100_000)

        assert fits is True
        assert isinstance(content, str)
        assert "test.md" in content
        assert "Title" in content
        assert "Line 1" in content

    def test_large_content_returns_dict(self, tmp_path):
        from tools.extraction_tools import build_file_content

        for name in ["a.md", "b.md"]:
            (tmp_path / name).write_text("x" * 100, encoding="utf-8")

        state = self._make_state(["a.md", "b.md"])
        with patch("tools.extraction_tools._get_data_dir", return_value=str(tmp_path)):
            content, fits = build_file_content(state, max_chars=50)

        assert fits is False
        assert isinstance(content, dict)
        assert "a.md" in content
        assert "b.md" in content

    def test_file_not_found(self, tmp_path):
        from tools.extraction_tools import build_file_content

        state = self._make_state(["missing.md"])
        with patch("tools.extraction_tools._get_data_dir", return_value=str(tmp_path)):
            content, fits = build_file_content(state, max_chars=100_000)

        assert fits is True
        assert "File not found" in content

    def test_line_numbers_preserved(self, tmp_path):
        from tools.extraction_tools import build_file_content

        md = tmp_path / "numbered.md"
        md.write_text("Line A\nLine B\nLine C\n", encoding="utf-8")

        state = self._make_state(["numbered.md"])
        with patch("tools.extraction_tools._get_data_dir", return_value=str(tmp_path)):
            content, fits = build_file_content(state)

        assert fits is True
        assert "1 |" in content or "   1 |" in content

    def test_multiple_small_files_concatenated(self, tmp_path):
        from tools.extraction_tools import build_file_content

        (tmp_path / "one.md").write_text("# One\nContent one\n", encoding="utf-8")
        (tmp_path / "two.md").write_text("# Two\nContent two\n", encoding="utf-8")

        state = self._make_state(["one.md", "two.md"])
        with patch("tools.extraction_tools._get_data_dir", return_value=str(tmp_path)):
            content, fits = build_file_content(state, max_chars=100_000)

        assert fits is True
        assert "one.md" in content
        assert "two.md" in content
        assert "Content one" in content
        assert "Content two" in content


# ---------------------------------------------------------------------------
# TestMergeEntityProposals
# ---------------------------------------------------------------------------


class TestMergeEntityProposals:
    """Tests for merge_entity_proposals()."""

    def test_single_proposal_passthrough(self):
        from tools.extraction_tools import merge_entity_proposals

        proposal = {
            "entity_types": [
                {
                    "name": "Product",
                    "source": "well_known",
                    "description": "A product",
                    "evidence_patterns": ["product"],
                }
            ],
            "analysis_summary": "Found products.",
        }
        result = merge_entity_proposals([proposal])
        assert len(result["entity_types"]) == 1
        assert result["entity_types"][0]["name"] == "Product"
        assert result["analysis_summary"] == "Found products."

    def test_dedup_by_name_longer_description_wins(self):
        from tools.extraction_tools import merge_entity_proposals

        p1 = {
            "entity_types": [
                {
                    "name": "Issue",
                    "source": "discovered",
                    "description": "Short",
                    "evidence_patterns": ["issue"],
                }
            ],
            "analysis_summary": "File 1.",
        }
        p2 = {
            "entity_types": [
                {
                    "name": "Issue",
                    "source": "discovered",
                    "description": "A much longer and more detailed description of issues",
                    "evidence_patterns": ["problem", "defect"],
                }
            ],
            "analysis_summary": "File 2.",
        }
        result = merge_entity_proposals([p1, p2])
        assert len(result["entity_types"]) == 1
        issue = result["entity_types"][0]
        assert "longer" in issue["description"]

    def test_evidence_patterns_union(self):
        from tools.extraction_tools import merge_entity_proposals

        p1 = {
            "entity_types": [
                {
                    "name": "Issue",
                    "source": "discovered",
                    "description": "desc",
                    "evidence_patterns": ["issue", "problem"],
                }
            ],
            "analysis_summary": "",
        }
        p2 = {
            "entity_types": [
                {
                    "name": "Issue",
                    "source": "discovered",
                    "description": "desc",
                    "evidence_patterns": ["problem", "defect"],
                }
            ],
            "analysis_summary": "",
        }
        result = merge_entity_proposals([p1, p2])
        patterns = result["entity_types"][0]["evidence_patterns"]
        assert set(patterns) == {"issue", "problem", "defect"}

    def test_well_known_source_preserved(self):
        from tools.extraction_tools import merge_entity_proposals

        p1 = {
            "entity_types": [
                {
                    "name": "Product",
                    "source": "discovered",
                    "description": "desc",
                    "evidence_patterns": [],
                }
            ],
            "analysis_summary": "",
        }
        p2 = {
            "entity_types": [
                {
                    "name": "Product",
                    "source": "well_known",
                    "description": "desc",
                    "evidence_patterns": [],
                }
            ],
            "analysis_summary": "",
        }
        result = merge_entity_proposals([p1, p2])
        assert result["entity_types"][0]["source"] == "well_known"

    def test_summaries_concatenated(self):
        from tools.extraction_tools import merge_entity_proposals

        p1 = {"entity_types": [], "analysis_summary": "Summary A."}
        p2 = {"entity_types": [], "analysis_summary": "Summary B."}
        result = merge_entity_proposals([p1, p2])
        assert "Summary A." in result["analysis_summary"]
        assert "Summary B." in result["analysis_summary"]

    def test_empty_proposals(self):
        from tools.extraction_tools import merge_entity_proposals

        result = merge_entity_proposals([])
        assert result["entity_types"] == []
        assert result["analysis_summary"] == ""

    def test_different_types_not_merged(self):
        from tools.extraction_tools import merge_entity_proposals

        p1 = {
            "entity_types": [
                {
                    "name": "Product",
                    "source": "well_known",
                    "description": "desc",
                    "evidence_patterns": [],
                }
            ],
            "analysis_summary": "",
        }
        p2 = {
            "entity_types": [
                {
                    "name": "Issue",
                    "source": "discovered",
                    "description": "desc",
                    "evidence_patterns": [],
                }
            ],
            "analysis_summary": "",
        }
        result = merge_entity_proposals([p1, p2])
        assert len(result["entity_types"]) == 2


# ---------------------------------------------------------------------------
# TestMergeFactProposals
# ---------------------------------------------------------------------------


class TestMergeFactProposals:
    """Tests for merge_fact_proposals()."""

    def test_single_proposal_passthrough(self):
        from tools.extraction_tools import merge_fact_proposals

        proposal = {
            "fact_types": [
                {
                    "subject": "Product",
                    "predicate": "has_issue",
                    "object": "Issue",
                    "description": "Product has issue",
                }
            ],
            "analysis_summary": "Found relationships.",
        }
        result = merge_fact_proposals([proposal])
        assert len(result["fact_types"]) == 1
        assert result["fact_types"][0]["predicate"] == "has_issue"

    def test_dedup_by_triple_first_wins(self):
        from tools.extraction_tools import merge_fact_proposals

        p1 = {
            "fact_types": [
                {
                    "subject": "Product",
                    "predicate": "has_issue",
                    "object": "Issue",
                    "description": "First description",
                }
            ],
            "analysis_summary": "",
        }
        p2 = {
            "fact_types": [
                {
                    "subject": "Product",
                    "predicate": "has_issue",
                    "object": "Issue",
                    "description": "Second description",
                }
            ],
            "analysis_summary": "",
        }
        result = merge_fact_proposals([p1, p2])
        assert len(result["fact_types"]) == 1
        assert result["fact_types"][0]["description"] == "First description"

    def test_different_triples_not_merged(self):
        from tools.extraction_tools import merge_fact_proposals

        p1 = {
            "fact_types": [
                {
                    "subject": "Product",
                    "predicate": "has_issue",
                    "object": "Issue",
                    "description": "desc",
                }
            ],
            "analysis_summary": "",
        }
        p2 = {
            "fact_types": [
                {
                    "subject": "Customer",
                    "predicate": "reported",
                    "object": "Issue",
                    "description": "desc",
                }
            ],
            "analysis_summary": "",
        }
        result = merge_fact_proposals([p1, p2])
        assert len(result["fact_types"]) == 2

    def test_summaries_concatenated(self):
        from tools.extraction_tools import merge_fact_proposals

        p1 = {"fact_types": [], "analysis_summary": "Summary X."}
        p2 = {"fact_types": [], "analysis_summary": "Summary Y."}
        result = merge_fact_proposals([p1, p2])
        assert "Summary X." in result["analysis_summary"]
        assert "Summary Y." in result["analysis_summary"]

    def test_empty_proposals(self):
        from tools.extraction_tools import merge_fact_proposals

        result = merge_fact_proposals([])
        assert result["fact_types"] == []
        assert result["analysis_summary"] == ""


# ---------------------------------------------------------------------------
# TestGatherEvidence
# ---------------------------------------------------------------------------


class TestGatherEvidence:
    """Tests for gather_evidence()."""

    def test_well_known_types_skipped(self):
        from tools.extraction_tools import gather_evidence

        types = [
            {
                "name": "Product",
                "source": "well_known",
                "description": "desc",
                "evidence_patterns": ["product"],
            }
        ]
        state = {"approved_files": {"unstructured": []}}
        result = gather_evidence(state, types)
        assert "grounding_evidence" not in result[0]

    def test_discovered_type_gets_evidence(self):
        from tools.extraction_tools import gather_evidence

        types = [
            {
                "name": "Issue",
                "source": "discovered",
                "description": "desc",
                "evidence_patterns": ["issue", "defect"],
            }
        ]
        # Mock handle_search_files to return matches including different files
        mock_result = {
            "status": "success",
            "match_count": 3,
            "matches": [
                {"file": "reviews.md", "line_number": 10, "context": "Found an issue"},
                {"file": "other.md", "line_number": 5, "context": "Third issue"},
                {"file": "reviews.md", "line_number": 20, "context": "Another issue"},
            ],
        }
        state = {"approved_files": {"unstructured": [{"path": "reviews.md"}]}}
        with patch(
            "tools.extraction_tools.handle_search_files", return_value=mock_result
        ):
            result = gather_evidence(state, types)

        ev = result[0]["grounding_evidence"]
        assert ev["search_patterns"] == ["issue", "defect"]
        assert ev["total_mentions"] == 6  # 3 per pattern * 2 patterns
        # gather_evidence takes [:2] matches per pattern, so both reviews.md and other.md
        assert ev["files_with_evidence"] == 2
        assert len(ev["example_excerpts"]) <= 5

    def test_empty_evidence_patterns(self):
        from tools.extraction_tools import gather_evidence

        types = [
            {
                "name": "Mystery",
                "source": "discovered",
                "description": "desc",
                "evidence_patterns": [],
            }
        ]
        state = {"approved_files": {"unstructured": []}}
        result = gather_evidence(state, types)
        ev = result[0]["grounding_evidence"]
        assert ev["total_mentions"] == 0
        assert ev["files_with_evidence"] == 0
        assert ev["example_excerpts"] == []

    def test_excerpt_limit_five(self):
        from tools.extraction_tools import gather_evidence

        types = [
            {
                "name": "Issue",
                "source": "discovered",
                "description": "desc",
                "evidence_patterns": ["p1", "p2", "p3", "p4"],
            }
        ]
        mock_result = {
            "status": "success",
            "match_count": 5,
            "matches": [
                {"file": "f.md", "line_number": i, "context": f"Match {i}"}
                for i in range(5)
            ],
        }
        state = {"approved_files": {"unstructured": [{"path": "f.md"}]}}
        with patch(
            "tools.extraction_tools.handle_search_files", return_value=mock_result
        ):
            result = gather_evidence(state, types)

        ev = result[0]["grounding_evidence"]
        assert len(ev["example_excerpts"]) <= 5


# ---------------------------------------------------------------------------
# TestProposeEntityTypes
# ---------------------------------------------------------------------------


class TestProposeEntityTypes:
    """Tests for propose_entity_types() with mocked Claude API."""

    def _mock_response(self, json_data):
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = json.dumps(json_data)
        response = MagicMock()
        response.content = [text_block]
        return response

    def test_returns_parsed_json(self):
        from tools.extraction_tools import propose_entity_types

        expected = {
            "entity_types": [
                {
                    "name": "Product",
                    "source": "well_known",
                    "description": "A product",
                    "evidence_patterns": ["product"],
                }
            ],
            "analysis_summary": "Found products.",
        }

        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._mock_response(expected)

        state = {
            "approved_user_goal": {"kind": "analysis", "description": "test"},
            "approved_construction_plan": {},
            "approved_files": {"unstructured": []},
        }

        with patch("tools.extraction_tools.wrap_anthropic", return_value=mock_client):
            with patch("tools.extraction_tools.anthropic.Anthropic"):
                result = propose_entity_types(state, content="file content")

        assert result == expected
        assert mock_client.messages.create.called

    def test_uses_correct_model(self):
        from tools.extraction_tools import propose_entity_types

        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._mock_response(
            {"entity_types": [], "analysis_summary": ""}
        )
        state = {
            "approved_user_goal": {"kind": "test", "description": "test"},
            "approved_construction_plan": {},
            "approved_files": {"unstructured": []},
        }

        with patch("tools.extraction_tools.wrap_anthropic", return_value=mock_client):
            with patch("tools.extraction_tools.anthropic.Anthropic"):
                propose_entity_types(state, content="test")

        call_kwargs = mock_client.messages.create.call_args
        from core.config import CLAUDE_MODEL_STRUCTURED
        assert call_kwargs.kwargs["model"] == CLAUDE_MODEL_STRUCTURED

    def test_uses_output_config(self):
        from tools.extraction_tools import propose_entity_types, ENTITY_TYPE_JSON_SCHEMA

        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._mock_response(
            {"entity_types": [], "analysis_summary": ""}
        )
        state = {
            "approved_user_goal": {"kind": "test", "description": "test"},
            "approved_construction_plan": {},
            "approved_files": {"unstructured": []},
        }

        with patch("tools.extraction_tools.wrap_anthropic", return_value=mock_client):
            with patch("tools.extraction_tools.anthropic.Anthropic"):
                propose_entity_types(state, content="test")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "output_config" in call_kwargs
        assert call_kwargs["output_config"]["format"]["type"] == "json_schema"
        assert call_kwargs["output_config"]["format"]["schema"] is ENTITY_TYPE_JSON_SCHEMA
        assert "extra_headers" not in call_kwargs

    def test_passes_user_message(self):
        from tools.extraction_tools import propose_entity_types

        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._mock_response(
            {"entity_types": [], "analysis_summary": ""}
        )
        state = {
            "approved_user_goal": {"kind": "test", "description": "test"},
            "approved_construction_plan": {},
            "approved_files": {"unstructured": []},
        }

        with patch("tools.extraction_tools.wrap_anthropic", return_value=mock_client):
            with patch("tools.extraction_tools.anthropic.Anthropic"):
                propose_entity_types(
                    state, content="test", user_message="focus on quality defects"
                )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["messages"][0]["content"].startswith("focus on quality defects")
        assert "## File Content" in call_kwargs["messages"][0]["content"]

    def test_default_user_message(self):
        from tools.extraction_tools import propose_entity_types

        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._mock_response(
            {"entity_types": [], "analysis_summary": ""}
        )
        state = {
            "approved_user_goal": {"kind": "test", "description": "test"},
            "approved_construction_plan": {},
            "approved_files": {"unstructured": []},
        }

        with patch("tools.extraction_tools.wrap_anthropic", return_value=mock_client):
            with patch("tools.extraction_tools.anthropic.Anthropic"):
                propose_entity_types(state, content="test")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["messages"][0]["content"].startswith("Analyze the files and propose entity types.")
        assert "## File Content" in call_kwargs["messages"][0]["content"]

    def test_skips_thinking_blocks(self):
        from tools.extraction_tools import propose_entity_types

        thinking_block = MagicMock()
        thinking_block.type = "thinking"

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = json.dumps({"entity_types": [], "analysis_summary": "ok"})

        response = MagicMock()
        response.content = [thinking_block, text_block]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = response

        state = {
            "approved_user_goal": {"kind": "test", "description": "test"},
            "approved_construction_plan": {},
            "approved_files": {"unstructured": []},
        }

        with patch("tools.extraction_tools.wrap_anthropic", return_value=mock_client):
            with patch("tools.extraction_tools.anthropic.Anthropic"):
                result = propose_entity_types(state, content="test")

        assert result["analysis_summary"] == "ok"

    def test_ner_prompt_contains_example(self):
        from tools.extraction_tools import _build_ner_prompt

        state = {
            "approved_user_goal": {"kind": "test", "description": "test"},
            "approved_construction_plan": {},
        }
        prompt = _build_ner_prompt(state)
        assert "## Example" in prompt
        assert "NOT entity types" in prompt
        assert "File Content" not in prompt

    def test_ner_content_in_user_message_not_system(self):
        from tools.extraction_tools import propose_entity_types

        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._mock_response(
            {"entity_types": [], "analysis_summary": ""}
        )
        state = {
            "approved_user_goal": {"kind": "test", "description": "test"},
            "approved_construction_plan": {},
            "approved_files": {"unstructured": []},
        }

        with patch("tools.extraction_tools.wrap_anthropic", return_value=mock_client):
            with patch("tools.extraction_tools.anthropic.Anthropic"):
                propose_entity_types(state, content="my file content here")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        # File content should be in user message, not system prompt
        assert "my file content here" in call_kwargs["messages"][0]["content"]
        assert "my file content here" not in call_kwargs["system"]


# ---------------------------------------------------------------------------
# TestProposeFactTypes
# ---------------------------------------------------------------------------


class TestProposeFactTypes:
    """Tests for propose_fact_types() with mocked Claude API."""

    def _mock_response(self, json_data):
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = json.dumps(json_data)
        response = MagicMock()
        response.content = [text_block]
        return response

    def test_returns_parsed_json(self):
        from tools.extraction_tools import propose_fact_types

        expected = {
            "fact_types": [
                {
                    "subject": "Product",
                    "predicate": "has_issue",
                    "object": "Issue",
                    "description": "Product has issue",
                }
            ],
            "analysis_summary": "Found relationships.",
        }

        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._mock_response(expected)

        state = {
            "approved_user_goal": {"kind": "analysis", "description": "test"},
            "approved_entity_types": {
                "Product": {"source": "well_known", "description": "A product"},
                "Issue": {"source": "discovered", "description": "An issue"},
            },
            "approved_files": {"unstructured": []},
        }

        with patch("tools.extraction_tools.wrap_anthropic", return_value=mock_client):
            with patch("tools.extraction_tools.anthropic.Anthropic"):
                result = propose_fact_types(state, content="file content")

        assert result == expected

    def test_uses_output_config(self):
        from tools.extraction_tools import propose_fact_types, FACT_TYPE_JSON_SCHEMA

        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._mock_response(
            {"fact_types": [], "analysis_summary": ""}
        )
        state = {
            "approved_user_goal": {"kind": "test", "description": "test"},
            "approved_entity_types": {
                "Product": {"source": "well_known", "description": "A product"},
            },
            "approved_files": {"unstructured": []},
        }

        with patch("tools.extraction_tools.wrap_anthropic", return_value=mock_client):
            with patch("tools.extraction_tools.anthropic.Anthropic"):
                propose_fact_types(state, content="test")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "output_config" in call_kwargs
        assert call_kwargs["output_config"]["format"]["type"] == "json_schema"
        assert call_kwargs["output_config"]["format"]["schema"] is FACT_TYPE_JSON_SCHEMA
        assert "extra_headers" not in call_kwargs

    def test_passes_user_message(self):
        from tools.extraction_tools import propose_fact_types

        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._mock_response(
            {"fact_types": [], "analysis_summary": ""}
        )
        state = {
            "approved_user_goal": {"kind": "test", "description": "test"},
            "approved_entity_types": {
                "Product": {"source": "well_known", "description": "A product"},
            },
            "approved_files": {"unstructured": []},
        }

        with patch("tools.extraction_tools.wrap_anthropic", return_value=mock_client):
            with patch("tools.extraction_tools.anthropic.Anthropic"):
                propose_fact_types(
                    state, content="test", user_message="focus on supply chain"
                )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["messages"][0]["content"].startswith("focus on supply chain")
        assert "## File Content" in call_kwargs["messages"][0]["content"]

    def test_fact_prompt_contains_example(self):
        from tools.extraction_tools import _build_fact_prompt

        state = {
            "approved_user_goal": {"kind": "test", "description": "test"},
            "approved_entity_types": {
                "Product": {"source": "well_known", "description": "A product"},
            },
        }
        prompt = _build_fact_prompt(state)
        assert "## Example" in prompt
        assert "Bad fact types" in prompt
        assert "File Content" not in prompt


# ---------------------------------------------------------------------------
# TestFormatResponses
# ---------------------------------------------------------------------------


class TestFormatResponses:
    """Tests for response formatting helpers."""

    def test_entity_proposal_response_format(self):
        from tools.extraction_tools import _format_entity_proposal_response

        result = {"analysis_summary": "Analyzed 1 file."}
        types = [
            {
                "name": "Product",
                "source": "well_known",
                "description": "A product from the catalog",
                "evidence_patterns": ["product"],
            },
            {
                "name": "Issue",
                "source": "discovered",
                "description": "A defect or problem",
                "evidence_patterns": ["issue"],
                "grounding_evidence": {
                    "search_patterns": ["issue", "defect"],
                    "total_mentions": 12,
                    "example_excerpts": ["found an issue"],
                    "files_with_evidence": 1,
                },
            },
        ]
        response = _format_entity_proposal_response(result, types)
        assert "Product" in response
        assert "[well-known]" in response
        assert "Issue" in response
        assert "[discovered]" in response
        assert "12 mentions" in response
        assert "approve" in response.lower()

    def test_zero_evidence_flagged(self):
        from tools.extraction_tools import _format_entity_proposal_response

        result = {"analysis_summary": "Analyzed."}
        types = [
            {
                "name": "Mystery",
                "source": "discovered",
                "description": "A mysterious entity",
                "evidence_patterns": ["mystery", "enigma"],
                "grounding_evidence": {
                    "search_patterns": ["mystery", "enigma"],
                    "total_mentions": 0,
                    "example_excerpts": [],
                    "files_with_evidence": 0,
                },
            },
        ]
        response = _format_entity_proposal_response(result, types)
        assert "[no evidence found]" in response
        assert "mystery" in response
        assert "enigma" in response

    def test_fact_proposal_response_format(self):
        from tools.extraction_tools import _format_fact_proposal_response

        result = {
            "fact_types": [
                {
                    "subject": "Product",
                    "predicate": "has_issue",
                    "object": "Issue",
                    "description": "Links products to their issues",
                }
            ],
            "analysis_summary": "Analyzed relationships.",
        }
        response = _format_fact_proposal_response(result)
        assert "(Product)-[has_issue]->(Issue)" in response
        assert "approve" in response.lower()


# ---------------------------------------------------------------------------
# TestFirstCallDetection (MCP tool level) — uses _run_* functions
# ---------------------------------------------------------------------------


class TestFirstCallDetectionNER:
    """Tests for first-call detection in _run_ner_extraction."""

    def _make_state(self, has_conversation=False, has_proposal=False):
        state = {
            "approved_user_goal": {"kind": "test", "description": "test"},
            "approved_files": {"unstructured": [{"path": "test.md"}]},
            "approved_construction_plan": {},
        }
        if has_conversation:
            state["_ner_extraction_conversation"] = [
                {"role": "user", "content": "hello"}
            ]
        if has_proposal:
            state["proposed_entity_types"] = {
                "Product": {"source": "well_known", "description": "A product"}
            }
        return state

    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._check_project_active", return_value=None)
    def test_first_call_uses_structured_output(self, mock_guard, mock_save):
        """First call (no conversation, no proposal) uses structured output."""
        from mcp_server.server import _run_ner_extraction

        state = self._make_state(has_conversation=False, has_proposal=False)

        mock_proposal = {
            "entity_types": [
                {
                    "name": "Product",
                    "source": "well_known",
                    "description": "A product",
                    "evidence_patterns": ["product"],
                }
            ],
            "analysis_summary": "Found products.",
        }

        with patch("mcp_server.server._load_clean_state", return_value=state):
            with patch("mcp_server.server._pop_conversation", return_value=None):
                with patch(
                    "tools.extraction_tools.propose_entity_types",
                    return_value=mock_proposal,
                ):
                    with patch(
                        "tools.extraction_tools.build_file_content",
                        return_value=("content", True),
                    ):
                        with patch(
                            "tools.extraction_tools.gather_evidence",
                            return_value=mock_proposal["entity_types"],
                        ):
                            result = _run_ner_extraction("analyze my files")

        assert result["status"]["mode"] == "structured_output"
        assert result["status"]["has_proposed_entities"] is True

    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._store_conversation")
    @patch("mcp_server.server._check_project_active", return_value=None)
    def test_subsequent_call_uses_agent_loop(self, mock_guard, mock_store, mock_save):
        """When conversation exists, routes through agent loop."""
        from mcp_server.server import _run_ner_extraction

        state = self._make_state(has_conversation=True)
        conversation = [{"role": "user", "content": "hello"}]

        mock_agent = MagicMock()
        mock_agent.run.return_value = ("Agent response", state, conversation)

        with patch("mcp_server.server._load_clean_state", return_value=state):
            with patch(
                "mcp_server.server._pop_conversation", return_value=conversation
            ):
                with patch(
                    "mcp_server.server.NerExtractionAgent", return_value=mock_agent
                ):
                    result = _run_ner_extraction("add Issue type")

        assert result["agent_response"] == "Agent response"
        assert "mode" not in result["status"]
        mock_agent.run.assert_called_once()

    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._store_conversation")
    @patch("mcp_server.server._check_project_active", return_value=None)
    def test_existing_proposal_uses_agent_loop(self, mock_guard, mock_store, mock_save):
        """When proposal already exists, routes through agent loop."""
        from mcp_server.server import _run_ner_extraction

        state = self._make_state(has_proposal=True)

        mock_agent = MagicMock()
        mock_agent.run.return_value = ("Agent response", state, [])

        with patch("mcp_server.server._load_clean_state", return_value=state):
            with patch("mcp_server.server._pop_conversation", return_value=None):
                with patch(
                    "mcp_server.server.NerExtractionAgent", return_value=mock_agent
                ):
                    result = _run_ner_extraction("modify proposal")

        mock_agent.run.assert_called_once()

    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._store_conversation")
    @patch("mcp_server.server._check_project_active", return_value=None)
    def test_structured_output_seeds_conversation(
        self, mock_guard, mock_store, mock_save
    ):
        """Structured output path seeds conversation for follow-up calls."""
        from mcp_server.server import _run_ner_extraction

        state = self._make_state(has_conversation=False, has_proposal=False)

        mock_proposal = {
            "entity_types": [
                {
                    "name": "Product",
                    "source": "well_known",
                    "description": "A product",
                    "evidence_patterns": ["product"],
                }
            ],
            "analysis_summary": "Found products.",
        }

        with patch("mcp_server.server._load_clean_state", return_value=state):
            with patch("mcp_server.server._pop_conversation", return_value=None):
                with patch(
                    "tools.extraction_tools.propose_entity_types",
                    return_value=mock_proposal,
                ):
                    with patch(
                        "tools.extraction_tools.build_file_content",
                        return_value=("content", True),
                    ):
                        with patch(
                            "tools.extraction_tools.gather_evidence",
                            return_value=mock_proposal["entity_types"],
                        ):
                            result = _run_ner_extraction("analyze my files")

        assert result["status"]["mode"] == "structured_output"
        # _store_conversation should have been called with the seed
        mock_store.assert_called_once()
        call_args = mock_store.call_args
        assert call_args[0][1] == "_ner_extraction_conversation"
        seed = call_args[0][2]
        assert len(seed) == 2
        assert seed[0]["role"] == "user"
        assert seed[0]["content"] == "analyze my files"
        assert seed[1]["role"] == "assistant"


class TestFirstCallDetectionFact:
    """Tests for first-call detection in _run_fact_extraction."""

    def _make_state(self, has_conversation=False, has_proposal=False):
        state = {
            "approved_user_goal": {"kind": "test", "description": "test"},
            "approved_files": {"unstructured": [{"path": "test.md"}]},
            "approved_entity_types": {
                "Product": {"source": "well_known", "description": "A product"},
                "Issue": {"source": "discovered", "description": "An issue"},
            },
        }
        if has_conversation:
            state["_fact_extraction_conversation"] = [
                {"role": "user", "content": "hello"}
            ]
        if has_proposal:
            state["proposed_fact_types"] = {
                "has_issue": {
                    "subject_label": "Product",
                    "predicate_label": "has_issue",
                    "object_label": "Issue",
                }
            }
        return state

    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._check_project_active", return_value=None)
    def test_first_call_uses_structured_output(self, mock_guard, mock_save):
        """First call (no conversation, no proposal) uses structured output."""
        from mcp_server.server import _run_fact_extraction

        state = self._make_state(has_conversation=False, has_proposal=False)

        mock_proposal = {
            "fact_types": [
                {
                    "subject": "Product",
                    "predicate": "has_issue",
                    "object": "Issue",
                    "description": "Links products to issues",
                }
            ],
            "analysis_summary": "Found relationships.",
        }

        with patch("mcp_server.server._load_clean_state", return_value=state):
            with patch("mcp_server.server._pop_conversation", return_value=None):
                with patch(
                    "tools.extraction_tools.propose_fact_types",
                    return_value=mock_proposal,
                ):
                    with patch(
                        "tools.extraction_tools.build_file_content",
                        return_value=("content", True),
                    ):
                        result = _run_fact_extraction("propose relationships")

        assert result["status"]["mode"] == "structured_output"
        assert result["status"]["has_proposed_facts"] is True
        facts = result["status"]["proposed_facts"]
        assert "has_issue" in facts

    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._check_project_active", return_value=None)
    def test_invalid_entity_types_filtered(self, mock_guard, mock_save):
        """Facts referencing non-approved entity types are filtered out."""
        from mcp_server.server import _run_fact_extraction

        state = self._make_state()

        mock_proposal = {
            "fact_types": [
                {
                    "subject": "Product",
                    "predicate": "has_issue",
                    "object": "Issue",
                    "description": "Valid",
                },
                {
                    "subject": "Unknown",
                    "predicate": "links_to",
                    "object": "Issue",
                    "description": "Invalid subject",
                },
                {
                    "subject": "Product",
                    "predicate": "INVALID FORMAT",
                    "object": "Issue",
                    "description": "Invalid predicate",
                },
            ],
            "analysis_summary": "Mixed.",
        }

        with patch("mcp_server.server._load_clean_state", return_value=state):
            with patch("mcp_server.server._pop_conversation", return_value=None):
                with patch(
                    "tools.extraction_tools.propose_fact_types",
                    return_value=mock_proposal,
                ):
                    with patch(
                        "tools.extraction_tools.build_file_content",
                        return_value=("content", True),
                    ):
                        result = _run_fact_extraction("propose")

        # Only the valid fact should survive
        facts = result["status"]["proposed_facts"]
        assert len(facts) == 1
        assert "has_issue" in facts

    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._store_conversation")
    @patch("mcp_server.server._check_project_active", return_value=None)
    def test_structured_output_seeds_conversation(
        self, mock_guard, mock_store, mock_save
    ):
        """Structured output path seeds conversation for follow-up calls."""
        from mcp_server.server import _run_fact_extraction

        state = self._make_state(has_conversation=False, has_proposal=False)

        mock_proposal = {
            "fact_types": [
                {
                    "subject": "Product",
                    "predicate": "has_issue",
                    "object": "Issue",
                    "description": "Links products to issues",
                }
            ],
            "analysis_summary": "Found relationships.",
        }

        with patch("mcp_server.server._load_clean_state", return_value=state):
            with patch("mcp_server.server._pop_conversation", return_value=None):
                with patch(
                    "tools.extraction_tools.propose_fact_types",
                    return_value=mock_proposal,
                ):
                    with patch(
                        "tools.extraction_tools.build_file_content",
                        return_value=("content", True),
                    ):
                        result = _run_fact_extraction("propose relationships")

        assert result["status"]["mode"] == "structured_output"
        # _store_conversation should have been called with the seed
        mock_store.assert_called_once()
        call_args = mock_store.call_args
        assert call_args[0][1] == "_fact_extraction_conversation"
        seed = call_args[0][2]
        assert len(seed) == 2
        assert seed[0]["role"] == "user"
        assert seed[0]["content"] == "propose relationships"
        assert seed[1]["role"] == "assistant"


# ---------------------------------------------------------------------------
# TestFallbackToAgentLoop
# ---------------------------------------------------------------------------


class TestFallbackToAgentLoop:
    """Tests for fallback when structured output fails."""

    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._store_conversation")
    @patch("mcp_server.server._check_project_active", return_value=None)
    def test_ner_fallback_on_api_error(self, mock_guard, mock_store, mock_save):
        """If structured output fails, falls back to agent loop."""
        from mcp_server.server import _run_ner_extraction

        state = {
            "approved_user_goal": {"kind": "test", "description": "test"},
            "approved_files": {"unstructured": [{"path": "test.md"}]},
            "approved_construction_plan": {},
        }

        mock_agent = MagicMock()
        mock_agent.run.return_value = ("Fallback response", state, [])

        with patch("mcp_server.server._load_clean_state", return_value=state):
            with patch("mcp_server.server._pop_conversation", return_value=None):
                with patch(
                    "tools.extraction_tools.build_file_content",
                    side_effect=Exception("API error"),
                ):
                    with patch(
                        "mcp_server.server.NerExtractionAgent",
                        return_value=mock_agent,
                    ):
                        result = _run_ner_extraction("analyze")

        assert result["agent_response"] == "Fallback response"
        mock_agent.run.assert_called_once()

    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._store_conversation")
    @patch("mcp_server.server._check_project_active", return_value=None)
    def test_fact_fallback_on_api_error(self, mock_guard, mock_store, mock_save):
        """If structured output fails for facts, falls back to agent loop."""
        from mcp_server.server import _run_fact_extraction

        state = {
            "approved_user_goal": {"kind": "test", "description": "test"},
            "approved_files": {"unstructured": [{"path": "test.md"}]},
            "approved_entity_types": {
                "Product": {"source": "well_known", "description": "A product"},
            },
        }

        mock_agent = MagicMock()
        mock_agent.run.return_value = ("Fallback response", state, [])

        with patch("mcp_server.server._load_clean_state", return_value=state):
            with patch("mcp_server.server._pop_conversation", return_value=None):
                with patch(
                    "tools.extraction_tools.build_file_content",
                    side_effect=RuntimeError("Connection failed"),
                ):
                    with patch(
                        "mcp_server.server.FactExtractionAgent",
                        return_value=mock_agent,
                    ):
                        result = _run_fact_extraction("propose")

        assert result["agent_response"] == "Fallback response"
        mock_agent.run.assert_called_once()


# ---------------------------------------------------------------------------
# TestPerFileFallback
# ---------------------------------------------------------------------------


class TestPerFileFallback:
    """Tests for per-file fallback when content exceeds budget."""

    @patch("mcp_server.server._save_state")
    @patch("mcp_server.server._check_project_active", return_value=None)
    def test_ner_per_file_calls_and_merges(self, mock_guard, mock_save):
        """When build_file_content returns per-file dict, calls per file and merges."""
        from mcp_server.server import _run_ner_extraction

        state = {
            "approved_user_goal": {"kind": "test", "description": "test"},
            "approved_files": {
                "unstructured": [{"path": "a.md"}, {"path": "b.md"}]
            },
            "approved_construction_plan": {},
        }

        per_file_content = {
            "a.md": "Content of file A",
            "b.md": "Content of file B",
        }

        proposal_a = {
            "entity_types": [
                {
                    "name": "Product",
                    "source": "well_known",
                    "description": "desc A",
                    "evidence_patterns": ["product"],
                }
            ],
            "analysis_summary": "File A analysis.",
        }
        proposal_b = {
            "entity_types": [
                {
                    "name": "Product",
                    "source": "well_known",
                    "description": "A much longer description from B",
                    "evidence_patterns": ["item"],
                },
                {
                    "name": "Issue",
                    "source": "discovered",
                    "description": "An issue",
                    "evidence_patterns": ["issue"],
                },
            ],
            "analysis_summary": "File B analysis.",
        }

        call_count = {"n": 0}

        def mock_propose(state, content=None):
            call_count["n"] += 1
            if "file A" in (content or ""):
                return proposal_a
            return proposal_b

        with patch("mcp_server.server._load_clean_state", return_value=state):
            with patch("mcp_server.server._pop_conversation", return_value=None):
                with patch(
                    "tools.extraction_tools.build_file_content",
                    return_value=(per_file_content, False),
                ):
                    with patch(
                        "tools.extraction_tools.propose_entity_types",
                        side_effect=mock_propose,
                    ):
                        with patch(
                            "tools.extraction_tools.gather_evidence",
                            side_effect=lambda s, t: t,
                        ):
                            result = _run_ner_extraction("analyze")

        assert call_count["n"] == 2  # One call per file
        assert result["status"]["mode"] == "structured_output"
        # Should have merged Product (longer desc) + Issue
        proposed = result["status"]["proposed_entities"]
        assert "Product" in proposed
        assert "Issue" in proposed
