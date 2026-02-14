"""Centralized LangSmith tracing imports for KG-Factory.

Provides graceful fallbacks when langsmith is not installed.
All other modules import traceable and wrap_anthropic from here.

Tracing activates only when:
1. langsmith package is installed
2. LANGSMITH_TRACING=true is set in environment
"""

import inspect

try:
    from langsmith import traceable
    from langsmith.wrappers import wrap_anthropic
except ImportError:
    # langsmith not installed -- provide no-op fallbacks

    def traceable(*args, **kwargs):
        """No-op decorator when langsmith is not installed."""
        def decorator(func):
            return func
        # Support both @traceable and @traceable(...) usage
        if args and callable(args[0]):
            return args[0]
        return decorator

    def wrap_anthropic(client, **kwargs):
        """No-op passthrough when langsmith is not installed."""
        return client


def mcp_traceable(name):
    """Apply @traceable while preserving the original function signature.

    langsmith's @traceable injects a ``config`` keyword-only parameter into
    the decorated function's signature. When stacked with FastMCP's
    ``@mcp.tool``, that extra parameter leaks into the MCP tool schema and
    can cause the agent to stall.

    This wrapper applies @traceable normally (tracing still works at runtime)
    then restores the original signature so @mcp.tool only sees the real
    parameters.
    """
    def decorator(func):
        original_sig = inspect.signature(func)
        traced = traceable(name=name)(func)
        traced.__signature__ = original_sig
        return traced
    return decorator


__all__ = ["traceable", "wrap_anthropic", "mcp_traceable"]
