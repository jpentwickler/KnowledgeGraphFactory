"""
Query Builder - Adaptive retrieval strategies for knowledge graph querying.

Provides 6 retrieval strategies:
1. _select_retrieval_strategy - Claude-powered strategy selection
2. _execute_schema_query - Graph structure exploration
3. _execute_cypher - Structured traversal queries
4. _execute_vector_search - Semantic similarity search
5. _execute_hybrid_search - Vector + keyword search
6. _execute_cross_layer_traversal - Hybrid search + domain entity traversal
"""

import os
import json
from typing import Any
import neo4j
from neo4j import Driver

from tools.query_tools import (
    _get_domain_labels,
    _get_text_entities,
    format_cypher_results,
    format_retriever_results,
    calculate_confidence,
    _validate_read_only_cypher,
)
from core.state import has_approved
from core.tracing import traceable, wrap_anthropic


# =============================================================================
# Custom Result Formatters
# =============================================================================

def _node_to_dict(node) -> dict | None:
    """Convert a Neo4j Node to a serializable dict."""
    if node is None:
        return None
    # Neo4j Node implements Mapping with keys() + __getitem__
    props = {k: node[k] for k in node.keys()} if hasattr(node, "keys") else {}
    labels = list(node.labels) if hasattr(node, "labels") else []
    return {"labels": labels, "properties": props}


def _cross_layer_formatter(record: neo4j.Record):
    """Format cross-layer traversal results with entity context.

    Maps custom RETURN columns from the traversal query into
    structured content and metadata fields.
    """
    from neo4j_graphrag.types import RetrieverResultItem

    chunk_text = record.get("chunk_text", "")
    source_file = record.get("source_file")
    score = record.get("score", 0.0)

    # Entity info
    entity_node = record.get("entity")
    entity_label = record.get("entity_label", "Unknown")

    # Domain entity info (from CORRESPONDS_TO traversal)
    domain_node = record.get("domain_entity")
    domain_label = record.get("domain_label")

    return RetrieverResultItem(
        content=chunk_text,
        metadata={
            "score": score,
            "source_file": source_file,
            "entity": _node_to_dict(entity_node),
            "entity_label": entity_label,
            "domain_entity": _node_to_dict(domain_node),
            "domain_label": domain_label,
        }
    )


# =============================================================================
# Strategy 1: Claude-Powered Strategy Selection
# =============================================================================

