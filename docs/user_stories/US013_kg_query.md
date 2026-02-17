# US013: Query Infrastructure & kg_query Tool

## User Story

**As a** KG-Factory User
**I want** to query the knowledge graph with natural language questions using a unified tool that automatically selects the best retrieval strategy
**So that** I can get answers from my graph without needing to understand vector search, Cypher, or cross-layer traversal

## Story Points: 8

## Status: Not Started

## Acceptance Criteria

### Index Auto-Creation Enhancement

- [ ] Indexes auto-created in `_build_unstructured()` after first successful file (vector + fulltext)
- [ ] Index creation is idempotent (checks if exists before creating)
- [ ] Index creation is non-blocking (build succeeds even if index creation fails)
- [ ] Clear error guidance if index creation fails (permissions issues):
  ```
  Indexes:
    [WARN] chunk-embeddings: error: Insufficient privileges
    [WARN] chunk-fulltext: error: Insufficient privileges

  Note: Query tools require these indexes.
  Ask your Neo4j administrator to create them or grant CREATE INDEX privileges.
  ```
- [ ] No manual index creation tool exposed (operational concern, not workflow)

### Internal Retrieval Strategies

All implemented as internal functions in `pipelines/query_builder.py` (NOT exposed as MCP tools):

- [ ] `_execute_schema_query(driver, state)` → Get graph schema with dynamic layer classification from `approved_construction_plan`
- [ ] `_execute_cypher(driver, query)` → Execute read-only Cypher with mutation keyword blocking
- [ ] `_execute_vector_search(driver, question, top_k)` → Semantic search via `VectorRetriever` from neo4j-graphrag
- [ ] `_execute_hybrid_search(driver, question, top_k)` → Vector + fulltext via `HybridRetriever` from neo4j-graphrag
- [ ] `_execute_cross_layer_traversal(driver, question, top_k)` → Lexical → Subject → Domain via `VectorCypherRetriever`
- [ ] All strategies use proper driver management (per-call, close in finally)
- [ ] All strategies return unified format: `{answer, evidence, confidence, details}`

### Claude-Powered Strategy Selection

- [ ] `_select_retrieval_strategy(question, context, state)` uses Claude API to analyze questions
- [ ] Strategy selector has access to schema context from state (domain labels, entity types, fact types)
- [ ] Returns JSON: `{strategy: "schema|cypher|vector|hybrid|cross_layer", reasoning: str, generated_query?: str}`
- [ ] For Cypher strategy, generates the query (read-only, validated)
- [ ] Clear system prompt explains each strategy with examples
- [ ] Uses `claude-sonnet-4-20250514` model

### kg_query MCP Tool

- [ ] Tool signature: `kg_query(question: str, context: str = "")`
- [ ] Tool description clearly states it's for getting ANSWERS (not evaluation)
- [ ] Returns: `{answer: str, evidence: list, strategy_used: str, confidence: float, query_details: dict}`
- [ ] Loads state via `_load_clean_state()` for schema context
- [ ] Creates driver via `get_neo4j_driver()`, closes in `finally`
- [ ] Calls `_select_retrieval_strategy()` to choose approach
- [ ] Executes selected strategy via `_execute_*()` functions
- [ ] Decorated with `@mcp.tool` and `@mcp_traceable(name="mcp.kg_query")`
- [ ] Confidence score calculation based on evidence quality (0.0-1.0)

### Helper Functions

In `tools/query_tools.py`:

- [ ] `_get_domain_labels(state)` → Extract domain labels from `approved_construction_plan`
- [ ] `format_cypher_results(records)` → Format Cypher results for display
- [ ] `format_retriever_results(items)` → Format retriever results for display
- [ ] `calculate_confidence(evidence, strategy)` → Compute confidence score based on evidence quality

### Error Handling

- [ ] Missing indexes: Clear error with suggestion to check build output or contact admin
- [ ] Missing OPENAI_API_KEY: Clear error for vector/hybrid/cross-layer strategies
- [ ] Invalid Cypher: Return error with query validation details
- [ ] Neo4j connection failures: Actionable error messages
- [ ] Strategy selection failures: Fallback to vector search with warning

### Integration Patterns

