"""
Unit tests for tools/query_tools.py

Tests:
- State extraction (10 tests)
- Cypher safety validation (5 tests)
- Formatting and confidence calculation (8 tests)
"""

import pytest
from unittest.mock import MagicMock
from tools.query_tools import (
    _get_domain_labels,
    _get_domain_node_properties,
    _get_domain_relationships,
    _get_text_entities,
    _get_text_relationships,
    _introspect_domain_schema,
    _introspect_text_schema,
    _introspect_relationship_schema,
    format_cypher_results,
    format_retriever_results,
    calculate_confidence,
    _validate_read_only_cypher,
    _escape_lucene,
)


# =============================================================================
# State Extraction Tests (10 tests)
# =============================================================================

def test_get_domain_labels_with_valid_plan():
    """Test extracting domain labels from valid construction plan."""
    state = {
        "approved_construction_plan": {
            "Supplier": {
                "construction_type": "node",
                "label": "Supplier",
                "source_file": "suppliers.csv"
            },
            "Product": {
                "construction_type": "node",
                "label": "Product",
                "source_file": "products.csv"
            },
            "SUPPLIES": {
                "construction_type": "relationship",
                "label": "SUPPLIES",
                "source_file": "supplies.csv"
            }
        }
    }

    labels = _get_domain_labels(state)
    assert len(labels) == 2
    assert "Supplier" in labels
    assert "Product" in labels
    assert "SUPPLIES" not in labels  # Should filter out relationships


def test_get_domain_labels_empty_plan():
    """Test extracting labels from empty construction plan."""
    state = {"approved_construction_plan": {}}
    labels = _get_domain_labels(state)
    assert labels == []


def test_get_domain_labels_missing_approved():
    """Test extracting labels when construction plan not approved."""
    state = {"proposed_construction_plan": {"Foo": {"construction_type": "node", "label": "Foo"}}}
    labels = _get_domain_labels(state)
    assert labels == []


def test_get_domain_labels_filters_relationships():
    """Test that only nodes are returned, not relationships."""
    state = {
        "approved_construction_plan": {
            "Node1": {"construction_type": "node", "label": "Node1"},
            "REL1": {"construction_type": "relationship", "label": "REL1"},
            "Node2": {"construction_type": "node", "label": "Node2"},
        }
    }
    labels = _get_domain_labels(state)
    assert len(labels) == 2
    assert "REL1" not in labels


# =============================================================================
# Domain Node Properties Tests (4 tests)
# =============================================================================

def test_get_domain_node_properties_with_valid_plan():
    """Test extracting node properties from valid construction plan."""
    state = {
        "approved_construction_plan": {
            "Product": {
                "construction_type": "node",
                "label": "Product",
                "unique_column_name": "product_id",
                "properties": ["product_name", "price", "description"],
                "source_file": "products.csv"
            },
            "Supplier": {
                "construction_type": "node",
                "label": "Supplier",
                "unique_column_name": "supplier_id",
                "properties": ["name", "city", "country"],
                "source_file": "suppliers.csv"
            },
            "SUPPLIES": {
                "construction_type": "relationship",
                "relationship_type": "SUPPLIES",
                "from_node_label": "Supplier",
                "to_node_label": "Product",
                "properties": ["lead_time_days"],
                "source_file": "supplies.csv"
            }
        }
    }

    result = _get_domain_node_properties(state)
    assert len(result) == 2
    assert "Product" in result
    assert "Supplier" in result
    assert "SUPPLIES" not in result  # Relationships excluded
    assert "product_id" in result["Product"]
    assert "product_name" in result["Product"]
    assert "price" in result["Product"]
    assert "supplier_id" in result["Supplier"]
    assert "name" in result["Supplier"]


def test_get_domain_node_properties_without_properties_key():
    """Test node entry without properties key returns empty list."""
    state = {
        "approved_construction_plan": {
            "Product": {
                "construction_type": "node",
                "label": "Product",
                "source_file": "products.csv"
            }
        }
    }

    result = _get_domain_node_properties(state)
    assert "Product" in result
    assert result["Product"] == []


def test_get_domain_node_properties_empty_or_missing_plan():
    """Test empty/missing plan returns empty dict."""
    assert _get_domain_node_properties({"approved_construction_plan": {}}) == {}
    assert _get_domain_node_properties({}) == {}
    assert _get_domain_node_properties({"proposed_construction_plan": {"X": {}}}) == {}


def test_get_domain_node_properties_includes_unique_column():
    """Test that unique_column_name is included and placed first."""
    state = {
        "approved_construction_plan": {
            "Product": {
                "construction_type": "node",
                "label": "Product",
                "unique_column_name": "product_id",
                "properties": ["product_name", "price"],
                "source_file": "products.csv"
            }
        }
    }

    result = _get_domain_node_properties(state)
    props = result["Product"]
    assert props[0] == "product_id"  # unique_column_name inserted first
    assert "product_name" in props
    assert "price" in props
    assert len(props) == 3


def test_get_domain_node_properties_unique_column_already_in_properties():
    """Test no duplicates when unique_column_name is already in properties."""
    state = {
        "approved_construction_plan": {
            "Product": {
                "construction_type": "node",
                "label": "Product",
                "unique_column_name": "product_id",
                "properties": ["product_id", "product_name", "price"],
                "source_file": "products.csv"
            }
        }
    }

    result = _get_domain_node_properties(state)
    props = result["Product"]
    assert props.count("product_id") == 1  # No duplicates
    assert len(props) == 3


