# Adaptive Retrieval Architecture — `kg_query`

> How `kg_query` uses knowledge graph structure to select, generate, validate, and execute retrieval strategies.

---

## 1. Overview

`kg_query` is a single MCP tool that receives a natural language question and returns an answer grounded in the knowledge graph. Internally, it runs a three-phase pipeline:

```
Question + Context
        |
        v
 +-----------------------+
 |  Strategy Selection   |   Claude classifies the question against a
 |  (compact_summary)    |   ~200-token graph summary
 +-----------------------+
        |
        v
 +-----------------------+
 |  Strategy Execution   |   One of 5 retrieval strategies executes,
 |  (cypher_notation)    |   each using a different schema renderer
 +-----------------------+
        |
        v
 +-----------------------+
 |  Result Synthesis     |   Formatting + confidence scoring
 +-----------------------+
        |
        v
 { answer, evidence, confidence, status }
```

Every phase relies on a `GraphSchema` object — a canonical, in-memory model of the graph's structure — to make its decisions. Without it, the system falls back to the least powerful strategy (schema exploration) and cannot generate, validate, or repair Cypher queries.

---

## 2. The Canonical Graph Schema

The `GraphSchema` (`core/graph_schema.py`) is a set of dataclasses that encode all structural knowledge about the graph:

```python
@dataclass
class GraphSchema:
    nodes: list[NodeSchema]              # Every node type (domain + text)
    relationships: list[RelationshipSchema]  # Every relationship type
    overlapping_labels: set[str]         # Labels that appear in BOTH layers
```

Each node and relationship carries typed properties with optional parse hints:

```python
@dataclass
class PropertyInfo:
    name: str
    sample: str | None = None       # e.g., "$1,299.00"
    inferred_type: str = "string"
    parse_hint: str | None = None   # e.g., "Strip '$' and commas, cast with toFloat()"
```

The schema provides four **renderers**, each producing a different projection of the same structural data for a different consumer:

| Renderer | Tokens | Consumer | Purpose |
|---|---|---|---|
| `compact_summary()` | ~200 | Strategy selector | Labels, relationships, bridges, queryable features |
| `cypher_notation()` | ~800 | Cypher generator | Full schema with properties structurally inside their owner |
| `for_repair(violation)` | ~300 | Cross-layer regenerator | Filtered schema relevant to a specific violation |
| `markdown(node_counts)` | ~400 | Schema query result | Human-readable summary with optional counts |

The critical design invariant: **properties are structurally inside their owner** (node or relationship) in every renderer. This means the LLM sees where each property lives and cannot accidentally move `lead_time_days` from the `SUPPLIES` relationship to the `Supplier` node.

---

## 3. Strategy Selection — Why Graph Awareness Matters

### 3.1 The Selector Prompt

Strategy selection uses `compact_summary()` — a ~200-token digest of the graph:

```
Domain layer: Product, Assembly, Part, Supplier
Domain relationships: HAS_ASSEMBLY (Product->Assembly), CONTAINS_PART (Assembly->Part),
    SUPPLIES (Supplier->Part)
Text layer: Product, Part, Supplier, Review, Reviewer, Defect (all :__Entity__)
Text relationships: authored (Reviewer->Review), evaluates (Review->Product),
    mentions_defect_in (Review->Part), reports (Review->Defect),
    observed_in (Defect->Part), belongs_to (Part->Product)
Cross-layer bridges: Product, Part, Supplier (via CORRESPONDS_TO)
Queryable features: structured properties, text embeddings, fulltext index
```

This summary tells Claude three things a schema-unaware system cannot know:

1. **What exists in each layer** — `Product` in the domain layer has `price`, `product_id`; `Product` in the text layer is an extracted mention from reviews.
2. **How layers connect** — `Product`, `Part`, and `Supplier` appear in both layers and are bridged by `CORRESPONDS_TO`.
3. **What retrieval capabilities are available** — structured properties enable Cypher; text embeddings enable vector search; fulltext index enables hybrid search.

### 3.2 The Decision Rules

The system prompt encodes these strategy selection rules:

```
1. schema:      User asks about graph structure
2. cypher:      Precise traversal, counting, ranking, aggregation (including cross-layer)
3. vector:      Content/meaning in unstructured text (NO specific names)
4. hybrid:      Specific keywords AND semantic meaning
5. cross_layer: Text content linked to domain entities OR specific names/keywords
                needing exact matching + entity context
```