- [ ] Follows existing MCP tool pattern (same as `kg_build_graph`, `kg_user_intent`)
- [ ] Uses `utils.get_neo4j_driver()` and `utils.close_driver()` (existing pattern)
- [ ] Uses `core.tracing.mcp_traceable` for observability (US011 pattern)
- [ ] Uses `_load_clean_state()` from mcp_server for state access
- [ ] No hardcoded values (domain labels read from state, not hardcoded)

## Definition of Done

- [ ] Code implemented and working
- [ ] Unit tests for all retrieval strategies (mock Neo4j driver)
- [ ] Unit tests for strategy selection (mock Claude API)
- [ ] Unit tests for helper functions
- [ ] Integration test: `test_08_kg_query.py` demonstrates all strategies
- [ ] All existing tests still pass (45+ unit tests)
- [ ] Index auto-creation verified (creates indexes, handles failures gracefully)
- [ ] MCP tool works from Claude Code
- [ ] Observability verified (traces visible in LangSmith if enabled)
- [ ] Code reviewed
- [ ] Documentation in code (docstrings for all functions)

## Technical Notes

### Architecture

```
kg_query(question, context)
  |
  +-> _load_clean_state()                 # Get schema context
  +-> get_neo4j_driver()                  # Create driver
  +-> _select_retrieval_strategy()        # Claude API call
  |     |
  |     +-> Analyze question
  |     +-> Read domain labels, entity types, fact types from state
  |     +-> Return: {strategy, reasoning, generated_query?}
  |
  +-> Execute strategy:
        |
        +-> "schema"      -> _execute_schema_query()
        +-> "cypher"      -> _execute_cypher()
        +-> "vector"      -> _execute_vector_search()
        +-> "hybrid"      -> _execute_hybrid_search()
        +-> "cross_layer" -> _execute_cross_layer_traversal()
  |
  +-> close_driver()                      # Always in finally
  +-> Return: {answer, evidence, strategy_used, confidence, query_details}
```

### Files to Create

```
pipelines/
  query_builder.py                # NEW: Internal retrieval strategies

tools/
  query_tools.py                  # NEW: Helper functions

tests/
  test_08_kg_query.py             # NEW: Interactive integration test
  unit/
    test_query_builder.py         # NEW: Unit tests for retrieval strategies
    test_query_tools.py           # NEW: Unit tests for helpers
    test_index_creation.py        # NEW: Unit tests for index auto-creation
```

### Files to Modify

```
mcp_server/server.py              # UPDATE: Add index auto-creation to _build_unstructured()
                                  #         Add _create_text_indexes() helper
                                  #         Add _format_index_results() helper
                                  #         Add kg_query MCP tool

requirements.txt                  # VERIFY: neo4j-graphrag>=1.0.0, openai>=1.0.0 (already from US009)
```

### Component Specifications

#### 1. Index Auto-Creation (in `mcp_server/server.py`)

Add after line 897, before `kg_build_graph`:

```python
def _create_text_indexes(driver) -> dict:
    """Create vector and fulltext indexes for text graph queries.

    Idempotent: checks if indexes exist before creating.
    Non-blocking: returns status per index (created/exists/error).

    Args:
        driver: Neo4j driver instance.

    Returns:
        Dict mapping index name to status string.
    """
    results = {}

    with driver.session() as session:
        # Vector index (3072 dimensions, cosine similarity)
        try:
            session.run("""
                CREATE VECTOR INDEX `chunk-embeddings` IF NOT EXISTS
                FOR (c:Chunk) ON (c.embedding)
                OPTIONS {
                  indexConfig: {
                    `vector.dimensions`: 3072,
                    `vector.similarity_function`: 'cosine'
                  }
                }
            """)
            results["chunk-embeddings"] = "created"
        except Exception as e:
            try:
                existing = session.run(
                    "SHOW INDEXES YIELD name WHERE name = 'chunk-embeddings'"
                ).single()
                results["chunk-embeddings"] = "exists" if existing else f"error: {e}"
            except Exception:
                results["chunk-embeddings"] = f"error: {e}"

        # Fulltext index
        try:
            session.run("""
                CREATE FULLTEXT INDEX `chunk-fulltext` IF NOT EXISTS
                FOR (c:Chunk) ON EACH [c.text]
            """)
            results["chunk-fulltext"] = "created"
        except Exception as e:
            try:
                existing = session.run(
                    "SHOW INDEXES YIELD name WHERE name = 'chunk-fulltext'"
                ).single()
                results["chunk-fulltext"] = "exists" if existing else f"error: {e}"
            except Exception:
                results["chunk-fulltext"] = f"error: {e}"

    return results
```

