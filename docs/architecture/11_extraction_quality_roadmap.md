# Extraction Quality Roadmap

Consolidated analysis of the NER & Fact Extraction pipeline (Stages 4-5),
integrating findings from the US020 critical review, WhyHow AI research,
Google's langextract patterns, and hands-on experience with the current
implementation.

This document replaces:
- `10_extraction_efficiency_review.md` (critical review)
- `10_extraction_efficiency_whyhow_research.md` (WhyHow research)

---

## 1. Where We Are

### What's Working

The US020 structured-output approach replaced a 15-20 API call agent loop with
a single structured-output call for the initial proposal. The savings are real:
~8x token reduction and ~10x fewer API calls for the common case.

Specifically, these foundations are solid:

| Component | Status | Why It Works |
|-----------|--------|-------------|
| `output_config` with JSON schema | Done | Guarantees valid JSON, no parse failures |
| User message passthrough | Done | Domain-specific guidance reaches the LLM |
| Zero-evidence flagging | Done | Surfaces hallucinated types to the user |
| Try/except fallback to agent loop | Done | Structured-output failure doesn't crash the system |
| Propose-approve pattern | Done | Users iterate after the initial draft |
| Critic validation | Done | `kg_critic(scope="unstructured")` still validates proposals |
| Evidence gathering | Done | Programmatic `handle_search_files`, zero LLM calls |

### What's Fragile

The fast path produces a **first draft with no self-correction**. It works well
for small, well-structured, domain-obvious text (product reviews, defect
reports). It degrades for:

1. **Large content** — per-file fallback loses cross-file visibility
2. **Messy/heterogeneous text** — single pass can't explore iteratively
3. **Non-obvious domains** — no examples to guide extraction quality

The rest of this document addresses these gaps in priority order.

---

## 2. Diagnosis

Five problems, ranked by impact on real-world usage.

### Problem 1: No Examples in Prompts

`_build_ner_prompt` and `_build_fact_prompt` explain *what* to do but never
show *what good output looks like*. The LLM infers quality expectations
entirely from the instruction text.

Every serious extraction system uses few-shot examples:
- **langextract** requires examples for every extraction call — they're not
  optional
- **WhyHow knowledge-table** includes structured response templates
- **OpenAI's extraction cookbook** recommends 2-3 examples minimum

Without examples, the LLM makes inconsistent decisions about:
- Granularity (is "broken_leg" one type or should it be "Issue"?)
- Naming (PascalCase consistency, singular vs plural)
- Source classification (well_known vs discovered boundary)
- Evidence pattern quality (too specific vs too broad)

**Impact: High.** This is the single highest-ROI improvement. Adding 2-3
domain-agnostic examples would improve consistency across all project types
without architectural changes.

### Problem 2: Evidence Gathering Never Feeds Back

The current flow is:

```
propose_entity_types() → gather_evidence() → format response → done
```

Evidence results are shown to the **user** but never shown to the **LLM**.
If Claude proposes an entity type "MaterialDefect" but `gather_evidence` finds
zero mentions in the text, the proposal still stands — flagged with
`[no evidence found]`, but not removed or refined.

This is a missed opportunity. The evidence step already runs (zero LLM cost).
Feeding results back for a second LLM call would let the model self-correct:
drop zero-evidence types, refine poor search patterns, and boost confidence in
well-grounded types.

The agent loop had this capability implicitly — Claude would search, see
results, and adjust. The fast path lost it.

**Impact: High.** Closes the feedback loop at the cost of one additional API
call (2 total, still far cheaper than 15-20).

### Problem 3: Per-File Fallback Loses Context

When total content exceeds the threshold, `build_file_content` returns a
per-file dict, and the server processes each file independently:

```python
for _path, file_text in content.items():
    proposals.append(propose_entity_types(state, content=file_text))
result = merge_entity_proposals(proposals)
```

Each API call sees one file in isolation. Three things break:

1. **No cross-file reasoning.** File A mentions "suppliers", File B mentions
   "defects". Neither alone suggests `SupplierDefect`, but together they might.
2. **No naming consistency.** File 1 proposes "Product", File 2 proposes "Item".
   `merge_entity_proposals` deduplicates by exact name match — these become two
   separate types.
3. **User message dropped.** Per-file calls use default prompts. If the user
   said "focus on quality defects", that guidance is lost.

Insights from external research:

