# Extraction Efficiency: From Agent Loops to Structured Output

## Problem Statement

The NER Extraction (Stage 4) and Fact Extraction (Stage 5) agents are the most
expensive tools in the KG-Factory pipeline. A single user message like "analyze
my files" triggers 15-20 Claude API calls internally, consuming significant time
(30-90s) and tokens (~200K input tokens due to conversation compounding).

This document explains the root cause and proposes a solution.

## Root Cause

### How It Works Today

Both agents use the `run_agent_sync()` loop from `core/agent.py`. Each tool
call triggers a full Claude API round-trip: the entire conversation history
(system prompt + all prior turns) is sent to Claude, Claude responds with a
tool call, the tool executes locally, and the result is sent back.

**NER Extraction — typical flow (~7-10 API calls):**

```
User: "analyze my files and propose entity types"

Turn 1: Claude reads previews, calls search_files("defect")      -> API call
Turn 2: Claude reads results, calls search_files("warranty")     -> API call
Turn 3: Claude reads results, calls search_files("assembly")     -> API call
Turn 4: Claude reads results, calls search_files("quality")      -> API call
Turn 5: Claude reads results, calls sample_file(lines 45-60)     -> API call
Turn 6: Claude calls set_proposed_entities({...})                 -> API call
Turn 7: Claude produces text response                             -> API call
```

**Fact Extraction — typical flow (~8-12 API calls):**

```
User: "propose relationship types"

Turn 1: Claude calls search_files("caused by")                   -> API call
Turn 2: Claude calls search_files("reported")                    -> API call
Turn 3: Claude calls add_proposed_fact("has_issue")              -> API call
Turn 4: Claude calls add_proposed_fact("has_feature")            -> API call
Turn 5: Claude calls add_proposed_fact("affects_feature")        -> API call
Turn 6: Claude calls add_proposed_fact("mentioned_in")           -> API call
Turn 7: Claude calls add_proposed_fact("supplied_by")            -> API call
Turn 8: Claude produces text response                             -> API call
```

**Total: ~15-20 API calls for the initial proposal across both stages.**

### Three Root Causes

| # | Root Cause | Impact | Location |
|---|-----------|--------|----------|
| 1 | **Evidence gathering via LLM tool calls** | ~5-8 unnecessary API calls | NER agent calls `search_files` once per pattern |
| 2 | **Fact types added one at a time** | ~5-8 unnecessary API calls | Fact agent calls `add_proposed_fact` per relationship |
| 3 | **Conversation context compounds** | Token cost grows quadratically | `run_agent_sync` resends full history each turn |

### Why It Compounds

Each API call sends the **entire conversation so far**. Turn 1 sends ~15K tokens
(system prompt + user message). By turn 7, the conversation includes all prior
tool calls and results, so it sends ~50-80K tokens. The total across all turns
is roughly 200K input tokens — far more than the actual content warrants.

### The Core Insight

The agent is using an LLM to grep files. The `search_files` tool is Python
`re.search()` — a 20-line function that needs no intelligence. But because it's
exposed as an agent tool, every grep costs a full Claude API round-trip.

