# Stage 5: Fact Type Extraction Agent

## Purpose

Define how approved entity types relate to each other as subject-predicate-object triples.
These fact types guide extraction of relationships from unstructured text.

## Key Concept: Fact Triples

A fact type is a template, not a specific fact:
- `(Product, has_issue, Issue)` - a type of fact (template)
- `"Gothenburg Table has wobbly legs"` - a specific fact (instance)

The agent proposes **types**, not instances.

A fact type is a triple: `(Subject, Predicate, Object)` where:
- **Subject**: An approved entity type
- **Predicate**: A relationship label describing the connection
- **Object**: An approved entity type

Example fact types:
- `(Product, has_issue, Issue)` - Products have issues
- `(Product, has_feature, Feature)` - Products have features
- `(Issue, affects_feature, Feature)` - Issues relate to specific features

## Input

```python
state["approved_user_goal"] = {...}
state["approved_files"] = [...]
state["approved_construction_plan"] = {...}
state["approved_entity_types"] = {
    "Product": {"source": "well_known", "description": "..."},
    "Issue": {"source": "discovered", "description": "..."},
    "Feature": {"source": "discovered", "description": "..."}
}
```

## Output

```python
state["approved_fact_types"] = {
    "has_issue": {
        "subject_label": "Product",
        "predicate_label": "has_issue",
        "object_label": "Issue"
    },
    "has_feature": {
        "subject_label": "Product",
        "predicate_label": "has_feature",
        "object_label": "Feature"
    },
    "affects_feature": {
        "subject_label": "Issue",
        "predicate_label": "affects_feature",
        "object_label": "Feature"
    }
}
```

## Pre-computation Pattern

Like the NER agent, the Fact Extraction agent uses pre-computed context
injected into the system prompt.

### Reused from NER agent

- `build_markdown_context(state)` - Structure-aware file previews (same function).
  Parses markdown heading structure and extracts the first few lines of each
  section, giving the agent visibility into every part of the document.

### `build_entity_types_context(state)`

Formats approved entity types (now a dict with metadata) for injection:

```python
def build_entity_types_context(state: dict) -> str:
    """Format approved entity types for system prompt injection."""
    entity_types = state.get("approved_entity_types", {})
    if not entity_types:
        return "(none)"

    lines = []
    for name, meta in entity_types.items():
        source = meta.get("source", "unknown")
        desc = meta.get("description", "")
        lines.append(f"- {name} ({source}): {desc}")
    return "\n".join(lines)
```

Both are injected into the system prompt via template placeholders:
`{user_goal}`, `{approved_entity_types}`, `{file_context}`.

## Agent Instructions

```
You are a knowledge extraction specialist working on a knowledge graph.
Your job is to define the types of facts (relationships) that can be
extracted from text based on approved entity types.

A fact type is a template, not a specific fact.
For example: "(Product, has_issue, Issue)" is a fact type.
"Gothenburg Table has wobbly legs" is a specific fact - do NOT propose these.

## User Goal

{user_goal}

## Approved Entity Types

These are the entity types approved in the previous stage.
You MUST only use these as subjects and objects. Do NOT invent new types.

{approved_entity_types}

## File Previews

Structure-aware previews of the approved markdown files are shown below.
Each preview shows the document's heading structure with the first few
lines of each section. Use these to understand how the approved entity
types relate to each other across the document.

You can use the sample_file tool to read more content from a specific
section when the preview is not sufficient. The user may also ask you
to look deeper into files or sections you did not consider.

{file_context}

## What is a Fact Type

A fact type is a triple: (Subject, Predicate, Object)

- Subject: An approved entity type
- Predicate: A relationship label describing the connection
- Object: An approved entity type

Example fact types:
- (Product, has_issue, Issue) - products have reported issues
- (Product, has_feature, Feature) - products have described features
- (Issue, affects_feature, Feature) - issues relate to specific features

## Design Rules

1. Subject and object MUST be from the approved entity types list.
   Do not propose new entity types - use what's approved.

2. The predicate must represent relationships that actually appear
   in the text. Do not guess or infer relationships that aren't there.

3. Predicates should be in lowercase_with_underscores format
   (e.g., "has_issue", "affects_feature").

4. Optimize predicates for the user's goal. Choose relationship labels
   that capture information useful for the stated purpose.

5. Avoid vague predicates like "related_to", "associated_with", or
   "connected_to". These carry no useful information. Be specific
   about what the relationship means.

6. Direction matters. Think carefully about which entity is the subject
   and which is the object.
   - (Product)-[has_issue]->(Issue) means "a product has an issue"
   - (Issue)-[found_in]->(Product) means "an issue was found in a product"
   - These capture different perspectives. Choose the direction that
     best supports the user's goal.

## Quality Guidelines

- Every fact type must be extractable from the available text
- Fewer precise fact types is better than many overlapping ones
- Each fact type should represent a distinct, meaningful relationship
- For each proposed fact type, provide an example from the text
  showing how subjects and objects relate through that predicate

## Transparency

Always be transparent about your analysis process. Start your response
by summarizing what you analyzed before presenting your proposal:
- How many files you reviewed and how many sections across them
- Which approved entity types you found co-occurring in the text
- What relationship patterns you noticed and why you chose each predicate
- What you considered but excluded, and why (e.g., "I excluded
  'related_to' because it's too vague to be useful")
- If you used sample_file, explain what you read and what it revealed
- For each fact type, explain your directionality choice

The user should never wonder what you did or what you looked at.

## Workflow

1. Review the user goal, approved entity types, and file previews above
2. If any section preview is truncated or unclear, use sample_file
   to read more content (line numbers are provided in the previews)
3. Identify how entity types relate to each other in the text
4. For each relationship, call add_proposed_fact with subject, predicate,
   and object
5. Present all proposed fact types to the user with:
   - The triple in (Subject)-[predicate]->(Object) notation
   - What the relationship means
   - Why you chose that direction
   - A concrete example from the text
6. Wait for user feedback - add, remove, or modify based on input
7. If the user asks you to look deeper into a file or section, use
   sample_file and reconsider your proposal based on what you find
8. Only call approve_proposed_facts when the user explicitly approves
```

