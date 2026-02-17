# US009: Text Graph Builder - Scalability Analysis & Improvements

## Overview

This document analyzes the scalability characteristics of the Text Graph Builder (US009) and proposes improvements for handling large document collections.

**Created**: 2026-02-12
**Status**: Analysis Complete, Improvements Proposed
**Related**: [US009_text_graph_builder.md](../user_stories/US009_text_graph_builder.md)

---

## Current Architecture Scalability

The Text Graph Builder has two distinct layers with different scalability characteristics:

### Layer 1: NER Discovery (Entity Type Discovery)

**Purpose**: Identify which entity types exist in the corpus

**Scalability**: ✅ **Excellent**

**Why it scales well**:

1. **Structure-aware sampling** - Uses `build_structured_preview()` to extract only N lines per markdown section:
   ```python
   # tools/extraction_tools.py:32-87
   def build_structured_preview(file_path, lines_per_section=2):
       """Parse headings, extract N lines per section"""
       for section in sections:
           lines = section["lines"][:lines_per_section]  # Only first 2 lines!
   ```

2. **Line truncation** - Max 200 chars per line to prevent token bloat

3. **Result**: A 10MB markdown file → ~2KB preview in system prompt

**Performance**:
- Document size: Irrelevant (samples structure, not content)
- Processing time: O(n) where n = number of sections, not file size
- Cost: ~$0.01 per corpus (single API call)

### Layer 2: Entity Extraction (SimpleKGPipeline)

**Purpose**: Extract specific entity instances from full document text

**Scalability**: ⚠️ **Limited by chunking strategy**

**Current implementation**:

```python
# pipelines/text_builder.py:164-201
def make_kg_pipeline(state, neo4j_driver, file_path):
    return SimpleKGPipeline(
        llm=OpenAILLM(model_name="gpt-4o"),
        embedder=OpenAIEmbeddings(model="text-embedding-3-large"),
        text_splitter=RegexTextSplitter("---"),  # ← BOTTLENECK
        # ... other config
    )
```

**How it works**:

1. **Chunking** - Splits document using `RegexTextSplitter("---")`
2. **Per-chunk extraction**:
   ```
   Document (10MB)
   → Split on "---" delimiter
   → For each chunk:
       - Extract entities (GPT-4o API call)
       - Generate embeddings (OpenAI API call)
       - Write to Neo4j (Chunk + Entity nodes)
   ```

3. **Sequential processing** - One file at a time to avoid Neo4j contention

---

## Scalability Analysis by Document Size

| Document Size | NER Discovery | Entity Extraction | Cost | Time | Issues |
|---------------|---------------|-------------------|------|------|--------|
| **Small** (< 50KB, ~10 pages) | ✅ Negligible | ✅ 1-5 chunks | $0.10-0.50 | 30-60s | None |
| **Medium** (50KB-500KB, ~100 pages) | ✅ Negligible | ⚠️ 10-50 chunks | $1-5 | 5-10m | Risk if no `---` delimiters |
| **Large** (500KB-5MB, ~1000 pages) | ✅ Negligible | ⚠️ 100-500 chunks | $10-50 | 30-60m | Context overflow risk |
| **Very Large** (> 5MB) | ✅ Negligible | ❌ 500+ chunks | $50+ | Hours | Rate limits, high cost |

---

## Current Bottlenecks

### 1. Hardcoded Regex Chunking Strategy

**Problem**: `RegexTextSplitter("---")` relies on document structure:

```python
# pipelines/text_builder.py:56-66
class RegexTextSplitter(TextSplitter):
    def __init__(self, pattern: str):
        self.re = pattern

    async def run(self, text: str) -> TextChunks:
        texts = re.split(self.re, text)  # ← Splits on fixed pattern
        chunks = [TextChunk(text=str(t), index=i) for i, t in enumerate(texts)]
        return TextChunks(chunks=chunks)
```