@traceable(name="query.select_strategy")
async def _select_retrieval_strategy(
    question: str,
    context: str,
    state: dict
) -> dict:
    """Use Claude API to select optimal retrieval strategy.

    Analyzes the question and available graph layers to choose the best
    retrieval approach. Returns structured decision with reasoning.

    Args:
        question: Natural language question or Cypher query
        context: Optional context to guide selection
        state: Pipeline state (to determine available graph layers)

    Returns:
        {
            "strategy": str,        # One of: schema, cypher, vector, hybrid, cross_layer
            "reasoning": str,       # Explanation of why this strategy was chosen
            "parameters": dict      # Strategy-specific parameters (cypher_query, top_k, etc.)
        }

    Fallback: Returns {"strategy": "schema", ...} on any error
    """
    # Extract graph context from state
    domain_labels = _get_domain_labels(state)
    text_entities = _get_text_entities(state)
    has_text_graph = "text_graph_progress" in state
    has_domain_graph = has_approved(state, "construction_plan")

    # Build graph context summary
    graph_context = []
    if has_domain_graph:
        graph_context.append(f"Domain layer with {len(domain_labels)} node types: {', '.join(domain_labels[:5])}")
    if has_text_graph:
        graph_context.append(f"Text layer with {len(text_entities)} entity types: {', '.join(text_entities[:5])}")

    if not graph_context:
        # No graph built yet, return schema strategy
        return {
            "strategy": "schema",
            "reasoning": "No graph built yet. Showing available schema.",
            "parameters": {}
        }

    graph_summary = "\n".join(graph_context)

    # Build system prompt for Claude
    system_prompt = f"""You are a knowledge graph query strategy selector.

Available graph layers:
{graph_summary}

Your task: Analyze the question and select the optimal retrieval strategy.

Available strategies:
1. **schema**: Explore graph structure (labels, relationships, counts)
   - Use when: User asks about graph structure, available entities, or "what's in the graph"

2. **cypher**: Execute structured Cypher queries
   - Use when: Question is a Cypher query OR requires precise graph traversal
   - CRITICAL: Only suggest Cypher if you can generate a SAFE, READ-ONLY query
   - Blocked keywords: CREATE, DELETE, SET, REMOVE, MERGE
   - Required keywords: MATCH or RETURN

3. **vector**: Semantic similarity search on text chunks
   - Use when: Question is about content/meaning in unstructured text
   - Requires: Text layer available

4. **hybrid**: Vector + fulltext keyword search
   - Use when: Question has specific keywords AND semantic meaning
   - Requires: Text layer available

5. **cross_layer**: Hybrid search (vector + fulltext) + entity traversal across layers
   - Use when: Question links text content to structured domain entities, or asks about
     extracted entities (customers, quality issues, product features) alongside domain data
   - ALSO use when: Question contains specific names, @mentions, or keywords that need
     exact matching AND you need entity/domain context (e.g. "reviews by @home_chef")
   - Requires: Both domain AND text layers available
   - Traverses: FROM_CHUNK (text entities to chunks) + CORRESPONDS_TO (text to domain entities)
   - Example: "Which suppliers are mentioned in quality reviews?"
   - Example: "What quality issues are linked to specific products?"
   - Example: "What did @home_chef say about the furniture?"

Respond with JSON only (no markdown):
{{
  "strategy": "schema|cypher|vector|hybrid|cross_layer",
  "reasoning": "Brief explanation of why this strategy is best",
  "parameters": {{
    "cypher_query": "...",  // Only for strategy=cypher
    "top_k": 5              // Only for vector-based strategies (optional, default=5)
  }}
}}"""

    # Prepare user message
    user_message = f"Question: {question}"
    if context:
        user_message += f"\n\nAdditional context: {context}"

    try:
        # Call Claude API
        import anthropic
        client = wrap_anthropic(anthropic.Anthropic())

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}]
        )

        # Extract JSON from response
        response_text = response.content[0].text.strip()

        # Handle markdown code blocks if present
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        result = json.loads(response_text)

        # Validate Cypher if strategy is cypher
        if result.get("strategy") == "cypher":
            cypher_query = result.get("parameters", {}).get("cypher_query", "")
            if not cypher_query:
                raise ValueError("Cypher strategy selected but no query provided")

            # Validate safety
            _validate_read_only_cypher(cypher_query)

        return result

    except Exception as e:
        # Fallback to schema on any error
        return {
            "strategy": "schema",
            "reasoning": f"Error selecting strategy ({str(e)}), falling back to schema exploration",
            "parameters": {}
        }


# =============================================================================
# Strategy 2: Schema Query
# =============================================================================

@traceable(name="query.execute_schema")
def _execute_schema_query(driver: Driver, state: dict) -> dict:
    """Return graph schema with dynamic layer classification.

    Queries the graph for labels, relationships, and node counts.
    Classifies labels into domain layer (from state) and text layer (Chunk/Document).

    Args:
        driver: Neo4j driver instance
        state: Pipeline state (for domain label classification)

    Returns:
        {
            "answer": str,          # Formatted schema summary
            "evidence": list,       # Schema details as structured data
            "confidence": float,    # 1.0 (deterministic)
            "details": dict         # Metadata
        }
    """
    domain_labels = _get_domain_labels(state)
    text_labels = ["Chunk", "Document", "__Entity__"]  # Known text layer labels

    with driver.session() as session:
        # Get all labels
        labels_result = session.run("CALL db.labels() YIELD label RETURN label")
        all_labels = [record["label"] for record in labels_result]

        # Get all relationship types
        rel_result = session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")
        all_rels = [record["relationshipType"] for record in rel_result]

        # Get node counts per label
        counts = {}
        for label in all_labels:
            count_result = session.run(f"MATCH (n:`{label}`) RETURN count(n) AS count")
            counts[label] = count_result.single()["count"]

    # Classify labels
    domain_found = [l for l in all_labels if l in domain_labels]
    text_found = [l for l in all_labels if l in text_labels]
    other = [l for l in all_labels if l not in domain_labels and l not in text_labels]

    # Build answer
    lines = ["# Knowledge Graph Schema\n"]

    if domain_found:
        lines.append("## Domain Layer (from structured data)")
        for label in domain_found:
            lines.append(f"  - {label}: {counts[label]:,} nodes")
        lines.append("")

    if text_found:
        lines.append("## Text Layer (from unstructured data)")
        for label in text_found:
            lines.append(f"  - {label}: {counts[label]:,} nodes")
        lines.append("")

    if other:
        lines.append("## Other Labels")
        for label in other:
            lines.append(f"  - {label}: {counts[label]:,} nodes")
        lines.append("")

    if all_rels:
        lines.append("## Relationships")
        for rel in all_rels:
            lines.append(f"  - {rel}")

    answer = "\n".join(lines)

    # Build evidence
    evidence = [
        {
            "type": "schema",
            "domain_labels": domain_found,
            "text_labels": text_found,
            "relationships": all_rels,
            "node_counts": counts
        }
    ]

    return {
        "answer": answer,
        "evidence": evidence,
        "confidence": 1.0,
        "details": {"strategy": "schema", "total_labels": len(all_labels), "total_relationships": len(all_rels)}
    }


