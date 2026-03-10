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

### ~~Priority 3: Embedding-Based Entity Resolution~~ — Attempted, Reverted

**Source**: Adamchic's Fixed Entity Architecture (FEA) research

**What was tried**: Replace rapidfuzz + Jaro-Winkler string matching in
`pipelines/entity_resolution.py` with cosine similarity between serialized
node embeddings (OpenAI `text-embedding-3-large`) for `CORRESPONDS_TO`
resolution.

**Why it was reverted**: Embedding similarity on full serialized node text
degraded resolution quality compared to Jaro-Winkler on the name field alone.
The root problem is property richness asymmetry: domain nodes (from CSV) have
many clean properties (product_id, price, description), while subject graph
entities (extracted by GPT-4o from reviews) often have only a name and a
short description. Embedding the full node text means the domain node's rich
property set pulls its vector away from the sparse entity vector, even when
the names are identical. String matching on the name key is immune to this
asymmetry. Reverted in commit `081a6c7` (Feb 25 2026).

**Current approach** (`pipelines/entity_resolution.py`):
1. `rapidfuzz.fuzz.ratio` to find the best `(entity_key, domain_key)` pair
   per label (e.g., `name` ↔ `product_name`)
2. `apoc.text.jaroWinklerDistance` in Cypher to match values at similarity
   ≥ `JAROWINKLER_AUTO_RESOLVE = 0.90`
3. `0.70–0.90` zone surfaced as human-review candidates via
   `proposed_resolution_candidates` in state

**Status**: Closed. Jaro-Winkler on the name key is the correct approach for
this data shape. Embedding-based resolution would only make sense if entity
nodes were consistently rich enough to produce stable, comparable embeddings —
which requires a different extraction strategy (e.g., extracting structured
properties rather than free-text descriptions per entity).

---

### Priority 3: Entity Property Name Constraints in Text Extraction

**Source**: Investigation of Reviewer node inconsistency (`name` vs `username`)
during cross-layer query testing (March 2026).

**Problem**: `build_entity_schema()` in `pipelines/text_builder.py` passes only
node labels (e.g., `["Product", "Part", "Reviewer"]`) to GPT-4o for extraction,
but never specifies what properties each entity type should have. GPT-4o invents
property names non-deterministically — the same Reviewer entity gets `name` in
one file and `username` in another. This causes:

1. Schema introspection (`_introspect_text_schema`) reports whichever property
   variant `LIMIT 1` happens to sample
2. Cypher queries filtering on a specific property miss nodes that used a
   different name for the same concept
3. Entity resolution key correlation (`rapidfuzz`) may pick the wrong key pair
   when the same semantic field has multiple names

**Root cause**: `approved_entity_types` stores only label names and descriptions,
not property specifications. `build_entity_schema()` builds the
`SimpleKGPipeline` schema from these labels alone — GPT-4o fills in properties
ad hoc during extraction.

**Proposed fix**:

1. Extend `approved_entity_types` to include an optional `properties` field per
   entity type (list of `{name, description}` dicts)
2. Update `build_entity_schema()` to pass property constraints to
   `SimpleKGPipeline` when available
3. Update `kg_ner_extraction` prompt to propose properties alongside entity types
4. Update `kg_fact_extraction` prompt similarly for relationship properties

```
Current approved_entity_types:
  {"Reviewer": {"description": "A person who wrote a review"}}

Target:
  {"Reviewer": {
    "description": "A person who wrote a review",
    "properties": [
      {"name": "username", "description": "The reviewer's handle or screen name"},
      {"name": "location", "description": "Where the reviewer is based"}
    ]
  }}
```

**Why**: Fixes non-determinism at the source. Without property constraints,
every text extraction run can produce a different property schema for the same
entity type, making Cypher generation unreliable and entity resolution brittle.
This is a prerequisite for industrial-mode reproducibility.

