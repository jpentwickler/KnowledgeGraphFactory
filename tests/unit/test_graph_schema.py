"""
Unit tests for core/graph_schema.py

Tests:
- _detect_format (7 patterns)
- build_graph_schema (full, domain-only, text-only, empty)
- cypher_notation renderer
- compact_summary renderer
- markdown renderer
- for_repair renderer
- validate_cypher (property access, unknown rels, direction, cross-layer)
- overlapping labels computation
"""

import pytest
from unittest.mock import patch, MagicMock
from core.graph_schema import (
    PropertyInfo,
    NodeSchema,
    RelationshipSchema,
    GraphSchema,
    ValidationIssue,
    _detect_format,
    build_graph_schema,
)


# =============================================================================
# Fixture State (furniture supply chain)
# =============================================================================

FIXTURE_STATE = {
    "approved_construction_plan": {
        "Product": {
            "construction_type": "node",
            "source_file": "products.csv",
            "label": "Product",
            "unique_column_name": "product_id",
            "properties": ["product_id", "product_name", "price", "description"],
        },
        "Supplier": {
            "construction_type": "node",
            "source_file": "suppliers.csv",
            "label": "Supplier",
            "unique_column_name": "supplier_id",
            "properties": ["supplier_id", "name", "specialty"],
        },
        "Part": {
            "construction_type": "node",
            "source_file": "parts.csv",
            "label": "Part",
            "unique_column_name": "part_id",
            "properties": ["part_id", "part_name"],
        },
        "Assembly": {
            "construction_type": "node",
            "source_file": "assemblies.csv",
            "label": "Assembly",
            "unique_column_name": "assembly_id",
            "properties": ["assembly_id", "assembly_name"],
        },
        "HAS_ASSEMBLY": {
            "construction_type": "relationship",
            "source_file": "assemblies.csv",
            "relationship_type": "HAS_ASSEMBLY",
            "from_node_label": "Product",
            "to_node_label": "Assembly",
            "properties": ["quantity"],
        },
        "CONTAINS_PART": {
            "construction_type": "relationship",
            "source_file": "parts.csv",
            "relationship_type": "CONTAINS_PART",
            "from_node_label": "Assembly",
            "to_node_label": "Part",
            "properties": ["quantity"],
        },
        "SUPPLIES": {
            "construction_type": "relationship",
            "source_file": "part_supplier_mapping.csv",
            "relationship_type": "SUPPLIES",
            "from_node_label": "Supplier",
            "to_node_label": "Part",
            "properties": ["lead_time_days", "unit_cost"],
        },
    },
    "approved_entity_types": {
        "Product": {"source": "well_known", "description": "A furniture product"},
        "Part": {"source": "well_known", "description": "A component"},
        "Supplier": {"source": "well_known", "description": "A vendor"},
        "Review": {"source": "discovered", "description": "A customer review"},
        "Reviewer": {"source": "discovered", "description": "A review author"},
        "Defect": {"source": "discovered", "description": "A reported defect"},
    },
    "approved_fact_types": {
        "authored": {
            "subject_label": "Reviewer",
            "predicate_label": "authored",
            "object_label": "Review",
        },
        "evaluates": {
            "subject_label": "Review",
            "predicate_label": "evaluates",
            "object_label": "Product",
        },
        "mentions_defect_in": {
            "subject_label": "Review",
            "predicate_label": "mentions_defect_in",
            "object_label": "Part",
        },
    },
    "domain_node_schema": {
        "Product": {
            "properties": {
                "product_id": {"sample": "P-1008"},
                "product_name": {"sample": "Stockholm Chair"},
                "price": {"sample": "$212"},
                "description": {"sample": "Centerpiece for your living room"},
            }
        },
        "Supplier": {
            "properties": {
                "supplier_id": {"sample": "SUP-001"},
                "name": {"sample": "Nordic Wood Industries"},
                "specialty": {"sample": "Wood"},
            }
        },
    },
    "text_entity_schema": {
        "Review": {
            "properties": {
                "rating": {"sample": "5/5"},
                "content": {"sample": "I love this chair!"},
            }
        },
        "Reviewer": {
            "properties": {
                "name": {"sample": "@scandi_lover"},
            }
        },
    },
    "relationship_schema": {
        "SUPPLIES": {
            "properties": {
                "lead_time_days": {"sample": "14"},
                "unit_cost": {"sample": "$35.50"},
            }
        },
    },
}


