"""Unit tests for Text Graph Builder and Entity Resolution utilities.

Tests pure functions that don't require Neo4j or OpenAI connections.
"""

import os
import sys
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import tempfile

from pipelines.text_builder import (
    build_entity_schema,
    _resolve_files_to_process,
    detect_splitting_strategy,
    _create_splitter_from_config,
    MarkdownSectionSplitter,
    ParagraphSplitter,
    RegexTextSplitter,
)
from pipelines.entity_resolution import normalize_key, correlate_entity_and_domain_keys


# -- Fixtures --


def _make_state(
    entity_types=None,
    fact_types=None,
    unstructured_files=None,
    processed_files=None,
):
    """Build a test state dict."""
    state = {}
    if entity_types is not None:
        state["approved_entity_types"] = entity_types
    if fact_types is not None:
        state["approved_fact_types"] = fact_types
    if unstructured_files is not None:
        state["approved_files"] = {
            "unstructured": [{"path": f} for f in unstructured_files]
        }
    if processed_files is not None:
        state["text_graph_progress"] = {
            "processed_files": [{"file": f} for f in processed_files],
            "pending_files": [],
        }
    return state


# -- build_entity_schema tests --


class TestBuildEntitySchema:
    def test_basic_schema(self):
        """Build schema from entity types and fact types."""
        state = _make_state(
            entity_types={
                "Product": {"source": "well_known"},
                "Issue": {"source": "discovered"},
                "Feature": {"source": "discovered"},
            },
            fact_types={
                "has_issue": {
                    "subject_label": "Product",
                    "predicate_label": "has_issue",
                    "object_label": "Issue",
                },
                "includes_feature": {
                    "subject_label": "Product",
                    "predicate_label": "includes_feature",
                    "object_label": "Feature",
                },
            },
        )
        schema = build_entity_schema(state)

        assert schema["node_types"] == ["Feature", "Issue", "Product"]
        assert schema["relationship_types"] == ["HAS_ISSUE", "INCLUDES_FEATURE"]
        assert ["Product", "HAS_ISSUE", "Issue"] in schema["patterns"]
        assert ["Product", "INCLUDES_FEATURE", "Feature"] in schema["patterns"]
        assert schema["additional_node_types"] is False

    def test_empty_facts(self):
        """Schema with entities but no fact types."""
        state = _make_state(
            entity_types={"Product": {}, "Location": {}},
            fact_types={},
        )
        schema = build_entity_schema(state)

        assert schema["node_types"] == ["Location", "Product"]
        assert schema["relationship_types"] == []
        assert schema["patterns"] == []

    def test_missing_state_keys(self):
        """Schema from empty state returns empty lists."""
        schema = build_entity_schema({})
        assert schema["node_types"] == []
        assert schema["relationship_types"] == []
        assert schema["patterns"] == []
        assert schema["additional_node_types"] is False


# -- _resolve_files_to_process tests --


