---
name: knowledge-graph
description: >
  Query a domain knowledge graph built with KG-Factory. Use when the user
  asks about domain-specific data, business entities, relationships between
  entities, or content from documents that have been indexed. Do NOT use
  for general knowledge questions -- only for data in the user's graph.
metadata: {"openclaw":{"emoji":"graph","requires":{"env":["NEO4J_URI","ANTHROPIC_API_KEY","OPENAI_API_KEY"]}}}
---

# Knowledge Graph Query

Query your domain knowledge graph with adaptive retrieval.

## When to use this skill

Use `kg_query` when the user asks about:
- Business entities (suppliers, products, customers, etc.)
- Relationships between entities ("which suppliers provide X?")
- Content from indexed documents (reviews, reports, specs)
- Cross-referencing structured data with document content
- Aggregations or counts over domain data

Do NOT use for:
- General knowledge ("what is Neo4j?")
- Questions about files on disk (use filesystem tools)
- Web searches (use web_search)

## Tools

### kg_query(question, context)
Single-shot adaptive query. Automatically selects the best retrieval strategy
(schema, cypher, vector, hybrid, or cross_layer) based on the question.

- `question`: Natural language question about the graph
- `context`: Optional prior context to guide strategy selection. Include
  relevant details from previous answers when asking follow-up questions.

### kg_graph_info()
Quick check of what's in the graph. Call this first if unsure whether
the graph has relevant data.

## Tips

- Start with kg_graph_info() to understand available data
- Use specific entity names when you know them
- For follow-ups, pass relevant details from the previous answer as `context`
- The tool is stateless -- each call is independent
