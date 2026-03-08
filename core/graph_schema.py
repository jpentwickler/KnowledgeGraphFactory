"""Canonical Graph Schema — single source of truth for graph structure.

Provides:
- Dataclasses: PropertyInfo, NodeSchema, RelationshipSchema, GraphSchema
- build_graph_schema(): builds schema from state + optional introspection
- Renderers: cypher_notation(), compact_summary(), markdown(), for_repair()
- validate_cypher(): deterministic Cypher validation against schema
"""

import re
import logging
from dataclasses import dataclass, field

from core.state import get_approved

logger = logging.getLogger(__name__)


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class PropertyInfo:
    name: str
    sample: str | None = None
    inferred_type: str = "string"
    parse_hint: str | None = None


@dataclass
class NodeSchema:
    label: str
    layer: str  # "domain" | "text"
    properties: list[PropertyInfo] = field(default_factory=list)


@dataclass
class RelationshipSchema:
    type: str
    from_label: str
    to_label: str
    layer: str  # "domain" | "text" | "bridge"
    properties: list[PropertyInfo] = field(default_factory=list)


@dataclass
class ValidationIssue:
    issue_type: str  # "property_access" | "relationship_unknown" | "direction" | "cross_layer"
    message: str
    suggestion: str | None = None


@dataclass
class GraphSchema:
    nodes: list[NodeSchema] = field(default_factory=list)
    relationships: list[RelationshipSchema] = field(default_factory=list)
    overlapping_labels: set[str] = field(default_factory=set)

    # -----------------------------------------------------------------
    # Accessors (derived from canonical data)
    # -----------------------------------------------------------------

    @property
    def domain_labels(self) -> list[str]:
        """Domain node labels."""
        return [n.label for n in self.nodes if n.layer == "domain"]

    @property
    def text_labels(self) -> list[str]:
        """Text entity labels."""
        return [n.label for n in self.nodes if n.layer == "text"]

    @property
    def domain_node_properties(self) -> dict[str, list[str]]:
        """Domain node labels mapped to their property names."""
        return {
            n.label: [p.name for p in n.properties]
            for n in self.nodes if n.layer == "domain"
        }

    @property
    def rel_endpoint_map(self) -> dict[str, dict]:
        """Relationship types mapped to endpoint info (non-bridge only)."""
        return {
            r.type: {
                "type": r.type,
                "from": r.from_label,
                "to": r.to_label,
                "properties": [p.name for p in r.properties],
            }
            for r in self.relationships if r.layer != "bridge"
        }

    # -----------------------------------------------------------------
    # Renderers
    # -----------------------------------------------------------------

    def cypher_notation(self) -> str:
        """Full schema in Cypher-like notation (~800 tokens).

        Key invariant: properties are structurally inside their owner
        (node or relationship), so the LLM sees where each property lives.
        """
        sections = []

        # -- DOMAIN LAYER --
        domain_nodes = [n for n in self.nodes if n.layer == "domain"]
        domain_rels = [r for r in self.relationships if r.layer == "domain"]
        if domain_nodes or domain_rels:
            lines = ["// DOMAIN LAYER"]
            for n in domain_nodes:
                props = _format_props_inline(n.properties)
                lines.append(f"(:{n.label} {{{props}}})" if props else f"(:{n.label})")
            for r in domain_rels:
                props = _format_props_inline(r.properties)
                rel_part = f"[:{r.type} {{{props}}}]" if props else f"[:{r.type}]"
                lines.append(f"(:{r.from_label})-{rel_part}->(:{r.to_label})")
            sections.append("\n".join(lines))

        # -- TEXT LAYER --
        text_nodes = [n for n in self.nodes if n.layer == "text"]
        text_rels = [r for r in self.relationships if r.layer == "text"]
        if text_nodes or text_rels:
            lines = ["// TEXT LAYER"]
            for n in text_nodes:
                props = _format_props_inline(n.properties)
                lines.append(
                    f"(:{n.label}:__Entity__ {{{props}}})" if props
                    else f"(:{n.label}:__Entity__)"
                )
            for r in text_rels:
                props = _format_props_inline(r.properties)
                rel_part = f"[:{r.type} {{{props}}}]" if props else f"[:{r.type}]"
                lines.append(f"(:{r.from_label})-{rel_part}->(:{r.to_label})")
            sections.append("\n".join(lines))

        # -- CROSS-LAYER BRIDGES --
        bridge_rels = [r for r in self.relationships if r.layer == "bridge"]
        if bridge_rels:
            lines = ["// CROSS-LAYER BRIDGES"]
            for r in bridge_rels:
                lines.append(
                    f"(:{r.from_label}:__Entity__)-[:{r.type}]->(:{r.to_label})"
                )
            sections.append("\n".join(lines))

        # -- DATA FORMAT NOTES --
        hints = []
        for n in self.nodes:
            for p in n.properties:
                if p.parse_hint:
                    hints.append(f"  {n.label}.{p.name}: {p.parse_hint}")
        for r in self.relationships:
            for p in r.properties:
                if p.parse_hint:
                    hints.append(f"[:{r.type}].{p.name}: {p.parse_hint}")
        if hints:
            sections.append("// DATA FORMAT NOTES\n" + "\n".join(hints))

        return "\n\n".join(sections)

    def compact_summary(self) -> str:
        """Compact label/relationship listing (~200 tokens). No properties."""
        lines = []

        domain_nodes = [n for n in self.nodes if n.layer == "domain"]
        domain_rels = [r for r in self.relationships if r.layer == "domain"]
        text_nodes = [n for n in self.nodes if n.layer == "text"]
        text_rels = [r for r in self.relationships if r.layer == "text"]

        if domain_nodes:
            labels = ", ".join(n.label for n in domain_nodes)
            lines.append(f"Domain layer: {labels}")
        if domain_rels:
            rel_strs = [f"{r.type} ({r.from_label}->{r.to_label})" for r in domain_rels]
            lines.append(f"Domain relationships: {', '.join(rel_strs)}")
        if text_nodes:
            labels = ", ".join(n.label for n in text_nodes)
            lines.append(f"Text layer: {labels} (all :__Entity__)")
        if text_rels:
            rel_strs = [f"{r.type} ({r.from_label}->{r.to_label})" for r in text_rels]
            lines.append(f"Text relationships: {', '.join(rel_strs)}")
        if self.overlapping_labels:
            lines.append(
                f"Cross-layer bridges: {', '.join(sorted(self.overlapping_labels))} (via CORRESPONDS_TO)"
            )

        features = []
        if domain_nodes:
            features.append("structured properties")
        if text_nodes:
            features.append("text embeddings")
            features.append("fulltext index")
        if features:
            lines.append(f"Queryable features: {', '.join(features)}")

        return "\n".join(lines)

    def markdown(self, node_counts: dict | None = None) -> str:
        """Markdown schema summary with optional node counts."""
        lines = ["# Knowledge Graph Schema\n"]

        domain_nodes = [n for n in self.nodes if n.layer == "domain"]
        text_nodes = [n for n in self.nodes if n.layer == "text"]
        domain_rels = [r for r in self.relationships if r.layer == "domain"]
        text_rels = [r for r in self.relationships if r.layer == "text"]
        bridge_rels = [r for r in self.relationships if r.layer == "bridge"]

        if domain_nodes:
            lines.append("## Domain Layer (from structured data)")
            for n in domain_nodes:
                count_str = f": {node_counts[n.label]:,} nodes" if node_counts and n.label in node_counts else ""
                prop_names = [p.name for p in n.properties]
                lines.append(f"  - {n.label}{count_str} {prop_names}")
            lines.append("")

        if text_nodes:
            lines.append("## Text Layer (from unstructured data)")
            for n in text_nodes:
                count_str = f": {node_counts[n.label]:,} nodes" if node_counts and n.label in node_counts else ""
                prop_names = [p.name for p in n.properties]
                lines.append(f"  - {n.label}{count_str} {prop_names}")
            lines.append("")

        all_rels = domain_rels + text_rels + bridge_rels
        if all_rels:
            lines.append("## Relationships")
            for r in all_rels:
                s = f"  - {r.type}: {r.from_label} -> {r.to_label}"
                prop_names = [p.name for p in r.properties]
                if prop_names:
                    s += f" [{', '.join(prop_names)}]"
                lines.append(s)

        return "\n".join(lines)

    def for_repair(self, violation: dict) -> str:
        """Schema context filtered to violation-relevant entities.

        Includes relationship properties (currently missing from repair prompt),
        parse hints, and bridge patterns.
        """
        # Collect relevant relationship types from violation
        relevant_rels = set()
        relevant_rels.update(violation.get("domain_rels_used", set()))
        relevant_rels.update(violation.get("text_rels_used", set()))

        # Always include CORRESPONDS_TO for bridge context
        relevant_rels.add("CORRESPONDS_TO")

        # Collect labels from relevant relationships
        relevant_labels = set()
        for r in self.relationships:
            if r.type in relevant_rels:
                relevant_labels.add(r.from_label)
                relevant_labels.add(r.to_label)

        # Add overlapping labels
        relevant_labels.update(self.overlapping_labels)

        sections = []

        # Domain relationships (filtered)
        domain_rels = [r for r in self.relationships if r.layer == "domain" and r.type in relevant_rels]
        if domain_rels:
            lines = ["DOMAIN LAYER:"]
            for r in domain_rels:
                props = _format_props_inline(r.properties)
                rel_part = f"[:{r.type} {{{props}}}]" if props else f"[:{r.type}]"
                lines.append(f"  (:{r.from_label})-{rel_part}->(:{r.to_label})")
            sections.append("\n".join(lines))

        # Text relationships (filtered)
        text_rels = [r for r in self.relationships if r.layer == "text" and r.type in relevant_rels]
        if text_rels:
            lines = ["TEXT LAYER:"]
            for r in text_rels:
                props = _format_props_inline(r.properties)
                rel_part = f"[:{r.type} {{{props}}}]" if props else f"[:{r.type}]"
                lines.append(f"  (:{r.from_label})-{rel_part}->(:{r.to_label})")
            sections.append("\n".join(lines))

        # Overlapping labels
        if self.overlapping_labels:
            sections.append(
                f"OVERLAPPING LABELS: {', '.join(sorted(self.overlapping_labels))}"
            )

        # Bridge pattern
        sections.append(
            "BRIDGE PATTERN:\n"
            "  (t:__Entity__:Label)-[:CORRESPONDS_TO]->(d:Label)"
        )

        # Parse hints for relevant labels
        hints = []
        for n in self.nodes:
            if n.label in relevant_labels:
                for p in n.properties:
                    if p.parse_hint:
                        hints.append(f"  {n.label}.{p.name}: {p.parse_hint}")
        for r in self.relationships:
            if r.type in relevant_rels:
                for p in r.properties:
                    if p.parse_hint:
                        hints.append(f"  [:{r.type}].{p.name}: {p.parse_hint}")
        if hints:
            sections.append("DATA FORMAT NOTES:\n" + "\n".join(hints))

        return "\n\n".join(sections)

    # -----------------------------------------------------------------
    # Cypher Validation
    # -----------------------------------------------------------------

    def validate_cypher(self, cypher: str) -> list[ValidationIssue]:
        """Validate Cypher query against schema. No LLM call.

        Checks:
        1. Property access — property on correct owner (node vs relationship)
        2. Relationship existence — flags unknown types, suggests closest match
        3. Direction — detects reversed relationship direction
        4. Cross-layer — detects both-layer usage without CORRESPONDS_TO
        """
        issues = []

        # Build lookup tables
        node_props = {}  # label -> set of property names
        for n in self.nodes:
            node_props[n.label] = {p.name for p in n.properties}

        rel_props = {}  # type -> set of property names
        rel_schema = {}  # type -> RelationshipSchema
        all_rel_types = set()
        for r in self.relationships:
            rel_props[r.type] = {p.name for p in r.properties}
            rel_schema[r.type] = r
            all_rel_types.add(r.type)

        # 1. Property access: extract variable.property and variable aliases
        var_labels = _extract_variable_labels(cypher)
        var_props = re.findall(r'(\w+)\.(\w+)', cypher)
        for var, prop in var_props:
            # Skip known non-variable references
            if var in ("labels", "count", "sum", "avg", "min", "max",
                       "collect", "size", "type", "id", "keys",
                       "toInteger", "toFloat", "toString", "trim",
                       "toLower", "toUpper", "replace", "split",
                       "head", "tail", "last", "nodes", "rels",
                       "relationships", "length", "properties",
                       "coalesce", "datetime", "date", "duration",
                       "point", "distance", "abs", "ceil", "floor",
                       "round", "rand", "sign", "log", "log10",
                       "sqrt", "exp", "e", "pi", "substring",
                       "left", "right", "ltrim", "rtrim",
                       "starts", "ends", "contains", "reverse",
                       "range", "reduce", "extract", "filter",
                       "apoc", "db", "gds", "algo"):
                continue

            label = var_labels.get(var)
            if not label:
                continue

            # Check if property belongs to this label
            if label in node_props:
                if prop not in node_props[label]:
                    # Check if it's a relationship property instead
                    for rtype, rprops in rel_props.items():
                        if prop in rprops:
                            issues.append(ValidationIssue(
                                issue_type="property_access",
                                message=f"{var}.{prop} — property '{prop}' not found on node :{label}",
                                suggestion=f"'{prop}' is a property of relationship [:{rtype}]. Use a relationship variable instead.",
                            ))
                            break

        # 2. Relationship existence: extract [:TYPE] patterns
        used_rels = set()
        raw_matches = re.findall(r'\[(?:\w+)?:\s*([^\]]+)\]', cypher)
        for match in raw_matches:
            for rel_type in match.split('|'):
                cleaned = rel_type.strip()
                if cleaned and cleaned.replace('_', '').isalnum():
                    used_rels.add(cleaned)

        for used in used_rels:
            if used not in all_rel_types:
                # Find closest match
                suggestion = _find_closest_rel(used, all_rel_types)
                issues.append(ValidationIssue(
                    issue_type="relationship_unknown",
                    message=f"Unknown relationship type [:{used}]",
                    suggestion=f"Did you mean [:{suggestion}]?" if suggestion else None,
                ))

        # 3. Direction: extract (label)-[:TYPE]->(label) and check
        direction_pattern = re.compile(
            r'\((?:\w+)?:(\w+)\)\s*-\[(?:\w+)?:(\w+)\]\s*->\s*\((?:\w+)?:(\w+)\)'
        )
        for m in direction_pattern.finditer(cypher):
            from_label, rel_type, to_label = m.group(1), m.group(2), m.group(3)
            if rel_type in rel_schema:
                schema_r = rel_schema[rel_type]
                if schema_r.from_label == to_label and schema_r.to_label == from_label:
                    issues.append(ValidationIssue(
                        issue_type="direction",
                        message=f"Reversed direction: (:{from_label})-[:{rel_type}]->(:{to_label})",
                        suggestion=f"Schema says (:{schema_r.from_label})-[:{rel_type}]->(:{schema_r.to_label})",
                    ))

        # 4. Cross-layer: check for both-layer usage without CORRESPONDS_TO
        domain_rel_types = {r.type for r in self.relationships if r.layer == "domain"}
        text_rel_types = {r.type for r in self.relationships if r.layer == "text"}

        if domain_rel_types and text_rel_types:
            domain_used = used_rels & domain_rel_types
            text_used = used_rels & text_rel_types
            if domain_used and text_used and "CORRESPONDS_TO" not in used_rels:
                issues.append(ValidationIssue(
                    issue_type="cross_layer",
                    message=(
                        f"Cross-layer query uses domain rels {sorted(domain_used)} "
                        f"and text rels {sorted(text_used)} without CORRESPONDS_TO bridge"
                    ),
                    suggestion="Add MATCH (t:__Entity__:Label)-[:CORRESPONDS_TO]->(d:Label) to bridge layers",
                ))

        return issues


