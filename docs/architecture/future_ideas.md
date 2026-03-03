# KG-Factory Roadmap: From Exploration Tool to Industrial Pipeline

## Vision

Industrialized knowledge graph construction at scale. KGs are infrastructure
for domain-specific agents, not an end product. The construction pipeline must
be reliable, fast, cheap, and repeatable. Human involvement is reserved for
new domain onboarding, not routine KG production.

```
Target value chain:

  Data Sources → Construction Pipeline → Knowledge Graph → Domain Agents → End Users
                         ↑                      ↑                ↑
                    industrialized          the product      the consumers
                    (this roadmap)         (optimized for     (the reason
                                           agent access)     this exists)
```

## Two Modes of Operation

**Exploration mode** (current): Interactive agents help a human discover the
right schema, entity types, and fact types for a new domain. Conversational,
iterative, human-in-the-loop at every stage. This mode produces a validated
schema template.

**Industrial mode** (target): A deterministic pipeline takes a schema template
+ data and produces a KG without conversation. No agent loops. No approval
gates. Runs unattended in CI, Airflow, or a scheduled job.

```
Exploration mode (new domains):
  Human ↔ Agents → Validated Schema Template (one-time per domain)

Industrial mode (production):
  Schema Template + Data → Pipeline → KG → Validate → Deploy Query Endpoint
```

The interactive agents don't disappear -- they become the template authoring
tool. They run once per domain to produce the template. The industrial pipeline
runs every time new data arrives.

---

## Completed

### Extraction Quality Roadmap Phase 1 (Done)

Implemented in `tools/extraction_tools.py`:

- [x] Few-shot examples in NER prompt (`_build_ner_prompt()`, lines 308-323)
- [x] Few-shot examples in Fact prompt (`_build_fact_prompt()`, lines 367-380)
- [x] Content threshold raised from 50K to 150K (`build_file_content()`, line 158)

---

## Phase A: Solidify the Foundation

Current pipeline improvements. These make both exploration and industrial
modes better.

### Priority 1: Evidence Feedback Loop

**Source**: Extraction Quality Roadmap Phase 2 (`11_extraction_quality_roadmap.md`)

**What**: Add a second LLM call after `gather_evidence()` that sees the evidence
results and refines the proposal. Drop zero-evidence types, improve search
patterns, add missed types.

```
Current:   propose (1 call) → evidence (0 calls) → return
Target:    propose (1 call) → evidence (0 calls) → refine (1 call) → return
```

Skip the refinement call if every proposed type has `total_mentions > 0`.

**Why**: Closes the biggest quality gap in extraction. Two LLM calls total.
Better extraction means better schema templates and more reliable industrial
runs.

**Scope**: New `refine_entity_types()` and `refine_fact_types()` in
`extraction_tools.py`, update orchestration in `server.py`, ~10 new tests.

---

### Priority 2: Multi-Use-Case Tagging Foundation

**Source**: `09_multi_use_case_integration.md`, Next Steps 1-3

**What**: Three small changes:

1. Add `_use_case` property to all nodes in `domain_builder.py` import queries
2. Add `use_case` key to state during `kg_user_intent`
3. Scope entity resolution queries to `AND entity._use_case = domain._use_case`

**Why**: Prerequisite for company-wide ontology. Without this, multiple KGs on
the same Neo4j instance cross-contaminate. Essential for both multi-use-case
merge and industrial-mode multi-domain production.

**Scope**: A few lines each in `domain_builder.py`, `text_builder.py`,
`entity_resolution.py`, and `agents/user_intent.py`.

---

### Priority 3: Embedding-Based Entity Resolution

**Source**: Adamchic's Fixed Entity Architecture (FEA) research

**What**: Replace rapidfuzz + Jaro-Winkler string matching in
`pipelines/entity_resolution.py` with cosine similarity between entity
embeddings for `CORRESPONDS_TO` resolution.

**Why**: String matching fails on semantic equivalences ("drawer hardware" vs
"Drawer Rails"). For industrial mode, entity resolution must work without
human review of candidates. Embedding similarity is more reliable unattended.

