# Usage Guides

User-facing guides and tutorials for working with KG-Factory agents.

---

## Cowork Plugin Deployment

**Location**: [deploy_cowork_plugin.md](deploy_cowork_plugin.md)

Step-by-step guide to deploying the remote query server (Railway/Fly.io) and
installing the Cowork plugin so end users can query your knowledge graph with
zero technical setup. Covers server deployment, plugin generation, end user
installation, and troubleshooting.

---

## OpenClaw Cloud Deployment

**Location**: [deploy_openclaw.md](deploy_openclaw.md)

Step-by-step guide to deploying OpenClaw on Railway and connecting it to the
KG-Query server via HTTP MCP transport. End users query the knowledge graph
from messaging channels (WhatsApp, Telegram, Slack, Discord) with no local
installation. Covers OpenClaw Railway deployment, mcp-adapter configuration,
SKILL.md installation, and messaging channel setup.

---

## NER Extraction Agent Guides

**Location**: [ner/](ner/)

The NER (Named Entity Recognition) agent helps extract entity types from unstructured text (markdown files). These guides show you how to use it effectively:

- **[Quick Start](ner/quick_start.md)** - Real conversation snippets to get started quickly
- **[Usage Examples](ner/usage_examples.md)** - Comprehensive usage scenarios and patterns
- **[Guided Discovery](ner/guided_discovery.md)** - Collaborative entity discovery with domain expertise

---

## When to Use These Guides

### Quick Start
Use when you're **new to the NER agent** and want to see basic patterns.

Example scenarios:
- "How do I start NER extraction?"
- "What does a typical conversation look like?"
- "How do I approve entity types?"

### Usage Examples
Use when you need **comprehensive coverage** of different scenarios.

Example scenarios:
- "What if I want to add a custom entity type?"
- "How do I handle similar but different concepts?"
- "What's the full workflow from start to approval?"

### Guided Discovery
Use when you want to **actively guide the agent** based on your domain knowledge.

Example scenarios:
- "I noticed a pattern in the text, how do I tell the agent?"
- "I want the agent to investigate specific sections"
- "How do I collaborate with the agent to find entities?"

---

## Guide Structure

Each guide follows this pattern:

1. **Prerequisites** - What you need before starting
2. **Dialog Examples** - Real conversations showing usage
3. **Patterns** - Common interaction patterns
4. **Tips** - Best practices and troubleshooting

---

## Related Documentation

- **[Architecture: NER Agent](../architecture/04_ner_extraction.md)** - Technical specification
- **[Implementation: US006](../user_stories/US006_ner_extraction_agent.md)** - Requirements and design
- **[MCP Tools](../mcp_tools/README.md)** - Tool reference

---

**Last Updated**: 2026-02-11
