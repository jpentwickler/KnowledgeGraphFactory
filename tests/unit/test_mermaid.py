"""
Unit tests for US017: Mermaid Diagram Generation

Tests:
- _sanitize_id helper (5 tests)
- _truncate_properties helper (4 tests)
- generate_schema_diagram (10 tests)
- generate_live_diagram (6 tests)
- _run_kg_diagram MCP impl (10 tests)
- Edge cases (4 tests)
"""

import os
import pytest
from unittest.mock import patch, MagicMock


# =============================================================================
# Fixtures / Helpers
# =============================================================================

def _make_state(**overrides):
    """Build a pipeline state dict with optional overrides."""
    state = {}
    state.update(overrides)
    return state


def _make_construction_plan(nodes=None, rels=None):
    """Build a minimal approved_construction_plan."""
    plan = {}
    for node in (nodes or []):
        label = node["label"]
        plan[label] = {
            "construction_type": "node",
            "label": label,
            "properties": node.get("properties", []),
            "unique_column_name": node.get("unique_column_name", f"{label.lower()}_id"),
        }
    for rel in (rels or []):
        key = rel["type"]
        plan[key] = {
            "construction_type": "relationship",
            "relationship_type": rel["type"],
            "from_node_label": rel["from"],
            "to_node_label": rel["to"],
            "properties": rel.get("properties", []),
        }
    return plan


def _make_entity_types(*names):
    """Build approved_entity_types from a list of names."""
    return {name: {"description": f"A {name}", "source": "test"} for name in names}


def _make_fact_types(*triples):
    """Build approved_fact_types from (predicate, subject, object) triples."""
    return {
        pred: {
            "predicate_label": pred,
            "subject_label": subj,
            "object_label": obj,
        }
        for pred, subj, obj in triples
    }


def _mock_neo4j_session(label_rows=None, rel_rows=None):
    """Create a mock Neo4j driver that returns specified rows."""
    mock_driver = MagicMock()
    mock_session = MagicMock()

    label_records = []
    for row in (label_rows or []):
        record = MagicMock()
        record.__iter__ = lambda self, items=row.items(): iter(items)
        record.keys.return_value = list(row.keys())
        record.__getitem__ = lambda self, key, r=row: r[key]
        # dict() support
        def make_dict(r=row):
            return dict(r)
        label_records.append(row)

    rel_records = []
    for row in (rel_rows or []):
        rel_records.append(row)

    def run_side_effect(query, **kwargs):
        result = MagicMock()
        if "UNWIND labels" in query:
            result.__iter__ = lambda self: iter(label_records)
        elif "type(r)" in query:
            result.__iter__ = lambda self: iter(rel_records)
        else:
            result.__iter__ = lambda self: iter([])
        return result

    mock_session.run = run_side_effect
    mock_driver.session.return_value.__enter__ = lambda self: mock_session
    mock_driver.session.return_value.__exit__ = lambda self, *a: None

    return mock_driver


# =============================================================================
# TestSanitizeId
# =============================================================================

class TestSanitizeId:
    """Tests for _sanitize_id helper."""

    def test_spaces_replaced(self):
        from utils.mermaid import _sanitize_id
        assert _sanitize_id("My Label") == "My_Label"

    def test_special_chars_replaced(self):
        from utils.mermaid import _sanitize_id
        assert _sanitize_id("foo-bar.baz") == "foo_bar_baz"

    def test_digit_prefix(self):
        from utils.mermaid import _sanitize_id
        result = _sanitize_id("3DModel")
        assert result == "n_3DModel"
        assert not result[0].isdigit()

    def test_empty_string(self):
        from utils.mermaid import _sanitize_id
        assert _sanitize_id("") == "node_unknown"

    def test_all_special_chars(self):
        from utils.mermaid import _sanitize_id
        assert _sanitize_id("---") == "node_unknown"


# =============================================================================
# TestTruncateProperties
# =============================================================================

class TestTruncateProperties:
    """Tests for _truncate_properties helper."""

    def test_under_limit(self):
        from utils.mermaid import _truncate_properties
        result = _truncate_properties(["a", "b", "c"])
        assert result == "a, b, c"

    def test_at_limit(self):
        from utils.mermaid import _truncate_properties
        result = _truncate_properties(["a", "b", "c", "d", "e"], max_display=5)
        assert result == "a, b, c, d, e"
        assert "..." not in result

    def test_over_limit(self):
        from utils.mermaid import _truncate_properties
        result = _truncate_properties(["a", "b", "c", "d", "e", "f"], max_display=5)
        assert result == "a, b, c, d, e, ..."

    def test_empty_list(self):
        from utils.mermaid import _truncate_properties
        assert _truncate_properties([]) == ""