**Scope**: ~100 lines in entity resolution path. Reuse existing OpenAI
embeddings infrastructure from `text_builder.py`.

---

### Priority 4: Context-Aware Per-File Processing + Bin-Packing

**Source**: Extraction Quality Roadmap Phase 3 (`11_extraction_quality_roadmap.md`)

**What**:
- Type accumulation across files via `prior_types` parameter
- Bin-packing small files into single API calls via `group_files()`
- User message forwarding to all per-file calls

**Why**: Industrial mode processes 100s of files. The current per-file fallback
loses context and wastes API calls. This is a scaling prerequisite.

**Scope**: New parameters in prompt builders, new helper, update fallback in
`server.py`, ~13 new tests.

---

### Priority 5: Second Real Use Case

Build a KG for a domain you actually care about. Validate Priorities 1-4 with
real data. The approved schema from this use case becomes the first entry in
the schema template library.

---

## Phase B: Build the Industrial Pipeline

The transition from exploration tool to production system. These items create
the "industrial mode" that runs without conversation.

### Priority 6: Schema Template Library

**Concept**: Extract reusable schema templates from completed KGs. A template
captures the approved artifacts from a domain that's been through exploration:

```
templates/
├── supply_chain/
│   ├── domain_schema.json          # node types, relationships, CSV mappings
│   ├── entity_types.json           # text extraction entity types
│   ├── fact_types.json             # relationship templates
│   └── competency_questions.json   # quality validation CQs
├── customer_experience/
└── ...
```

A new project picks a template, applies customizations, and runs the pipeline.
80% of the schema is reused. The remaining 20% is domain-specific adjustment.

**Why**: This is the key leverage point for industrialization. Without templates,
every new project rediscovers what supply chains have Products, Parts, and
Suppliers. With templates, that knowledge is captured once and reused.

**Trigger**: After completing Priority 5 (second real use case). Two completed
domains give you the first two templates and reveal which parts generalize.

**Scope**: Template format definition, export function from state to template,
import function from template to state, CLI or API entry point.

---

### Priority 7: Headless Pipeline Runner

**Concept**: A single function that takes config + data and produces a KG
without any agent conversation:

```python
from kg_factory import build_knowledge_graph

result = build_knowledge_graph(
    data_dir="./data",
    schema_template="supply_chain",
    customizations={"extra_entity_types": ["Warranty"]},
    neo4j_uri="bolt://localhost:7687",
    validate=True,   # run CQ evaluation after build
)
```

Internally this calls the same builders (domain_builder, text_builder,
entity_resolution) but skips the agent loops entirely. Schema comes from the
template, not from a conversation.

**Why**: This is industrial mode. Runs in CI/CD, Airflow, cron, or any
orchestrator. No MCP, no Claude Code, no human approval. The human approved
the template; the pipeline applies it.

**Trigger**: After Priority 6 (schema templates exist). The pipeline runner
consumes templates.

**Scope**: New `pipelines/headless_runner.py`. Orchestrates existing builders.
Adds validation step (CQ evaluation as quality gate). Returns structured
build report.

---

### Priority 8: Automated Quality Gate

**Concept**: After headless build, automatically run CQ evaluation and fail
the build if coverage score drops below a threshold. This replaces human
review of the graph with automated validation.

```python
# In headless_runner.py
build_result = run_builders(config)
eval_result = evaluate_competency_questions(state, driver)

if eval_result["coverage_score"] < config.min_coverage:
    raise BuildQualityError(
        f"Coverage {eval_result['coverage_score']:.0%} below "
        f"threshold {config.min_coverage:.0%}",
        failing_cqs=eval_result["not_answerable"],
    )
```

**Why**: Industrial pipelines need pass/fail signals. You can't have a human
inspect every graph. CQ evaluation already exists (US014) -- this wraps it
as a build gate.

**Trigger**: After Priority 7 (headless runner exists).

**Scope**: Small. Integration of existing `_run_cq_evaluation()` into the
headless pipeline with threshold configuration.

---

## Phase C: Harden the Query Layer

The query layer is the API contract for domain-specific agents. It must be
reliable, fast, and structured for agent consumption.