# =============================================================================
# _detect_format tests
# =============================================================================

class TestDetectFormat:
    def test_none_returns_string(self):
        assert _detect_format(None) == ("string", None)

    def test_empty_returns_string(self):
        assert _detect_format("") == ("string", None)

    def test_currency(self):
        typ, hint = _detect_format("$212")
        assert typ == "float"
        assert "currency" in hint
        assert "strip" in hint

    def test_currency_with_decimals(self):
        typ, hint = _detect_format("$35.50")
        assert typ == "float"
        assert "currency" in hint

    def test_fraction(self):
        typ, hint = _detect_format("5/5")
        assert typ == "string"
        assert "fraction" in hint
        assert "split" in hint

    def test_boolean_true(self):
        assert _detect_format("true") == ("boolean", None)

    def test_boolean_false(self):
        assert _detect_format("False") == ("boolean", None)

    def test_boolean_like_yes(self):
        typ, hint = _detect_format("yes")
        assert typ == "boolean"
        assert hint is not None
        assert "boolean-like" in hint
        assert "string" in hint
        assert "'yes'" in hint

    def test_boolean_like_no(self):
        typ, hint = _detect_format("no")
        assert typ == "boolean"
        assert hint is not None
        assert "boolean-like" in hint
        assert "'no'" in hint

    def test_boolean_like_yes_case_insensitive(self):
        typ, hint = _detect_format("Yes")
        assert typ == "boolean"
        assert hint is not None
        assert "boolean-like" in hint

    def test_boolean_like_no_case_insensitive(self):
        typ, hint = _detect_format("NO")
        assert typ == "boolean"
        assert hint is not None

    def test_integer(self):
        assert _detect_format("14") == ("integer", None)

    def test_negative_integer(self):
        assert _detect_format("-5") == ("integer", None)

    def test_float(self):
        assert _detect_format("3.14") == ("float", None)

    def test_plain_string(self):
        assert _detect_format("Stockholm Chair") == ("string", None)

    def test_whitespace_stripped(self):
        assert _detect_format("  42  ") == ("integer", None)


# =============================================================================
# build_graph_schema tests
# =============================================================================

