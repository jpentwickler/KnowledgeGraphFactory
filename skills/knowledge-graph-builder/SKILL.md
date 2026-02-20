---
name: knowledge-graph-builder
description: >
  Build a knowledge graph from CSV and markdown files using the KG-Factory
  construction pipeline. Use when the user wants to create, design, or populate
  a knowledge graph -- NOT for querying an existing one.
metadata: {"openclaw":{"emoji":"hammer_and_wrench","requires":{"env":["NEO4J_URI","ANTHROPIC_API_KEY"]}}}
---

# Knowledge Graph Builder

Build knowledge graphs through a guided, multi-stage pipeline.

## When to use this skill

Use the `kg_` construction tools when the user wants to:
- Start a new knowledge graph project
- Define what a graph should represent (goal/intent)
- Select and review data files (CSV, markdown)
- Design a schema (construction plan)
- Extract entity types and fact types from text
- Build the graph in Neo4j
- Evaluate competency questions against the graph

Do NOT use for:
- Querying an existing graph (use the `knowledge-graph` skill instead)
- General questions about Neo4j or graph databases

## Starting a session

If `KG_BASE_DIR` is configured, always start by selecting a project:

1. `kg_project('list')` -- see available projects
2. `kg_project('create <name>')` -- start a new project
3. `kg_project('open <name>')` -- resume an existing project

If `KG_BASE_DIR` is not set, the pipeline uses `KG_STATE_DIR` or `./state/`
directly (single-project mode).

## Pipeline workflow

Follow these stages in order. Each stage must be approved before the next.

1. **kg_project** -- Select or create a project (if `KG_BASE_DIR` is set)
2. **kg_user_intent** -- Define the graph goal and competency questions
3. **kg_file_suggestion** -- Select data files to include
4. **kg_schema_proposal** -- Design the construction plan (CSV schema)
5. **kg_critic** (scope="structured") -- Validate the schema
6. **kg_ner_extraction** -- Extract entity types from markdown files
7. **kg_fact_extraction** -- Extract fact types (relationships)
8. **kg_critic** (scope="unstructured") -- Validate entity/fact types
9. **kg_build_graph** -- Build the graph in Neo4j
10. **kg_query** -- Query and verify the graph
11. **kg_evaluate_cqs** -- Evaluate competency questions

Use `kg_get_state` at any time to check pipeline progress.
Use `kg_competency_questions` to manage CQs at any stage.
Use `kg_diagram` to generate a Mermaid schema diagram.

## Relay pattern

The `kg_` tools connect to specialized agents. Your role is to **relay
messages** between the user and the agents:

- Pass the user's message to the agent AS-IS
- Show the agent's response to the user AS-IS
- Do NOT read data files, analyze schemas, or add context
- Do NOT answer questions the agent asks -- let the user answer them
- Do NOT summarize or paraphrase -- relay faithfully in both directions

The agents guide the user through each stage with their own questions.

## Data files

Users must place CSV and markdown files in the project's `data/` directory
before running the file suggestion stage. The pipeline reads files from:
- `{KG_BASE_DIR}/{project}/data/` (project mode)
- `KG_DATA_DIR` environment variable
- `./data/` (default)

## Tools reference

| Tool | Purpose |
|------|---------|
| `kg_project(message)` | Manage projects (list/create/open/status) |
| `kg_get_state()` | Check pipeline progress |
| `kg_user_intent(message)` | Define graph goal |
| `kg_file_suggestion(message)` | Select data files |
| `kg_schema_proposal(message)` | Design CSV schema |
| `kg_competency_questions(message)` | Manage competency questions |
| `kg_critic(scope)` | Validate proposals |
| `kg_ner_extraction(message)` | Extract entity types |
| `kg_fact_extraction(message)` | Extract fact types |
| `kg_build_graph(message, scope)` | Build graph in Neo4j |
| `kg_query(question, context)` | Query the graph |
| `kg_evaluate_cqs(cq_id, cq_ids)` | Evaluate competency questions |
| `kg_diagram(scope)` | Generate Mermaid diagram |
| `kg_reset_state()` | Clear all state |