def test_get_text_entities_with_valid_types():
    """Test extracting entity names from valid entity_types."""
    state = {
        "approved_entity_types": {
            "Person": {
                "source": "documents.md",
                "description": "People mentioned in text",
                "grounding_evidence": []
            },
            "Organization": {
                "source": "documents.md",
                "description": "Organizations mentioned",
                "grounding_evidence": []
            }
        }
    }

    entities = _get_text_entities(state)
    assert len(entities) == 2
    assert "Person" in entities
    assert "Organization" in entities


def test_get_text_entities_empty_types():
    """Test extracting entities from empty entity_types."""
    state = {"approved_entity_types": {}}
    entities = _get_text_entities(state)
    assert entities == []


def test_get_text_entities_missing_approved():
    """Test extracting entities when entity_types not approved."""
    state = {"proposed_entity_types": {"Foo": {"source": "test.md"}}}
    entities = _get_text_entities(state)
    assert entities == []


def test_get_text_entities_uses_keys_not_list():
    """Test that entity names are extracted from dict keys, not a list."""
    state = {
        "approved_entity_types": {
            "EntityA": {"description": "First entity"},
            "EntityB": {"description": "Second entity"},
            "EntityC": {"description": "Third entity"},
        }
    }

    entities = _get_text_entities(state)
    assert len(entities) == 3
    assert set(entities) == {"EntityA", "EntityB", "EntityC"}


def test_construction_plan_structure_values_not_entries():
    """Verify construction plan uses dict.values(), not dict['entries']."""
    # This test ensures we use the correct structure from US008
    state = {
        "approved_construction_plan": {
            "Label1": {"construction_type": "node", "label": "Label1"},
            "Label2": {"construction_type": "node", "label": "Label2"},
        }
    }

    # Should work with values()
    labels = _get_domain_labels(state)
    assert len(labels) == 2

    # Should NOT work with entries (would return empty)
    bad_state = {
        "approved_construction_plan": {
            "entries": [
                {"construction_type": "node", "label": "Label1"},
                {"construction_type": "node", "label": "Label2"},
            ]
        }
    }
    labels = _get_domain_labels(bad_state)
    assert labels == []  # Confirms we're NOT using this structure


def test_entity_types_structure_dict_not_list():
    """Verify entity_types uses dict keys, not a list of entries."""
    # This test ensures we use the correct structure from US006
    state = {
        "approved_entity_types": {
            "Type1": {"description": "First"},
            "Type2": {"description": "Second"},
        }
    }

    # Should work with keys()
    entities = _get_text_entities(state)
    assert len(entities) == 2

    # Should NOT work with list structure (would return empty)
    bad_state = {
        "approved_entity_types": {
            "entity_types": [
                {"name": "Type1", "description": "First"},
                {"name": "Type2", "description": "Second"},
            ]
        }
    }
    entities = _get_text_entities(bad_state)
    assert entities == []  # Confirms we're NOT using this structure


# =============================================================================
# Domain Relationship Extraction Tests (4 tests)
# =============================================================================

def test_get_domain_relationships_with_valid_plan():
    """Test extracting relationships from valid construction plan."""
    state = {
        "approved_construction_plan": {
            "Product": {
                "construction_type": "node",
                "label": "Product",
                "source_file": "products.csv"
            },
            "HAS_PART": {
                "construction_type": "relationship",
                "relationship_type": "HAS_PART",
                "from_node_label": "Assembly",
                "to_node_label": "Part",
                "properties": ["quantity"],
                "source_file": "bom.csv"
            },
            "SUPPLIES_PART": {
                "construction_type": "relationship",
                "relationship_type": "SUPPLIES_PART",
                "from_node_label": "Supplier",
                "to_node_label": "Part",
                "properties": ["lead_time_days", "unit_cost"],
                "source_file": "part_supplier_mapping.csv"
            }
        }
    }

    rels = _get_domain_relationships(state)
    assert len(rels) == 2
    types = [r["type"] for r in rels]
    assert "HAS_PART" in types
    assert "SUPPLIES_PART" in types
    # Nodes should not appear
    assert "Product" not in types


def test_get_domain_relationships_empty_plan():
    """Test extracting relationships from empty construction plan."""
    state = {"approved_construction_plan": {}}
    rels = _get_domain_relationships(state)
    assert rels == []


def test_get_domain_relationships_missing_approved():
    """Test extracting relationships when construction plan not approved."""
    state = {"proposed_construction_plan": {"REL": {"construction_type": "relationship"}}}
    rels = _get_domain_relationships(state)
    assert rels == []


def test_get_domain_relationships_includes_properties():
    """Test that properties list is included in extracted relationships."""
    state = {
        "approved_construction_plan": {
            "SUPPLIES_PART": {
                "construction_type": "relationship",
                "relationship_type": "SUPPLIES_PART",
                "from_node_label": "Supplier",
                "to_node_label": "Part",
                "properties": ["lead_time_days", "unit_cost", "minimum_order_quantity"],
                "source_file": "mapping.csv"
            }
        }
    }

    rels = _get_domain_relationships(state)
    assert len(rels) == 1
    assert rels[0]["type"] == "SUPPLIES_PART"
    assert rels[0]["from"] == "Supplier"
    assert rels[0]["to"] == "Part"
    assert "lead_time_days" in rels[0]["properties"]
    assert "unit_cost" in rels[0]["properties"]
    assert len(rels[0]["properties"]) == 3


# =============================================================================
# Text Relationship Extraction Tests (4 tests)
# =============================================================================

def test_get_text_relationships_with_valid_types():
    """Test extracting fact types from valid approved_fact_types."""
    state = {
        "approved_fact_types": {
            "has_issue": {
                "subject_label": "Product",
                "predicate_label": "has_issue",
                "object_label": "QualityIssue"
            },
            "reviewed": {
                "subject_label": "Customer",
                "predicate_label": "reviewed",
                "object_label": "Product"
            }
        }
    }

    rels = _get_text_relationships(state)
    assert len(rels) == 2
    types = [r["type"] for r in rels]
    assert "HAS_ISSUE" in types
    assert "REVIEWED" in types