**Scope**: Changes to `agents/ner_extraction.py` (prompt + tool schema),
`agents/fact_extraction.py` (prompt + tool schema), `pipelines/text_builder.py`
(`build_entity_schema()`), and `mcp_server/server.py` (state shape). ~15 tests.

**Effort**: Medium. Requires prompt engineering for the NER/Fact agents to
propose good properties, and backward compatibility with existing states that
lack the `properties` field.

---

### Priority 4: Post-Build Graph Hygiene Filtering

**What**: Two Cypher passes run automatically at the end of `build_text_graph()`:

1. Remove orphan entity nodes — extracted by GPT-4o but connected to no
   relationships (pure noise with no query value)
2. Remove entities with meaningless names — pure numbers, single non-alphabetic
   characters, stopwords ("the", "n/a", "etc.", "various")

**Why**: Baseline text graph quality. There is no scenario where keeping orphan
nodes or garbage names is desirable. Running this by default means extraction
noise is cleaned before entity resolution, consolidation, and query all run on
the graph. Smallest possible effort, immediate impact.

**Scope**: New `pipelines/hygiene.py` with `remove_orphan_entities(driver)`,
`remove_meaningless_entities(driver)`, and `run_hygiene(driver, state)`.
Exposed as `scope="hygiene"` on `kg_build_graph` and run automatically as the
final step of `scope="unstructured"`. See Idea 13 for full implementation
detail.

**Effort**: Very low. ~60 lines, no new dependencies, ~8 unit tests.

---

### Priority 5: Intra-Graph Entity Description Consolidation

**What**: After `build_text_graph()`, find entity nodes merged from multiple
chunks, collect all descriptions GPT-4o assigned them across chunks, and make
one batch LLM call (20 entities per call) to produce a single consolidated
description per entity. Write the merged description back to `e.description`.

**Why**: `ON MATCH SET e.description = $new_description` silently overwrites
every prior description — only the last-seen chunk's version survives. For
entities that appear across many chunks (recurring part names, defect types,
product names), the surviving description is thin and often missing the most
diagnostically useful facts. Entity nodes are the cross-layer bridges via
`CORRESPONDS_TO` — a weak description degrades all cross-layer retrieval
through that node.

**Scope**: New `pipelines/consolidation.py` with `find_multi_chunk_entities()`,
`consolidate_batch()`, and `consolidate_entities()`. Exposed as
`scope="consolidate"` on `kg_build_graph`. See Idea 11 for full implementation
detail including the detection query and batch prompt design.

**Effort**: Low-Medium. ~150 lines, ~15 unit tests.

---

### Priority 6: Context-Aware Per-File Processing + Bin-Packing

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

### Priority 7: Second Real Use Case

Build a KG for a domain you actually care about. Validate Priorities 1-4 with
real data. The approved schema from this use case becomes the first entry in
the schema template library.

---

## Phase B: Build the Industrial Pipeline

The transition from exploration tool to production system. These items create
the "industrial mode" that runs without conversation.

### Priority 8: GraphRAG Community Summaries for Global Query Answering

**What**: After `build_text_graph()`, run the Louvain algorithm (via Neo4j GDS)
on the text layer to assign a `community_id` property to each `Chunk` and
`__Entity__` node. For each community, generate one LLM summary capturing the
thematic content of its member chunks. Store summaries as `CommunitySummary`
nodes connected to member chunks (`SUMMARIZES`), member entities (`REPRESENTS`),
and reachable domain nodes (`COVERS`).

