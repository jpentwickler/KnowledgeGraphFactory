"""Tool handlers for NER and Fact Extraction Agents (Stages 4 & 5).

Provides:
- Pre-computation functions for markdown file context
- Tools for proposing and approving entity types (NER)
- Tools for proposing and approving fact types (Fact Extraction)
"""

import copy
import os

from core import (
    create_tool_schema,
    set_proposed,
    has_proposed,
    approve,
    get_approved,
    has_approved,
)
from tools.file_tools import _get_data_dir, _normalize_path


# ---------------------------------------------------------------------------
# Pre-computation Functions (for NER & Fact Extraction)
# ---------------------------------------------------------------------------


def build_structured_preview(file_path: str, lines_per_section: int = 5) -> str:
    """Extract heading structure + first N lines of each section.

    Parses markdown headings (#, ##, ###) and captures the first
    lines_per_section lines after each heading. This gives visibility
    into every section of the document regardless of file length.

    Args:
        file_path: Absolute path to the markdown file.
        lines_per_section: Number of lines to extract per section (default 5).

    Returns:
        Formatted string with heading structure and previews.
    """
    if not os.path.isfile(file_path):
        return f"=== {file_path} ===\n[ERROR: File not found]\n"

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = [line.rstrip("\n") for line in f]
    except Exception as exc:
        return f"=== {file_path} ===\n[ERROR: {exc}]\n"

    total = len(lines)
    sections = []
    current_heading = None
    current_lines = []

    for i, line in enumerate(lines):
        if line.startswith("#"):
            if current_heading:
                preview = current_lines[:lines_per_section]
                sections.append((current_heading, preview))
            current_heading = (i + 1, line.strip())
            current_lines = []
        else:
            current_lines.append(line)

    # Don't forget the last section
    if current_heading:
        preview = current_lines[:lines_per_section]
        sections.append((current_heading, preview))

    # Format output
    output = [f"=== {file_path} ({total} lines) ===\n"]
    for (line_num, heading), preview in sections:
        output.append(f"{heading}  [line {line_num}]")
        for p in preview:
            if p.strip():
                output.append(f"  {p.rstrip()}")
        output.append("")

    return "\n".join(output)


def build_markdown_context(state: dict) -> str:
    """Build structure-aware preview context for all approved markdown files.

    Reads each unstructured file and builds a structured preview showing
    all sections with line numbers and preview content.

    Args:
        state: Current state dictionary (must contain approved_files).

    Returns:
        Formatted string with all markdown file previews, or empty if no files.
    """
    if not has_approved(state, "files"):
        return ""

    approved = get_approved(state, "files")
    unstructured = approved.get("unstructured", [])
    data_dir = _get_data_dir()

    parts = []
    for file_entry in unstructured:
        path = file_entry["path"]
        abs_path = os.path.join(data_dir, path)
        abs_path = os.path.abspath(abs_path)
        parts.append(build_structured_preview(abs_path))

    return "\n".join(parts)


def build_well_known_types(state: dict) -> str:
    """Extract well-known entity types from the approved construction plan.

    Retrieves all node labels from the construction plan. These are
    "well-known" types that already exist in the graph schema.

    Args:
        state: Current state dictionary (must contain approved_construction_plan).

    Returns:
        Comma-separated string of node labels, or "(none)" if no node labels found.
    """
    if not has_approved(state, "construction_plan"):
        return "(none)"

    plan = get_approved(state, "construction_plan")
    types = [
        entry["label"]
        for entry in plan.values()
        if entry.get("construction_type") == "node"
    ]
    return ", ".join(types) if types else "(none)"


def build_entity_types_context(state: dict) -> str:
    """Format approved entity types for injection into Fact Extraction prompt.

    Args:
        state: Current state dictionary (must contain approved_entity_types).

    Returns:
        Formatted string listing each entity type with source and description.
    """
    if not has_approved(state, "entity_types"):
        return "(none)"

    entity_types = get_approved(state, "entity_types")

    lines = []
    for name, details in entity_types.items():
        source = details.get("source", "unknown")
        description = details.get("description", "No description")
        lines.append(f"- {name} ({source}): {description}")

    return "\n".join(lines) if lines else "(none)"


# ---------------------------------------------------------------------------
# NER Tool Schemas
# ---------------------------------------------------------------------------

TOOL_SET_PROPOSED_ENTITIES = create_tool_schema(
    name="set_proposed_entities",
    description="Save the proposed list of entity types to extract from text.",
    properties={
        "entity_types": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Entity type name in PascalCase (e.g., 'Product', 'Issue')",
                    },
                    "source": {
                        "type": "string",
                        "enum": ["well_known", "discovered"],
                        "description": "Whether the type comes from the existing graph schema or was discovered in the text",
                    },
                    "description": {
                        "type": "string",
                        "description": "What this entity type represents and why it's relevant to the goal",
                    },
                },
                "required": ["name", "source", "description"],
            },
            "description": "List of entity type definitions",
        }
    },
    required=["entity_types"],
)

TOOL_GET_PROPOSED_ENTITIES = create_tool_schema(
    name="get_proposed_entities",
    description="Get the currently proposed entity types.",
    properties={},
    required=[],
)

TOOL_APPROVE_PROPOSED_ENTITIES = create_tool_schema(
    name="approve_proposed_entities",
    description="Finalize entity types after user explicitly approves. Only use when user explicitly says to approve.",
    properties={},
    required=[],
)


# ---------------------------------------------------------------------------
# NER Tool Handlers
# ---------------------------------------------------------------------------


def handle_set_proposed_entities(state: dict, entity_types: list) -> dict:
    """Save the proposed entity types with source and description metadata.

    Validates:
    - Entity names are in PascalCase (first letter uppercase)
    - Source is either "well_known" or "discovered"

    Args:
        state: Current state dictionary.
        entity_types: List of dicts with name, source, description.

    Returns:
        Tool result with the proposed entity types or validation error.
    """
    result = {}
    for et in entity_types:
        name = et["name"]

        # Validate PascalCase
        if not name[0].isupper():
            return {
                "status": "error",
                "message": f"Entity type '{name}' should be in PascalCase (e.g., 'ProductIssue')",
            }

        # Validate source
        if et["source"] not in ("well_known", "discovered"):
            return {
                "status": "error",
                "message": f"Source for '{name}' must be 'well_known' or 'discovered'",
            }

        result[name] = {
            "source": et["source"],
            "description": et["description"],
        }

    state["proposed_entity_types"] = result
    return {
        "status": "success",
        "message": f"Proposed {len(result)} entity types. Present to user for approval.",
        "proposed_entity_types": result,
    }


def handle_get_proposed_entities(state: dict) -> dict:
    """Retrieve current proposal.

    Args:
        state: Current state dictionary.

    Returns:
        Tool result with the currently proposed entity types.
    """
    return {
        "status": "success",
        "proposed_entity_types": state.get("proposed_entity_types", {}),
    }


def handle_approve_proposed_entities(state: dict) -> dict:
    """Finalize entity types after user approval.

    Uses deep copy to avoid shared references between proposed and approved.

    Args:
        state: Current state dictionary.

    Returns:
        Tool result with the approved entity types or error if no proposal exists.
    """
    if "proposed_entity_types" not in state or not state["proposed_entity_types"]:
        return {"status": "error", "message": "No proposed entities to approve."}

    # Deep copy to avoid shared references
    state["approved_entity_types"] = copy.deepcopy(state["proposed_entity_types"])
    return {
        "status": "success",
        "message": "Entity types approved.",
        "approved_entity_types": state["approved_entity_types"],
    }
