"""Tool handlers for the Schema Proposal Agent (Stage 3).

Provides tools for:
- Reading approved context (files, user goal)
- Searching file content (column validation)
- Proposing/removing node and relationship construction rules
- Structured critic review (submit_review)
- Approving the final construction plan
"""

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
# Tool Schemas
# ---------------------------------------------------------------------------

TOOL_GET_APPROVED_FILES = create_tool_schema(
    name="get_approved_files",
    description=(
        "Get the list of approved files from Stage 2. "
        "Returns structured (CSV) and unstructured (markdown) files "
        "that were approved for the knowledge graph pipeline."
    ),
    properties={},
    required=[],
)

TOOL_SEARCH_FILE = create_tool_schema(
    name="search_file",
    description=(
        "Search a text file (CSV, markdown, txt) for lines containing a query string. "
        "Case-insensitive. Use this to verify that column names exist in a file, "
        "or to check for data patterns and identifier uniqueness."
    ),
    properties={
        "file_path": {
            "type": "string",
            "description": "Path to the file, relative to the data directory.",
        },
        "query": {
            "type": "string",
            "description": "The string to search for (case insensitive).",
        },
    },
    required=["file_path", "query"],
)

TOOL_PROPOSE_NODE_CONSTRUCTION = create_tool_schema(
    name="propose_node_construction",
    description=(
        "Propose a node construction rule for an approved file. "
        "The rule specifies how a CSV file should be transformed into graph nodes. "
        "The unique_column_name will be validated against the file content."
    ),
    properties={
        "approved_file": {
            "type": "string",
            "description": "The approved file to create nodes from.",
        },
        "proposed_label": {
            "type": "string",
            "description": "The node label in PascalCase (e.g., 'Product', 'Supplier').",
        },
        "unique_column_name": {
            "type": "string",
            "description": "Column that uniquely identifies each node.",
        },
        "proposed_properties": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Column names to include as node properties.",
        },
    },
    required=["approved_file", "proposed_label", "unique_column_name", "proposed_properties"],
)

TOOL_PROPOSE_RELATIONSHIP_CONSTRUCTION = create_tool_schema(
    name="propose_relationship_construction",
    description=(
        "Propose a relationship construction rule for an approved file. "
        "The rule specifies how a CSV file should be transformed into graph relationships. "
        "Both from_node_column and to_node_column will be validated against the file."
    ),
    properties={
        "approved_file": {
            "type": "string",
            "description": "The approved file to create relationships from.",
        },
        "proposed_relationship_type": {
            "type": "string",
            "description": "Relationship type in SCREAMING_SNAKE_CASE (e.g., 'SUPPLIED_BY').",
        },
        "from_node_label": {
            "type": "string",
            "description": "Label of the source node.",
        },
        "from_node_column": {
            "type": "string",
            "description": "Column in the file containing the source node identifier.",
        },
        "to_node_label": {
            "type": "string",
            "description": "Label of the target node.",
        },
        "to_node_column": {
            "type": "string",
            "description": "Column in the file containing the target node identifier.",
        },
        "proposed_properties": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Column names to include as relationship properties.",
        },
    },
    required=[
        "approved_file",
        "proposed_relationship_type",
        "from_node_label",
        "from_node_column",
        "to_node_label",
        "to_node_column",
    ],
)

TOOL_REMOVE_NODE_CONSTRUCTION = create_tool_schema(
    name="remove_node_construction",
    description="Remove a node construction rule from the proposed plan by label.",
    properties={
        "node_label": {
            "type": "string",
            "description": "The label of the node construction to remove.",
        },
    },
    required=["node_label"],
)

TOOL_REMOVE_RELATIONSHIP_CONSTRUCTION = create_tool_schema(
    name="remove_relationship_construction",
    description="Remove a relationship construction rule from the proposed plan by type.",
    properties={
        "relationship_type": {
            "type": "string",
            "description": "The type of the relationship construction to remove.",
        },
    },
    required=["relationship_type"],
)

TOOL_GET_PROPOSED_CONSTRUCTION_PLAN = create_tool_schema(
    name="get_proposed_construction_plan",
    description=(
        "Get the current proposed construction plan. "
        "Returns all node and relationship construction rules "
        "with summary counts."
    ),
    properties={},
    required=[],
)

