# Target Architecture: Ontology-Enhanced Knowledge Graphs with SHACL and RDF

## A Reference Architecture for Layering Semantic Validation and Retrieval Optimization on Property Graphs

---

## 1. Executive Summary

This document defines the target architecture for enhancing Neo4j property graphs with a semantic layer built on RDF and SHACL (Shapes Constraint Language). The architecture addresses three core challenges that emerge as knowledge graphs scale:

1. **Context precision**: Delivering surgical, domain-specific schema context to LLM agents instead of overwhelming them with the full graph schema.
2. **Data quality assurance**: Validating graph data against formal constraints before LLM reasoning occurs.
3. **Retrieval optimization**: Grounding retriever selection and orchestration in explicit metadata about data characteristics rather than relying on LLM intuition.

The architecture is designed to be **additive and non-invasive**—Neo4j remains the primary data store and operational layer. The semantic layer sits on top, providing validation, context delivery, and retrieval planning without altering how the property graph is built or queried day-to-day.

---

## 2. Architectural Principles

### 2.1 Neo4j First
The property graph is always built first. Neo4j is the source of truth for data storage, traversal, and querying. The semantic layer is derived from the property graph, not the other way around. No semantic metadata pollutes the Neo4j data model.

### 2.2 Derive Before Define
SHACL shapes and RDF mappings are generated from introspection of the existing Neo4j graph. Manual definition is reserved only for enrichment—adding constraints and universal concept mappings that cannot be inferred from the data alone.

### 2.3 Modular by Domain
SHACL shapes are organized into domain-specific partitions that reflect the natural clustering of the graph. Each domain partition is independently loadable, enabling surgical context delivery to agents.

### 2.4 Reuse Before Create
When mapping local graph concepts to semantic vocabularies, existing published ontologies are preferred. Custom concepts are created only when no suitable match exists in established vocabularies.

### 2.5 Human in the Loop
Automated processes handle schema extraction, shape generation, and concept matching. Human review is required for approval of universal concept mappings, validation of edge-case classifications, and enrichment of business constraints that cannot be inferred from data alone.

---

## 3. Technology Stack

### 3.1 Core Components

| Component | Role | Description |
|-----------|------|-------------|
| **Neo4j** | Data layer | Property graph database. Stores all domain data as nodes, relationships, and properties. Provides Cypher querying, vector indexes, full-text indexes, and the Graph Data Science (GDS) library. |
| **Neosemantics (n10s)** | Bridge layer | Neo4j plugin that translates between property graph representations and RDF. Manages namespace prefixes and URI mappings. Enables export of Neo4j data as RDF triples and import of RDF data as property graph elements. |
| **RDFLib** | Semantic authoring | Python library for creating, manipulating, and serializing RDF data. Used to author SHACL shapes, define ontology concepts, and manage RDF serialization formats (Turtle, JSON-LD, RDF/XML). |
| **pySHACL** | Validation engine | Python library that validates RDF data against SHACL shape definitions. Takes data graphs and shape graphs as input, produces conformance reports identifying violations. |
| **Neo4j Graph Data Science (GDS)** | Graph analytics | Library for running graph algorithms including community detection (Louvain, Label Propagation), centrality metrics, and similarity computations. Used for domain partitioning. |

### 3.2 Supporting Tools

| Tool | Role |
|------|------|
| **Linked Open Vocabularies (LOV)** | Search engine for published ontologies at lov.linkeddata.es. Used during concept enrichment to find matching universal vocabulary terms. |
| **Python (Anaconda)** | Orchestration environment for all scripts—introspection, shape generation, classification, and enrichment agents. |
| **LLM Agent Framework** | Agent architecture (e.g., Claude with MCP tools) for assisted concept mapping, retrieval planning, and query decomposition. |

### 3.3 Installation Summary

