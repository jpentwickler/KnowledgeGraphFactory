"""
Query Tools - Helper functions for knowledge graph querying.

Provides utilities for:
- State extraction (domain labels, text entities)
- Result formatting (Cypher results, retriever items)
- Confidence calculation
- Cypher safety validation
"""

import logging
from typing import Any
from core.state import get_approved

logger = logging.getLogger(__name__)


_LUCENE_SPECIAL = set(r'+-&|!(){}[]^"~*?:\/')


def _escape_lucene(text: str) -> str:
    """Escape Lucene special characters for fulltext index queries.

    Neo4j fulltext indexes use Apache Lucene. Unescaped special characters
    in natural language queries cause parse errors.
    """
    return "".join(f"\\{c}" if c in _LUCENE_SPECIAL else c for c in text)


def _get_domain_labels(state: dict) -> list[str]:
    """Extract node labels from approved_construction_plan.

    CRITICAL: Construction plan structure is {label: {construction_type, label, ...}}
    Use plan.values(), NOT plan.get("entries", [])

    Args:
        state: Pipeline state dictionary

    Returns:
        List of node label names from the construction plan
    """
    plan = get_approved(state, "construction_plan")
    if not plan:
        return []

    return [
        entry["label"]
        for entry in plan.values()
        if isinstance(entry, dict) and entry.get("construction_type") == "node"
    ]


def _get_domain_relationships(state: dict) -> list[dict]:
    """Extract relationship info from approved_construction_plan.

    Returns list of dicts with relationship metadata for graph context.
    Filters plan entries where construction_type == "relationship".

    Args:
        state: Pipeline state dictionary

    Returns:
        List of {"type": "HAS_PART", "from": "Assembly", "to": "Part", "properties": [...]}
    """
    plan = get_approved(state, "construction_plan")
    if not plan:
        return []

    rels = []
    for entry in plan.values():
        if isinstance(entry, dict) and entry.get("construction_type") == "relationship":
            rels.append({
                "type": entry.get("relationship_type", ""),
                "from": entry.get("from_node_label", ""),
                "to": entry.get("to_node_label", ""),
                "properties": entry.get("properties", []),
            })
    return rels


def _get_domain_node_properties(state: dict) -> dict[str, list[str]]:
    """Extract node labels with their properties from approved_construction_plan.

    Returns a dict mapping each node label to its list of queryable property names.
    Includes unique_column_name (the Neo4j ID property) alongside explicit properties.

    Args:
        state: Pipeline state dictionary

    Returns:
        {"Product": ["product_id", "product_name", "price", "description"], ...}
    """
    plan = get_approved(state, "construction_plan")
    if not plan:
        return {}

    result = {}
    for entry in plan.values():
        if isinstance(entry, dict) and entry.get("construction_type") == "node":
            label = entry.get("label", "")
            props = list(entry.get("properties", []))
            # Include unique_column_name as a queryable property
            unique_col = entry.get("unique_column_name")
            if unique_col and unique_col not in props:
                props.insert(0, unique_col)
            result[label] = props
    return result


def _get_text_relationships(state: dict) -> list[dict]:
    """Extract fact types from approved_fact_types.

    Returns list of dicts with relationship metadata for graph context.
    Reads predicate_label, subject_label, object_label from each entry.

    Args:
        state: Pipeline state dictionary

    Returns:
        List of {"type": "EVALUATES", "from": "Review", "to": "Product"}
    """
    fact_types = get_approved(state, "fact_types")
    if not fact_types:
        return []

    rels = []
    for value in fact_types.values():
        if isinstance(value, dict):
            rels.append({
                "type": value.get("predicate_label", "").upper(),
                "from": value.get("subject_label", ""),
                "to": value.get("object_label", ""),
            })
    return rels


def _get_text_entities(state: dict) -> list[str]:
    """Extract entity type names from approved_entity_types.

    CRITICAL: Entity types dict has names as KEYS
    Structure: {entity_name: {source, description, grounding_evidence, ...}}

    Args:
        state: Pipeline state dictionary

    Returns:
        List of entity type names
    """
    entity_types = get_approved(state, "entity_types")
    if not entity_types:
        return []

    # Only return keys that map to dictionaries (valid entity type entries)
    return [
        name
        for name, value in entity_types.items()
        if isinstance(value, dict)
    ]


def format_cypher_results(records: list) -> str:
    """Format Neo4j records as readable table.

    Limits to first 10 rows and truncates long strings to 100 characters.

    Args:
        records: List of Neo4j Record objects

    Returns:
        Formatted string representation of results
    """
    if not records:
        return "No results found."

    # Limit to first 10 rows
    display_records = records[:10]

    # Get column names from first record
    if not display_records:
        return "No results found."

    keys = display_records[0].keys()

    # Build header
    lines = []
    lines.append(" | ".join(keys))
    lines.append("-" * (sum(len(k) for k in keys) + 3 * (len(keys) - 1)))

    # Build rows
    for record in display_records:
        values = []
        for key in keys:
            value = record[key]
            # Convert to string and truncate if needed
            value_str = str(value)
            if len(value_str) > 100:
                value_str = value_str[:97] + "..."
            values.append(value_str)
        lines.append(" | ".join(values))

    # Add truncation notice if needed
    if len(records) > 10:
        lines.append(f"\n... ({len(records) - 10} more rows)")

    return "\n".join(lines)


