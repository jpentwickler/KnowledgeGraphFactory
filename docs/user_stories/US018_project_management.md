# US018: Project Management

## User Story

**As a** KG-Factory user running the construction pipeline from Claude Cowork (or any MCP host)
**I want** to manage multiple knowledge graph projects without changing environment variables or config files between projects
**So that** I can configure the MCP server once and switch between projects entirely through conversation

## Story Points: 5

## Status: Not Started

## Context

Today, `KG_STATE_DIR` and `KG_DATA_DIR` are set per-project in the MCP host config (`claude_desktop_config.json`, `.mcp.json`). Starting a new project means editing the config and restarting the server. This is acceptable for a single project in Claude Code but doesn't scale to Cowork where a user wants to build many knowledge graphs over time without touching config files.

The solution: a single `KG_BASE_DIR` configured once, with project selection happening at runtime through a single `kg_project` MCP tool.

## Directory Layout

```
KG_BASE_DIR/                         # Set once in config, never changes
  furniture_supply_chain/
    state/current_state.json         # Pipeline state for this project
    data/                            # CSV and markdown files
      products.csv
      suppliers.csv
      reviews/
        stockholm_chair_reviews.md
  social_network/
    state/current_state.json
    data/
      users.csv
      posts.csv
      comments.md
```

## Acceptance Criteria

### kg_project MCP Tool

Single tool that manages project lifecycle via the `message` parameter:

- [ ] Tool signature: `kg_project(message: str) -> dict`
- [ ] Tool description: "Manage KG-Factory projects. Use 'list' to see projects, 'create <name>' to start a new one, 'open <name>' to switch to an existing one, 'status' to see the active project."
- [ ] Decorated with `@mcp.tool` and `@mcp_traceable(name="mcp.kg_project")`
- [ ] Returns error with guidance if `KG_BASE_DIR` is not set

#### Commands

**`list`** — List available projects

- [ ] Scans `KG_BASE_DIR` for subdirectories that contain a `state/` or `data/` subfolder
- [ ] Returns project names with status summary (has state, has data, pipeline stage)
- [ ] Shows currently active project (if any)
- [ ] Response format:
  ```
  Available projects:
    1. furniture_supply_chain (graph built, 6 data files)
    2. social_network (new, 3 data files)

  Active project: furniture_supply_chain
  ```

**`create <name>`** — Create a new project

