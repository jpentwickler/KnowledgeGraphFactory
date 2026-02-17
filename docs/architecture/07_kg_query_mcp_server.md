# KG Query & Evaluation Tools — Design & Implementation

> **REVISION HISTORY**
> - **Original**: Separate `kg-query-mcp` server with 8 query tools (created with Claude Desktop, missing project context)
> - **Revised**: Integrated into existing `mcp_server/server.py` with **2 unified tools** following KG-Factory patterns
> - **Key Changes**: Single `kg_query` tool (Claude-powered strategy selection), US012 CQ integration, auto-only index creation (no manual tool), dynamic layer classification, proper driver management

---

## Architecture Overview

The KG Query tools expose the three-layer knowledge graph (Domain–Subject–Lexical) as MCP tools integrated into the existing KG-Factory MCP server. Since Claude Code **is** the agent, we expose retrieval primitives and evaluation tools and let Claude reason about which to call.

**ARCHITECTURAL DECISION**: These tools are **integrated into the existing `mcp_server/server.py`**, not a separate MCP server. This follows the established pattern of exposing all KG-Factory capabilities through a single unified MCP interface.

```
┌─────────────────────────────────────────────────────────┐
│  Claude Code (Agent / Orchestrator)                     │
│                                                         │
│  • Reads competency questions from state                │
│  • Selects retrieval strategy per question              │
│  • Chains tools if needed                               │
│  • Evaluates answer quality                             │
│                                                         │
│     ┌──────────────────────────────────────────┐        │
│     │ KG-Factory MCP Server (Single Unified)   │        │
│     │                                           │        │
│     │  Construction Tools  │  Query Tools      │        │
│     │  • kg_user_intent    │  • kg_schema      │        │
│     │  • kg_schema_...     │  • kg_vector_...  │        │
│     │  • kg_build_graph    │  • kg_evaluate... │        │
│     │  • kg_critic         │  • kg_cypher_...  │        │
│     └─────────────┬─────────────────────────────┘        │
└───────────────────┼───────────────────────────────────────┘
                    │ stdio
       ┌────────────▼────────────┐
       │  KG-Factory MCP Server  │
       │  (mcp_server/server.py) │
       │                         │
       │  Reads: state/          │     ┌─────────────────┐
       │         current_state   │────►│  Neo4j Database │
       │                         │     │  (3-layer KG)   │
       │  Uses: utils/           │     └─────────────────┘
       │        neo4j_utils      │
       │        core/tracing     │────► LangSmith (optional)
       │                         │
       │  Embedder via OpenAI    │────► OpenAI API
       └─────────────────────────┘
```

## Integration Patterns

### State Management
All query tools follow the existing state management pattern:
- Read from `state/current_state.json` via `_load_clean_state()`
- Access approved artifacts: `approved_construction_plan`, `approved_entity_types`, `approved_competency_questions`
- Store evaluation results: `state["cq_evaluation_results"]` for persistence

### Driver Management
Follow the existing `utils.neo4j_utils` pattern:
```python
from utils import get_neo4j_driver, close_driver

driver = get_neo4j_driver()
try:
    # ... query operations ...
finally:
    close_driver(driver)
```
**Critical**: Never create global drivers. Always close in try/finally.

### Tracing Integration
All tools use `@mcp_traceable` from `core.tracing`:
```python
from core.tracing import mcp_traceable

@mcp.tool
@mcp_traceable(name="mcp.kg_vector_search")
def kg_vector_search(...):
    ...
```

### Layer Classification
Domain labels are **not hardcoded**—they are read from `approved_construction_plan`:
```python
def _get_domain_labels(state: dict) -> set[str]:
    """Extract domain layer labels from approved construction plan."""
    plan = state.get("approved_construction_plan", {})
    return {
        entry["label"]
        for entry in plan.values()
        if entry.get("construction_type") == "node"
    }
```

---

## MCP Tools Exposed

**Simplified Design**: Only **2 user-facing tools** focused on the knowledge graph workflow.

### 1. `kg_query` — Unified Query Interface

**Single entry point** for all knowledge graph queries. Internally uses Claude API to analyze the question and select the optimal retrieval strategy (schema introspection, Cypher, vector search, hybrid search, or cross-layer traversal).

```
Input:  {
    question: str,    # Natural language question about the graph
    context?: str     # Optional context to guide strategy selection
}
Output: {
    answer: str,              # Natural language answer
    evidence: [...],          # Supporting evidence from the graph
    strategy_used: str,       # "schema" | "cypher" | "vector" | "hybrid" | "cross_layer"
    confidence: float,        # 0.0 - 1.0
    query_details: {...}      # Strategy-specific details (query used, results, etc.)
}
```

**How it works**:
1. Uses Claude API to analyze the question and understand intent
2. Selects best retrieval strategy based on question type and available data
3. Executes the query using the selected strategy
4. Returns synthesized answer with evidence

**State Integration**:
- Reads `approved_construction_plan` for domain layer classification
- Reads `approved_entity_types` and `approved_fact_types` for context
- Can generate Cypher queries referencing the actual schema

**Strategy Selection Examples**:
- "What labels are in the graph?" → **schema** introspection
- "How many suppliers are there?" → **cypher** (COUNT query)
- "Tell me about quality issues" → **vector** (semantic search)
- "Quality issues with batch #2024-0871" → **hybrid** (keyword + semantic)
- "Which suppliers might be responsible for defects?" → **cross_layer** (text → entities → domain)

### 2. `kg_evaluate_cqs` — Evaluate Approved Competency Questions

Evaluates approved competency questions from state (single, subset, or all). Tests answerability by trying multiple retrieval strategies and gathering evidence. **Does not return answers**, only assessment metrics.

**IMPORTANT**: This tool works ONLY with approved CQs from state. For ad-hoc questions, use `kg_query` (which returns answers + confidence scores).