- **n10s**: JAR file installed in Neo4j's `plugins/` directory. Activated via `CALL n10s.graphconfig.init()`.
- **RDFLib**: `pip install rdflib`
- **pySHACL**: `pip install pyshacl`
- **Neo4j GDS**: Installed as a Neo4j plugin (licensed separately for enterprise features).

---

## 4. Architecture Layers

The architecture consists of five layers, each with a distinct responsibility:

```
+---------------------------------------------------+
|  Layer 5: LLM Agent & Retrieval Planner           |
|  (Query decomposition, retriever orchestration)    |
+---------------------------------------------------+
|  Layer 4: Retrieval Strategy Metadata              |
|  (Per-property retrieval annotations on shapes)    |
+---------------------------------------------------+
|  Layer 3: Semantic Enrichment                      |
|  (Universal concept mappings, ontology reuse)      |
+---------------------------------------------------+
|  Layer 2: SHACL Shape Definitions                  |
|  (Validation constraints, domain partitioning)     |
+---------------------------------------------------+
|  Layer 1: Neo4j Property Graph                     |
|  (Data storage, Cypher, vector/text indexes)       |
+---------------------------------------------------+
```

### 4.1 Layer 1: Neo4j Property Graph

This is the operational data layer. It contains all domain knowledge represented as labeled property graph elements. It provides multiple retrieval mechanisms: Cypher traversal queries, vector similarity search via vector indexes, full-text search via text indexes, and hybrid combinations of the above.

The property graph is built using domain-natural terminology. Node labels, relationship types, and property names reflect the language of the domain without any semantic or RDF considerations. This layer is self-sufficient—all querying and data manipulation works without the layers above.

### 4.2 Layer 2: SHACL Shape Definitions

SHACL shapes are derived from the Neo4j property graph through automated introspection (see Section 5). Each shape defines:

- **Target class**: Which Neo4j node label the shape applies to.
- **Property constraints**: Expected properties, their data types, minimum/maximum values, cardinality (required vs. optional), and string patterns.
- **Relationship constraints**: Expected outgoing and incoming relationships, their target node types, and cardinality (e.g., "every RevenueStream must connect to exactly one CustomerSegment").
- **Domain partition membership**: Which logical domain the shape belongs to.

Shapes are organized into domain-specific files. Each file contains all shapes for one domain partition and is independently loadable. This enables surgical context delivery—only the relevant domain's shapes are loaded into an agent's context for a given task.

### 4.3 Layer 3: Semantic Enrichment

This layer adds universal concept mappings to the SHACL shapes. Each shape's target class is linked to the most appropriate concept from published ontologies using `rdfs:subClassOf` or `owl:equivalentClass` declarations. Properties are similarly mapped to published predicates where matches exist.

Common source ontologies include:

- **Schema.org**: General-purpose vocabulary covering organizations, products, offers, events, places, and common business concepts.
- **GoodRelations (GR)**: E-commerce and business model concepts—offerings, pricing, business entities, payment methods.
- **FIBO**: Financial Industry Business Ontology—financial instruments, contracts, investment structures, regulatory concepts.
- **Dublin Core (DC)**: Metadata terms—titles, descriptions, creators, dates, identifiers.
- **SKOS**: Simple Knowledge Organization System—taxonomies, concept schemes, broader/narrower relationships.
- **FOAF**: Friend of a Friend—people, organizations, social connections.
- **PROV-O**: Provenance ontology—tracking the origin and lineage of data.
- **Domain-specific ontologies**: Industry-specific vocabularies discoverable through LOV.

Concepts with no suitable match in published ontologies are defined in a custom namespace specific to the project. The custom namespace URI follows the pattern `https://{project-domain}/ontology#`.

### 4.4 Layer 4: Retrieval Strategy Metadata

This layer annotates SHACL shapes with per-property and per-relationship retrieval strategy tags. These annotations are derived from empirical analysis of the actual data in Neo4j (see Section 7). Each property receives:

- **Retrieval strategy tag**: One or more of `vector`, `exact-match`, `full-text`, `cypher-filter`, `traversal`.
- **Confidence score**: A numeric value (0.0-1.0) indicating how strongly the data characteristics support this classification.
- **Rationale**: Brief explanation of why this classification was assigned.

Each relationship receives:

- **Traversal priority**: Indicating how structurally important this relationship is for graph navigation, derived from centrality and frequency metrics.
- **Common path patterns**: Frequently occurring multi-hop traversal patterns that include this relationship.

### 4.5 Layer 5: LLM Agent & Retrieval Planner

This is the agent layer that consumes all layers below to execute queries. It has three sub-components:

**Query Decomposer**: Takes a natural language question, loads relevant domain SHACL shapes (selected based on concept recognition in the question), and breaks the question into retrieval sub-tasks. Each sub-task targets specific properties or relationships and is assigned a retrieval strategy based on the Layer 4 annotations.

**Retrieval Orchestrator**: Determines the execution order of sub-tasks and the data flow between them. Uses SHACL relationship definitions to understand how results from one sub-task connect to inputs for the next. Constructs a retrieval plan that chains vector search, Cypher traversal, and filtering steps.

**Result Validator**: After retrieval, passes the returned subgraph through pySHACL validation against the relevant shapes. Flags data quality issues, excludes malformed data, and presents validated results to the LLM for final reasoning.


---

## 5. Process: Deriving SHACL Shapes from Neo4j

This section describes the automated pipeline for generating SHACL shapes from an existing Neo4j property graph.

### 5.1 Step 1: Domain Partitioning via Community Detection

Before extracting schemas, the graph is partitioned into logical domains using community detection algorithms from the Neo4j Graph Data Science library.

**Approach**: Project the full graph (or a representative subgraph) into the GDS catalog. Run the Louvain or Label Propagation algorithm to detect communities of tightly connected node labels. Each detected community becomes a candidate domain partition.

**Cypher example (Louvain)**:
```cypher
CALL gds.graph.project('fullGraph', '*', '*')
CALL gds.louvain.stream('fullGraph')
YIELD nodeId, communityId
RETURN gds.util.asNode(nodeId).name AS node, communityId
ORDER BY communityId
```

**Output**: A mapping of node labels to domain IDs. For example: `{CustomerSegment: 1, ValueProposition: 1, RevenueStream: 1, Token: 2, SmartContract: 2, Wallet: 2, Exporter: 3, Shipment: 3, TrustScore: 3}`.

**Human review**: The automatically detected partitions are reviewed. Domains may be merged, split, or renamed to reflect meaningful business boundaries. Cross-domain bridge nodes (nodes that connect two domains) are identified and noted for inclusion in multiple domain shape files.

### 5.2 Step 2: Per-Domain Schema Extraction

For each domain partition, run introspection queries to extract the structural patterns.

**Node properties per domain**:
```cypher
MATCH (n)
WHERE labels(n)[0] IN $domainLabels
WITH labels(n) AS nodeLabels, keys(n) AS props, n
UNWIND props AS prop
RETURN DISTINCT nodeLabels, prop,
       apoc.meta.cypher.type(n[prop]) AS propType,
       count(*) AS occurrences
```

**Relationships within domain**:
```cypher
MATCH (a)-[r]->(b)
WHERE labels(a)[0] IN $domainLabels AND labels(b)[0] IN $domainLabels
RETURN DISTINCT labels(a) AS sourceLabels, type(r) AS relType,
       labels(b) AS targetLabels, count(*) AS frequency
```

**Cross-domain relationships**:
```cypher
MATCH (a)-[r]->(b)
WHERE labels(a)[0] IN $domainLabels AND NOT labels(b)[0] IN $domainLabels
RETURN DISTINCT labels(a) AS sourceLabels, type(r) AS relType,
       labels(b) AS targetLabels, count(*) AS frequency
```

**Cardinality analysis**:
```cypher
MATCH (a:NodeLabel)-[r:REL_TYPE]->(b:TargetLabel)
WITH a, count(b) AS relCount
RETURN min(relCount) AS minCardinality,
       max(relCount) AS maxCardinality,
       avg(relCount) AS avgCardinality
```