def test_get_text_relationships_empty():
    """Test extracting fact types from empty approved_fact_types."""
    state = {"approved_fact_types": {}}
    rels = _get_text_relationships(state)
    assert rels == []


def test_get_text_relationships_missing_approved():
    """Test extracting fact types when fact_types not approved."""
    state = {"proposed_fact_types": {"has_issue": {"subject_label": "Product"}}}
    rels = _get_text_relationships(state)
    assert rels == []


def test_get_text_relationships_structure():
    """Test that from/to/type fields are correctly mapped."""
    state = {
        "approved_fact_types": {
            "reported": {
                "subject_label": "Customer",
                "predicate_label": "reported",
                "object_label": "QualityIssue"
            }
        }
    }

    rels = _get_text_relationships(state)
    assert len(rels) == 1
    assert rels[0]["type"] == "REPORTED"
    assert rels[0]["from"] == "Customer"
    assert rels[0]["to"] == "QualityIssue"


# =============================================================================
# Cypher Safety Validation Tests (5 tests)
# =============================================================================

def test_validate_safe_cypher_match_return():
    """Test that valid MATCH...RETURN queries pass validation."""
    valid_queries = [
        "MATCH (n) RETURN n LIMIT 10",
        "MATCH (s:Supplier) RETURN s.name, s.location",
        "MATCH (a)-[r]->(b) RETURN type(r), count(*)",
        "RETURN 1 AS number",  # Pure RETURN is also valid
    ]

    for query in valid_queries:
        # Should not raise
        _validate_read_only_cypher(query)


def test_validate_blocks_create():
    """Test that CREATE operations are blocked."""
    with pytest.raises(ValueError) as exc_info:
        _validate_read_only_cypher("CREATE (n:Node {name: 'test'})")

    assert "CREATE" in str(exc_info.value)
    assert "Mutation operations not allowed" in str(exc_info.value)


def test_validate_blocks_delete_detach():
    """Test that DELETE and DETACH DELETE are blocked."""
    queries = [
        "MATCH (n) DELETE n",
        "MATCH (n) DETACH DELETE n",
    ]

    for query in queries:
        with pytest.raises(ValueError) as exc_info:
            _validate_read_only_cypher(query)
        assert "DELETE" in str(exc_info.value)


def test_validate_blocks_set_remove_merge():
    """Test that SET, REMOVE, and MERGE are blocked."""
    queries = [
        "MATCH (n) SET n.property = 'value'",
        "MATCH (n) REMOVE n.property",
        "MERGE (n:Node {id: 1})",
    ]

    for query in queries:
        with pytest.raises(ValueError) as exc_info:
            _validate_read_only_cypher(query)
        assert "Mutation operations not allowed" in str(exc_info.value)


def test_validate_requires_match_or_return():
    """Test that queries must contain MATCH or RETURN."""
    invalid_queries = [
        "CALL db.labels()",  # Valid Cypher but doesn't have MATCH/RETURN
        "SHOW INDEXES",  # Admin command
    ]

    for query in invalid_queries:
        with pytest.raises(ValueError) as exc_info:
            _validate_read_only_cypher(query)
        assert "Must contain at least one of: MATCH, RETURN" in str(exc_info.value)


# =============================================================================
# Formatting and Confidence Tests (8 tests)
# =============================================================================

def test_format_cypher_results_empty():
    """Test formatting empty Cypher results."""
    result = format_cypher_results([])
    assert result == "No results found."


def test_format_cypher_results_with_data():
    """Test formatting Cypher results with actual data."""
    # Mock Neo4j Record-like objects
    class MockRecord:
        def __init__(self, data):
            self._data = data

        def keys(self):
            return list(self._data.keys())

        def __getitem__(self, key):
            return self._data[key]

    records = [
        MockRecord({"name": "Alice", "age": 30}),
        MockRecord({"name": "Bob", "age": 25}),
    ]

    result = format_cypher_results(records)
    assert "name | age" in result
    assert "Alice" in result
    assert "Bob" in result
    assert "30" in result
    assert "25" in result


def test_format_retriever_results_empty():
    """Test formatting empty retriever results."""
    result = format_retriever_results([])
    assert result == "No results found."


def test_format_retriever_results_with_scores():
    """Test formatting retriever results with scores and content."""
    items = [
        {
            "content": "This is the first chunk of text.",
            "score": 0.95,
            "metadata": {"source_file": "doc1.md"}
        },
        {
            "content": "This is the second chunk of text.",
            "score": 0.87,
            "metadata": {"source_file": "doc2.md"}
        },
    ]

    result = format_retriever_results(items)
    assert "[1] Score: 0.950" in result
    assert "[2] Score: 0.870" in result
    assert "doc1.md" in result
    assert "doc2.md" in result
    assert "first chunk" in result
    assert "second chunk" in result


def test_calculate_confidence_schema():
    """Test confidence calculation for schema strategy."""
    confidence = calculate_confidence(["some", "data"], "schema")
    assert confidence == 1.0  # Schema queries are deterministic


def test_calculate_confidence_cypher():
    """Test confidence calculation for Cypher strategy."""
    # With results
    confidence = calculate_confidence([{"name": "Alice"}], "cypher")
    assert confidence == 0.8

    # Without results
    confidence = calculate_confidence([], "cypher")
    assert confidence == 0.0


