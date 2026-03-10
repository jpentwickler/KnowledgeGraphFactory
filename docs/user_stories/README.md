# User Stories

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Personas** | KG-Factory Developer, Knowledge Graph Developer | Two distinct users: those building the platform vs those using it |
| **Slicing** | Vertical | Deliver complete functionality end-to-end early; validate Claude Code integration before building all agents |
| **Initial focus** | KG-Factory Developer | Build minimal working system first, then validate with Knowledge Graph Developer stories |
| **Example project** | Include in first stories | Enables testing from user perspective immediately |

## Personas

| Persona | Description | Goals |
|---------|-------------|-------|
| **KG-Factory Developer** | Developer building the KG-Factory platform | Create robust, well-tested agents and MCP integration |
| **Knowledge Graph Developer** | End user building knowledge graphs using KG-Factory + Claude Code | Rapidly create high-quality knowledge graphs through natural conversation |

## Story Point Scale

| Points | Effort | Description |
|--------|--------|-------------|
| 1 | Hours | Trivial, well-understood |
| 2 | ~1 day | Small, clear scope |
| 3 | 2-3 days | Medium complexity |
| 5 | ~1 week | Significant work |
| 8 | 1-2 weeks | Complex, some unknowns |
| 13 | 2+ weeks | Should probably split |

## User Story Template

```markdown
# US[NNN]: [Title]

## User Story

**As a** [persona]
**I want** [capability]
**So that** [benefit]

## Story Points: [N]

## Acceptance Criteria

- [ ] [Criterion 1]
- [ ] [Criterion 2]
- [ ] [Criterion N]

## Definition of Done

- [ ] Code implemented and working
- [ ] Unit tests passing
- [ ] Integration test passing (if applicable)
- [ ] Documentation updated
- [ ] Code reviewed
- [ ] Acceptance criteria verified

## Notes

[Any additional context, technical notes, or dependencies]
```

## Global Definition of Done

All user stories must meet these criteria before being considered complete:

1. **Code Quality**
   - Code follows project patterns (see CLAUDE.md)
   - No hardcoded secrets or credentials
   - Error handling implemented

2. **Testing**
   - Unit tests for new functionality
   - Interactive test script works (for agents)
   - MCP tool callable (for MCP stories)

3. **Documentation**
   - CLAUDE.md updated if architecture changes
   - Code has docstrings for public functions
   - Example usage documented

4. **Integration**
   - Works with existing components
   - State properly passed between stages
   - No regressions in existing functionality

## Story Index

| ID | Title | Points | Status |
|----|-------|--------|--------|
| [US001](US001_core_agent_framework.md) | Core Agent Framework | 5 | Not Started |
| [US002](US002_user_intent_agent.md) | User Intent Agent | 3 | Not Started |
| [US003](US003_mcp_server_user_intent.md) | MCP Server with User Intent | 5 | Not Started |
| [US004](US004_file_suggestion_agent.md) | File Suggestion Agent | 3 | Not Started |
| [US005](US005_schema_proposal_agent.md) | Schema Proposal Agent | 5 | Not Started |
| [US006](US006_ner_extraction_agent.md) | NER Extraction Agent | 3 | Not Started |
| [US007](US007_fact_extraction_agent.md) | Fact Extraction Agent | 3 | Not Started |
| [US008](US008_graph_builder.md) | Domain Graph Builder | 5 | Not Started |
| [US009](US009_text_graph_builder.md) | Text Graph Builder | 8 | Not Started |
| [US010](US010_adaptive_markdown_splitting.md) | Adaptive Markdown Splitting | 3 | Not Started |
| [US011](US011_langsmith_observability.md) | LangSmith Observability | 3 | Not Started |
| [US012](US012_competency_questions.md) | Competency Questions | 3 | Not Started |
| [US013](US013_kg_query.md) | KG Query Infrastructure | 5 | Not Started |
| [US014](US014_cq_evaluation.md) | CQ Evaluation | 5 | Not Started |
| [US015](US015_query_agent_openclaw.md) | Query Agent & Platform Integration | 13 | Not Started |
| [US017](US017_mermaid_diagram.md) | Mermaid Diagram Generation | 3 | Not Started |
| [US018](US018_project_management.md) | Project Management | 5 | Not Started |
| [US020](US020_extraction_efficiency.md) | Extraction Efficiency | 5 | Not Started |
| [US021](US021_remote_query_server.md) | Remote Query Server | 5 | Not Started |
| [US022](US022_plugin_distribution.md) | Plug-and-Play Plugin Distribution | 3 | Not Started |
| [US023](US023_canonical_graph_schema.md) | Canonical Graph Schema | 3 | Not Started |
| [US024](US024_openclaw_integration.md) | OpenClaw Cloud Integration | 3 | Not Started |