TOOL_APPROVE_PROPOSED_CONSTRUCTION_PLAN = create_tool_schema(
    name="approve_proposed_construction_plan",
    description=(
        "Approve the proposed construction plan after the user explicitly confirms. "
        "Only use when the user says 'approve', 'looks good', 'yes', or similar."
    ),
    properties={},
    required=[],
)

TOOL_SUBMIT_REVIEW = create_tool_schema(
    name="submit_review",
    description=(
        "Submit your review verdict for the proposed construction plan. "
        "You MUST call this tool after completing your analysis. "
        "Use verdict 'valid' if the schema is correct, or 'retry' with a list of problems."
    ),
    properties={
        "verdict": {
            "type": "string",
            "enum": ["valid", "retry"],
            "description": "The review verdict: 'valid' if schema is correct, 'retry' if problems found.",
        },
        "problems": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of specific problems to fix. Empty list if verdict is 'valid'.",
        },
    },
    required=["verdict", "problems"],
)

# Coordinator-only tool: wraps the refinement loop
TOOL_RUN_REFINEMENT_LOOP = create_tool_schema(
    name="run_refinement_loop",
    description=(
        "Run the schema proposal refinement loop. "
        "This analyzes approved files and proposes a construction plan, "
        "then validates it with a critic agent. "
        "The result is stored in the proposed construction plan. "
        "Call this to generate or regenerate the schema proposal."
    ),
    properties={
        "user_feedback": {
            "type": "string",
            "description": (
                "Optional feedback from the user about what to change. "
                "This will be included in the refinement process."
            ),
        },
    },
    required=[],
)


# ---------------------------------------------------------------------------
# Tool Handlers
# ---------------------------------------------------------------------------


def handle_get_approved_files(state: dict) -> dict:
    """Retrieve the approved file list from state.

    Extracts file paths from the Stage 2 approved_files structure
    (which has structured/unstructured arrays of {path, reason}).

    Args:
        state: Current state dictionary.

    Returns:
        Tool result with file path lists, or error if not found.
    """
    if not has_approved(state, "files"):
        return {
            "status": "error",
            "message": (
                "No approved files found. "
                "Stage 2 (File Suggestion) must be completed first."
            ),
        }

    approved = get_approved(state, "files")

    structured_paths = [f["path"] for f in approved.get("structured", [])]
    unstructured_paths = [f["path"] for f in approved.get("unstructured", [])]

    return {
        "status": "success",
        "message": "Retrieved approved files.",
        "structured_files": structured_paths,
        "unstructured_files": unstructured_paths,
        "all_files": structured_paths + unstructured_paths,
    }


def handle_search_file(state: dict, file_path: str, query: str) -> dict:
    """Search a text file for lines containing the query string.

    Case-insensitive search. Returns matching lines with line numbers.
    Limits results to 20 matches.

    Args:
        state: Current state dictionary (unused).
        file_path: Relative path within the data directory.
        query: String to search for (case insensitive).

    Returns:
        Tool result with matching lines and metadata.
    """
    data_dir = _get_data_dir()
    abs_path = os.path.join(data_dir, file_path)
    abs_path = os.path.abspath(abs_path)

    # Security: ensure the resolved path is within the data directory
    if not abs_path.startswith(os.path.abspath(data_dir)):
        return {
            "status": "error",
            "message": "File path is outside the data directory.",
        }

    if not os.path.isfile(abs_path):
        return {
            "status": "error",
            "message": f"File not found: {file_path}",
        }

    query_lower = query.lower()
    matching_lines = []
    max_matches = 20

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, start=1):
                if query_lower in line.lower():
                    matching_lines.append({
                        "line_number": i,
                        "content": line.rstrip("\n"),
                    })
                    if len(matching_lines) >= max_matches:
                        break

        return {
            "status": "success",
            "file_path": _normalize_path(file_path),
            "query": query,
            "lines_found": len(matching_lines),
            "matching_lines": matching_lines,
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Error searching file {file_path}: {exc}",
        }