```
Input:  {
    cq_id?: str,            # Single approved CQ ID (e.g., "CQ3")
    cq_ids?: list[str],     # List of approved CQ IDs (e.g., ["CQ1", "CQ3"])
                            # If neither provided: evaluates ALL approved CQs
}

Output (single CQ):  {
    cq_id: str,
    question: str,
    category: str,
    priority: str,
    evidence_found: bool,
    strategies_tried: [...],
    evidence_count: int,
    has_cross_layer_bridge: bool,
    assessment: {
        status: "answerable" | "partial" | "not_answerable",
        note: str
    }
}

Output (multiple CQs):  {
    total: int,
    answerable: int,
    partial: int,
    not_answerable: int,
    coverage_score: float,      # (answerable + 0.5*partial) / total
    per_cq_results: [
        {
            cq_id: str,
            question: str,
            status: "answerable" | "partial" | "not_answerable",
            evidence_count: int
        },
        ...
    ]
}
```

**State Integration**:
- Reads `state["approved_competency_questions"]` (US012)
- Uses `kg_query` internally for each CQ (without returning answers, only collecting evidence)
- Stores full results in `state["cq_evaluation_results"]` with timestamp
- Returns assessment (single) or coverage scorecard (batch)

**Why No Ad-hoc Questions?**
- Removes ambiguity: ad-hoc questions always go through `kg_query`
- Clear separation: `kg_query` = get answers, `kg_evaluate_cqs` = test approved CQs
- Users can test questions before approving by using `kg_query` and checking confidence scores

---

## Implementation

### Project Structure (Integrated)

Query and evaluation tools are added to the **existing KG-Factory structure**:

```
kg-factory/
├── mcp_server/
│   └── server.py              # Add query tools here (kg_schema, kg_vector_search, etc.)
│
├── tools/
│   └── query_tools.py         # NEW: Helper functions for query tools
│
├── pipelines/
│   └── query_builder.py       # NEW: Retriever construction & cross-layer logic
│
├── utils/
│   └── neo4j_utils.py         # Existing: get_neo4j_driver(), close_driver()
│
├── core/
│   ├── state.py               # Existing: load_state(), save_state()
│   └── tracing.py             # Existing: @mcp_traceable decorator
│
└── tests/unit/
    ├── test_query_tools.py    # NEW: Unit tests for query functionality
    └── test_index_creation.py # NEW: Unit tests for index management
```

**Key Files Modified**:
- `mcp_server/server.py`: Add 7 new tools (schema, cypher, vector, hybrid, cross-layer, evaluate, create_indexes)
- `requirements.txt`: Already has `neo4j-graphrag>=1.0.0`, `openai>=1.0.0` (from US009)

**Key Files Created**:
- `tools/query_tools.py`: Shared helpers (format results, evidence gathering, layer classification)
- `pipelines/query_builder.py`: Retriever construction, cross-layer traversal logic

---

## Index Management (Auto-Only)

### Automatic Index Creation

Indexes are **automatically created** after the first successful text graph build. No manual tool is exposed—this is purely operational infrastructure.

**Location**: `mcp_server/server.py` in `_build_unstructured()` helper (after line 839)

**Design Principle**: Index creation is an **operational concern**, not part of the knowledge graph workflow. All KG-Factory MCP tools are workflow-focused (design, construction, evaluation), so index management remains internal.

```python
def _create_text_indexes(driver) -> dict:
    """Create vector and fulltext indexes for text graph queries.

    Idempotent: checks if indexes exist before creating.
    Non-blocking: returns status per index (created/exists/error).

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
            existing = session.run(
                "SHOW INDEXES YIELD name WHERE name = 'chunk-embeddings'"
            ).single()
            results["chunk-embeddings"] = "exists" if existing else f"error: {e}"

        # Fulltext index
        try:
            session.run("""
                CREATE FULLTEXT INDEX `chunk-fulltext` IF NOT EXISTS
                FOR (c:Chunk) ON EACH [c.text]
            """)
            results["chunk-fulltext"] = "created"
        except Exception as e:
            existing = session.run(
                "SHOW INDEXES YIELD name WHERE name = 'chunk-fulltext'"
            ).single()
            results["chunk-fulltext"] = "exists" if existing else f"error: {e}"

    return results

# Integrated into _build_unstructured():
async def _build_unstructured(state, driver, message):
    # ... existing validation & build logic ...

    results = await build_text_graph(state, driver, message)
    _save_state(state)

    # Auto-create indexes after first successful file
    if results["files_processed"]:
        index_status = _create_text_indexes(driver)
        results["indexes"] = index_status

    # ... format response including index status ...

    # Format response with index status
    lines.append("\nIndexes:")
    for idx_name, status in results.get("indexes", {}).items():
        if status == "created":
            lines.append(f"  [OK] {idx_name}: created")
        elif status == "exists":
            lines.append(f"  [OK] {idx_name}: already exists")
        else:
            lines.append(f"  [WARN] {idx_name}: {status}")

    # If index creation failed, provide guidance
    if any("error" in str(s) for s in results.get("indexes", {}).values()):
        lines.append("")
        lines.append("Note: Query tools (kg_query) require these indexes to work.")
        lines.append("If index creation failed due to permissions:")
        lines.append("  1. Ask your Neo4j administrator to create the indexes")
        lines.append("  2. Or grant your user CREATE INDEX privileges")
        lines.append("  3. See index creation commands in the build output above")
```

### Error Handling

**If index creation fails** (typically due to insufficient privileges):
- Build succeeds with warnings
- User receives clear guidance:
  ```
  Text graph processing complete!
  Files processed: 3

  Indexes:
    [WARN] chunk-embeddings: error: Insufficient privileges to create index
    [WARN] chunk-fulltext: error: Insufficient privileges to create index

  Note: Query tools (kg_query) require these indexes to work.
  If index creation failed due to permissions:
    1. Ask your Neo4j administrator to create the indexes
    2. Or grant your user CREATE INDEX privileges
    3. See index creation commands in the build output above
  ```

**No manual tool provided** because:
- Index creation is operational, not workflow-related
- If auto-creation fails, root cause (permissions) must be fixed
- Exposing a workaround tool would violate the workflow-focused tool design

---

## Tool Implementation Patterns