def format_retriever_results(items: list, include_entities: bool = False) -> str:
    """Format retriever items with scores and sources.

    Args:
        items: List of retriever result items
        include_entities: If True, include entity information (for cross-layer results)

    Returns:
        Formatted string representation of results
    """
    if not items:
        return "No results found."

    lines = []
    for i, item in enumerate(items[:10], 1):
        # Extract metadata
        metadata = item.get("metadata", {})
        content = item.get("content", "")
        score = item.get("score", 0.0)

        # Build result entry
        lines.append(f"\n[{i}] Score: {score:.3f}")

        # Add source file if available
        source_file = metadata.get("source_file") or metadata.get("file_path")
        if source_file:
            lines.append(f"    Source: {source_file}")

        # Add entity information for cross-layer results
        if include_entities:
            entity = metadata.get("entity")
            entity_label = metadata.get("entity_label")
            if entity and entity_label:
                lines.append(f"    Entity: {entity_label} - {entity}")
            domain_entity = metadata.get("domain_entity")
            domain_label = metadata.get("domain_label")
            if domain_entity and domain_label:
                lines.append(f"    Domain: {domain_label} - {domain_entity}")

        # Add text preview (truncate to 200 chars)
        if content:
            preview = content.strip()
            if len(preview) > 200:
                preview = preview[:197] + "..."
            lines.append(f"    Text: {preview}")

    if len(items) > 10:
        lines.append(f"\n... ({len(items) - 10} more results)")

    return "\n".join(lines)


def calculate_confidence(evidence: list, strategy: str) -> float:
    """Calculate 0.0-1.0 confidence score based on evidence quality.

    Different strategies have different confidence calculations:
    - schema: 1.0 (deterministic)
    - cypher: based on result count (0.8 if results, 0.2 if empty)
    - vector/hybrid/cross_layer: based on similarity scores

    Args:
        evidence: List of evidence items (records, retriever results, etc.)
        strategy: Retrieval strategy name

    Returns:
        Confidence score between 0.0 and 1.0
    """
    if not evidence:
        return 0.0

    # Schema queries are deterministic
    if strategy == "schema":
        return 1.0

    # Cypher queries: high confidence if results exist
    if strategy == "cypher":
        return 0.8 if evidence else 0.2

    # Vector-based strategies: use similarity scores
    if strategy in ["vector", "hybrid", "cross_layer"]:
        # Extract scores from evidence items
        scores = []
        for item in evidence:
            if isinstance(item, dict):
                score = item.get("score", 0.0)
                scores.append(score)

        if not scores:
            return 0.0

        # Average of top scores (weighted toward top results)
        top_scores = sorted(scores, reverse=True)[:3]
        avg_score = sum(top_scores) / len(top_scores)

        # Normalize to 0.0-1.0 range (assuming scores are similarities)
        # High similarity (>0.8) = high confidence
        # Medium similarity (0.5-0.8) = medium confidence
        # Low similarity (<0.5) = low confidence
        if avg_score >= 0.8:
            return 0.9
        elif avg_score >= 0.6:
            return 0.7
        elif avg_score >= 0.4:
            return 0.5
        else:
            return 0.3

    # Default: moderate confidence
    return 0.5


def _validate_read_only_cypher(cypher: str) -> None:
    """Validate that Cypher query is read-only (no mutations).

    Blocks: CREATE, DELETE, SET, REMOVE, MERGE
    Requires: MATCH or RETURN

    Args:
        cypher: Cypher query string

    Raises:
        ValueError: If query contains mutation operations
    """
    cypher_upper = cypher.upper()

    # Check for mutation keywords
    mutation_keywords = ["CREATE", "DELETE", "SET", "REMOVE", "MERGE"]
    for keyword in mutation_keywords:
        if keyword in cypher_upper:
            raise ValueError(
                f"Mutation operations not allowed. Found '{keyword}' in query. "
                "Only read-only queries (MATCH, RETURN) are permitted."
            )

    # Require at least MATCH or RETURN
    if "MATCH" not in cypher_upper and "RETURN" not in cypher_upper:
        raise ValueError(
            "Invalid Cypher query. Must contain at least one of: MATCH, RETURN"
        )


