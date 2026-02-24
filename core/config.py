"""Centralized configuration for KG-Factory.

Model constants are overridable via environment variables so users can
swap models without touching code (e.g., for cost optimization or
local LLM experiments).
"""

import os

# General-purpose model for agent loops, critic, query builder
CLAUDE_MODEL = os.environ.get("KG_CLAUDE_MODEL", "claude-sonnet-4-20250514")

# Model for structured-output calls (requires output_config support)
CLAUDE_MODEL_STRUCTURED = os.environ.get(
    "KG_CLAUDE_MODEL_STRUCTURED", "claude-sonnet-4-6"
)
