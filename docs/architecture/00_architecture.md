# Knowledge Graph Architecture

## Overview

The knowledge graph follows a **Domain-Subject-Lexical** three-layer architecture that integrates structured and unstructured data into a unified queryable graph.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   STRUCTURED DATA                         UNSTRUCTURED DATA                 │
│   (CSV files)                             (Markdown, text files)            │
│                                                                             │
│        │                                           │                        │
│        │ SOURCE                                    │ SOURCE                 │
│        ▼                                           ▼                        │
│   ┌─────────────┐                           ┌─────────────┐                 │
│   │             │                           │             │                 │
│   │   DOMAIN    │◄──── CORRESPONDS_TO ─────►│   SUBJECT   │                 │
│   │   GRAPH     │                           │   GRAPH     │                 │
│   │             │                           │             │                 │
│   └─────────────┘                           └──────┬──────┘                 │
│                                                    │                        │
│                                              MENTIONS                       │
│                                                    │                        │
│                                                    ▼                        │
│                                             ┌─────────────┐                 │
│                                             │             │                 │
│                                             │   LEXICAL   │                 │
│                                             │   GRAPH     │                 │
│                                             │             │                 │
│                                             └─────────────┘                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## The Three Layers

### 1. Domain Graph (Structured Data)

The Domain Graph represents your **business entities** imported from structured data sources like CSV files and databases.

**Characteristics:**
- Nodes represent well-defined business objects (Product, Supplier, Part, Assembly)
- Relationships represent known business connections (SUPPLIED_BY, PART_OF, CONTAINS)
- Data is clean, typed, and has unique identifiers
- Schema is defined by the `approved_construction_plan`

**Example:**
```
(:Product {product_id: "PROD001", name: "Stockholm Chair", price: 299.99})
    │
    ├──[:CONTAINS]──►(:Assembly {assembly_id: "ASM001", name: "Seat Assembly"})
    │                     │
    │                     └──[:HAS_PART]──►(:Part {part_id: "PRT001", name: "Foam Cushion"})
    │                                          │
    │                                          └──[:SUPPLIED_BY]──►(:Supplier {name: "Finnish Foam"})
    │
    └──[:CONTAINS]──►(:Assembly {assembly_id: "ASM002", name: "Base Assembly"})
```

**Source:** CSV files processed according to `approved_construction_plan`

---

### 2. Subject Graph (Extracted Knowledge)

The Subject Graph represents **semantic knowledge** extracted from unstructured text using NLP/LLM techniques.

**Characteristics:**
- Nodes are entities extracted from text (marked with `:__Entity__` label)
- Relationships are facts expressed as subject-predicate-object triples
- Entities may correspond to Domain Graph nodes (well-known entities)
- Entities may be newly discovered concepts (discovered entities)
- Schema is defined by `approved_entity_types` and `approved_fact_types`

**Example:**
```
(:Product:__Entity__ {name: "Stockholm Chair"})
    │
    ├──[:HAS_ISSUE]──►(:Issue:__Entity__ {name: "wobbly armrests"})
    │
    ├──[:HAS_ISSUE]──►(:Issue:__Entity__ {name: "gas lift failure"})
    │
    └──[:HAS_FEATURE]──►(:Feature:__Entity__ {name: "lumbar support"})
```

**Key Pattern - Entity Labels:**
- All extracted entities have the `:__Entity__` label (Neo4j GraphRAG convention)
- They also have their semantic label (`:Product`, `:Issue`, `:Feature`)
- This allows distinguishing extracted entities from domain nodes

**Source:** Markdown/text files processed according to `approved_entity_types` and `approved_fact_types`

---

### 3. Lexical Graph (Document Structure)

The Lexical Graph represents the **source documents** and their structure, enabling traceability and RAG queries.

**Characteristics:**
- Document nodes represent source files
- Chunk nodes represent text segments (for embedding-based retrieval)
- Chunks have vector embeddings for similarity search
- Maintains reading order via NEXT relationships

**Example:**
```
(:Document {path: "stockholm_chair_reviews.md", title: "Stockholm Chair Reviews"})
    │
    └──[:HAS_CHUNK]──►(:Chunk {index: 0, text: "Review by @office_guru...", embedding: [0.1, 0.2, ...]})
                          │
                          └──[:NEXT]──►(:Chunk {index: 1, text: "Review by @back_pain_no_more...", embedding: [...]})
                                            │
                                            └──[:NEXT]──►(:Chunk {index: 2, ...})
```

**Source:** Chunked markdown files with embeddings from the text processing pipeline

---

## Cross-Layer Relationships

The power of this architecture comes from **connecting the layers**:

### CORRESPONDS_TO (Subject ↔ Domain)

Links extracted entities to their canonical domain counterparts.

```
(:Product:__Entity__ {name: "Stockholm Chair"})
    │
    └──[:CORRESPONDS_TO]──►(:Product {product_id: "PROD001", name: "Stockholm Chair"})
```

**Why it matters:**
- Enables queries that start from extracted issues and trace to suppliers
- "Which supplier's parts are mentioned in negative reviews?"
- Requires entity resolution (fuzzy matching on names)

### MENTIONS (Subject ↔ Lexical)

Links extracted entities to the text chunks where they were found.

```
(:Issue:__Entity__ {name: "wobbly armrests"})
    │
    └──[:MENTIONED_IN]──►(:Chunk {text: "...the armrests feel a bit wobbly after a few months..."})
```

