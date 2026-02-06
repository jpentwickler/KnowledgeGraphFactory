# KG-Factory

A multi-agent system for automated knowledge graph construction in Neo4j.

Built with pure Python + Claude API. No LangChain, no frameworks.

## Quick Start

```bash
# 1. Clone and enter directory
cd kg-factory

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and edit environment file
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# 5. Run the first test
python -m tests.test_01_user_intent
```

## Project Structure

```
kg-factory/
├── CLAUDE.md           # Context for Claude Code (read this first if using Claude Code)
├── docs/               # Detailed specifications for each agent
│   ├── 01_user_intent.md
│   ├── 02_file_suggestion.md
│   ├── 03_schema_proposal.md
│   ├── 04_ner_extraction.md
│   ├── 05_fact_extraction.md
│   └── 06_graph_construction.md
├── core/               # Framework: agent runner, state management, tools
├── agents/             # Agent implementations (one per stage)
├── tools/              # Tool definitions for each agent
├── pipelines/          # Multi-agent workflows
├── tests/              # Interactive test scripts
└── data/               # Sample CSV and markdown files
```

## Development Approach

Build and test each agent sequentially:

1. **Stage 1: User Intent** - Define what kind of graph to build
2. **Stage 2: File Suggestion** - Select relevant data files
3. **Stage 3: Schema Proposal** - Design the graph schema
4. **Stage 4: NER Extraction** - Identify entity types in text
5. **Stage 5: Fact Extraction** - Define relationship types
6. **Stage 6: Graph Construction** - Build the actual graph

Each stage has:
- A detailed spec in `docs/`
- An agent implementation in `agents/`
- An interactive test in `tests/`

## Using with Claude Code

This project is designed to be developed with Claude Code. The `CLAUDE.md` file provides context about the architecture and implementation patterns.

```bash
# Open the project in Claude Code
claude code kg-factory/
```

Claude Code can:
- Read the specs in `docs/` to understand each agent
- Implement agents following the patterns in `core/`
- Run tests to verify implementations
- Iterate based on test results

## License

MIT
