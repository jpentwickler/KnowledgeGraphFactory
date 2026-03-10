#!/usr/bin/env python
"""Generate a distributable Cowork plugin for a KG-Factory query server.

Creates a self-contained plugin directory that end users can upload to
Cowork (Plugins > "+" > select folder) for zero-config graph querying.

Usage:
    python scripts/generate_plugin.py --url https://my-server.up.railway.app/mcp
    python scripts/generate_plugin.py --url https://my-server.up.railway.app/mcp --token secret123
    python scripts/generate_plugin.py --url https://my-server.up.railway.app/mcp --output dist/my-plugin
"""

import argparse
import json
import os
import shutil
import sys


PLUGIN_JSON = {
    "name": "kg-query",
    "version": "1.0.0",
    "description": "Query knowledge graphs built with KG-Factory",
    "author": {"name": "KG-Factory"},
    "keywords": ["knowledge-graph", "neo4j", "query"],
}


def build_mcp_json(url: str, token: str | None) -> dict:
    """Build .mcp.json config with the deployment URL and optional token."""
    server_config: dict = {
        "type": "http",
        "url": url,
    }
    if token:
        server_config["headers"] = {
            "Authorization": f"Bearer {token}",
        }
    else:
        server_config["headers"] = {
            "Authorization": "Bearer ${KG_QUERY_TOKEN}",
        }
    return {"mcpServers": {"domain-kg": server_config}}


def find_skill_md() -> str:
    """Resolve the path to the source SKILL.md."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_path = os.path.join(
        script_dir, "..", "skills", "knowledge-graph", "SKILL.md"
    )
    skill_path = os.path.normpath(skill_path)
    if not os.path.isfile(skill_path):
        print(f"Error: SKILL.md not found at {skill_path}", file=sys.stderr)
        sys.exit(1)
    return skill_path


def generate(url: str, token: str | None, output: str) -> str:
    """Generate the plugin directory. Returns the output path."""
    # Resolve SKILL.md source
    skill_source = find_skill_md()

    # Create directory structure
    plugin_dir = os.path.join(output, ".claude-plugin")
    skill_dir = os.path.join(output, "skills", "knowledge-graph")
    os.makedirs(plugin_dir, exist_ok=True)
    os.makedirs(skill_dir, exist_ok=True)

    # Write plugin.json
    plugin_json_path = os.path.join(plugin_dir, "plugin.json")
    with open(plugin_json_path, "w", encoding="utf-8") as f:
        json.dump(PLUGIN_JSON, f, indent=2)
        f.write("\n")

    # Write .mcp.json
    mcp_json_path = os.path.join(output, ".mcp.json")
    mcp_config = build_mcp_json(url, token)
    with open(mcp_json_path, "w", encoding="utf-8") as f:
        json.dump(mcp_config, f, indent=2)
        f.write("\n")

    # Copy SKILL.md
    skill_dest = os.path.join(skill_dir, "SKILL.md")
    shutil.copy2(skill_source, skill_dest)

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Generate a Cowork plugin for a KG-Factory query server"
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Full MCP endpoint URL (e.g. https://my-server.up.railway.app/mcp)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Bake a literal bearer token into the plugin. "
        "If omitted, uses ${KG_QUERY_TOKEN} placeholder.",
    )
    parser.add_argument(
        "--output",
        default=os.path.join("dist", "kg-query-plugin"),
        help="Output directory (default: dist/kg-query-plugin)",
    )
    args = parser.parse_args()

    output = generate(args.url, args.token, args.output)

    # Summary
    print(f"Plugin generated at: {output}")
    print(f"  .claude-plugin/plugin.json")
    print(f"  .mcp.json (url: {args.url})")
    print(f"  skills/knowledge-graph/SKILL.md")
    if args.token:
        print(f"  Token: baked in (literal)")
    else:
        print(f"  Token: placeholder (${{KG_QUERY_TOKEN}})")


if __name__ == "__main__":
    main()