class TestBuildGraphSchema:
    def test_full_state(self):
        schema = build_graph_schema(FIXTURE_STATE)
        domain_nodes = [n for n in schema.nodes if n.layer == "domain"]
        text_nodes = [n for n in schema.nodes if n.layer == "text"]
        domain_rels = [r for r in schema.relationships if r.layer == "domain"]
        text_rels = [r for r in schema.relationships if r.layer == "text"]
        bridge_rels = [r for r in schema.relationships if r.layer == "bridge"]

        assert len(domain_nodes) == 4  # Product, Supplier, Part, Assembly
        assert len(text_nodes) == 6    # Product, Part, Supplier, Review, Reviewer, Defect
        assert len(domain_rels) == 3   # HAS_ASSEMBLY, CONTAINS_PART, SUPPLIES
        assert len(text_rels) == 3     # AUTHORED, EVALUATES, MENTIONS_DEFECT_IN
        assert len(bridge_rels) == 3   # Product, Part, Supplier (overlapping)

    def test_overlapping_labels(self):
        schema = build_graph_schema(FIXTURE_STATE)
        assert schema.overlapping_labels == {"Product", "Part", "Supplier"}

    def test_domain_only_state(self):
        state = {
            "approved_construction_plan": FIXTURE_STATE["approved_construction_plan"],
            "domain_node_schema": FIXTURE_STATE["domain_node_schema"],
        }
        schema = build_graph_schema(state)
        assert len([n for n in schema.nodes if n.layer == "domain"]) == 4
        assert len([n for n in schema.nodes if n.layer == "text"]) == 0
        assert schema.overlapping_labels == set()

    def test_text_only_state(self):
        state = {
            "approved_entity_types": FIXTURE_STATE["approved_entity_types"],
            "approved_fact_types": FIXTURE_STATE["approved_fact_types"],
            "text_entity_schema": FIXTURE_STATE["text_entity_schema"],
        }
        schema = build_graph_schema(state)
        assert len([n for n in schema.nodes if n.layer == "domain"]) == 0
        assert len([n for n in schema.nodes if n.layer == "text"]) == 6
        assert schema.overlapping_labels == set()

    def test_empty_state(self):
        schema = build_graph_schema({})
        assert len(schema.nodes) == 0
        assert len(schema.relationships) == 0
        assert schema.overlapping_labels == set()

    def test_domain_node_properties_include_samples(self):
        schema = build_graph_schema(FIXTURE_STATE)
        product = next(n for n in schema.nodes if n.label == "Product" and n.layer == "domain")
        price_prop = next(p for p in product.properties if p.name == "price")
        assert price_prop.sample == "$212"
        assert price_prop.inferred_type == "float"
        assert "currency" in price_prop.parse_hint

    def test_relationship_properties_include_samples(self):
        schema = build_graph_schema(FIXTURE_STATE)
        supplies = next(r for r in schema.relationships if r.type == "SUPPLIES")
        lead_time = next(p for p in supplies.properties if p.name == "lead_time_days")
        assert lead_time.sample == "14"
        assert lead_time.inferred_type == "integer"

        unit_cost = next(p for p in supplies.properties if p.name == "unit_cost")
        assert unit_cost.sample == "$35.50"
        assert unit_cost.inferred_type == "float"
        assert "currency" in unit_cost.parse_hint

    def test_text_entity_properties_include_samples(self):
        schema = build_graph_schema(FIXTURE_STATE)
        review = next(n for n in schema.nodes if n.label == "Review" and n.layer == "text")
        rating = next(p for p in review.properties if p.name == "rating")
        assert rating.sample == "5/5"
        assert "fraction" in rating.parse_hint

    def test_bridge_rels_are_corresponds_to(self):
        schema = build_graph_schema(FIXTURE_STATE)
        bridges = [r for r in schema.relationships if r.layer == "bridge"]
        for b in bridges:
            assert b.type == "CORRESPONDS_TO"
            assert b.from_label == b.to_label
            assert b.from_label in {"Product", "Part", "Supplier"}


# =============================================================================
# build_graph_schema introspection fallback tests
# =============================================================================

