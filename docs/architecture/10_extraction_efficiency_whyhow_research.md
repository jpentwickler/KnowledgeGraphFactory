# WhyHow AI Research: Patterns Relevant to Extraction Efficiency

Research into [whyhow-ai](https://github.com/whyhow-ai) repositories for patterns
applicable to US020 (Extraction Efficiency).

## WhyHow AI Overview

WhyHow builds open-source knowledge graph construction tools. Key repositories:

| Repository | Stars | What It Does |
|---|---|---|
| [knowledge-graph-studio](https://github.com/whyhow-ai/knowledge-graph-studio) | ~900 | Full KG platform: MongoDB + FastAPI + OpenAI |
| [knowledge-table](https://github.com/whyhow-ai/knowledge-table) | ~665 | Spreadsheet-like extraction via natural language queries |
| [schemas](https://github.com/whyhow-ai/schemas) | ~97 | Open-source domain schema library (healthcare, manufacturing, etc.) |
| [rule-based-retrieval](https://github.com/whyhow-ai/rule-based-retrieval) | ~248 | RAG with metadata-driven filtering |

## Relevant Patterns

### 1. Semantic Chunk Pre-Filtering (High Relevance)

**What they do:** Before extraction, WhyHow uses vector similarity to retrieve
only semantically relevant chunks for each pattern/question. Not all chunks are
sent to the LLM — only those that are likely to contain matches.

**How it works:**
- Documents are chunked and embedded at ingestion time
- For each extraction pattern (e.g., "medication CAUSES side_effect"), vector
  search retrieves the top-K most relevant chunks
- Only those chunks are sent to the LLM for extraction

**Why it matters for us:** Our `build_file_content` sends the full text of every
file to Claude. For large content (Tier 2), we process each file independently.
But within a large file, most sections may be irrelevant to a given entity type.

**Applicability to KG-Factory:**
- We already have embeddings via `SimpleKGPipeline` (Stage 6) but not at the
  discovery stage (Stages 4-5)
- Adding embedding + retrieval before Stages 4-5 would add complexity and a
  dependency on an embedding model
- **Verdict: Low priority for US020.** The structured-output approach already
  sends full text, which is simpler and sufficient for typical file sizes. Worth
  revisiting if we encounter quality issues with very large files (>100K chars)
  where "lost in the middle" becomes a problem

### 2. Pattern-Level Decomposition with Parallel Execution (Medium Relevance)

**What they do:** Instead of asking the LLM to extract ALL triples from a chunk,
they decompose by schema pattern. Each pattern gets its own focused prompt:

```
Pattern: (medication)-[CAUSES]->(side_effect)
Prompt: "Find [head, tail] pairs matching this pattern in the text"
```

All patterns run in parallel via `asyncio.gather()`.

**How it works** (from `builders.py`):
```python
async def fetch_triples(self, chunks, schema):
    tasks = []
    for pattern in schema.patterns:
        tasks.append(self.process_pattern(chunks, pattern))
    results = await asyncio.gather(*tasks)
```

**Trade-off:**
- More focused prompts = higher precision per extraction
- But N_patterns x N_chunks API calls = higher total cost
- For 6 patterns x 10 chunks = 60 API calls vs our 1-2 calls

**Applicability to KG-Factory:**
- Our structured-output approach (1 call for all types) is more cost-efficient
  for the *discovery* phase (Stages 4-5)
- Pattern decomposition is more relevant to Stage 6 (actual extraction via
  `SimpleKGPipeline`), where we already use neo4j-graphrag
- **Verdict: Not applicable to US020.** Our single-call approach is the right
  choice for type discovery. Pattern decomposition makes more sense for
  instance extraction (Stage 6), and we already delegate that to neo4j-graphrag

### 3. Schema Patterns as Extraction Constraints (High Relevance)

**What they do:** WhyHow schemas include explicit `patterns` that constrain
which (head_type, relation, tail_type) combinations are valid:

```json
{
    "entities": [
        {"name": "medication", "description": "..."},
        {"name": "side_effect", "description": "..."}
    ],
    "relations": [
        {"name": "causes", "description": "..."}
    ],
    "patterns": [
        {
            "head": "medication",
            "relation": "causes",
            "tail": "side_effect",
            "description": "A medication causes a side effect"
        }
    ]
}
```

Extraction only looks for triples matching defined patterns. This prevents
hallucinated relationship types.

**Why it matters for us:** Our `fact_types` are already structured as
(subject, predicate, object) triples, which is equivalent to WhyHow's `patterns`.
However, we don't enforce pattern-level constraints during Stage 6 extraction —
we pass entity types and fact types to `SimpleKGPipeline` separately.

**Applicability to KG-Factory:**
- Our fact type schema already captures this: `(Product)-[has_issue]->(Issue)`
- The key insight is that **patterns should be the primary schema artifact**,
  not separate entity lists and fact lists
- Consider: In the structured-output call, ask Claude to propose patterns
  directly rather than entity types and fact types separately. The entities
  are implicit in the patterns
- **Verdict: Consider for future optimization.** A combined entity+fact
  proposal (Option A in the architecture doc) would naturally produce patterns.
  Not worth refactoring US020 for this, but worth noting for a future iteration

### 4. Structured Output via Pydantic Models (High Relevance)

**What they do (knowledge-table):** Use OpenAI's native structured output with
Pydantic models as the response format:

```python
response = self.client.beta.chat.completions.parse(
    model=self.settings.llm_model,
    messages=[{"role": "user", "content": prompt}],
    response_format=response_model,  # Pydantic model class
)
parsed_response = response.choices[0].message.parsed
```

Their Pydantic models include pre-validators (`mode="before"`) that normalize
LLM output quirks (e.g., "none", "not found", empty string -> `None`).

**What they do (knowledge-graph-studio):** More manual approach — prompt for
JSON, strip markdown fences, `json.loads()`, manual validation, fallback to
empty list on parse error.

**Why it matters for us:** Our US020 implementation currently resembles the
knowledge-graph-studio approach (manual JSON parsing with no safety net).
The knowledge-table approach is superior.

**Applicability to KG-Factory:**
- Anthropic's equivalent is `response_format={"type": "json_schema", ...}`
  which we define in `ENTITY_TYPE_SCHEMA` / `FACT_TYPE_SCHEMA` but **don't
  actually pass to the API call** (see review doc, issue I1)
- Consider adding Pydantic validation as a post-parse step even with
  structured output, for defense in depth
- **Verdict: Reinforces the critical need to fix I1** (add `response_format`).
  Also consider adding a Pydantic validation layer for additional safety

### 5. Schema Auto-Generation from Questions (Medium Relevance)

**What they do (deprecated SDK):** The original `whyhow` SDK could generate
schemas from seed questions:

```python
schema = client.generate_schema(
    questions=["What side effects does Advil cause?",
               "Which medications interact with aspirin?"]
)
```

The LLM analyzes the questions to determine what entity types and relationship
types would be needed to answer them.

**Why it matters for us:** We already have competency questions
(`approved_competency_questions`) that serve the same purpose. Our NER and
Fact prompts include CQs in the context. But we treat CQs as supplementary
guidance — WhyHow treats them as the *primary input* for schema generation.

**Applicability to KG-Factory:**
- Our CQs are already injected into the structured-output prompts
- WhyHow's approach is more direct: questions -> schema, no file analysis
- For us, file content + CQs together give richer context than CQs alone
- **Verdict: No action needed.** Our approach (CQs + file content + goal)
  is more comprehensive than question-only schema generation

### 6. Strict vs. Permissive Schema Validation (Medium Relevance)

**What they do:** WhyHow offers two validation modes:
- **Strict:** Rejects triples that don't match defined patterns
- **Permissive:** Returns new patterns, enabling automatic schema extension
  via `extend_schema()`

```python
def validate_triples(triples, schema, mode="strict"):
    for triple in triples:
        if not matches_pattern(triple, schema.patterns):
            if mode == "strict":
                reject(triple)
            else:
                new_pattern = create_pattern(triple)
                schema.extend(new_pattern)
```

**Why it matters for us:** Our critic (`kg_critic(scope="unstructured")`)
validates proposals but doesn't auto-extend. During iteration, the user
manually adds types. A permissive mode could auto-suggest extensions.

**Applicability to KG-Factory:**
- Could be useful during Stage 6 extraction: if `SimpleKGPipeline` discovers
  triples that don't match approved fact types, surface them to the user
- Not relevant to US020 (which is about the discovery/proposal phase)
- **Verdict: Worth noting for future work, not for US020**

### 7. Rate Limiter with Token Estimation (Low Relevance)

**What they do:** A `RateLimiter` class tracks both requests-per-minute (RPM)
and tokens-per-minute (TPM) using sliding 60-second windows. Token counts
are estimated via `tiktoken` before making API calls.

**Applicability to KG-Factory:**
- We make 1-2 API calls for the structured-output path — rate limiting is
  unnecessary for this volume
- Would be relevant if we adopted pattern-per-call decomposition (Pattern 2)
  with many parallel calls
- **Verdict: Not needed for US020.** Consider if we ever do high-volume
  batch extraction

### 8. Entity Resolution via Rules (Low Relevance for US020)

**What they do:**
- `MergeNodesRule` for explicit node deduplication
- Knowledge-table normalizes entity name variations ("BlackRock Inc." ->
  "BlackRock") via extraction rules
- "Must Return" (exhaustive list) vs "May Return" (examples) rule types
- MongoDB `$search` aggregation for fuzzy name matching + cluster deduplication

**Applicability to KG-Factory:**
- We already have entity resolution in Stage 6 (`resolve_entities()` using
  rapidfuzz + apoc.text.jaroWinklerDistance)
- Their rules-based approach is more explicit but less flexible
- **Verdict: Not relevant to US020**

## Summary: What to Adopt

### Adopt Now (for US020)

| # | Pattern | Action | Effort |
|---|---------|--------|--------|
| 1 | Structured output via API schema enforcement | Fix I1: add `response_format` to API calls | Small |
| 2 | Post-parse validation (Pydantic-style) | Add validation layer after `json.loads()` | Small |

### Consider for Future Work

| # | Pattern | When | Why |
|---|---------|------|-----|
| 3 | Semantic chunk pre-filtering | If large-file quality degrades | Reduces "lost in the middle" |
| 4 | Schema patterns as primary artifact | When considering Option A (combined call) | Cleaner schema model |
| 5 | Permissive schema validation | Stage 6 improvements | Auto-discover missing types |
| 6 | Rate limiter with token estimation | If batch extraction is needed | Prevents API throttling |

### Not Applicable

| # | Pattern | Why Not |
|---|---------|---------|
| 7 | Pattern-per-call decomposition | Our single-call approach is more efficient for discovery |
| 8 | Schema from questions only | Our CQs + files + goal gives richer context |
| 9 | Entity resolution rules | Already covered by our Stage 6 resolution |

## Key Takeaway

WhyHow's architecture validates our general direction but highlights a
different philosophy:

- **WhyHow**: Many focused LLM calls, each doing one narrow task (one pattern
  per chunk). Higher precision, higher cost, pattern-level parallelism.
- **KG-Factory (US020)**: Few broad LLM calls, each doing a comprehensive task
  (all types from all content). Lower cost, relies on prompt quality, simpler
  architecture.

Our approach is better suited for the *discovery* phase (what types exist?),
while WhyHow's is better suited for the *extraction* phase (find all instances
of known types). Since US020 targets discovery, our structured-output approach
is the right choice.

The most actionable finding is the **reinforcement of the `response_format`
gap** (I1 from the review doc). WhyHow's knowledge-table evolved from manual
JSON parsing to native structured output for exactly the reliability reasons
we identified.

## References

- [knowledge-graph-studio](https://github.com/whyhow-ai/knowledge-graph-studio) — `src/whyhow_api/utilities/builders.py`
- [knowledge-table](https://github.com/whyhow-ai/knowledge-table) — `backend/src/app/models/llm_responses.py`
- [schemas](https://github.com/whyhow-ai/schemas) — domain schema templates
- [whyhow (deprecated SDK)](https://github.com/whyhow-ai/whyhow) — schema generation from questions