**Failure scenarios**:

- ❌ Document has no `---` delimiters → 1 giant chunk → context window overflow
- ❌ Document has `---` every 100 pages → chunks too large
- ❌ Document has `---` every paragraph → too many chunks (cost bloat)

**Impact**:
- Unpredictable chunk sizes
- Unpredictable costs
- Risk of extraction failure for poorly structured documents

### 2. Sequential File Processing

**Current behavior**:

```python
# pipelines/text_builder.py:434
for i, file_path in enumerate(files_to_process, 1):
    file_result = await _process_single_file(...)  # ← One at a time
```

**Impact**:
- 10 files × 5 minutes each = 50 minutes total
- Cannot leverage async I/O parallelism
- Idle time during API calls

### 3. No Token-Based Size Limiting

**Problem**: No enforcement of maximum chunk size in tokens

**Risk**:
- GPT-4o context window: ~128K tokens
- A single section between `---` delimiters could be 200KB
- Would exceed context window → extraction fails

---

## Proposed Improvements

### Priority 1: Token-Aware Chunking (High Priority)

**Goal**: Replace regex splitter with token-based chunking

**Implementation**:

```python
# Use neo4j-graphrag's built-in token-aware splitter
from neo4j_graphrag.experimental.components.text_splitters.fixed_size_splitter import FixedSizeSplitter

def make_kg_pipeline(state, neo4j_driver, file_path, chunk_size=4000, chunk_overlap=200):
    return SimpleKGPipeline(
        llm=llm,
        embedder=embedder,
        text_splitter=FixedSizeSplitter(
            chunk_size=chunk_size,      # tokens per chunk (configurable)
            chunk_overlap=chunk_overlap # overlap for context continuity
        ),
        # ... rest of config
    )
```

**Benefits**:
- ✅ Handles documents of ANY size
- ✅ Prevents context window overflow
- ✅ Predictable cost per document (cost ∝ document tokens ÷ chunk_size)
- ✅ Maintains semantic continuity via overlap

**Estimated effort**: 2-3 hours
- Verify `FixedSizeSplitter` exists in neo4j-graphrag
- Update `make_kg_pipeline()` signature
- Add configuration parameters to MCP tool
- Update tests

### Priority 2: Configurable Chunking Strategy (High Priority)

**Goal**: Allow users to choose chunking strategy per document type

**Implementation**:

```python
def make_kg_pipeline(
    state,
    neo4j_driver,
    file_path,
    chunking_strategy="token_based",  # "token_based" | "regex" | "semantic"
    **chunking_params
):
    if chunking_strategy == "token_based":
        splitter = FixedSizeSplitter(
            chunk_size=chunking_params.get("chunk_size", 4000),
            chunk_overlap=chunking_params.get("chunk_overlap", 200)
        )
    elif chunking_strategy == "regex":
        splitter = RegexTextSplitter(
            pattern=chunking_params.get("pattern", "---")
        )
    elif chunking_strategy == "semantic":
        # Future: split on semantic boundaries (paragraphs, sections)
        pass

    return SimpleKGPipeline(text_splitter=splitter, ...)
```

**Benefits**:
- ✅ Flexibility for different document types
- ✅ Backward compatible (regex still available)
- ✅ Future-proof (can add semantic chunking)

**Estimated effort**: 3-4 hours

### Priority 3: Parallel File Processing (Medium Priority)

**Goal**: Process multiple files concurrently

**Implementation**:

```python
# pipelines/text_builder.py
async def build_text_graph(state, driver, message="all", max_parallel=3):
    """Process up to N files in parallel"""

    files_to_process = _resolve_files_to_process(state, message)

    # Process in batches to avoid rate limits
    for batch in _batched(files_to_process, max_parallel):
        tasks = [
            _process_single_file(driver, state, file_path, data_dir)
            for file_path in batch
        ]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle results and update progress
        for file_path, result in zip(batch, batch_results):
            # ... update state, handle errors
```

