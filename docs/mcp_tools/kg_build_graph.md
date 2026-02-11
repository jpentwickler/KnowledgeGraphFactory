# MCP Tool: `kg_build_graph`

## Overview

The `kg_build_graph` tool executes the graph construction pipeline, importing structured CSV data into Neo4j according to the approved construction plan from Stage 3.

**Status**: ✅ Implemented (US008 + MCP Integration)

---

## Function Signature

```python
@mcp.tool
def kg_build_graph(message: str = "build") -> dict
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message` | str | No | User message (e.g., "build the graph", "start construction"). Defaults to "build". |

### Returns

Dictionary with:
- `agent_response` (str): Human-readable build results or error message
- `status` (dict): Structured status information

---

## What It Does

The tool executes a **5-step build process**:

1. **CSV Validation** - Checks for duplicates, nulls, whitespace in unique columns
2. **Constraint Creation** - Creates NODE KEY constraints for all node labels
3. **Node Import** - Imports nodes using LOAD CSV + MERGE (idempotent)
4. **Relationship Import** - Imports relationships using LOAD CSV + MATCH + MERGE (serial)
5. **Verification** - Counts nodes/relationships, detects orphans

---

## Prerequisites

### 1. Completed Stages

The tool requires these prior stages to be completed:

- ✅ **Stage 1**: User Intent (approved_user_goal)
- ✅ **Stage 2**: File Suggestion (approved_files)
- ✅ **Stage 3**: Schema Proposal (approved_construction_plan) **← REQUIRED**

### 2. Neo4j Instance

- Neo4j database running and accessible
- Credentials configured in environment variables

### 3. Environment Variables

Set in `.mcp.json`:

```json
{
  "mcpServers": {
    "kg-factory": {
      "env": {
        "NEO4J_URI": "neo4j+s://xxxxx.databases.neo4j.io",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "yourpassword",
        "KG_DATA_DIR": "${workspaceFolder}/data"
      }
    }
  }
}
```

---

## Usage Examples

### Example 1: Successful Build

**User**: "Build the graph"

**Claude Code** (calls tool):
```python
kg_build_graph(message="Build the graph")
```

**Response**:
```
Domain Graph built successfully!

Connected to Neo4j 5.23.0 (database: neo4j)

Nodes Imported:
  [OK] Product: 5 nodes
  [OK] Supplier: 18 nodes
  [OK] Part: 36 nodes
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
    Supplier: 18
    Part: 36
    Assembly: 16

  Relationship counts by type:
    SUPPLIED_BY: 88
    HAS_PART: 23

You can explore the graph in Neo4j Browser at: https://xxxxx.databases.neo4j.io:7474

Useful queries:
  // View all nodes
  MATCH (n) RETURN n LIMIT 25

  // Check schema
  CALL db.schema.visualization()

  // Count all entities
  MATCH (n) RETURN labels(n) as label, count(*) as count
```

**Status**:
```json
{
  "success": true,
  "neo4j_version": "5.23.0",
  "database": "neo4j",
  "verification": {
    "total_nodes": 75,
    "total_relationships": 111,
    "orphan_nodes": 0,
    "node_counts": {
      "Product": 5,
      "Supplier": 18,
      "Part": 36,
      "Assembly": 16
    },
    "relationship_counts": {
      "SUPPLIED_BY": 88,
      "HAS_PART": 23
    }
  },
  "node_import": [...],
  "relationship_import": [...]
}
```

---

### Example 2: Missing Prerequisites

**User**: "Build the graph"

**Claude Code** (calls tool):
```python
kg_build_graph(message="Build the graph")
```

**Response**:
```
Cannot build graph: No approved construction plan found.

Please complete Stage 3 (Schema Proposal) first:
1. Use kg_schema_proposal to design the schema
2. Use kg_critic with scope='structured' to validate
3. Approve the construction plan
```

**Status**:
```json
{
  "success": false,
  "error": "missing_construction_plan"
}
```

---

### Example 3: Neo4j Connection Failure

**Response**:
```
Failed to connect to Neo4j: [Errno 111] Connection refused

Please check:
1. Neo4j instance is running
2. NEO4J_URI is correct
3. Credentials are valid
4. Network connectivity
```

**Status**:
```json
{
  "success": false,
  "error": "neo4j_connection_failed",
  "details": "[Errno 111] Connection refused"
}
```

---

### Example 4: CSV Validation Failure

**Response**:
```
Graph build completed with errors:

  - CSV validation failed for Product: Found 2 duplicate values in 'product_id' column
  - CSV validation failed for Supplier: Found 1 null/empty values in 'supplier_id' column

Please review the errors and fix any data issues before retrying.
```

**Status**:
```json
{
  "success": false,
  "errors": [
    "CSV validation failed for Product: Found 2 duplicate values in 'product_id' column",
    "CSV validation failed for Supplier: Found 1 null/empty values in 'supplier_id' column"
  ],
  "verification": {}
}
```

