# US008: Domain Graph Builder Implementation

## Overview

The Domain Graph Builder is a deterministic pipeline that imports structured CSV data into Neo4j according to an approved construction plan. Unlike Stages 1-5 which use conversational LLM agents, Stage 6 is pure Python code that executes without human intervention.

## Architecture

### Three-Layer Validation Approach

Based on patterns from [neo4j-contrib/mcp-neo4j-data-modeling](https://github.com/neo4j-contrib/mcp-neo4j), the implementation uses three layers of validation:

1. **Layer 1 - Pre-Import CSV Validation**
   - Validates CSV files before any Neo4j operations
   - Checks: file exists, column exists, no nulls, no duplicates, no whitespace
   - Uses pandas for efficient validation
   - Fails fast with clear error messages

2. **Layer 2 - Database Constraints**
   - Creates NODE KEY constraints for all node labels
   - Enforces uniqueness + existence + automatic indexing
   - Pattern: `CREATE CONSTRAINT {label}_{col}_key FOR (n:{label}) REQUIRE (n.{col}) IS NODE KEY`

3. **Layer 3 - Idempotent MERGE Queries**
   - Uses `LOAD CSV + MERGE` for safe, repeatable imports
   - MERGE on unique column only (fast index lookup)
   - `trim()` handles whitespace in data
   - `SET n += row` copies all CSV columns as properties

### Import Process

```
[1/5] Validate CSV files
  → Check all files exist and pass uniqueness validation
  → Fail fast if any validation fails

[2/5] Create NODE KEY constraints
  → One constraint per node label
  → {label}_{unique_col}_key

[3/5] Import nodes
  → LOAD CSV + MERGE for each node type
  → Serial execution (one CSV at a time)

[4/5] Import relationships
  → LOAD CSV + MATCH + MERGE for each relationship type
  → Serial execution (critical to avoid deadlocks)
  → Orphan detection (CSV rows without matching nodes)

[5/5] Verify import
  → Count nodes by label
  → Count relationships by type
  → Count orphan nodes (no relationships)
```

## Files Created

### 1. `utils/neo4j_utils.py`

Neo4j connection utilities:

- `get_neo4j_driver()` - Create driver from env vars or parameters
- `test_connection()` - Verify connectivity and get server info
- `close_driver()` - Safe cleanup

Environment variables:
- `NEO4J_URI` - Connection URI (bolt://, neo4j://, or neo4j+s://)
- `NEO4J_USER` - Username
- `NEO4J_PASSWORD` - Password

### 2. `pipelines/domain_builder.py`

Main implementation:

- `validate_csv_uniqueness()` - Layer 1 validation
- `create_unique_constraint()` - Layer 2 constraints
- `import_nodes()` - Node import via LOAD CSV + MERGE
- `import_relationships()` - Relationship import via LOAD CSV + MATCH + MERGE
- `verify_import()` - Post-import verification
- `build_domain_graph()` - Main entry point orchestrating all steps

### 3. `tests/test_06_domain_builder.py`

Interactive test script:

- Loads state from Stage 3 (approved_construction_plan required)
- Connects to Neo4j and tests connectivity
- Optional: Clear existing graph
- Runs domain builder and displays results
- Shows verification statistics

### 4. `tests/unit/test_domain_builder.py`

Unit tests for CSV validation:

- ✅ Valid unique column
- ✅ Duplicate values detection
- ✅ Null values detection
- ✅ Whitespace detection
- ✅ Missing column detection
- ✅ File not found handling

All 6 tests passing.

## Usage

### Prerequisites

1. **Neo4j Instance Running**
   - Cloud (Aura) or local
   - Accessible at NEO4J_URI

2. **Environment Variables Set**
   ```bash
   NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=yourpassword
   NEO4J_IMPORT_DIR=./data  # For file paths
   ```

3. **Stage 3 Completed**
   - State file must contain `approved_construction_plan`

### Run the Builder

```bash
# Interactive test (with prompts)
python -m tests.test_06_domain_builder

# In code (programmatic)
from pipelines import build_domain_graph
from utils import get_neo4j_driver, close_driver
from core import load_state

state = load_state("state.json")
driver = get_neo4j_driver()
results = build_domain_graph(state, driver)
close_driver(driver)
```

## Construction Plan Format

The builder expects `state["approved_construction_plan"]` with this structure:

```python
{
    "Product": {
        "construction_type": "node",
        "source_file": "products.csv",
        "label": "Product",
        "unique_column_name": "product_id",
        "properties": ["product_name", "price", ...]
    },
    "SUPPLIED_BY": {
        "construction_type": "relationship",
        "source_file": "part_supplier_mapping.csv",
        "relationship_type": "SUPPLIED_BY",
        "from_node_label": "Part",
        "from_node_column": "part_id",
        "to_node_label": "Supplier",
        "to_node_column": "supplier_id",
        "properties": [...]  # Optional
    },
    # ... more nodes and relationships
}
```

## Results Format

The builder returns:

```python
{
    "nodes": [
        {"label": "Product", "count": 50, "errors": []},
        {"label": "Supplier", "count": 20, "errors": []}
    ],
    "relationships": [
        {"type": "SUPPLIED_BY", "count": 30, "orphans": 0, "errors": []}
    ],
    "errors": [],  # Any critical errors
    "verification": {
        "node_counts": {"Product": 50, "Supplier": 20},
        "relationship_counts": {"SUPPLIED_BY": 30},
        "orphan_nodes": 0,
        "total_nodes": 70,
        "total_relationships": 30
    }
}
```

## Error Handling

### Pre-Flight Failures (Fail Fast)

- **Missing construction plan**: ValueError before any Neo4j operations
- **CSV validation failure**: ValueError with specific issue (duplicates, nulls, etc.)
- **File not found**: FileNotFoundError with path
- **Neo4j connection failure**: ServiceUnavailable with connection details

### Import Failures (Continue with Errors)

- **Constraint creation failure**: Logged, added to errors, but continues
- **Node import failure**: Logged, added to errors, count = 0
- **Relationship import failure**: Logged, added to errors
- **Orphan relationships**: Logged as warnings (MATCH found no nodes)

All errors collected in `results["errors"]` for post-execution review.

## Key Design Decisions

### Why NODE KEY (not UNIQUE)?

NODE KEY provides:
1. Uniqueness enforcement
2. Existence enforcement (no nulls)
3. Automatic range index
4. Single constraint covers all three

UNIQUE constraint only provides uniqueness.

### Why Serial Relationship Import?

Parallel relationship imports can cause Neo4j deadlocks when multiple transactions try to lock the same nodes. Serial execution is slower but reliable.

### Why Pandas for Validation?

- Fast CSV parsing and validation
- Rich data manipulation (null detection, duplicate detection)
- Industry standard, well-tested
- Small dependency (~10MB)

Alternative considered: pure Python csv module (no duplicate detection without manual tracking).

### Why MERGE (not CREATE)?

MERGE is idempotent:
- Can re-run the builder safely
- Updates existing nodes if already present
- No "node already exists" errors

CREATE would fail on second run.

## Testing

### Unit Tests

```bash
pytest tests/unit/test_domain_builder.py -v
```

Tests CSV validation logic in isolation.

### Integration Test

```bash
python -m tests.test_06_domain_builder
```

Tests end-to-end CSV → Neo4j import with real database.

### Manual Verification (Neo4j Browser)

```cypher
// Check node counts
MATCH (n) RETURN labels(n) as label, count(*) as count

// Check relationship counts
MATCH ()-[r]->() RETURN type(r) as type, count(*) as count

// Verify constraints
SHOW CONSTRAINTS

// Sample data
MATCH (n) RETURN n LIMIT 25
```

## Future Enhancements (Out of Scope)

These are NOT implemented in US008:

1. **Text Processing** (US009)
   - Subject Graph (entity extraction from markdown)
   - Lexical Graph (chunks + embeddings)
   - Entity resolution (Subject ↔ Domain linking)

2. **Large CSV Support**
   - PERIODIC COMMIT for 100K+ rows
   - Batch processing for memory efficiency

3. **Composite Keys**
   - Currently only single-column uniqueness
   - Would need multi-column NODE KEY support

4. **Relationship Properties Validation**
   - Construction plan supports it
   - Not validated in Layer 1 (only existence)

5. **MCP Integration**
   - `kg_build_graph` tool
   - Progress reporting
   - Interactive rebuild option

## Dependencies Added

```
pandas>=2.0.0  # CSV validation
neo4j>=5.0.0   # Already present
```

## Success Criteria

✅ All criteria met:

1. ✅ `utils/neo4j_utils.py` provides working Neo4j driver management
2. ✅ `pipelines/domain_builder.py` implements three-layer validation
3. ✅ `build_domain_graph(state, driver)` successfully imports CSV data
4. ✅ NODE KEY constraints created for all node labels
5. ✅ MERGE queries are idempotent (safe to re-run)
6. ✅ Verification queries confirm correct counts
7. ✅ Test script runs end-to-end without errors
8. ✅ Unit tests verify CSV validation logic (6/6 passing)

## Example Output

```
======================================================================
DOMAIN GRAPH BUILDER - Stage 6 Test
======================================================================

[Config] Loading state from: state_after_schema_proposal.json
[Config] Found construction plan with 6 items
  - Node types: 4
  - Relationship types: 2

[Pre-flight] Testing Neo4j connection...
  Connected to Neo4j 5.23.0
  Edition: enterprise
  Database: neo4j

[Optional] Clear existing graph before import?
  Type 'yes' to clear, or press Enter to skip: yes
  Clearing graph...
  Graph cleared.

======================================================================
BUILDING DOMAIN GRAPH
======================================================================

Data directory: C:\Users\...\data
Construction plan items: 6

[1/5] Validating CSV files...
  Validating products.csv... [OK]
  Validating parts.csv... [OK]
  Validating suppliers.csv... [OK]
  Validating assemblies.csv... [OK]
  Validating part_supplier_mapping.csv... [OK]

[2/5] Creating NODE KEY constraints...
  Creating constraint for Product.product_id... [OK]
  Creating constraint for Part.part_id... [OK]
  Creating constraint for Supplier.supplier_id... [OK]
  Creating constraint for Assembly.assembly_id... [OK]

[3/5] Importing nodes from CSV files...
  Importing Product nodes... [OK] - 5 nodes
  Importing Part nodes... [OK] - 36 nodes
  Importing Supplier nodes... [OK] - 18 nodes
  Importing Assembly nodes... [OK] - 16 nodes

[4/5] Importing relationships from CSV files...
  Importing SUPPLIED_BY relationships... [OK] - 88 relationships
  Importing HAS_PART relationships... [OK] - 23 relationships

[5/5] Verifying graph construction...
  Total nodes: 75
  Total relationships: 111
  Orphan nodes: 0

======================================================================
RESULTS
======================================================================

Nodes Imported:
  [OK] Product: 5 nodes
  [OK] Part: 36 nodes
  [OK] Supplier: 18 nodes
  [OK] Assembly: 16 nodes

Relationships Imported:
  [OK] SUPPLIED_BY: 88 relationships
  [OK] HAS_PART: 23 relationships

Verification:
  Total nodes: 75
  Total relationships: 111
  Orphan nodes (no relationships): 0

  Node counts by label:
    Product: 5
    Part: 36
    Supplier: 18
    Assembly: 16

  Relationship counts by type:
    SUPPLIED_BY: 88
    HAS_PART: 23

======================================================================
SUCCESS - Domain Graph Built!
======================================================================

You can now explore the graph in Neo4j Browser:
  - Check node counts: MATCH (n) RETURN labels(n), count(*)
  - Check relationships: MATCH ()-[r]->() RETURN type(r), count(*)
  - View sample: MATCH (n) RETURN n LIMIT 25
```