**Considerations**:
- ⚠️ Neo4j connection pool management (multiple concurrent writes)
- ⚠️ OpenAI API rate limits (10-100 requests/second depending on tier)
- ⚠️ Memory usage (multiple files in memory)

**Benefits**:
- ✅ 3-5x speedup for multiple files
- ✅ Better resource utilization

**Estimated effort**: 4-6 hours
- Implement batching logic
- Test Neo4j concurrent writes
- Add error handling for parallel failures
- Monitor OpenAI rate limits

### Priority 4: Progress Tracking for Large Files (Low Priority)

**Goal**: Show chunk-level progress for large documents

**Implementation**:

```python
# In _process_single_file():
async def _process_single_file(neo4j_driver, state, file_path, data_dir, progress_callback=None):
    pipeline = make_kg_pipeline(state, neo4j_driver, full_path)

    # Hook into pipeline's chunk processing
    total_chunks = estimate_chunks(full_path, chunk_size=4000)

    async for chunk_index, chunk_result in pipeline.run_async_with_progress(full_path):
        if progress_callback:
            progress_callback(chunk_index, total_chunks)

    return result
```

**Benefits**:
- ✅ User visibility into long-running operations
- ✅ Early detection of failures (fail fast on chunk 1, not after all chunks)

**Estimated effort**: 4-6 hours (requires understanding SimpleKGPipeline internals)

### Priority 5: Streaming Extraction (Future/Research)

**Goal**: Process arbitrarily large documents with constant memory

**Concept**:

```python
async def stream_extract(file_path, chunk_size=4000):
    """Process document in streaming fashion"""
    async for chunk in stream_chunks(file_path, chunk_size):
        entities = await extract_entities(chunk)
        await write_to_neo4j(entities)
        # Chunk is garbage collected, memory stays constant
```

**Benefits**:
- ✅ Constant memory usage (O(1) instead of O(n))
- ✅ Can process GB-sized documents

**Challenges**:
- ⚠️ Complex implementation
- ⚠️ May require changes to SimpleKGPipeline
- ⚠️ Entity resolution across chunks is harder

**Estimated effort**: 2-3 days (research + implementation)

---

## Practical Workarounds (No Code Changes)

For current system users who encounter scalability issues:

### 1. Structure Markdown Files with Delimiters

Add `---` delimiters every 2-5 pages:

```markdown
# Section 1
Content here (2-5 pages)...

---

# Section 2
More content (2-5 pages)...

---
```

**Target**: Chunks of 2000-5000 tokens (~1500-4000 words)

### 2. Split Very Large Files Before Processing

Use file splitting tools:

```bash
# Split 10MB file into 1MB chunks
csplit large_file.md '/^---$/' '{*}'
```

**Target**: < 500KB per file (~ 125K tokens)

### 3. Process Files One at a Time

Use MCP tool's message parameter:

```python
# Instead of:
kg_build_graph(message="all", scope="unstructured")

# Do:
kg_build_graph(message="file1.md", scope="unstructured")
kg_build_graph(message="file2.md", scope="unstructured")
# ... etc
```

**Benefit**: Better control, easier to resume after failures

---

## Real-World Example: 10 Files × 2MB Each

**Scenario**: 10 markdown files, each 2MB (~500K tokens), total 20MB

### Current System Performance

**NER Discovery**:
- Files analyzed: 10 files (structure preview only)
- API calls: 1
- Cost: ~$0.01
- Time: 10 seconds
- Scalability: ✅ **Excellent**

**Entity Extraction** (assuming well-structured with `---` every 5 pages):
- Chunks per file: ~50 (if 10 pages × 5 `---` delimiters)
- Total chunks: 500
- API calls: 500 × 2 (extraction + embeddings) = 1000
- Cost: ~$50-100
- Time: 2-3 hours (sequential)
- Scalability: ⚠️ **Limited** (sequential processing)