---

## Error Handling

The tool handles errors gracefully and returns informative messages:

| Error Type | Status Error Key | User Action |
|------------|------------------|-------------|
| No construction plan | `missing_construction_plan` | Complete Stage 3 |
| Missing Neo4j credentials | `missing_neo4j_credentials` | Set env vars in .mcp.json |
| Neo4j connection failed | `neo4j_connection_failed` | Check Neo4j is running |
| CSV validation failed | (errors list) | Fix CSV data issues |
| Build failed | `build_failed` | Check error details |

---

## Behind the Scenes

When the tool is called, it:

1. **Loads state** from `state/current_state.json`
2. **Validates prerequisites** (construction plan exists)
3. **Checks environment** (Neo4j credentials set)
4. **Imports modules**:
   - `pipelines.build_domain_graph`
   - `utils.get_neo4j_driver`
   - `utils.test_connection`
   - `utils.close_driver`
5. **Connects to Neo4j** and tests connection
6. **Runs domain builder** (`build_domain_graph(state, driver)`)
7. **Formats results** for display
8. **Closes connection** (even on error)
9. **Returns response** to Claude Code

---

## Current Limitations

**Currently builds**:
- ✅ Domain Graph (CSV → Neo4j nodes + relationships)

**Not yet implemented** (future US009):
- ⏳ Subject Graph (markdown → extracted entities)
- ⏳ Lexical Graph (document chunks + embeddings)
- ⏳ Entity Resolution (Subject ↔ Domain linking)

The tool will be extended in US009 to support text processing.

---

## Testing

### Manual Test

```bash
# Test the MCP tool directly
python -m tests.test_mcp_build_graph
```

### Via Claude Code

```
User: "I've completed all the planning stages. Build the graph now."

Claude Code: [calls kg_build_graph tool]

Claude Code: "The domain graph has been built successfully!
I imported 75 nodes and 111 relationships into Neo4j..."
```

---

## Implementation Details

### Helper Functions

The tool uses two helper functions for formatting:

```python
def _format_node_results(nodes: list[dict]) -> str:
    """Format node import results for display."""
    # Returns formatted string like:
    #   [OK] Product: 5 nodes
    #   [OK] Supplier: 18 nodes

def _format_rel_results(rels: list[dict]) -> str:
    """Format relationship import results for display."""
    # Returns formatted string like:
    #   [OK] SUPPLIED_BY: 88 relationships
    #   [OK] HAS_PART: 23 relationships (WARNING: 2 orphans)
```

### State Management

Unlike conversational agents (kg_user_intent, kg_ner_extraction), this tool:
- ❌ Does NOT maintain conversation history
- ✅ Loads state in read-only mode
- ✅ Does NOT modify state (build results are transient)
- ✅ Is **idempotent** (safe to call multiple times)

Rationale: Graph building is a deterministic operation, not a conversation.

---

## Verification Queries

After a successful build, these Cypher queries are useful:

```cypher
// View all nodes
MATCH (n) RETURN n LIMIT 25

// Check schema visualization
CALL db.schema.visualization()

// Count nodes by label
MATCH (n) RETURN labels(n) as label, count(*) as count

// Count relationships by type
MATCH ()-[r]->() RETURN type(r) as type, count(*) as count

// Find orphan nodes (no relationships)
MATCH (n) WHERE NOT (n)--() RETURN n

// Check constraints
SHOW CONSTRAINTS
```

---

## Related Tools

| Tool | Purpose | Stage |
|------|---------|-------|
| `kg_schema_proposal` | Design the construction plan | 3 |
| `kg_critic` | Validate the plan | 3 |
| `kg_get_state` | Check if plan is approved | - |
| **`kg_build_graph`** | **Build the graph** | **6** |

---

## FAQ

**Q: Can I run this tool multiple times?**
A: Yes! The build process uses MERGE queries, which are idempotent. Re-running will update existing nodes/relationships.

**Q: What happens if Neo4j already has data?**
A: The builder will MERGE new data into the existing graph. It won't delete existing data unless there are unique constraint violations.

**Q: Can I clear the graph before building?**
A: Yes, run this Cypher query in Neo4j Browser before calling the tool:
```cypher
MATCH (n) DETACH DELETE n
```

**Q: Does this process markdown files?**
A: Not yet. Text processing (Subject/Lexical graphs) will be added in US009.

**Q: How long does it take?**
A: For typical datasets (<1000 rows per CSV), expect 5-10 seconds. Larger datasets may take longer.

**Q: What if I get "Connection refused"?**
A: Check that:
1. Neo4j is running (local: `neo4j start`, cloud: check Aura console)
2. NEO4J_URI is correct
3. Firewall allows connection

---

## Source Code

**File**: `mcp_server/server.py`
**Lines**: ~526-720
**Dependencies**: `pipelines.build_domain_graph`, `utils.neo4j_utils`

---

**Last Updated**: 2026-02-11
**Status**: Production Ready ✅
