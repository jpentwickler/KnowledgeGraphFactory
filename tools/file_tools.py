"""Tool handlers for the File Suggestion Agent."""

import csv
import os

from core import (
    create_tool_schema,
    set_proposed,
    has_proposed,
    approve,
    get_approved,
    has_approved,
)


def _get_data_dir() -> str:
    """Resolve the data directory from environment variables or default."""
    return os.path.abspath(
        os.environ.get(
            "KG_DATA_DIR",
            os.environ.get("NEO4J_IMPORT_DIR", "./data"),
        )
    )


def _normalize_path(path: str) -> str:
    """Normalize path to use forward slashes for cross-platform consistency."""
    return path.replace("\\", "/")


# ---------------------------------------------------------------------------
# Tool Schemas
# ---------------------------------------------------------------------------

TOOL_GET_APPROVED_USER_GOAL = create_tool_schema(
    name="get_approved_user_goal",
    description=(
        "Retrieve the approved user goal from a previous stage. "
        "Call this FIRST to understand what the user wants to build."
    ),
    properties={},
    required=[],
)

TOOL_LIST_AVAILABLE_FILES = create_tool_schema(
    name="list_available_files",
    description=(
        "List files available in the data directory. "
        "Use file_type to filter: 'all' (default), 'csv', or 'markdown'."
    ),
    properties={
        "file_type": {
            "type": "string",
            "enum": ["all", "csv", "markdown"],
            "description": "Filter by file type: 'all', 'csv', or 'markdown'. Defaults to 'all'.",
        }
    },
    required=[],
)

TOOL_GET_FILE_INFO = create_tool_schema(
    name="get_file_info",
    description=(
        "Get metadata about a specific file. "
        "For CSV: column names, row count, size. "
        "For markdown: headings, line count, size."
    ),
    properties={
        "file_path": {
            "type": "string",
            "description": "Relative path to the file within the data directory (e.g. 'suppliers.csv').",
        }
    },
    required=["file_path"],
)

TOOL_SAMPLE_FILE = create_tool_schema(
    name="sample_file",
    description=(
        "Read the first N lines of a file to inspect its content. "
        "Use only when get_file_info is not enough to classify a file."
    ),
    properties={
        "file_path": {
            "type": "string",
            "description": "Relative path to the file within the data directory.",
        },
        "num_lines": {
            "type": "integer",
            "description": "Number of lines to read. Defaults to 100.",
        },
    },
    required=["file_path"],
)

TOOL_SET_PROPOSED_FILES = create_tool_schema(
    name="set_proposed_files",
    description=(
        "Save the proposed file classification. "
        "Structured files (CSV) go to 'structured', "
        "unstructured files (markdown) go to 'unstructured'. "
        "Each entry should include 'path' and 'reason'."
    ),
    properties={
        "structured": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative file path within the data directory.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this file is relevant to the user's goal.",
                    },
                },
                "required": ["path", "reason"],
            },
            "description": "List of structured (CSV) files with relevance explanations.",
        },
        "unstructured": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative file path within the data directory.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this file is relevant to the user's goal.",
                    },
                },
                "required": ["path", "reason"],
            },
            "description": "List of unstructured (markdown) files with relevance explanations.",
        },
    },
    required=["structured", "unstructured"],
)

TOOL_APPROVE_PROPOSED_FILES = create_tool_schema(
    name="approve_proposed_files",
    description=(
        "Approve the proposed file classification after the user explicitly confirms. "
        "Only use when user says 'approve', 'looks good', 'yes', or similar."
    ),
    properties={},
    required=[],
)


# ---------------------------------------------------------------------------
# Tool Handlers
# ---------------------------------------------------------------------------


def handle_get_approved_user_goal(state: dict) -> dict:
    """Retrieve the approved user goal from state.

    Args:
        state: Current state dictionary.

    Returns:
        Tool result with the approved goal, or error if not found.
    """
    if not has_approved(state, "user_goal"):
        return {
            "status": "error",
            "message": (
                "No approved user goal found. "
                "Stage 1 (User Intent) must be completed first."
            ),
        }

    goal = get_approved(state, "user_goal")
    return {
        "status": "success",
        "message": "Retrieved approved user goal.",
        "approved_goal": goal,
    }


def handle_list_available_files(state: dict, file_type: str = "all") -> dict:
    """List files in the data directory.

    Args:
        state: Current state dictionary (unused but required by pattern).
        file_type: Filter — 'all', 'csv', or 'markdown'.

    Returns:
        Tool result with sorted file list.
    """
    data_dir = _get_data_dir()

    if not os.path.isdir(data_dir):
        return {
            "status": "error",
            "message": f"Data directory not found: {data_dir}",
        }

    csv_exts = {".csv"}
    md_exts = {".md", ".markdown", ".txt"}

    files = []
    try:
        for root, _dirs, filenames in os.walk(data_dir):
            for fname in filenames:
                abs_path = os.path.join(root, fname)
                rel_path = os.path.relpath(abs_path, data_dir)
                rel_path = _normalize_path(rel_path)
                ext = os.path.splitext(fname)[1].lower()

                if file_type == "csv" and ext not in csv_exts:
                    continue
                if file_type == "markdown" and ext not in md_exts:
                    continue

                files.append(rel_path)
    except OSError as exc:
        return {
            "status": "error",
            "message": f"Error reading data directory: {exc}",
        }

    files.sort()
    return {
        "status": "success",
        "data_dir": _normalize_path(data_dir),
        "file_type": file_type,
        "count": len(files),
        "files": files,
    }


