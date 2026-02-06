# Stage 5: Fact Type Extraction Agent

## Purpose

Define how approved entity types relate to each other as subject-predicate-object triples.
These fact types guide extraction of relationships from unstructured text.

## Key Concept: Fact Triples

A fact type is a template: `(Subject, Predicate, Object)` where:
- **Subject**: An approved entity type
- **Predicate**: A relationship label describing the connection
- **Object**: An approved entity type

Example fact types:
- `(Product, HAS_ISSUE, Issue)` - Products have issues
- `(Product, HAS_FEATURE, Feature)` - Products have features
- `(Reviewer, REPORTED, Issue)` - Reviewers reported issues

## Input

```python
state["approved_user_goal"] = {...}
state["approved_files"] = [...]
state["approved_construction_plan"] = {...}
state["approved_entity_types"] = ["Product", "Issue", "Feature"]
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
    }
}
```

## Agent Instructions

```
You are a knowledge extraction specialist. Your job is to define types of facts 
(relationships) that can be extracted from text based on approved entity types.

A fact type is a triple: (Subject, Predicate, Object)
- Subject and Object MUST be from the approved entity types list
- Predicate describes how they are related
- The predicate must represent relationships that actually appear in the text

Guidelines:
1. ONLY use approved entity types as subjects and objects
2. Do NOT propose new entity types - use what's approved
3. Predicates should be lowercase_with_underscores (e.g., "has_issue")
4. Predicates should describe relationships visible in the text
5. Focus on fact types that support the user's stated goal
6. Every fact type should be extractable from the available text files

Workflow:
1. Get the approved entity types
2. Sample text files to see how entities relate
3. For each potential relationship, call add_proposed_fact
4. Present all proposed fact types to the user
5. Iterate based on feedback
6. Call approve_proposed_facts when user approves
```

## Tools

### get_approved_user_goal / get_approved_files / sample_file

Same as previous stages.

### get_approved_entities

Get the approved entity types from previous stage.

```python
TOOL_SCHEMA = {
    "name": "get_approved_entities",
    "description": "Get the approved entity types from the NER extraction stage.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

def handle_get_approved_entities(state: dict) -> dict:
    if "approved_entity_types" not in state:
        return {
            "status": "error",
            "message": "No approved entity types found. Run NER extraction first."
        }
    return {
        "status": "success",
        "approved_entity_types": state["approved_entity_types"]
    }
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
    approved_entities = state.get("approved_entity_types", [])
    
    # Validate subject is approved
    if subject_label not in approved_entities:
        return {
            "status": "error",
            "message": f"Subject '{subject_label}' is not an approved entity type. Approved: {approved_entities}"
        }
    
    # Validate object is approved
    if object_label not in approved_entities:
        return {
            "status": "error",
            "message": f"Object '{object_label}' is not an approved entity type. Approved: {approved_entities}"
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
    "description": "Finalize fact types after user explicitly approves.",
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
User: Define the fact types for our entity types

Agent: Let me see what entity types we're working with and sample the text to 
understand how they relate.

[Calls get_approved_entities]

Approved entities: Product, Issue, Feature

[Calls sample_file("product_reviews/gothenburg_table_reviews.md")]

Looking at the reviews, I can see relationships like:
- "The Gothenburg Table has scratches" → Product has Issue
- "I love the modern design" → Product has Feature  
- "The table fits perfectly in small spaces" → Product has Feature

Let me propose fact types:

[Calls add_proposed_fact("Product", "has_issue", "Issue")]
[Calls add_proposed_fact("Product", "has_feature", "Feature")]

**Proposed Fact Types:**

1. `(Product)-[has_issue]->(Issue)`
   - Example: "Gothenburg Table" has_issue "scratched surface"
   
2. `(Product)-[has_feature]->(Feature)`
   - Example: "Stockholm Chair" has_feature "ergonomic design"

These support your root cause analysis goal by connecting products to their 
reported issues and documented features.

Would you like to add, remove, or modify any fact types?

User: Can you add one that connects issues to features? Sometimes an issue is about a specific feature.

Agent: Good thinking! That would capture "the adjustable height mechanism is broken."

[Calls add_proposed_fact("Issue", "affects_feature", "Feature")]

Added:

3. `(Issue)-[affects_feature]->(Feature)`
   - Example: "broken mechanism" affects_feature "adjustable height"

Current proposal has 3 fact types. Approve?

User: Yes, looks good

Agent: [Calls approve_proposed_facts]

✅ Fact types approved!

1. (Product)-[has_issue]->(Issue)
2. (Product)-[has_feature]->(Feature)
3. (Issue)-[affects_feature]->(Feature)

All stages of schema design are complete. Ready for graph construction.
```

## Success Criteria

1. Agent only uses approved entity types (validation in tools)
2. Predicates follow lowercase_with_underscores convention
3. Fact types are grounded in actual text content (agent samples files)
4. Each fact type supports the user's stated goal
5. Agent can iterate: add, remove, modify based on feedback
6. Final fact types provide meaningful knowledge extraction patterns

## Common Issues

1. **Using non-approved entities** - Tool validation catches this, but agent should check first.

2. **Vague predicates** - "related_to" is too vague. Encourage specific predicates like "has_issue", "caused_by".

3. **Predicates not in text** - Agent should verify relationships actually appear in the content.

4. **Missing direction consideration** - `(A)-[r]->(B)` vs `(B)-[r]->(A)` matters. Agent should think about directionality.