# =============================================================================
# TestGenerateSchemaDiagram
# =============================================================================

class TestGenerateSchemaDiagram:
    """Tests for generate_schema_diagram."""

    def test_empty_state(self):
        from utils.mermaid import generate_schema_diagram
        assert generate_schema_diagram({}) == ""

    def test_domain_only(self):
        from utils.mermaid import generate_schema_diagram
        plan = _make_construction_plan(
            nodes=[{"label": "Product", "properties": ["name", "price"]}]
        )
        state = _make_state(approved_construction_plan=plan)
        result = generate_schema_diagram(state)

        assert "graph LR" in result
        assert "Product" in result
        assert "name, price" in result
        # No subgraph when text layer absent
        assert "subgraph" not in result

    def test_text_only(self):
        from utils.mermaid import generate_schema_diagram
        entities = _make_entity_types("QualityIssue", "Material")
        state = _make_state(approved_entity_types=entities)
        result = generate_schema_diagram(state)

        assert "graph LR" in result
        assert "QualityIssue" in result
        assert "Material" in result
        assert 'subgraph Text["Text Layer"]' in result

    def test_both_layers(self):
        from utils.mermaid import generate_schema_diagram
        plan = _make_construction_plan(
            nodes=[{"label": "Supplier", "properties": ["name"]}]
        )
        entities = _make_entity_types("Issue")
        state = _make_state(
            approved_construction_plan=plan,
            approved_entity_types=entities,
        )
        result = generate_schema_diagram(state)

        assert 'subgraph Domain["Domain Layer"]' in result
        assert 'subgraph Text["Text Layer"]' in result
        assert "Supplier" in result
        assert "Issue" in result

    def test_domain_relationships_solid_arrows(self):
        from utils.mermaid import generate_schema_diagram
        plan = _make_construction_plan(
            nodes=[
                {"label": "Supplier", "properties": ["name"]},
                {"label": "Product", "properties": ["sku"]},
            ],
            rels=[{"type": "SUPPLIES", "from": "Supplier", "to": "Product"}],
        )
        state = _make_state(approved_construction_plan=plan)
        result = generate_schema_diagram(state)

        assert "-->|SUPPLIES|" in result

    def test_text_relationships_dashed_arrows(self):
        from utils.mermaid import generate_schema_diagram
        entities = _make_entity_types("Issue", "Product")
        facts = _make_fact_types(("affects", "Issue", "Product"))
        state = _make_state(
            approved_entity_types=entities,
            approved_fact_types=facts,
        )
        result = generate_schema_diagram(state)

        assert "-.->|affects|" in result

    def test_properties_displayed(self):
        from utils.mermaid import generate_schema_diagram
        plan = _make_construction_plan(
            nodes=[{"label": "Widget", "properties": ["id", "name", "weight"]}]
        )
        state = _make_state(approved_construction_plan=plan)
        result = generate_schema_diagram(state)

        assert "id, name, weight" in result

    def test_shared_label_bridge(self):
        from utils.mermaid import generate_schema_diagram
        plan = _make_construction_plan(
            nodes=[{"label": "Product", "properties": ["sku"]}]
        )
        entities = _make_entity_types("Product", "Issue")
        state = _make_state(
            approved_construction_plan=plan,
            approved_entity_types=entities,
        )
        result = generate_schema_diagram(state)

        # Text subgraph should have Product_t
        assert "Product_t" in result
        # Bridge arrow
        assert "==>|CORRESPONDS_TO|" in result

    def test_self_referencing_relationship(self):
        from utils.mermaid import generate_schema_diagram
        plan = _make_construction_plan(
            nodes=[{"label": "Person", "properties": ["name"]}],
            rels=[{"type": "KNOWS", "from": "Person", "to": "Person"}],
        )
        state = _make_state(approved_construction_plan=plan)
        result = generate_schema_diagram(state)

        assert "Person -->|KNOWS| Person" in result

    def test_special_chars_in_labels(self):
        from utils.mermaid import generate_schema_diagram
        entities = _make_entity_types("Quality Issue", "3D-Model")
        state = _make_state(approved_entity_types=entities)
        result = generate_schema_diagram(state)

        # Should not crash and should contain sanitized IDs
        assert "graph LR" in result
        assert "Quality Issue" in result
        assert "3D-Model" in result


# =============================================================================
# TestGenerateLiveDiagram
# =============================================================================