### 1. Unified Query Tool with Claude-Powered Strategy Selection

The `kg_query` tool uses **Claude API internally** to analyze questions and select the optimal retrieval strategy:

```python
from utils import get_neo4j_driver, close_driver
from core.tracing import mcp_traceable
import anthropic

@mcp.tool
@mcp_traceable(name="mcp.kg_query")
def kg_query(question: str, context: str = "") -> dict:
    """Get the knowledge graph schema: node labels, relationship types,
    property keys, and node counts. Use this first to understand
    the graph before querying.

    Args:
        layer: Filter by layer - "domain", "subject", "lexical", or "all"
    """
    # Load state for dynamic layer classification
    state = _load_clean_state()

    # Get driver (managed per-tool, not global)
    driver = get_neo4j_driver()
    try:
        with driver.session() as session:
            # Get node labels with counts
            labels_result = session.run("""
                CALL db.labels() YIELD label
                CALL {
                    WITH label
                    MATCH (n) WHERE label IN labels(n)
                    RETURN count(n) AS cnt
                }
                RETURN label, cnt ORDER BY cnt DESC
            """)
            labels = [{"label": r["label"], "count": r["cnt"]}
                      for r in labels_result]

            # Get relationship types with counts
            rels_result = session.run("""
                CALL db.relationshipTypes() YIELD relationshipType AS type
                CALL {
                    WITH type
                    MATCH ()-[r]->() WHERE type(r) = type
                    RETURN count(r) AS cnt
                }
                RETURN type, cnt ORDER BY cnt DESC
            """)
            relationships = [{"type": r["type"], "count": r["cnt"]}
                             for r in rels_result]

            # Get indexes
            indexes_result = session.run(
                "SHOW INDEXES YIELD name, type, labelsOrTypes, properties"
            )
            indexes = [dict(r) for r in indexes_result]

            # CRITICAL: Dynamic layer classification from state
            domain_labels = _get_domain_labels(state)
            lexical_labels = {"Document", "Chunk"}

            def classify(label):
                if label in domain_labels:
                    return "domain"
                if label in lexical_labels:
                    return "lexical"
                return "subject"

            # Filter by layer if requested
            if layer != "all":
                labels = [l for l in labels if classify(l["label"]) == layer]

            return {
                "labels": labels,
                "relationships": relationships,
                "indexes": indexes,
                "layer_classification": {
                    "domain": [l["label"] for l in labels if classify(l["label"]) == "domain"],
                    "subject": [l["label"] for l in labels if classify(l["label"]) == "subject"],
                    "lexical": [l["label"] for l in labels if classify(l["label"]) == "lexical"],
                }
            }
    finally:
        close_driver(driver)


def _get_domain_labels(state: dict) -> set[str]:
    """Extract domain layer labels from approved construction plan.

    Args:
        state: Current pipeline state.

    Returns:
        Set of domain node labels. Empty if no construction plan approved.
    """
    plan = state.get("approved_construction_plan", {})
    return {
        entry["label"]
        for entry in plan.values()
        if entry.get("construction_type") == "node"
    }
```

**Key Patterns**:
- ✅ Driver created per-tool, closed in `finally`
- ✅ State loaded for dynamic classification
- ✅ `@mcp_traceable` for observability
- ✅ No hardcoded domain labels

### 2. Cypher Query Tool (Read-Only)

```python
FORBIDDEN_KEYWORDS = {"CREATE", "MERGE", "DELETE", "DETACH", "SET", "REMOVE", "DROP", "CALL {"}

@mcp.tool
@mcp_traceable(name="mcp.kg_cypher_query")
def kg_cypher_query(query: str, params: dict | None = None) -> dict:
        """Execute a read-only Cypher query against the knowledge graph.

    Use for precise, structured queries: specific entity lookups,
    aggregations, path queries, counts. The graph has three layers:
    - Domain: From approved_construction_plan (dynamic)
    - Subject: Nodes with :__Entity__ label (extracted from text)
    - Lexical: Document, Chunk (with embeddings)
    - Cross-layer: CORRESPONDS_TO, MENTIONED_IN relationships

    Args:
        query: A Cypher READ query (no mutations allowed)
        params: Optional query parameters as key-value pairs
    """
    # Safety: block mutation keywords
    upper_query = query.upper()
    for kw in FORBIDDEN_KEYWORDS:
        if kw in upper_query:
            return {"error": f"Mutation keyword '{kw}' not allowed. Read-only queries only."}

    driver = get_neo4j_driver()
    try:
        with driver.session() as session:
            try:
                result = session.run(query, params or {})
                records = [dict(r) for r in result]
                summary = result.consume()
                return {
                    "records": records[:100],  # cap at 100
                    "total_records": len(records),
                    "query_time_ms": summary.result_available_after,
                }
            except Exception as e:
                return {"error": str(e)}
    finally:
        close_driver(driver)
```

### 3. Vector & Hybrid Search Tools

**Implementation Pattern**: Create retriever per-call (not global) to properly manage driver lifecycle.