### 5.3 Step 3: SHACL Shape Generation

A Python script takes the extracted schema information and generates SHACL shapes using RDFLib. For each node label in a domain:

1. Create a `sh:NodeShape` targeting that class.
2. For each observed property, create a `sh:property` constraint with the observed data type, min/max count based on cardinality analysis (if a property appears on 100% of nodes, `sh:minCount 1`; if it is optional, `sh:minCount 0`).
3. For each observed relationship, create a `sh:property` constraint with `sh:node` pointing to the target shape and cardinality derived from the analysis.

**Example generated shape (Turtle format)**:
```turtle
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix ex: <https://example.org/ontology#> .

ex:CustomerSegmentShape a sh:NodeShape ;
    sh:targetClass ex:CustomerSegment ;
    sh:property [
        sh:path ex:name ;
        sh:datatype xsd:string ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
    ] ;
    sh:property [
        sh:path ex:type ;
        sh:datatype xsd:string ;
        sh:minCount 1 ;
        sh:in ("B2B" "B2C" "B2G") ;
    ] ;
    sh:property [
        sh:path ex:receivesValue ;
        sh:node ex:ValuePropositionShape ;
        sh:minCount 1 ;
    ] .
```

### 5.4 Step 4: Constraint Enrichment (Human-Assisted)

The generated shapes capture what exists in the data. This step adds constraints about what should exist—business rules that cannot be inferred from data patterns alone.

Examples of enrichment:

- Adding `sh:minInclusive 0` to numeric amount properties (values must be non-negative).
- Adding `sh:maxCount` constraints where business logic dictates limits.
- Adding `sh:pattern` constraints for string formats (e.g., ISO currency codes).
- Adding custom validation rules using SPARQL-based SHACL constraints for complex cross-property logic.

This is a manual step performed by domain experts, assisted by the LLM agent which can suggest likely constraints based on the data distribution.

---

## 6. Process: Universal Concept Mapping

This section describes how local graph concepts are mapped to published ontology vocabularies.

### 6.1 Agent-Assisted Mapping Workflow

The mapping process is driven by an enrichment agent that combines LLM knowledge, LOV API search, and human approval.

**For each concept (node label or relationship type) in the generated SHACL shapes**:

1. **LLM Knowledge Check**: The agent first uses its training knowledge of common ontologies (Schema.org, GoodRelations, Dublin Core, FIBO, etc.) to propose candidate mappings. For well-known concepts like "Organization" or "Product," this produces high-confidence matches immediately.

2. **LOV API Search**: For concepts where the LLM is uncertain, the agent queries the Linked Open Vocabularies API with the concept name and related terms. The API returns matching classes and properties from published ontologies, ranked by usage and relevance.

3. **Candidate Evaluation**: The agent compares each candidate's formal definition against the local concept's properties and relationships. A good match means the published concept's expected properties align with what exists in the graph. A poor match means the published concept expects properties that don't exist or has a fundamentally different semantic meaning.

4. **Recommendation Presentation**: The agent presents its recommendation to the human reviewer with the concept name, recommended mapping, confidence level, rationale, alternatives, and whether a custom concept is needed.

5. **Human Approval**: The reviewer approves, selects an alternative, or requests a custom concept. The approved mapping is written into the SHACL shape file as a `rdfs:subClassOf` or `owl:equivalentClass` declaration.

### 6.2 n10s Namespace Configuration

Once mappings are approved, the corresponding namespace prefixes are registered in Neo4j via n10s:

```cypher
CALL n10s.nsprefixes.add("schema", "https://schema.org/")
CALL n10s.nsprefixes.add("gr", "http://purl.org/goodrelations/v1#")
CALL n10s.nsprefixes.add("fibo", "https://spec.edmcouncil.org/fibo/ontology/")
CALL n10s.nsprefixes.add("ex", "https://example.org/ontology#")
```