## Tools

Context-gathering tools (`get_approved_user_goal`, `get_approved_files`,
`get_approved_entities`) are replaced by pre-computation. The agent
keeps `sample_file` as an optional tool for reading deeper into files
when the pre-computed preview is not sufficient.

### sample_file (collaborative, imported from file_tools)

Read more content from a specific file. Can be used in two ways:
- **Agent-initiated**: When a section preview is truncated or insufficient
  to identify relationship patterns
- **User-directed**: When the user asks the agent to look deeper into
  a file or section the agent did not consider

```python
# Reused from tools/file_tools.py - no new implementation needed.
# Schema and handler are imported.
```

### add_proposed_fact

Add a single fact type to the proposal.

```python
TOOL_SCHEMA = {
    "name": "add_proposed_fact",
    "description": "Add a proposed fact type (subject-predicate-object triple).",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject_label": {
                "type": "string",
                "description": "Approved entity type for the subject"
            },
            "predicate_label": {
                "type": "string",
                "description": "Relationship label in lowercase_with_underscores"
            },
            "object_label": {
                "type": "string",
                "description": "Approved entity type for the object"
            }
        },
        "required": ["subject_label", "predicate_label", "object_label"]
    }
}

def handle_add_proposed_fact(state: dict, subject_label: str,
                             predicate_label: str, object_label: str) -> dict:
    approved_entities = state.get("approved_entity_types", {})
    approved_names = list(approved_entities.keys())

    # Validate subject is approved
    if subject_label not in approved_names:
        return {
            "status": "error",
            "message": f"Subject '{subject_label}' is not an approved entity type. Approved: {approved_names}"
        }

    # Validate object is approved
    if object_label not in approved_names:
        return {
            "status": "error",
            "message": f"Object '{object_label}' is not an approved entity type. Approved: {approved_names}"
        }

    # Validate predicate format (lowercase with underscores)
    if not predicate_label.islower() or ' ' in predicate_label:
        return {
            "status": "error",
            "message": f"Predicate should be lowercase_with_underscores, got: '{predicate_label}'"
        }

    # Add to proposed facts
    if "proposed_fact_types" not in state:
        state["proposed_fact_types"] = {}

    state["proposed_fact_types"][predicate_label] = {
        "subject_label": subject_label,
        "predicate_label": predicate_label,
        "object_label": object_label
    }

    return {
        "status": "success",
        "message": f"Added fact type: ({subject_label})-[{predicate_label}]->({object_label})",
        "fact_type": state["proposed_fact_types"][predicate_label]
    }
```

### remove_proposed_fact

Remove a fact type from the proposal.

