# US020: Extraction Efficiency — Structured Output for NER & Fact Discovery

## User Story

**As a** KG-Factory user building knowledge graphs from unstructured text
**I want** entity type and fact type proposals to be generated quickly and cheaply
**So that** the extraction stages don't dominate pipeline cost and wall-clock time

## Story Points: 5

## Status: Not Started

## Context

The NER Extraction (Stage 4) and Fact Extraction (Stage 5) agents are the most
expensive tools in the pipeline. A single user message like "analyze my files"
triggers 15-20 Claude API calls internally, consuming 30-90 seconds and ~200K
input tokens due to conversation compounding.

The root cause is that the agent loop uses the LLM to grep files. The
`search_files` tool is Python `re.search()` — it needs no intelligence — but
because it's exposed as an agent tool, every grep costs a full Claude API
round-trip. The LLM invents search terms on the fly, one at a time, when it
could look at the same file content and produce the full answer in one shot.

Similarly, the Fact Extraction agent calls `add_proposed_fact` once per
relationship type, so 6 fact types = 6 additional API calls.

Production systems (neo4j-graphrag `SchemaFromTextExtractor`, Microsoft GraphRAG
auto-tuning) treat type discovery as a one-shot classification task: 1-2 LLM
calls, not 15-20.

See `docs/architecture/10_extraction_efficiency.md` for the full analysis.

## Approach

Replace the multi-turn agent loop for the **initial proposal** with:

1. **One structured-output API call** per stage — Claude receives the same
   context (user goal, competency questions, well-known types, file content)
   and returns a complete JSON proposal
2. **Programmatic evidence gathering** — Python code runs `handle_search_files`
   for each discovered entity type's suggested patterns, populating
   `grounding_evidence` without any LLM calls
3. **Agent loop preserved for iteration** — User feedback ("add X", "remove Y",
   "look deeper into this file") still goes through the existing conversational
   agents with their full tool sets

## Acceptance Criteria

### Adaptive File Content Injection

- [ ] New function `build_file_content(state, max_chars=50_000) -> tuple[str, bool]` in `tools/extraction_tools.py`
- [ ] Returns `(content_string, fits_in_one_call)`
- [ ] For each approved unstructured file, reads full text
- [ ] If total content across all files fits within `max_chars`:
  - Returns concatenated full text of all files, `fits_in_one_call=True`
- [ ] If total content exceeds `max_chars`:
  - Returns per-file content as a `dict[str, str]` (file path -> full text), `fits_in_one_call=False`
  - Caller uses per-file strategy (see below)
- [ ] Content formatted with file paths and line numbers preserved
- [ ] Used by both NER and Fact extraction structured-output calls

### Per-File Fallback for Large Content

- [ ] When `fits_in_one_call=False`, the NER and Fact extraction functions call the structured-output API **once per file**, each seeing the full text of that file
- [ ] Results are merged across files by deduplicating:
  - Entity types: by name — if two files propose the same type, keep the longer description, combine `evidence_patterns`
  - Fact types: by (subject, predicate, object) triple — keep the first description
  - `analysis_summary`: concatenate per-file summaries
- [ ] New function `merge_entity_proposals(proposals: list[dict]) -> dict` in `tools/extraction_tools.py`
- [ ] New function `merge_fact_proposals(proposals: list[dict]) -> dict` in `tools/extraction_tools.py`
- [ ] Unit tests for merge logic (duplicate handling, evidence_patterns union, description selection)

### NER Structured Output (Stage 4)

- [ ] New function `propose_entity_types(state) -> dict` in `tools/extraction_tools.py`
- [ ] Constructs a prompt with:
  - User goal and competency questions
  - Well-known types from construction plan
  - File content via `build_file_content`
  - Quality guidelines from current NER system prompt (PascalCase, no quantities, etc.)
- [ ] Uses Claude API with `response_format={"type": "json_schema", ...}` for guaranteed valid JSON
- [ ] Output schema:
  ```json
  {
    "entity_types": [
      {
        "name": "string (PascalCase)",
        "source": "well_known | discovered",
        "description": "string",
        "evidence_patterns": ["string", "string"]
      }
    ],
    "analysis_summary": "string"
  }
  ```
- [ ] Returns proposed entity types in the same format as `handle_set_proposed_entities`
- [ ] Two strategies based on content size:
  - **Small content** (fits in one call): single API call with all files
  - **Large content** (exceeds budget): one API call per file, results merged via `merge_entity_proposals`
- [ ] Model: `claude-sonnet-4-20250514`

### Fact Type Structured Output (Stage 5)

- [ ] New function `propose_fact_types(state) -> dict` in `tools/extraction_tools.py`
- [ ] Constructs a prompt with:
  - User goal and competency questions
  - Approved entity types (from Stage 4)
  - File content via `build_file_content`
  - Design rules from current Fact Extraction system prompt (directionality, no vague predicates, etc.)