### 3.3 Example: How the Same Question Routes Differently

Consider these questions against the furniture supply chain graph:

| Question | Strategy | Why |
|---|---|---|
| "How many suppliers are there?" | **cypher** | COUNT aggregation on domain nodes |
| "What do customers say about quality?" | **vector** | Semantic search over review text chunks |
| "What do reviews say about the Stockholm Chair's legs?" | **cross_layer** | Text content linked to a specific domain product |
| "Which supplier has the lowest unit cost for oak legs?" | **cypher** | Aggregation over `SUPPLIES` relationship properties |
| "Reviews mentioning @angry_customer about drawer issues" | **cross_layer** | Specific @handle + semantic meaning, needs entity context |
| "What labels exist in the graph?" | **schema** | Graph structure exploration |

Without the compact summary, the selector cannot distinguish "How many suppliers are there?" (which needs a `MATCH (s:Supplier) RETURN count(s)` Cypher query) from "What do customers say about quality?" (which needs vector search over text chunks). Both mention entities, but they require fundamentally different retrieval mechanisms.

---

## 4. Cypher Generation — Schema as Type System

When the `cypher` strategy is selected, `_generate_cypher_query()` uses the full `cypher_notation()` renderer (~800 tokens) to give Claude precise structural context:

```
// DOMAIN LAYER
(:Product {product_id, product_name, price, description})
(:Assembly {assembly_id, assembly_name, quantity})
(:Part {part_id, part_name, quantity})
(:Supplier {supplier_id, name, specialty, city, country, website, contact_email})
(:Product)-[:HAS_ASSEMBLY {quantity}]->(:Assembly)
(:Assembly)-[:CONTAINS_PART {quantity}]->(:Part)
(:Supplier)-[:SUPPLIES {lead_time_days, unit_cost, minimum_order_quantity, preferred_supplier}]->(:Part)

// TEXT LAYER
(:Product:__Entity__ {name})
(:Part:__Entity__ {name})
(:Supplier:__Entity__ {name})
(:Review:__Entity__ {name})
(:Reviewer:__Entity__ {name})
(:Defect:__Entity__ {name})
(:Reviewer)-[:authored]->(:Review)
(:Review)-[:evaluates]->(:Product)
(:Review)-[:mentions_defect_in]->(:Part)
(:Review)-[:reports]->(:Defect)
(:Defect)-[:observed_in]->(:Part)
(:Part)-[:belongs_to]->(:Product)

// CROSS-LAYER BRIDGES
(:Product:__Entity__)-[:CORRESPONDS_TO]->(:Product)
(:Part:__Entity__)-[:CORRESPONDS_TO]->(:Part)
(:Supplier:__Entity__)-[:CORRESPONDS_TO]->(:Supplier)

// DATA FORMAT NOTES
  Product.price: Strip '$' and commas, cast with toFloat()
```

### 4.1 Why This Matters: Three Failure Modes Without Schema

**Failure 1: Property misplacement**. Without the schema, Claude might generate:

```cypher
-- WRONG: lead_time_days is on the SUPPLIES relationship, not on Supplier
MATCH (s:Supplier) WHERE s.lead_time_days < 14 RETURN s.name
```

The schema makes it structurally clear that `lead_time_days` belongs to `[:SUPPLIES]`, so the correct query is:

```cypher
-- CORRECT: property accessed on the relationship
MATCH (s:Supplier)-[r:SUPPLIES]->(p:Part)
WHERE toInteger(r.lead_time_days) < 14
RETURN s.name, p.part_name, r.lead_time_days
```

**Failure 2: Reversed direction**. Neo4j relationships are directed. The schema says `(Supplier)-[:SUPPLIES]->(Part)`. Without this, Claude might generate:

```cypher
-- WRONG: reversed direction, returns zero results with no error
MATCH (p:Part)-[:SUPPLIES]->(s:Supplier) RETURN p.part_name, s.name
```

**Failure 3: Data format mismatch**. The `price` property is stored as `"$1,299.00"` (a string). Without the parse hint, Claude might generate:

```cypher
-- WRONG: comparing string "$1,299.00" numerically fails
MATCH (p:Product) WHERE p.price > 500 RETURN p.product_name
```

The schema includes `Product.price: Strip '$' and commas, cast with toFloat()`, producing:

