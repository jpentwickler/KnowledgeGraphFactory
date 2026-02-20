"""Mermaid diagram generation for knowledge graph visualization.

Generates schema-level Mermaid markup from pipeline state artifacts and/or
live Neo4j graph data. Both diagram types show node types + relationship types
(not individual instances).

Functions:
    generate_schema_diagram(state) - From approved state artifacts (no Neo4j)
    generate_live_diagram(driver, state) - From live Neo4j graph
"""

import re

from tools.query_tools import (
    _get_domain_node_properties,
    _get_domain_relationships,
    _get_text_entities,
    _get_text_relationships,
    _get_domain_labels,
)


def _sanitize_id(label: str) -> str:
    """Convert a label to a valid Mermaid node ID.

    Replaces spaces and special characters with underscores. Prefixes IDs
    that start with a digit with ``n_``. Returns ``node_unknown`` for empty
    or all-special-char inputs.

    Args:
        label: Raw node label string.

    Returns:
        Sanitized Mermaid-safe node ID.
    """
    if not label or not label.strip():
        return "node_unknown"

    safe = re.sub(r"[^a-zA-Z0-9_]", "_", label)
    safe = safe.strip("_")

    if not safe:
        return "node_unknown"

    if safe[0].isdigit():
        safe = f"n_{safe}"

    return safe


def _truncate_properties(properties: list[str], max_display: int = 5) -> str:
    """Format a property list, truncating with ``...`` if too long.

    Args:
        properties: List of property name strings.
        max_display: Maximum properties to show before truncating.

    Returns:
        Comma-separated property string, e.g. ``"id, name, ..."``
        or empty string if no properties.
    """
    if not properties:
        return ""

    if len(properties) <= max_display:
        return ", ".join(properties)

    shown = properties[:max_display]
    return ", ".join(shown) + ", ..."


def generate_schema_diagram(state: dict) -> str:
    """Generate Mermaid diagram from approved state artifacts.

    Reads approved_construction_plan, approved_entity_types, and
    approved_fact_types to produce a schema-level diagram. Shows whatever
    is approved so far (progressive).

    Visual conventions:
    - Domain nodes in ``subgraph Domain["Domain Layer"]`` with properties
    - Text entities in ``subgraph Text["Text Layer"]``
    - Solid arrows ``-->`` for domain relationships
    - Dashed arrows ``-.->`` for text relationships
    - Thick arrows ``==>|CORRESPONDS_TO|`` for shared labels between layers

    Args:
        state: Pipeline state dict with approved_* keys.

    Returns:
        Mermaid markup string (without code fences), or empty string
        if no approved artifacts exist.
    """
    domain_node_props = _get_domain_node_properties(state)
    domain_rels = _get_domain_relationships(state)
    text_entities = _get_text_entities(state)
    text_rels = _get_text_relationships(state)

    if not domain_node_props and not text_entities:
        return ""

    lines = ["graph LR"]

    # Determine shared labels (appear in both domain and text layers)
    domain_label_set = set(domain_node_props.keys())
    text_entity_set = set(text_entities)
    shared_labels = domain_label_set & text_entity_set

    # --- Domain Layer ---
    has_text_layer = bool(text_entities)

    if domain_node_props:
        if has_text_layer:
            lines.append('  subgraph Domain["Domain Layer"]')

        for label, props in domain_node_props.items():
            safe_id = _sanitize_id(label)
            prop_str = _truncate_properties(props)
            if prop_str:
                lines.append(f'    {safe_id}["{label}\\n({prop_str})"]')
            else:
                lines.append(f'    {safe_id}["{label}"]')

        if has_text_layer:
            lines.append("  end")

    # --- Text Layer ---
    if text_entities:
        lines.append('  subgraph Text["Text Layer"]')

        for entity_name in text_entities:
            if entity_name in shared_labels:
                # Use _t suffix in text subgraph for shared labels
                safe_id = _sanitize_id(entity_name) + "_t"
            else:
                safe_id = _sanitize_id(entity_name)
            lines.append(f'    {safe_id}["{entity_name}"]')

        lines.append("  end")

    # --- Domain relationships (solid arrows) ---
    for rel in domain_rels:
        from_id = _sanitize_id(rel["from"])
        to_id = _sanitize_id(rel["to"])
        lines.append(f'  {from_id} -->|{rel["type"]}| {to_id}')

    # --- Text relationships (dashed arrows) ---
    for rel in text_rels:
        from_name = rel["from"]
        to_name = rel["to"]
        # Use _t suffix for shared labels in text layer
        from_id = _sanitize_id(from_name)
        if from_name in shared_labels:
            from_id += "_t"
        to_id = _sanitize_id(to_name)
        if to_name in shared_labels:
            to_id += "_t"
        lines.append(f'  {from_id} -.->|{rel["type"]}| {to_id}')

    # --- CORRESPONDS_TO bridges for shared labels ---
    for label in sorted(shared_labels):
        domain_id = _sanitize_id(label)
        text_id = _sanitize_id(label) + "_t"
        lines.append(f"  {text_id} ==>|CORRESPONDS_TO| {domain_id}")

    return "\n".join(lines)


