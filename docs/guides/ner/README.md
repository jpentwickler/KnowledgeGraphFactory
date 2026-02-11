# NER Extraction Agent - Usage Guides

Comprehensive guides for using the NER (Named Entity Recognition) Extraction Agent to identify entity types from unstructured text.

---

## Available Guides

### 1. [Quick Start](quick_start.md) ⚡

**Best for**: First-time users, quick reference

Real conversation snippets showing common patterns:
- First-time user flow
- Basic entity discovery
- Approving entity types
- Adding custom entities
- Handling edge cases

**Time to read**: 5 minutes

---

### 2. [Usage Examples](usage_examples.md) 📚

**Best for**: Comprehensive understanding, reference

Detailed end-to-end scenarios:
- Complete workflow from start to approval
- Standard analysis (well-known + discovered types)
- Custom entity types (user-driven discovery)
- Handling nuances (similar concepts, overlapping types)
- Evidence-based validation

**Time to read**: 15 minutes

---

### 3. [Guided Discovery](guided_discovery.md) 🎯

**Best for**: Domain experts, collaborative discovery

Shows how to actively guide the agent:
- User spots patterns and directs investigation
- Focused file exploration
- Domain-specific concept discovery
- Collaborative entity refinement
- Hypothesis validation

**Time to read**: 10 minutes

---

## Which Guide Should I Use?

```
┌─────────────────────────────────────────────────┐
│ Start Here: Quick Start                         │
│ ├─ Need more detail? → Usage Examples          │
│ └─ Want to guide the agent? → Guided Discovery │
└─────────────────────────────────────────────────┘
```

### Decision Tree

**Q: Is this your first time using the NER agent?**
- Yes → Start with [Quick Start](quick_start.md)
- No → Continue below

**Q: Do you know what entity types you're looking for?**
- Yes, I have specific types in mind → [Guided Discovery](guided_discovery.md)
- Not sure, want agent to discover → [Usage Examples](usage_examples.md)

**Q: How much detail do you need?**
- Just show me the patterns → [Quick Start](quick_start.md)
- Show me complete workflows → [Usage Examples](usage_examples.md)

---

## NER Agent Overview

The NER Extraction Agent:

1. **Analyzes** approved markdown files from Stage 2
2. **Identifies** entity types (categories) to extract
3. **Proposes** both well-known types (from CSV schema) and discovered types (from text)
4. **Gathers evidence** using search patterns to validate discovered types
5. **Iterates** with you to refine the entity list
6. **Approves** finalized entity types for downstream use

---

## Prerequisites

Before using the NER agent, complete:

- ✅ **Stage 1**: User Intent (approved_user_goal)
- ✅ **Stage 2**: File Suggestion (approved_files with markdown files)
- ✅ **Stage 3**: Schema Proposal (approved_construction_plan)

---

## Common Patterns

### Pattern 1: Let Agent Discover
```
User: "Analyze the review files and find entity types"
Agent: [reviews files, proposes entities with evidence]
User: "Looks good, approve"
```

### Pattern 2: Add Custom Types
```
User: "Also include 'CustomerComplaint' as an entity type"
Agent: [searches for evidence, validates]
User: "Approve"
```

### Pattern 3: Guide Investigation
```
User: "Look at the 'Issues' section in product_reviews.md"
Agent: [examines specific section]
User: "What entity types do you see there?"
```

---

## Key Features

### Evidence-Based Discovery

The agent **doesn't just guess** - it:
- Searches files using multiple patterns
- Counts total mentions
- Shows example excerpts
- Reports file distribution

Example:
```
QualityIssue (7 mentions across 3 files)
  Patterns: "defect", "broke", "issue", "problem"
  Examples:
    - "the leg broke after 2 months"
    - "paint defect on armrest"
    - "assembly issue with screws"
```

### Well-Known vs Discovered Types

- **Well-known**: Node labels from your CSV schema (Product, Supplier, etc.)
  - Automatically included if they appear in text
  - No evidence gathering needed

- **Discovered**: New types found in markdown (QualityIssue, Feature, etc.)
  - Requires evidence gathering
  - Must have sufficient mentions (≥3)

### Transparent Process

The agent narrates its analysis:
- Which files it reviewed
- How many sections it found
- What patterns it searched
- How many matches it discovered
- Why it excluded certain types

---

## Tips for Success

1. **Be Specific**: Guide the agent to relevant sections if you know where to look
2. **Validate Evidence**: Check that excerpts actually support the entity type
3. **Avoid Overlap**: Don't create similar types (Issue vs Problem vs Defect - pick one)
4. **Think Categories**: Entity types are categories, not individual instances
5. **Consider Goal**: Only include types that serve your graph's purpose

---

## Related Documentation

- **[Architecture: NER Agent](../../architecture/04_ner_extraction.md)** - How it works internally
- **[User Story: US006](../../user_stories/US006_ner_extraction_agent.md)** - Requirements
- **[MCP Tool: kg_ner_extraction](../../mcp_tools/README.md)** - Tool reference

---

**Last Updated**: 2026-02-11
