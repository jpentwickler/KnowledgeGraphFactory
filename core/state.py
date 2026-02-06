"""State management for KG-Factory agents.

Provides load/save operations for state persistence and get/set operations
for managing proposed and approved artifacts.
"""

import json
from pathlib import Path
from typing import Any


def load_state(path: str) -> dict:
    """Load state from a JSON file.

    Args:
        path: Path to the JSON state file.

    Returns:
        State dictionary. Returns empty dict if file doesn't exist.
    """
    state_path = Path(path)
    if not state_path.exists():
        return {}

    with open(state_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_state(state: dict, path: str) -> None:
    """Save state to a JSON file.

    Args:
        state: State dictionary to save.
        path: Path to save the JSON state file.
    """
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)


def get_approved(state: dict, key: str) -> Any:
    """Get an approved artifact from state.

    Args:
        state: State dictionary.
        key: The artifact key (without 'approved_' prefix).

    Returns:
        The approved artifact value, or None if not found.
    """
    return state.get(f"approved_{key}")


def get_proposed(state: dict, key: str) -> Any:
    """Get a proposed artifact from state.

    Args:
        state: State dictionary.
        key: The artifact key (without 'proposed_' prefix).

    Returns:
        The proposed artifact value, or None if not found.
    """
    return state.get(f"proposed_{key}")


def set_proposed(state: dict, key: str, value: Any) -> None:
    """Set a proposed artifact in state.

    Args:
        state: State dictionary (modified in place).
        key: The artifact key (without 'proposed_' prefix).
        value: The value to set.
    """
    state[f"proposed_{key}"] = value


def approve(state: dict, key: str) -> None:
    """Approve a proposed artifact, copying it to approved status.

    Copies the value from proposed_{key} to approved_{key}.

    Args:
        state: State dictionary (modified in place).
        key: The artifact key (without prefix).

    Raises:
        KeyError: If no proposed artifact exists for the given key.
    """
    proposed_key = f"proposed_{key}"
    if proposed_key not in state:
        raise KeyError(f"No proposed artifact found for key: {key}")

    state[f"approved_{key}"] = state[proposed_key]


def has_approved(state: dict, key: str) -> bool:
    """Check if an approved artifact exists.

    Args:
        state: State dictionary.
        key: The artifact key (without 'approved_' prefix).

    Returns:
        True if the approved artifact exists.
    """
    return f"approved_{key}" in state


def has_proposed(state: dict, key: str) -> bool:
    """Check if a proposed artifact exists.

    Args:
        state: State dictionary.
        key: The artifact key (without 'proposed_' prefix).

    Returns:
        True if the proposed artifact exists.
    """
    return f"proposed_{key}" in state