class TestBuildGraphSchemaIntrospection:
    """Tests for driver fallback introspection in build_graph_schema."""

    def test_calls_introspection_when_driver_and_empty_schemas(self):
        """When driver provided and schema keys empty, all 3 introspections fire."""
        state = {
            "approved_construction_plan": FIXTURE_STATE["approved_construction_plan"],
            "approved_entity_types": FIXTURE_STATE["approved_entity_types"],
            "approved_fact_types": FIXTURE_STATE["approved_fact_types"],
        }
        mock_driver = MagicMock()

        with patch("tools.query_tools._introspect_domain_schema") as mock_domain, \
             patch("tools.query_tools._introspect_text_schema") as mock_text, \
             patch("tools.query_tools._introspect_relationship_schema") as mock_rel:
            build_graph_schema(state, driver=mock_driver)
            mock_domain.assert_called_once_with(mock_driver, state)
            mock_text.assert_called_once_with(mock_driver, state)
            mock_rel.assert_called_once_with(mock_driver, state)

    def test_skips_introspection_when_schemas_fully_populated(self):
        """When schema keys already have data including overlapping labels, no introspection."""
        # Add overlapping labels to text_entity_schema so it's complete
        complete_state = dict(FIXTURE_STATE)
        complete_text_schema = dict(FIXTURE_STATE["text_entity_schema"])
        complete_text_schema["Part"] = {"properties": {"name": {"sample": "drawer rails"}}}
        complete_text_schema["Product"] = {"properties": {"name": {"sample": "Stockholm Chair"}}}
        complete_text_schema["Supplier"] = {"properties": {"name": {"sample": "Nordic Wood"}}}
        complete_state["text_entity_schema"] = complete_text_schema
        mock_driver = MagicMock()

        with patch("tools.query_tools._introspect_domain_schema") as mock_domain, \
             patch("tools.query_tools._introspect_text_schema") as mock_text, \
             patch("tools.query_tools._introspect_relationship_schema") as mock_rel:
            build_graph_schema(complete_state, driver=mock_driver)
            mock_domain.assert_not_called()
            mock_text.assert_not_called()
            mock_rel.assert_not_called()

    def test_skips_introspection_when_no_driver(self):
        """When no driver provided, introspection is NOT called even if schemas empty."""
        state = {
            "approved_construction_plan": FIXTURE_STATE["approved_construction_plan"],
        }

        with patch("tools.query_tools._introspect_domain_schema") as mock_domain, \
             patch("tools.query_tools._introspect_text_schema") as mock_text, \
             patch("tools.query_tools._introspect_relationship_schema") as mock_rel:
            build_graph_schema(state)
            mock_domain.assert_not_called()
            mock_text.assert_not_called()
            mock_rel.assert_not_called()

    def test_graceful_degradation_on_introspection_failure(self):
        """If introspection raises, logs warning and returns schema without samples."""
        state = {
            "approved_construction_plan": FIXTURE_STATE["approved_construction_plan"],
            "approved_entity_types": FIXTURE_STATE["approved_entity_types"],
            "approved_fact_types": FIXTURE_STATE["approved_fact_types"],
        }
        mock_driver = MagicMock()

        with patch("tools.query_tools._introspect_domain_schema",
                    side_effect=RuntimeError("connection failed")):
            schema = build_graph_schema(state, driver=mock_driver)
            # Still produces nodes from the plan (just without property samples)
            domain_nodes = [n for n in schema.nodes if n.layer == "domain"]
            assert len(domain_nodes) == 4

    def test_partial_introspection_only_relationship(self):
        """If only relationship_schema is empty, relationship + text introspection fires.

        Text introspection also fires because the text_entity_schema is
        missing overlapping labels (Part, Product, Supplier).
        """
        state = {
            "approved_construction_plan": FIXTURE_STATE["approved_construction_plan"],
            "approved_entity_types": FIXTURE_STATE["approved_entity_types"],
            "approved_fact_types": FIXTURE_STATE["approved_fact_types"],
            "domain_node_schema": FIXTURE_STATE["domain_node_schema"],
            "text_entity_schema": FIXTURE_STATE["text_entity_schema"],
            # relationship_schema deliberately omitted
        }
        mock_driver = MagicMock()

        with patch("tools.query_tools._introspect_domain_schema") as mock_domain, \
             patch("tools.query_tools._introspect_text_schema") as mock_text, \
             patch("tools.query_tools._introspect_relationship_schema") as mock_rel:
            build_graph_schema(state, driver=mock_driver)
            mock_domain.assert_not_called()
            # Text re-introspection fires due to missing overlapping labels
            mock_text.assert_called_once_with(mock_driver, state)
            mock_rel.assert_called_once_with(mock_driver, state)

    def test_re_introspects_text_when_overlapping_labels_missing(self):
        """When text_entity_schema exists but is missing overlapping labels, re-introspect."""
        state = {
            "approved_construction_plan": FIXTURE_STATE["approved_construction_plan"],
            "approved_entity_types": FIXTURE_STATE["approved_entity_types"],
            "approved_fact_types": FIXTURE_STATE["approved_fact_types"],
            "domain_node_schema": FIXTURE_STATE["domain_node_schema"],
            # text_entity_schema has Review/Reviewer but NOT Part/Product/Supplier
            "text_entity_schema": FIXTURE_STATE["text_entity_schema"],
            "relationship_schema": FIXTURE_STATE["relationship_schema"],
        }
        mock_driver = MagicMock()

        with patch("tools.query_tools._introspect_domain_schema") as mock_domain, \
             patch("tools.query_tools._introspect_text_schema") as mock_text, \
             patch("tools.query_tools._introspect_relationship_schema") as mock_rel:
            build_graph_schema(state, driver=mock_driver)
            mock_domain.assert_not_called()
            # Key assertion: text introspection IS called because
            # Part, Product, Supplier are overlapping but missing
            mock_text.assert_called_once_with(mock_driver, state)
            mock_rel.assert_not_called()

    def test_skips_text_re_introspection_when_overlapping_labels_present(self):
        """When text_entity_schema already has all overlapping labels, skip introspection."""
        # Add overlapping labels to text_entity_schema
        complete_text_schema = dict(FIXTURE_STATE["text_entity_schema"])
        complete_text_schema["Part"] = {"properties": {"name": {"sample": "drawer rails"}}}
        complete_text_schema["Product"] = {"properties": {"name": {"sample": "Stockholm Chair"}}}
        complete_text_schema["Supplier"] = {"properties": {"name": {"sample": "Nordic Wood"}}}
        state = {
            "approved_construction_plan": FIXTURE_STATE["approved_construction_plan"],
            "approved_entity_types": FIXTURE_STATE["approved_entity_types"],
            "approved_fact_types": FIXTURE_STATE["approved_fact_types"],
            "domain_node_schema": FIXTURE_STATE["domain_node_schema"],
            "text_entity_schema": complete_text_schema,
            "relationship_schema": FIXTURE_STATE["relationship_schema"],
        }
        mock_driver = MagicMock()

        with patch("tools.query_tools._introspect_domain_schema") as mock_domain, \
             patch("tools.query_tools._introspect_text_schema") as mock_text, \
             patch("tools.query_tools._introspect_relationship_schema") as mock_rel:
            build_graph_schema(state, driver=mock_driver)
            mock_domain.assert_not_called()
            mock_text.assert_not_called()
            mock_rel.assert_not_called()

    def test_text_node_properties_populated_after_re_introspection(self):
        """After re-introspection, overlapping text nodes have correct properties."""
        def fake_introspect(driver, state):
            state["text_entity_schema"] = {
                "Review": {"properties": {"rating": {"sample": "5/5"}}},
                "Reviewer": {"properties": {"name": {"sample": "@user"}}},
                "Part": {"properties": {"name": {"sample": "drawer rails"}}},
                "Product": {"properties": {"name": {"sample": "Stockholm Chair"}}},
                "Supplier": {"properties": {"name": {"sample": "Nordic Wood"}}},
                "Defect": {"properties": {"description": {"sample": "rough edges"}}},
            }
            return state["text_entity_schema"]

        state = {
            "approved_construction_plan": FIXTURE_STATE["approved_construction_plan"],
            "approved_entity_types": FIXTURE_STATE["approved_entity_types"],
            "approved_fact_types": FIXTURE_STATE["approved_fact_types"],
            "domain_node_schema": FIXTURE_STATE["domain_node_schema"],
            "text_entity_schema": FIXTURE_STATE["text_entity_schema"],  # incomplete
            "relationship_schema": FIXTURE_STATE["relationship_schema"],
        }
        mock_driver = MagicMock()

        with patch("tools.query_tools._introspect_text_schema", side_effect=fake_introspect), \
             patch("tools.query_tools._introspect_domain_schema"), \
             patch("tools.query_tools._introspect_relationship_schema"):
            schema = build_graph_schema(state, driver=mock_driver)
            # Text Part should now have 'name' property from introspection
            text_part = next(
                n for n in schema.nodes if n.label == "Part" and n.layer == "text"
            )
            prop_names = [p.name for p in text_part.properties]
            assert "name" in prop_names, f"Expected 'name' in text Part properties, got {prop_names}"


