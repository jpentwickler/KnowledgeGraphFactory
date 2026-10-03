#!/usr/bin/env bash
# Python for US025, through uv: the repo requirements plus this prototype's, with no
# project venv (the repo has no pyproject.toml). Runs from the repo root, so
# `python -m prototypes.us025_virtual_domain.<module>` resolves from anywhere.
#
# Usage: prototypes/us025_virtual_domain/py.sh -m prototypes.us025_virtual_domain.<module> [args]
#        prototypes/us025_virtual_domain/py.sh -m pytest tests/unit/test_us025_virtual_domain.py
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
cd "$REPO"

exec uv run --no-project --python 3.13 \
  --with-requirements requirements.txt \
  --with-requirements prototypes/us025_virtual_domain/requirements.txt \
  python "$@"