And the label-to-URI mappings are registered:

```cypher
CALL n10s.mapping.add("https://schema.org/Audience", "CustomerSegment")
CALL n10s.mapping.add("http://purl.org/goodrelations/v1#PriceSpecification", "RevenueStream")
CALL n10s.mapping.add("https://example.org/ontology#CustomConcept", "CustomConcept")
```

These mappings enable n10s to translate between Neo4j labels and RDF URIs in both directions—export and import.


---

## 7. Process: Retrieval Strategy Classification

This section describes how SHACL shapes are annotated with retrieval strategy metadata based on empirical analysis of Neo4j data.

### 7.1 Data Characteristic Analysis

A Python script connects to Neo4j and analyzes each property across all nodes of each type. The following metrics are computed:

**For text properties**:
```cypher
MATCH (n:NodeLabel)
WHERE n.propertyName IS NOT NULL
RETURN avg(size(n.propertyName)) AS avgLength,
       count(DISTINCT n.propertyName) AS uniqueValues,
       count(n) AS totalNodes,
       percentileDisc(size(n.propertyName), 0.5) AS medianLength,
       percentileDisc(size(n.propertyName), 0.95) AS p95Length
```

**For numeric properties**:
```cypher
MATCH (n:NodeLabel)
WHERE n.propertyName IS NOT NULL
RETURN min(n.propertyName) AS minValue,
       max(n.propertyName) AS maxValue,
       avg(n.propertyName) AS avgValue,
       count(DISTINCT n.propertyName) AS uniqueValues,
       count(n) AS totalNodes
```

**For relationships (topology analysis)**:
```cypher
MATCH (a:NodeLabel)-[r:REL_TYPE]->(b)
RETURN count(r) AS frequency,
       count(DISTINCT a) AS distinctSources,
       count(DISTINCT b) AS distinctTargets,
       avg(size((a)-[:REL_TYPE]->())) AS avgOutDegree
```

### 7.2 Classification Rules

The classification applies rule-based thresholds to the measured metrics:

**Vector-searchable**: A text property is classified as vector-searchable when average text length exceeds 50 characters, unique values represent more than 80% of total nodes, and vocabulary diversity is high (measured by distinct word count relative to total word count). Confidence is proportional to how strongly the metrics exceed these thresholds.

**Exact-match / Cypher-filter**: A property is classified as exact-match when it is numeric, boolean, or date-typed; or when it is a string with low cardinality (unique values less than 20% of total nodes); or when it has a constrained value set (e.g., enum-like patterns detected in the data). Confidence is proportional to cardinality concentration.

**Full-text searchable**: A text property is classified as full-text searchable when it has moderate text length (20-50 characters average), moderate cardinality, and keyword-style content rather than natural language prose. This is a middle ground between vector and exact-match.

**Traversal-relevant**: A relationship is classified as traversal-relevant when it has high frequency relative to other relationships from the same source node type, when it connects nodes across different domain partitions (bridge relationships), and when centrality metrics (betweenness, PageRank) indicate structural importance. The Graph Data Science library provides these metrics.

### 7.3 Edge Case Handling

Properties with ambiguous metrics (moderate confidence in multiple categories) are flagged for human review. The enrichment agent also uses the semantic layer to inform borderline decisions. If a property is mapped to a universal concept like `schema:description`, the ontological definition confirms it is meant to be natural language text, reinforcing a vector classification even if the measured text length is shorter than the threshold.

Properties may legitimately belong to multiple retrieval categories. Classification operates at the property level within each shape, and a single node type can have properties tagged with different strategies. The retrieval planner combines strategies per-query based on which properties of a node are being targeted.

### 7.4 Annotation Format

Classifications are written as custom RDF annotations on the SHACL property constraints:

```turtle
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <https://example.org/ontology#> .
@prefix ret: <https://example.org/retrieval#> .

ex:ValuePropositionShape a sh:NodeShape ;
    sh:targetClass ex:ValueProposition ;
    sh:property [
        sh:path ex:description ;
        sh:datatype xsd:string ;
        ret:retrievalStrategy "vector" ;
        ret:confidence 0.92 ;
        ret:rationale "avgLength=142, uniqueRatio=0.97, highVocabDiversity" ;
    ] ;
    sh:property [
        sh:path ex:type ;
        sh:datatype xsd:string ;
        ret:retrievalStrategy "exact-match" ;
        ret:confidence 0.95 ;
        ret:rationale "cardinality=4, enumPattern=true" ;
    ] ;
    sh:property [
        sh:path ex:targets ;
        sh:node ex:CustomerSegmentShape ;
        ret:retrievalStrategy "traversal" ;
        ret:traversalPriority 0.88 ;
        ret:commonPaths "ValueProposition-[:TARGETS]->CustomerSegment-[:BELONGS_TO]->RevenueStream" ;
    ] .
```

---

## 8. Agent Query Execution Flow

This section describes the complete flow when an LLM agent receives a natural language question and uses the full architecture to produce an answer.

### 8.1 Step 1: Domain Identification and Shape Loading

The agent analyzes the incoming question to identify which domain(s) are relevant. It uses keyword recognition, semantic similarity to domain descriptions, or a lightweight classifier trained on domain-labeled example questions. Only the SHACL shape files for the identified domains are loaded into the agent's context window.

**Advantage over raw Neo4j schema**: Instead of loading the entire graph schema (which may be thousands of lines for a large graph), the agent loads only the relevant domain shapes—typically tens of lines. This preserves context window space for reasoning and reduces attention dilution.

### 8.2 Step 2: Query Decomposition

The agent reads the loaded SHACL shapes, including retrieval strategy annotations, and decomposes the question into retrieval sub-tasks. Each sub-task specifies the target node type and property or relationship, the retrieval strategy to use (from the annotation), the search terms or filter conditions extracted from the question, and dependencies on other sub-tasks.

**Advantage over ad hoc retriever selection**: The decomposition is grounded in explicit metadata rather than LLM intuition. The agent does not guess that a property needs vector search—it reads the annotation that confirms it, along with the confidence score.

### 8.3 Step 3: Retrieval Plan Construction

The agent determines the execution order of sub-tasks based on data dependencies. SHACL relationship definitions tell the agent how nodes from one sub-task connect to nodes in another, enabling it to construct a coherent retrieval chain.

**Example plan for a multi-strategy question**:

1. Execute vector search on `ValueProposition.description` for semantic similarity to query terms. Output: set of ValueProposition node IDs.
2. Execute Cypher traversal from matched ValuePropositions through `TARGETS` to CustomerSegment nodes. Output: set of CustomerSegment nodes with their properties.
3. Execute Cypher traversal from matched CustomerSegments through `BELONGS_TO` to RevenueStream nodes. Filter on `RevenueStream.amount > threshold`. Output: filtered RevenueStream nodes.
4. Aggregate and return the combined subgraph.

### 8.4 Step 4: Retrieval Execution

Each sub-task is executed against Neo4j using the appropriate retrieval mechanism. The agent generates Cypher queries informed by the SHACL shapes for structural correctness. Vector searches are scoped to the specific node types and properties indicated by the shapes.

**Advantage over unguided Cypher generation**: The SHACL shapes provide the agent with explicit knowledge of valid node types, property names, relationship directions, and cardinality. This dramatically reduces hallucinated or structurally incorrect Cypher queries.

### 8.5 Step 5: Result Validation

The retrieved subgraph is validated against the relevant SHACL shapes using pySHACL. The validation report identifies any nodes or relationships that violate the defined constraints—missing required properties, out-of-range values, incorrect relationship targets, or cardinality violations.

**Advantage over reasoning over unvalidated data**: The agent knows the data it is about to reason over is structurally sound. Malformed or incomplete data is flagged before it can contaminate the reasoning. For use cases where accuracy matters (financial projections, compliance reporting, investment decisions), this validation step is essential.