# =============================================================================
# Accessor property tests
# =============================================================================

class TestAccessorProperties:
    """Tests for GraphSchema accessor properties used to replace _get_* calls."""

    def test_domain_labels(self):
        schema = build_graph_schema(FIXTURE_STATE)
        labels = schema.domain_labels
        assert "Product" in labels
        assert "Supplier" in labels
        assert "Part" in labels
        # Text entities should NOT appear
        assert "Review" not in labels

    def test_text_labels(self):
        schema = build_graph_schema(FIXTURE_STATE)
        labels = schema.text_labels
        assert "Review" in labels
        assert "Reviewer" in labels
        # Domain nodes should NOT appear (even if overlapping, layer is "domain")
        # Product/Part/Supplier appear in both layers; domain copies have layer="domain"
        # text copies have layer="text"
        for lbl in labels:
            node = next(n for n in schema.nodes if n.label == lbl and n.layer == "text")
            assert node.layer == "text"

    def test_domain_node_properties(self):
        schema = build_graph_schema(FIXTURE_STATE)
        props = schema.domain_node_properties
        assert "Product" in props
        assert "product_id" in props["Product"]
        assert "price" in props["Product"]
        assert "Supplier" in props
        assert "supplier_id" in props["Supplier"]
        # Text entities should NOT appear
        assert "Review" not in props

    def test_domain_node_properties_empty_state(self):
        schema = build_graph_schema({})
        assert schema.domain_node_properties == {}

    def test_rel_endpoint_map(self):
        schema = build_graph_schema(FIXTURE_STATE)
        rem = schema.rel_endpoint_map
        assert "SUPPLIES" in rem
        assert rem["SUPPLIES"]["from"] == "Supplier"
        assert rem["SUPPLIES"]["to"] == "Part"
        # Bridge rels should NOT appear
        assert "CORRESPONDS_TO" not in rem

    def test_rel_endpoint_map_includes_text_rels(self):
        schema = build_graph_schema(FIXTURE_STATE)
        rem = schema.rel_endpoint_map
        assert "EVALUATES" in rem
        assert rem["EVALUATES"]["from"] == "Review"
        assert rem["EVALUATES"]["to"] == "Product"

    def test_domain_labels_empty_state(self):
        schema = build_graph_schema({})
        assert schema.domain_labels == []

    def test_text_labels_empty_state(self):
        schema = build_graph_schema({})
        assert schema.text_labels == []