# =============================================================================
# Format detection
# =============================================================================

def _detect_format(sample: str | None) -> tuple[str, str | None]:
    """Detect data format from a sample value.

    Returns (inferred_type, parse_hint).
    Ordered rules: None, currency, fraction, boolean, integer, float, string.
    """
    if sample is None:
        return ("string", None)

    s = sample.strip()
    if not s:
        return ("string", None)

    # Currency: starts with $ and has numeric content
    if s.startswith("$") and re.match(r'^\$[\d,]+\.?\d*$', s):
        return ("float", f"currency — strip '$' and commas before numeric comparison (e.g. '{s}')")

    # Fraction: digits/digits
    if re.match(r'^\d+/\d+$', s):
        return ("string", f"fraction — stored as string like '{s}', split on '/' for numeric comparison")

    # Boolean
    if s.lower() in ("true", "false"):
        return ("boolean", None)

    # Boolean-like (yes/no stored as strings)
    if s.lower() in ("yes", "no"):
        return ("boolean", f"boolean-like — stored as string '{s.lower()}', compare as string not boolean")

    # Integer
    if re.match(r'^-?\d+$', s):
        return ("integer", None)

    # Float/decimal
    if re.match(r'^-?\d+\.\d+$', s):
        return ("float", None)

    return ("string", None)