### 8.6 Step 6: LLM Reasoning over Validated Data

The agent reasons over the validated subgraph with the semantic context from the SHACL shapes and universal concept mappings. The formal definitions from mapped ontologies provide additional grounding for the agent's interpretation of the data.

**Advantage over pure property graph reasoning**: The agent has formal concept definitions to ground its reasoning rather than relying solely on node label names and its training data. The semantic layer provides a shared vocabulary that reduces ambiguity and misinterpretation.


---

## 9. Interaction Between Neo4j and the SHACL/RDF Layer

### 9.1 The Role of n10s as the Bridge

Neosemantics (n10s) is the critical integration point. It maintains a bidirectional mapping between Neo4j's property graph model and the RDF/SHACL semantic model.

**Neo4j to RDF direction (export)**:

- n10s translates Neo4j node labels to RDF class URIs using the configured mappings.
- Node properties become RDF literal triples.
- Relationships become RDF object property triples.
- The output is valid RDF that pySHACL can validate.

**RDF to Neo4j direction (import)**:

- n10s translates RDF class URIs back to Neo4j labels.
- RDF literal triples become node properties.
- RDF object property triples become relationships.
- This enables importing external RDF data into the property graph.

### 9.2 Namespace Management

n10s manages namespace prefixes that map short labels to full URIs:

```cypher
-- Register namespaces
CALL n10s.nsprefixes.add("schema", "https://schema.org/")
CALL n10s.nsprefixes.add("ex", "https://example.org/ontology#")

-- Register label-to-URI mappings
CALL n10s.mapping.add("https://schema.org/Audience", "CustomerSegment")
```

These mappings are persistent in Neo4j and are used automatically whenever n10s translates between representations.

### 9.3 Validation Flow

The validation flow uses n10s to extract relevant data from Neo4j as RDF, then pySHACL to validate:

```python
from pyshacl import validate
from rdflib import Graph

# Load SHACL shapes for the relevant domain
shapes_graph = Graph()
shapes_graph.parse("domain_shapes.ttl", format="turtle")

# Extract data from Neo4j as RDF via n10s
# (using Neo4j driver + n10s RDF export procedure)
data_graph = Graph()
data_graph.parse(neo4j_rdf_export, format="turtle")

# Validate
conforms, results_graph, results_text = validate(
    data_graph,
    shacl_graph=shapes_graph,
    inference="rdfs"
)

if not conforms:
    # Handle violations before LLM reasoning
    process_violations(results_text)
```

---

## 10. Retrieval Plan Architecture for Multi-Strategy Queries

### 10.1 The Problem

Real-world questions rarely map cleanly to a single retrieval strategy. A question like "Which high-revenue customer segments are receiving value propositions similar to blockchain traceability?" simultaneously requires vector search (semantic similarity on descriptions), Cypher filtering (numeric thresholds on revenue), and graph traversal (connecting matched nodes across relationship paths).

### 10.2 The Retrieval Plan Concept

Instead of picking one retriever, the agent constructs a retrieval plan—an ordered sequence of retrieval sub-tasks with data flow dependencies between them. The plan is analogous to a query execution plan in a relational database.

### 10.3 Plan Construction Logic

The agent uses three information sources to construct the plan:

1. **SHACL shapes** tell the agent what node types and properties exist and how they connect.
2. **Retrieval annotations** tell the agent which strategy is appropriate for each property.
3. **Relationship definitions** tell the agent how to chain results from one sub-task to the next.

The construction follows these rules:

- Sub-tasks that produce node IDs used by downstream sub-tasks execute first.
- Vector and full-text searches typically execute first (they produce initial candidate sets).
- Cypher traversals execute next (they expand from candidates along known relationship paths).
- Cypher filters execute last (they narrow results based on numeric or categorical constraints).
- Cross-domain queries load shapes from multiple domains and include bridge relationship traversals.