- **langextract** solves this with **context windows**: carrying N characters
  from the end of the previous chunk into the beginning of the next. This
  preserves coreference resolution across boundaries.
- **WhyHow** solves it differently with **semantic pre-filtering**: embedding
  chunks and retrieving only relevant ones per pattern. Effective but requires
  embedding infrastructure we don't have at the discovery stage.

**Impact: Medium-High.** Affects any project with more than a few markdown
files. The current merge is purely mechanical — it can't synthesize.

### Problem 4: Content Threshold Is Too Conservative

The `max_chars=50_000` threshold triggers per-file fallback for ~12K tokens of
content. Claude's context window handles 200K tokens. A project with 8 files
of 8K chars each (64K total) barely exceeds the threshold and gets the degraded
per-file path, even though it would comfortably fit in one call.

**Impact: Medium.** Many real projects fall in the 50K-150K range where the
fast path would work fine but the threshold forces them into the inferior
per-file path. This is the easiest fix on the list.

### Problem 5: No Strategy for Very Large Individual Files

A single 300K-character markdown file gets sent in one API call. Claude's
context window can handle it, but extraction quality degrades in long contexts
— the "lost in the middle" phenomenon (Liu et al., 2023). Entity types
mentioned in the middle of a very long document are less likely to be proposed.

**Impact: Medium for now.** Rare in typical KG-Factory usage (most markdown
files are <50K chars). Becomes critical if the tool is used for large
documents like full manuals, specification documents, or scraped web archives.

---

## 3. Solutions

### Solution 1: Few-Shot Examples in Prompts

Add 2-3 domain-agnostic examples to `_build_ner_prompt` and
`_build_fact_prompt`. The examples should demonstrate:

- Correct PascalCase naming and singular nouns
- The difference between well_known and discovered sources
- Good vs bad evidence patterns (specific enough to find matches, broad enough
  to catch variants)
- Quality over quantity (showing a concise, focused proposal)

**For NER prompt**, add one example showing input text and expected output:

```
## Example

Given a product review mentioning "The oak frame cracked after 2 weeks.
Customer service sent a replacement part quickly.":

Good entity types:
- Product (well_known) — evidence_patterns: ["chair", "table", "desk"]
- Issue (discovered) — evidence_patterns: ["cracked", "broken", "defect"]
- CustomerInteraction (discovered) — evidence_patterns: ["customer service", "support", "warranty"]

Bad entity types:
- CrackedFrame (too specific — this is an instance, not a category)
- Rating (this is a property/measurement, not an entity)
- Thing (too vague)
```

**For Fact prompt**, add an example showing pattern quality:

```
## Example

Good: (Customer)-[reported_issue]->(Issue) — natural reading direction, specific predicate
Bad: (Issue)-[related_to]->(Product) — vague predicate, wrong direction
```

**Effort: Small.** Changes only `_build_ner_prompt()` and `_build_fact_prompt()`
in `extraction_tools.py`. No architectural changes. No new tests needed beyond
verifying the prompt string includes the examples.

### Solution 2: Raise Content Threshold

Change `max_chars` default from 50,000 to 150,000 (~37K tokens). This still
leaves ample room for the system prompt (~2K tokens) and the response (~4K
tokens) within Claude's 200K token context window.

Optionally make it configurable via state:

```python
def build_file_content(state: dict, max_chars: int = 150_000):
    max_chars = state.get("_extraction_max_chars", max_chars)
```

**Effort: Trivial.** One constant change. Update relevant tests.

### Solution 3: Evidence-Informed Re-Proposal

Add a second LLM call that sees the evidence results and refines the proposal.
The flow becomes:

```
propose_entity_types()     → initial draft (1 LLM call)
gather_evidence()          → programmatic search (0 LLM calls)
refine_entity_types()      → evidence-informed refinement (1 LLM call)
```

The refinement call receives:
- The initial proposal with evidence counts
- Zero-evidence types flagged
- The user's original message
- Instruction to drop unsupported types and refine search patterns

This mirrors langextract's **multi-pass extraction** concept, but adapted
for type discovery: instead of running the same extraction multiple times
and merging by character offsets, we run propose → verify → refine. The
verification step is programmatic (not LLM), making this cheaper than
langextract's approach.

**Key design decision:** The refinement call should use the same structured
output schema. The entire proposal is replaced, not patched — this is simpler
and avoids merge logic.

