# Furniture Supply Chain Knowledge Graph

This project uses KG-Factory via MCP to build a knowledge graph.

## How to Use

The `kg_` tools connect to specialized agents. Your role is to **relay messages**
between the user and the agents — pass messages through exactly as written,
and show responses back without summarizing or adding your own analysis.

Do NOT read data files or add context unless the user explicitly asks you to.
The agents will ask their own questions.

## Data Files

Available in `data/` if the user or agent needs them:

- `data/products.csv`
- `data/suppliers.csv`
- `data/reviews/stockholm_chair_reviews.md`

## State

Saved to `state/current_state.json`.
