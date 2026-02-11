# KG-Factory Documentation

Complete documentation for the KG-Factory knowledge graph construction pipeline.

---

## 📁 Documentation Structure

```
docs/
├── architecture/       - Agent architecture and design specifications
├── guides/            - User-facing guides and tutorials
│   └── ner/          - NER agent usage guides
├── implementation/     - Implementation guides and technical details
├── mcp_tools/         - MCP tool reference documentation
├── research/          - Assessments and analysis of external patterns
├── summaries/         - High-level completion reports and summaries
└── user_stories/      - Requirements and user story specifications
```

---

## 🎯 Quick Start

### New to KG-Factory?

1. **[Architecture Overview](architecture/00_architecture.md)** - Understand the multi-agent pipeline
2. **[MCP Tools Reference](mcp_tools/README.md)** - Learn about available tools
3. **[Walkthrough](architecture/WALKTHROUGH.md)** - Step-by-step example

### Building a Graph?

1. **Stage 1**: [User Intent](architecture/01_user_intent.md) - Define your goals
2. **Stage 2**: [File Suggestion](architecture/02_file_suggestion.md) - Select data files
3. **Stage 3**: [Schema Proposal](architecture/03_schema_proposal.md) - Design CSV schema
4. **Stage 4**: [NER Extraction](architecture/04_ner_extraction.md) - Extract entity types
5. **Stage 5**: [Fact Extraction](architecture/05_fact_extraction.md) - Extract relationships
6. **Stage 6**: [Graph Construction](architecture/06_graph_construction.md) - Build Neo4j graph

### Implementing Agents?

See **[implementation/](implementation/)** for detailed guides:
- [US008: Domain Builder](implementation/US008_domain_builder.md) - CSV → Neo4j pipeline
- [US008: MCP Integration](implementation/US008_mcp_integration.md) - MCP tool implementation

---

## 📚 Documentation by Category

### Architecture & Design

**Location**: [architecture/](architecture/)

- **[00_architecture.md](architecture/00_architecture.md)** - System overview and multi-agent pipeline
- **[01_user_intent.md](architecture/01_user_intent.md)** - Stage 1: Goal definition agent
- **[02_file_suggestion.md](architecture/02_file_suggestion.md)** - Stage 2: File selection agent
- **[03_schema_proposal.md](architecture/03_schema_proposal.md)** - Stage 3: Schema design agent
- **[04_ner_extraction.md](architecture/04_ner_extraction.md)** - Stage 4: Entity extraction agent
- **[05_fact_extraction.md](architecture/05_fact_extraction.md)** - Stage 5: Relationship extraction agent
- **[06_graph_construction.md](architecture/06_graph_construction.md)** - Stage 6: Graph building pipeline
- **[WALKTHROUGH.md](architecture/WALKTHROUGH.md)** - Complete example walkthrough

### Implementation Guides

**Location**: [implementation/](implementation/)

- **[US008_domain_builder.md](implementation/US008_domain_builder.md)** - Domain Graph Builder implementation
  - Three-layer validation (CSV + constraints + MERGE)
  - Node and relationship import logic
  - Verification and error handling

- **[US008_mcp_integration.md](implementation/US008_mcp_integration.md)** - MCP tool integration
  - How kg_build_graph tool works
  - Tool definition and registration
  - State management patterns

### MCP Tools Reference

**Location**: [mcp_tools/](mcp_tools/)

- **[README.md](mcp_tools/README.md)** - Index of all MCP tools
- **[kg_build_graph.md](mcp_tools/kg_build_graph.md)** - Graph builder tool reference
  - Function signature
  - Prerequisites and configuration
  - Usage examples
  - Error handling guide

### User Stories

**Location**: [user_stories/](user_stories/)

Requirements and specifications for each feature:
- **US001**: Core agent framework
- **US002**: User Intent agent
- **US003**: MCP server (User Intent)
- **US004**: File Suggestion agent
- **US005**: Schema Proposal agent
- **US006**: NER Extraction agent
- **US007**: Fact Extraction agent
- **US008**: Graph Builder (CSV → Neo4j)

### Completion Summaries