### Priority 9: Structured Query Results for Domain Agents

**Concept**: Domain agents need structured data, not just text chunks. Add a
query mode that returns entities, properties, paths, and aggregates as JSON:

```python
# Current: returns text chunks (good for RAG)
{"content": "The drawer rails were defective...", "score": 0.87}

# Target: returns structured data (good for domain agents)
{
    "entities": [
        {"label": "Part", "name": "Drawer Rails", "part_id": "PT-1050"},
        {"label": "Supplier", "name": "German Precision Fasteners", "supplier_id": "S-1078"}
    ],
    "paths": [
        {"from": "Drawer Rails", "rel": "SUPPLIES", "to": "German Precision Fasteners"}
    ],
    "evidence": ["@angry_customer: drawer rails were so rough..."],
    "confidence": 0.92
}
```

**Why**: Domain agents making decisions need facts, not passages. A supply
chain agent deciding whether to switch suppliers needs the supplier ID, cost,
and lead time -- not a review excerpt.

**Trigger**: When building the first domain-specific agent that consumes the
KG. The agent's needs will define the exact response format.

**Effort**: Medium. New response formatter in query_builder. New query mode
parameter in kg_query / query_server.

---

### Priority 10: Deterministic Strategy Selection

**Concept**: Replace Claude-based strategy selection with rule-based selection
grounded in retrieval hints (computed from data characteristics after build).

```python
# Current: Claude guesses
strategy = ask_claude_to_pick_strategy(question, context)

# Target: rules + hints, no LLM call
strategy = select_strategy(question, state["retrieval_hints"])
```

Retrieval hints are computed once after graph build (see Future Idea 2). The
strategy selector becomes a deterministic function: keyword patterns map to
strategies, property types map to strategies, question classification maps
to strategies.

**Why**: Domain agents need predictable latency. An LLM call for strategy
selection adds 1-3 seconds and non-determinism to every query. For industrial
use, strategy selection should be instant and repeatable.

**Trigger**: When query latency matters -- i.e., when a domain agent is in
a conversation with an end user and can't wait for strategy selection.

**Effort**: Medium. Data analysis script + rule-based selector + integration.

---

### Priority 11: Production Query Server

**Concept**: Evolve `query_server.py` from a dev tool (2 MCP tools,
in-memory sessions) into a production service:

- REST API (not just MCP) for universal client access
- Authentication and rate limiting
- Connection pooling and query caching
- Schema introspection endpoint (domain agents discover what they can query)
- Health checks and monitoring
- Multi-tenant (serve multiple KGs from one instance)

**Why**: Domain agents will connect via REST, not MCP. Enterprise deployment
needs auth, monitoring, and multi-tenancy. The current query server is a
prototype.

**Trigger**: When deploying the first domain agent to users beyond yourself.

**Effort**: High. This is essentially US021 (Remote Query Server) fully
realized. Some groundwork exists in `docs/architecture/12_remote_query_distribution.md`.

---

## Phase D: Scale to Company-Wide Ontology

Building multiple domain KGs and composing them into a unified knowledge base.

### Priority 12: Multi-Use-Case Merge Tool (kg_merge)

**Source**: `09_multi_use_case_integration.md`

**Concept**: MCP tool / Python function that:
1. Loads base state (merged/) and new use case state
2. Detects concept overlaps (same label, different label same meaning, unique)
3. Presents merge strategy options per shared concept
4. Executes merge in Neo4j (property copying, relationship migration, dedup)
5. Saves merged state

**Why**: The mechanism for growing from domain-specific KGs to company-wide
ontology. Each use case is built independently, then composed.

**Trigger**: After building two real use cases that share concepts (e.g.,
both have "Product" or "Customer").

**Effort**: Medium-High. State comparison logic, Cypher merge queries, user
interaction for conflict resolution.

---

### Priority 13: Schema Template Inheritance

**Concept**: Templates can extend other templates. A "retail supply chain"
template inherits from "supply chain" and adds retail-specific types:

```json
{
    "extends": "supply_chain",
    "add_entity_types": ["StoreLocation", "ShelfPlacement"],
    "add_fact_types": [
        {"subject": "Product", "predicate": "stocked_at", "object": "StoreLocation"}
    ]
}
```

**Why**: As the template library grows, domains share common patterns. Supply
chain, retail, manufacturing all share Products/Parts/Suppliers. Inheritance
avoids duplication and ensures consistency.

**Trigger**: When the template library has 3+ templates with visible overlap.

**Effort**: Medium. Template resolution logic, merge of inherited + local
definitions.

---

## Future Ideas (Store for Later)

Ideas worth revisiting when specific triggers fire.

### Idea 1: Chunk-to-Domain Direct Linking via Cosine Similarity

**Source**: Adamchic's Fixed Entity Architecture (FEA)

**Concept**: Direct `RELATES_TO` edges between Chunk embeddings and domain
entity embeddings (cosine similarity > 0.8 threshold). Bypasses the extraction
dependency for chunk-to-domain connectivity.

**Trigger**: Cross-layer query recall is measurably low. CQ evaluation shows
`partial`/`not_answerable` CQs with relevant but unreachable chunks.

**Effort**: ~100 lines. Depends on Priority 3 (embedding-based resolution).

---

### Idea 2: SHACL Validation as Post-Build Quality Gate

**Source**: Target Architecture doc, Layer 2

**Concept**: Derive SHACL shapes from approved schema, validate Neo4j data
with pySHACL after build. Catches missing properties, orphan relationships,
cardinality violations.

**Trigger**: Data quality issues cause incorrect query results. Graph too
large for manual inspection. Also valuable as part of the automated quality
gate (Priority 8) for formal validation beyond CQ coverage.

**Effort**: Medium. n10s + RDFLib + pySHACL. New dependency.

---

### Idea 3: Domain Partitioning for Focused Agent Context

**Source**: Target Architecture doc, Section 5.1

**Concept**: GDS community detection to partition graph into domains. Load
only relevant domain context per query.

**Trigger**: Unified graph schema exceeds ~50 node types. Query quality
degrades from context dilution.

**Effort**: Medium-High. Depends on GDS plugin + multiple merged use cases.

---

### Idea 4: Universal Concept Mapping (Schema.org, FIBO, etc.)

**Source**: Target Architecture doc, Layer 3

**Concept**: Map local concepts to published ontologies for interoperability.

**Trigger**: Integration with external RDF datasets or cross-organization
knowledge sharing requirement.

**Effort**: Low-Medium. Depends on an actual interoperability requirement.

---

### Idea 5: Multi-Step Retrieval Plans

**Source**: Target Architecture doc, Section 10

**Concept**: Decompose complex questions into ordered retrieval sub-tasks
(vector → traverse → filter → aggregate).

**Trigger**: Complex CQs fail because they need chained strategies. Structural
CQs pass but cross-domain analytical CQs fail.

**Effort**: High. Depends on retrieval strategy metadata (Priority 10).

---

### Idea 6: Local LLM with Iterative Convergence

**Source**: Extraction Quality Roadmap, Section 8

**Concept**: Replace Claude extraction calls with local LLM iteration
(propose → evidence → critic → revise, 2-3 rounds). Zero API cost.

**Trigger**: API costs become a concern AND extraction roadmap Phases 1-4
are complete.

**Effort**: High. Provider abstraction + iteration loop + benchmarking.

---

### Idea 7: Fixed Ontology Anchor Layer (FEA-Style)

**Source**: Adamchic's FEA, Layer 1

**Concept**: For mature domains, pre-define ontology concepts with embeddings.
New documents auto-link via cosine similarity without LLM extraction. The
approved entity types from a completed use case become the fixed ontology.

**Trigger**: Need to ingest many new documents into an established domain
without re-running the full extraction pipeline. The "incremental document
ingestion" use case.

**Effort**: Medium. Depends on a stable, validated domain schema.

**Note**: This is the natural evolution of schema templates (Priority 6).
A mature template with embedded descriptions IS a fixed ontology.

---

### Idea 8: Databricks Data Source + Selective Materialization

**Source**: Enterprise reality -- production data lives in Databricks (Unity
Catalog), not CSV files.