```python
from neo4j_graphrag.retrievers import VectorRetriever, HybridRetriever
from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings
import os

@mcp.tool
@mcp_traceable(name="mcp.kg_vector_search")
def kg_vector_search(query: str, top_k: int = 5) -> dict:
    """Semantic similarity search over text chunks in the knowledge graph.

    Best for: exploratory questions, general topics, finding relevant
    passages without knowing exact terminology.

    Args:
        query: Natural language query to search for
        top_k: Number of results to return (default 5)
    """
    driver = get_neo4j_driver()
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

        result = retriever.search(query_text=query, top_k=top_k)
        items = [
            {
                "text": item.content,
                "score": item.metadata.get("score"),
                "metadata": item.metadata,
            }
            for item in result.items
        ]
        return {"results": items, "count": len(items)}

    except Exception as e:
        return {
            "error": str(e),
            "hint": "If index not found, run kg_create_indexes()"
        }
    finally:
        close_driver(driver)


@mcp.tool
@mcp_traceable(name="mcp.kg_hybrid_search")
def kg_hybrid_search(query: str, top_k: int = 5) -> dict:
    """Combined vector + full-text search over text chunks.

    Best for: queries with specific identifiers, codes, batch numbers,
    or exact terms combined with semantic intent.
    Example: "quality issues with batch #2024-0871"

    Args:
        query: Natural language query (semantic + keyword matching)
        top_k: Number of results to return (default 5)
    """
    driver = get_neo4j_driver()
    try:
        embedder = OpenAIEmbeddings(
            model="text-embedding-3-large",
            api_key=os.environ.get("OPENAI_API_KEY"),
        )

        retriever = HybridRetriever(
            driver=driver,
            vector_index_name="chunk-embeddings",
            fulltext_index_name="chunk-fulltext",
            embedder=embedder,
            return_properties=["text", "index"],
        )

        result = retriever.search(query_text=query, top_k=top_k)
        items = []
        for item in result.items:
            items.append({
                "text": item.content,
                "score": item.metadata.get("score"),
                "metadata": item.metadata,
            })
        return {"results": items, "count": len(items)}

    except Exception as e:
        return {
            "error": str(e),
            "hint": "If index not found, run kg_create_indexes()"
        }
    finally:
        close_driver(driver)
```

### `src/kg_query_mcp/tools/cross_layer.py`

```python
"""Three-layer cross-layer traversal tool."""
from neo4j import Driver
from neo4j_graphrag.retrievers import VectorCypherRetriever
from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings


# Cypher that traverses from Chunk → Subject → Domain
TRAVERSAL_QUERY = """
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
"""


def register_cross_layer_tools(mcp, driver: Driver, config):

    embedder = OpenAIEmbeddings(
        model=config.embedding_model,
        api_key=config.openai_api_key,
    )

    retriever = VectorCypherRetriever(
        driver=driver,
        index_name=config.vector_index_name,
        embedder=embedder,
        retrieval_query=TRAVERSAL_QUERY,
        neo4j_database=config.neo4j_database,
    )

    @mcp.tool()
    def kg_cross_layer_traverse(query: str, top_k: int = 5) -> dict:
        """Three-layer traversal: Lexical → Subject → Domain.

        Starts with vector search on Chunks, then traverses to extracted
        entities (:__Entity__), then bridges to Domain nodes via
        CORRESPONDS_TO. Returns the full traversal path.

        Best for: questions that span structured and unstructured data,
        root cause analysis, traceability queries.
        Example: "Which suppliers might be responsible for quality issues?"

        Args:
            query: Natural language query
            top_k: Number of initial chunk matches (default 5)
        """
        try:
            result = retriever.search(query_text=query, top_k=top_k)
            items = []
            for item in result.items:
                items.append({
                    "content": item.content,
                    "metadata": item.metadata,
                })
            return {"results": items, "count": len(items)}
        except Exception as e:
            return {"error": str(e)}
```

### `src/kg_query_mcp/tools/evaluate.py`

