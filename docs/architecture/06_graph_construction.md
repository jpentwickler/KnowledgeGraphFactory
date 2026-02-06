# Stage 6: Graph Construction

## Purpose

Execute the approved plans to build the actual knowledge graph in Neo4j.
This stage is **NOT an LLM agent** - it's deterministic Python code that:

1. Imports structured data (CSV → Domain Graph)
2. Processes unstructured data (Markdown → Subject/Lexical Graph)
3. Connects the graphs via entity resolution

## Input

All approved artifacts from previous stages:

```python
state["approved_user_goal"] = {...}
state["approved_files"] = [...]
state["approved_construction_plan"] = {...}  # For CSV → nodes/relationships
state["approved_entity_types"] = [...]       # For entity extraction
state["approved_fact_types"] = {...}         # For relationship extraction
```

## Output

A populated Neo4j graph with three layers:

1. **Domain Graph**: Structured data from CSVs (Product, Supplier, Part, etc.)
2. **Lexical Graph**: Document chunks with embeddings
3. **Subject Graph**: Extracted entities and relationships from text
4. **Cross-layer links**: CORRESPONDS_TO relationships connecting Subject ↔ Domain

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DOMAIN GRAPH                              │
│  (Product)──[PART_OF]──(Assembly)──[HAS_PART]──(Part)           │
│      │                                           │               │
│      │                                    [SUPPLIED_BY]          │
│      │                                           │               │
│      │                                      (Supplier)           │
│      │                                                           │
│  [CORRESPONDS_TO]                                                │
│      │                                                           │
│      ▼                                                           │
├─────────────────────────────────────────────────────────────────┤
│                        SUBJECT GRAPH                             │
│  (Product:__Entity__)──[HAS_ISSUE]──(Issue:__Entity__)          │
│         │                                                        │
│    [HAS_FEATURE]                                                 │
│         │                                                        │
│         ▼                                                        │
│  (Feature:__Entity__)                                            │
│                                                                  │
│  [MENTIONED_IN]                                                  │
│         │                                                        │
│         ▼                                                        │
├─────────────────────────────────────────────────────────────────┤
│                        LEXICAL GRAPH                             │
│  (Document)──[HAS_CHUNK]──(Chunk)──[NEXT]──(Chunk)              │
│                             │                                    │
│                        [embedding]                               │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Components

### 1. Domain Graph Builder

Reads CSV files and creates nodes/relationships according to construction plan.

```python
# pipelines/domain_builder.py

def build_domain_graph(state: dict, neo4j_driver):
    """Build domain graph from structured data."""
    plan = state["approved_construction_plan"]
    
    # First pass: create nodes
    for name, spec in plan.items():
        if spec["construction_type"] == "node":
            import_nodes(neo4j_driver, spec)
    
    # Second pass: create relationships
    for name, spec in plan.items():
        if spec["construction_type"] == "relationship":
            import_relationships(neo4j_driver, spec)

def import_nodes(driver, spec: dict):
    """Import nodes from a CSV file."""
    query = f"""
    LOAD CSV WITH HEADERS FROM 'file:///{spec["source_file"]}' AS row
    MERGE (n:{spec["label"]} {{{spec["unique_column_name"]}: row.{spec["unique_column_name"]}}})
    SET n += row
    """
    driver.execute_query(query)

def import_relationships(driver, spec: dict):
    """Import relationships from a CSV file."""
    query = f"""
    LOAD CSV WITH HEADERS FROM 'file:///{spec["source_file"]}' AS row
    MATCH (from:{spec["from_node_label"]} {{{spec["from_node_column"]}: row.{spec["from_node_column"]}}})
    MATCH (to:{spec["to_node_label"]} {{{spec["to_node_column"]}: row.{spec["to_node_column"]}}})
    MERGE (from)-[r:{spec["relationship_type"]}]->(to)
    """
    driver.execute_query(query)
```

### 2. Lexical/Subject Graph Builder

Uses Neo4j GraphRAG library for entity extraction from text.

```python
# pipelines/text_builder.py

from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline
from neo4j_graphrag.llm import OpenAILLM  # or AnthropicLLM when available
from neo4j_graphrag.embeddings import OpenAIEmbeddings

def build_text_graph(state: dict, neo4j_driver, llm, embedder):
    """Process markdown files into subject and lexical graphs."""
    
    # Build entity schema from approved types
    entity_schema = {
        "node_types": state["approved_entity_types"],
        "relationship_types": [
            fact["predicate_label"].upper() 
            for fact in state["approved_fact_types"].values()
        ],
        "patterns": [
            [fact["subject_label"], fact["predicate_label"].upper(), fact["object_label"]]
            for fact in state["approved_fact_types"].values()
        ]
    }
    
    # Process each markdown file
    for file_path in state["approved_files"]:
        if file_path.endswith(".md"):
            pipeline = SimpleKGPipeline(
                llm=llm,
                driver=neo4j_driver,
                embedder=embedder,
                schema=entity_schema,
                # Custom loader and splitter for markdown
            )
            pipeline.run(file_path)
```