class TestResolveFiles:
    FILES = [
        "reviews/gothenburg_table_reviews.md",
        "reviews/malmo_desk_reviews.md",
        "reviews/stockholm_chair_reviews.md",
    ]

    def test_all_files(self):
        """Message='all' returns all unprocessed files."""
        state = _make_state(unstructured_files=self.FILES)
        result = _resolve_files_to_process(state, "all")
        assert result == self.FILES

    def test_remaining_files(self):
        """Message='remaining' returns all pending files."""
        state = _make_state(unstructured_files=self.FILES)
        result = _resolve_files_to_process(state, "remaining")
        assert result == self.FILES

    def test_specific_file(self):
        """Message with filename returns just that file."""
        state = _make_state(unstructured_files=self.FILES)
        result = _resolve_files_to_process(state, "process gothenburg_table_reviews.md")
        assert result == ["reviews/gothenburg_table_reviews.md"]

    def test_specific_file_no_extension(self):
        """Message with filename without extension."""
        state = _make_state(unstructured_files=self.FILES)
        result = _resolve_files_to_process(state, "process gothenburg_table_reviews")
        assert result == ["reviews/gothenburg_table_reviews.md"]

    def test_next_file(self):
        """Message='next' returns the first unprocessed file."""
        state = _make_state(
            unstructured_files=self.FILES,
            processed_files=["reviews/gothenburg_table_reviews.md"],
        )
        result = _resolve_files_to_process(state, "next")
        assert result == ["reviews/malmo_desk_reviews.md"]

    def test_next_file_none_processed(self):
        """Message='next' with nothing processed returns first file."""
        state = _make_state(unstructured_files=self.FILES)
        result = _resolve_files_to_process(state, "next")
        assert result == ["reviews/gothenburg_table_reviews.md"]

    def test_all_already_processed(self):
        """All files already processed returns empty list."""
        state = _make_state(
            unstructured_files=self.FILES,
            processed_files=self.FILES,
        )
        result = _resolve_files_to_process(state, "all")
        assert result == []

    def test_specific_already_processed(self):
        """Specific file already processed returns empty list."""
        state = _make_state(
            unstructured_files=self.FILES,
            processed_files=["reviews/gothenburg_table_reviews.md"],
        )
        result = _resolve_files_to_process(
            state, "process gothenburg_table_reviews.md"
        )
        assert result == []

    def test_no_unstructured_files(self):
        """No unstructured files returns empty list."""
        state = _make_state(unstructured_files=[])
        result = _resolve_files_to_process(state, "all")
        assert result == []

    def test_empty_message(self):
        """Empty message returns all pending (default behavior)."""
        state = _make_state(unstructured_files=self.FILES)
        result = _resolve_files_to_process(state, "")
        assert result == self.FILES


# -- normalize_key tests --


class TestNormalizeKey:
    def test_strip_label_prefix_underscore(self):
        assert normalize_key("Product", "Product_name") == "name"

    def test_strip_label_prefix_space(self):
        assert normalize_key("Product", "Product Name") == "name"

    def test_lowercase_prefix(self):
        assert normalize_key("Product", "product name") == "name"

    def test_no_prefix(self):
        assert normalize_key("Product", "price") == "price"

    def test_preserve_non_prefix(self):
        assert normalize_key("Product", "description") == "description"

    def test_whitespace_handling(self):
        assert normalize_key("Product", "  price  ") == "price"


# -- correlate_entity_and_domain_keys tests --


class TestCorrelateKeys:
    def test_exact_match_after_normalization(self):
        """Keys that normalize to the same string should match."""
        result = correlate_entity_and_domain_keys(
            "Product",
            entity_keys=["name"],
            domain_keys=["product_name"],
            similarity=0.9,
        )
        assert len(result) == 1
        assert result[0][0] == "name"
        assert result[0][1] == "product_name"
        assert result[0][2] == 1.0  # Exact match after normalization

    def test_no_match_below_threshold(self):
        """Unrelated keys should not match at high threshold."""
        result = correlate_entity_and_domain_keys(
            "Product",
            entity_keys=["name"],
            domain_keys=["supplier_id"],
            similarity=0.9,
        )
        assert len(result) == 0

    def test_multiple_matches_sorted(self):
        """Multiple matches sorted by score descending."""
        result = correlate_entity_and_domain_keys(
            "Product",
            entity_keys=["name", "description"],
            domain_keys=["product_name", "description", "price"],
            similarity=0.5,
        )
        # Should find name<->product_name and description<->description
        assert len(result) >= 2
        # Best match first
        assert result[0][2] >= result[1][2]

    def test_low_threshold_matches_more(self):
        """Lower threshold finds more matches."""
        result_high = correlate_entity_and_domain_keys(
            "Product",
            entity_keys=["name", "price"],
            domain_keys=["product_name", "unit_price"],
            similarity=0.9,
        )
        result_low = correlate_entity_and_domain_keys(
            "Product",
            entity_keys=["name", "price"],
            domain_keys=["product_name", "unit_price"],
            similarity=0.3,
        )
        assert len(result_low) >= len(result_high)