def test_calculate_confidence_vector():
    """Test confidence calculation for vector-based strategies."""
    # High similarity scores
    high_score_items = [
        {"score": 0.95},
        {"score": 0.92},
        {"score": 0.88},
    ]
    confidence = calculate_confidence(high_score_items, "vector")
    assert confidence == 0.9

    # Medium similarity scores
    medium_score_items = [
        {"score": 0.65},
        {"score": 0.62},
        {"score": 0.60},
    ]
    confidence = calculate_confidence(medium_score_items, "vector")
    assert confidence == 0.7

    # Low similarity scores
    low_score_items = [
        {"score": 0.35},
        {"score": 0.32},
        {"score": 0.30},
    ]
    confidence = calculate_confidence(low_score_items, "vector")
    assert confidence == 0.3


def test_calculate_confidence_empty():
    """Test confidence calculation with empty evidence."""
    confidence = calculate_confidence([], "vector")
    assert confidence == 0.0

    confidence = calculate_confidence([], "hybrid")
    assert confidence == 0.0


# =============================================================================
# Cross-Layer Formatter Tests
# =============================================================================

def test_node_to_dict_with_node():
    """Test _node_to_dict converts Neo4j-like node to dict."""
    from pipelines.query_builder import _node_to_dict

    class MockNode:
        def __init__(self, labels, props):
            self.labels = frozenset(labels)
            self._props = props
        def keys(self):
            return self._props.keys()
        def __getitem__(self, key):
            return self._props[key]

    node = MockNode(["Product", "__KGBuilder__"], {"name": "Chair", "price": "$100"})
    result = _node_to_dict(node)
    assert result["labels"] == ["Product", "__KGBuilder__"] or set(result["labels"]) == {"Product", "__KGBuilder__"}
    assert result["properties"]["name"] == "Chair"
    assert result["properties"]["price"] == "$100"


def test_node_to_dict_with_none():
    """Test _node_to_dict returns None for None input."""
    from pipelines.query_builder import _node_to_dict
    assert _node_to_dict(None) is None


def test_cross_layer_formatter_extracts_all_fields():
    """Test _cross_layer_formatter properly maps Record columns to metadata."""
    from pipelines.query_builder import _cross_layer_formatter

    class MockNode:
        def __init__(self, labels, props):
            self.labels = frozenset(labels)
            self._props = props
        def keys(self):
            return self._props.keys()
        def __getitem__(self, key):
            return self._props[key]

    class MockRecord:
        def __init__(self, data):
            self._data = data
        def get(self, key, default=None):
            return self._data.get(key, default)

    entity = MockNode(["QualityIssue", "__KGBuilder__"], {"description": "drawer rails defective"})
    domain = MockNode(["Product"], {"product_name": "Dresser", "price": "$212"})

    record = MockRecord({
        "chunk_text": "The drawer rails were defective...",
        "source_file": "reviews.md",
        "score": 0.671,
        "entity": entity,
        "entity_label": "QualityIssue",
        "domain_entity": domain,
        "domain_label": "Product",
    })

    result = _cross_layer_formatter(record)

    # Content should be chunk text
    assert result.content == "The drawer rails were defective..."

    # Metadata should have proper score
    assert result.metadata["score"] == 0.671
    assert result.metadata["source_file"] == "reviews.md"
    assert result.metadata["entity_label"] == "QualityIssue"
    assert result.metadata["domain_label"] == "Product"

    # Entity should be converted to dict
    assert result.metadata["entity"]["properties"]["description"] == "drawer rails defective"
    assert result.metadata["domain_entity"]["properties"]["product_name"] == "Dresser"


def test_cross_layer_formatter_handles_no_domain_entity():
    """Test _cross_layer_formatter when CORRESPONDS_TO yields no match."""
    from pipelines.query_builder import _cross_layer_formatter

    class MockNode:
        def __init__(self, labels, props):
            self.labels = frozenset(labels)
            self._props = props
        def keys(self):
            return self._props.keys()
        def __getitem__(self, key):
            return self._props[key]

    class MockRecord:
        def __init__(self, data):
            self._data = data
        def get(self, key, default=None):
            return self._data.get(key, default)

    entity = MockNode(["Customer", "__Entity__"], {"name": "@home_chef"})

    record = MockRecord({
        "chunk_text": "Good chair, good price.",
        "source_file": None,
        "score": 0.710,
        "entity": entity,
        "entity_label": "Customer",
        "domain_entity": None,
        "domain_label": None,
    })

    result = _cross_layer_formatter(record)

    assert result.content == "Good chair, good price."
    assert result.metadata["score"] == 0.710
    assert result.metadata["entity_label"] == "Customer"
    assert result.metadata["entity"]["properties"]["name"] == "@home_chef"
    assert result.metadata["domain_entity"] is None
    assert result.metadata["domain_label"] is None


# =============================================================================
# Lucene Escaping Tests (4 tests)
# =============================================================================

def test_escape_lucene_plain_text():
    """Plain text passes through unchanged."""
    assert _escape_lucene("which suppliers have complaints") == "which suppliers have complaints"


def test_escape_lucene_special_chars():
    """All Lucene special characters are escaped."""
    assert _escape_lucene('a + b') == r'a \+ b'
    assert _escape_lucene('a/b') == r'a\/b'
    assert _escape_lucene('say "hello"') == r'say \"hello\"'
    assert _escape_lucene('price: 100') == r'price\: 100'


def test_escape_lucene_question_marks_and_wildcards():
    """Question marks and wildcards are escaped."""
    assert _escape_lucene("what is this?") == r"what is this\?"
    assert _escape_lucene("test*") == r"test\*"
    assert _escape_lucene("a~b") == r"a\~b"


def test_escape_lucene_empty_string():
    """Empty string returns empty."""
    assert _escape_lucene("") == ""


# =============================================================================
# Strategy Selector Architecture Block Tests (3 tests)
# =============================================================================