# =============================================================================
# Strategy 3: Cypher Execution
# =============================================================================

@traceable(name="query.execute_cypher")
def _execute_cypher(driver: Driver, query: str) -> dict:
    """Execute read-only Cypher query.

    Validates query safety before execution.
    Blocks: CREATE, DELETE, SET, REMOVE, MERGE
    Requires: MATCH or RETURN

    Args:
        driver: Neo4j driver instance
        query: Cypher query string

    Returns:
        {
            "answer": str,          # Formatted query results
            "evidence": list,       # Raw Neo4j records
            "confidence": float,    # 0.8 if results, 0.2 if empty
            "details": dict         # Metadata
        }

    Raises:
        ValueError: If query contains mutation operations
    """
    # Validate safety
    _validate_read_only_cypher(query)

    # Execute query
    with driver.session() as session:
        result = session.run(query)
        records = list(result)

    # Format results
    answer = format_cypher_results(records)

    # Calculate confidence
    confidence = calculate_confidence(records, "cypher")

    return {
        "answer": answer,
        "evidence": [dict(record) for record in records],
        "confidence": confidence,
        "details": {"strategy": "cypher", "query": query, "result_count": len(records)}
    }


# =============================================================================
# Strategy 4: Vector Search (to be implemented in Phase 4)
# =============================================================================

@traceable(name="query.execute_vector")
def _execute_vector_search(driver: Driver, question: str, top_k: int = 5) -> dict:
    """Semantic vector search via VectorRetriever.

    Args:
        driver: Neo4j driver instance
        question: Natural language question
        top_k: Number of results to return

    Returns:
        {
            "answer": str,
            "evidence": list,
            "confidence": float,
            "details": dict
        }

    Raises:
        RuntimeError: If OPENAI_API_KEY not set or indexes missing
    """
    # Check for OPENAI_API_KEY
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "Vector search requires OPENAI_API_KEY.\n"
            "Set OPENAI_API_KEY in your environment or .mcp.json.\n"
            "Required for text-embedding-3-large embeddings."
        )

    try:
        from neo4j_graphrag.embeddings import OpenAIEmbeddings
        from neo4j_graphrag.retrievers import VectorRetriever

        # Create embedder (consistent with US009)
        embedder = OpenAIEmbeddings(model="text-embedding-3-large")

        # Create retriever
        retriever = VectorRetriever(
            driver=driver,
            index_name="chunk-embeddings",
            embedder=embedder
        )

        # Execute search
        search_result = retriever.search(query_text=question, top_k=top_k)

    except Exception as e:
        error_msg = str(e)
        if "index" in error_msg.lower() or "not found" in error_msg.lower():
            raise RuntimeError(
                f"Vector index 'chunk-embeddings' not found or not ready.\n\n"
                f"The index should be auto-created during text graph build.\n"
                f"If you haven't built the text graph yet, use:\n"
                f"  kg_build_graph(scope='unstructured')\n\n"
                f"Original error: {error_msg}"
            )
        else:
            raise RuntimeError(f"Vector search failed: {error_msg}")

    # Convert retriever items to evidence format
    evidence = []
    for item in search_result.items:
        metadata = item.metadata or {}
        evidence.append({
            "content": item.content,
            "score": metadata.get("score", 0.0),
            "metadata": metadata
        })

    # Format answer
    answer = format_retriever_results(evidence, include_entities=False)

    # Calculate confidence
    confidence = calculate_confidence(evidence, "vector")

    return {
        "answer": answer,
        "evidence": evidence,
        "confidence": confidence,
        "details": {
            "strategy": "vector",
            "index": "chunk-embeddings",
            "top_k": top_k,
            "result_count": len(evidence)
        }
    }