```python
def refine_entity_types(
    state: dict,
    initial_proposal: dict,
    entity_types_with_evidence: list[dict],
    user_message: str = None,
) -> dict:
    """Refine entity types based on evidence results. 1 LLM call."""
    # Build prompt showing initial proposal + evidence results
    # Ask Claude to: drop zero-evidence types, improve patterns, add
    # any types it may have missed
    # Returns same schema as propose_entity_types
```

**Cost:** 2 LLM calls total (still ~7x cheaper than agent loop). The second
call is smaller — it receives a summary, not the full file content.

**Effort: Medium.** New function in `extraction_tools.py`, update orchestration
in `server.py`, ~10 new tests.

### Solution 4: Context-Aware Per-File Processing

When the per-file fallback is needed (content > threshold), carry context
forward between files. Inspired by langextract's `context_window_chars`
parameter.

Two complementary mechanisms:

**A. Type accumulation.** After processing each file, pass the accumulated
entity type names to the next file's prompt as "types already found":

```python
accumulated_types = []
for path, file_text in content.items():
    result = propose_entity_types(
        state,
        content=file_text,
        user_message=message,
        prior_types=accumulated_types,  # new parameter
    )
    accumulated_types.extend(t["name"] for t in result["entity_types"])
```

The prompt for file N includes: "These types were already discovered in
previous files: [Product, Issue, Supplier]. You may reference them. Propose
any additional types found in this file, using the same names where
applicable."

This solves the naming inconsistency problem (file 2 sees that file 1
already called it "Product", not "Item") and enables cross-file reasoning
(file 2 knows "Supplier" exists and can propose `SupplierDefect`).

**B. User message forwarding.** Pass the user's message to every per-file
call, not just the first. This is a one-line fix.

**Effort: Medium.** New `prior_types` parameter in prompt-building functions,
sequential (not parallel) file processing, ~8 new tests.

### Solution 5: File Bin-Packing

For projects with many small files, group files that fit together within the
content threshold into a single API call. This reduces 50 files of 5K chars
from 50 API calls to ~2 calls (at 150K per group).

```python
def group_files(file_texts: dict, max_chars: int) -> list[str]:
    groups, current, size = [], [], 0
    for path, text in file_texts.items():
        if size + len(text) > max_chars and current:
            groups.append("\n\n".join(current))
            current, size = [], 0
        current.append(text)
        size += len(text)
    if current:
        groups.append("\n\n".join(current))
    return groups
```

This combines naturally with Solution 4 (type accumulation across groups).

**Effort: Small.** New helper function, update the per-file fallback loop,
~5 new tests.

### Solution 6: Large File Sectioning (Future)

For individual files exceeding ~150K chars, split by top-level headings
(`# Section`), process each section as a "virtual file", and merge results.
This uses the same splitting logic already in `pipelines/text_builder.py`
for the adaptive markdown splitting (US010).

**Effort: Medium.** Reuse existing splitting infrastructure. Not urgent —
few real projects have single files this large.

---

## 4. What NOT to Do

### Don't adopt pattern-per-call decomposition

WhyHow extracts instances by running a separate LLM call per schema pattern
per chunk (N_patterns x N_chunks calls). This is appropriate for **instance
extraction** (Stage 6, which we delegate to `SimpleKGPipeline`) but wasteful
for **type discovery** (Stages 4-5). Our single-call approach is the right
choice for discovery.

### Don't add embedding infrastructure before extraction

WhyHow uses vector similarity to pre-filter chunks before extraction. This
requires embedding all chunks at the discovery stage — a dependency we don't
have and don't need. Our full-text approach is simpler and sufficient for
typical file sizes. Revisit only if "lost in the middle" becomes a measured
problem with very large files.

### Don't combine entity and fact proposals into one call

The critical review notes that fact quality depends on entity quality (W4).
The temptation is to propose both in one call (Option A from the architecture
doc). But the current two-stage flow (entities → approval → facts) matches the
user approval pattern and gives the user a chance to refine entities before
facts are proposed. The separation is deliberate and valuable.

### Don't add Pydantic validation as a post-parse layer

WhyHow's knowledge-table uses Pydantic models with pre-validators for defense
in depth. We already have `output_config` with JSON schema enforcement, which
guarantees valid JSON at the API level. Adding a Pydantic layer on top is
redundant complexity for the same guarantee.

### Don't build sampled diversity yet

