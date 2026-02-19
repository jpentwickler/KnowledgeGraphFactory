"""
Unit tests for tools/query_tools.py

Tests:
- State extraction (10 tests)
- Cypher safety validation (5 tests)
- Formatting and confidence calculation (8 tests)
"""

import pytest
from tools.query_tools import (
    _get_domain_labels,
    _get_domain_node_properties,
    _get_domain_relationships,
    _get_text_entities,
    _get_text_relationships,
    format_cypher_results,
    format_retriever_results,
    calculate_confidence,
    _validate_read_only_cypher,
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
    assert "has_issue" in types
    assert "reviewed" in types


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
    assert rels[0]["type"] == "reported"
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