def _validate_column_in_file(file_path: str, column_name: str) -> dict | None:
    """Check if a column name exists in the first line (header) of a CSV file.

    Args:
        file_path: Relative path within the data directory.
        column_name: Column name to validate.

    Returns:
        None if column exists, or an error dict if not found.
    """
    data_dir = _get_data_dir()
    abs_path = os.path.join(data_dir, file_path)
    abs_path = os.path.abspath(abs_path)

    if not os.path.isfile(abs_path):
        return {
            "status": "error",
            "message": f"File not found: {file_path}",
        }

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            header_line = f.readline().rstrip("\n")
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Error reading file {file_path}: {exc}",
        }

    # Check if column name appears in the header (case-insensitive)
    header_lower = header_line.lower()
    if column_name.lower() not in header_lower:
        return {
            "status": "error",
            "message": (
                f"Column '{column_name}' not found in header of {file_path}. "
                f"Available columns: {header_line}"
            ),
        }

    return None  # Validation passed


def handle_propose_node_construction(
    state: dict,
    approved_file: str,
    proposed_label: str,
    unique_column_name: str,
    proposed_properties: list,
) -> dict:
    """Add a node construction rule to the proposed construction plan.

    Validates that unique_column_name exists in the file header before adding.

    Args:
        state: Current state dictionary.
        approved_file: CSV file to create nodes from.
        proposed_label: Node label in PascalCase.
        unique_column_name: Column that uniquely identifies each node.
        proposed_properties: Column names to include as node properties.

    Returns:
        Tool result with the construction rule.
    """
    # Validate the unique column exists in the file
    error = _validate_column_in_file(approved_file, unique_column_name)
    if error:
        return error

    # Initialize plan if needed
    if "proposed_construction_plan" not in state:
        state["proposed_construction_plan"] = {}

    rule = {
        "construction_type": "node",
        "source_file": _normalize_path(approved_file),
        "label": proposed_label,
        "unique_column_name": unique_column_name,
        "properties": proposed_properties,
    }

    state["proposed_construction_plan"][proposed_label] = rule

    return {
        "status": "success",
        "message": f"Node construction '{proposed_label}' added to proposal.",
        "construction": rule,
    }


def handle_propose_relationship_construction(
    state: dict,
    approved_file: str,
    proposed_relationship_type: str,
    from_node_label: str,
    from_node_column: str,
    to_node_label: str,
    to_node_column: str,
    proposed_properties: list = None,
) -> dict:
    """Add a relationship construction rule to the proposed construction plan.

    Validates that both from_node_column and to_node_column exist in the file.

    Args:
        state: Current state dictionary.
        approved_file: CSV file to create relationships from.
        proposed_relationship_type: Relationship type in SCREAMING_SNAKE_CASE.
        from_node_label: Label of the source node.
        from_node_column: Column containing the source node identifier.
        to_node_label: Label of the target node.
        to_node_column: Column containing the target node identifier.
        proposed_properties: Column names to include as relationship properties.

    Returns:
        Tool result with the construction rule.
    """
    # Validate both columns exist
    error = _validate_column_in_file(approved_file, from_node_column)
    if error:
        error["message"] = f"from_node_column: {error['message']}"
        return error

    error = _validate_column_in_file(approved_file, to_node_column)
    if error:
        error["message"] = f"to_node_column: {error['message']}"
        return error

    # Initialize plan if needed
    if "proposed_construction_plan" not in state:
        state["proposed_construction_plan"] = {}

    rule = {
        "construction_type": "relationship",
        "source_file": _normalize_path(approved_file),
        "relationship_type": proposed_relationship_type,
        "from_node_label": from_node_label,
        "from_node_column": from_node_column,
        "to_node_label": to_node_label,
        "to_node_column": to_node_column,
        "properties": proposed_properties or [],
    }

    state["proposed_construction_plan"][proposed_relationship_type] = rule

    return {
        "status": "success",
        "message": f"Relationship construction '{proposed_relationship_type}' added to proposal.",
        "construction": rule,
    }


def handle_remove_node_construction(state: dict, node_label: str) -> dict:
    """Remove a node construction rule from the proposed plan.

    Idempotent: returns success even if the label does not exist.

    Args:
        state: Current state dictionary.
        node_label: The label of the node construction to remove.

    Returns:
        Tool result.
    """
    plan = state.get("proposed_construction_plan", {})

    if node_label in plan:
        del plan[node_label]
        return {
            "status": "success",
            "message": f"Node construction '{node_label}' removed from proposal.",
        }

    return {
        "status": "success",
        "message": f"Node construction '{node_label}' was not in the proposal (no action needed).",
    }


