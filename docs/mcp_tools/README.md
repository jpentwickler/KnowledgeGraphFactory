# MCP Tools Reference

This directory contains detailed documentation for each MCP tool exposed by the KG-Factory server.

## Available Tools

### State Management
- **[kg_get_state](../architecture/00_architecture.md)** - Check current pipeline progress and approved artifacts

### Pipeline Stages

| Stage | Tool | Documentation | Purpose |
|-------|------|---------------|---------|
| 1 | `kg_user_intent` | [Architecture](../architecture/01_user_intent.md) | Define graph goals conversationally |
| 2 | `kg_file_suggestion` | [Architecture](../architecture/02_file_suggestion.md) | Select relevant data files |
| 3 | `kg_schema_proposal` | [Architecture](../architecture/03_schema_proposal.md) | Design CSV → graph schema |
| 3/5 | `kg_critic` | [Architecture](../architecture/03_schema_proposal.md) | Validate proposals (structured/unstructured) |
| 4 | `kg_ner_extraction` | [Architecture](../architecture/04_ner_extraction.md) | Extract entity types from text |
| 5 | `kg_fact_extraction` | [Architecture](../architecture/05_fact_extraction.md) | Extract relationship types from text |
| 6 | **`kg_build_graph`** | **[Tool Docs](kg_build_graph.md)** | **Build Neo4j graph from approved artifacts** |

### Utilities
- **kg_reset_state** - Clear all state and start fresh

---

## Tool Patterns

### Conversational Agents (Stages 1-5)

These tools maintain conversation history and support iterative refinement:

```python
# Multi-turn conversation
kg_user_intent(message="I want to build a furniture supply chain graph")
# Agent asks clarifying questions...
kg_user_intent(message="Office furniture with suppliers and customer reviews")
# Agent proposes goal...
kg_user_intent(message="approve")
```

**Pattern**:
- Pass user messages through exactly as written
- Agent maintains conversation history (last 20 messages)
- Propose → Review → Iterate → Approve workflow

### Validation Tools

**kg_critic** validates proposals at two stages:

```python
# After schema proposal (Stage 3)
kg_critic(scope="structured")

# After entity/fact extraction (Stage 5)
kg_critic(scope="unstructured")
```

### Execution Tools (Stage 6)

**kg_build_graph** is deterministic - no conversation, just execution:

```python
# Build the graph
kg_build_graph(message="build")
```

**Pattern**:
- No conversation history
- Validates prerequisites
- Executes build process
- Returns verification results

---

## Quick Start

1. **Check state**: `kg_get_state()` - See what's been completed
2. **Start pipeline**: `kg_user_intent(message="...")` - Define your goal
3. **Follow stages 2-5**: Each tool guides you through its stage
4. **Build graph**: `kg_build_graph(message="build")` - Execute construction

---

## Tool Documentation Details

### Stage 6: Build Graph

**Detailed Documentation**: [kg_build_graph.md](kg_build_graph.md)

The `kg_build_graph` tool:
- ✅ Validates prerequisites (construction plan, Neo4j credentials)
- ✅ Executes 5-step build process (validate → constraints → nodes → rels → verify)
- ✅ Returns detailed verification statistics
- ✅ Handles errors gracefully with actionable messages

**Prerequisites**:
- Stage 3 completed (approved_construction_plan)
- Neo4j instance running
- Environment variables set (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

**Usage**:
```python
kg_build_graph(message="build the graph")
```

**Returns**:
- Node import results (count, errors)
- Relationship import results (count, orphans, errors)
- Verification stats (total nodes/rels, orphan nodes)
- Neo4j connection info (version, database)

---

## For More Information

- **Architecture**: See `../architecture/` for detailed agent specifications
- **Implementation**: See `../implementation/` for implementation guides
- **User Stories**: See `../user_stories/` for requirements and specifications

---

**Last Updated**: 2026-02-11