### Optimized System Performance (After Improvements)

**NER Discovery**: Same (already optimal)

**Entity Extraction** (with token-based chunking + parallel processing):
- Chunks per file: ~125 (2MB ÷ 4000 tokens = ~125 chunks)
- Total chunks: 1250
- API calls: 2500 (extraction + embeddings)
- Cost: ~$125-150 (higher due to finer chunking, but predictable)
- Time: 20-30 minutes (3 files in parallel)
- Scalability: ✅ **Good** (predictable cost, faster, handles any size)

**Trade-off analysis**:
- Cost increases by 25-50% (finer chunking)
- Time decreases by 75-85% (parallel processing)
- Reliability increases significantly (no context overflow risk)

---

## Implementation Roadmap

### Phase 1: Quick Wins (Week 1)

1. ✅ Add `FixedSizeSplitter` as default chunking strategy
2. ✅ Make chunk_size and chunk_overlap configurable
3. ✅ Add documentation and examples
4. ✅ Update unit tests

**Effort**: 1-2 days
**Impact**: Eliminates context overflow risk

### Phase 2: Configurability (Week 2)

1. ✅ Support multiple chunking strategies (token, regex, semantic)
2. ✅ Add chunking strategy parameter to MCP tool
3. ✅ Add configuration validation
4. ✅ Update integration tests

**Effort**: 2-3 days
**Impact**: Flexibility for different document types

### Phase 3: Performance (Week 3)

1. ✅ Implement parallel file processing with batching
2. ✅ Add Neo4j connection pool management
3. ✅ Add OpenAI rate limit handling
4. ✅ Performance benchmarking

**Effort**: 3-4 days
**Impact**: 3-5x speedup for multiple files

### Phase 4: UX (Week 4)

1. ✅ Add chunk-level progress tracking
2. ✅ Add estimation of time/cost before processing
3. ✅ Add resumable processing (save progress, resume after failure)

**Effort**: 3-4 days
**Impact**: Better user experience for long operations

---

## Success Metrics

### Before Improvements

- ❌ Context overflow risk for large documents
- ❌ Unpredictable cost (depends on `---` delimiter placement)
- ❌ Sequential processing only
- ⚠️ No progress visibility

### After Phase 1 (Token-Based Chunking)

- ✅ Handles documents of any size
- ✅ Predictable cost (tokens ÷ chunk_size)
- ❌ Still sequential processing
- ⚠️ No progress visibility

### After Phase 3 (Parallel Processing)

- ✅ Handles documents of any size
- ✅ Predictable cost
- ✅ 3-5x faster for multiple files
- ⚠️ No progress visibility

### After Phase 4 (Full UX)

- ✅ Handles documents of any size
- ✅ Predictable cost
- ✅ 3-5x faster for multiple files
- ✅ Real-time progress tracking
- ✅ Resumable after failures

---

## Conclusion

The Text Graph Builder's **NER Discovery layer is already highly scalable** due to structure-aware sampling. However, the **Entity Extraction layer needs improvements** to handle large document collections reliably and efficiently.

**Recommended priority**:

1. **Token-based chunking** (eliminates context overflow risk)
2. **Configurable chunking strategy** (flexibility for different documents)
3. **Parallel file processing** (significant speedup)
4. **Progress tracking** (UX improvement)

**Total estimated effort**: 2-3 weeks for all phases

**Expected outcomes**:
- Reliable processing of documents of any size
- 3-5x speedup for multiple files
- Predictable costs
- Better user experience

---

## References

- [US009 User Story](../user_stories/US009_text_graph_builder.md)
- [text_builder.py](../../pipelines/text_builder.py)
- [extraction_tools.py](../../tools/extraction_tools.py)
- [SimpleKGPipeline Documentation](https://neo4j.com/docs/neo4j-graphrag-python/current/)