**Location**: [summaries/](summaries/)

High-level reports for major milestones:
- **[US008_domain_builder_summary.md](summaries/US008_domain_builder_summary.md)** - Technical implementation summary
- **[US008_mcp_tool_summary.md](summaries/US008_mcp_tool_summary.md)** - User-facing completion report

---

## 🔍 Finding Documentation

### By Topic

| Topic | Document |
|-------|----------|
| **Getting Started** | [Architecture Overview](architecture/00_architecture.md) |
| **MCP Tools** | [MCP Tools README](mcp_tools/README.md) |
| **Building Graphs** | [Walkthrough](architecture/WALKTHROUGH.md) |
| **CSV Import** | [Domain Builder](implementation/US008_domain_builder.md) |
| **Entity Extraction** | [NER Architecture](architecture/04_ner_extraction.md) |
| **Neo4j Setup** | [Graph Construction](architecture/06_graph_construction.md) |

### By User Type

**End Users** (building graphs):
1. [Walkthrough](architecture/WALKTHROUGH.md)
2. [MCP Tools README](mcp_tools/README.md)
3. [NER Quick Start](NER_QUICK_START_DIALOGS.md)

**Developers** (implementing features):
1. [Architecture Overview](architecture/00_architecture.md)
2. [Implementation Guides](implementation/)
3. [User Stories](user_stories/)

**Contributors** (extending the system):
1. [Architecture](architecture/)
2. [Implementation Guides](implementation/)
3. [Assessment: MCP Neo4j Data Modeling](assessment_mcp_neo4j_data_modeling.md)

---

## 📖 Special Topics

### NER Agent Documentation

The NER (Named Entity Recognition) agent has additional usage guides:

- **[NER_QUICK_START_DIALOGS.md](NER_QUICK_START_DIALOGS.md)** - Quick start examples
- **[NER_AGENT_USAGE_EXAMPLES.md](NER_AGENT_USAGE_EXAMPLES.md)** - Comprehensive usage scenarios
- **[NER_GUIDED_DISCOVERY_DIALOGS.md](NER_GUIDED_DISCOVERY_DIALOGS.md)** - Collaborative entity discovery

### Assessment Documents

- **[assessment_mcp_neo4j_data_modeling.md](assessment_mcp_neo4j_data_modeling.md)** - Analysis of neo4j-contrib/mcp-neo4j patterns
  - NODE KEY constraint approach
  - Three-layer validation strategy
  - LOAD CSV + MERGE patterns

---

## 🚀 Development Workflow

### Adding a New Agent (Stages 1-5)

1. Write architecture spec in `architecture/`
2. Create user story in `user_stories/`
3. Implement agent in `agents/`
4. Add MCP tool to `mcp_server/server.py`
5. Write implementation guide in `implementation/`
6. Document MCP tool in `mcp_tools/`

### Adding a New Pipeline Component (Stage 6)

1. Write architecture spec in `architecture/`
2. Create user story in `user_stories/`
3. Implement pipeline in `pipelines/`
4. Add MCP tool (if applicable)
5. Write implementation guide in `implementation/`
6. Create completion summary in `summaries/`

---

## 📝 Documentation Standards

### File Naming

- **Architecture**: `NN_component_name.md` (e.g., `01_user_intent.md`)
- **User Stories**: `USXXX_feature_name.md` (e.g., `US008_graph_builder.md`)
- **Implementation**: `USXXX_component_name.md` (e.g., `US008_domain_builder.md`)
- **Summaries**: `USXXX_component_summary.md`

### Document Structure

Each document should include:
- **Purpose** - What it does
- **Prerequisites** - What's needed
- **Usage** - How to use it
- **Examples** - Real-world scenarios
- **Troubleshooting** - Common issues

---

## 🔗 External Resources

- **Neo4j Graph Database**: https://neo4j.com/docs/
- **Anthropic Claude API**: https://docs.anthropic.com/
- **MCP Protocol**: https://modelcontextprotocol.io/
- **FastMCP Framework**: https://github.com/jlowin/fastmcp

---

## 📄 License

This documentation is part of the KG-Factory project.

**Last Updated**: 2026-02-11