def _build_architecture_block(domain_labels, text_entities, has_domain, has_text):
    """Replicate the architecture block logic from _select_retrieval_strategy."""
    if not (has_domain and has_text):
        return ""
    arch_lines = [
        "",
        "DUAL-LAYER ARCHITECTURE:",
        "This graph has two separate node populations that share some labels.",
        "Text-extracted nodes (from unstructured data) carry the `__Entity__` label.",
        "Domain nodes (from structured data) do NOT have the `__Entity__` label.",
        "The `CORRESPONDS_TO` relationship bridges text entities to domain entities.",
    ]
    overlap = set(domain_labels) & set(text_entities)
    if overlap:
        arch_lines.append(f"Overlapping labels (exist in BOTH layers as separate nodes): {', '.join(sorted(overlap))}")
    arch_lines.append("Cross-layer Cypher pattern: MATCH (t:__Entity__:Label)-[:CORRESPONDS_TO]->(d:Label)")
    return "\n".join(arch_lines)


def test_architecture_block_both_layers_with_overlap():
    """Architecture block shows overlapping labels when both layers exist."""
    block = _build_architecture_block(
        domain_labels=["Product", "Supplier", "Part"],
        text_entities=["Part", "Review", "Defect"],
        has_domain=True,
        has_text=True,
    )
    assert "DUAL-LAYER ARCHITECTURE" in block
    assert "__Entity__" in block
    assert "CORRESPONDS_TO" in block
    assert "Part" in block  # Overlapping label
    assert "Supplier" not in block  # Domain-only, not in overlap line


def test_architecture_block_both_layers_no_overlap():
    """Architecture block still appears without overlapping labels."""
    block = _build_architecture_block(
        domain_labels=["Product", "Supplier"],
        text_entities=["Review", "Defect"],
        has_domain=True,
        has_text=True,
    )
    assert "DUAL-LAYER ARCHITECTURE" in block
    assert "CORRESPONDS_TO" in block
    assert "Overlapping" not in block


def test_architecture_block_single_layer():
    """No architecture block when only one layer exists."""
    assert _build_architecture_block(["Product"], [], True, False) == ""
    assert _build_architecture_block([], ["Review"], False, True) == ""


# =============================================================================
# Mock helpers for Neo4j nodes
# =============================================================================

class MockNode:
    """Mock Neo4j Node with keys() and __getitem__."""
    def __init__(self, props):
        self._props = props
    def keys(self):
        return list(self._props.keys())
    def __getitem__(self, key):
        return self._props[key]


def _mock_driver_for_introspect(label_results):
    """Build a mock driver that returns specified results per label.

    Args:
        label_results: dict mapping label -> (props_list, node_props_dict) or None
    """
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__ = MagicMock(return_value=session)
    driver.session.return_value.__exit__ = MagicMock(return_value=False)

    def run_side_effect(query):
        result = MagicMock()
        # Extract label from query
        for label, data in label_results.items():
            if f":`{label}`" in query:
                if data is None:
                    result.single.return_value = None
                else:
                    props_list, node_props = data
                    node = MockNode(node_props)
                    record = {"props": props_list, "n": node}
                    mock_record = MagicMock()
                    mock_record.__getitem__ = lambda self, key, r=record: r[key]
                    result.single.return_value = mock_record
                return result
        result.single.return_value = None
        return result

    session.run.side_effect = run_side_effect
    return driver


# =============================================================================
# TestIntrospectTextSchema (8 tests)
# =============================================================================

class TestIntrospectTextSchema:
    """Tests for _introspect_text_schema."""

    def test_introspect_basic(self):
        """Two entity labels produce correct state structure."""
        state = {
            "approved_entity_types": {
                "Product": {"description": "A product"},
                "Review": {"description": "A review"},
            }
        }
        driver = _mock_driver_for_introspect({
            "Product": (["name", "url"], {"name": "Stockholm Chair", "url": "http://example.com"}),
            "Review": (["content", "rating"], {"content": "Great chair!", "rating": "4/5"}),
        })

        result = _introspect_text_schema(driver, state)

        assert "Product" in result
        assert "Review" in result
        assert result["Product"]["properties"]["name"]["sample"] == "Stockholm Chair"
        assert result["Review"]["properties"]["rating"]["sample"] == "4/5"
        assert state["text_entity_schema"] == result

    def test_introspect_filters_embedding(self):
        """Embedding property is excluded."""
        state = {
            "approved_entity_types": {
                "Product": {"description": "A product"},
            }
        }
        driver = _mock_driver_for_introspect({
            "Product": (["name", "embedding"], {"name": "Chair", "embedding": [0.1, 0.2]}),
        })

        result = _introspect_text_schema(driver, state)

        assert "name" in result["Product"]["properties"]
        assert "embedding" not in result["Product"]["properties"]

    def test_introspect_filters_dunder_props(self):
        """__internal__ prefixed properties are excluded."""
        state = {
            "approved_entity_types": {
                "Product": {"description": "A product"},
            }
        }
        driver = _mock_driver_for_introspect({
            "Product": (["name", "__internal_id__"], {"name": "Chair", "__internal_id__": "abc"}),
        })

        result = _introspect_text_schema(driver, state)

        assert "name" in result["Product"]["properties"]
        assert "__internal_id__" not in result["Product"]["properties"]

    def test_introspect_skips_infrastructure_labels(self):
        """Chunk, Document, __KGBuilder__, __Entity__ are skipped."""
        state = {
            "approved_entity_types": {
                "Product": {"description": "A product"},
                "Chunk": {"description": "Shouldn't be here"},
                "Document": {"description": "Shouldn't be here"},
                "__Entity__": {"description": "Infrastructure"},
                "__KGBuilder__": {"description": "Infrastructure"},
            }
        }
        driver = _mock_driver_for_introspect({
            "Product": (["name"], {"name": "Chair"}),
        })

        result = _introspect_text_schema(driver, state)

        assert "Product" in result
        assert "Chunk" not in result
        assert "Document" not in result
        assert "__Entity__" not in result
        assert "__KGBuilder__" not in result

    def test_introspect_empty_graph(self):
        """Labels in state but no nodes in graph produces empty schema."""
        state = {
            "approved_entity_types": {
                "Product": {"description": "A product"},
            }
        }
        driver = _mock_driver_for_introspect({
            "Product": None,  # No nodes found
        })

        result = _introspect_text_schema(driver, state)

        assert result == {}
        assert state["text_entity_schema"] == {}

    def test_introspect_error_handling(self):
        """Driver exception returns empty dict without raising."""
        state = {
            "approved_entity_types": {
                "Product": {"description": "A product"},
            }
        }
        driver = MagicMock()
        driver.session.side_effect = Exception("Connection refused")

        result = _introspect_text_schema(driver, state)

        assert result == {}
        assert state["text_entity_schema"] == {}

    def test_introspect_truncates_long_values(self):
        """Sample values longer than 100 chars are truncated."""
        long_value = "x" * 500
        state = {
            "approved_entity_types": {
                "Review": {"description": "A review"},
            }
        }
        driver = _mock_driver_for_introspect({
            "Review": (["content"], {"content": long_value}),
        })

        result = _introspect_text_schema(driver, state)

        sample = result["Review"]["properties"]["content"]["sample"]
        assert len(sample) == 100
        assert sample == "x" * 100

    def test_introspect_no_entity_types(self):
        """No approved_entity_types produces empty schema."""
        state = {}
        driver = MagicMock()

        result = _introspect_text_schema(driver, state)

        assert result == {}
        assert state["text_entity_schema"] == {}