**Problem**: The entire pipeline currently assumes local CSV files. File
discovery uses `os.walk()`, schema analysis uses `csv.reader()`, validation
uses `pd.read_csv()`, import uses pandas DataFrames. In the target enterprise
environment, source data lives in Databricks tables governed by Unity Catalog.
CSVs are manual exports -- an extra step that breaks automation and introduces
staleness.

**Concept -- three parts**:

#### Part A: Data Source Abstraction

Replace CSV-specific code with a `DataSource` interface:

```python
class DataSource:
    def list_tables(self) -> list[TableInfo]
    def get_schema(self, table: str) -> list[ColumnInfo]
    def sample_rows(self, table: str, n: int) -> list[dict]
    def validate_uniqueness(self, table: str, column: str) -> ValidationResult
    def read_batches(self, table: str, batch_size: int) -> Iterator[list[dict]]
```

Three implementations:

- `CsvDataSource` -- wraps current behavior (os.walk, pandas). Keeps backward
  compatibility for local development and toy examples.

- `DatabricksSqlDataSource` -- uses `databricks-sql-connector` for data access
  and `databricks-sdk` (Unity Catalog) for schema discovery:

```python
from databricks import sql
from databricks.sdk import WorkspaceClient

class DatabricksSqlDataSource(DataSource):
    def __init__(self, http_path: str, catalog: str, schema: str):
        self.conn = sql.connect(
            server_hostname=os.environ["DATABRICKS_HOST"],
            http_path=http_path,
            access_token=os.environ["DATABRICKS_TOKEN"],
        )
        self.uc = WorkspaceClient()
        self.catalog = catalog
        self.schema = schema

    def list_tables(self):
        # Unity Catalog SDK -- deterministic, exact metadata
        return self.uc.tables.list(
            catalog_name=self.catalog,
            schema_name=self.schema,
        )

    def get_schema(self, table):
        # Unity Catalog -- column names, types, comments
        info = self.uc.tables.get(f"{self.catalog}.{self.schema}.{table}")
        return info.columns

    def sample_rows(self, table, n=5):
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT * FROM {self.catalog}.{self.schema}.{table} LIMIT {n}")
        return cursor.fetchall()

    def read_batches(self, table, batch_size=500):
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT * FROM {self.catalog}.{self.schema}.{table}")
        while batch := cursor.fetchmany(batch_size):
            yield [dict(row) for row in batch]
```

- `SqlDataSource` -- generic SQL via any Python DB API 2.0 connector. Works
  with PostgreSQL (`psycopg2`), MySQL (`mysql-connector-python`), SQL Server
  (`pyodbc`), Oracle (`oracledb`), SQLite (`sqlite3`), or any other database
  that provides a PEP 249 driver. Uses `information_schema` for discovery:

```python
class SqlDataSource(DataSource):
    def __init__(self, connection, schema: str = None):
        """
        Args:
            connection: Any DB API 2.0 connection object.
            schema: Database schema name (optional, for filtering).
        """
        self.conn = connection
        self.schema = schema

    def list_tables(self):
        cursor = self.conn.cursor()
        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
        """
        if self.schema:
            query += " AND table_schema = %s"
            cursor.execute(query, [self.schema])
        else:
            cursor.execute(query)
        return [row[0] for row in cursor.fetchall()]

    def get_schema(self, table):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, [table])
        return cursor.fetchall()

    def sample_rows(self, table, n=5):
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT * FROM {table} LIMIT {n}")
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def validate_uniqueness(self, table, column):
        cursor = self.conn.cursor()
        cursor.execute(f"""
            SELECT COUNT(*) AS total,
                   COUNT(DISTINCT {column}) AS distinct_count,
                   COUNT(*) - COUNT({column}) AS null_count
            FROM {table}
        """)
        row = cursor.fetchone()
        total, distinct, nulls = row
        return {
            "valid": distinct == total and nulls == 0,
            "total_rows": total,
            "distinct_values": distinct,
            "null_count": nulls,
            "duplicate_count": total - distinct,
        }

    def read_batches(self, table, batch_size=500):
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT * FROM {table}")
        columns = [desc[0] for desc in cursor.description]
        while batch := cursor.fetchmany(batch_size):
            yield [dict(zip(columns, row)) for row in batch]
```