def generate_live_diagram(driver, state: dict) -> str:
    """Generate Mermaid diagram from live Neo4j graph.

    Queries Neo4j for actual labels, counts, and relationship schema.
    Classifies labels into domain vs text using state context and
    known text-layer labels (Chunk, Document, __Entity__).

    Visual conventions match ``generate_schema_diagram``: subgraphs,
    solid/dashed/thick arrows. Shows instance counts in node labels.

    Args:
        driver: Neo4j driver instance.
        state: Pipeline state dict (for domain label classification).

    Returns:
        Mermaid markup string (without code fences), or empty string
        if graph is empty.
    """
    KNOWN_TEXT_LABELS = {"Chunk", "Document", "__Entity__"}
    MAX_NODE_TYPES = 50

    with driver.session() as session:
        # Get node labels with counts
        label_result = session.run(
            "MATCH (n) "
            "UNWIND labels(n) AS label "
            "RETURN label, count(DISTINCT n) AS count "
            "ORDER BY count DESC"
        )
        label_rows = [dict(r) for r in label_result]

        # Get relationship schema
        rel_result = session.run(
            "MATCH (a)-[r]->(b) "
            "WITH type(r) AS rel_type, "
            "  [l IN labels(a) WHERE NOT l STARTS WITH '__'][0] AS from_label, "
            "  [l IN labels(b) WHERE NOT l STARTS WITH '__'][0] AS to_label, "
            "  count(*) AS count "
            "RETURN from_label, rel_type, to_label, count "
            "ORDER BY count DESC"
        )
        rel_rows = [dict(r) for r in rel_result]

    if not label_rows:
        return ""

    # Classify labels into domain vs text
    known_domain = set(_get_domain_labels(state))

    domain_labels = {}  # label -> count
    text_labels = {}  # label -> count
    truncated = False

    for row in label_rows:
        label = row["label"]
        count = row["count"]

        if label in KNOWN_TEXT_LABELS or label.startswith("__"):
            text_labels[label] = count
        elif label in known_domain:
            domain_labels[label] = count
        else:
            # Unknown labels: default to domain unless text-like
            domain_labels[label] = count

    # Truncate if too many node types
    total_types = len(domain_labels) + len(text_labels)
    if total_types > MAX_NODE_TYPES:
        truncated = True
        # Keep top domain labels by count
        sorted_domain = sorted(domain_labels.items(), key=lambda x: -x[1])
        max_domain = MAX_NODE_TYPES - len(text_labels)
        if max_domain < 1:
            max_domain = 1
        domain_labels = dict(sorted_domain[:max_domain])

    lines = ["graph LR"]

    has_text = bool(text_labels)

    # --- Domain Layer ---
    if domain_labels:
        if has_text:
            lines.append('  subgraph Domain["Domain Layer"]')

        for label, count in domain_labels.items():
            safe_id = _sanitize_id(label)
            lines.append(f'    {safe_id}["{label} ({count})"]')

        if has_text:
            lines.append("  end")

    # --- Text Layer ---
    if text_labels:
        lines.append('  subgraph Text["Text Layer"]')

        for label, count in text_labels.items():
            safe_id = _sanitize_id(label)
            lines.append(f'    {safe_id}["{label} ({count})"]')

        lines.append("  end")

    # Build set of text label IDs for arrow-style classification
    text_id_set = {_sanitize_id(lbl) for lbl in text_labels}

    # --- Relationships ---
    for rel in rel_rows:
        from_label = rel["from_label"] or "Unknown"
        to_label = rel["to_label"] or "Unknown"
        rel_type = rel["rel_type"]
        count = rel["count"]

        from_id = _sanitize_id(from_label)
        to_id = _sanitize_id(to_label)

        if rel_type == "CORRESPONDS_TO":
            lines.append(f'  {from_id} == "{rel_type} ({count})" ==> {to_id}')
        elif from_id in text_id_set or to_id in text_id_set:
            lines.append(f'  {from_id} -. "{rel_type} ({count})" .-> {to_id}')
        else:
            lines.append(f'  {from_id} -- "{rel_type} ({count})" --> {to_id}')

    if truncated:
        lines.append(
            f"  truncated_note[\"... {total_types - MAX_NODE_TYPES} more node types omitted\"]"
        )

    return "\n".join(lines)