- [ ] Parses project name from message (e.g., `"create furniture_v2"`)
- [ ] Validates name: no path traversal (`..`, `/`, `\`), no spaces, alphanumeric + underscores + hyphens only
- [ ] Creates `{KG_BASE_DIR}/{name}/state/` and `{KG_BASE_DIR}/{name}/data/`
- [ ] Sets the session-scoped active project to `name`
- [ ] Clears any in-memory agent conversations from a previous project
- [ ] Returns confirmation with the data directory path for the user to place files
- [ ] Returns error if project already exists (suggests `open` instead)

**`open <name>`** — Open an existing project

- [ ] Parses project name from message (e.g., `"open furniture_supply_chain"`)
- [ ] Validates that `{KG_BASE_DIR}/{name}/` exists
- [ ] Sets the session-scoped active project to `name`
- [ ] Clears any in-memory agent conversations from a previous project
- [ ] Loads state and returns summary (approved artifacts, pipeline stage, data file count)
- [ ] Returns error if project doesn't exist (suggests `create` instead)

**`status`** — Show active project info

- [ ] Returns active project name, pipeline stage, approved artifacts, data file count
- [ ] Returns "No project selected" with guidance if none active

**Unrecognized command** — Help text

- [ ] Returns usage guidance listing the four commands with examples

### Session-Scoped Project Context

- [ ] Module-level `_active_project: str | None = None` in `mcp_server/server.py`
- [ ] `_get_state_file() -> str` replaces the current `STATE_FILE` constant:
  - If `_active_project` is set and `KG_BASE_DIR` is set: `{KG_BASE_DIR}/{_active_project}/state/current_state.json`
  - Else if `KG_STATE_DIR` is set: `{KG_STATE_DIR}/current_state.json` (backwards compat)
  - Else: `state/current_state.json` (current default)
- [ ] All existing `_load_clean_state()` and `_save_state()` calls use `_get_state_file()` instead of the `STATE_FILE` constant
- [ ] `save_state` auto-creates parent directories (already does via `Path.mkdir(parents=True)`)

### Data Directory Override

When a project is activated (`create` or `open`), the tool sets `os.environ["KG_DATA_DIR"]` to `{KG_BASE_DIR}/{name}/data/`. This works because `tools/file_tools._get_data_dir()` already reads from `KG_DATA_DIR` at call time. No changes to `file_tools.py` needed.

- [ ] `kg_project("create ...")` sets `os.environ["KG_DATA_DIR"]`
- [ ] `kg_project("open ...")` sets `os.environ["KG_DATA_DIR"]`
- [ ] `_get_data_dir()` picks it up automatically (no code change)

### Pipeline Guard

- [ ] All existing `kg_*` agent tools (except `kg_project`, `kg_get_state`, `kg_reset_state`) check that a project is active before proceeding **only when `KG_BASE_DIR` is set**
- [ ] Guard function: `_check_project_active() -> dict | None`
  - Returns `None` if `KG_BASE_DIR` is not set (backwards compat, no guard)
  - Returns `None` if `_active_project` is set (project selected, proceed)
  - Returns error dict with guidance to call `kg_project` if `KG_BASE_DIR` is set but no project active
- [ ] Guard is called at the top of each agent tool; if it returns a dict, return that dict immediately

### Backwards Compatibility

- [ ] If `KG_BASE_DIR` is not set, all behavior is identical to today
- [ ] `KG_STATE_DIR` and `KG_DATA_DIR` still work as direct overrides
- [ ] Priority chain: active project (`KG_BASE_DIR` + name) > `KG_STATE_DIR`/`KG_DATA_DIR` > defaults
- [ ] No breaking changes to existing Claude Code workflows
- [ ] No changes needed to `claude_desktop_config.json` for existing users who don't set `KG_BASE_DIR`

### SKILL.md for Construction Pipeline

- [ ] Create `skills/knowledge-graph-builder/SKILL.md`
- [ ] Include the relay pattern instructions (pass messages through, don't interpret)
- [ ] Include the workflow sequence: `kg_project` -> `kg_user_intent` -> `kg_file_suggestion` -> `kg_schema_proposal` -> ...
- [ ] Reference `kg_project` as the starting point for every session
- [ ] Include note about placing data files in the project's `data/` directory

### Query Server Alignment

- [ ] `mcp_server/query_server.py` supports `KG_BASE_DIR` + project name for state loading
- [ ] Approach: `_load_state_once()` accepts an optional project name, or reads from `KG_BASE_DIR` + last-used project
- [ ] Alternatively: query server reads a `_last_active_project` file from `KG_BASE_DIR` written by the construction server

## Definition of Done

- [ ] Code implemented and working
- [ ] Unit tests for `kg_project` command parsing (list, create, open, status, unrecognized)
- [ ] Unit tests for `_get_state_file()` with all priority chain scenarios
- [ ] Unit tests for pipeline guard (error when no project active + `KG_BASE_DIR` set)
- [ ] Unit tests for project name validation (path traversal, spaces, special chars)
- [ ] All existing tests still pass (backwards compat verified)
- [ ] Interactive test: `tests/test_11_project_management.py`
- [ ] MCP tool works from Claude Cowork
- [ ] Construction SKILL.md written
- [ ] Observability: traces visible in LangSmith when enabled
- [ ] Code reviewed

## Technical Notes

### Architecture

```
kg_project(message)
  |
  +-> parse command from message (list | create | open | status)
  |
  +-> "list":
  |     +-> scan KG_BASE_DIR for project directories
  |     +-> for each: check state/data existence, summarize stage
  |     +-> return formatted list
  |
  +-> "create <name>":
  |     +-> validate name (no traversal, alphanumeric + _ + -)
  |     +-> mkdir {KG_BASE_DIR}/{name}/state/ and data/
  |     +-> set _active_project = name
  |     +-> set os.environ["KG_DATA_DIR"] = {KG_BASE_DIR}/{name}/data/
  |     +-> clear _conversations
  |     +-> return confirmation
  |
  +-> "open <name>":
  |     +-> validate directory exists
  |     +-> set _active_project = name
  |     +-> set os.environ["KG_DATA_DIR"] = {KG_BASE_DIR}/{name}/data/
  |     +-> clear _conversations
  |     +-> load state, summarize pipeline stage
  |     +-> return summary
  |
  +-> "status":
        +-> return active project info or "no project selected"
```

### State File Resolution

```python
def _get_state_file() -> str:
    """Resolve the state file path based on active project or env vars."""
    base_dir = os.environ.get("KG_BASE_DIR")

    if base_dir and _active_project:
        return os.path.join(base_dir, _active_project, "state", "current_state.json")

    state_dir = os.environ.get("KG_STATE_DIR", "state")
    return os.path.join(state_dir, "current_state.json")
```

### Command Parsing

Simple keyword-based parsing, no Claude agent needed:

```python
def _parse_project_command(message: str) -> tuple[str, str]:
    """Parse command and argument from message.

    Returns:
        (command, argument) tuple. command is one of:
        'list', 'create', 'open', 'status', 'unknown'.
    """
    msg = message.strip().lower()

    if msg in ("list", "ls"):
        return ("list", "")
    if msg in ("status", "info"):
        return ("status", "")
    if msg.startswith("create "):
        return ("create", message.strip()[7:].strip())
    if msg.startswith("new "):
        return ("new", message.strip()[4:].strip())
    if msg.startswith("open "):
        return ("open", message.strip()[5:].strip())

    return ("unknown", message)
```

### Pipeline Stage Detection

For `list` and `status` responses, derive pipeline stage from state:

```python
def _detect_stage(state: dict) -> str:
    """Determine how far the pipeline has progressed."""
    if state.get("cq_evaluation_results"):
        return "evaluated"
    if state.get("text_graph_progress"):
        return "graph built"
    if state.get("approved_construction_plan"):
        return "schema approved"
    if state.get("approved_files"):
        return "files selected"
    if state.get("approved_user_goal"):
        return "goal defined"
    return "new"
```

### Files to Create

```
tests/
  test_11_project_management.py     # NEW: Interactive test
  unit/
    test_project_management.py      # NEW: Unit tests

skills/
  knowledge-graph-builder/
    SKILL.md                        # NEW: Construction pipeline skill for Cowork
```

### Files to Modify

```
mcp_server/server.py               # UPDATE: Add kg_project tool,
                                    #         _active_project, _get_state_file(),
                                    #         _check_project_active() guard,
                                    #         replace STATE_FILE with _get_state_file()

mcp_server/query_server.py          # UPDATE: Support KG_BASE_DIR for state loading
```

### Example claude_desktop_config.json (set once, never change)

```json
{
  "mcpServers": {
    "kg-factory": {
      "command": "C:\\Users\\jprob\\anaconda3\\envs\\base1\\python.exe",
      "args": ["-m", "mcp_server.server"],
      "env": {
        "PYTHONPATH": "C:\\Users\\jprob\\Documents\\Personal\\VisualStudio\\KnowledgeGraphFactory",
        "KG_BASE_DIR": "C:\\Users\\jprob\\Documents\\KGProjects",
        "ANTHROPIC_API_KEY": "...",
        "NEO4J_URI": "...",
        "NEO4J_USER": "...",
        "NEO4J_PASSWORD": "...",
        "OPENAI_API_KEY": "..."
      }
    }
  }
}
```

### Example Cowork Conversation

```
User: I want to build a knowledge graph for my furniture supply chain data

Cowork: [calls kg_project("list")]

        Available projects:
          1. furniture_supply_chain (graph built, 6 data files)
          2. social_network (new, 3 data files)

        No project selected. Would you like to open an existing project
        or create a new one?

User: Create a new project called furniture_v2

Cowork: [calls kg_project("create furniture_v2")]

        Project "furniture_v2" created.
          State: C:\Users\jprob\Documents\KGProjects\furniture_v2\state\
          Data:  C:\Users\jprob\Documents\KGProjects\furniture_v2\data\

        Place your CSV and markdown files in the data directory,
        then we can start defining your graph goal.

User: I've added the files. Let's define the goal.

Cowork: [calls kg_user_intent("I want to build a supply chain knowledge graph...")]
        ... pipeline continues normally ...
```

## Dependencies

- Existing `core/state.py` (load_state, save_state — no changes needed)
- Existing `tools/file_tools.py` (_get_data_dir — no changes needed, reads KG_DATA_DIR at call time)
- Existing `mcp_server/server.py` (all existing tools)
- Existing `core/tracing.py` (observability)

## Out of Scope

- Project deletion (manual filesystem operation — `rm -rf` the directory)
- Project export/import (copy directories manually)
- Multi-user project sharing (single-user tool)
- Project-level Neo4j database isolation (all projects share the same Neo4j instance)
- Git-based project versioning
- Project templates (future enhancement)
- Renaming projects (rename the directory manually)
- Data file upload through the tool (user places files on disk or through Cowork UI)