def _introspect_text_schema(driver, state: dict) -> dict:
    """Sample text entity properties from the graph and store in state.

    For each label in approved_entity_types, queries one __Entity__ node
    to discover property names and sample values. Skips infrastructure
    labels and filters out embedding and __-prefixed properties.

    Args:
        driver: Neo4j driver instance
        state: Pipeline state dictionary (modified in place)

    Returns:
        The text_entity_schema dict (also stored in state)
    """
    _SKIP_LABELS = {"__KGBuilder__", "__Entity__", "Chunk", "Document"}

    entity_types = get_approved(state, "entity_types")
    if not entity_types:
        state["text_entity_schema"] = {}
        return {}

    labels = [
        name for name, value in entity_types.items()
        if isinstance(value, dict) and name not in _SKIP_LABELS
    ]

    schema = {}
    try:
        with driver.session() as session:
            for label in labels:
                result = session.run(
                    f"MATCH (n:`{label}`) WHERE n:`__Entity__` "
                    f"RETURN keys(n) AS props, n LIMIT 1"
                )
                record = result.single()
                if not record:
                    continue

                raw_props = record["props"]
                node = record["n"]

                properties = {}
                for prop in raw_props:
                    if prop == "embedding" or prop.startswith("__"):
                        continue
                    value = node[prop]
                    sample = str(value) if value is not None else ""
                    if len(sample) > 100:
                        sample = sample[:100]
                    properties[prop] = {"sample": sample}

                if properties:
                    schema[label] = {"properties": properties}
    except Exception as e:
        logger.warning("Text schema introspection failed: %s", e)
        state["text_entity_schema"] = {}
        return {}

    state["text_entity_schema"] = schema
    return schema


def _introspect_domain_schema(driver, state: dict) -> dict:
    """Sample domain node properties from the graph and store in state.

    For each node label in approved_construction_plan, queries one node
    (excluding __Entity__ nodes) to discover property names and sample values.
    Filters out embedding and __-prefixed properties.

    Args:
        driver: Neo4j driver instance
        state: Pipeline state dictionary (modified in place)

    Returns:
        The domain_node_schema dict (also stored in state)
    """
    plan = get_approved(state, "construction_plan")
    if not plan:
        state["domain_node_schema"] = {}
        return {}

    labels = [
        entry["label"]
        for entry in plan.values()
        if isinstance(entry, dict) and entry.get("construction_type") == "node"
    ]

    schema = {}
    try:
        with driver.session() as session:
            for label in labels:
                result = session.run(
                    f"MATCH (n:`{label}`) WHERE NOT n:`__Entity__` "
                    f"RETURN keys(n) AS props, n LIMIT 1"
                )
                record = result.single()
                if not record:
                    continue

                raw_props = record["props"]
                node = record["n"]

                properties = {}
                for prop in raw_props:
                    if prop == "embedding" or prop.startswith("__"):
                        continue
                    value = node[prop]
                    sample = str(value) if value is not None else ""
                    if len(sample) > 100:
                        sample = sample[:100]
                    properties[prop] = {"sample": sample}

                if properties:
                    schema[label] = {"properties": properties}
    except Exception as e:
        logger.warning("Domain schema introspection failed: %s", e)
        state["domain_node_schema"] = {}
        return {}

    state["domain_node_schema"] = schema
    return schema


def _introspect_relationship_schema(driver, state: dict) -> dict:
    """Sample relationship properties from the graph and store in state.

    For each domain relationship in approved_construction_plan and each text
    relationship in approved_fact_types, queries one relationship instance to
    discover property names and sample values. Filters out embedding and
    __-prefixed properties.

    Args:
        driver: Neo4j driver instance
        state: Pipeline state dictionary (modified in place)

    Returns:
        The relationship_schema dict (also stored in state)
    """
    schema = {}

    # Domain relationships from construction plan
    plan = get_approved(state, "construction_plan")
    if plan:
        for entry in plan.values():
            if isinstance(entry, dict) and entry.get("construction_type") == "relationship":
                rel_type = entry.get("relationship_type", "")
                if not rel_type:
                    continue
                _introspect_single_rel(driver, rel_type, "", schema)

    # Text relationships from fact types
    fact_types = get_approved(state, "fact_types")
    if fact_types:
        for value in fact_types.values():
            if isinstance(value, dict):
                rel_type = value.get("predicate_label", "").upper()
                if not rel_type:
                    continue
                _introspect_single_rel(driver, rel_type, "__Entity__", schema)

    state["relationship_schema"] = schema
    return schema


def _introspect_single_rel(driver, rel_type: str, entity_filter: str, schema: dict):
    """Introspect a single relationship type and add to schema dict."""
    try:
        if entity_filter:
            query = (
                f"MATCH (n:__Entity__)-[r:`{rel_type}`]->() "
                f"RETURN keys(r) AS props, r LIMIT 1"
            )
        else:
            query = (
                f"MATCH ()-[r:`{rel_type}`]->() "
                f"RETURN keys(r) AS props, r LIMIT 1"
            )
        with driver.session() as session:
            result = session.run(query)
            record = result.single()
            if not record:
                return

            raw_props = record["props"]
            rel = record["r"]

            properties = {}
            for prop in raw_props:
                if prop == "embedding" or prop.startswith("__"):
                    continue
                value = rel[prop]
                sample = str(value) if value is not None else ""
                if len(sample) > 100:
                    sample = sample[:100]
                properties[prop] = {"sample": sample}

            if properties:
                schema[rel_type] = {"properties": properties}
    except Exception as e:
        logger.warning("Relationship schema introspection failed for %s: %s", rel_type, e)


