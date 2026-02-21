# Extraction Efficiency: Critical Review

Peer review of the US020 structured-output approach documented in
`10_extraction_efficiency.md` and `docs/user_stories/US020_extraction_efficiency.md`.

Addresses two primary concerns: (1) quality of extracted entities and
relationships, and (2) scalability for large files.

## 1. Quality Assessment

### 1.1 Strengths

**Richer context than the agent loop.** The current agent loop injects 2-line
previews per section (`lines_per_section=2`) into the system prompt. The
structured-output approach sends full file text. Claude sees *more* content in
one shot than the agent loop ever accumulates across its iterative searches.
For well-structured, domain-obvious text (product reviews, defect reports),
quality should be equivalent or better.

**Evidence patterns are a clever bridge.** Having the LLM suggest search terms
(`evidence_patterns`) and then validating programmatically via
`handle_search_files` is a good division of labor — intelligence for hypothesis
generation, code for verification. The critic receives identical
`grounding_evidence` structures regardless of how they were produced.

**Propose-approve loop preserved.** Users can still iterate after the initial
proposal ("add X", "remove Y", "look deeper into this file"). A mediocre first
pass gets corrected interactively through the existing agent loop.

**Critic validation unchanged.** `kg_critic(scope="unstructured")` still
validates proposals against grounding evidence. The safety net is intact.

### 1.2 Weaknesses

#### W1: Single-pass vs. iterative discovery tradeoff

The agent loop lets Claude iteratively explore: search, find something
unexpected, search deeper, adjust. The structured approach forces a single-pass
classification. For messy, heterogeneous text with non-obvious entity types,
quality will degrade.

**Mitigation:** Accept this tradeoff for the initial proposal. The agent loop
remains available for iteration. Document that the first proposal is a
"fast draft" — users should expect to refine.

#### W2: Evidence patterns are a single point of failure

In the agent loop, Claude adapts: if "defect" finds nothing, it tries
"problem", then "issue". In the structured approach, you get 2-3 fixed terms
per entity type with zero feedback. If Claude picks poor search terms (too
specific like "cracked_surface" or too broad like "the"), the grounding
evidence will be misleading.

**Recommended fix:** After `gather_evidence`, if a discovered entity has
`total_mentions == 0`, flag it in the response (e.g., "[no evidence found]")
and consider demoting or dropping it. Add a post-evidence validation step:

```python
# After gather_evidence
for entity in entity_types:
    if entity["source"] == "discovered":
        mentions = entity.get("grounding_evidence", {}).get("total_mentions", 0)
        if mentions == 0:
            entity["_low_confidence"] = True
```

#### W3: No cross-file reasoning in per-file fallback

When content exceeds 50K chars and you process per-file, each API call sees
one file in isolation. Entity types that only make sense in relation to
patterns across files won't be discovered. The merge is purely mechanical
(dedup by name) — it can't synthesize.

Example: File A mentions "suppliers" but not "defects", File B mentions
"defects" but not "suppliers". Neither file alone suggests a `SupplierDefect`
relationship, but together they might.

**Mitigation options:**
1. After merging per-file results, do a lightweight "synthesis" call that
   sees the merged entity list + summaries from each file and can propose
   cross-file types. Cost: 1 additional API call.
2. Accept the limitation and document it. Cross-file patterns will be caught
   during the iteration phase when the user asks for refinement.

#### W4: Fact type quality depends on entity type quality