class TestGenerateLiveDiagram:
    """Tests for generate_live_diagram with mocked Neo4j driver."""

    def test_empty_graph(self):
        from utils.mermaid import generate_live_diagram
        driver = _mock_neo4j_session(label_rows=[], rel_rows=[])
        result = generate_live_diagram(driver, {})
        assert result == ""

    def test_domain_nodes_with_counts(self):
        from utils.mermaid import generate_live_diagram
        driver = _mock_neo4j_session(
            label_rows=[
                {"label": "Product", "count": 42},
                {"label": "Supplier", "count": 10},
            ]
        )
        result = generate_live_diagram(driver, {})

        assert "graph LR" in result
        assert 'Product["Product (42)"]' in result
        assert 'Supplier["Supplier (10)"]' in result

    def test_mixed_layers(self):
        from utils.mermaid import generate_live_diagram
        driver = _mock_neo4j_session(
            label_rows=[
                {"label": "Product", "count": 42},
                {"label": "Chunk", "count": 100},
                {"label": "__Entity__", "count": 55},
            ]
        )
        result = generate_live_diagram(driver, {})

        assert 'subgraph Domain["Domain Layer"]' in result
        assert 'subgraph Text["Text Layer"]' in result
        assert "Product" in result
        assert "Chunk" in result

    def test_relationships_with_counts(self):
        from utils.mermaid import generate_live_diagram
        driver = _mock_neo4j_session(
            label_rows=[
                {"label": "Supplier", "count": 10},
                {"label": "Product", "count": 42},
            ],
            rel_rows=[
                {"from_label": "Supplier", "to_label": "Product",
                 "rel_type": "SUPPLIES", "count": 50},
            ],
        )
        result = generate_live_diagram(driver, {})

        assert '-- "SUPPLIES (50)" -->' in result

    def test_corresponds_to_thick_arrow(self):
        from utils.mermaid import generate_live_diagram
        driver = _mock_neo4j_session(
            label_rows=[
                {"label": "Product", "count": 42},
                {"label": "__Entity__", "count": 55},
            ],
            rel_rows=[
                {"from_label": "__Entity__", "to_label": "Product",
                 "rel_type": "CORRESPONDS_TO", "count": 30},
            ],
        )
        result = generate_live_diagram(driver, {})

        assert '== "CORRESPONDS_TO (30)" ==>' in result

    def test_truncation_over_50(self):
        from utils.mermaid import generate_live_diagram
        # Create 55 domain labels
        label_rows = [{"label": f"Type{i}", "count": 100 - i} for i in range(55)]
        driver = _mock_neo4j_session(label_rows=label_rows)
        result = generate_live_diagram(driver, {})

        assert "more node types omitted" in result


# =============================================================================
# TestRunKgDiagram
# =============================================================================