```python
"""Competency Question evaluation tools."""
from neo4j import Driver
from neo4j_graphrag.retrievers import VectorRetriever, HybridRetriever
from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings


def register_evaluate_tools(mcp, driver: Driver, config):

    embedder = OpenAIEmbeddings(
        model=config.embedding_model,
        api_key=config.openai_api_key,
    )

    @mcp.tool()
    def kg_evaluate_competency_question(
        question: str,
        expected_answer: str = "",
        strategy: str = "auto",
    ) -> dict:
        """Evaluate whether a competency question can be answered by the KG.

        Tries multiple retrieval strategies and returns evidence of whether
        the knowledge graph contains sufficient information to answer the
        question. This is the primary evaluation tool.

        Args:
            question: The competency question to test
            expected_answer: Optional expected answer for comparison
            strategy: "auto" tries all strategies, or pick one:
                      "cypher", "vector", "hybrid", "cross_layer"
        """
        results = {}
        strategies_to_try = (
            ["vector", "hybrid", "cross_layer"]
            if strategy == "auto"
            else [strategy]
        )

        with driver.session(database=config.neo4j_database) as session:
            for strat in strategies_to_try:
                try:
                    if strat == "vector":
                        evidence = _vector_search(driver, embedder, config, question)
                    elif strat == "hybrid":
                        evidence = _hybrid_search(driver, embedder, config, question)
                    elif strat == "cross_layer":
                        evidence = _cross_layer_search(session, driver, embedder, config, question)
                    elif strat == "cypher":
                        evidence = _schema_probe(session, question)
                    else:
                        evidence = {"error": f"Unknown strategy: {strat}"}

                    results[strat] = evidence
                except Exception as e:
                    results[strat] = {"error": str(e)}

        # Aggregate: compute rough answerability score
        total_evidence = sum(
            len(r.get("items", []))
            for r in results.values()
            if isinstance(r, dict) and "items" in r
        )

        has_cross_layer = any(
            r.get("has_domain_bridge", False)
            for r in results.values()
            if isinstance(r, dict)
        )

        return {
            "question": question,
            "expected_answer": expected_answer,
            "strategies_tried": list(results.keys()),
            "evidence_by_strategy": results,
            "total_evidence_items": total_evidence,
            "has_cross_layer_bridge": has_cross_layer,
            "assessment": {
                "evidence_found": total_evidence > 0,
                "evidence_count": total_evidence,
                "note": (
                    "Evidence found across layers — question is likely answerable"
                    if has_cross_layer and total_evidence > 2
                    else "Some evidence found — partial coverage"
                    if total_evidence > 0
                    else "No evidence found — question may not be answerable with current KG"
                )
            },
        }


    @mcp.tool()
    def kg_evaluate_cq_batch(questions: list[dict]) -> dict:
        """Batch-evaluate multiple competency questions against the KG.

        Returns a scorecard with coverage metrics.

        Args:
            questions: List of dicts with keys: "question" (required),
                      "expected_answer" (optional)
        """
        results = []
        answerable = 0
        partial = 0
        not_answerable = 0

        for q in questions:
            question_text = q.get("question", "")
            expected = q.get("expected_answer", "")

            eval_result = kg_evaluate_competency_question(
                question=question_text,
                expected_answer=expected,
                strategy="auto",
            )

            evidence_count = eval_result["total_evidence_items"]
            has_bridge = eval_result["has_cross_layer_bridge"]

            if has_bridge and evidence_count > 2:
                status = "answerable"
                answerable += 1
            elif evidence_count > 0:
                status = "partial"
                partial += 1
            else:
                status = "not_answerable"
                not_answerable += 1

            results.append({
                "question": question_text,
                "status": status,
                "evidence_count": evidence_count,
                "has_cross_layer_bridge": has_bridge,
            })

        total = len(questions)
        coverage = (answerable + 0.5 * partial) / total if total > 0 else 0

        return {
            "total": total,
            "answerable": answerable,
            "partial": partial,
            "not_answerable": not_answerable,
            "coverage_score": round(coverage, 3),
            "results": results,
        }


# --- Internal helpers ---

def _vector_search(driver, embedder, config, query, top_k=5):
    retriever = VectorRetriever(
        driver=driver,
        index_name=config.vector_index_name,
        embedder=embedder,
        return_properties=["text", "index"],
        neo4j_database=config.neo4j_database,
    )
    result = retriever.search(query_text=query, top_k=top_k)
    items = [{"text": i.content[:200], "score": i.metadata.get("score")}
             for i in result.items]
    return {"items": items, "strategy": "vector"}


def _hybrid_search(driver, embedder, config, query, top_k=5):
    retriever = HybridRetriever(
        driver=driver,
        vector_index_name=config.vector_index_name,
        fulltext_index_name=config.fulltext_index_name,
        embedder=embedder,
        return_properties=["text", "index"],
        neo4j_database=config.neo4j_database,
    )
    result = retriever.search(query_text=query, top_k=top_k)
    items = [{"text": i.content[:200], "score": i.metadata.get("score")}
             for i in result.items]
    return {"items": items, "strategy": "hybrid"}


def _cross_layer_search(session, driver, embedder, config, query, top_k=5):
    """Vector search + check for cross-layer bridges."""
    items_data = _vector_search(driver, embedder, config, query, top_k)

    # Probe for cross-layer connections
    bridge_result = session.run("""
        MATCH (e:__Entity__)-[:CORRESPONDS_TO]->(d)
        RETURN count(*) AS bridge_count
    """)
    bridge_count = bridge_result.single()["bridge_count"]

    entity_result = session.run("""
        MATCH (e:__Entity__)-[:MENTIONED_IN]->(c:Chunk)
        RETURN count(DISTINCT e) AS entity_count
    """)
    entity_count = entity_result.single()["entity_count"]

    items_data["has_domain_bridge"] = bridge_count > 0
    items_data["bridge_count"] = bridge_count
    items_data["entities_with_mentions"] = entity_count
    items_data["strategy"] = "cross_layer"
    return items_data


def _schema_probe(session, question):
    """Check if the schema has relevant node types for the question."""
    labels_result = session.run("CALL db.labels() YIELD label RETURN collect(label) AS labels")
    labels = labels_result.single()["labels"]

    rels_result = session.run("""
        CALL db.relationshipTypes() YIELD relationshipType
        RETURN collect(relationshipType) AS types
    """)
    rel_types = rels_result.single()["types"]

    return {
        "items": [],
        "available_labels": labels,
        "available_relationship_types": rel_types,
        "strategy": "cypher_schema_probe",
        "note": "Schema returned for LLM-based Cypher generation"
    }
```

---

## Competency Question (CQ) Evaluation Integration

### US012 Integration

Query tools are **tightly integrated** with the Competency Questions system (US012). CQs are stored in state and used for evaluation:

```python
# state["approved_competency_questions"]
{
    "CQ1": {
        "question": "Which suppliers provide parts for the Stockholm Chair?",
        "category": "supply_chain_impact",
        "priority": "high"
    },
    "CQ2": {
        "question": "What quality issues have been reported for products?",
        "category": "quality_analysis",
        "priority": "high"
    },
    ...
}
```

### Evaluation Tool: `kg_evaluate_cqs`

**Stateful evaluation** of approved CQs (single, subset, or all) from state:

```python
@mcp.tool
@mcp_traceable(name="mcp.kg_evaluate_cqs")
def kg_evaluate_cqs(cq_id: str = "", cq_ids: list[str] = None) -> dict:
    """Evaluate approved competency questions from state.

    Tests if approved CQs are answerable by gathering evidence from the graph.
    Returns assessment metrics (not answers).

    Works with approved CQs only. For ad-hoc questions, use kg_query.

    Args:
        cq_id: Single approved CQ ID to evaluate (e.g., "CQ3")
        cq_ids: List of approved CQ IDs to evaluate (e.g., ["CQ1", "CQ3"])
                If neither provided: evaluates ALL approved CQs

    Returns:
        Single CQ: Individual assessment with evidence
        Multiple CQs: Coverage scorecard + per-CQ results
    """
    state = _load_clean_state()

    cqs = state.get("approved_competency_questions", {})
    if not cqs:
        return {
            "agent_response": "No approved competency questions to evaluate.\n\n"
                "Use kg_user_intent or kg_competency_questions first.",
            "status": {"error": "no_approved_cqs"},
        }

    # Determine which CQs to evaluate
    if cq_id:
        # Single CQ by ID
        if cq_id not in cqs:
            return {
                "agent_response": f"CQ ID '{cq_id}' not found in approved CQs.",
                "status": {"error": "cq_not_found"},
            }
        cqs_to_evaluate = {cq_id: cqs[cq_id]}
    elif cq_ids:
        # Specific subset of CQs
        cqs_to_evaluate = {cq_id: cqs[cq_id] for cq_id in cq_ids if cq_id in cqs}
        if not cqs_to_evaluate:
            return {
                "agent_response": "None of the provided CQ IDs found in approved CQs.",
                "status": {"error": "cqs_not_found"},
            }
    else:
        # All approved CQs
        cqs_to_evaluate = cqs

    driver = get_neo4j_driver()
    try:
        results = []
        answerable = 0
        partial = 0
        not_answerable = 0

        for cq_id, cq_data in cqs.items():
            question = cq_data["question"]
            category = cq_data.get("category", "unknown")
            priority = cq_data.get("priority", "medium")

            # Evaluate this CQ using specified strategy
            eval_result = _evaluate_single_cq(
                driver, question, strategy=strategy
            )

            evidence_count = eval_result["total_evidence_items"]
            has_bridge = eval_result["has_cross_layer_bridge"]

            # Classify answerability
            if has_bridge and evidence_count > 2:
                status = "answerable"
                answerable += 1
            elif evidence_count > 0:
                status = "partial"
                partial += 1
            else:
                status = "not_answerable"
                not_answerable += 1

            results.append({
                "cq_id": cq_id,
                "question": question,
                "category": category,
                "priority": priority,
                "status": status,
                "evidence_count": evidence_count,
                "has_cross_layer_bridge": has_bridge,
                "strategies_tried": eval_result["strategies_tried"],
            })

        total = len(cqs)
        coverage_score = (answerable + 0.5 * partial) / total if total > 0 else 0

        # CRITICAL: Store results in state for persistence
        state["cq_evaluation_results"] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total": total,
            "answerable": answerable,
            "partial": partial,
            "not_answerable": not_answerable,
            "coverage_score": round(coverage_score, 3),
            "per_cq_results": results,
        }
        _save_state(state)

        # Format response
        lines = [f"Competency Question Evaluation: {total} questions\n"]
        lines.append(f"Answerable: {answerable}")
        lines.append(f"Partial: {partial}")
        lines.append(f"Not Answerable: {not_answerable}")
        lines.append(f"Coverage Score: {coverage_score:.1%}\n")

        lines.append("Per-CQ Results:")
        for r in results:
            icon = "[OK]" if r["status"] == "answerable" else \
                   "[PARTIAL]" if r["status"] == "partial" else "[FAIL]"
            lines.append(
                f"  {icon} {r['cq_id']}: {r['question'][:60]}... "
                f"({r['evidence_count']} evidence)"
            )

        return {
            "agent_response": "\n".join(lines),
            "status": {
                "success": True,
                "total": total,
                "answerable": answerable,
                "partial": partial,
                "not_answerable": not_answerable,
                "coverage_score": coverage_score,
            },
            "results": results,
        }

    finally:
        close_driver(driver)


def _evaluate_single_cq(driver, question: str, strategy: str = "auto") -> dict:
    """Evaluate a single CQ using one or more retrieval strategies.

    Internal helper for kg_evaluate_approved_cqs.

    Returns:
        Evidence summary with strategies_tried, total_evidence_items,
        has_cross_layer_bridge fields.
    """
    # Implementation: try vector, hybrid, cross-layer strategies
    # Gather evidence from each, aggregate results
    # (detailed implementation in pipelines/query_builder.py)
    pass
```

**Key Pattern**: Evaluation results are **persisted to state**, not just returned. This allows:
- Tracking CQ coverage over time
- Comparing before/after graph improvements
- Identifying consistently failing CQs

---

## Configuration (Existing MCP Server)

**No separate configuration needed** — query tools are part of the existing KG-Factory MCP server.

Users already have this in their `.mcp.json`:
```json
{
  "mcpServers": {
    "kg-factory": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/KnowledgeGraphFactory",
      "env": {
        "NEO4J_URI": "neo4j+s://xxxxx.databases.neo4j.io",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "password",
        "OPENAI_API_KEY": "sk-...",
        "LANGSMITH_TRACING": "true"
      }
    }
  }
}
```

Query tools become available automatically after this feature is implemented.

---

## Usage Workflow

### 1. Build the Knowledge Graph (Existing Pipeline)

```
> Build the graph from my approved artifacts
```

Claude Code calls:
- `kg_build_graph(scope="structured")` → Domain layer from CSVs
- `kg_build_graph(scope="unstructured", message="all")` → Subject + Lexical layers from markdown
  - **Indexes auto-created** after first successful file
- `kg_build_graph(scope="resolve")` → Links Subject to Domain

### 2. Understand the Graph Schema

```
> Show me what's in the knowledge graph
```

Claude Code calls `kg_schema(layer="all")` → labels, counts, relationships, **dynamic layer classification from state**

### 3. Evaluate Approved Competency Questions

#### **Batch Evaluation (All CQs)**
```
> Evaluate all my competency questions
```

Claude Code calls `kg_evaluate_cqs()`:
- Reads ALL CQs from `state["approved_competency_questions"]` (US012)
- Tests each using `kg_query` internally (collects evidence, not answers)
- Returns coverage scorecard
- **Stores results in state** for tracking

**Example Output**:
```
Competency Question Evaluation: 8 questions

Answerable: 5
Partial: 2
Not Answerable: 1
Coverage Score: 75.0%

Per-CQ Results:
  [OK] CQ1: Which suppliers provide parts for the Stockholm Chair? (12 evidence)
  [OK] CQ2: What quality issues have been reported for products? (8 evidence)
  [PARTIAL] CQ3: Which supplier's parts are most mentioned in negative reviews? (3 evidence)
  [FAIL] CQ4: What is the average lead time for international suppliers? (0 evidence)
  ...
```

#### **Single CQ Evaluation**
```
> Test if CQ3 is answerable now
```

Claude Code calls `kg_evaluate_cqs(cq_id="CQ3")`:
- Returns individual assessment with evidence details
- Shows which strategies found evidence

#### **Subset Evaluation**
```
> Evaluate CQ1, CQ3, and CQ5
```

Claude Code calls `kg_evaluate_cqs(cq_ids=["CQ1", "CQ3", "CQ5"])`:
- Returns mini coverage scorecard for just those 3 CQs

### 4. Investigate Failures with kg_query

```
> Why did CQ3 score "partial"? Can you answer it now?
```