Since facts are proposed in a separate call after entity approval, a poor
initial entity proposal cascades. The agent loop at least allowed the fact
agent to implicitly discover missing entity types ("I see `reported_by`
patterns but there's no Reporter entity type"). The structured approach
can't self-correct across stages.

**Mitigation:** The separation is deliberate (Option B in the architecture
doc) and matches the user approval flow. Accept this limitation.

#### W5: No confidence signal

The schema doesn't include a confidence measure. The agent loop provided an
implicit signal (more searching = less certainty about a type). The structured
output loses this.

**Recommended fix:** Add an optional `confidence` field to the schema:

```json
{
    "name": "Issue",
    "source": "discovered",
    "description": "...",
    "confidence": "high",
    "evidence_patterns": ["defect", "issue", "problem"]
}
```

This helps the critic and the user prioritize review. Low-confidence types
get more scrutiny.

## 2. Scalability Assessment

### 2.1 Strengths

**Dramatic cost reduction for common cases.** 200K input tokens -> 25K is an
8x reduction. 15-20 API calls -> 2 is a 7-10x reduction. For the typical
KG-Factory project (1-5 small-to-medium markdown files), this is a clear win.

**Full text eliminates information loss.** The current 2-line previews truncate
heavily. Sending full text means Claude sees everything. This is actually a
quality *improvement* for files that fit in one call.

**Token economics are sound.** No conversation compounding (the dominant cost
driver in the agent loop) means token cost is proportional to content size,
not to the number of agent turns.

### 2.2 Weaknesses

#### S1: No strategy for individually large files

If a single markdown file is 300K chars (~75K tokens), it gets sent in one
API call. Claude's context window can handle it, but extraction quality
degrades significantly in long contexts — the "lost in the middle" phenomenon
is well-documented in the literature (Liu et al., 2023).

**Recommended fix:** Add a per-file size threshold (e.g., 100K chars). For
files that exceed it, split by top-level headings (`# Section`), process
each section as a separate "virtual file", and merge results:

```python
def build_file_content(state, max_chars=50_000, max_per_file=100_000):
    # ... existing logic ...
    for path, text in file_texts.items():
        if len(text) > max_per_file:
            # Split into sections by heading
            sections = split_by_headings(text)
            for section in sections:
                section_texts[f"{path}#section_{i}"] = section
```

#### S2: The 50K char threshold is arbitrary

No analysis of what content sizes are typical across real KG-Factory projects.
A project with 8 files of 8K chars each (64K total) barely exceeds the
threshold and triggers per-file mode, but could easily fit in one call with
a higher budget.

**Recommended fix:** Make the threshold configurable and consider
auto-calibrating based on the model's effective context window. The model's
`max_tokens` for input is ~200K; 50K chars (~12K tokens) is very conservative.
A budget of 80K-120K chars would still leave ample room for the system prompt.

#### S3: Linear scaling with no file grouping

Per-file mode is O(N) API calls. For a project with 50 markdown files, that's
50 NER calls + 50 fact calls = 100 API calls. Better than 50*15=750, but
still substantial.

**Recommended fix:** Bin-pack small files into groups that fit within the
char budget:

```python
def group_files(file_texts: dict, max_chars: int) -> list[str]:
    """Group small files into chunks that fit within the budget."""
    groups = []
    current_group = []
    current_size = 0
    for path, text in file_texts.items():
        if current_size + len(text) > max_chars and current_group:
            groups.append("\n\n".join(current_group))
            current_group = []
            current_size = 0
        current_group.append(text)
        current_size += len(text)
    if current_group:
        groups.append("\n\n".join(current_group))
    return groups
```

This reduces 50 files of 5K chars each from 50 API calls to 5 API calls
(at 50K per group).

#### S4: No progress feedback for long runs

For large-content scenarios (per-file with many files), the user gets no
feedback during processing. Combined with Cowork's ~60s timeout (US019),
a per-file run with 10+ files at 5-12s each will likely timeout.

**Recommended fix:** Integrate with the `_async_capable` pattern from US019
and add progress tracking:

```python
state["_extraction_progress"] = {
    "total_files": len(files),
    "completed": 0,
    "current_file": path,
}
```

## 3. Implementation Issues

These are bugs or gaps in the current code (`tools/extraction_tools.py`)
relative to the user story specification.

### I1: Missing `response_format` parameter (Critical)

Lines 391-403 and 430-443 of `extraction_tools.py` call
`client.messages.create()` **without** the `response_format` parameter.
The user story explicitly requires `response_format={"type": "json_schema", ...}`
for guaranteed valid JSON.

Without it, the code relies on the prompt to produce valid JSON and calls
`json.loads(text)` with no safety net. Claude sometimes wraps JSON in
markdown fences, adds preamble text, or produces subtly invalid JSON.

```python
# Current (broken):
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    system=system_prompt,
    messages=[...],
    extra_headers={"anthropic-beta": "interleaved-thinking-2025-05-14"},
)

# Fix — add response_format:
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    system=system_prompt,
    messages=[...],
    response_format=ENTITY_TYPE_SCHEMA,
)
```

**Note:** Verify compatibility between `response_format` and the
`interleaved-thinking` beta header. If they conflict, drop the thinking
header — structured output guarantees are more important for correctness
than thinking tokens are for quality.

### I2: No try/except or fallback to agent loop

The user story specifies: "If the structured-output call fails (API error,
invalid response), fall through to the existing agent loop." This is not
implemented. `propose_entity_types` and `propose_fact_types` will crash on
`json.loads()` errors or API failures.

### I3: Hardcoded user message ignores actual user input

The structured-output calls always send `"Analyze the files and propose
entity types."` regardless of what the user actually said. If the user calls
`kg_ner_extraction("propose entity types focusing on quality defects")`,
the domain-specific guidance is discarded.

**Recommended fix:** Pass the user's actual message into the
structured-output call, or at minimum append it to the system prompt.

### I4: Fact type subject/object validation is post-hoc

If Claude proposes a fact with `subject: "Reporter"` but Reporter isn't an
approved entity type, the entire call is partially wasted. With
`response_format` and strict schemas, you could constrain `subject` and
`object` to an enum of approved type names. Without it, add a post-call
filter that drops invalid triples with a warning.

## 4. Risk Summary

| Dimension | Assessment | Risk |
|-----------|-----------|------|
| Quality (small files, simple domains) | Equivalent or better (more context) | Low |
| Quality (complex/messy text) | Somewhat worse (no iterative exploration) | Medium |
| Quality (per-file fallback) | Notably worse (no cross-file reasoning) | Medium-High |
| Scalability (1-5 small files) | Excellent (1 call vs 15) | Low |
| Scalability (10+ files) | Good but needs progress/timeout handling | Medium |
| Scalability (huge individual files) | No strategy, quality degrades | High |
| Implementation correctness | Missing `response_format`, no retry, no fallback | High |

## 5. Recommendations (Priority Order)

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 1 | Add `response_format` to API calls | Small | Critical — correctness |
| 2 | Add try/except + fallback to agent loop | Small | Critical — reliability |
| 3 | Add zero-evidence filtering/flagging | Small | Medium — quality |
| 4 | Inject user's actual message | Small | Medium — usability |
| 5 | Add per-file size threshold + section splitting | Medium | High — scalability |
| 6 | Add file bin-packing for per-file mode | Medium | Medium — scalability |
| 7 | Add cross-file synthesis call (optional) | Medium | Medium — quality |
| 8 | Add confidence field to schema | Small | Low — observability |
| 9 | Make char threshold configurable | Small | Low — flexibility |

## References

- Liu et al. (2023), "Lost in the Middle: How Language Models Use Long Contexts"
- `docs/architecture/10_extraction_efficiency.md` — original design
- `docs/user_stories/US020_extraction_efficiency.md` — acceptance criteria
- `tools/extraction_tools.py` lines 150-631 — implementation under review
