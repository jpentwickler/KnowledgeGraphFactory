# US011: LangSmith Observability

## User Story

**As a** KG-Factory Developer
**I want** opt-in LangSmith tracing across all agents, tools, and pipeline functions
**So that** I can observe token usage, latency, tool call sequences, and failure points across the full knowledge graph construction workflow

## Story Points: 3

## Status: Not Started

## Acceptance Criteria

- [ ] All Claude API calls are traced via `wrap_anthropic()` on the Anthropic client
- [ ] Agent `run()` methods are decorated with `@traceable` producing named spans (e.g. `"user_intent.run"`)
- [ ] `execute_tool()` in `core/tools.py` is decorated with `@traceable` so each tool invocation appears as a child span
- [ ] MCP server tool functions (all 9 tools) are decorated with `@traceable`
- [ ] Pipeline functions (`build_domain_graph`, `build_text_graph`, `resolve_entities`) are decorated with `@traceable`
- [ ] Tracing is fully opt-in: only activates when `LANGSMITH_TRACING=true` is set
- [ ] Zero performance or behavioral impact when tracing is disabled (no-op decorators)
- [ ] No changes to function signatures, return types, or existing behavior
- [ ] `langsmith>=0.3.0` added to `requirements.txt`
- [ ] `.env.example` updated with LangSmith environment variables
- [ ] Unit tests pass with and without `langsmith` installed

## Definition of Done

- [ ] Code implemented and working
- [ ] Unit tests passing (existing 45+ tests unaffected)
- [ ] Manual verification: traces visible in LangSmith dashboard for a full pipeline run
- [ ] Documentation updated (`.env.example`, inline docstrings)
- [ ] Code reviewed
- [ ] Acceptance criteria verified

## Technical Notes

### Architecture

LangSmith integration uses three mechanisms, each targeting a different layer:

```
Layer 1: wrap_anthropic()     -- auto-traces all Claude API calls
Layer 2: @traceable           -- named spans for agents, tools, MCP, pipelines
Layer 3: trace() context mgr  -- optional manual spans for async blocks
```

Trace hierarchy produced:

```
kg_schema_proposal (MCP tool)            # @traceable on MCP function
  -> SchemaProposalAgent.run()           # @traceable on agent run()
    -> Claude API call                   # wrap_anthropic() auto-capture
    -> execute_tool("set_proposed_plan") # @traceable on execute_tool()
    -> Claude API call                   # wrap_anthropic() auto-capture
```

### Integration Points

**1. Anthropic Client Wrapping (`core/agent.py`)**

Both `run_agent()` and `run_agent_sync()` create an `anthropic.Anthropic()` client. Wrap it to auto-trace all Claude API calls:

```python
import anthropic

try:
    from langsmith.wrappers import wrap_anthropic
except ImportError:
    wrap_anthropic = None  # graceful fallback

async def run_agent(message, state, system_prompt, tools, tool_handlers, ...):
    client = anthropic.Anthropic()
    if wrap_anthropic:
        client = wrap_anthropic(client)
    # ... rest unchanged
```

**2. `@traceable` on Agent `run()` Methods (`agents/*.py`)**

Each of the 6 agent classes has a `run()` method. Decorate each:

```python
try:
    from langsmith import traceable
except ImportError:
    def traceable(*args, **kwargs):  # no-op fallback
        def decorator(func):
            return func
        return decorator

class UserIntentAgent:
    @traceable(name="user_intent.run")
    def run(self, message, state, conversation=None):
        ...
```

Agent files to modify:
- `agents/user_intent.py` -- `@traceable(name="user_intent.run")`
- `agents/file_suggestion.py` -- `@traceable(name="file_suggestion.run")`
- `agents/schema_proposal.py` -- `@traceable(name="schema_proposal.run")`
- `agents/schema_critic.py` -- `@traceable(name="schema_critic.run")`
- `agents/ner_extraction.py` -- `@traceable(name="ner_extraction.run")`
- `agents/fact_extraction.py` -- `@traceable(name="fact_extraction.run")`

**3. Tool Execution (`core/tools.py`)**

Decorate `execute_tool()` so every tool invocation is a child span:

```python
try:
    from langsmith import traceable
except ImportError:
    def traceable(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

@traceable(name="execute_tool")
def execute_tool(tool_handlers, tool_name, tool_input, state):
    # ... existing code unchanged
```

**4. MCP Server Tool Functions (`mcp_server/server.py`)**

Decorate each of the 9 MCP tool functions:

```python
try:
    from langsmith import traceable
except ImportError:
    def traceable(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

@traceable(name="mcp.kg_user_intent")
async def kg_user_intent(message: str) -> str:
    ...

@traceable(name="mcp.kg_build_graph")
async def kg_build_graph(message: str, scope: str = "all") -> str:
    ...
```

**5. Pipeline Functions (`pipelines/*.py`)**