**Why**: The current `kg_query` tool answers local questions — what a specific
chunk says about a topic. An entire class of CQs returns `not_answerable`:
global and thematic questions ("What are the main quality risks across all
products?", "Are our defects supplier-linked or design-linked?"). Community
summaries are pre-computed answers to this class. They require no additional
LLM call at query time — vector search hits the summary nodes directly.
One LLM call per community at build time unlocks an entirely new query
capability.

**Scope**: New `pipelines/community_builder.py`. New `community` retrieval
strategy in `query_builder.py`. Exposed as `scope="communities"` on
`kg_build_graph`. See Idea 10 for full implementation detail including the
furniture domain simulation, Cypher wiring, and cross-layer traversal path.

**Dependencies**: Neo4j GDS plugin (available in Community, Enterprise, and
Aura). No new Python dependencies.

**Effort**: Medium. ~300 lines, ~20 unit tests.

---

### Priority 9: Schema Template Library

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

**Trigger**: After completing Priority 6 (second real use case). Two completed
domains give you the first two templates and reveal which parts generalize.

**Scope**: Template format definition, export function from state to template,
import function from template to state, CLI or API entry point.

---

### Priority 10: Headless Pipeline Runner

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

**Trigger**: After Priority 8 (schema templates exist). The pipeline runner
consumes templates.

**Scope**: New `pipelines/headless_runner.py`. Orchestrates existing builders.
Adds validation step (CQ evaluation as quality gate). Returns structured
build report.

---

### Priority 11: Automated Quality Gate

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

**Trigger**: After Priority 9 (headless runner exists).

**Scope**: Small. Integration of existing `_run_cq_evaluation()` into the
headless pipeline with threshold configuration.

---

## Phase C: Harden the Query Layer

The query layer is the API contract for domain-specific agents. It must be
reliable, fast, and structured for agent consumption.

### Priority 12: Structured Query Results for Domain Agents

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

### Priority 13: Deterministic Strategy Selection

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

### Priority 14: Production Query Server

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

### Priority 15: Multi-Use-Case Merge Tool (kg_merge)

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

### Priority 16: Schema Template Inheritance

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

**Effort**: ~100 lines. Note: the embedding entity resolution this originally
depended on was attempted and reverted (see closed Priority 3). This idea can
be implemented independently using the embedding infrastructure already present
in `pipelines/text_builder.py`.

---

### Idea 2: SHACL Validation as Post-Build Quality Gate

**Source**: Target Architecture doc, Layer 2

**Concept**: Derive SHACL shapes from approved schema, validate Neo4j data
with pySHACL after build. Catches missing properties, orphan relationships,
cardinality violations.

**Trigger**: Data quality issues cause incorrect query results. Graph too
large for manual inspection. Also valuable as part of the automated quality
gate (Priority 10) for formal validation beyond CQ coverage.

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

**Depends on**: Priority 8 (schema templates) for materialization config.
Priority 11 (structured query results) for the enrichment merge point.

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

### Idea 9: LLM Call Caching for Structured Output Proposals

**Source**: knwler cache.py comparison, session analysis March 2026

**Concept**: Cache the result of `propose_entity_types()` and
`propose_fact_types()` to disk, keyed on a hash of the inputs (model, system
prompt, user message). A cache hit returns the stored JSON instantly with zero
API calls.

**Why it is NOT relevant for the current interactive workflow**:

The state persistence mechanism already serves this purpose. `propose_entity_types()`
only runs on the first call — when there is no conversation and no proposal in
state. The moment it runs, the result is stored in `state["proposed_entity_types"]`
and persisted to `current_state.json`. On the next session, state is reloaded
and the proposal is already there. The expensive structured output call never
fires again.

Iteration after the first call goes through the agent loop (small
conversational turns, ~1–2K tokens each), not through another structured
output call on the full file content. The 15K-token call happens exactly once
per project in normal usage.

**When it would become relevant**: The industrial mode (Priority 7) — a
headless pipeline running nightly in CI/CD on the same corpus. If the source
files haven't changed since the last run, re-running the pipeline should not
re-call Claude for proposals. The cache key (hash of file content + goal +
CQs) would detect this automatically.

**Trigger**: Priority 7 (headless pipeline runner) is implemented and the
pipeline runs repeatedly on stable corpora.

**Effort**: Low. `diskcache` library, ~20 lines wrapping `propose_entity_types`
and `propose_fact_types`, cache stored alongside `current_state.json`.

---

### Idea 10: GraphRAG Community Summaries for Global Query Answering

**Status**: Promoted to Phase B as Priority 7. Full detail retained here.

**Source**: Microsoft GraphRAG (2024–2025), session analysis March 2026

**Why this is distinct from Idea 3**: Idea 3 (Domain Partitioning) uses
community detection to *partition* the graph into domains for performance —
reducing context dilution when the schema exceeds ~50 node types. That is a
query-time optimization.

This idea uses community detection to *generate pre-computed summary nodes*
that answer a class of questions the current query layer cannot handle at all:
global, thematic, cross-document questions.

**The gap it fills**: The current `kg_query` tool answers local questions —
"what does chunk X say about topic Y?" Competency questions like "What are the
main quality themes across all products?" or "Are our defects supplier-linked
or design-linked?" consistently return `not_answerable` in CQ evaluation
because they require synthesizing across the entire corpus, not retrieving a
single chunk.

**Concept**:

After `build_text_graph()`, run Louvain on the text layer graph. Louvain
assigns a `community_id` integer property to each `Chunk` and `__Entity__`
node based on the density of `NEXT_CHUNK` (within-file chains) and
`FROM_CHUNK` (entity-to-chunk) edges. Cross-document bridges form where entity
nodes are shared across multiple review files.

For each community, collect all member chunk texts and send them in one LLM
call asking for a concise thematic summary. Store the result as a new node
type and wire it into the graph:

```cypher
// Step 1: GDS projection + Louvain
CALL gds.louvain.write('textGraphProjection', {writeProperty: 'community_id'})

// Step 2: Per community — create summary node
CREATE (cs:CommunitySummary {
    community_id: 0,
    label: "Drawer Hardware Defects",
    summary: "The Helsingborg Dresser is the primary quality failure...",
    severity: "critical",
    member_count: 14
})

// Step 3: Wire to member chunks
MATCH (chunk:Chunk {community_id: 0})
CREATE (cs)-[:SUMMARIZES]->(chunk)

// Step 4: Wire to member entities
MATCH (e:__Entity__ {community_id: 0})
CREATE (cs)-[:REPRESENTS]->(e)

// Step 5: Wire to domain nodes reachable via CORRESPONDS_TO
MATCH (cs)-[:SUMMARIZES]->(chunk)<-[:FROM_CHUNK]-(e)-[:CORRESPONDS_TO]->(domain)
MERGE (cs)-[:COVERS]->(domain)
```

**What this produces for the furniture domain** (simulated from data):

| Community | Label | Products Covered | Severity |
|---|---|---|---|
| A | Drawer Hardware Defects | Helsingborg Dresser, Norrköping Nightstand | critical |
| B | Assembly Process Failures | Gothenburg Table, Malmö Desk, Västerås Bookshelf | high |
| C | Material Durability Concerns | Uppsala Sofa, Jönköping Coffee Table | medium |
| D | Scandinavian Design Strengths | Stockholm Chair, Örebro Lamp, Linköping Bed | low |
| E | Cross-product Assembly Experience | multiple | medium |

**Queries that become answerable**:

- "What are our biggest product quality risks?" → vector search hits
  `CommunitySummary` nodes, returns structured thematic clusters ranked by
  severity
- "Are our defects supplier-linked or design-linked?" → Community A summary
  mentions "customer service acknowledged supplier issue"; Community B says
  "manufacturing precision failures, not design problems" — the LLM embedded
  this distinction during summarization
- "Which products are safe to promote right now?" → Community D (Strong
  Performers) answers directly

**Full traversal path unlocked**:

```
CommunitySummary -[:COVERS]-> Product -[:HAS_ASSEMBLY]-> Assembly
    -[:CONTAINS_PART]-> Part <-[:SUPPLIES]- Supplier
```

A thematic quality cluster connects all the way to specific suppliers in one
Cypher traversal. No LLM hop required.

**Important caveat**: The `:COVERS` → domain path depends on `CORRESPONDS_TO`
links existing. Sparse entity resolution means sparse community-to-domain
connections. Community summaries are most powerful after entity resolution is
healthy.

**Implementation**:

New `pipelines/community_builder.py`:
- `project_text_graph(driver)` — GDS in-memory projection of Chunk +
  __Entity__ nodes and their edges
- `run_louvain(driver)` — write `community_id` property back to nodes
- `summarize_community(community_id, chunks, state)` — single Claude API
  call per community, returns label + summary + severity
- `build_community_summaries(driver, state)` — orchestrates all steps,
  creates nodes and edges
- Exposed via new `scope="communities"` on `kg_build_graph` MCP tool

New query strategy `community` in `query_builder.py`:
- Vector search on `CommunitySummary.summary` text
- Falls back to current strategies for local questions

**Trigger**: CQ evaluation shows `not_answerable` results for thematic or
global questions. Also valuable as a standalone reporting feature — running
`kg_build_graph(scope="communities")` produces a structured quality report
from any text corpus without writing any Cypher.

**Dependencies**: Neo4j GDS plugin (for Louvain). GDS is available in Neo4j
Community, Enterprise, and Aura. No new Python dependencies.

**Effort**: Medium. ~300 lines across new pipeline + query strategy + MCP
wiring. ~20 unit tests.

---

### Idea 11: Intra-Graph Entity Description Consolidation

**Status**: Promoted to Phase A as Priority 4. Full detail retained here.

**Source**: knwler `consolidation.py` comparison, session analysis March 2026

**The problem**: `SimpleKGPipeline` processes review files chunk by chunk. GPT-4o
extracts the same real-world entity from multiple chunks, each time writing a
description based only on that chunk's local context. Neo4j merges them into
one node via `MERGE (e:__Entity__ {name: $name})`, but `ON MATCH SET
e.description = $new_description` means only the last-seen description
survives. All earlier descriptions are silently overwritten and lost.

**Concrete example** — "drawer rails" appears in 5 chunks across the
Helsingborg Dresser and Norrköping Nightstand reviews. Each chunk produces a
valid but partial description:

| Chunk | Description written by GPT-4o |
|---|---|
| 12 | "Metal sliding components used in dresser assembly" |
| 13 | "Hardware components with rough edges reported by customer" |
| 14 | "Defective rails causing drawer misalignment and assembly failure" |
| 15 | "Supplier-linked quality issue acknowledged by customer service" |
| 31 | "Drawer mechanism that sticks after initial installation" |

The surviving description (from chunk 31): *"Drawer mechanism that sticks
after initial installation."* The supplier issue, defective edges, and
assembly failure — the most diagnostically useful facts — are gone.

**Why this matters beyond description quality**: Entity nodes are the
cross-layer bridges. `CORRESPONDS_TO` links them to domain `Part` and
`Product` nodes, and the `kg_query` vector search uses their `description`
property as searchable text. A thin or wrong description on a heavily-linked
entity node degrades cross-layer retrieval for all queries that traverse it.

**Concept**:

After `build_text_graph()`, a consolidation pass:

1. Finds entity nodes that were merged from more than one chunk:

```cypher
MATCH (e:__Entity__)<-[:FROM_CHUNK]-(chunk:Chunk)
WITH e, collect(chunk.text) AS source_texts, count(chunk) AS chunk_count
WHERE chunk_count > 1
RETURN e.name, e.description, source_texts, chunk_count
ORDER BY chunk_count DESC
```

2. Batches them (20 per LLM call) and sends all known descriptions to Claude
   with a prompt asking for one consolidated 2–3 sentence description that
   captures all of them.

3. Writes the merged description back to `e.description`.

**What consolidation produces for "drawer rails"**:

> *"Drawer rail hardware used in dresser and nightstand assemblies. Multiple
> customers report defective rails with rough edges, uneven surfaces, and
> severe misalignment causing assembly failures of 3–7 hours. Customer service
> has acknowledged a supplier quality issue as the root cause."*

This description now carries the full diagnostic picture and surfaces
correctly for queries like "which parts have known supplier quality issues?"

**Detection — two options**:

Option A (no schema change): query `chunk_count` at consolidation time using
the Cypher above. Works on existing graphs.

Option B (schema change): add `source_chunk_count` property to entity nodes
during `build_text_graph()`, increment on `ON MATCH`. Consolidation filters
on `source_chunk_count > 1`. More efficient at scale.

Option A is the right starting point — it requires no changes to the build
pipeline.

**When it matters vs. when it doesn't**:

High impact on entities that appear frequently across multiple chunks — product
names, recurring part names (drawer rails, cushion foam), defect types,
supplier names. These are exactly the nodes that sit at the center of the
graph and act as cross-layer bridges.

Low impact on entities that appear in only one chunk — rare mentions, specific
measurements, one-off reviewer observations. These already have the correct
description.

In the furniture graph, the top 20–30 entities by `chunk_count` capture most
of the benefit. The rest can be left as-is.

**Implementation**:

New `pipelines/consolidation.py`:
- `find_multi_chunk_entities(driver)` — Cypher query returning entities with
  `chunk_count > 1` and their source chunk texts
- `consolidate_batch(entities, state)` — single Claude API call per batch of
  20, structured output mapping entity name → merged description
- `write_consolidated_descriptions(driver, results)` — Cypher `MATCH + SET`
  pass to update `e.description`
- `consolidate_entities(driver, state)` — orchestrates all steps, returns
  summary dict (entities_checked, entities_updated, batches_called)

Exposed via new `scope="consolidate"` on `kg_build_graph` MCP tool, or run
automatically as the final step of `scope="unstructured"` when the flag
`consolidate=True` is set in state.

**Cost**: One LLM call per 20 multi-chunk entities. For the furniture graph
(~148 entities, ~30 multi-chunk), that is 2 API calls. Negligible.

**Trigger**: `kg_query` cross-layer results are thin or incorrect for
well-known entities. CQ evaluation shows `partial` for questions about
entities that appear frequently in the source documents. Also useful as a
routine post-build step whenever `build_text_graph()` is run on a corpus with
overlapping entity mentions.

**Effort**: Low-Medium. ~150 lines in new pipeline + MCP wiring + ~15 unit
tests.

---

### Idea 12: Relation Confidence Score on Text Graph Edges

**Source**: knwler extraction comparison, session analysis March 2026

**The problem**: Text graph relationships extracted by GPT-4o from review prose
are treated identically regardless of how much evidence supports them. A
relationship mentioned in 4 separate reviews and one inferred from a vague
half-sentence sit in the graph with equal weight. Queries traversing them have
no way to distinguish solid extractions from noise.

**Scope**: Text graph relationships only. Domain graph relationships (from CSV:
`SUPPLIES`, `HAS_ASSEMBLY`, `CONTAINS_PART`) are deterministic and need no
confidence scoring.

**Approach — co-occurrence proxy (0 LLM calls)**:

After `build_text_graph()`, count how many chunks contain both the subject and
the object of each extracted relationship. Normalize by the total chunks
mentioning the subject:

```cypher
MATCH (a:__Entity__)<-[:FROM_CHUNK]-(chunk:Chunk)-[:FROM_CHUNK]->(b:__Entity__)
WITH a, b, count(chunk) AS support_chunks
MATCH (a)<-[:FROM_CHUNK]-(all_chunks:Chunk)
WITH a, b, support_chunks, count(all_chunks) AS subject_chunks
SET // on the relationship between a and b
    r.confidence = toFloat(support_chunks) / subject_chunks,
    r.support_chunks = support_chunks
```

This is a proxy, not true extraction confidence — co-occurrence confirms
proximity, not that GPT-4o's inferred predicate is correct. But it reliably
separates well-evidenced extractions (4+ chunks) from single-mention noise.

**What becomes possible**:

- Filtered traversal: `WHERE r.confidence > 0.3` removes noise from query paths
- Human review queue: relationships with `support_chunks = 1` surfaced for
  spot-checking
- Additional quality signal alongside the CQ coverage score (Priority 8)
- Ranked cross-layer paths: weight = `r.confidence × CORRESPONDS_TO.similarity`

**Important caveats**:

The co-occurrence proxy cannot validate the predicate — two entities in the
same chunk doesn't confirm the relationship GPT-4o inferred between them. True
confidence would require GPT-4o to output a score during extraction, which
means modifying `SimpleKGPipeline`'s extraction schema — a non-trivial change
to a library we don't control.

CQ evaluation (US014) already provides the primary quality signal. This adds
granularity at the individual edge level, not a replacement.

**Trigger**: CQ evaluation shows unexpectedly low coverage on a corpus that
should answer well, suggesting noisy extractions are polluting traversal
results. Or the text graph exceeds ~500 entity nodes where manual review of
extractions is no longer feasible.

**Effort**: Low. Post-build Cypher pass, no new dependencies, ~50 lines in
a new `pipelines/consolidation.py` section or standalone helper, ~8 unit tests.

---

### Idea 13: Post-Build Graph Hygiene Filtering

**Status**: Promoted to Phase A as Priority 3. Full detail retained here.

**Source**: knwler consolidation.py comparison, session analysis March 2026

**The problem**: GPT-4o extraction from review text produces noise alongside
valid entities. Two categories of noise accumulate silently in the text graph:

1. **Orphan nodes** — entity nodes with no relationships. GPT-4o extracted
   them from a chunk but they didn't participate in any inferred relationship.
   They consume index space and pollute schema introspection without
   contributing to any query path.

2. **Meaningless names** — entities whose names are pure numbers, single
   non-alphabetic characters, or stopwords: "1", "x", "the", "n/a", "etc.",
   "various". GPT-4o occasionally extracts these as entity mentions, especially
   from list-formatted review text.

Today neither category is removed. Both accumulate across every
`build_text_graph()` run.

**Concept**: Two Cypher queries run as a post-build pass after
`build_text_graph()` completes. No LLM calls, no new dependencies.

```cypher
-- 1. Remove orphan entity nodes (no relationships of any kind)
MATCH (e:__Entity__)
WHERE NOT (e)--()
DELETE e

-- 2. Remove meaningless names
MATCH (e:__Entity__)
WHERE e.name =~ '^[0-9]+$'           -- pure numbers
   OR e.name =~ '^[^a-zA-Z]$'        -- single non-alpha character
   OR toLower(trim(e.name)) IN ['the', 'a', 'an', 'n/a', 'etc', 'various',
                                 'other', 'some', 'many', 'several']
DETACH DELETE e
```

**Why distinct from Idea 2 (SHACL)**: SHACL validates schema conformance —
missing required properties, cardinality violations, type constraints against
a declared ontology. Hygiene filtering is heuristic pruning of extraction
noise using simple string and graph structure rules. No schema required,
no RDF, no pySHACL dependency.

**Implementation**: New `pipelines/hygiene.py`:
- `remove_orphan_entities(driver)` — executes orphan deletion, returns count
- `remove_meaningless_entities(driver, stopwords=None)` — executes name
  filtering with a configurable stopword list, returns count
- `run_hygiene(driver, state)` — orchestrates both passes, logs results

Exposed as `scope="hygiene"` on `kg_build_graph` MCP tool, or run
automatically as the final step of `scope="unstructured"`.

**Trigger**: Available immediately. Useful on any text graph build. Should
be a default post-build step rather than an opt-in — there is no scenario
where keeping orphan nodes or garbage names is desirable.

**Effort**: Very low. ~60 lines, no new dependencies, ~8 unit tests.

---

### Idea 14: Chunk Overlap in the Text Graph Builder

**Source**: knwler chunking.py comparison, session analysis March 2026

**The problem**: The current adaptive splitters (RegexTextSplitter,
MarkdownSectionSplitter, ParagraphSplitter) produce non-overlapping chunks.
When two adjacent chunks are processed independently by GPT-4o, any entity
or relationship that spans the boundary between them — where the end of chunk
N and the start of chunk N+1 together form a coherent statement — is invisible
to extraction. Each chunk only sees half the sentence.

**Concrete example from the furniture data**: A Helsingborg Dresser review
paragraph split at a section boundary:

```
Chunk N (end):   "...the drawer rails felt rough to the touch.
Chunk N+1 (start): Customer service told us it was a known issue..."
```

Processed independently, chunk N extracts a quality complaint about drawer
rails. Chunk N+1 extracts a customer service statement about an unspecified
issue. Neither chunk captures the causal link — that the customer service
statement *refers to* the drawer rail complaint. With overlap, both GPT-4o
calls see the boundary region and are more likely to extract the full
relationship.

**How knwler handles it**: Token-based overlap — each new chunk starts at
`end - overlap_tokens` of the previous chunk. Default overlap is configurable.
The overlapping tokens appear in both chunks, giving the model boundary context.

**Why lower priority for our corpus**: Our adaptive splitters are
structure-aware. MarkdownSectionSplitter splits at heading boundaries —
semantically coherent break points. RegexTextSplitter splits at `---`
dividers — also intentional boundaries. For well-structured markdown, boundary
context loss is less severe than for prose PDFs (knwler's primary target).
Overlap matters most for the ParagraphSplitter fallback, which splits
arbitrary prose without structural cues.

**Concept**: Add an `overlap_sentences` parameter (default: 1) to the
adaptive splitter selection in `make_kg_pipeline()`. Apply overlap only
when the ParagraphSplitter strategy is selected — the two structure-aware
strategies don't need it.

```python
# In pipelines/text_builder.py
if strategy == "paragraphs":
    splitter = ParagraphSplitter(
        chunk_size=config.chunk_size,
        overlap=state.get("text_splitting", {}).get("overlap_sentences", 1)
    )
```

User override via state:
```python
state["text_splitting"] = {"strategy": "paragraphs", "overlap_sentences": 2}
```

**Trigger**: CQ evaluation shows `partial` results for questions that should
be answerable from contiguous review text. Specifically: cross-sentence
relationships (cause → effect, complaint → resolution) are missing from the
text graph despite being clearly stated in the source. Or the corpus contains
long prose sections that fall through to ParagraphSplitter.

**Effort**: Low-Medium. Parameter threading through `make_kg_pipeline()`,
splitter configuration, state key documentation, ~10 unit tests. Depends on
whether `neo4j-graphrag`'s ParagraphSplitter exposes an overlap parameter
— if not, a custom subclass is needed (~30 additional lines).

---

## Review Schedule

Revisit this file after each milestone:

| Milestone | Expected Priorities to Review |
|-----------|-------------------------------|
| After Priority 5 (per-file context) | Confirm Phase A complete, plan Phase B |
| After Priority 6 (second use case) | Start Priority 8 (schema templates) |
| After first headless pipeline run | Evaluate query layer needs (Phase C) |
| After first multi-use-case merge | Evaluate scaling needs (Phase D) |
| After first domain agent deployed | Review all future ideas for relevance |
| When source data is in Databricks | Start Idea 8 (Databricks data source + selective materialization) |
| When graph exceeds 10,000 nodes | Check domain partitioning trigger |
| When template library has 3+ entries | Check template inheritance trigger |