```cypher
-- CORRECT: parse hint applied
MATCH (p:Product)
WHERE toFloat(replace(replace(p.price, '$', ''), ',', '')) > 500
RETURN p.product_name, p.price
```

---

## 5. Deterministic Cypher Validation

After Cypher generation, `schema.validate_cypher()` runs **without any LLM call** and checks four structural properties:

```python
def validate_cypher(self, cypher: str) -> list[ValidationIssue]:
    # 1. Property access — is the property on the correct owner?
    # 2. Relationship existence — does this type exist? (suggests closest match if not)
    # 3. Direction — is the arrow pointing the right way?
    # 4. Cross-layer — does the query touch both layers without CORRESPONDS_TO?
```

### 5.1 Cross-Layer Violation Detection

The most architecturally significant check. The knowledge graph has two separate node populations:

- **Domain layer**: Clean, structured entities imported from CSVs (`products.csv`, `suppliers.csv`, etc.)
- **Text layer**: Entities extracted from review markdown files, all tagged `:__Entity__`

Labels like `Product`, `Part`, and `Supplier` exist in **both** layers. A `Product` node from `products.csv` and a `Product:__Entity__` node extracted from a review are **different nodes**. They are connected only through `CORRESPONDS_TO` relationships created during entity resolution.

The validator detects when a query uses relationships from both layers without this bridge:

```python
domain_used = used_rels & domain_rel_types    # e.g., {SUPPLIES}
text_used = used_rels & text_rel_types        # e.g., {reports}
if domain_used and text_used and "CORRESPONDS_TO" not in used_rels:
    # Cross-layer violation
```

### 5.2 Guided Regeneration

When a cross-layer violation is detected, the system doesn't just fail — it **repairs** the query:

1. Extracts the specific violation details
2. Calls `schema.for_repair(violation)` to produce a **filtered schema** containing only the relevant relationships, overlapping labels, and the bridge pattern
3. Sends the failed query + violation context + repair schema to Claude
4. Claude rewrites with the `CORRESPONDS_TO` bridge

**Example**: A question like "Which suppliers have the most defect reports in reviews?" might initially generate:

```cypher
-- INITIAL (violates cross-layer rule)
MATCH (s:Supplier)-[:SUPPLIES]->(p:Part)<-[:observed_in]-(d:Defect)<-[:reports]-(r:Review)
RETURN s.name, count(d) AS defects ORDER BY defects DESC
```

This mixes domain relationships (`SUPPLIES`) with text relationships (`observed_in`, `reports`) without bridging. The repair prompt includes:

```
FAILED QUERY: [the query above]

WHY IT FAILS: Cross-layer query uses domain rels ['SUPPLIES'] and text rels
['observed_in', 'reports'] without CORRESPONDS_TO bridge

BRIDGE PATTERN:
  (t:__Entity__:Label)-[:CORRESPONDS_TO]->(d:Label)
```

The regenerated query:

```cypher
-- CORRECTED: bridges via CORRESPONDS_TO
MATCH (r:Review)-[:reports]->(d:Defect)-[:observed_in]->(tp:Part:__Entity__)
MATCH (tp)-[:CORRESPONDS_TO]->(dp:Part)
MATCH (s:Supplier)-[:SUPPLIES]->(dp)
RETURN s.name, count(DISTINCT d) AS defects ORDER BY defects DESC
```

---

## 6. Cross-Layer Traversal Strategy

The `cross_layer` strategy is the most graph-architecture-dependent. It uses a `HybridCypherRetriever` that combines three steps:

```
 [1] Hybrid search (vector + fulltext) finds relevant text chunks
                    |
                    v
 [2] FROM_CHUNK traversal finds text entities connected to those chunks
                    |
                    v
 [3] CORRESPONDS_TO traversal links text entities to domain entities
```

The traversal Cypher is injected into the retriever and encodes the exact graph architecture:

```cypher
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
```

The `$entity_labels` parameter is dynamically built from the schema:

```python
domain_labels = schema.domain_labels    # [Product, Assembly, Part, Supplier]
text_labels = schema.text_labels        # [Product, Part, Supplier, Review, Reviewer, Defect]
entity_labels = list(dict.fromkeys(domain_labels + text_labels))  # deduplicated
```

### 6.1 Example: "What do reviews say about drawer rail quality?"