def handle_remove_relationship_construction(state: dict, relationship_type: str) -> dict:
    """Remove a relationship construction rule from the proposed plan.

    Idempotent: returns success even if the type does not exist.

    Args:
        state: Current state dictionary.
        relationship_type: The type of the relationship construction to remove.

    Returns:
        Tool result.
    """
    plan = state.get("proposed_construction_plan", {})

    if relationship_type in plan:
        del plan[relationship_type]
        return {
            "status": "success",
            "message": f"Relationship construction '{relationship_type}' removed from proposal.",
        }

    return {
        "status": "success",
        "message": f"Relationship construction '{relationship_type}' was not in the proposal (no action needed).",
    }


def handle_get_proposed_construction_plan(state: dict) -> dict:
    """Get the current proposed construction plan.

    Args:
        state: Current state dictionary.

    Returns:
        Tool result with the full plan and summary counts.
    """
    plan = state.get("proposed_construction_plan", {})

    node_count = sum(1 for v in plan.values() if v.get("construction_type") == "node")
    rel_count = sum(1 for v in plan.values() if v.get("construction_type") == "relationship")

    return {
        "status": "success",
        "proposed_construction_plan": plan,
        "node_count": node_count,
        "relationship_count": rel_count,
        "total_rules": len(plan),
    }


def handle_approve_proposed_construction_plan(state: dict) -> dict:
    """Approve the proposed construction plan.

    Uses core.approve() to copy proposed_construction_plan to approved_construction_plan.

    Args:
        state: Current state dictionary.

    Returns:
        Tool result with the approved plan.
    """
    if "proposed_construction_plan" not in state:
        return {
            "status": "error",
            "message": "No proposed construction plan to approve. Run the refinement loop first.",
        }

    if not state["proposed_construction_plan"]:
        return {
            "status": "error",
            "message": "Proposed construction plan is empty. Add constructions first.",
        }

    # Use set_proposed + approve pattern for consistency with core state functions
    set_proposed(state, "construction_plan", state["proposed_construction_plan"])
    approve(state, "construction_plan")

    approved = get_approved(state, "construction_plan")

    node_count = sum(1 for v in approved.values() if v.get("construction_type") == "node")
    rel_count = sum(1 for v in approved.values() if v.get("construction_type") == "relationship")

    return {
        "status": "approved",
        "message": (
            f"Construction plan approved! "
            f"{node_count} node types, {rel_count} relationship types."
        ),
        "approved_construction_plan": approved,
    }


def handle_submit_review(state: dict, verdict: str, problems: list) -> dict:
    """Record the critic's structured review verdict.

    Stores the verdict and problems list in state for the refinement loop
    to read. This avoids fragile free-text parsing.

    Args:
        state: Current state dictionary.
        verdict: "valid" or "retry".
        problems: List of problem descriptions (empty if valid).

    Returns:
        Tool result confirming the recorded verdict.
    """
    state["_critic_verdict"] = verdict
    state["_critic_problems"] = problems

    if verdict == "valid":
        return {
            "status": "success",
            "message": "Review recorded: schema is valid.",
            "verdict": verdict,
        }

    return {
        "status": "success",
        "message": f"Review recorded: retry needed. {len(problems)} problem(s) identified.",
        "verdict": verdict,
        "problems": problems,
    }


def handle_run_refinement_loop(state: dict, user_feedback: str = "") -> dict:
    """Run the schema proposal refinement loop.

    This is a tool handler that wraps the pipeline function,
    callable as a tool by the coordinator agent.

    Args:
        state: Current state dictionary (mutated in place).
        user_feedback: Optional feedback from the user.

    Returns:
        Tool result with summary and counts.
    """
    # Import here to avoid circular imports
    from pipelines.schema_loop import run_refinement_loop

    # If user provided feedback, prepend it to existing feedback
    if user_feedback:
        existing = state.get("feedback", "")
        state["feedback"] = f"{user_feedback}\n{existing}".strip()

    summary, _ = run_refinement_loop(state)

    plan = state.get("proposed_construction_plan", {})
    node_count = sum(1 for v in plan.values() if v.get("construction_type") == "node")
    rel_count = sum(1 for v in plan.values() if v.get("construction_type") == "relationship")

    return {
        "status": "success",
        "message": summary,
        "node_count": node_count,
        "relationship_count": rel_count,
    }