The LLM invents search terms on the fly ("let me check if 'defect' appears...
now let me try 'warranty'..."), one at a time, when it could produce the full
answer in a single call. The file previews are already in the system prompt —
Claude has already "seen" the text before it starts searching.

### What the Evidence Gathering Actually Does

The `search_files` loop exists for a reason: it populates `grounding_evidence`
on each discovered entity type (search patterns, total mentions, example
excerpts, files with evidence). The critic agent (`kg_critic(scope="unstructured")`)
uses this evidence to validate proposals.

The problem is not the evidence — it's that the evidence is gathered **by the
LLM via tool calls** instead of **by code**.

## Research: How Others Solve This

Production knowledge graph systems treat type/schema discovery as a one-shot
classification task, not an iterative exploration:

| System | Approach | API Calls |
|--------|----------|-----------|
| **neo4j-graphrag** `SchemaFromTextExtractor` | Single structured-output call from text sample | 1 |
| **Microsoft GraphRAG** auto-tuning | Domain detection + type discovery + few-shot generation | 2-3 |
| **LLMs4OL** (ISWC 2023) | Zero-shot prompting for type classification | 1 per task |
| **KG-Factory** (current) | Multi-turn agent loop with tool calls | 15-20 |

### Why Not Use SchemaFromTextExtractor Directly?

Our agents do things `SchemaFromTextExtractor` cannot:

1. **Well-known type bridging** — Awareness of the existing domain graph schema
   (Product, Supplier from CSVs) to bridge structured and unstructured layers
2. **Goal steering** — Uses the user's stated goal and competency questions to
   decide what's relevant
3. **Propose-approve loop** — The user reviews and refines types before extraction
4. **Evidence trail** — The critic validates proposals against grounding evidence

We should steal the *approach* (single structured-output call) while keeping
our *capabilities* (goal-aware, schema-aware, user-in-the-loop).

## Proposed Solution

### Principle: One API Call for Discovery, Plain Code for Evidence

Replace the agent loop's initial proposal with:

1. **One structured-output API call** — Claude receives the same context
   (user goal, competency questions, well-known types, file content) and returns
   a complete JSON proposal for both entity types and fact types
2. **Programmatic evidence gathering** — Python code runs `handle_search_files`
   for each discovered type to populate `grounding_evidence`, no LLM needed
3. **Agent loop preserved for iteration** — User feedback ("add X", "remove Y")
   still goes through the conversational agent

### File Content Strategy

The file previews currently use `lines_per_section=2`, which truncates content.
The solution uses a two-tier adaptive strategy:

**Tier 1 — All files in one call (default):**

When total markdown content fits within a budget (`max_chars`, default 50K
chars / ~12K tokens), include the full text of all files in a single prompt.
No information loss, one API call.

This is the common case for typical KG-Factory projects (1-5 small-to-medium
markdown files).

**Tier 2 — Per-file calls with merge (large content fallback):**

When total content exceeds the budget, switch to one structured-output call
per file, each seeing the full text of that file. The results are then merged
by deduplicating entity types (by name) and fact types (by predicate). Merge
rules:

- Entity types: If two files both propose "Issue", keep the one with longer
  description. Combine `evidence_patterns` from both.
- Fact types: Deduplicate by (subject, predicate, object) triple. Keep the
  first description seen.
- `analysis_summary`: Concatenate per-file summaries.

This ensures every file gets full coverage — no truncation, no sampling — at
the cost of N API calls for N files. This is still dramatically cheaper than
the current agent loop (N calls vs N * 15 calls).

| Content Size | Strategy | API Calls | File Coverage |
|-------------|----------|-----------|---------------|
| < 50K chars total | All files in one call | 1 | Full |
| >= 50K chars total | One call per file, merge | N (one per file) | Full |

Both tiers eliminate the need for `search_files` and `sample_file` during the
initial proposal. Those tools remain available for user-directed iteration.

### Structured Output Schema

```python
EXTRACTION_SCHEMA = {
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
                        "items": {"type": "string"},
                        "description": "2-3 search terms to verify this type in text"
                    }
                },
                "required": ["name", "source", "description", "evidence_patterns"]
            }
        },
        "fact_types": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "predicate": {"type": "string"},
                    "object": {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["subject", "predicate", "object", "description"]
            }
        },
        "analysis_summary": {
            "type": "string",
            "description": "Brief summary of what was analyzed and why types were chosen"
        }
    },
    "required": ["entity_types", "fact_types", "analysis_summary"]
}
```

The `evidence_patterns` field is key: Claude suggests search terms for each
discovered type, and Python code executes the searches after the call.

### Programmatic Evidence Gathering

After the structured-output call returns, run `handle_search_files` (the
existing function) for each discovered entity type's `evidence_patterns`:

```python
for entity in proposal["entity_types"]:
    if entity["source"] == "discovered":
        evidence = {"search_patterns": [], "total_mentions": 0,
                    "example_excerpts": [], "files_with_evidence": 0}
        files_with_hits = set()

        for pattern in entity["evidence_patterns"]:
            result = handle_search_files(state, pattern=pattern)
            evidence["search_patterns"].append(pattern)
            evidence["total_mentions"] += result["match_count"]

            for match in result["matches"][:2]:
                evidence["example_excerpts"].append(match["context"])
                files_with_hits.add(match["file"])

        evidence["files_with_evidence"] = len(files_with_hits)
        entity["grounding_evidence"] = evidence
```

This produces the same `grounding_evidence` structure the critic expects,
without any LLM calls.

### Cost Comparison

| Approach | API Calls | Est. Input Tokens | Est. Time |
|----------|-----------|-------------------|-----------|
| Current (agent loops, stages 4+5) | ~16 | ~200K (compounding) | 30-90s |
| Structured output, all files (small content) | 2 + code | ~25K | 5-12s |
| Structured output, per-file merge (large content) | 2N + code | ~15K per file | 3-8s per file |

### What Changes

- The **initial proposal** goes from multi-turn agent loop to single
  structured-output call
- Evidence gathering moves from LLM tool calls to deterministic Python grep
- Entity types and fact types can be proposed together in one call
- The agent loop is preserved for **iteration** (user says "add X", "remove Y")

### What Stays the Same

- The propose-approve pattern (user reviews before finalizing)
- The critic validation (`kg_critic(scope="unstructured")` still works)
- The `grounding_evidence` structure (populated by code instead of LLM)
- The `search_files` and `sample_file` tools (available for user-driven iteration)
- Multi-turn conversation for refinement after the initial proposal
- The downstream `SimpleKGPipeline` in Stage 6 (consumes the same
  `approved_entity_types` and `approved_fact_types`)

## Decision: Combined vs Separate Calls

Two options for the structured-output call:

**Option A — Combined (entity types + fact types in one call):**
- Pros: 1 API call total, fact types informed by entity type reasoning
- Cons: More cognitive load on the LLM, harder to iterate on entities alone
- Risk: Lower quality on fact types if the model is overloaded

**Option B — Separate (entity types first, then fact types):**
- Pros: Matches current stage separation, easier to iterate per stage
- Cons: 2 API calls, fact type call must wait for entity type approval
- Benefit: User can approve entity types before seeing fact types

Recommendation: **Option B** for the initial implementation. It preserves the
existing stage separation and user approval flow. Option A can be offered as a
"fast mode" later.

## References

- [neo4j-graphrag SchemaFromTextExtractor](https://github.com/neo4j/neo4j-graphrag-python)
- [Microsoft GraphRAG Auto-Tuning](https://microsoft.github.io/graphrag/prompt_tuning/auto_prompt_tuning/)
- [LLMs4OL: LLMs for Ontology Learning (ISWC 2023)](https://arxiv.org/abs/2307.16648)
- [EDC: Extract, Define, Canonicalize (EMNLP 2024)](https://arxiv.org/abs/2404.03868)
- [Claude Structured Outputs](https://docs.anthropic.com/en/docs/build-with-claude/structured-output)