# =============================================================================
# Strategy 5: Hybrid Search (to be implemented in Phase 4)
# =============================================================================

@traceable(name="query.execute_hybrid")
def _execute_hybrid_search(driver: Driver, question: str, top_k: int = 5) -> dict:
    """Vector + fulltext via HybridRetriever.

    Args:
        driver: Neo4j driver instance
        question: Natural language question
        top_k: Number of results to return

    Returns:
        {
            "answer": str,
            "evidence": list,
            "confidence": float,
            "details": dict
        }

    Raises:
        RuntimeError: If OPENAI_API_KEY not set or indexes missing
    """
    # Check for OPENAI_API_KEY
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "Hybrid search requires OPENAI_API_KEY.\n"
            "Set OPENAI_API_KEY in your environment or .mcp.json.\n"
            "Required for text-embedding-3-large embeddings."
        )

    try:
        from neo4j_graphrag.embeddings import OpenAIEmbeddings
        from neo4j_graphrag.retrievers import HybridRetriever

        # Create embedder (consistent with US009)
        embedder = OpenAIEmbeddings(model="text-embedding-3-large")

        # Create retriever with both vector and fulltext indexes
        retriever = HybridRetriever(
            driver=driver,
            vector_index_name="chunk-embeddings",
            fulltext_index_name="chunk-fulltext",
            embedder=embedder
        )

        # Execute search
        search_result = retriever.search(query_text=question, top_k=top_k)

    except Exception as e:
        error_msg = str(e)
        if "index" in error_msg.lower() or "not found" in error_msg.lower():
            raise RuntimeError(
                f"Required indexes not found or not ready.\n\n"
                f"Hybrid search requires both 'chunk-embeddings' and 'chunk-fulltext' indexes.\n"
                f"These should be auto-created during text graph build.\n"
                f"If you haven't built the text graph yet, use:\n"
                f"  kg_build_graph(scope='unstructured')\n\n"
                f"Original error: {error_msg}"
            )
        else:
            raise RuntimeError(f"Hybrid search failed: {error_msg}")

    # Convert retriever items to evidence format
    evidence = []
    for item in search_result.items:
        metadata = item.metadata or {}
        evidence.append({
            "content": item.content,
            "score": metadata.get("score", 0.0),
            "metadata": metadata
        })

    # Format answer
    answer = format_retriever_results(evidence, include_entities=False)

    # Calculate confidence
    confidence = calculate_confidence(evidence, "hybrid")

    return {
        "answer": answer,
        "evidence": evidence,
        "confidence": confidence,
        "details": {
            "strategy": "hybrid",
            "vector_index": "chunk-embeddings",
            "fulltext_index": "chunk-fulltext",
            "top_k": top_k,
            "result_count": len(evidence)
        }
    }


# =============================================================================
# Strategy 6: Cross-Layer Traversal (to be implemented in Phase 5)
# =============================================================================