### 10.4 Handling Multi-Category Properties

When a single node type has properties tagged with different retrieval strategies, the plan assigns different sub-tasks to different properties of the same node. The results are joined by node ID. This is functionally equivalent to a multi-index query in a database—each index is consulted for what it does best, and results are intersected.

---

## 11. Implementation Phases

### Phase 1: Foundation (Recommended Starting Point)

- Install n10s in Neo4j.
- Select one domain of the existing graph.
- Run introspection queries to extract the domain schema.
- Generate basic SHACL shapes using a Python script with RDFLib.
- Test validation with pySHACL against actual graph data.
- Compare agent query quality with SHACL context vs. raw Neo4j schema using competency questions.
- **Deliverable**: One domain's SHACL shapes, validation script, comparison benchmark.

### Phase 2: Semantic Enrichment

- Build the enrichment agent with LOV API integration.
- Map all concepts from Phase 1 domain to universal vocabularies.
- Configure n10s namespace and label mappings.
- Extend to additional domains.
- **Deliverable**: Enriched SHACL shapes with universal mappings, n10s configuration.

### Phase 3: Retrieval Strategy Classification

- Build the data characteristic analysis script.
- Classify all properties and relationships with retrieval strategy tags.
- Annotate SHACL shapes with retrieval metadata.
- Test retriever selection accuracy with annotated shapes vs. without.
- **Deliverable**: Annotated SHACL shapes, classification report, benchmark results.

### Phase 4: Retrieval Planner

- Build the query decomposition component.
- Build the retrieval orchestration component.
- Build the result validation component.
- Integrate into the existing agent architecture as MCP tools or Python functions.
- **Deliverable**: Full retrieval planner integrated with agent framework.

### Phase 5: Continuous Maintenance

- Schedule periodic re-introspection of the Neo4j graph to detect schema drift.
- Re-generate and update SHACL shapes when new node types or properties are added.
- Re-run retrieval classification when data distributions change significantly.
- **Deliverable**: Automated maintenance pipeline.

---

## 12. Decision Framework: When Does This Architecture Pay Off?

The full architecture is justified when:

- The graph schema is too large to fit comfortably in an agent's context window.
- Retrieval quality is degrading because the agent picks wrong strategies or generates incorrect queries.
- Data quality issues are causing incorrect reasoning (missing properties, invalid values, wrong relationships).
- Multiple domains coexist in the graph and questions need focused context from specific domains.
- Interoperability with external systems or datasets that use RDF/OWL is required.
- Formal compliance or audit requirements demand provable data validation.

The architecture may not be justified when:

- The graph is small enough that the full schema fits easily in the agent's context.
- Data quality is consistently high and manually maintained.
- All queries are simple, single-strategy retrievals.
- The graph serves a single domain with a straightforward schema.

The recommended approach is always to start with Phase 1, measure the impact, and expand only when the measured improvement justifies the additional complexity.

---

## 13. Summary of Key Advantages

| Capability | Pure Neo4j | Neo4j + SHACL/RDF Layer |
|-----------|-----------|------------------------|
| Schema context for agents | Full schema dump (potentially large) | Surgical, per-domain shape loading |
| Query generation accuracy | Depends on schema comprehension | Guided by explicit constraints and types |
| Data validation | Manual or application-level checks | Automated SHACL validation with conformance reports |
| Retriever selection | LLM intuition based on question text | Grounded in empirical per-property classification |
| Multi-strategy retrieval | Ad hoc combination | Structured retrieval plans with dependency ordering |
| Semantic interoperability | None (proprietary labels) | Universal concept mappings via published ontologies |
| Concept reuse | N/A | Leverages Schema.org, GoodRelations, FIBO, etc. |
| Scalability of agent context | Degrades as schema grows | Remains focused regardless of total schema size |

---

*This document serves as a target architecture reference. Implementation should follow the phased approach outlined in Section 11, starting with a thin vertical slice to validate the approach before committing to the full stack.*
