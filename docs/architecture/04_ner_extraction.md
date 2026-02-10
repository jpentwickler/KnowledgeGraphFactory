# Stage 4: Named Entity Recognition (NER) Agent

## Purpose

Analyze unstructured data files (markdown) and propose entity types that can be extracted.
These entities will form the Subject Graph that bridges to the Domain Graph.

## Key Concept: Two Types of Entities

1. **Well-known entities**: Match existing node labels from the construction plan
   - Example: "Product" already exists in the domain graph
   - We want to find mentions of products in the text

2. **Discovered entities**: New types found in the text that support the user's goal
   - Example: "Issue", "Feature" found in product reviews
   - These add depth to the knowledge graph

## Input

```python
state["approved_user_goal"] = {...}
state["approved_files"] = ["product_reviews/gothenburg_table_reviews.md", ...]
state["approved_construction_plan"] = {
    "Product": {"construction_type": "node", "label": "Product", ...},
    "Supplier": {"construction_type": "node", "label": "Supplier", ...},
    ...
}
```

## Output

```python
state["approved_entity_types"] = {
    "Product": {
        "source": "well_known",
        "description": "Products mentioned in reviews, bridges to existing Product nodes"
    },
    "Issue": {
        "source": "discovered",
        "description": "Problems reported by reviewers that support root cause analysis"
    },
    "Feature": {
        "source": "discovered",
        "description": "Product characteristics mentioned in reviews"
    }
}
```

Each entity type includes:
- **source**: `"well_known"` (from construction plan) or `"discovered"` (found in text)
- **description**: What this entity type represents and why it's relevant

## Pre-computation Pattern

Like the Schema Proposal Agent (Stage 3), the NER agent uses pre-computed context
injected into the system prompt. This avoids multiple tool calls for context gathering.

### `build_markdown_context(state)`

Reads all approved markdown files and builds a **structure-aware preview**.
Instead of reading just the first N lines, it parses the markdown heading
structure and extracts the first few lines of each section. This ensures
the agent sees every section of the document, even for long non-repetitive
files where important entity types may only appear in specific sections.

```python
def build_structured_preview(file_path: str, lines_per_section: int = 5) -> str:
    """Extract heading structure + first N lines of each section.

    Parses markdown headings (#, ##, ###) and captures the first
    lines_per_section lines after each heading. This gives visibility
    into every section of the document regardless of file length.
    """
    lines = read_all_lines(file_path)
    total = len(lines)

    sections = []
    current_heading = None
    current_lines = []

    for i, line in enumerate(lines):
        if line.startswith('#'):
            if current_heading:
                preview = current_lines[:lines_per_section]
                sections.append((current_heading, preview))
            current_heading = (i + 1, line.strip())
            current_lines = []
        else:
            current_lines.append(line)

    if current_heading:
        preview = current_lines[:lines_per_section]
        sections.append((current_heading, preview))

    # Format output
    output = [f"=== {file_path} ({total} lines) ===\n"]
    for (line_num, heading), preview in sections:
        output.append(f"{heading}  [line {line_num}]")
        for p in preview:
            if p.strip():
                output.append(f"  {p.rstrip()}")
        output.append("")

    return "\n".join(output)


def build_markdown_context(state: dict) -> str:
    """Build structure-aware preview context for all approved markdown files."""
    approved_files = state.get("approved_files", {})
    unstructured = approved_files.get("unstructured", [])

    parts = []
    for file_entry in unstructured:
        path = file_entry["path"]
        full_path = resolve_data_path(path)
        parts.append(build_structured_preview(full_path))

    return "\n".join(parts)
```

For a 380-line audit report with 10 sections, this produces ~60 lines of
structured preview covering every section — compared to 15 lines from just
the top. The line numbers (`[line 26]`) allow the agent to make informed
`sample_file` calls to read specific sections in full.

### `build_well_known_types(state)`

Extracts node labels from the construction plan:

```python
def build_well_known_types(state: dict) -> str:
    """Extract well-known entity types from the approved construction plan."""
    plan = state.get("approved_construction_plan", {})
    types = [
        entry["label"]
        for entry in plan.values()
        if entry.get("construction_type") == "node"
    ]
    return ", ".join(types) if types else "(none)"
```

Both are injected into the system prompt via template placeholders:
`{user_goal}`, `{well_known_types}`, `{file_context}`.

## Agent Instructions