# =============================================================================
# cypher_notation tests
# =============================================================================

class TestCypherNotation:
    def test_text_nodes_have_entity_label(self):
        schema = build_graph_schema(FIXTURE_STATE)
        output = schema.cypher_notation()
        assert ":__Entity__" in output

    def test_lead_time_on_supplies_not_supplier(self):
        """Key invariant: lead_time_days inside [:SUPPLIES], not (:Supplier)."""
        schema = build_graph_schema(FIXTURE_STATE)
        output = schema.cypher_notation()
        # lead_time_days should appear in SUPPLIES context
        assert "SUPPLIES" in output
        lines = output.split("\n")
        for line in lines:
            if "lead_time_days" in line:
                assert "SUPPLIES" in line, f"lead_time_days should be on SUPPLIES, found in: {line}"
                assert "Supplier" not in line or "->(:Part)" in line, \
                    f"lead_time_days should not be on Supplier node: {line}"

    def test_corresponds_to_bridges(self):
        schema = build_graph_schema(FIXTURE_STATE)
        output = schema.cypher_notation()
        assert "CORRESPONDS_TO" in output
        assert "CROSS-LAYER BRIDGES" in output

    def test_data_format_notes(self):
        schema = build_graph_schema(FIXTURE_STATE)
        output = schema.cypher_notation()
        assert "DATA FORMAT NOTES" in output
        assert "currency" in output

    def test_domain_only_no_text_section(self):
        state = {
            "approved_construction_plan": FIXTURE_STATE["approved_construction_plan"],
        }
        schema = build_graph_schema(state)
        output = schema.cypher_notation()
        assert "DOMAIN LAYER" in output
        assert "TEXT LAYER" not in output
        assert "CROSS-LAYER BRIDGES" not in output