The sampled diversity approach (selecting representative sections via
unique-term scoring) is a good idea for truly massive content (100+ files).
But Solutions 2 (raise threshold) + 4 (context-aware processing) + 5
(bin-packing) handle the same problem space more simply. Sampled diversity
should be reconsidered only after these are implemented and measured.

---

## 5. Implementation Roadmap

### Phase 1: Prompt Quality (Solutions 1 + 2)

**Goal:** Improve first-call quality with zero architectural changes.

| Task | File | Change |
|------|------|--------|
| Add few-shot examples to NER prompt | `extraction_tools.py` | Update `_build_ner_prompt()` |
| Add few-shot examples to Fact prompt | `extraction_tools.py` | Update `_build_fact_prompt()` |
| Raise `max_chars` to 150,000 | `extraction_tools.py` | Update default in `build_file_content()` |
| Update tests | `test_extraction_efficiency.py` | Verify examples in prompts, threshold tests |

**Estimated scope:** ~50 lines of prompt text, 1 constant change, ~4 new tests.

### Phase 2: Evidence Feedback Loop (Solution 3)

**Goal:** Self-correcting proposals at the cost of one additional API call.

| Task | File | Change |
|------|------|--------|
| Add `refine_entity_types()` | `extraction_tools.py` | New function + prompt |
| Add `refine_fact_types()` | `extraction_tools.py` | New function + prompt |
| Update orchestration | `server.py` | Call refine after gather_evidence |
| Make refinement optional | `server.py` | Skip if all types have evidence |
| Add tests | `test_extraction_efficiency.py` | ~10 new tests |

**Key optimization:** Skip the refinement call if every proposed type has
`total_mentions > 0`. No wasted API call when the first pass is already good.

### Phase 3: Scalable Multi-File Processing (Solutions 4 + 5)

**Goal:** Per-file fallback that maintains context and minimizes API calls.

| Task | File | Change |
|------|------|--------|
| Add `prior_types` to prompt builders | `extraction_tools.py` | New parameter |
| Add `group_files()` helper | `extraction_tools.py` | New function |
| Update per-file fallback | `server.py` | Bin-pack + accumulate types |
| Forward user message to all calls | `server.py` | One-line fix |
| Add tests | `test_extraction_efficiency.py` | ~13 new tests |

### Phase 4: Large File Handling (Solution 6)

**Goal:** Handle individual files >150K chars without quality degradation.

Deferred until a real project triggers this. The infrastructure (heading-based
splitting) already exists in `pipelines/text_builder.py`.

---

## 6. Decision Log

Decisions made during this analysis, with rationale.

| Decision | Rationale | Source |
|----------|-----------|--------|
| Few-shot examples over schema constraints | Examples guide quality without constraining discovery | langextract, WhyHow |
| Evidence re-proposal over multi-pass merge | We extract types (not spans), so character-offset merge doesn't apply; evidence feedback is more targeted | langextract adaptation |
| Type accumulation over context windows | Carrying full text across files is expensive; type names are cheap and solve the naming problem | langextract adaptation |
| Bin-packing over sampled diversity | Simpler, preserves full content, reduces API calls without information loss | Original analysis |
| 150K threshold over configurable per-model | Practical for current Claude models; avoids configuration complexity | Review doc S2 |
| Sequential per-file over parallel | Type accumulation requires sequential processing; parallel loses cross-file context | Design tradeoff |

---

## 7. Evaluation System

Measuring extraction quality requires two complementary approaches: a
hand-curated golden reference for objective precision/recall, and programmatic
evidence metrics for always-on grounding checks.

### 7.1 Golden Reference (Furniture Supply Chain)

A human-curated answer key for the furniture supply chain project, based on
analysis of all 10 review files and 5 CSVs. Entity types and fact types are
divided into two tiers:

- **Required:** Types that any reasonable extraction must find. Unambiguous,
  high-frequency, present across multiple files.
- **Bonus:** Types that a good extraction might find. Present in the data but
  require more nuanced judgment. Not penalized if missed.

#### Golden Entity Types

| Type | Source | Tier | Rationale |
|------|--------|------|-----------|
| Product | well_known | Required | Named in every review file title and body. Defined in CSVs. |
| Reviewer | discovered | Required | `@username` pattern in every review. 100% coverage across all files. |
| Issue | discovered | Required | "cracked", "wobbles", "defective", "scratches" across multiple files. Helsingborg dresser reviews are dominated by defect reports. |
| Location | discovered | Required | City name after every reviewer. 100% coverage. |
| Feature | discovered | Bonus | "assembly", "storage", "cable management", "removable covers". Present but requires judgment to distinguish from properties. |
| CustomerService | discovered | Bonus | "customer service sent a replacement", "contacted customer service". Present in ~5 reviews across files. |