class TestRunKgDiagram:
    """Tests for _run_kg_diagram MCP implementation."""

    def test_invalid_scope(self):
        from mcp_server.server import _run_kg_diagram
        result = _run_kg_diagram("invalid")
        assert result["status"]["error"] == "invalid_scope"

    @patch("mcp_server.server._load_clean_state", return_value={})
    def test_schema_no_data(self, mock_load):
        from mcp_server.server import _run_kg_diagram
        result = _run_kg_diagram("schema")
        assert result["status"]["error"] == "no_data"
        assert "No diagram data available" in result["agent_response"]

    @patch("mcp_server.server._load_clean_state")
    def test_schema_with_data(self, mock_load):
        from mcp_server.server import _run_kg_diagram
        plan = _make_construction_plan(
            nodes=[{"label": "Product", "properties": ["name"]}]
        )
        mock_load.return_value = {"approved_construction_plan": plan}

        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__ = lambda s: MagicMock()
            mock_open.return_value.__exit__ = lambda s, *a: None
            with patch("os.makedirs"):
                result = _run_kg_diagram("schema")

        assert result["status"]["success"] is True
        assert result["status"]["scope"] == "schema"
        assert "mermaid" in result
        assert "graph LR" in result["mermaid"]

    @patch("mcp_server.server._load_clean_state", return_value={})
    @patch("mcp_server.server.get_neo4j_driver", side_effect=Exception("No Neo4j"))
    def test_live_neo4j_failure(self, mock_driver, mock_load):
        from mcp_server.server import _run_kg_diagram
        result = _run_kg_diagram("live")
        assert result["status"]["success"] is False
        assert "No Neo4j" in result["status"]["error"]

    @patch("mcp_server.server._load_clean_state", return_value={})
    @patch("mcp_server.server.close_driver")
    @patch("mcp_server.server.get_neo4j_driver")
    def test_live_with_data(self, mock_get_driver, mock_close, mock_load):
        from mcp_server.server import _run_kg_diagram
        mock_get_driver.return_value = _mock_neo4j_session(
            label_rows=[{"label": "Product", "count": 5}]
        )

        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__ = lambda s: MagicMock()
            mock_open.return_value.__exit__ = lambda s, *a: None
            with patch("os.makedirs"):
                result = _run_kg_diagram("live")

        assert result["status"]["success"] is True
        assert result["status"]["scope"] == "live"

    @patch("mcp_server.server._load_clean_state")
    @patch("mcp_server.server.get_neo4j_driver", side_effect=Exception("fail"))
    def test_auto_fallback_to_schema(self, mock_driver, mock_load):
        from mcp_server.server import _run_kg_diagram
        plan = _make_construction_plan(
            nodes=[{"label": "Product", "properties": ["name"]}]
        )
        mock_load.return_value = {"approved_construction_plan": plan}

        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__ = lambda s: MagicMock()
            mock_open.return_value.__exit__ = lambda s, *a: None
            with patch("os.makedirs"):
                result = _run_kg_diagram("auto")

        assert result["status"]["success"] is True
        assert result["status"]["scope"] == "schema"

    @patch("mcp_server.server._load_clean_state", return_value={})
    @patch("mcp_server.server.get_neo4j_driver", side_effect=Exception("fail"))
    def test_auto_no_data_at_all(self, mock_driver, mock_load):
        from mcp_server.server import _run_kg_diagram
        result = _run_kg_diagram("auto")
        assert result["status"]["error"] == "no_data"

    @patch("mcp_server.server._load_clean_state")
    def test_response_contains_mermaid_fence(self, mock_load):
        from mcp_server.server import _run_kg_diagram
        plan = _make_construction_plan(
            nodes=[{"label": "Item", "properties": ["id"]}]
        )
        mock_load.return_value = {"approved_construction_plan": plan}

        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__ = lambda s: MagicMock()
            mock_open.return_value.__exit__ = lambda s, *a: None
            with patch("os.makedirs"):
                result = _run_kg_diagram("schema")

        assert "```mermaid" in result["agent_response"]

    @patch("mcp_server.server._load_clean_state")
    def test_file_path_in_status(self, mock_load):
        from mcp_server.server import _run_kg_diagram
        plan = _make_construction_plan(
            nodes=[{"label": "Node", "properties": ["x"]}]
        )
        mock_load.return_value = {"approved_construction_plan": plan}

        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__ = lambda s: MagicMock()
            mock_open.return_value.__exit__ = lambda s, *a: None
            with patch("os.makedirs"):
                result = _run_kg_diagram("schema")

        assert "file" in result["status"]
        assert "diagram.mmd" in result["status"]["file"]

    @patch("mcp_server.server._load_clean_state")
    def test_file_written(self, mock_load):
        """Verify the diagram file is actually written with correct content."""
        from mcp_server.server import _run_kg_diagram
        plan = _make_construction_plan(
            nodes=[{"label": "Foo", "properties": ["bar"]}]
        )
        mock_load.return_value = {"approved_construction_plan": plan}

        written_content = []

        mock_file = MagicMock()
        mock_file.write = lambda s: written_content.append(s)

        with patch("builtins.open", return_value=MagicMock(
            __enter__=lambda s: mock_file,
            __exit__=lambda s, *a: None,
        )):
            with patch("os.makedirs"):
                result = _run_kg_diagram("schema")

        content = "".join(written_content)
        assert "graph LR" in content
        assert "```mermaid" not in content


# =============================================================================
# TestEdgeCases
# =============================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_no_relationships(self):
        from utils.mermaid import generate_schema_diagram
        plan = _make_construction_plan(
            nodes=[
                {"label": "A", "properties": ["x"]},
                {"label": "B", "properties": ["y"]},
            ]
        )
        state = _make_state(approved_construction_plan=plan)
        result = generate_schema_diagram(state)

        assert "graph LR" in result
        assert "-->" not in result

    def test_long_property_list(self):
        from utils.mermaid import generate_schema_diagram
        plan = _make_construction_plan(
            nodes=[{"label": "Big", "properties": [
                "p1", "p2", "p3", "p4", "p5", "p6", "p7",
            ]}]
        )
        state = _make_state(approved_construction_plan=plan)
        result = generate_schema_diagram(state)

        # unique_column_name "big_id" is prepended, so 8 total props => truncated
        assert "..." in result

    def test_unicode_labels(self):
        from utils.mermaid import generate_schema_diagram
        entities = _make_entity_types("Lieferant", "Produkt")
        state = _make_state(approved_entity_types=entities)
        result = generate_schema_diagram(state)

        assert "Lieferant" in result
        assert "Produkt" in result

    def test_proposed_only_state_not_shown(self):
        """Only approved artifacts should appear in diagrams."""
        from utils.mermaid import generate_schema_diagram
        state = _make_state(
            proposed_construction_plan=_make_construction_plan(
                nodes=[{"label": "Draft", "properties": ["x"]}]
            )
        )
        result = generate_schema_diagram(state)
        assert result == ""