#### 2. Strategy Selection (in `pipelines/query_builder.py`)

```python
def _select_retrieval_strategy(question: str, context: str, state: dict) -> dict:
    """Use Claude API to analyze question and select retrieval strategy.

    Args:
        question: User's natural language question
        context: Optional context provided by user
        state: Current pipeline state (for schema info)

    Returns:
        Dict with "strategy" key and optional "generated_query" for Cypher
    """
    from tools.query_tools import _get_domain_labels
    import anthropic
    import json

    # Get schema context from state
    domain_labels = _get_domain_labels(state)
    entity_types = list(state.get("approved_entity_types", {}).keys())
    fact_types = list(state.get("approved_fact_types", {}).keys())

    system_prompt = f"""You are a query strategy selector for a three-layer knowledge graph.

Graph Structure:
- Domain Layer: {', '.join(sorted(domain_labels)) if domain_labels else 'No domain nodes yet'}
- Subject Layer: Entity types: {', '.join(entity_types) if entity_types else 'No entities yet'}
- Lexical Layer: Documents and Chunks (with embeddings)

Cross-layer relationships:
- CORRESPONDS_TO: Subject entities → Domain nodes
- MENTIONED_IN: Subject entities → Lexical chunks

Analyze the question and select the BEST retrieval strategy:

1. "schema" - For meta-questions about the graph itself
   Examples: "What's in the graph?", "Show me the structure", "What labels exist?"

2. "cypher" - For precise queries requiring structured data
   Examples: "How many suppliers?", "List all products", "Average price of X"
   If selected, generate the Cypher query (READ-ONLY, no mutations)

3. "vector" - For exploratory/semantic questions without specific identifiers
   Examples: "Tell me about quality issues", "What are the main themes?"

4. "hybrid" - For queries with specific identifiers + semantic meaning
   Examples: "Quality issues with batch #2024-0871", "Problems in supplier X"

5. "cross_layer" - For questions spanning structured and unstructured data
   Examples: "Which suppliers mentioned in negative reviews?", "Root cause of defects?"

Additional context: {context if context else "None provided"}

Return ONLY valid JSON:
{{"strategy": "schema|cypher|vector|hybrid|cross_layer", "reasoning": "brief explanation", "generated_query": "MATCH ... RETURN ..." (only if strategy=cypher)}}
"""

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": question}]
    )

    return json.loads(response.content[0].text)
```

#### 3. Vector Search Strategy (example)

```python
def _execute_vector_search(driver, question: str, top_k: int = 5) -> dict:
    """Semantic search using VectorRetriever.

    Args:
        driver: Neo4j driver instance
        question: Natural language query
        top_k: Number of results to return

    Returns:
        Dict with answer, evidence, confidence, details
    """
    from neo4j_graphrag.retrievers import VectorRetriever
    from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings
    import os

    try:
        embedder = OpenAIEmbeddings(
            model="text-embedding-3-large",
            api_key=os.environ.get("OPENAI_API_KEY"),
        )

        retriever = VectorRetriever(
            driver=driver,
            index_name="chunk-embeddings",
            embedder=embedder,
            return_properties=["text", "index"],
        )

        result = retriever.search(query_text=question, top_k=top_k)

        # Format evidence
        evidence = [
            {
                "text": item.content,
                "score": item.metadata.get("score"),
                "source": item.metadata.get("path"),
            }
            for item in result.items
        ]

        # Calculate confidence based on top score
        confidence = evidence[0]["score"] if evidence else 0.0

        # Synthesize answer from top results
        answer = f"Found {len(evidence)} relevant passages. " + \
                 (evidence[0]["text"][:200] + "..." if evidence else "No results found.")

        return {
            "answer": answer,
            "evidence": evidence,
            "confidence": confidence,
            "details": {"retriever": "vector", "top_k": top_k}
        }

    except Exception as e:
        return {
            "answer": f"Vector search failed: {str(e)}",
            "evidence": [],
            "confidence": 0.0,
            "details": {"error": str(e), "hint": "Check if chunk-embeddings index exists"}
        }
```