Claude Code calls `kg_query("Which supplier's parts are most mentioned in negative reviews?")`:
- Returns actual answer (or partial answer)
- Shows confidence score: 0.4 (low)
- Evidence shows only 1 supplier mapped, others missing

Reports: "Found mentions of 3 suppliers in reviews, but only 1 has CORRESPONDS_TO link to domain. Need entity resolution."

### 5. Test Questions Before Approving as CQs

```
> Before I approve this as a CQ, test if the graph can answer: "What is the average lead time?"
```

Claude Code calls `kg_query("What is the average lead time for international suppliers?")`:
- Returns answer (or "insufficient data")
- Shows confidence: 0.2 (very low)
- User decides: "Not good enough yet, won't add this CQ"

### 6. Iterate on Graph Construction

```
> Fix the entity resolution and re-evaluate all CQs
```

Claude Code:
1. `kg_build_graph(scope="resolve")` → Creates missing CORRESPONDS_TO links
2. `kg_evaluate_cqs()` → Re-runs full evaluation
3. Compares new coverage score (now 87.5%) with previous (75.0%)

### 7. Ad-Hoc Queries

```
> What products are mentioned in quality issue reviews?
```

Claude Code calls `kg_query("What products are mentioned in quality issue reviews?")`:
- Internal strategy selection: chooses "cross_layer"
- Returns: "Stockholm Chair (mentioned in 12 chunks), Gothenburg Table (8 chunks)..."
- Confidence: 0.85

---

## Implementation Summary

### Files to Modify

1. **`mcp_server/server.py`** (add after line 897):
   - `_create_text_indexes(driver)` → Index creation helper
   - `_format_index_results(index_results)` → Format index status
   - `_get_domain_labels(state)` → Dynamic layer classification
   - `_select_retrieval_strategy(question, context, state)` → Claude-powered strategy selection
   - Integrate index creation into `_build_unstructured()` (auto-creation with error guidance)
   - Add **2 new MCP tools**: `kg_query`, `kg_evaluate_approved_cqs`

2. **`requirements.txt`** → No changes needed (dependencies already present from US009)

### Files to Create

1. **`tools/query_tools.py`** → Shared helpers:
   - Evidence gathering functions
   - Result formatting utilities
   - CQ evaluation helpers

2. **`pipelines/query_builder.py`** → Internal retrieval strategies (NOT exposed as MCP tools):
   - `_execute_schema_query(driver, state)` → Get schema with layer classification
   - `_execute_cypher(driver, query)` → Execute read-only Cypher with safety checks
   - `_execute_vector_search(driver, question, top_k)` → Semantic search via VectorRetriever
   - `_execute_hybrid_search(driver, question, top_k)` → Hybrid search via HybridRetriever
   - `_execute_cross_layer_traversal(driver, question, top_k)` → Three-layer traversal via VectorCypherRetriever
   - `evaluate_single_cq(driver, question, strategy)` → CQ evaluation logic (used by kg_evaluate_approved_cqs)

3. **`tests/unit/test_query_tools.py`** → Unit tests:
   - Test index creation (idempotent, handles errors)
   - Test layer classification (dynamic from state)
   - Test CQ evaluation logic
   - Mock Neo4j driver for fast tests

4. **`tests/unit/test_index_creation.py`** → Index-specific tests:
   - Auto-creation in `_build_unstructured()`
   - Manual creation via `kg_create_indexes()`
   - Recreate with `recreate=True`
   - Error handling for permissions issues

### Testing Checklist

**Index Management**:
- [ ] Indexes auto-created after first text graph file
- [ ] Index creation failure provides clear error guidance
- [ ] Build succeeds even if index creation fails (non-blocking)

**kg_query Tool**:
- [ ] Claude API strategy selection works correctly
- [ ] Strategy "schema" returns graph structure with dynamic layer classification
- [ ] Strategy "cypher" blocks mutation keywords, executes safely
- [ ] Strategy "vector" returns semantic search results
- [ ] Strategy "hybrid" combines vector + fulltext search
- [ ] Strategy "cross_layer" traverses Lexical → Subject → Domain
- [ ] Proper driver management (create per-call, close in finally)
- [ ] `@mcp_traceable` integration works

**kg_evaluate_cqs Tool**:
- [ ] Single CQ: `kg_evaluate_cqs(cq_id="CQ3")` works
- [ ] Subset: `kg_evaluate_cqs(cq_ids=["CQ1", "CQ3"])` works
- [ ] Batch: `kg_evaluate_cqs()` (no params) evaluates all approved CQs
- [ ] Reads CQs from `state["approved_competency_questions"]`
- [ ] Uses `kg_query` internally for evidence gathering (not answers)
- [ ] Stores results in `state["cq_evaluation_results"]` with timestamp
- [ ] Returns single assessment OR coverage scorecard based on input
- [ ] Rejects ad-hoc questions (must use approved CQ IDs)
- [ ] Proper driver management

**General**:
- [ ] All tools use `@mcp_traceable` for observability
- [ ] Windows: No subprocess deadlock (fix already present)
- [ ] No user-facing operational tools (indexes are auto-only)

---

## Key Architectural Decisions

### 1. **Integrated vs Separate Server** ✅
**Decision**: Integrate into existing `mcp_server/server.py`
**Rationale**: Single MCP server, unified config, shared state management, existing driver utilities, LangSmith fix already present
**Alternative Rejected**: Separate `kg-query-mcp` server (duplicate config, split responsibilities, maintenance overhead)