#### Golden Fact Types

| Triple | Tier | Rationale |
|--------|------|-----------|
| (Reviewer)-[reviewed]->(Product) | Required | Every review links a reviewer to a product. Fundamental structure. |
| (Reviewer)-[located_in]->(Location) | Required | Every reviewer has a city. Consistent pattern. |
| (Product)-[has_issue]->(Issue) | Required | Multiple products have reported problems. Central to supply chain analysis. |
| (Product)-[has_feature]->(Feature) | Bonus | Only valid if Feature entity type is proposed. |
| (Reviewer)-[reported_issue]->(Issue) | Bonus | Alternative direction to Product-has_issue. Either is acceptable. |

#### Scoring Metrics

**Precision** = correct proposed types / total proposed types

A proposed type is "correct" if it fuzzy-matches a golden type (case-insensitive,
Levenshtein distance ≤ 2, or semantic equivalence like "ProductIssue" ≈ "Issue").

**Required recall** = required golden types found / total required types

**Bonus recall** = bonus golden types found / total bonus types (informational,
not penalized).

**Passing thresholds:**

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| Required entity recall | >= 75% (≥ 3 of 4) | Missing at most 1 required type is acceptable |
| Required fact recall | >= 67% (≥ 2 of 3) | Missing at most 1 required fact is acceptable |
| Entity precision | >= 60% | Allows exploration — up to 40% speculative types is fine for a first draft |
| Evidence grounding rate | >= 80% | Most proposed types should have textual evidence |
| Zero-evidence count | <= 1 | At most 1 hallucinated type |

These thresholds define "acceptable first draft" quality. The user refines
from here via the agent loop.

### 7.2 Evidence-Based Metrics (Programmatic, Always-On)

These metrics use `gather_evidence()` results — zero LLM cost, deterministic,
already built. They run as part of every evaluation:

| Metric | Formula | What it catches |
|--------|---------|-----------------|
| Grounding rate | types with `total_mentions > 0` / total types | Hallucinated types |
| Evidence depth | average `total_mentions` per type | Shallow vs well-supported types |
| File coverage | files with ≥ 1 matching type / total files | Types concentrated in one file |
| Zero-evidence count | types with `total_mentions == 0` | Direct hallucination count |

Evidence metrics don't measure completeness (missing types aren't penalized).
The golden reference covers that gap. Together they provide both dimensions:
"did we propose real things?" (evidence) and "did we find the right things?"
(golden reference).

### 7.3 Implementation

**File:** `examples/furniture_supply_chain/eval/golden_reference.json`

```json
{
  "entity_types": {
    "required": [
      {"name": "Product", "source": "well_known",
       "evidence_patterns": ["chair", "table", "desk", "sofa"]},
      {"name": "Reviewer", "source": "discovered",
       "evidence_patterns": ["@", "reviewer", "username"]},
      {"name": "Issue", "source": "discovered",
       "evidence_patterns": ["cracked", "broken", "defective", "wobble"]},
      {"name": "Location", "source": "discovered",
       "evidence_patterns": ["Minneapolis", "Portland", "Seattle"]}
    ],
    "bonus": [
      {"name": "Feature", "source": "discovered",
       "evidence_patterns": ["assembly", "storage", "cable management"]},
      {"name": "CustomerService", "source": "discovered",
       "evidence_patterns": ["customer service", "support", "replacement"]}
    ]
  },
  "fact_types": {
    "required": [
      {"subject": "Reviewer", "predicate": "reviewed", "object": "Product"},
      {"subject": "Reviewer", "predicate": "located_in", "object": "Location"},
      {"subject": "Product", "predicate": "has_issue", "object": "Issue"}
    ],
    "bonus": [
      {"subject": "Product", "predicate": "has_feature", "object": "Feature"},
      {"subject": "Reviewer", "predicate": "reported_issue", "object": "Issue"}
    ]
  },
  "name_equivalences": {
    "Issue": ["ProductIssue", "Defect", "Problem", "QualityIssue"],
    "Reviewer": ["User", "Customer", "Author"],
    "Location": ["City", "Place", "Geography"],
    "Feature": ["ProductFeature", "Attribute"],
    "CustomerService": ["Support", "CustomerInteraction", "CustomerSupport"]
  }
}
```