- [ ] Uses Claude API with `response_format={"type": "json_schema", ...}`
- [ ] Output schema:
  ```json
  {
    "fact_types": [
      {
        "subject": "string",
        "predicate": "string (lowercase_underscores)",
        "object": "string",
        "description": "string"
      }
    ],
    "analysis_summary": "string"
  }
  ```
- [ ] Validates subject/object against approved entity types, predicate format
- [ ] Returns proposed fact types in the same format as `handle_add_proposed_fact`
- [ ] Two strategies based on content size:
  - **Small content**: single API call with all files
  - **Large content**: one API call per file, results merged via `merge_fact_proposals`

### Programmatic Evidence Gathering

- [ ] New function `gather_evidence(state, entity_types) -> dict` in `tools/extraction_tools.py`
- [ ] For each entity type where `source == "discovered"`:
  - Runs `handle_search_files(state, pattern=p)` for each pattern in `evidence_patterns`
  - Populates `grounding_evidence` with: `search_patterns`, `total_mentions`, `example_excerpts` (up to 5), `files_with_evidence`
- [ ] Returns updated entity types dict with `grounding_evidence` attached
- [ ] No LLM calls — purely deterministic Python
- [ ] Produces the same `grounding_evidence` structure the critic expects

### Updated MCP Tool Behavior

- [ ] `kg_ner_extraction(message)` detects first-time invocation (no prior conversation, no existing proposal)
  - First call: runs `propose_entity_types` + `gather_evidence`, saves as `proposed_entity_types`, returns proposal with analysis summary
  - Subsequent calls: routes through existing agent loop for iteration (user says "add X", "remove Y", "look deeper")
- [ ] `kg_fact_extraction(message)` same pattern:
  - First call: runs `propose_fact_types`, saves as `proposed_fact_types`, returns proposal
  - Subsequent calls: routes through existing agent loop for iteration
- [ ] Approval still goes through agent loop (`approve_proposed_entities` / `approve_proposed_facts` tools)
- [ ] `search_files` and `sample_file` tools remain available for user-driven exploration

### Fallback to Agent Loop

- [ ] If the structured-output call fails (API error, invalid response), fall through to the existing agent loop
- [ ] If `response_format` is not supported by the model, fall through to the existing agent loop
- [ ] Log a warning when falling back

### Backwards Compatibility

- [ ] Existing agent prompts and tools unchanged
- [ ] Existing `approved_entity_types` and `approved_fact_types` state format unchanged
- [ ] Existing critic validation unchanged (same `grounding_evidence` structure)
- [ ] Downstream `build_entity_schema()` in `pipelines/text_builder.py` unchanged
- [ ] All existing unit tests pass without modification

## Definition of Done

- [ ] Code implemented and working
- [ ] Unit tests for `build_file_content` (small files → full text + True, large files → per-file dict + False)
- [ ] Unit tests for `propose_entity_types` (mocked Claude call, validates output format)
- [ ] Unit tests for `propose_fact_types` (mocked Claude call, validates entity membership + predicate format)
- [ ] Unit tests for `gather_evidence` (verifies grounding_evidence structure)
- [ ] Unit tests for `merge_entity_proposals` (dedup by name, longer description wins, evidence_patterns union)
- [ ] Unit tests for `merge_fact_proposals` (dedup by triple, first description wins)
- [ ] Unit tests for per-file fallback (content exceeds budget → N calls + merge)
- [ ] Unit tests for first-call detection in MCP tools
- [ ] Unit tests for fallback to agent loop on error
- [ ] All existing tests still pass (backwards compat verified)
- [ ] Interactive test: `tests/test_12_extraction_efficiency.py`
- [ ] MCP tools work from Claude Code and Cowork
- [ ] Observability: traces visible in LangSmith when enabled
- [ ] Code reviewed

## Technical Notes

### Architecture

```
kg_ner_extraction(message)
  |
  +-> First call? (no conversation, no proposal)
  |     |
  |     YES:
  |     +-> build_file_content(state)             # Full text of all files
  |     |     |
  |     |     +-> Fits in one call? (< max_chars)
  |     |     |     YES -> propose_entity_types(state, all_content)   # 1 API call
  |     |     |     NO  -> for each file:
  |     |     |              propose_entity_types(state, file_content) # 1 API call per file
  |     |     |            merge_entity_proposals(results)             # Deduplicate
  |     |
  |     +-> gather_evidence(state, types)         # 0 API calls (Python grep)
  |     +-> Save as proposed_entity_types
  |     +-> Return proposal + analysis_summary
  |     |
  |     NO:
  |     +-> Existing agent loop (for iteration)
  |
kg_fact_extraction(message)
  |
  +-> First call? (no conversation, no proposal)
  |     |
  |     YES:
  |     +-> build_file_content(state)             # Full text of all files
  |     |     |
  |     |     +-> Fits in one call? (< max_chars)
  |     |     |     YES -> propose_fact_types(state, all_content)     # 1 API call
  |     |     |     NO  -> for each file:
  |     |     |              propose_fact_types(state, file_content)   # 1 API call per file
  |     |     |            merge_fact_proposals(results)               # Deduplicate
  |     |
  |     +-> Validate subject/object membership
  |     +-> Save as proposed_fact_types
  |     +-> Return proposal + analysis_summary
  |     |
  |     NO:
  |     +-> Existing agent loop (for iteration)
```