# =============================================================================
# TestIntrospectDomainSchema (8 tests)
# =============================================================================

class TestIntrospectDomainSchema:
    """Tests for _introspect_domain_schema."""

    def _plan_state(self, **extra_entries):
        """Build a state with a construction plan containing node entries."""
        plan = {
            "Product": {
                "construction_type": "node",
                "label": "Product",
                "properties": ["product_name", "price"],
                "source_file": "products.csv",
            },
            "Supplier": {
                "construction_type": "node",
                "label": "Supplier",
                "properties": ["name", "city"],
                "source_file": "suppliers.csv",
            },
        }
        plan.update(extra_entries)
        return {"approved_construction_plan": plan}

    def test_introspect_basic(self):
        """Two node labels produce correct state structure."""
        state = self._plan_state()
        driver = _mock_driver_for_introspect({
            "Product": (
                ["product_name", "price"],
                {"product_name": "Stockholm Chair", "price": "$349.99"},
            ),
            "Supplier": (
                ["name", "city"],
                {"name": "Nordic Wood Co.", "city": "Stockholm"},
            ),
        })

        result = _introspect_domain_schema(driver, state)

        assert "Product" in result
        assert "Supplier" in result
        assert result["Product"]["properties"]["product_name"]["sample"] == "Stockholm Chair"
        assert result["Product"]["properties"]["price"]["sample"] == "$349.99"
        assert result["Supplier"]["properties"]["name"]["sample"] == "Nordic Wood Co."
        assert state["domain_node_schema"] == result

    def test_introspect_filters_embedding(self):
        """Embedding property is excluded."""
        state = self._plan_state()
        driver = _mock_driver_for_introspect({
            "Product": (
                ["product_name", "embedding"],
                {"product_name": "Chair", "embedding": [0.1, 0.2]},
            ),
            "Supplier": None,
        })

        result = _introspect_domain_schema(driver, state)

        assert "product_name" in result["Product"]["properties"]
        assert "embedding" not in result["Product"]["properties"]

    def test_introspect_filters_dunder_props(self):
        """__internal__ prefixed properties are excluded."""
        state = self._plan_state()
        driver = _mock_driver_for_introspect({
            "Product": (
                ["product_name", "__internal_id__"],
                {"product_name": "Chair", "__internal_id__": "abc"},
            ),
            "Supplier": None,
        })

        result = _introspect_domain_schema(driver, state)

        assert "product_name" in result["Product"]["properties"]
        assert "__internal_id__" not in result["Product"]["properties"]

    def test_introspect_skips_relationships(self):
        """Relationship entries in plan are ignored."""
        state = self._plan_state(
            SUPPLIES={
                "construction_type": "relationship",
                "relationship_type": "SUPPLIES",
                "from_node_label": "Supplier",
                "to_node_label": "Product",
            }
        )
        driver = _mock_driver_for_introspect({
            "Product": (["product_name"], {"product_name": "Chair"}),
            "Supplier": (["name"], {"name": "Nordic"}),
        })

        result = _introspect_domain_schema(driver, state)

        assert "SUPPLIES" not in result
        assert "Product" in result
        assert "Supplier" in result

    def test_introspect_empty_graph(self):
        """Labels in plan but no nodes in Neo4j produces empty schema."""
        state = self._plan_state()
        driver = _mock_driver_for_introspect({
            "Product": None,
            "Supplier": None,
        })

        result = _introspect_domain_schema(driver, state)

        assert result == {}
        assert state["domain_node_schema"] == {}

    def test_introspect_error_handling(self):
        """Driver exception returns empty dict without raising."""
        state = self._plan_state()
        driver = MagicMock()
        driver.session.side_effect = Exception("Connection refused")

        result = _introspect_domain_schema(driver, state)

        assert result == {}
        assert state["domain_node_schema"] == {}

    def test_introspect_truncates_long_values(self):
        """Sample values longer than 100 chars are truncated."""
        long_value = "x" * 500
        state = self._plan_state()
        driver = _mock_driver_for_introspect({
            "Product": (["product_name"], {"product_name": long_value}),
            "Supplier": None,
        })

        result = _introspect_domain_schema(driver, state)

        sample = result["Product"]["properties"]["product_name"]["sample"]
        assert len(sample) == 100
        assert sample == "x" * 100

    def test_introspect_no_construction_plan(self):
        """No approved_construction_plan produces empty schema."""
        state = {}
        driver = MagicMock()

        result = _introspect_domain_schema(driver, state)

        assert result == {}
        assert state["domain_node_schema"] == {}