1. **Hybrid search** finds text chunks semantically similar to "drawer rail quality" AND containing keyword matches
2. **FROM_CHUNK traversal** finds entities like `Part:__Entity__("drawer rails")`, `Defect:__Entity__("rough edges")`, `Product:__Entity__("Helsingborg Dresser")`
3. **CORRESPONDS_TO traversal** links `Part:__Entity__("drawer rails")` to the domain `Part` node from `parts.csv`, which has `part_id`, and from there we can reach the `Supplier` via `SUPPLIES`

The result includes both the review text ("the drawer rails were the worst part — they were defective") and the domain entity context (which supplier provides those drawer rails, at what cost and lead time).

---

## 7. Schema-Aware Layer Sampling

When the `schema` strategy runs, it must handle **overlapping labels** — labels that exist in both domain and text layers:

```python
if label in overlapping:
    # Domain copy: exclude __Entity__ nodes
    session.run(f"MATCH (n:`{label}`) WHERE NOT n:`__Entity__` RETURN keys(n) LIMIT 1")
    # Text copy: stored under "label:__Entity__" key
    session.run(f"MATCH (n:`{label}`) WHERE n:`__Entity__` RETURN keys(n) LIMIT 1")
```

For the furniture supply chain graph, `Product` in the domain layer has properties `{product_id, product_name, price, description}`, while `Product:__Entity__` in the text layer has `{name}`. A schema-unaware system would sample one node at random and return a mixed property set, leading to incorrect downstream Cypher generation.

---

## 8. The Full Orchestration (`kg_query` in `mcp_server/server.py`)

```python
async def kg_query(question: str, context: str = "") -> dict:
    state = _load_clean_state()
    driver = get_neo4j_driver()
    schema = _get_schema(state, driver)    # cached, invalidated on state changes

    # Phase 1: Classify (uses compact_summary)
    strategy_data = await _select_retrieval_strategy(question, context, state, schema=schema)

    # Phase 2: Execute (uses cypher_notation, for_repair, validate_cypher)
    if strategy == "cypher":
        cypher_query = await _generate_cypher_query(question, schema, context)
        result, correction_note = await _execute_validated_cypher(
            driver, cypher_query, question, state, schema=schema
        )
    elif strategy == "cross_layer":
        result = _execute_cross_layer_traversal(driver, question, top_k, state, schema=schema)
    # ... other strategies ...

    return { "answer": ..., "evidence": ..., "confidence": ..., "status": ... }
```

The schema flows through every phase:
- **Selection**: `compact_summary()` tells Claude what retrieval capabilities exist
- **Generation**: `cypher_notation()` gives Claude the type system for Cypher
- **Validation**: `validate_cypher()` catches structural errors deterministically
- **Repair**: `for_repair()` provides focused context for cross-layer regeneration
- **Execution**: `domain_labels`, `text_labels`, `overlapping_labels` control layer-aware sampling and entity label filtering

---

## 9. Confidence Scoring

Each strategy reports confidence differently, reflecting the certainty of its evidence:

| Strategy | Confidence | Basis |
|---|---|---|
| schema | 1.0 | Deterministic introspection |
| cypher | 0.8 (results) / 0.2 (empty) | Query executed successfully but empty may mean wrong query |
| vector | 0.3 - 0.9 | Average cosine similarity of top-3 results |
| hybrid | 0.3 - 0.9 | Blended similarity scores |
| cross_layer | 0.3 - 0.9 | Hybrid similarity scores |

---

## 10. The Core Argument

A knowledge graph is not a document store — it is a **typed, directed, multi-layer structure**. Retrieval strategies that ignore this structure produce one of three failure modes:

1. **Silent empty results**: Wrong relationship direction, wrong property placement, or cross-layer traversal without bridges. The query executes successfully but returns nothing.

2. **Wrong layer**: Searching text chunks when the answer is in structured properties (or vice versa). A schema-unaware system has no basis to distinguish these.

3. **Conflated populations**: Treating domain `Product` and text `Product:__Entity__` as the same nodes. This produces mixed property sets and incorrect aggregations.

The `GraphSchema` object serves as a **query compiler's type system** — it tells the retrieval pipeline what operations are valid, where properties live, how layers connect, and what data formats to expect. Without it, the retriever is a text search engine that happens to be connected to a graph database. With it, the retriever exploits the full structure of the knowledge graph to select the right strategy, generate correct queries, and bridge across layers.