# =============================================================================
# Schema builder
# =============================================================================

def build_graph_schema(state: dict, driver=None) -> "GraphSchema":
    """Build a GraphSchema from pipeline state and optional introspection.

    Sources:
    - Domain nodes/rels from approved_construction_plan
    - Text nodes from approved_entity_types
    - Text rels from approved_fact_types
    - Property samples from domain_node_schema, text_entity_schema, relationship_schema
    - If driver provided and schema keys missing, falls back to introspection
    """
    nodes = []
    relationships = []

    # Load state-cached property samples
    domain_node_schema = state.get("domain_node_schema", {})
    text_entity_schema = state.get("text_entity_schema", {})
    relationship_schema = state.get("relationship_schema", {})
    plan = get_approved(state, "construction_plan")

    # Fallback: introspect from Neo4j when schema keys are empty or incomplete.
    # For text_entity_schema, also check that overlapping labels (labels that
    # exist in both domain and text layers) have entries — a partial cache that
    # only contains text-only labels like Review/Reviewer is insufficient.
    if driver is not None:
        try:
            if not domain_node_schema:
                from tools.query_tools import _introspect_domain_schema
                _introspect_domain_schema(driver, state)
                domain_node_schema = state.get("domain_node_schema", {})
            if not text_entity_schema:
                from tools.query_tools import _introspect_text_schema
                _introspect_text_schema(driver, state)
                text_entity_schema = state.get("text_entity_schema", {})
            elif plan:
                # Check for missing overlapping labels in existing cache
                domain_labels_from_plan = {
                    entry["label"]
                    for entry in plan.values()
                    if isinstance(entry, dict) and entry.get("construction_type") == "node"
                }
                entity_type_labels = set(
                    name for name, v in (get_approved(state, "entity_types") or {}).items()
                    if isinstance(v, dict)
                )
                overlapping = domain_labels_from_plan & entity_type_labels
                missing = overlapping - set(text_entity_schema.keys())
                if missing:
                    from tools.query_tools import _introspect_text_schema
                    _introspect_text_schema(driver, state)
                    text_entity_schema = state.get("text_entity_schema", {})
            if not relationship_schema:
                from tools.query_tools import _introspect_relationship_schema
                _introspect_relationship_schema(driver, state)
                relationship_schema = state.get("relationship_schema", {})
        except Exception as e:
            logger.warning("Schema introspection fallback failed: %s", e)

    # ---- Domain layer ----
    domain_labels = set()
    if plan:
        for entry in plan.values():
            if not isinstance(entry, dict):
                continue
            if entry.get("construction_type") == "node":
                label = entry.get("label", "")
                domain_labels.add(label)
                props = _build_node_properties(
                    label, entry, domain_node_schema
                )
                nodes.append(NodeSchema(label=label, layer="domain", properties=props))

            elif entry.get("construction_type") == "relationship":
                rel_type = entry.get("relationship_type", "")
                from_label = entry.get("from_node_label", "")
                to_label = entry.get("to_node_label", "")
                plan_props = entry.get("properties", [])
                props = _build_rel_properties(rel_type, plan_props, relationship_schema)
                relationships.append(RelationshipSchema(
                    type=rel_type,
                    from_label=from_label,
                    to_label=to_label,
                    layer="domain",
                    properties=props,
                ))

    # ---- Text layer ----
    entity_types = get_approved(state, "entity_types")
    text_labels = set()
    if entity_types:
        for name, value in entity_types.items():
            if isinstance(value, dict):
                text_labels.add(name)
                props = _build_text_node_properties(name, text_entity_schema)
                nodes.append(NodeSchema(label=name, layer="text", properties=props))

    fact_types = get_approved(state, "fact_types")
    if fact_types:
        for value in fact_types.values():
            if isinstance(value, dict):
                rel_type = value.get("predicate_label", "").upper()
                from_label = value.get("subject_label", "")
                to_label = value.get("object_label", "")
                props = _build_rel_properties(rel_type, [], relationship_schema)
                relationships.append(RelationshipSchema(
                    type=rel_type,
                    from_label=from_label,
                    to_label=to_label,
                    layer="text",
                    properties=props,
                ))

    # ---- Cross-layer bridges ----
    overlapping = domain_labels & text_labels
    for label in sorted(overlapping):
        relationships.append(RelationshipSchema(
            type="CORRESPONDS_TO",
            from_label=label,
            to_label=label,
            layer="bridge",
        ))

    return GraphSchema(
        nodes=nodes,
        relationships=relationships,
        overlapping_labels=overlapping,
    )


