"""Tool handlers for NER and Fact Extraction Agents (Stages 4 & 5).

Provides:
- Pre-computation functions for markdown file context
- Tools for proposing and approving entity types (NER)
- Tools for proposing and approving fact types (Fact Extraction)
"""

import copy
import os
import re

from core import (
    create_tool_schema,
    set_proposed,
    has_proposed,
    approve,
    get_approved,
    has_approved,
)

# Regex for valid predicate labels: lowercase letters, digits, underscores only
_PREDICATE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
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
                line_text = p.rstrip()
                if len(line_text) > 200:
                    line_text = line_text[:200] + "..."
                output.append(f"  {line_text}")
        output.append("")

    return "\n".join(output)


def build_markdown_context(state: dict, lines_per_section: int = 5) -> str:
    """Build structure-aware preview context for all approved markdown files.

    Reads each unstructured file and builds a structured preview showing
    all sections with line numbers and preview content.

    Args:
        state: Current state dictionary (must contain approved_files).
        lines_per_section: Number of preview lines per section (default 5).

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
        parts.append(build_structured_preview(abs_path, lines_per_section))

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
# Search Tool Schema & Handler
# ---------------------------------------------------------------------------

TOOL_SEARCH_FILES = create_tool_schema(
    name="search_files",
    description=(
        "Search approved markdown files for a text pattern. "
        "Returns matching lines with context. Use this to check "
        "whether specific terms, concepts, or patterns appear in the text."
    ),
    properties={
        "pattern": {
            "type": "string",
            "description": (
                "Search pattern (case-insensitive substring match). "
                "Examples: 'warranty', 'defect', 'customer complaint'."
            ),
        },
        "file_path": {
            "type": "string",
            "description": (
                "Optional. Search only this file (e.g., 'reviews.md'). "
                "If omitted, searches all approved markdown files."
            ),
        },
    },
    required=["pattern"],
)


def handle_search_files(
    state: dict, pattern: str, file_path: str = None
) -> dict:
    """Search approved markdown files for a text pattern.

    Performs case-insensitive search across approved unstructured files.
    Returns matching lines with 1 line of context before/after.

    Args:
        state: Current state dictionary (must contain approved_files).
        pattern: Search pattern (case-insensitive substring match).
        file_path: Optional specific file to search. If omitted, searches all.

    Returns:
        Tool result with matches, or error if no approved files.
    """
    if not has_approved(state, "files"):
        return {
            "status": "error",
            "message": "No approved files found. File Suggestion stage must be completed first.",
        }

    approved = get_approved(state, "files")
    unstructured = approved.get("unstructured", [])

    if not unstructured:
        return {
            "status": "error",
            "message": "No approved markdown files to search.",
        }

    data_dir = _get_data_dir()

    # Filter to specific file if requested
    if file_path:
        unstructured = [f for f in unstructured if f["path"] == file_path]
        if not unstructured:
            return {
                "status": "error",
                "message": f"File '{file_path}' is not in the approved markdown files.",
            }

    max_matches = 20
    matches = []
    files_searched = []

    for file_entry in unstructured:
        fpath = file_entry["path"]
        abs_path = os.path.join(data_dir, fpath)
        abs_path = os.path.abspath(abs_path)

        # Security: ensure path stays within data directory
        if not abs_path.startswith(os.path.abspath(data_dir)):
            continue

        if not os.path.isfile(abs_path):
            continue

        files_searched.append(fpath)

        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                lines = [line.rstrip("\n") for line in f]
        except Exception:
            continue

        for i, line in enumerate(lines):
            if len(matches) >= max_matches:
                break

            if re.search(pattern, line, re.IGNORECASE):
                # Build context: 1 line before and after, truncate long lines
                max_line_len = 200
                context_lines = []
                if i > 0:
                    prev = lines[i - 1][:max_line_len]
                    context_lines.append(f"  {i}: {prev}")
                match_line = line[:max_line_len]
                context_lines.append(f"> {i + 1}: {match_line}")
                if i < len(lines) - 1:
                    next_line = lines[i + 1][:max_line_len]
                    context_lines.append(f"  {i + 2}: {next_line}")

                matches.append({
                    "file": fpath,
                    "line_number": i + 1,
                    "context": "\n".join(context_lines),
                })

        if len(matches) >= max_matches:
            break

    return {
        "status": "success",
        "pattern": pattern,
        "files_searched": files_searched,
        "match_count": len(matches),
        "matches": matches,
    }


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
                    "grounding_evidence": {
                        "type": "object",
                        "description": (
                            "Evidence gathered via search_files for discovered types. "
                            "Not required for well_known types."
                        ),
                        "properties": {
                            "search_patterns": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Patterns searched (e.g., ['defect', 'defective', 'flaw'])",
                            },
                            "total_mentions": {
                                "type": "integer",
                                "description": "Total matches found across all patterns and files",
                            },
                            "example_excerpts": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Representative matching lines from the text (3-5 examples)",
                            },
                            "files_with_evidence": {
                                "type": "integer",
                                "description": "Number of files where matches were found",
                            },
                        },
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

        if "grounding_evidence" in et:
            result[name]["grounding_evidence"] = et["grounding_evidence"]

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


# ---------------------------------------------------------------------------
# Fact Type Tool Schemas
# ---------------------------------------------------------------------------

TOOL_ADD_PROPOSED_FACT = create_tool_schema(
    name="add_proposed_fact",
    description=(
        "Add a single proposed fact type (relationship template). "
        "Each fact type defines a directed relationship between two entity types. "
        "Call once per fact type. The predicate must be unique."
    ),
    properties={
        "subject_label": {
            "type": "string",
            "description": (
                "Source entity type (must be an approved entity type). "
                "Example: 'Product'"
            ),
        },
        "predicate_label": {
            "type": "string",
            "description": (
                "Relationship name in lowercase_with_underscores. "
                "Example: 'has_issue', 'supplied_by'"
            ),
        },
        "object_label": {
            "type": "string",
            "description": (
                "Target entity type (must be an approved entity type). "
                "Example: 'Issue'"
            ),
        },
    },
    required=["subject_label", "predicate_label", "object_label"],
)

TOOL_REMOVE_PROPOSED_FACT = create_tool_schema(
    name="remove_proposed_fact",
    description="Remove a previously proposed fact type by its predicate label.",
    properties={
        "predicate_label": {
            "type": "string",
            "description": "The predicate label of the fact type to remove.",
        },
    },
    required=["predicate_label"],
)

TOOL_GET_PROPOSED_FACTS = create_tool_schema(
    name="get_proposed_facts",
    description="Get all currently proposed fact types.",
    properties={},
    required=[],
)

TOOL_APPROVE_PROPOSED_FACTS = create_tool_schema(
    name="approve_proposed_facts",
    description=(
        "Finalize fact types after user explicitly approves. "
        "Only use when user explicitly says to approve."
    ),
    properties={},
    required=[],
)


# ---------------------------------------------------------------------------
# Fact Type Tool Handlers
# ---------------------------------------------------------------------------


def handle_add_proposed_fact(
    state: dict, subject_label: str, predicate_label: str, object_label: str
) -> dict:
    """Add a single proposed fact type (relationship template).

    Validates:
    - subject_label is in approved_entity_types
    - object_label is in approved_entity_types
    - predicate_label is lowercase_with_underscores (no spaces, no uppercase)

    Args:
        state: Current state dictionary (must contain approved_entity_types).
        subject_label: Source entity type name.
        predicate_label: Relationship name in lowercase_with_underscores.
        object_label: Target entity type name.

    Returns:
        Tool result with the added fact type or validation error.
    """
    # Validate approved entity types exist
    approved_entities = state.get("approved_entity_types", {})
    if not approved_entities:
        return {
            "status": "error",
            "message": "No approved entity types found. NER stage must be completed first.",
        }

    # Validate subject
    if subject_label not in approved_entities:
        available = ", ".join(sorted(approved_entities.keys()))
        return {
            "status": "error",
            "message": (
                f"Subject '{subject_label}' is not an approved entity type. "
                f"Available: {available}"
            ),
        }

    # Validate object
    if object_label not in approved_entities:
        available = ", ".join(sorted(approved_entities.keys()))
        return {
            "status": "error",
            "message": (
                f"Object '{object_label}' is not an approved entity type. "
                f"Available: {available}"
            ),
        }

    # Validate predicate format
    if not _PREDICATE_RE.match(predicate_label):
        return {
            "status": "error",
            "message": (
                f"Predicate '{predicate_label}' must be lowercase_with_underscores "
                f"(e.g., 'has_issue', 'supplied_by'). No spaces or uppercase."
            ),
        }

    # Store fact type (predicate is dict key for uniqueness)
    if "proposed_fact_types" not in state:
        state["proposed_fact_types"] = {}

    fact = {
        "subject_label": subject_label,
        "predicate_label": predicate_label,
        "object_label": object_label,
    }
    state["proposed_fact_types"][predicate_label] = fact

    return {
        "status": "success",
        "message": (
            f"Added fact type: ({subject_label})-[{predicate_label}]->({object_label}). "
            f"Total proposed: {len(state['proposed_fact_types'])}."
        ),
        "fact": fact,
    }


def handle_remove_proposed_fact(state: dict, predicate_label: str) -> dict:
    """Remove a proposed fact type by predicate label.

    Args:
        state: Current state dictionary.
        predicate_label: The predicate of the fact type to remove.

    Returns:
        Tool result confirming removal or error if not found.
    """
    proposed = state.get("proposed_fact_types", {})

    if predicate_label not in proposed:
        available = ", ".join(sorted(proposed.keys())) if proposed else "(none)"
        return {
            "status": "error",
            "message": (
                f"No proposed fact type with predicate '{predicate_label}'. "
                f"Current predicates: {available}"
            ),
        }

    removed = proposed.pop(predicate_label)
    return {
        "status": "success",
        "message": (
            f"Removed fact type: ({removed['subject_label']})-"
            f"[{predicate_label}]->({removed['object_label']}). "
            f"Remaining: {len(proposed)}."
        ),
    }


def handle_get_proposed_facts(state: dict) -> dict:
    """Get all currently proposed fact types.

    Args:
        state: Current state dictionary.

    Returns:
        Tool result with proposed fact types and count.
    """
    proposed = state.get("proposed_fact_types", {})
    return {
        "status": "success",
        "proposed_fact_types": proposed,
        "count": len(proposed),
    }


def handle_approve_proposed_facts(state: dict) -> dict:
    """Finalize fact types after user approval.

    Uses deep copy to avoid shared references between proposed and approved.

    Args:
        state: Current state dictionary.

    Returns:
        Tool result with approved fact types or error if no proposal exists.
    """
    proposed = state.get("proposed_fact_types")
    if not proposed:
        return {"status": "error", "message": "No proposed fact types to approve."}

    state["approved_fact_types"] = copy.deepcopy(proposed)
    return {
        "status": "success",
        "message": f"Fact types approved ({len(state['approved_fact_types'])} total).",
        "approved_fact_types": state["approved_fact_types"],
    }


# ---------------------------------------------------------------------------
# Shared Helper: format_user_goal
# ---------------------------------------------------------------------------


def format_user_goal(goal: dict) -> str:
    """Format user goal dict into readable text for prompt injection.

    Args:
        goal: Dictionary with 'kind' and 'description' keys.

    Returns:
        Formatted string for prompt injection.
    """
    if not goal:
        return "(No user goal found)"

    kind = goal.get("kind", "Unknown")
    description = goal.get("description", "No description")
    return f"- Kind: {kind}\n- Description: {description}"


