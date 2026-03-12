#!/usr/bin/env python
"""Generate distributable plugin configs for KG-Factory query servers.

Supports two platforms:
- **Cowork** (default): Creates a .claude-plugin directory with plugin.json,
  .mcp.json, and SKILL.md that users upload via Cowork's plugin UI.
- **OpenClaw**: Creates an openclaw.json.example with mcp-adapter config,
  SKILL.md, and README for OpenClaw cloud deployments.

Usage:
    # Cowork plugin (default)
    python scripts/generate_plugin.py --url https://my-server.up.railway.app/mcp
    python scripts/generate_plugin.py --url https://my-server.up.railway.app/mcp --token secret123

    # OpenClaw config
    python scripts/generate_plugin.py --url https://my-server.up.railway.app/mcp --platform openclaw

    # Both platforms
    python scripts/generate_plugin.py --url https://my-server.up.railway.app/mcp --platform all
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


def build_openclaw_json(url: str, token: str | None) -> dict:
    """Build OpenClaw mcp-adapter config with the deployment URL and optional token."""
    auth_value = f"Bearer {token}" if token else "Bearer ${KG_QUERY_TOKEN}"
    return {
        "plugins": {
            "entries": {
                "mcp-adapter": {
                    "enabled": True,
                    "config": {
                        "toolPrefix": True,
                        "servers": [
                            {
                                "name": "domain-kg",
                                "transport": "http",
                                "url": url,
                                "headers": {
                                    "Authorization": auth_value,
                                },
                            }
                        ],
                    },
                }
            }
        }
    }


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


def find_openclaw_readme() -> str:
    """Resolve the path to the OpenClaw README.md."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    readme_path = os.path.join(
        script_dir, "..", "plugins", "openclaw-remote", "README.md"
    )
    readme_path = os.path.normpath(readme_path)
    if not os.path.isfile(readme_path):
        print(f"Error: README.md not found at {readme_path}", file=sys.stderr)
        sys.exit(1)
    return readme_path


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


def generate_openclaw(url: str, token: str | None, output: str) -> str:
    """Generate the OpenClaw config directory. Returns the output path."""
    # Resolve source files
    skill_source = find_skill_md()
    readme_source = find_openclaw_readme()

    # Create directory structure (no .claude-plugin for OpenClaw)
    skill_dir = os.path.join(output, "skills", "knowledge-graph")
    os.makedirs(skill_dir, exist_ok=True)

    # Write openclaw.json.example
    config_path = os.path.join(output, "openclaw.json.example")
    openclaw_config = build_openclaw_json(url, token)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(openclaw_config, f, indent=2)
        f.write("\n")

    # Copy SKILL.md
    skill_dest = os.path.join(skill_dir, "SKILL.md")
    shutil.copy2(skill_source, skill_dest)

    # Copy README.md
    readme_dest = os.path.join(output, "README.md")
    shutil.copy2(readme_source, readme_dest)

    return output


def _print_token_info(token: str | None):
    """Print token status line."""
    if token:
        print("  Token: baked in (literal)")
    else:
        print("  Token: placeholder (${KG_QUERY_TOKEN})")


def main():
    parser = argparse.ArgumentParser(
        description="Generate a plugin/config for a KG-Factory query server"
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Full MCP endpoint URL (e.g. https://my-server.up.railway.app/mcp)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Bake a literal bearer token into the config. "
        "If omitted, uses ${KG_QUERY_TOKEN} placeholder.",
    )
    parser.add_argument(
        "--platform",
        choices=["cowork", "openclaw", "all"],
        default="cowork",
        help="Target platform (default: cowork)",
    )
    parser.add_argument(
        "--output",
        default=os.path.join("dist", "kg-query-plugin"),
        help="Output directory (default: dist/kg-query-plugin)",
    )
    args = parser.parse_args()

    if args.platform == "cowork":
        output = generate(args.url, args.token, args.output)
        print(f"Cowork plugin generated at: {output}")
        print("  .claude-plugin/plugin.json")
        print(f"  .mcp.json (url: {args.url})")
        print("  skills/knowledge-graph/SKILL.md")
        _print_token_info(args.token)

    elif args.platform == "openclaw":
        output = generate_openclaw(args.url, args.token, args.output)
        print(f"OpenClaw config generated at: {output}")
        print(f"  openclaw.json.example (url: {args.url})")
        print("  skills/knowledge-graph/SKILL.md")
        print("  README.md")
        _print_token_info(args.token)

    elif args.platform == "all":
        cowork_output = os.path.join(args.output, "cowork")
        openclaw_output = os.path.join(args.output, "openclaw")

        generate(args.url, args.token, cowork_output)
        generate_openclaw(args.url, args.token, openclaw_output)

        print(f"All platforms generated at: {args.output}")
        print(f"  cowork/    - Cowork plugin")
        print(f"  openclaw/  - OpenClaw config")
        _print_token_info(args.token)


if __name__ == "__main__":
    main()