### 2. **Unified Query Tool (Single Entry Point)** ✅
**Decision**: Single `kg_query(question, context?)` tool with internal Claude-powered strategy selection
**Rationale**: Simplifies UX (users don't choose strategies), follows workflow-focused tool design, Claude selects optimal approach
**Alternative Rejected**: Exposing 8 separate query tools (overwhelming, operational complexity, user must understand retrieval strategies)

### 3. **Index Creation Strategy (Auto-Only)** ✅
**Decision**: Auto-create in `_build_unstructured()` with clear error guidance, NO manual tool
**Rationale**: Index creation is operational (not workflow), failures indicate infrastructure issues (permissions) that should be fixed at root cause, consistent with workflow-focused tool philosophy
**Alternative Rejected**: Manual `kg_create_indexes()` tool (breaks workflow/operational separation, encourages workarounds instead of fixing root cause)

### 4. **Layer Classification** ✅
**Decision**: Dynamic from `approved_construction_plan` in state
**Rationale**: Works for all domains, not just furniture supply chain
**Alternative Rejected**: Hardcoded `{"Product", "Assembly", ...}` (domain-specific)

### 5. **CQ Integration (US012)** ✅
**Decision**: `kg_evaluate_cqs(cq_id?, cq_ids?)` works ONLY with approved CQs from state (no ad-hoc question parameter)
**Rationale**:
- Removes ambiguity: ad-hoc questions always go through `kg_query` (get answers)
- Clear separation: `kg_evaluate_cqs` is for testing approved CQs (get assessments)
- Users test questions before approving via `kg_query` + confidence scores
**Alternative Rejected**: Allow ad-hoc questions in evaluation tool (creates ambiguity about which tool to use for ad-hoc questions)

### 6. **Driver Management** ✅
**Decision**: Use `get_neo4j_driver()` per-tool, close in `finally`
**Rationale**: Follows existing pattern, testable, no connection leaks
**Alternative Rejected**: Global driver (leaks on crash, hard to test, violates existing utilities pattern)

### 7. **Observability** ✅
**Decision**: Use `@mcp_traceable` from `core.tracing` on all tools
**Rationale**: Consistent with US011, optional (only when `LANGSMITH_TRACING=true`)
**Alternative Rejected**: No tracing (harder to debug), separate tracing setup (inconsistent)

### 8. **Evidence vs Judgment** ✅
**Decision**: Tools return **evidence**, Claude Code makes **judgment**
**Rationale**: MCP tools stay deterministic, Claude applies nuanced reasoning with full context
**Alternative Rejected**: LLM-powered answerability scoring (adds latency, non-deterministic, less transparent)

### 9. **Tool Intent Clarity (No Ambiguity)** ✅
**Decision**: `kg_query` for ALL ad-hoc questions, `kg_evaluate_cqs` ONLY for approved CQs from state
**Rationale**:
- Removes ambiguity: "Can the graph answer X?" always goes to `kg_query` (returns answer + confidence)
- Clear tool purposes: `kg_query` = get answers, `kg_evaluate_cqs` = assess coverage of approved CQs
- Confidence scores in `kg_query` let users test questions before approving them as CQs
**Alternative Rejected**: Allow ad-hoc questions in `kg_evaluate_cqs` via `question` parameter (creates ambiguity: should ad-hoc questions go to `kg_query` or `kg_evaluate_cqs`?)

### 10. **Workflow vs Operational Concerns** ✅
**Decision**: MCP tools are **workflow-focused only** (design, construction, evaluation). No operational tools.
**Rationale**: Consistent with all existing KG-Factory tools (user_intent, file_suggestion, schema_proposal, critic, ner, fact, build, reset). Index creation, permissions, backups are operational concerns handled outside the workflow.
**Alternative Rejected**: Exposing operational tools like `kg_create_indexes` (breaks philosophy, encourages workarounds, inconsistent with tool purpose)

---

## Final Tool Design Summary

### 🎯 **2 User-Facing Tools**

#### **1. `kg_query(question: str, context: str = "")`**
**Purpose**: Answer ANY question about the knowledge graph
**Returns**: Answer, evidence, strategy_used, confidence (0.0-1.0)
**Use for**:
- Ad-hoc questions: "What suppliers provide parts?"
- Testing questions before approving as CQs: "Can the graph answer X?" (check confidence)
- Investigating specific data: "Tell me about quality issues"

#### **2. `kg_evaluate_cqs(cq_id: str = "", cq_ids: list[str] = None)`**
**Purpose**: Evaluate approved competency questions from state
**Returns**: Assessment (single) or coverage scorecard (batch)
**Use for**:
- Single CQ test: `kg_evaluate_cqs(cq_id="CQ3")`
- Subset evaluation: `kg_evaluate_cqs(cq_ids=["CQ1", "CQ3", "CQ5"])`
- Full coverage report: `kg_evaluate_cqs()` (no parameters)

**DOES NOT** accept ad-hoc questions — only works with approved CQ IDs from state.

---

### 📋 **Decision Rules for Claude Code**

| User Says | Tool to Call | Why |
|-----------|--------------|-----|
| "What suppliers provide parts?" | `kg_query` | Wants an answer |
| "How many products mention X?" | `kg_query` | Wants an answer |
| "Can the graph answer: Which...?" | `kg_query` | Check answer + confidence |
| "Test this question before I approve it" | `kg_query` | Check confidence score |
| "Evaluate CQ3" | `kg_evaluate_cqs(cq_id="CQ3")` | Test specific approved CQ |
| "Test CQ1, CQ3, and CQ5" | `kg_evaluate_cqs(cq_ids=[...])` | Test subset of CQs |
| "Evaluate all my CQs" | `kg_evaluate_cqs()` | Full coverage report |
| "Coverage report" | `kg_evaluate_cqs()` | Full coverage report |

**Key Distinction**:
- `kg_query` → "What IS the answer?" (returns data)
- `kg_evaluate_cqs` → "CAN the graph answer this CQ?" (returns assessment)

---

### ✅ **No Ambiguity**

**Scenario**: User asks *"Can the graph answer: Which suppliers have high defect rates?"*

**Old Design** (ambiguous):
- Could call `kg_query` OR `kg_evaluate_cqs(question="...")`
- Unclear which is correct

**New Design** (clear):
- ALWAYS calls `kg_query`
- Returns answer + confidence (e.g., 0.3 = low confidence, 0.9 = high confidence)
- User sees: "Here's what I found, but confidence is low (0.3)"

If user wants to track this as a formal CQ:
1. Add to approved CQs via `kg_competency_questions`
2. Then evaluate via `kg_evaluate_cqs(cq_id="CQ_NEW")`