Decorate the top-level pipeline entry points:

```python
# pipelines/domain_builder.py
@traceable(name="pipeline.build_domain_graph")
def build_domain_graph(state, driver):
    ...

# pipelines/text_builder.py
@traceable(name="pipeline.build_text_graph")
async def build_text_graph(state, driver, message):
    ...

# pipelines/entity_resolution.py
@traceable(name="pipeline.resolve_entities")
def resolve_entities(state, driver):
    ...
```

### Opt-In Behavior

LangSmith tracing activates only when the user sets environment variables:

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_PROJECT=kg-factory        # optional, defaults to "default"
```

When `LANGSMITH_TRACING` is unset or `false`:
- `wrap_anthropic()` is a pass-through (returns unwrapped client)
- `@traceable` decorators are no-ops (zero overhead)
- No network calls to LangSmith servers

When `langsmith` is not installed at all:
- Import fallbacks ensure `wrap_anthropic = None` and `traceable` is a no-op decorator
- All existing functionality works identically

### Graceful Import Pattern

Use a consistent pattern across all modified files:

```python
try:
    from langsmith import traceable
except ImportError:
    def traceable(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
```

This could optionally be centralized in `core/__init__.py` or a small `core/tracing.py` utility, but given the simplicity of the fallback, inline imports in each file are acceptable and avoid coupling.

### Files to Create/Update

```
core/
  agent.py              # UPDATE: wrap_anthropic() on Anthropic client
  tools.py              # UPDATE: @traceable on execute_tool()

agents/
  user_intent.py        # UPDATE: @traceable on run()
  file_suggestion.py    # UPDATE: @traceable on run()
  schema_proposal.py    # UPDATE: @traceable on run()
  schema_critic.py      # UPDATE: @traceable on run()
  ner_extraction.py     # UPDATE: @traceable on run()
  fact_extraction.py    # UPDATE: @traceable on run()

mcp_server/
  server.py             # UPDATE: @traceable on all 9 MCP tool functions

pipelines/
  domain_builder.py     # UPDATE: @traceable on build_domain_graph()
  text_builder.py       # UPDATE: @traceable on build_text_graph()
  entity_resolution.py  # UPDATE: @traceable on resolve_entities()

requirements.txt        # UPDATE: add langsmith>=0.3.0
.env.example            # UPDATE: add LangSmith env vars
```

### Environment Variables to Add (`.env.example`)

```bash
# LangSmith Observability (optional, set to enable tracing)
LANGSMITH_TRACING=false
LANGSMITH_API_KEY=your-langsmith-api-key-here
LANGSMITH_PROJECT=kg-factory
```

## Dependencies

- All prior user stories (US001-US010) must be complete (tracing wraps existing code)
- LangSmith account for verification (free tier sufficient)
- `langsmith>=0.3.0` Python package

## Out of Scope

- **Evaluation pipelines** -- LangSmith supports evals/datasets, but that is a separate feature
- **OpenAI call wrapping** -- GPT-4o calls inside `neo4j-graphrag`'s `SimpleKGPipeline` are not directly wrappable without modifying the library
- **Custom LangSmith dashboards** -- Use the default LangSmith UI; no custom dashboard work
- **Neo4j query tracing** -- Cypher query observability is not part of this story
- **Prompt versioning** -- LangSmith Hub prompt management is a separate concern
- **Automated alerting** -- LangSmith alerting/monitoring rules are out of scope

## Validation Scenarios

### Scenario 1: Full pipeline trace visibility

1. Set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY`
2. Run a full pipeline: user intent -> file suggestion -> schema proposal -> critic -> NER -> facts -> build graph
3. Open LangSmith dashboard
4. Verify a trace tree shows:
   - Each MCP tool call as a top-level span
   - Agent `run()` as a child span within each MCP tool
   - Claude API calls nested within agent runs
   - Tool executions (`execute_tool`) nested within agent runs
5. Verify token usage and latency are visible per span

### Scenario 2: Opt-in behavior (tracing disabled)

1. Ensure `LANGSMITH_TRACING` is unset or `false`
2. Run the same full pipeline
3. Verify no network calls to LangSmith (no errors, no slowdown)
4. Verify all pipeline output is identical to pre-US011 behavior

### Scenario 3: Graceful degradation (langsmith not installed)

1. Uninstall `langsmith` package (`pip uninstall langsmith`)
2. Run existing unit tests (`pytest tests/unit/`)
3. Verify all 45+ tests pass with no import errors
4. Run an interactive agent test
5. Verify agents work identically without `langsmith` installed

### Scenario 4: Pipeline-level tracing

1. Enable tracing
2. Run `kg_build_graph(scope="all")`
3. Verify three pipeline spans appear:
   - `pipeline.build_domain_graph`
   - `pipeline.build_text_graph`
   - `pipeline.resolve_entities`
4. Verify each pipeline span shows duration and success/failure status
