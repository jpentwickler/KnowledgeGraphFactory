# Assessment: Neo4j Data Modeling MCP Server

**Repository**: [neo4j-contrib/mcp-neo4j](https://github.com/neo4j-contrib/mcp-neo4j)
**Server**: `mcp-neo4j-data-modeling`
**Assessment Date**: 2026-02-11
**Assessed For**: KG-Factory Domain Graph Builder (Component 1, Stage 6)

---

## Executive Summary

**Recommendation**: ✅ **Use selectively for code generation patterns**

The `mcp-neo4j-data-modeling` MCP server provides excellent **reference patterns** for:
1. Constraint creation queries
2. MERGE-based import queries
3. Data model validation

However, we should **NOT use it as a dependency** because:
- Adds complexity (another MCP server to configure)
- Solves a different problem (interactive data modeling, not pipeline execution)
- Our needs are simpler (direct CSV import from construction plan)

**Best approach**: Study their code patterns and implement simplified versions in our Domain Graph Builder.

---

## What the MCP Server Does

### Primary Purpose
Interactive **data modeling assistant** for Neo4j schemas - helps users design node/relationship schemas through conversation with Claude.

### Key Features
1. **Schema Design Tools**
   - Validate node/relationship definitions
   - Generate Mermaid diagrams for visualization
   - Import/export from Arrows.app (visual graph editor)

2. **Code Generation Tools**
   - Generate constraint creation queries
   - Generate MERGE-based ingest queries
   - Export to Pydantic models, OWL, etc.

3. **Example Models**
   - 7 pre-built domain models (healthcare, supply chain, fraud, etc.)
   - Educational templates

---

## Relevant Code Patterns for KG-Factory

### 1. ✅ **Constraint Creation** (Highly Relevant)

**Their approach**:
```python
# From data_model.py line 336
def get_cypher_constraint_query(self) -> str:
    """Create a NODE KEY constraint on the node."""
    return f"CREATE CONSTRAINT {self.label}_constraint IF NOT EXISTS FOR (n:{self.label}) REQUIRE (n.{self.key_property.name}) IS NODE KEY"
```

**Why NODE KEY?**
- `NODE KEY` enforces **both uniqueness AND existence** (not null)
- Creates a **range index** automatically (faster MERGE)
- Stronger guarantee than `UNIQUE` alone

**For KG-Factory**:
```python
def create_node_constraint(driver, label: str, unique_col: str):
    """Create NODE KEY constraint for uniqueness + existence."""
    query = f"""
    CREATE CONSTRAINT {label.lower()}_{unique_col}_key IF NOT EXISTS
    FOR (n:{label})
    REQUIRE (n.{unique_col}) IS NODE KEY
    """
    driver.execute_query(query)
```

**✅ Takeaway**: Use `NODE KEY` instead of `UNIQUE` for better guarantees.

---

### 2. ✅ **MERGE-Based Node Import** (Highly Relevant)

**Their approach**:
```python
# From data_model.py line 325
def get_cypher_ingest_query_for_many_records(self) -> str:
    """Generate bulk import query using UNWIND."""
    formatted_props = ", ".join(
        [f"{p.name}: record.{p.name}" for p in self.properties]
    )
    return f"""
    UNWIND $records as record
    MERGE (n:{self.label} {{{self.key_property.name}: record.{self.key_property.name}}})
    SET n += {{{formatted_props}}}
    """
```

**Key insights**:
1. Uses `UNWIND` for bulk processing (passes data as parameter, not LOAD CSV)
2. `MERGE` on key property only (uniqueness check)
3. `SET n += {...}` updates all properties

**Why not LOAD CSV?**
- Their approach: data comes from application memory (`$records` parameter)
- Our approach: data comes from CSV files on disk (LOAD CSV more efficient)

**For KG-Factory**:
```python
# We'll use LOAD CSV (better for file-based import)
def import_nodes_from_csv(driver, spec: dict):
    query = f"""
    LOAD CSV WITH HEADERS FROM 'file:///{spec["source_file"]}' AS row
    MERGE (n:{spec["label"]} {{{spec["unique_column_name"]}: trim(row.{spec["unique_column_name"]})}})
    SET n += row
    """
    driver.execute_query(query)
```

**✅ Takeaway**: MERGE on key + SET for properties is the right pattern.

---

### 3. ✅ **Ingest Process Guidelines** (Highly Relevant)

**Their documentation** (`static.py`):
```python
DATA_INGEST_PROCESS = """
Follow these steps when ingesting data into Neo4j.
1. Create constraints before loading any data.
2. Load all nodes before relationships.
3. Then load relationships serially to avoid deadlocks.
"""
```

**Why this order matters**:

**Step 1: Constraints First**
- Creates indexes for fast lookups during MERGE
- Enforces data integrity from the start

**Step 2: All Nodes Before Relationships**
- Relationships require both endpoints to exist
- MATCH fails silently if node doesn't exist → orphan relationship data

**Step 3: Relationships Serially**
- **Deadlock risk**: If two relationships reference the same nodes in different order, Neo4j can deadlock
- Serial loading prevents concurrent writes to same nodes

**For KG-Factory**:
```python
def build_domain_graph(state: dict, driver):
    plan = state["approved_construction_plan"]

    # Step 1: Create all constraints
    for name, spec in plan.items():
        if spec["construction_type"] == "node":
            create_node_constraint(driver, spec["label"], spec["unique_column_name"])

    # Step 2: Import all nodes
    for name, spec in plan.items():
        if spec["construction_type"] == "node":
            import_nodes(driver, spec)

    # Step 3: Import relationships (one at a time)
    for name, spec in plan.items():
        if spec["construction_type"] == "relationship":
            import_relationships(driver, spec)  # No parallelization
```

**✅ Takeaway**: Follow the 3-step process religiously.

---

### 4. ⚠️ **Relationship Import** (Less Relevant)

**Their approach**:
```python
# From data_model.py line 608
def get_cypher_relationship_ingest_query(self) -> str:
    return f"""
    UNWIND $records as record
    MATCH (start:{self.start_node_label} {{{self.start_key}: record.{self.start_key}}})
    MATCH (end:{self.end_node_label} {{{self.end_key}: record.{self.end_key}}})
    MERGE (start)-[:{self.type}]->(end)
    """
```

**Issues for our use case**:
1. Assumes data in memory (`$records` parameter)
2. Doesn't handle relationship properties beyond key
3. No error handling for missing nodes

**For KG-Factory** (better):
```python
def import_relationships_from_csv(driver, spec: dict):
    query = f"""
    LOAD CSV WITH HEADERS FROM 'file:///{spec["source_file"]}' AS row
    MATCH (from:{spec["from_node_label"]} {{{spec["from_node_column"]}: trim(row.{spec["from_node_column"]})}})
    MATCH (to:{spec["to_node_label"]} {{{spec["to_node_column"]}: trim(row.{spec["to_node_column"]})}})
    MERGE (from)-[r:{spec["relationship_type"]}]->(to)
    """
    result = driver.execute_query(query)
    # TODO: Check if result count < CSV row count (indicates orphan references)
```

**⚠️ Takeaway**: Their pattern is a starting point, but we need CSV-specific logic.

---

## What We SHOULD NOT Use

### ❌ 1. The MCP Server as a Dependency

**Why not**:
- **Different use case**: They're building an interactive modeling assistant, we're building a pipeline executor
- **Overhead**: Requires running another MCP server, configuration complexity
- **Not needed**: We already have the construction plan from Stage 3

**What we need instead**: Direct Python code that reads our construction plan and executes imports.

---

### ❌ 2. Their Data Model Classes

**Their approach**: Pydantic models for `Node`, `Relationship`, `DataModel`

```python
class Node(BaseModel):
    label: str
    key_property: Property
    properties: list[Property]
    # ... lots of validation, conversion methods
```

**Why not**:
- **Too heavyweight**: We just need simple dict parsing
- **Different schema**: Our construction plan is simpler (no Property objects, just column names)
- **Conversion overhead**: Would need to translate our format → their format → back

**What we need instead**: Simple functions that read our existing construction plan dict.

---

### ❌ 3. Their Validation Tools

**Their tools**: `validate_node`, `validate_relationship`, `validate_data_model`

**Why not**:
- **Already validated**: Our Schema Critic (Stage 3) validated the construction plan
- **Different validation**: They validate schema structure, we need CSV content validation

**What we need instead**: CSV-specific validation (duplicates, nulls, encoding).

---

## Code We SHOULD Borrow

### ✅ Constraint Query Pattern

```python
# From their code
f"CREATE CONSTRAINT {label}_constraint IF NOT EXISTS FOR (n:{label}) REQUIRE (n.{key_property}) IS NODE KEY"

# Our adaptation
def create_unique_constraint(driver, label: str, unique_col: str):
    constraint_name = f"{label.lower()}_{unique_col}_key"
    query = f"""
    CREATE CONSTRAINT {constraint_name} IF NOT EXISTS
    FOR (n:{label})
    REQUIRE (n.{unique_col}) IS NODE KEY
    """
    driver.execute_query(query)
```

---

### ✅ Three-Step Import Process

```python
# From their docs
# 1. Constraints
# 2. Nodes
# 3. Relationships (serial)

# Our implementation
def build_domain_graph(state: dict, driver):
    plan = state["approved_construction_plan"]

    # Layer 1: Pre-import validation (our addition)
    for name, spec in plan.items():
        if spec["construction_type"] == "node":
            validate_csv(spec["source_file"], spec["unique_column_name"])

    # Layer 2: Constraints (from their pattern)
    for name, spec in plan.items():
        if spec["construction_type"] == "node":
            create_unique_constraint(driver, spec["label"], spec["unique_column_name"])

    # Layer 3: Nodes (from their pattern)
    for name, spec in plan.items():
        if spec["construction_type"] == "node":
            import_nodes(driver, spec)

    # Layer 4: Relationships (from their pattern)
    for name, spec in plan.items():
        if spec["construction_type"] == "relationship":
            import_relationships(driver, spec)
```

---

### ✅ MERGE + SET Pattern

```python
# From their code
f"MERGE (n:{label} {{{key}: record.{key}}})\nSET n += {{...}}"

# Our adaptation (with LOAD CSV)
query = f"""
LOAD CSV WITH HEADERS FROM 'file:///{source_file}' AS row
MERGE (n:{label} {{{unique_col}: trim(row.{unique_col})}})
SET n += row
"""
```

---

## Final Recommendations

### ✅ **DO**:
1. **Use their constraint pattern**: `NODE KEY` instead of `UNIQUE`
2. **Follow their import process**: Constraints → Nodes → Relationships (serial)
3. **Use MERGE + SET**: Their query structure is solid
4. **Reference their examples**: Study their 7 domain models for best practices

### ❌ **DON'T**:
1. **Add MCP server as dependency**: Not needed, adds complexity
2. **Use their Pydantic models**: Our construction plan is simpler
3. **Use their validation tools**: We have different validation needs (CSV content, not schema structure)
4. **Use UNWIND with $records**: LOAD CSV is more efficient for our file-based workflow

---

## Implementation Plan for KG-Factory

```python
# pipelines/domain_builder.py

def build_domain_graph(state: dict, driver):
    """Build domain graph using patterns from mcp-neo4j-data-modeling."""

    plan = state["approved_construction_plan"]

    # Pattern 1: Three-step process (from their docs)
    print("[1/4] Validating CSV files...")
    validate_all_csvs(plan)

    print("[2/4] Creating constraints...")
    create_all_constraints(driver, plan)  # NODE KEY pattern

    print("[3/4] Importing nodes...")
    import_all_nodes(driver, plan)  # MERGE + SET pattern

    print("[4/4] Importing relationships...")
    import_all_relationships(driver, plan)  # Serial, not parallel

    return verify_import(driver)


def create_all_constraints(driver, plan: dict):
    """Use NODE KEY pattern from mcp-neo4j-data-modeling."""
    for name, spec in plan.items():
        if spec["construction_type"] == "node":
            constraint_name = f"{spec['label'].lower()}_{spec['unique_column_name']}_key"
            query = f"""
            CREATE CONSTRAINT {constraint_name} IF NOT EXISTS
            FOR (n:{spec['label']})
            REQUIRE (n.{spec['unique_column_name']}) IS NODE KEY
            """
            driver.execute_query(query)
```

---

## References

- **Main Repository**: [neo4j-contrib/mcp-neo4j](https://github.com/neo4j-contrib/mcp-neo4j)
- **Blog Post**: [Explore the Neo4j Data Modeling MCP Server](https://medium.com/neo4j/explore-the-neo4j-data-modeling-mcp-server-56a6fdb1d2f7)
- **Developer Guide**: [Model Context Protocol (MCP) Integrations](https://neo4j.com/developer/genai-ecosystem/model-context-protocol-mcp/)
- **PyPI Package**: [mcp-neo4j-data-modeling](https://pypi.org/project/mcp-neo4j-data-modeling/)

---

## Conclusion

The `mcp-neo4j-data-modeling` MCP server is an **excellent reference** but not a good **dependency** for KG-Factory.

**Value**:
- Validated best practices for Neo4j import
- Production-tested constraint patterns
- Clear documentation of import process

**Non-value**:
- Interactive modeling (we have Schema Proposal Agent)
- Pydantic models (too complex for our needs)
- UNWIND-based import (we use LOAD CSV)

**Action**: Borrow their patterns, implement our own simplified version optimized for CSV import pipelines.