# =============================================================================
# compact_summary tests
# =============================================================================

class TestCompactSummary:
    def test_all_labels_listed(self):
        schema = build_graph_schema(FIXTURE_STATE)
        output = schema.compact_summary()
        assert "Product" in output
        assert "Supplier" in output
        assert "Review" in output
        assert "Reviewer" in output

    def test_no_property_names(self):
        """compact_summary should NOT include property names or sample values."""
        schema = build_graph_schema(FIXTURE_STATE)
        output = schema.compact_summary()
        assert "lead_time_days" not in output
        assert "P-1008" not in output
        assert "$212" not in output

    def test_no_sample_values(self):
        schema = build_graph_schema(FIXTURE_STATE)
        output = schema.compact_summary()
        assert "Stockholm Chair" not in output

    def test_cross_layer_bridges_listed(self):
        schema = build_graph_schema(FIXTURE_STATE)
        output = schema.compact_summary()
        assert "CORRESPONDS_TO" in output
        assert "Product" in output
        assert "Part" in output

    def test_domain_only(self):
        state = {
            "approved_construction_plan": FIXTURE_STATE["approved_construction_plan"],
        }
        schema = build_graph_schema(state)
        output = schema.compact_summary()
        assert "Domain layer:" in output
        assert "Text layer:" not in output
        assert "CORRESPONDS_TO" not in output

    def test_queryable_features(self):
        schema = build_graph_schema(FIXTURE_STATE)
        output = schema.compact_summary()
        assert "structured properties" in output
        assert "text embeddings" in output


# =============================================================================
# markdown tests
# =============================================================================

class TestMarkdown:
    def test_has_heading(self):
        schema = build_graph_schema(FIXTURE_STATE)
        output = schema.markdown()
        assert "# Knowledge Graph Schema" in output

    def test_with_counts(self):
        schema = build_graph_schema(FIXTURE_STATE)
        counts = {"Product": 10, "Supplier": 5}
        output = schema.markdown(node_counts=counts)
        assert "10 nodes" in output
        assert "5 nodes" in output

    def test_without_counts(self):
        schema = build_graph_schema(FIXTURE_STATE)
        output = schema.markdown()
        assert "nodes" not in output or "Domain Layer" in output

    def test_relationships_section(self):
        schema = build_graph_schema(FIXTURE_STATE)
        output = schema.markdown()
        assert "## Relationships" in output
        assert "SUPPLIES" in output


# =============================================================================
# for_repair tests
# =============================================================================

class TestForRepair:
    def test_includes_relationship_properties(self):
        schema = build_graph_schema(FIXTURE_STATE)
        violation = {
            "domain_rels_used": {"SUPPLIES"},
            "text_rels_used": {"EVALUATES"},
            "overlapping_labels": {"Product"},
        }
        output = schema.for_repair(violation)
        assert "lead_time_days" in output
        assert "unit_cost" in output

    def test_includes_parse_hints(self):
        schema = build_graph_schema(FIXTURE_STATE)
        violation = {
            "domain_rels_used": {"SUPPLIES"},
            "text_rels_used": {"EVALUATES"},
            "overlapping_labels": {"Product"},
        }
        output = schema.for_repair(violation)
        assert "currency" in output

    def test_includes_bridge_pattern(self):
        schema = build_graph_schema(FIXTURE_STATE)
        violation = {
            "domain_rels_used": {"SUPPLIES"},
            "text_rels_used": set(),
            "overlapping_labels": set(),
        }
        output = schema.for_repair(violation)
        assert "CORRESPONDS_TO" in output
        assert "BRIDGE PATTERN" in output

    def test_filters_to_relevant_rels(self):
        schema = build_graph_schema(FIXTURE_STATE)
        violation = {
            "domain_rels_used": {"SUPPLIES"},
            "text_rels_used": set(),
            "overlapping_labels": set(),
        }
        output = schema.for_repair(violation)
        assert "SUPPLIES" in output
        # HAS_ASSEMBLY should NOT be in the filtered output
        assert "HAS_ASSEMBLY" not in output