### 3. Entity Resolution

Connect Subject Graph entities to Domain Graph nodes.

```python
# pipelines/entity_resolution.py

def resolve_entities(state: dict, neo4j_driver):
    """Connect subject graph entities to domain graph nodes."""
    
    # Find entities that match domain nodes
    # Use fuzzy string matching on names
    
    query = """
    MATCH (entity:Product:__Entity__), (domain:Product)
    WHERE NOT domain:__Entity__
    WITH entity, domain, 
         apoc.text.jaroWinklerDistance(entity.name, domain.product_name) as distance
    WHERE distance < 0.2
    MERGE (entity)-[:CORRESPONDS_TO]->(domain)
    """
    neo4j_driver.execute_query(query)
```

## Testing Strategy

Unlike the design stages (1-5), the build stage doesn't require human-in-the-loop during execution. However, testing should verify:

### Pre-build Checks
- All approved artifacts are present
- CSV files exist and are readable
- Markdown files exist and are readable
- Neo4j connection is working

### Post-build Verification
```python
def verify_graph(driver):
    """Check that the graph was built correctly."""
    
    # Check node counts
    node_counts = driver.execute_query("""
        MATCH (n) 
        RETURN labels(n) as labels, count(*) as count
    """)
    
    # Check relationship counts
    rel_counts = driver.execute_query("""
        MATCH ()-[r]->() 
        RETURN type(r) as type, count(*) as count
    """)
    
    # Check for orphan nodes
    orphans = driver.execute_query("""
        MATCH (n) 
        WHERE NOT (n)--() 
        RETURN labels(n), count(*)
    """)
    
    # Check entity resolution worked
    correspondences = driver.execute_query("""
        MATCH (s:__Entity__)-[:CORRESPONDS_TO]->(d)
        RETURN labels(s), labels(d), count(*)
    """)
    
    return {
        "node_counts": node_counts,
        "relationship_counts": rel_counts,
        "orphan_nodes": orphans,
        "entity_correspondences": correspondences
    }
```

## Test Script

```python
# tests/test_06_build.py

import asyncio
import json
from pipelines.domain_builder import build_domain_graph
from pipelines.text_builder import build_text_graph
from pipelines.entity_resolution import resolve_entities
from utils.neo4j_client import get_driver

async def main():
    # Load state from previous stages
    with open("state_after_stage_5.json") as f:
        state = json.load(f)
    
    driver = get_driver()
    
    print("=" * 60)
    print("GRAPH CONSTRUCTION - Stage 6")
    print("=" * 60)
    
    # Step 1: Build domain graph
    print("\n[1/4] Building domain graph from CSV files...")
    build_domain_graph(state, driver)
    print("✓ Domain graph complete")
    
    # Step 2: Build lexical/subject graph
    print("\n[2/4] Processing markdown files...")
    build_text_graph(state, driver, llm, embedder)
    print("✓ Text processing complete")
    
    # Step 3: Entity resolution
    print("\n[3/4] Resolving entities...")
    resolve_entities(state, driver)
    print("✓ Entity resolution complete")
    
    # Step 4: Verification
    print("\n[4/4] Verifying graph...")
    results = verify_graph(driver)
    
    print("\nNode counts:")
    for row in results["node_counts"]:
        print(f"  {row['labels']}: {row['count']}")
    
    print("\nRelationship counts:")
    for row in results["relationship_counts"]:
        print(f"  {row['type']}: {row['count']}")
    
    print("\n" + "=" * 60)
    print("✅ Graph construction complete!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
```

## Dependencies

Stage 6 requires additional libraries:

```
neo4j>=5.0.0
neo4j-graphrag>=0.1.0  # For entity extraction
rapidfuzz>=3.0.0       # For fuzzy string matching
```

## Common Issues

1. **CSV encoding** - Ensure UTF-8 encoding. Add error handling for encoding issues.

2. **Memory with large files** - Process in batches using `LOAD CSV` with `PERIODIC COMMIT`.

3. **Entity resolution mismatches** - Tune the similarity threshold. Too strict = missed matches, too loose = false matches.

4. **Missing APOC** - Entity resolution queries use APOC. Ensure APOC plugin is installed.
