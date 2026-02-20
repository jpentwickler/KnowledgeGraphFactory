"""
Unit tests for US018: Project Management

Tests:
- _validate_project_name (6 tests)
- _detect_stage (6 tests)
- _get_state_file (4 tests)
- _check_project_active (3 tests)
- _parse_project_command (8 tests)
- _project_list (4 tests)
- _project_create (4 tests)
- _project_open (3 tests)
- _project_status (2 tests)
- _run_kg_project dispatch (5 tests)
- query_server._get_state_file (3 tests)
"""

import json
import os
import pytest
from unittest.mock import patch


# =============================================================================
# Helpers
# =============================================================================

def _reset_active_project():
    """Reset module-level _active_project to None."""
    import mcp_server.server as srv
    srv._active_project = None


def _write_state(path, state):
    """Write a state dict as JSON."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f)


# =============================================================================
# TestValidateProjectName
# =============================================================================

class TestValidateProjectName:
    def setup_method(self):
        _reset_active_project()

    def test_valid_simple(self):
        from mcp_server.server import _validate_project_name
        assert _validate_project_name("my_project") is None

    def test_valid_with_hyphens(self):
        from mcp_server.server import _validate_project_name
        assert _validate_project_name("my-project-v2") is None

    def test_valid_alphanumeric(self):
        from mcp_server.server import _validate_project_name
        assert _validate_project_name("Project123") is None

    def test_rejects_path_traversal(self):
        from mcp_server.server import _validate_project_name
        assert _validate_project_name("../evil") is not None
        assert _validate_project_name("foo/bar") is not None
        assert _validate_project_name("foo\\bar") is not None

    def test_rejects_spaces(self):
        from mcp_server.server import _validate_project_name
        assert _validate_project_name("my project") is not None

    def test_rejects_special_chars(self):
        from mcp_server.server import _validate_project_name
        assert _validate_project_name("my@project") is not None
        assert _validate_project_name("project!") is not None

    def test_rejects_empty(self):
        from mcp_server.server import _validate_project_name
        assert _validate_project_name("") is not None


# =============================================================================
# TestDetectStage
# =============================================================================

class TestDetectStage:
    def test_empty_state(self):
        from mcp_server.server import _detect_stage
        assert _detect_stage({}) == "new"

    def test_goal_defined(self):
        from mcp_server.server import _detect_stage
        assert _detect_stage({"approved_user_goal": {"description": "test"}}) == "goal defined"

    def test_files_selected(self):
        from mcp_server.server import _detect_stage
        state = {"approved_user_goal": {}, "approved_files": {"structured": []}}
        assert _detect_stage(state) == "files selected"

    def test_schema_approved(self):
        from mcp_server.server import _detect_stage
        state = {
            "approved_user_goal": {"description": "test"},
            "approved_files": {"structured": ["a.csv"]},
            "approved_construction_plan": {"Product": {"construction_type": "node"}},
        }
        assert _detect_stage(state) == "schema approved"

    def test_graph_built(self):
        from mcp_server.server import _detect_stage
        state = {"text_graph_progress": {"some_file": "done"}}
        assert _detect_stage(state) == "graph built"

    def test_evaluated(self):
        from mcp_server.server import _detect_stage
        state = {"cq_evaluation_results": {"coverage": 0.8}}
        assert _detect_stage(state) == "evaluated"


# =============================================================================
# TestGetStateFile
# =============================================================================

class TestGetStateFile:
    def setup_method(self):
        _reset_active_project()

    def test_default_path(self):
        from mcp_server.server import _get_state_file
        with patch.dict(os.environ, {}, clear=True):
            # Remove KG_BASE_DIR and KG_STATE_DIR
            os.environ.pop("KG_BASE_DIR", None)
            os.environ.pop("KG_STATE_DIR", None)
            result = _get_state_file()
            assert result == os.path.join("state", "current_state.json")

    def test_kg_state_dir(self):
        from mcp_server.server import _get_state_file
        with patch.dict(os.environ, {"KG_STATE_DIR": "/custom/state"}, clear=False):
            os.environ.pop("KG_BASE_DIR", None)
            result = _get_state_file()
            assert result == os.path.join("/custom/state", "current_state.json")

    def test_kg_base_dir_without_active_project(self):
        from mcp_server.server import _get_state_file
        import mcp_server.server as srv
        srv._active_project = None
        with patch.dict(os.environ, {"KG_BASE_DIR": "/base"}, clear=False):
            os.environ.pop("KG_STATE_DIR", None)
            result = _get_state_file()
            # Falls back to default since no active project
            assert result == os.path.join("state", "current_state.json")

    def test_kg_base_dir_with_active_project(self):
        from mcp_server.server import _get_state_file
        import mcp_server.server as srv
        srv._active_project = "my_project"
        with patch.dict(os.environ, {"KG_BASE_DIR": "/base"}, clear=False):
            result = _get_state_file()
            assert result == os.path.join("/base", "my_project", "state", "current_state.json")
        srv._active_project = None


# =============================================================================
# TestCheckProjectActive
# =============================================================================

class TestCheckProjectActive:
    def setup_method(self):
        _reset_active_project()

    def test_no_base_dir_returns_none(self):
        from mcp_server.server import _check_project_active
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KG_BASE_DIR", None)
            assert _check_project_active() is None

    def test_base_dir_with_active_project_returns_none(self):
        from mcp_server.server import _check_project_active
        import mcp_server.server as srv
        srv._active_project = "test_proj"
        with patch.dict(os.environ, {"KG_BASE_DIR": "/base"}, clear=False):
            assert _check_project_active() is None
        srv._active_project = None

    def test_base_dir_without_active_project_returns_error(self):
        from mcp_server.server import _check_project_active
        import mcp_server.server as srv
        srv._active_project = None
        with patch.dict(os.environ, {"KG_BASE_DIR": "/base"}, clear=False):
            result = _check_project_active()
            assert result is not None
            assert "no_active_project" in str(result["status"])


# =============================================================================
# TestParseProjectCommand
# =============================================================================

class TestParseProjectCommand:
    def test_list(self):
        from mcp_server.server import _parse_project_command
        assert _parse_project_command("list") == ("list", "")

    def test_ls(self):
        from mcp_server.server import _parse_project_command
        assert _parse_project_command("ls") == ("list", "")

    def test_status(self):
        from mcp_server.server import _parse_project_command
        assert _parse_project_command("status") == ("status", "")

    def test_info(self):
        from mcp_server.server import _parse_project_command
        assert _parse_project_command("info") == ("status", "")

    def test_create(self):
        from mcp_server.server import _parse_project_command
        assert _parse_project_command("create my_project") == ("create", "my_project")

    def test_new(self):
        from mcp_server.server import _parse_project_command
        assert _parse_project_command("new my_project") == ("create", "my_project")

    def test_open(self):
        from mcp_server.server import _parse_project_command
        assert _parse_project_command("open my_project") == ("open", "my_project")

    def test_unknown(self):
        from mcp_server.server import _parse_project_command
        cmd, arg = _parse_project_command("something else")
        assert cmd == "unknown"

    def test_create_preserves_case(self):
        from mcp_server.server import _parse_project_command
        assert _parse_project_command("Create My_Project") == ("create", "My_Project")


# =============================================================================
# TestProjectList
# =============================================================================

class TestProjectList:
    def setup_method(self):
        _reset_active_project()

    def test_empty_base_dir(self, tmp_path):
        from mcp_server.server import _project_list
        result = _project_list(str(tmp_path))
        assert "No projects found" in result["agent_response"]
        assert result["status"]["projects"] == []

    def test_multiple_projects(self, tmp_path):
        from mcp_server.server import _project_list

        # Create two projects
        proj1 = tmp_path / "alpha"
        (proj1 / "state").mkdir(parents=True)
        (proj1 / "data").mkdir()
        _write_state(str(proj1 / "state" / "current_state.json"), {"approved_user_goal": {"description": "test"}})

        proj2 = tmp_path / "beta"
        (proj2 / "state").mkdir(parents=True)
        (proj2 / "data").mkdir()
        _write_state(str(proj2 / "state" / "current_state.json"), {})

        result = _project_list(str(tmp_path))
        projects = result["status"]["projects"]
        assert len(projects) == 2
        assert projects[0]["name"] == "alpha"
        assert projects[0]["stage"] == "goal defined"
        assert projects[1]["name"] == "beta"
        assert projects[1]["stage"] == "new"

    def test_skips_non_project_dirs(self, tmp_path):
        from mcp_server.server import _project_list

        # Dir without state/ or data/ is not a project
        (tmp_path / "random_dir").mkdir()
        # File is not a project
        (tmp_path / "some_file.txt").write_text("hi")

        # Real project
        proj = tmp_path / "real"
        (proj / "data").mkdir(parents=True)

        result = _project_list(str(tmp_path))
        projects = result["status"]["projects"]
        assert len(projects) == 1
        assert projects[0]["name"] == "real"

    def test_counts_data_files(self, tmp_path):
        from mcp_server.server import _project_list

        proj = tmp_path / "proj"
        (proj / "state").mkdir(parents=True)
        data = proj / "data"
        data.mkdir()
        (data / "file1.csv").write_text("a,b\n1,2")
        (data / "file2.md").write_text("# test")
        (data / "ignored.txt").write_text("not counted")

        result = _project_list(str(tmp_path))
        assert result["status"]["projects"][0]["data_files"] == 2


# =============================================================================
# TestProjectCreate
# =============================================================================

class TestProjectCreate:
    def setup_method(self):
        _reset_active_project()

    def test_create_success(self, tmp_path):
        from mcp_server.server import _project_create
        import mcp_server.server as srv

        with patch.dict(os.environ, {"KG_BASE_DIR": str(tmp_path)}):
            result = _project_create("new_proj", str(tmp_path))

        assert "created" in result["agent_response"].lower()
        assert result["status"]["created"] == "new_proj"
        assert srv._active_project == "new_proj"
        assert (tmp_path / "new_proj" / "state").is_dir()
        assert (tmp_path / "new_proj" / "data").is_dir()
        srv._active_project = None

    def test_create_already_exists(self, tmp_path):
        from mcp_server.server import _project_create

        (tmp_path / "existing").mkdir()
        result = _project_create("existing", str(tmp_path))
        assert "already exists" in result["agent_response"]
        assert result["status"]["error"] == "already_exists"

    def test_create_invalid_name(self, tmp_path):
        from mcp_server.server import _project_create

        result = _project_create("bad name", str(tmp_path))
        assert result["status"]["error"] == "invalid_name"

    def test_create_writes_marker(self, tmp_path):
        from mcp_server.server import _project_create
        import mcp_server.server as srv

        with patch.dict(os.environ, {"KG_BASE_DIR": str(tmp_path)}):
            _project_create("test_proj", str(tmp_path))

        marker = tmp_path / "_last_active_project"
        assert marker.exists()
        assert marker.read_text().strip() == "test_proj"
        srv._active_project = None


# =============================================================================
# TestProjectOpen
# =============================================================================

class TestProjectOpen:
    def setup_method(self):
        _reset_active_project()

    def test_open_success(self, tmp_path):
        from mcp_server.server import _project_open
        import mcp_server.server as srv

        proj = tmp_path / "my_proj"
        (proj / "state").mkdir(parents=True)
        (proj / "data").mkdir()
        _write_state(
            str(proj / "state" / "current_state.json"),
            {"approved_user_goal": {"description": "test goal"}},
        )

        with patch.dict(os.environ, {"KG_BASE_DIR": str(tmp_path)}):
            result = _project_open("my_proj", str(tmp_path))

        assert "Opened" in result["agent_response"]
        assert result["status"]["stage"] == "goal defined"
        assert srv._active_project == "my_proj"
        srv._active_project = None

    def test_open_not_found(self, tmp_path):
        from mcp_server.server import _project_open

        result = _project_open("nonexistent", str(tmp_path))
        assert "not found" in result["agent_response"]
        assert result["status"]["error"] == "not_found"

    def test_open_shows_artifacts(self, tmp_path):
        from mcp_server.server import _project_open
        import mcp_server.server as srv

        proj = tmp_path / "full_proj"
        (proj / "state").mkdir(parents=True)
        (proj / "data").mkdir()
        _write_state(
            str(proj / "state" / "current_state.json"),
            {
                "approved_user_goal": {"description": "build a supply chain graph"},
                "approved_files": {"structured": [{"path": "a.csv"}], "unstructured": []},
                "approved_construction_plan": {"Product": {}, "Supplier": {}},
            },
        )

        with patch.dict(os.environ, {"KG_BASE_DIR": str(tmp_path)}):
            result = _project_open("full_proj", str(tmp_path))

        assert "Schema: 2 entries" in result["agent_response"]
        assert result["status"]["stage"] == "schema approved"
        srv._active_project = None


# =============================================================================
# TestProjectStatus
# =============================================================================

class TestProjectStatus:
    def setup_method(self):
        _reset_active_project()

    def test_no_active_project(self, tmp_path):
        from mcp_server.server import _project_status

        result = _project_status(str(tmp_path))
        assert "No project selected" in result["agent_response"]
        assert result["status"]["active_project"] is None

    def test_active_project(self, tmp_path):
        from mcp_server.server import _project_status
        import mcp_server.server as srv

        proj = tmp_path / "active_proj"
        (proj / "state").mkdir(parents=True)
        (proj / "data").mkdir()
        _write_state(str(proj / "state" / "current_state.json"), {})

        srv._active_project = "active_proj"
        with patch.dict(os.environ, {"KG_BASE_DIR": str(tmp_path)}):
            result = _project_status(str(tmp_path))

        assert "active_proj" in result["agent_response"]
        assert result["status"]["active_project"] == "active_proj"
        srv._active_project = None


# =============================================================================
# TestRunKgProject
# =============================================================================

class TestRunKgProject:
    def setup_method(self):
        _reset_active_project()

    def test_no_base_dir(self):
        from mcp_server.server import _run_kg_project
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KG_BASE_DIR", None)
            result = _run_kg_project("list")
            assert "KG_BASE_DIR not set" in result["agent_response"]

    def test_dispatch_list(self, tmp_path):
        from mcp_server.server import _run_kg_project
        with patch.dict(os.environ, {"KG_BASE_DIR": str(tmp_path)}):
            result = _run_kg_project("list")
            assert "projects" in result["status"]

    def test_dispatch_create(self, tmp_path):
        from mcp_server.server import _run_kg_project
        import mcp_server.server as srv
        with patch.dict(os.environ, {"KG_BASE_DIR": str(tmp_path)}):
            result = _run_kg_project("create test123")
            assert result["status"].get("created") == "test123"
        srv._active_project = None

    def test_dispatch_status(self, tmp_path):
        from mcp_server.server import _run_kg_project
        with patch.dict(os.environ, {"KG_BASE_DIR": str(tmp_path)}):
            result = _run_kg_project("status")
            assert "active_project" in result["status"]

    def test_dispatch_unknown(self, tmp_path):
        from mcp_server.server import _run_kg_project
        with patch.dict(os.environ, {"KG_BASE_DIR": str(tmp_path)}):
            result = _run_kg_project("foobar")
            assert result["status"]["error"] == "unknown_command"


# =============================================================================
# TestCountDataFiles
# =============================================================================

class TestCountDataFiles:
    def test_nonexistent_dir(self):
        from mcp_server.server import _count_data_files
        assert _count_data_files("/nonexistent/path") == 0

    def test_counts_csv_and_md(self, tmp_path):
        from mcp_server.server import _count_data_files
        (tmp_path / "a.csv").write_text("x")
        (tmp_path / "b.md").write_text("y")
        (tmp_path / "c.markdown").write_text("z")
        (tmp_path / "d.txt").write_text("skip")
        assert _count_data_files(str(tmp_path)) == 3

    def test_counts_nested_files(self, tmp_path):
        from mcp_server.server import _count_data_files
        sub = tmp_path / "reviews"
        sub.mkdir()
        (sub / "review.md").write_text("test")
        (tmp_path / "products.csv").write_text("a,b")
        assert _count_data_files(str(tmp_path)) == 2


# =============================================================================
# TestQueryServerGetStateFile
# =============================================================================

class TestQueryServerGetStateFile:
    def test_default(self):
        from mcp_server.query_server import _get_state_file
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KG_BASE_DIR", None)
            os.environ.pop("KG_STATE_DIR", None)
            assert _get_state_file() == os.path.join("state", "current_state.json")

    def test_kg_state_dir(self):
        from mcp_server.query_server import _get_state_file
        with patch.dict(os.environ, {"KG_STATE_DIR": "/custom"}, clear=False):
            os.environ.pop("KG_BASE_DIR", None)
            assert _get_state_file() == os.path.join("/custom", "current_state.json")

    def test_reads_marker(self, tmp_path):
        from mcp_server.query_server import _get_state_file

        marker = tmp_path / "_last_active_project"
        marker.write_text("my_proj")

        with patch.dict(os.environ, {"KG_BASE_DIR": str(tmp_path)}, clear=False):
            result = _get_state_file()
            assert result == os.path.join(str(tmp_path), "my_proj", "state", "current_state.json")
