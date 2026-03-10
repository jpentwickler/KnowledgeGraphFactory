"""Tests for scripts/generate_plugin.py."""

import json
import os
import sys

import pytest

# Add project root to path so we can import the script
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
)

from generate_plugin import PLUGIN_JSON, build_mcp_json, find_skill_md, generate


class TestBuildMcpJson:
    """Tests for .mcp.json generation."""

    def test_url_appears_in_config(self):
        result = build_mcp_json("https://example.com/mcp", None)
        assert result["mcpServers"]["domain-kg"]["url"] == "https://example.com/mcp"

    def test_type_is_http(self):
        result = build_mcp_json("https://example.com/mcp", None)
        assert result["mcpServers"]["domain-kg"]["type"] == "http"

    def test_placeholder_token_when_no_token(self):
        result = build_mcp_json("https://example.com/mcp", None)
        headers = result["mcpServers"]["domain-kg"]["headers"]
        assert headers["Authorization"] == "Bearer ${KG_QUERY_TOKEN}"

    def test_baked_token_when_provided(self):
        result = build_mcp_json("https://example.com/mcp", "secret123")
        headers = result["mcpServers"]["domain-kg"]["headers"]
        assert headers["Authorization"] == "Bearer secret123"

    def test_server_name_is_domain_kg(self):
        result = build_mcp_json("https://example.com/mcp", None)
        assert "domain-kg" in result["mcpServers"]


class TestFindSkillMd:
    """Tests for SKILL.md source resolution."""

    def test_finds_skill_md(self):
        path = find_skill_md()
        assert os.path.isfile(path)
        assert path.endswith("SKILL.md")


class TestGenerate:
    """Tests for full plugin generation."""

    def test_creates_directory_structure(self, tmp_path):
        output = str(tmp_path / "test-plugin")
        generate("https://example.com/mcp", None, output)

        assert os.path.isdir(os.path.join(output, ".claude-plugin"))
        assert os.path.isdir(os.path.join(output, "skills", "knowledge-graph"))

    def test_plugin_json_format(self, tmp_path):
        output = str(tmp_path / "test-plugin")
        generate("https://example.com/mcp", None, output)

        with open(os.path.join(output, ".claude-plugin", "plugin.json")) as f:
            data = json.load(f)

        assert data["name"] == "kg-query"
        assert data["version"] == "1.0.0"
        assert isinstance(data["author"], dict)
        assert data["author"]["name"] == "KG-Factory"
        assert "claude_plugin_version" not in data

    def test_mcp_json_with_url(self, tmp_path):
        output = str(tmp_path / "test-plugin")
        generate("https://my-server.railway.app/mcp", None, output)

        with open(os.path.join(output, ".mcp.json")) as f:
            data = json.load(f)

        assert data["mcpServers"]["domain-kg"]["url"] == "https://my-server.railway.app/mcp"

    def test_mcp_json_placeholder_token(self, tmp_path):
        output = str(tmp_path / "test-plugin")
        generate("https://example.com/mcp", None, output)

        with open(os.path.join(output, ".mcp.json")) as f:
            data = json.load(f)

        auth = data["mcpServers"]["domain-kg"]["headers"]["Authorization"]
        assert auth == "Bearer ${KG_QUERY_TOKEN}"

    def test_mcp_json_baked_token(self, tmp_path):
        output = str(tmp_path / "test-plugin")
        generate("https://example.com/mcp", "my-secret", output)

        with open(os.path.join(output, ".mcp.json")) as f:
            data = json.load(f)

        auth = data["mcpServers"]["domain-kg"]["headers"]["Authorization"]
        assert auth == "Bearer my-secret"

    def test_skill_md_copied(self, tmp_path):
        output = str(tmp_path / "test-plugin")
        generate("https://example.com/mcp", None, output)

        skill_path = os.path.join(output, "skills", "knowledge-graph", "SKILL.md")
        assert os.path.isfile(skill_path)

        with open(skill_path) as f:
            content = f.read()
        assert "kg_query" in content
        assert "kg_graph_info" in content

    def test_overwrite_existing_output(self, tmp_path):
        output = str(tmp_path / "test-plugin")

        # Generate twice - second should overwrite cleanly
        generate("https://first.com/mcp", None, output)
        generate("https://second.com/mcp", "token2", output)

        with open(os.path.join(output, ".mcp.json")) as f:
            data = json.load(f)

        assert data["mcpServers"]["domain-kg"]["url"] == "https://second.com/mcp"

    def test_returns_output_path(self, tmp_path):
        output = str(tmp_path / "test-plugin")
        result = generate("https://example.com/mcp", None, output)
        assert result == output