# -- Adaptive Splitting: detect_splitting_strategy tests --


def _write_temp_file(content: str) -> str:
    """Write content to a temporary file and return its path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return f.name


class TestDetectSplittingStrategy:
    """Test auto-detection of markdown splitting strategy."""

    def test_detect_horizontal_rules(self):
        """File with >=3 horizontal rules -> RegexTextSplitter."""
        content = "Review 1\n---\nReview 2\n---\nReview 3\n---\nReview 4"
        path = _write_temp_file(content)
        try:
            splitter = detect_splitting_strategy(path)
            assert isinstance(splitter, RegexTextSplitter)
        finally:
            os.unlink(path)

    def test_detect_headings(self):
        """File with >=3 headings and no horizontal rules -> MarkdownSectionSplitter."""
        content = "# Title\n\nIntro\n\n## Section 1\nContent 1\n\n## Section 2\nContent 2\n\n## Section 3\nContent 3"
        path = _write_temp_file(content)
        try:
            splitter = detect_splitting_strategy(path)
            assert isinstance(splitter, MarkdownSectionSplitter)
        finally:
            os.unlink(path)

    def test_detect_paragraphs(self):
        """File with neither horizontal rules nor headings -> ParagraphSplitter."""
        content = "First paragraph about something.\n\nSecond paragraph continues.\n\nThird paragraph ends."
        path = _write_temp_file(content)
        try:
            splitter = detect_splitting_strategy(path)
            assert isinstance(splitter, ParagraphSplitter)
        finally:
            os.unlink(path)

    def test_horizontal_rules_take_priority(self):
        """File with both horizontal rules and headings -> RegexTextSplitter (rules win)."""
        content = "# Title\n## Section\nContent\n---\nMore\n---\nMore\n---\nEnd"
        path = _write_temp_file(content)
        try:
            splitter = detect_splitting_strategy(path)
            assert isinstance(splitter, RegexTextSplitter)
        finally:
            os.unlink(path)

    def test_two_horizontal_rules_not_enough(self):
        """File with only 2 horizontal rules -> not delimiter (threshold is 3)."""
        content = "Section A\n---\nSection B\n---\nSection C"
        path = _write_temp_file(content)
        try:
            splitter = detect_splitting_strategy(path)
            assert not isinstance(splitter, RegexTextSplitter)
        finally:
            os.unlink(path)

    def test_file_not_found_falls_back(self):
        """Non-existent file -> ParagraphSplitter fallback."""
        splitter = detect_splitting_strategy("/nonexistent/path/file.md")
        assert isinstance(splitter, ParagraphSplitter)


# -- Adaptive Splitting: _create_splitter_from_config tests --


class TestCreateSplitterFromConfig:
    """Test creating splitters from state configuration."""

    def test_delimiter_strategy(self):
        splitter = _create_splitter_from_config({"strategy": "delimiter", "pattern": "==="})
        assert isinstance(splitter, RegexTextSplitter)
        assert splitter.re == "==="

    def test_delimiter_default_pattern(self):
        splitter = _create_splitter_from_config({"strategy": "delimiter"})
        assert isinstance(splitter, RegexTextSplitter)
        assert splitter.re == "---"

    def test_sections_strategy(self):
        splitter = _create_splitter_from_config({"strategy": "sections"})
        assert isinstance(splitter, MarkdownSectionSplitter)

    def test_paragraphs_strategy(self):
        splitter = _create_splitter_from_config({"strategy": "paragraphs"})
        assert isinstance(splitter, ParagraphSplitter)

    def test_unknown_strategy_falls_back(self):
        splitter = _create_splitter_from_config({"strategy": "something_else"})
        assert isinstance(splitter, ParagraphSplitter)

    def test_empty_config(self):
        """Empty dict defaults to delimiter with '---' pattern."""
        splitter = _create_splitter_from_config({})
        assert isinstance(splitter, RegexTextSplitter)
        assert splitter.re == "---"


# -- Adaptive Splitting: splitter output tests --


class TestMarkdownSectionSplitter:
    """Test MarkdownSectionSplitter output."""

    def test_splits_on_headings(self):
        text = "# Title\nIntro text\n\n## Section 1\nContent 1\n\n## Section 2\nContent 2"
        splitter = MarkdownSectionSplitter()
        chunks = asyncio.run(splitter.run(text))
        # Should produce 3 chunks: Title section, Section 1, Section 2
        assert len(chunks.chunks) == 3
        assert "# Title" in chunks.chunks[0].text
        assert "## Section 1" in chunks.chunks[1].text
        assert "## Section 2" in chunks.chunks[2].text

    def test_handles_preamble(self):
        """Text before first heading is kept as preamble chunk."""
        text = "Some preamble text\n\n# First Heading\nContent"
        splitter = MarkdownSectionSplitter()
        chunks = asyncio.run(splitter.run(text))
        assert len(chunks.chunks) == 2
        assert "preamble" in chunks.chunks[0].text
        assert "# First Heading" in chunks.chunks[1].text

    def test_nested_headings(self):
        """Different heading levels all trigger splits."""
        text = "# H1\nContent 1\n## H2\nContent 2\n### H3\nContent 3"
        splitter = MarkdownSectionSplitter()
        chunks = asyncio.run(splitter.run(text))
        assert len(chunks.chunks) == 3

    def test_no_headings_returns_single_chunk(self):
        """Text with no headings returns one chunk."""
        text = "Just some plain text without any headings."
        splitter = MarkdownSectionSplitter()
        chunks = asyncio.run(splitter.run(text))
        assert len(chunks.chunks) == 1

    def test_chunks_have_sequential_indices(self):
        text = "# A\ntext\n## B\ntext\n## C\ntext"
        splitter = MarkdownSectionSplitter()
        chunks = asyncio.run(splitter.run(text))
        indices = [c.index for c in chunks.chunks]
        assert indices == list(range(len(chunks.chunks)))


class TestParagraphSplitter:
    """Test ParagraphSplitter output."""

    def test_splits_on_double_newlines(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        splitter = ParagraphSplitter()
        chunks = asyncio.run(splitter.run(text))
        assert len(chunks.chunks) == 3
        assert chunks.chunks[0].text == "Paragraph one."
        assert chunks.chunks[1].text == "Paragraph two."
        assert chunks.chunks[2].text == "Paragraph three."

    def test_skips_empty_paragraphs(self):
        """Multiple blank lines don't produce empty chunks."""
        text = "First.\n\n\n\n\nSecond.\n\n\n\nThird."
        splitter = ParagraphSplitter()
        chunks = asyncio.run(splitter.run(text))
        assert len(chunks.chunks) == 3

    def test_single_paragraph(self):
        text = "Just one paragraph with no breaks."
        splitter = ParagraphSplitter()
        chunks = asyncio.run(splitter.run(text))
        assert len(chunks.chunks) == 1

    def test_strips_whitespace(self):
        text = "  First paragraph.  \n\n  Second paragraph.  "
        splitter = ParagraphSplitter()
        chunks = asyncio.run(splitter.run(text))
        assert chunks.chunks[0].text == "First paragraph."
        assert chunks.chunks[1].text == "Second paragraph."

    def test_chunks_have_sequential_indices(self):
        text = "A\n\nB\n\nC\n\nD"
        splitter = ParagraphSplitter()
        chunks = asyncio.run(splitter.run(text))
        indices = [c.index for c in chunks.chunks]
        assert indices == [0, 1, 2, 3]