Usage with any database:

```python
# PostgreSQL
import psycopg2
ds = SqlDataSource(psycopg2.connect("postgresql://host/db"), schema="public")

# MySQL
import mysql.connector
ds = SqlDataSource(mysql.connector.connect(host="h", database="db"))

# SQL Server
import pyodbc
ds = SqlDataSource(pyodbc.connect("DRIVER={ODBC Driver 18}; ..."))

# SQLite (local testing)
import sqlite3
ds = SqlDataSource(sqlite3.connect("local.db"))
```

No new dependencies for `SqlDataSource` itself -- the user provides the
connection object using whatever driver they already have. KG-Factory only
depends on the DB API 2.0 interface, which all Python database drivers
implement.

The Neo4j import logic (UNWIND → MERGE) stays identical -- it already works
with Python dicts, regardless of where they came from.

**Files affected**: `tools/file_tools.py` (discovery, metadata),
`tools/schema_tools.py` (context building, column validation),
`pipelines/domain_builder.py` (validation, import).

#### Part B: Selective Materialization

Not all Databricks data needs to be copied into Neo4j. **Materialize graph
topology (node IDs + relationships + match keys), leave detail properties
in Databricks, fetch on-demand at query time.**

What must be in Neo4j (graph structure):
- Node identities: IDs + labels (e.g., `Product(product_id)`)
- Relationships with foreign keys (e.g., `SUPPLIES(supplier→part)`)
- Properties used for graph traversal and filtering
- Text layer: chunks, embeddings, extracted entities (no SQL equivalent)

What stays in Databricks (fetched on-demand):
- Detail properties only read in final answers (description, price, email)
- Historical data, time series, audit logs
- Anything that changes frequently
- Large tables where full materialization is impractical

Schema template configuration:

```json
{
    "data_source": {
        "type": "databricks",
        "http_path": "/sql/1.0/warehouses/abc123",
        "catalog": "production",
        "schema": "supply_chain"
    },
    "nodes": {
        "Product": {
            "source_table": "products",
            "unique_key": "product_id",
            "materialize": ["product_id", "product_name"],
            "virtual": ["price", "description"]
        },
        "Supplier": {
            "source_table": "suppliers",
            "unique_key": "supplier_id",
            "materialize": ["supplier_id", "name"],
            "virtual": ["specialty", "city", "country", "website", "contact_email"]
        }
    }
}
```

The `materialize` vs `virtual` split is defined once in the template. The
pipeline materializes only the listed columns during construction. The query
server fetches virtual columns on-demand using the same template as lookup.

#### Part C: Query-Time Enrichment

After Neo4j graph traversal returns node IDs, the query server looks up the
schema template to construct the enrichment SQL mechanically -- no LLM needed:

```python
def enrich(label: str, node_ids: list[str], template: dict) -> list[dict]:
    """Fetch virtual properties from Databricks for matched nodes."""
    config = template["nodes"][label]
    table = f"{template['data_source']['catalog']}.{template['data_source']['schema']}.{config['source_table']}"
    key = config["unique_key"]
    columns = ", ".join([key] + config["virtual"])
    placeholders = ", ".join(["%s"] * len(node_ids))

    cursor = databricks_conn.cursor()
    cursor.execute(
        f"SELECT {columns} FROM {table} WHERE {key} IN ({placeholders})",
        node_ids,
    )
    return [dict(row) for row in cursor.fetchall()]
```

How it works end to end:

```
1. Domain agent asks: "Which suppliers are linked to dresser defects?"

2. Query server → Neo4j graph traversal:
   MATCH (chunk:Chunk)-[:FROM_CHUNK]->(d:Defect)
         -[:observed_in]->(p:Part)<-[:SUPPLIES]-(s:Supplier)
   RETURN s.supplier_id AS id, s.name AS name
   → Returns: [{id: "S-1078", name: "German Precision Fasteners"}, ...]

3. Query server looks up "Supplier" in schema template:
   → source_table: "suppliers"
   → unique_key: "supplier_id"
   → virtual: ["specialty", "city", "country", "website", "contact_email"]

4. Query server → Databricks SQL:
   SELECT supplier_id, specialty, city, country, website, contact_email
   FROM production.supply_chain.suppliers
   WHERE supplier_id IN ('S-1078', 'S-1085')

5. Merge Neo4j result + Databricks result → return to domain agent
```

No LLM in the enrichment path. The template defines the mapping, Neo4j
provides the IDs, the SQL query is constructed mechanically.

**Target architecture for domain agents**:

```
                    Domain Agent (Claude)
                   /            \
                  /              \
      KG Query Server        generates SQL
      (graph questions:       (tabular questions:
       traversal, vector       aggregation, time
       search, cross-layer)    series, filtering)
            |                     |
          Neo4j            databricks-sql-connector
      (topology +                 |
       text layer)         Databricks / Unity Catalog
                          (full data, source of truth)
```

Both paths use `databricks-sql-connector` for SQL access. The query server
uses it for enrichment; the domain agent uses it directly (or via Claude
generating SQL) for purely tabular questions. No intermediary LLM needed
between the agent and the data.

**Why this matters for industrialization**:
- Eliminates the CSV export step from the pipeline
- Source data stays fresh (no staleness from materialization)
- Reduces Neo4j storage (only topology, not full property copies)
- Enables incremental sync (detect changed rows in Databricks, update graph)
- Schema templates become the single config for graph structure, data source
  mapping, and materialization decisions
- Unity Catalog provides schema discovery, governance, and lineage for free
- `databricks-sql-connector` is Databricks' supported Python interface,
  DB API 2.0 compliant, with Arrow for efficient data transfer

**Trigger**: When building a KG for a domain where the source data lives in
Databricks (i.e., any real enterprise project beyond the furniture toy
example).

**Effort**: High. Three work packages:
- Part A (data source abstraction): Medium. New interface +
  DatabricksSqlDataSource + CsvDataSource refactor. ~300 lines.
- Part B (selective materialization): Medium. Materialization config in schema
  templates + import logic respects `materialize` list. ~200 lines.
- Part C (query-time enrichment): Medium. Enrichment function in query server
  + template lookup logic. ~200 lines.

**Depends on**: Priority 6 (schema templates) for materialization config.
Priority 9 (structured query results) for the enrichment merge point.

**New dependencies**:
- `databricks-sql-connector` (PyPI) -- SQL access to Databricks warehouses
- `databricks-sdk` (PyPI) -- Unity Catalog API for schema discovery

**Alternatives considered**:
- Databricks Genie API: Adds an unnecessary LLM hop. Genie translates
  natural language to SQL, but the pipeline already knows the exact SQL
  needed (from the schema template). Genie is useful as a human-facing
  exploration tool, not as a programmatic data access layer.
- APOC Data Virtualization (`apoc.dv`): Virtual nodes can't be traversed,
  no indexes, network round-trip per query. Useful for ad-hoc enrichment
  but not as primary architecture.
- Full virtualization (Stardog-style): No graph algorithms, no embeddings,
  no vector search on virtual data. Doesn't work for the text layer.
- Full materialization (current): Works but doubles storage, data goes stale,
  requires CSV export step. Acceptable for small/static datasets only.

---

## Review Schedule

Revisit this file after each milestone:

| Milestone | Expected Priorities to Review |
|-----------|-------------------------------|
| After Priority 4 (per-file context) | Confirm Phase A complete, plan Phase B |
| After Priority 5 (second use case) | Start Priority 6 (schema templates) |
| After first headless pipeline run | Evaluate query layer needs (Phase C) |
| After first multi-use-case merge | Evaluate scaling needs (Phase D) |
| After first domain agent deployed | Review all future ideas for relevance |
| When source data is in Databricks | Start Idea 8 (Databricks data source + selective materialization) |
| When graph exceeds 10,000 nodes | Check domain partitioning trigger |
| When template library has 3+ entries | Check template inheritance trigger |