# =============================================================================
# Relationship Schema Introspection Tests
# =============================================================================

class TestIntrospectRelationshipSchema:
    """Tests for _introspect_relationship_schema."""

    def test_basic_introspection(self):
        """Introspects domain relationship properties."""
        state = {
            "approved_construction_plan": {
                "SUPPLIES": {
                    "construction_type": "relationship",
                    "relationship_type": "SUPPLIES",
                    "from_node_label": "Supplier",
                    "to_node_label": "Part",
                    "properties": ["lead_time_days", "unit_cost"],
                },
            },
        }
        mock_rel = MagicMock()
        mock_rel.__getitem__ = lambda self, key: {"lead_time_days": "14", "unit_cost": "$35"}[key]

        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: {
            "props": ["lead_time_days", "unit_cost"],
            "r": mock_rel,
        }[key]

        mock_result = MagicMock()
        mock_result.single.return_value = mock_record

        mock_session = MagicMock()
        mock_session.run.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_driver = MagicMock()
        mock_driver.session.return_value = mock_session

        result = _introspect_relationship_schema(mock_driver, state)
        assert "SUPPLIES" in result
        assert "lead_time_days" in result["SUPPLIES"]["properties"]
        assert result["SUPPLIES"]["properties"]["lead_time_days"]["sample"] == "14"
        assert state["relationship_schema"] == result

    def test_filters_dunder_properties(self):
        """Filters out __-prefixed properties."""
        state = {
            "approved_construction_plan": {
                "SUPPLIES": {
                    "construction_type": "relationship",
                    "relationship_type": "SUPPLIES",
                    "from_node_label": "Supplier",
                    "to_node_label": "Part",
                    "properties": [],
                },
            },
        }
        mock_rel = MagicMock()
        mock_rel.__getitem__ = lambda self, key: {"lead_time_days": "14", "__internal": "x"}[key]

        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: {
            "props": ["lead_time_days", "__internal", "embedding"],
            "r": mock_rel,
        }[key]

        mock_result = MagicMock()
        mock_result.single.return_value = mock_record

        mock_session = MagicMock()
        mock_session.run.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_driver = MagicMock()
        mock_driver.session.return_value = mock_session

        result = _introspect_relationship_schema(mock_driver, state)
        assert "SUPPLIES" in result
        props = result["SUPPLIES"]["properties"]
        assert "lead_time_days" in props
        assert "__internal" not in props
        assert "embedding" not in props

    def test_graceful_failure(self):
        """Returns empty dict and stores it on Neo4j error."""
        state = {
            "approved_construction_plan": {
                "SUPPLIES": {
                    "construction_type": "relationship",
                    "relationship_type": "SUPPLIES",
                    "from_node_label": "Supplier",
                    "to_node_label": "Part",
                    "properties": [],
                },
            },
        }
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("connection error")
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_driver = MagicMock()
        mock_driver.session.return_value = mock_session

        result = _introspect_relationship_schema(mock_driver, state)
        # Individual rel failures are logged but don't crash
        assert "relationship_schema" in state
        assert isinstance(result, dict)

    def test_empty_construction_plan(self):
        """Returns empty dict with no construction plan."""
        state = {}
        mock_driver = MagicMock()
        result = _introspect_relationship_schema(mock_driver, state)
        assert result == {}
        assert state["relationship_schema"] == {}

    def test_text_relationships_introspected(self):
        """Introspects text layer relationships from approved_fact_types."""
        state = {
            "approved_fact_types": {
                "evaluates": {
                    "subject_label": "Review",
                    "predicate_label": "evaluates",
                    "object_label": "Product",
                },
            },
        }
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: {
            "props": [],
            "r": MagicMock(),
        }[key]

        mock_result = MagicMock()
        mock_result.single.return_value = mock_record

        mock_session = MagicMock()
        mock_session.run.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_driver = MagicMock()
        mock_driver.session.return_value = mock_session

        result = _introspect_relationship_schema(mock_driver, state)
        # Should have been queried (even if no properties found)
        assert mock_session.run.called
        # The query should use __Entity__ for text relationships
        call_args = mock_session.run.call_args[0][0]
        assert "__Entity__" in call_args

    def test_no_record_returns_empty(self):
        """Handles relationships with no instances in the graph."""
        state = {
            "approved_construction_plan": {
                "SUPPLIES": {
                    "construction_type": "relationship",
                    "relationship_type": "SUPPLIES",
                    "from_node_label": "Supplier",
                    "to_node_label": "Part",
                    "properties": ["lead_time_days"],
                },
            },
        }
        mock_result = MagicMock()
        mock_result.single.return_value = None

        mock_session = MagicMock()
        mock_session.run.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_driver = MagicMock()
        mock_driver.session.return_value = mock_session

        result = _introspect_relationship_schema(mock_driver, state)
        assert result == {}


# =============================================================================
# _execute_schema_query layer-aware property sampling (4 tests)
# =============================================================================