### Cross-Layer Traversal Query

```cypher
// Used by _execute_cross_layer_traversal via VectorCypherRetriever
// $node_id and $score are injected by VectorCypherRetriever

WITH node AS chunk, score

// Get source document
OPTIONAL MATCH (doc:Document)-[:HAS_CHUNK]->(chunk)

// Traverse to Subject layer: entities mentioned in this chunk
OPTIONAL MATCH (entity:__Entity__)-[:MENTIONED_IN]->(chunk)

// Traverse to Domain layer: corresponding domain nodes
OPTIONAL MATCH (entity)-[:CORRESPONDS_TO]->(domain)

// Expand domain context (1 hop)
OPTIONAL MATCH (domain)-[domain_rel]-(domain_neighbor)

RETURN chunk.text AS chunk_text,
       score AS similarity_score,
       doc.path AS source_document,
       chunk.index AS chunk_index,
       collect(DISTINCT {
           entity: entity.name,
           entity_labels: labels(entity),
           domain_node: domain.name,
           domain_labels: labels(domain),
           domain_neighbor: domain_neighbor.name,
           domain_rel_type: type(domain_rel)
       }) AS traversal_paths
```

## Dependencies

- **US009**: Text Graph Builder (provides Chunk nodes with embeddings)
- **US011**: LangSmith Observability (provides @mcp_traceable decorator)
- Existing `utils/neo4j_utils.py` (driver management)
- Existing `core/state.py` (state management)

## Out of Scope

- Competency question evaluation (covered in US014)
- Manual index creation tool (operational concern, not workflow)
- Query result caching (future enhancement)
- Query history tracking (future enhancement)
- Custom retriever configurations (future enhancement)
- Multi-hop reasoning beyond cross-layer traversal (future enhancement)
- Multi-strategy execution (future enhancement, see below)

## Future Improvement: Multi-Strategy Execution

### Problem

The current strategy selector picks a **single** retrieval strategy per query.
Some questions benefit from multiple strategies run in parallel:

- "What quality issues did @home_chef report about products?" needs:
  - **hybrid** for precise `@home_chef` keyword matching
  - **cross_layer** for entity traversal to domain Product nodes
  - **cypher** for structured aggregation (count by product, average rating)

Running only one strategy loses information the others would have found.

### Proposed Design

Allow the strategy selector to return multiple strategies:

```json
{
  "strategies": [
    {"strategy": "hybrid", "parameters": {"top_k": 10}},
    {"strategy": "cross_layer", "parameters": {"top_k": 5}}
  ],
  "reasoning": "Keyword '@home_chef' needs fulltext matching. Entity traversal
                needed to connect reviews to domain product data."
}
```

### Architecture

```
Question
    |
    v
Strategy Selector (Claude)
    |
    v (returns 1-3 strategies)
    |
    +---> Strategy A (e.g. hybrid)     ---> Results A
    |                                        |
    +---> Strategy B (e.g. cross_layer) ---> Results B
    |                                        |
    v                                        v
Result Merger
    |
    +-- Deduplicate by chunk text (same chunk from different strategies)
    +-- Union unique results
    +-- Re-rank merged set by combined score
    +-- Cap at top_k
    |
    v
Merged Response
```

### Key Design Decisions

1. **Max strategies per query**: 2-3 (diminishing returns beyond that)
2. **Parallel execution**: Run strategies concurrently with `asyncio.gather()`
3. **Deduplication**: Match on chunk text hash; keep highest-scoring occurrence
4. **Score normalization**: Each strategy produces scores on different scales
   (cosine similarity vs fulltext BM25). Normalize to 0-1 before merging.
5. **Confidence**: Weighted average of per-strategy confidence scores
6. **Backwards compatible**: Single-strategy responses still work unchanged

### Complexity Estimate

- Strategy selector prompt changes: small
- Parallel execution orchestrator: medium
- Result deduplication and merging: medium
- Score normalization across strategies: medium
- Tests: medium

Story points: 5

### When to Implement

After validating that the HybridCypherRetriever swap (which gives cross_layer
keyword matching) is insufficient for real-world query patterns. The swap
covers the most common case; multi-strategy is for edge cases where
fundamentally different retrieval approaches need to be combined.