```
You are a named entity recognition specialist working on a knowledge graph.
Your job is to analyze text files and propose the types of entities that
could be extracted to enrich the graph.

Entity types are categories of people, places, things, and qualities -
NOT individual instances.
For example: "Product" is an entity type, "Gothenburg Table" is an instance.

## User Goal

{user_goal}

## Well-Known Entity Types

These node labels already exist in the graph schema:

{well_known_types}

## File Previews

Structure-aware previews of the approved markdown files are shown below.
Each preview shows the document's heading structure with the first few
lines of each section. Use these to understand what kinds of entities
appear across the entire document.

You can use the sample_file tool to read more content from a specific
section when the preview is not sufficient. The user may also ask you
to look deeper into files or sections you did not consider.

{file_context}

## How to Identify Entity Types

There are two approaches:

1. Well-known entities (ALWAYS include these):
   - The well-known types listed above come from the existing graph schema.
   - If those types of entities appear in the text, always include them.
   - These bridge unstructured text to the structured graph.
   - Example: If "Product" is a well-known type and products are mentioned
     in reviews, include "Product".

2. Discovered entities:
   - Look for categories of things consistently mentioned across files
     that support the user's goal.
   - Focus on entities that add depth or breadth to the existing graph.
   - Example: If the goal is root cause analysis and the graph has "Product"
     nodes, discovered types like "Issue" or "Feature" add analytical depth.
   - Example: If the goal is social communities and the graph has "Person"
     nodes, discovered types like "Hobby" or "Event" add breadth.

## What NOT to Propose

- Quantities or measurements: "Rating", "Price", "Age", "Count" are
  properties on an entity, not entities themselves. For example, "Age"
  is better represented as a property on "Person", not as its own type.
- Overly specific types: Prefer "Issue" over "BrokenLeg". Capture the
  pattern, not the instance.
- Types that don't support the stated goal: Every proposed type must
  have a clear connection to what the user wants to achieve.

## Disambiguation

Be aware that a word can mean different things in different contexts.
For example, "Assembly" may be a component type in the graph schema
(a subassembly of a product) and also appear in reviews as the process
of assembling furniture. These are different concepts. When in doubt,
clarify with the user.

## Quality Guidelines

- Entity types should be singular nouns in PascalCase (e.g., "ProductIssue")
- Prefer reusing well-known types over creating new ones
- Quality over quantity: 3 to 6 meaningful types is better than 12 vague ones
- Every proposed type should clearly support the user's goal
- For each proposed type, explain what it is and why it's relevant

## Transparency

Always be transparent about your analysis process. Start your response
by summarizing what you analyzed before presenting your proposal:
- How many files you reviewed and how many sections across them
- Which well-known types you found in the text
- What patterns you noticed that led to discovered types
- What you considered but excluded, and why (e.g., "I excluded Rating
  because it's a quantity, not an entity")
- If you used sample_file, explain what you read and what it revealed

The user should never wonder what you did or what you looked at.

## Workflow

1. Review the user goal, well-known types, and file previews above
2. If any section preview is truncated or unclear, use sample_file
   to read more content (line numbers are provided in the previews)
3. Identify which well-known types appear in the text
4. Discover additional types that support the user's goal
5. Propose the combined list using set_proposed_entities
6. Present each type with:
   - Whether it's well-known or discovered
   - What it represents
   - Why it supports the goal
   - An example mention from the text
7. Wait for user feedback - iterate if they want changes
8. If the user asks you to look deeper into a file or section, use
   sample_file and reconsider your proposal based on what you find
9. Only call approve_proposed_entities when the user explicitly approves
```

## Tools

Context-gathering tools (`get_approved_user_goal`, `get_approved_files`,
`get_well_known_types`) are replaced by pre-computation. The agent
keeps `sample_file` as an optional tool for reading deeper into files
when the pre-computed preview is not sufficient.

### sample_file (collaborative, imported from file_tools)

Read more content from a specific file. Can be used in two ways:
- **Agent-initiated**: When a section preview is truncated or insufficient
  to identify entity types
- **User-directed**: When the user asks the agent to look deeper into
  a file or section the agent did not consider

```python
# Reused from tools/file_tools.py - no new implementation needed.
# Schema and handler are imported.
```

### set_proposed_entities

Save the proposed entity types with source and description metadata.

```python
TOOL_SCHEMA = {
    "name": "set_proposed_entities",
    "description": "Save the proposed list of entity types to extract from text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_types": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Entity type name in PascalCase (e.g., 'Product', 'Issue')"
                        },
                        "source": {
                            "type": "string",
                            "enum": ["well_known", "discovered"],
                            "description": "Whether the type comes from the existing graph schema or was discovered in the text"
                        },
                        "description": {
                            "type": "string",
                            "description": "What this entity type represents and why it's relevant to the goal"
                        }
                    },
                    "required": ["name", "source", "description"]
                },
                "description": "List of entity type definitions"
            }
        },
        "required": ["entity_types"]
    }
}

def handle_set_proposed_entities(state: dict, entity_types: list) -> dict:
    result = {}
    for et in entity_types:
        name = et["name"]
        # Validate PascalCase
        if not name[0].isupper():
            return {
                "status": "error",
                "message": f"Entity type '{name}' should be in PascalCase (e.g., 'ProductIssue')"
            }
        # Validate source
        if et["source"] not in ("well_known", "discovered"):
            return {
                "status": "error",
                "message": f"Source for '{name}' must be 'well_known' or 'discovered'"
            }
        result[name] = {
            "source": et["source"],
            "description": et["description"]
        }

    state["proposed_entity_types"] = result
    return {
        "status": "success",
        "message": f"Proposed {len(result)} entity types. Present to user for approval.",
        "proposed_entity_types": result
    }
```