@traceable(name="query.execute_cross_layer")
def _execute_cross_layer_traversal(
    driver: Driver,
    question: str,
    top_k: int = 5,
    state: dict = None
) -> dict:
    """Hybrid search + entity traversal across text and domain layers.

    Bridges the text and domain graph layers:
    1. Hybrid search (vector + fulltext) finds relevant chunks
    2. FROM_CHUNK traversal finds text entities connected to those chunks
    3. CORRESPONDS_TO traversal (optional) links to domain entities

    Uses HybridCypherRetriever for combined semantic + keyword matching,
    so queries with specific names (e.g. "@home_chef") get precise fulltext
    hits alongside semantic relevance.

    Relationship pattern: (entity)-[:FROM_CHUNK]->(chunk)
    Entity resolution:   (text_entity)-[:CORRESPONDS_TO]->(domain_entity)

    Args:
        driver: Neo4j driver instance
        question: Natural language question
        top_k: Number of results to return
        state: Pipeline state (for label extraction)

    Returns:
        {
            "answer": str,
            "evidence": list,
            "confidence": float,
            "details": dict
        }

    Raises:
        RuntimeError: If OPENAI_API_KEY not set or indexes missing
    """
    # Check for OPENAI_API_KEY
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "Cross-layer traversal requires OPENAI_API_KEY.\n"
            "Set OPENAI_API_KEY in your environment or .mcp.json.\n"
            "Required for text-embedding-3-large embeddings."
        )

    # Get labels from both layers
    domain_labels = _get_domain_labels(state) if state else []
    text_entities = _get_text_entities(state) if state else []

    if not domain_labels:
        raise RuntimeError(
            "Cross-layer traversal requires domain graph.\n\n"
            "Domain labels not found in state. Please build the domain graph first:\n"
            "  kg_build_graph(scope='structured')\n\n"
            "Cross-layer traversal links text chunks to domain entities,\n"
            "so both layers must exist."
        )

    # Combine domain + text entity labels (deduplicated) for broad matching
    entity_labels = list(dict.fromkeys(domain_labels + text_entities))

    try:
        from neo4j_graphrag.embeddings import OpenAIEmbeddings
        from neo4j_graphrag.retrievers import HybridCypherRetriever

        # Create embedder (consistent with US009)
        embedder = OpenAIEmbeddings(model="text-embedding-3-large")

        # Build traversal Cypher query
        # CRITICAL: Start with "WITH node AS chunk, score" (required by HybridCypherRetriever)
        # CRITICAL: Relationship is FROM_CHUNK (created by SimpleKGPipeline)
        # CRITICAL: Direction is (entity)-[:FROM_CHUNK]->(chunk)
        traversal_cypher = f"""
        WITH node AS chunk, score
        MATCH (entity)-[:FROM_CHUNK]->(chunk)
        WHERE any(label IN labels(entity) WHERE label IN $entity_labels)
        OPTIONAL MATCH (entity)-[:CORRESPONDS_TO]->(domain_entity)
        RETURN
            chunk.text AS chunk_text,
            chunk.source_file AS source_file,
            entity,
            [label IN labels(entity) WHERE NOT label STARTS WITH '__'][0] AS entity_label,
            domain_entity,
            CASE WHEN domain_entity IS NOT NULL
                 THEN [label IN labels(domain_entity) WHERE NOT label STARTS WITH '__'][0]
                 ELSE null END AS domain_label,
            score
        ORDER BY score DESC
        LIMIT {top_k * 2}
        """

        # HybridCypherRetriever = vector + fulltext + Cypher traversal
        # Combines semantic similarity with keyword matching before traversal,
        # so queries with specific names/keywords (e.g. "@home_chef") get
        # precise fulltext matching alongside semantic relevance.
        retriever = HybridCypherRetriever(
            driver=driver,
            vector_index_name="chunk-embeddings",
            fulltext_index_name="chunk-fulltext",
            retrieval_query=traversal_cypher,
            embedder=embedder,
            result_formatter=_cross_layer_formatter
        )

        # Execute search with entity labels as parameter
        search_result = retriever.search(
            query_text=question,
            top_k=top_k,
            query_params={"entity_labels": entity_labels}
        )

    except Exception as e:
        error_msg = str(e)
        if "index" in error_msg.lower() or "not found" in error_msg.lower():
            raise RuntimeError(
                f"Required indexes not found or not ready.\n\n"
                f"Cross-layer traversal requires both indexes:\n"
                f"  - chunk-embeddings (vector)\n"
                f"  - chunk-fulltext (fulltext)\n\n"
                f"These are auto-created during text graph build.\n"
                f"If you haven't built the text graph yet, use:\n"
                f"  kg_build_graph(scope='unstructured')\n\n"
                f"Original error: {error_msg}"
            )
        else:
            raise RuntimeError(f"Cross-layer traversal failed: {error_msg}")

    # Convert retriever items to evidence format with entity context
    # Custom formatter already structures metadata with entity/domain fields
    evidence = []
    for item in search_result.items:
        metadata = item.metadata or {}
        evidence.append({
            "content": item.content,
            "score": metadata.get("score", 0.0),
            "metadata": metadata
        })

    # Format answer with entity context
    answer = format_retriever_results(evidence, include_entities=True)

    # Calculate confidence
    confidence = calculate_confidence(evidence, "cross_layer")

    return {
        "answer": answer,
        "evidence": evidence,
        "confidence": confidence,
        "details": {
            "strategy": "cross_layer",
            "index": "chunk-embeddings",
            "top_k": top_k,
            "domain_labels": domain_labels,
            "text_entities": text_entities,
            "entity_labels": entity_labels,
            "result_count": len(evidence),
            "traversal_query": traversal_cypher
        }
    }