# =============================================================================
# Internal helpers
# =============================================================================

def _build_node_properties(
    label: str,
    plan_entry: dict,
    domain_node_schema: dict,
) -> list[PropertyInfo]:
    """Build PropertyInfo list for a domain node from plan + introspected schema."""
    prop_names = list(plan_entry.get("properties", []))
    unique_col = plan_entry.get("unique_column_name")
    if unique_col and unique_col not in prop_names:
        prop_names.insert(0, unique_col)

    schema_props = domain_node_schema.get(label, {}).get("properties", {})

    result = []
    for pname in prop_names:
        sample = schema_props.get(pname, {}).get("sample")
        inferred_type, parse_hint = _detect_format(sample)
        result.append(PropertyInfo(
            name=pname, sample=sample,
            inferred_type=inferred_type, parse_hint=parse_hint,
        ))
    # Add any introspected props not in the plan
    for pname, pinfo in schema_props.items():
        if pname not in prop_names:
            sample = pinfo.get("sample")
            inferred_type, parse_hint = _detect_format(sample)
            result.append(PropertyInfo(
                name=pname, sample=sample,
                inferred_type=inferred_type, parse_hint=parse_hint,
            ))
    return result


def _build_text_node_properties(
    label: str,
    text_entity_schema: dict,
) -> list[PropertyInfo]:
    """Build PropertyInfo list for a text entity from introspected schema."""
    schema_props = text_entity_schema.get(label, {}).get("properties", {})
    result = []
    for pname, pinfo in schema_props.items():
        sample = pinfo.get("sample")
        inferred_type, parse_hint = _detect_format(sample)
        result.append(PropertyInfo(
            name=pname, sample=sample,
            inferred_type=inferred_type, parse_hint=parse_hint,
        ))
    return result