**File:** `tests/eval/test_extraction_quality.py`

Loads the golden reference, runs `propose_entity_types()` and
`propose_fact_types()` against the furniture supply chain data, computes
all metrics, and asserts passing thresholds. Makes real API calls — run
explicitly, not in CI.

### 7.4 Usage

The evaluation serves three purposes:

1. **Baseline measurement.** Run before any Phase 1-3 changes to capture
   current quality. This is the number to beat.
2. **Regression testing.** Run after each phase to verify improvement (or
   at least no degradation).
3. **Model comparison.** Run with different models (Sonnet, Haiku, local)
   on the same input. The golden reference + evidence metrics produce
   directly comparable scores.

---

## 8. Future: Local LLM with Iterative Convergence

Once Phases 1-3 establish the golden model on Claude (correct behavior,
validated quality, full test coverage), the extraction pipeline becomes a
candidate for cost reduction via locally deployed LLMs.

### The idea

Replace one expensive Sonnet call with multiple free local calls that converge
on equivalent quality through a **fixed iteration pipeline**:

```
propose (local)  →  evidence (programmatic)  →  critic (local)  →  revise (local)
    ↑                                                                    │
    └────────────────────── repeat 2-3x ─────────────────────────────────┘
```

A local model's single-pass proposal may be mediocre. But each step in the
loop is a simple, well-defined task:

1. **Propose:** "Read this text, output entity types as JSON." Structured
   extraction — the easiest LLM task.
2. **Evidence:** Programmatic grep. No LLM. Produces concrete feedback:
   "MaterialDefect: 0 mentions. Issue: 14 mentions."
3. **Critic:** "Here's a proposal. Check for overlapping names, missing
   evidence, invalid predicates." Rule-following — within reach for 7-8B models.
4. **Revise:** "Here's your proposal with critic feedback. Fix the problems."
   Targeted correction — small input, constrained output.

After 2-3 rounds, the proposal converges. The total cost is zero API dollars.

### Why this is different from the agent loop

The current agent loop is a **free-form conversation** where the LLM decides
what tool to call next. That requires strong tool-calling capability — local
models struggle with it. The iterative pipeline is a **fixed sequence** — we
control the flow, the model just processes text at each step. This removes
the hardest part (deciding what to do) and keeps only the part local models
handle well (structured text-in, JSON-out).

### Why not now

- **No golden model yet.** We need Phases 1-3 working on Claude first to
  establish what "correct" looks like. The golden model defines the quality
  bar that local iteration must match.
- **Evaluation harness needed first.** The golden reference and evidence metrics
  (Section 7) must be implemented and baselined on Claude before comparing
  local models. Without a measured baseline, we can't quantify the quality gap.
- **Provider abstraction needed.** `propose_entity_types()` currently hardcodes
  `client.messages.create()` with Claude-specific parameters (`output_config`).
  Supporting local models requires an abstraction that handles different
  structured-output mechanisms (grammar constraints for llama.cpp/vLLM,
  `response_format` for OpenAI-compatible APIs).

### When to revisit

After Phase 3 is complete and tested:
1. Add a configurable model provider to `propose_entity_types()` /
   `propose_fact_types()`
2. Run the furniture supply chain extraction on both Claude and a local model
   (e.g., Llama 3 8B via Ollama)
3. Compare proposal quality — if the local model's single-pass is within
   80% of Sonnet's quality, the iterative pipeline will likely close the gap
4. Build the fixed iteration loop and measure convergence

---

## 9. References

- `tools/extraction_tools.py` — Fast path implementation (US020)
- `mcp_server/server.py:1000-1155` — NER orchestration
- `mcp_server/server.py:1158-1290` — Fact orchestration
- `10_extraction_efficiency.md` — Original US020 design
- `10_extraction_efficiency_review.md` — Critical review (superseded)
- `10_extraction_efficiency_whyhow_research.md` — WhyHow research (superseded)
- [google/langextract](https://github.com/google/langextract) — Multi-pass extraction, context windows
- [whyhow-ai/knowledge-graph-studio](https://github.com/whyhow-ai/knowledge-graph-studio) — Pattern decomposition, schema constraints
- [whyhow-ai/knowledge-table](https://github.com/whyhow-ai/knowledge-table) — Structured output via Pydantic
- Liu et al. (2023), "Lost in the Middle: How Language Models Use Long Contexts"