# =============================================================================
# validate_cypher tests
# =============================================================================

class TestValidateCypher:
    def _schema(self):
        return build_graph_schema(FIXTURE_STATE)

    def test_valid_cypher_passes(self):
        schema = self._schema()
        cypher = "MATCH (s:Supplier)-[r:SUPPLIES]->(p:Part) RETURN s.name, r.lead_time_days"
        issues = schema.validate_cypher(cypher)
        assert issues == []

    def test_property_on_wrong_node(self):
        """lead_time_days on Supplier node flagged — it's on SUPPLIES relationship."""
        schema = self._schema()
        cypher = "MATCH (s:Supplier) RETURN s.lead_time_days"
        issues = schema.validate_cypher(cypher)
        prop_issues = [i for i in issues if i.issue_type == "property_access"]
        assert len(prop_issues) >= 1
        assert "SUPPLIES" in prop_issues[0].suggestion

    def test_unknown_relationship_flagged(self):
        schema = self._schema()
        cypher = "MATCH (r:Review)-[:MENTIONED_IN]->(p:Part) RETURN r"
        issues = schema.validate_cypher(cypher)
        rel_issues = [i for i in issues if i.issue_type == "relationship_unknown"]
        assert len(rel_issues) == 1
        assert "MENTIONED_IN" in rel_issues[0].message

    def test_unknown_relationship_suggests_closest(self):
        schema = self._schema()
        cypher = "MATCH (r:Review)-[:MENTIONED_IN]->(p:Part) RETURN r"
        issues = schema.validate_cypher(cypher)
        rel_issues = [i for i in issues if i.issue_type == "relationship_unknown"]
        assert rel_issues[0].suggestion is not None
        assert "MENTIONS_DEFECT_IN" in rel_issues[0].suggestion

    def test_reversed_direction(self):
        schema = self._schema()
        cypher = "MATCH (p:Part)-[r:SUPPLIES]->(s:Supplier) RETURN p, s"
        issues = schema.validate_cypher(cypher)
        dir_issues = [i for i in issues if i.issue_type == "direction"]
        assert len(dir_issues) == 1
        assert "Reversed" in dir_issues[0].message
        assert "Supplier" in dir_issues[0].suggestion
        assert "Part" in dir_issues[0].suggestion

    def test_cross_layer_without_bridge(self):
        schema = self._schema()
        cypher = (
            "MATCH (s:Supplier)-[:SUPPLIES]->(p:Part) "
            "MATCH (r:Review)-[:EVALUATES]->(prod:Product) "
            "RETURN s, r"
        )
        issues = schema.validate_cypher(cypher)
        cl_issues = [i for i in issues if i.issue_type == "cross_layer"]
        assert len(cl_issues) == 1
        assert "CORRESPONDS_TO" in cl_issues[0].suggestion

    def test_cross_layer_with_bridge_passes(self):
        schema = self._schema()
        cypher = (
            "MATCH (s:Supplier)-[:SUPPLIES]->(p:Part) "
            "MATCH (te:__Entity__:Part)-[:CORRESPONDS_TO]->(p) "
            "MATCH (r:Review)-[:MENTIONS_DEFECT_IN]->(te) "
            "RETURN s, r"
        )
        issues = schema.validate_cypher(cypher)
        cl_issues = [i for i in issues if i.issue_type == "cross_layer"]
        assert len(cl_issues) == 0

    def test_single_layer_query_no_cross_layer_issue(self):
        schema = self._schema()
        cypher = "MATCH (s:Supplier)-[r:SUPPLIES]->(p:Part) RETURN s.name, r.unit_cost"
        issues = schema.validate_cypher(cypher)
        cl_issues = [i for i in issues if i.issue_type == "cross_layer"]
        assert len(cl_issues) == 0
