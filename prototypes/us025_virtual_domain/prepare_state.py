"""Write the prototype's own copy of the furniture pipeline state (US025).

The tracked ``state/current_state.json`` records a finished build: all 10 review
files in ``text_graph_progress`` and the entity-resolution candidates. A build
from an unmodified copy would process nothing. This keeps only what the text
build needs, so all 10 files are pending again. The shared file is only read.

Usage (from the repo root):
    prototypes/us025_virtual_domain/py.sh -m prototypes.us025_virtual_domain.prepare_state
"""

import json
from pathlib import Path

from prototypes.us025_virtual_domain.duckdb_domain import REPO_ROOT

SOURCE_STATE = REPO_ROOT / "state" / "current_state.json"
PROTOTYPE_STATE_DIR = Path(__file__).resolve().parent / "state"

# Everything else (text_graph_progress, *resolution_candidates, domain/text
# schemas, CQ results, agent conversations) is dropped.
KEEP_KEYS = ("approved_entity_types", "approved_fact_types", "approved_files")


def filtered_state(source: dict) -> dict:
    """The subset of ``source`` that the unstructured build reads."""
    missing = [k for k in KEEP_KEYS if k not in source]
    if missing:
        raise KeyError(f"Source state lacks {missing}")
    return {k: source[k] for k in KEEP_KEYS}


def prepare(source_path: Path = SOURCE_STATE, state_dir: Path = PROTOTYPE_STATE_DIR) -> Path:
    """Write ``state_dir/current_state.json`` from ``source_path``. Returns the path written."""
    state = filtered_state(json.loads(Path(source_path).read_text()))
    state_dir.mkdir(parents=True, exist_ok=True)
    target = state_dir / "current_state.json"
    target.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    return target


def main() -> None:
    target = prepare()
    files = json.loads(target.read_text())["approved_files"]["unstructured"]
    print(f"Wrote {target} from {SOURCE_STATE}")
    print(f"  kept: {', '.join(KEEP_KEYS)}")
    print(f"  review files pending: {len(files)}")


if __name__ == "__main__":
    main()