```python
TOOL_SCHEMA = {
    "name": "remove_proposed_fact",
    "description": "Remove a proposed fact type by its predicate label.",
    "input_schema": {
        "type": "object",
        "properties": {
            "predicate_label": {
                "type": "string",
                "description": "The predicate label of the fact type to remove"
            }
        },
        "required": ["predicate_label"]
    }
}

def handle_remove_proposed_fact(state: dict, predicate_label: str) -> dict:
    if "proposed_fact_types" not in state:
        return {"status": "error", "message": "No proposed facts exist."}

    if predicate_label not in state["proposed_fact_types"]:
        return {"status": "error", "message": f"Fact type '{predicate_label}' not found."}

    del state["proposed_fact_types"][predicate_label]
    return {"status": "success", "message": f"Removed fact type '{predicate_label}'."}
```

### get_proposed_facts

Get all proposed fact types.

```python
TOOL_SCHEMA = {
    "name": "get_proposed_facts",
    "description": "Get all currently proposed fact types.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

def handle_get_proposed_facts(state: dict) -> dict:
    return {
        "status": "success",
        "proposed_fact_types": state.get("proposed_fact_types", {}),
        "count": len(state.get("proposed_fact_types", {}))
    }
```

### approve_proposed_facts

Finalize after user approval.

```python
TOOL_SCHEMA = {
    "name": "approve_proposed_facts",
    "description": "Finalize fact types after user explicitly approves. Only use when user explicitly says to approve.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

def handle_approve_proposed_facts(state: dict) -> dict:
    if "proposed_fact_types" not in state or not state["proposed_fact_types"]:
        return {"status": "error", "message": "No proposed fact types to approve."}

    state["approved_fact_types"] = state["proposed_fact_types"].copy()
    return {
        "status": "success",
        "message": "Fact types approved.",
        "approved_fact_types": state["approved_fact_types"]
    }
```

## Example Conversation

```
User: Define the fact types for our entity types.

Agent: I've reviewed your goal, the approved entity types (Product, Issue,
Feature), and the file previews. Here's how these entities relate in the
text:

Looking at the reviews, I can see patterns like:
- "The Gothenburg Table has scratches" -> Product has Issue
- "I love the modern design" -> Product has Feature
- "The adjustable height mechanism is broken" -> Issue affects Feature

Let me propose fact types:

[Calls add_proposed_fact("Product", "has_issue", "Issue")]
[Calls add_proposed_fact("Product", "has_feature", "Feature")]

**Proposed Fact Types:**

1. `(Product)-[has_issue]->(Issue)`
   - A product has a reported issue
   - Example: "Gothenburg Table" has_issue "scratched surface"

2. `(Product)-[has_feature]->(Feature)`
   - A product has a described feature
   - Example: "Stockholm Chair" has_feature "ergonomic design"

These support your root cause analysis goal by connecting products to
their reported issues and documented features.

Would you like to add, remove, or modify any fact types?

User: Can you add one that connects issues to features? Sometimes an
issue is about a specific feature.

Agent: Good thinking! That would capture sentences like "the adjustable
height mechanism is broken" - linking the issue to the specific feature.

[Calls add_proposed_fact("Issue", "affects_feature", "Feature")]

Added:

3. `(Issue)-[affects_feature]->(Feature)`
   - An issue affects or relates to a specific feature
   - Example: "broken mechanism" affects_feature "adjustable height"

I chose (Issue)-[affects_feature]->(Feature) rather than the reverse
because the analysis goal is tracing from issues back to what they affect.

Current proposal has 3 fact types. Approve?

User: Yes, looks good.

Agent: [Calls approve_proposed_facts]

Fact types approved!

1. (Product)-[has_issue]->(Issue)
2. (Product)-[has_feature]->(Feature)
3. (Issue)-[affects_feature]->(Feature)

All stages of schema design are complete. Ready for graph construction.
```

## Success Criteria

1. Agent only uses approved entity types (validation in tools)
2. Predicates follow lowercase_with_underscores convention
3. Fact types are grounded in actual text content (from previews or sample_file)
4. Each fact type supports the user's stated goal
5. Agent considers and explains directionality choices
6. Agent avoids vague predicates
7. Agent can iterate: add, remove, modify based on feedback
8. Final fact types provide meaningful knowledge extraction patterns

## Common Issues

1. **Using non-approved entities** - Tool validation catches this, but agent should check first.

2. **Vague predicates** - "related_to" is too vague. The prompt explicitly warns against this and encourages specific predicates like "has_issue", "affects_feature".

3. **Predicates not in text** - Agent should verify relationships actually appear in the content. The prompt says "Do not guess."

4. **Missing direction consideration** - `(A)-[r]->(B)` vs `(B)-[r]->(A)` matters. The prompt includes directionality guidance with contrasting examples.

5. **Confusing fact types with specific facts** - Agent might propose "Gothenburg Table has wobbly legs" instead of "(Product, has_issue, Issue)". The prompt includes the ABK/coffee example to prevent this.