**Why it matters:**
- Provides provenance for extracted facts
- Enables "show me where this issue was mentioned"
- Supports RAG by linking retrieved chunks to structured knowledge

### SOURCE (Data ↔ Graph)

Conceptual link from original data sources to graph elements (often implicit).

---

## Complete Example: Root Cause Analysis Query

With all three layers connected, you can answer complex queries:

**Question:** "Which suppliers might be responsible for quality issues reported in reviews?"

**Cypher Query:**
```cypher
// Start from issues mentioned in reviews
MATCH (issue:Issue:__Entity__)<-[:HAS_ISSUE]-(product:Product:__Entity__)

// Bridge to domain graph
MATCH (product)-[:CORRESPONDS_TO]->(domainProduct:Product)

// Traverse domain graph to find suppliers
MATCH (domainProduct)-[:CONTAINS]->(:Assembly)-[:HAS_PART]->(:Part)-[:SUPPLIED_BY]->(supplier:Supplier)

// Return results
RETURN issue.name AS issue, 
       domainProduct.name AS product,
       supplier.name AS potential_supplier,
       count(*) AS mentions
ORDER BY mentions DESC
```

**Query Flow:**
```
LEXICAL          SUBJECT              DOMAIN
────────         ───────              ──────
                 
(Chunk)          (Issue)              
   │                │                 
   │ MENTIONED_IN   │ HAS_ISSUE       
   ▼                ▼                 
(Chunk)◄────────(Product:__Entity__)  
                    │                 
                    │ CORRESPONDS_TO  
                    ▼                 
                (Product)─────►(Assembly)─────►(Part)─────►(Supplier)
                              CONTAINS       HAS_PART    SUPPLIED_BY
```

---

## How Agents Build Each Layer

| Layer | Built By | Input | Output |
|-------|----------|-------|--------|
| Domain | Stage 6 (CSV import) | `approved_construction_plan` | Product, Supplier, Part nodes + relationships |
| Subject | Stage 6 (Text extraction) | `approved_entity_types`, `approved_fact_types` | Entity nodes with `:__Entity__` label + fact relationships |
| Lexical | Stage 6 (Text chunking) | Markdown files | Document, Chunk nodes with embeddings |
| CORRESPONDS_TO | Stage 6 (Entity resolution) | Subject + Domain nodes | Cross-layer links |
| MENTIONS | Stage 6 (Text extraction) | Neo4j GraphRAG pipeline | Chunk → Entity links |

---

## Schema Summary

### Node Labels

| Label | Layer | Description |
|-------|-------|-------------|
| `Product` | Domain | Products from products.csv |
| `Assembly` | Domain | Assemblies from assemblies.csv |
| `Part` | Domain | Parts from parts.csv |
| `Supplier` | Domain | Suppliers from suppliers.csv |
| `Product:__Entity__` | Subject | Products extracted from text |
| `Issue:__Entity__` | Subject | Issues/problems extracted from text |
| `Feature:__Entity__` | Subject | Features extracted from text |
| `Document` | Lexical | Source document metadata |
| `Chunk` | Lexical | Text segment with embedding |

### Relationship Types

| Type | Layer | Pattern |
|------|-------|---------|
| `CONTAINS` | Domain | (Product)-[:CONTAINS]->(Assembly) |
| `HAS_PART` | Domain | (Assembly)-[:HAS_PART]->(Part) |
| `SUPPLIED_BY` | Domain | (Part)-[:SUPPLIED_BY]->(Supplier) |
| `HAS_ISSUE` | Subject | (Product:__Entity__)-[:HAS_ISSUE]->(Issue:__Entity__) |
| `HAS_FEATURE` | Subject | (Product:__Entity__)-[:HAS_FEATURE]->(Feature:__Entity__) |
| `HAS_CHUNK` | Lexical | (Document)-[:HAS_CHUNK]->(Chunk) |
| `NEXT` | Lexical | (Chunk)-[:NEXT]->(Chunk) |
| `CORRESPONDS_TO` | Cross-layer | (Subject:__Entity__)-[:CORRESPONDS_TO]->(Domain) |
| `MENTIONED_IN` | Cross-layer | (Entity:__Entity__)-[:MENTIONED_IN]->(Chunk) |

---

## Visual Reference

The architecture diagram from the training materials:

```
┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
│                  │         │                  │         │                  │
│  Structured      │ SOURCE  │                  │         │  Unstructured    │
│  Data Sources    │────────►│  Domain Graph    │         │  Data Sources    │
│  (CSV)           │         │                  │         │  (Markdown)      │
│                  │         │                  │         │                  │
└──────────────────┘         └────────┬─────────┘         └────────┬─────────┘
                                      │                            │
                                      │                            │ SOURCE
                                      │ CORRESPONDS_TO             │
                                      │                            ▼
                                      │                   ┌──────────────────┐
                                      │                   │                  │
                                      └──────────────────►│  Subject Graph   │
                                                          │                  │
                                                          └────────┬─────────┘
                                                                   │
                                                                   │ MENTIONS
                                                                   │
                                                                   ▼
                                                          ┌──────────────────┐
                                                          │                  │
                                                          │  Lexical Graph   │
                                                          │                  │
                                                          └──────────────────┘
```

This architecture enables powerful queries that combine structured business knowledge with insights extracted from unstructured text, all while maintaining traceability back to source documents.