def _build_rel_properties(
    rel_type: str,
    plan_props: list,
    relationship_schema: dict,
) -> list[PropertyInfo]:
    """Build PropertyInfo list for a relationship from plan + introspected schema."""
    schema_props = relationship_schema.get(rel_type, {}).get("properties", {})

    result = []
    seen = set()
    # Plan-declared properties first
    for pname in plan_props:
        seen.add(pname)
        sample = schema_props.get(pname, {}).get("sample")
        inferred_type, parse_hint = _detect_format(sample)
        result.append(PropertyInfo(
            name=pname, sample=sample,
            inferred_type=inferred_type, parse_hint=parse_hint,
        ))
    # Introspected properties not in plan
    for pname, pinfo in schema_props.items():
        if pname not in seen:
            sample = pinfo.get("sample")
            inferred_type, parse_hint = _detect_format(sample)
            result.append(PropertyInfo(
                name=pname, sample=sample,
                inferred_type=inferred_type, parse_hint=parse_hint,
            ))
    return result


def _format_props_inline(properties: list[PropertyInfo]) -> str:
    """Format properties as inline Cypher-like notation: prop: \"sample\", ..."""
    parts = []
    for p in properties:
        if p.sample is not None:
            # Truncate long samples
            sample = p.sample[:50] if len(p.sample) > 50 else p.sample
            parts.append(f'{p.name}: "{sample}"')
        else:
            parts.append(p.name)
    return ", ".join(parts)


def _extract_variable_labels(cypher: str) -> dict[str, str]:
    """Extract variable->label mapping from MATCH clauses.

    Handles: (var:Label), [var:TYPE]
    """
    mapping = {}
    # Node variables: (var:Label)
    for m in re.finditer(r'\((\w+):(\w+)', cypher):
        mapping[m.group(1)] = m.group(2)
    # Relationship variables: [var:TYPE]
    for m in re.finditer(r'\[(\w+):(\w+)', cypher):
        mapping[m.group(1)] = m.group(2)
    return mapping


def _find_closest_rel(target: str, known: set[str]) -> str | None:
    """Find closest relationship type via substring matching."""
    target_lower = target.lower()
    # Try substring match
    for rel in sorted(known):
        if target_lower in rel.lower() or rel.lower() in target_lower:
            return rel
    # Try word overlap
    target_words = set(target_lower.split("_"))
    best = None
    best_score = 0
    for rel in known:
        rel_words = set(rel.lower().split("_"))
        score = len(target_words & rel_words)
        if score > best_score:
            best_score = score
            best = rel
    return best if best_score > 0 else None