class TestExecuteSchemaQueryProperties:
    """Tests for layer-aware property sampling in _execute_schema_query.

    Overlapping labels (same label in both domain and text layers) must
    sample properties separately per layer to avoid returning the wrong
    property names to the Cypher generator.
    """

    def _make_driver(self, query_results):
        """Build a mock driver that returns specific results per query pattern.

        Args:
            query_results: list of (pattern, result_dict) tuples.
                Each result_dict maps to what session.run().single() returns,
                or to a list for session.run() iteration.
        """
        driver = MagicMock()
        session = MagicMock()
        driver.session.return_value.__enter__ = MagicMock(return_value=session)
        driver.session.return_value.__exit__ = MagicMock(return_value=False)

        def run_side_effect(query):
            result = MagicMock()
            for pattern, response in query_results:
                if pattern in query:
                    if isinstance(response, list):
                        # For iteration (db.labels, etc.)
                        result.__iter__ = MagicMock(return_value=iter(response))
                        result.single.return_value = response[0] if response else None
                    elif response is None:
                        result.single.return_value = None
                        result.__iter__ = MagicMock(return_value=iter([]))
                    else:
                        result.single.return_value = response
                        result.__iter__ = MagicMock(return_value=iter([response]))
                    return result
            # Default: empty
            result.single.return_value = None
            result.__iter__ = MagicMock(return_value=iter([]))
            return result

        session.run.side_effect = run_side_effect
        return driver

    def test_overlapping_label_samples_both_layers(self):
        """For overlapping labels, evidence has separate domain and text entries."""
        from pipelines.query_builder import _execute_schema_query
        from core.graph_schema import GraphSchema, NodeSchema

        schema = GraphSchema(
            nodes=[
                NodeSchema(label="Part", layer="domain"),
                NodeSchema(label="Part", layer="text"),
            ],
            overlapping_labels={"Part"},
        )

        driver = self._make_driver([
            ("db.labels", [{"label": "Part"}]),
            ("db.relationshipTypes", []),
            ("count(n)", {"count": 10}),
            # Domain Part query (NOT __Entity__)
            ("NOT n:`__Entity__`", {"props": ["part_id", "part_name", "quantity"]}),
            # Text Part query (WHERE __Entity__)
            ("WHERE n:`__Entity__`", {"props": ["name", "embedding"]}),
        ])

        result = _execute_schema_query(driver, {}, schema=schema)
        props = result["evidence"][0]["properties"]

        # Domain properties under "Part"
        assert "Part" in props
        assert "part_id" in props["Part"]
        assert "part_name" in props["Part"]

        # Text properties under "Part:__Entity__" (separate key)
        assert "Part:__Entity__" in props
        assert "name" in props["Part:__Entity__"]
        # embedding should be filtered out
        assert "embedding" not in props["Part:__Entity__"]

    def test_non_overlapping_label_samples_normally(self):
        """Non-overlapping labels use the original single-query path."""
        from pipelines.query_builder import _execute_schema_query
        from core.graph_schema import GraphSchema, NodeSchema

        schema = GraphSchema(
            nodes=[
                NodeSchema(label="Review", layer="text"),
            ],
        )

        driver = self._make_driver([
            ("db.labels", [{"label": "Review"}]),
            ("db.relationshipTypes", []),
            ("count(n)", {"count": 70}),
            (":`Review`", {"props": ["rating", "content"]}),
        ])

        result = _execute_schema_query(driver, {}, schema=schema)
        props = result["evidence"][0]["properties"]

        assert "Review" in props
        assert "rating" in props["Review"]
        assert "content" in props["Review"]
        # No separate __Entity__ key
        assert "Review:__Entity__" not in props

    def test_overlapping_label_filters_dunder_props_from_text(self):
        """Text-layer properties filter out __ prefixed props and embedding."""
        from pipelines.query_builder import _execute_schema_query
        from core.graph_schema import GraphSchema, NodeSchema

        schema = GraphSchema(
            nodes=[
                NodeSchema(label="Product", layer="domain"),
                NodeSchema(label="Product", layer="text"),
            ],
            overlapping_labels={"Product"},
        )

        driver = self._make_driver([
            ("db.labels", [{"label": "Product"}]),
            ("db.relationshipTypes", []),
            ("count(n)", {"count": 20}),
            ("NOT n:`__Entity__`", {"props": ["product_id", "product_name", "price"]}),
            ("WHERE n:`__Entity__`", {"props": ["name", "url", "embedding", "__createdAt"]}),
        ])

        result = _execute_schema_query(driver, {}, schema=schema)
        text_props = result["evidence"][0]["properties"]["Product:__Entity__"]

        assert "name" in text_props
        assert "url" in text_props
        assert "embedding" not in text_props
        assert "__createdAt" not in text_props

    def test_overlapping_label_no_text_nodes_found(self):
        """Overlapping label with no text nodes doesn't create __Entity__ key."""
        from pipelines.query_builder import _execute_schema_query
        from core.graph_schema import GraphSchema, NodeSchema

        schema = GraphSchema(
            nodes=[
                NodeSchema(label="Supplier", layer="domain"),
                NodeSchema(label="Supplier", layer="text"),
            ],
            overlapping_labels={"Supplier"},
        )

        driver = self._make_driver([
            ("db.labels", [{"label": "Supplier"}]),
            ("db.relationshipTypes", []),
            ("count(n)", {"count": 22}),
            ("NOT n:`__Entity__`", {"props": ["supplier_id", "name", "specialty"]}),
            ("WHERE n:`__Entity__`", None),  # No text nodes found
        ])

        result = _execute_schema_query(driver, {}, schema=schema)
        props = result["evidence"][0]["properties"]

        assert "Supplier" in props
        assert "Supplier:__Entity__" not in props