### Cost Comparison

| Approach | API Calls | Est. Input Tokens | Est. Time |
|----------|-----------|-------------------|-----------|
| Current (agent loops, stages 4+5) | ~16 | ~200K (compounding) | 30-90s |
| Structured output, small content (all files) | 2 + code | ~25K | 5-12s |
| Structured output, large content (per-file) | 2N + code | ~15K per file | 3-8s per file |

### Structured Output Call (NER)

```python
import json
import anthropic
from core.tracing import wrap_anthropic

ENTITY_TYPE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "entity_type_proposal",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "entity_types": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "source": {"type": "string", "enum": ["well_known", "discovered"]},
                            "description": {"type": "string"},
                            "evidence_patterns": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["name", "source", "description", "evidence_patterns"],
                        "additionalProperties": False
                    }
                },
                "analysis_summary": {"type": "string"}
            },
            "required": ["entity_types", "analysis_summary"],
            "additionalProperties": False
        }
    }
}

def propose_entity_types(state: dict) -> dict:
    client = wrap_anthropic(anthropic.Anthropic())

    system_prompt = _build_ner_prompt(state)  # Reuses existing prompt logic

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": "Analyze the files and propose entity types."}],
        response_format=ENTITY_TYPE_SCHEMA,
    )

    return json.loads(response.content[0].text)
```

### Programmatic Evidence Gathering

```python
def gather_evidence(state: dict, entity_types: list[dict]) -> list[dict]:
    for entity in entity_types:
        if entity["source"] != "discovered":
            continue

        evidence = {
            "search_patterns": [],
            "total_mentions": 0,
            "example_excerpts": [],
            "files_with_evidence": 0,
        }
        files_with_hits = set()

        for pattern in entity.get("evidence_patterns", []):
            result = handle_search_files(state, pattern=pattern)
            evidence["search_patterns"].append(pattern)
            evidence["total_mentions"] += result.get("match_count", 0)

            for match in result.get("matches", [])[:2]:
                evidence["example_excerpts"].append(match["context"])
                files_with_hits.add(match["file"])

        evidence["files_with_evidence"] = len(files_with_hits)
        evidence["example_excerpts"] = evidence["example_excerpts"][:5]
        entity["grounding_evidence"] = evidence

    return entity_types
```

### First-Call Detection

```python
# In kg_ner_extraction MCP tool handler:
conversation = _pop_conversation(state, "_ner_extraction_conversation")
has_prior_proposal = "proposed_entity_types" in state

if conversation is None and not has_prior_proposal:
    # First call — use structured output
    result = propose_entity_types(state)
    entity_types = gather_evidence(state, result["entity_types"])
    # ... save to state, format response ...
else:
    # Iteration — use existing agent loop
    agent = NerExtractionAgent()
    response, state, conversation = agent.run(message, state, conversation)
```

### Files to Create

```
tests/
  test_12_extraction_efficiency.py        # NEW: Interactive test
  unit/
    test_extraction_efficiency.py         # NEW: Unit tests
```

### Files to Modify

```
tools/extraction_tools.py                 # UPDATE: Add build_file_content,
                                          #         propose_entity_types,
                                          #         propose_fact_types,
                                          #         gather_evidence

mcp_server/server.py                      # UPDATE: kg_ner_extraction and
                                          #         kg_fact_extraction to use
                                          #         structured output on first call
```

## Dependencies

- Existing `tools/extraction_tools.py` (handle_search_files, build_markdown_context, build_well_known_types)
- Existing `tools/file_tools.py` (handle_sample_file, _get_data_dir)
- Existing `tools/competency_tools.py` (format_competency_questions)
- Existing `agents/ner_extraction.py` and `agents/fact_extraction.py` (unchanged, used for iteration)
- Existing `core/tracing.py` (wrap_anthropic, traceable)
- Claude API `response_format` parameter (structured outputs)

## Out of Scope

- Changing the agent loop architecture in `core/agent.py`
- Modifying the downstream `SimpleKGPipeline` (Stage 6)
- Modifying the critic agent behavior
- Combined single-call for both entity + fact types (future optimization)
- Automatic re-proposal when files change
- Batch processing of multiple projects