### get_proposed_entities

Retrieve current proposal.

```python
TOOL_SCHEMA = {
    "name": "get_proposed_entities",
    "description": "Get the currently proposed entity types.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

def handle_get_proposed_entities(state: dict) -> dict:
    return {
        "status": "success",
        "proposed_entity_types": state.get("proposed_entity_types", {})
    }
```

### approve_proposed_entities

Finalize after user approval.

```python
TOOL_SCHEMA = {
    "name": "approve_proposed_entities",
    "description": "Finalize entity types after user explicitly approves. Only use when user explicitly says to approve.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

def handle_approve_proposed_entities(state: dict) -> dict:
    if "proposed_entity_types" not in state or not state["proposed_entity_types"]:
        return {"status": "error", "message": "No proposed entities to approve."}

    # Deep copy to avoid shared references
    import copy
    state["approved_entity_types"] = copy.deepcopy(state["proposed_entity_types"])
    return {
        "status": "success",
        "message": "Entity types approved.",
        "approved_entity_types": state["approved_entity_types"]
    }
```

## Example Conversation

```
User: Analyze the product reviews and propose entity types for extraction.

Agent: I've reviewed your goal, the existing graph schema, and previews of
all 10 markdown files. Here's what I found:

**Well-known types from the graph schema:**
Product, Assembly, Part, Supplier

Looking at the file previews, I can see the reviews contain:
- Product names (matches existing "Product" type)
- Reviewer usernames
- Ratings (numeric - this is a property, not an entity)
- Issues mentioned: quality problems, assembly difficulty, reliability
- Product features: design, materials, functionality

"Assembly" appears in reviews but refers to the process of assembling
furniture, not the component type in your graph schema. I'll exclude it
to avoid confusion.

Based on your root cause analysis goal, I propose these entity types:

[Calls set_proposed_entities([
    {"name": "Product", "source": "well_known", "description": "Products mentioned in reviews, bridges to existing Product nodes"},
    {"name": "Issue", "source": "discovered", "description": "Problems reported by reviewers that support root cause analysis"},
    {"name": "Feature", "source": "discovered", "description": "Product characteristics, useful for understanding which features cause issues"}
])]

**Proposed Entity Types:**

1. **Product** (well-known) - Products mentioned in reviews, bridges
   review data to existing Product nodes in the graph.
   Example: "The Gothenburg Table arrived with scratches"

2. **Issue** (discovered) - Problems reported by reviewers that support
   root cause analysis. Consistently appears across all review files.
   Example: "wobbly legs", "missing screws", "scratched surface"

3. **Feature** (discovered) - Product characteristics mentioned in
   reviews, useful for understanding which features cause issues.
   Example: "adjustable height", "solid wood", "modern design"

I excluded Reviewer because tracking who said what doesn't directly
support root cause analysis. I excluded Rating because it's a numeric
property, not an entity.

Would you like to adjust this list?

User: Looks good, approve it.

Agent: [Calls approve_proposed_entities]

Entity types approved: Product, Issue, Feature

Next step is to define how these entities relate to each other (fact types).
```

## Success Criteria

1. Agent analyzes pre-computed file previews and well-known types (can optionally use sample_file for deeper reading)
2. Proposed types are in PascalCase
3. Agent distinguishes entities from properties (no numeric/quantitative types)
4. Agent handles disambiguation (e.g., "Assembly" as component vs process)
5. Each proposed type has clear relevance to user's goal
6. Agent explains each type with well-known/discovered classification and text examples
7. Agent iterates based on user feedback
8. Final list supports meaningful knowledge extraction

## Common Issues

1. **Including quantities as entities** - "Rating", "Price", "Count" should be properties, not entities. The prompt includes explicit guidance and examples.

2. **Confusing "Assembly" process with "Assembly" component** - The word appears in both domain (component) and text (process of assembling). The prompt includes disambiguation guidance.

3. **Too many discovered types** - Focus on types that support the stated goal. Prompt limits to 3-6 types.

4. **Missing well-known types** - Agent should always include well-known types that appear in the text. Prompt says "ALWAYS include these".