def handle_get_file_info(state: dict, file_path: str) -> dict:
    """Get metadata about a specific file.

    Args:
        state: Current state dictionary (unused).
        file_path: Relative path within the data directory.

    Returns:
        Tool result with file metadata.
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

    ext = os.path.splitext(abs_path)[1].lower()
    size_kb = round(os.path.getsize(abs_path) / 1024, 2)

    try:
        if ext == ".csv":
            return _csv_info(file_path, abs_path, size_kb)
        else:
            return _text_info(file_path, abs_path, size_kb)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Error reading file {file_path}: {exc}",
        }


def _csv_info(file_path: str, abs_path: str, size_kb: float) -> dict:
    """Extract metadata from a CSV file."""
    with open(abs_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader, [])
        row_count = sum(1 for _ in reader)

    return {
        "status": "success",
        "file_path": _normalize_path(file_path),
        "file_type": "csv",
        "size_kb": size_kb,
        "columns": headers,
        "row_count": row_count,
    }


def _text_info(file_path: str, abs_path: str, size_kb: float) -> dict:
    """Extract metadata from a text/markdown file."""
    headings = []
    line_count = 0

    with open(abs_path, "r", encoding="utf-8") as f:
        for line in f:
            line_count += 1
            stripped = line.strip()
            if stripped.startswith("#"):
                headings.append(stripped)

    return {
        "status": "success",
        "file_path": _normalize_path(file_path),
        "file_type": "markdown",
        "size_kb": size_kb,
        "headings": headings,
        "line_count": line_count,
    }


def handle_sample_file(state: dict, file_path: str, num_lines: int = 100) -> dict:
    """Read the first N lines of a file.

    Args:
        state: Current state dictionary (unused).
        file_path: Relative path within the data directory.
        num_lines: Number of lines to read (default 100).

    Returns:
        Tool result with file content preview.
    """
    data_dir = _get_data_dir()
    abs_path = os.path.join(data_dir, file_path)
    abs_path = os.path.abspath(abs_path)

    # Security check
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

    try:
        lines = []
        with open(abs_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= num_lines:
                    break
                lines.append(line.rstrip("\n"))

        return {
            "status": "success",
            "file_path": _normalize_path(file_path),
            "num_lines": len(lines),
            "content": "\n".join(lines),
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Error reading file {file_path}: {exc}",
        }


def handle_set_proposed_files(
    state: dict, structured: list, unstructured: list
) -> dict:
    """Save the proposed file classification.

    Args:
        state: Current state dictionary.
        structured: List of structured file entries (path + reason).
        unstructured: List of unstructured file entries (path + reason).

    Returns:
        Tool result dictionary.
    """
    proposal = {
        "structured": structured,
        "unstructured": unstructured,
    }

    set_proposed(state, "files", proposal)

    return {
        "status": "proposed",
        "message": (
            f"Proposed files saved: {len(structured)} structured, "
            f"{len(unstructured)} unstructured."
        ),
        "proposal": proposal,
    }


TOOL_GET_APPROVED_COMPETENCY_QUESTIONS = create_tool_schema(
    name="get_approved_competency_questions",
    description=(
        "Retrieve the approved competency questions. "
        "These define what the knowledge graph must be able to answer. "
        "Call this to understand what questions drive the file selection."
    ),
    properties={},
    required=[],
)


def handle_get_approved_competency_questions(state: dict) -> dict:
    """Retrieve approved competency questions from state.

    Args:
        state: Current state dictionary.

    Returns:
        Tool result with approved CQs, or message if none exist.
    """
    if not has_approved(state, "competency_questions"):
        return {
            "status": "success",
            "message": "No approved competency questions yet.",
            "approved_competency_questions": {},
        }

    cqs = get_approved(state, "competency_questions")
    return {
        "status": "success",
        "message": f"Retrieved {len(cqs)} approved competency questions.",
        "approved_competency_questions": cqs,
    }


def handle_approve_proposed_files(state: dict) -> dict:
    """Approve the proposed file classification.

    Args:
        state: Current state dictionary.

    Returns:
        Tool result dictionary.
    """
    if not has_proposed(state, "files"):
        return {
            "status": "error",
            "message": "No proposed files to approve. Please classify files first.",
        }

    approve(state, "files")
    approved = get_approved(state, "files")

    return {
        "status": "approved",
        "message": "Files approved! Ready for downstream agents.",
        "approved_files": approved,
    }
