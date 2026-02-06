# Stage 4: Named Entity Recognition (NER) Agent

## Purpose

Analyze unstructured data files (markdown) and propose entity types that can be extracted.
These entities will form the Subject Graph that bridges to the Domain Graph.

## Key Concept: Two Types of Entities

1. **Well-known entities**: Match existing node labels from the construction plan
   - Example: "Product" already exists in the domain graph
   - We want to find mentions of products in the text

2. **Discovered entities**: New types found in the text that support the user's goal
   - Example: "Issue", "Feature", "Reviewer" found in product reviews
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
state["approved_entity_types"] = [
    "Product",   # Well-known (from construction plan)
    "Issue",     # Discovered
    "Feature",   # Discovered
    "Reviewer"   # Discovered
]
```

## Agent Instructions

```
You are a named entity recognition specialist. Your job is to analyze text files and 
identify the types of entities that could be extracted for a knowledge graph.

Entity types are categories of people, places, things, and qualities - NOT individual instances.
For example: "Product" is an entity type, "Gothenburg Table" is an instance.

Two approaches to finding entity types:

1. Well-known entities (ALWAYS include these):
   - Check the approved construction plan for existing node labels
   - If those entities appear in the text, include them
   - Example: If "Product" nodes exist and products are mentioned in reviews, include "Product"

2. Discovered entities:
   - Look for consistent patterns in the text that support the user's goal
   - Focus on entities that would provide useful connections
   - Avoid quantities (prices, counts) - those are properties, not entities
   - Example: For root cause analysis, "Issue" and "Feature" are useful entity types

Guidelines:
- Entity types should be singular nouns in PascalCase
- Prefer reusing existing types over creating new ones
- Every proposed type should clearly support the user's goal
- Quality over quantity - fewer meaningful types is better than many vague ones

Workflow:
1. Get the approved goal, files, and construction plan
2. Identify well-known types from the construction plan
3. Sample the markdown files to discover additional entity types
4. Propose the combined list using set_proposed_entities
5. Explain each entity type and why it's relevant
6. Get user approval before finalizing
```

## Tools

### get_approved_user_goal / get_approved_files / sample_file

Same as previous stages.

### get_well_known_types

Extract existing node labels from the construction plan.

```python
TOOL_SCHEMA = {
    "name": "get_well_known_types",
    "description": "Get existing node labels from the construction plan that could be entity types.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

def handle_get_well_known_types(state: dict) -> dict:
    construction_plan = state.get("approved_construction_plan", {})
    
    # Extract labels from node constructions
    well_known = [
        entry["label"] 
        for entry in construction_plan.values() 
        if entry.get("construction_type") == "node"
    ]
    
    return {
        "status": "success",
        "well_known_types": well_known,
        "count": len(well_known)
    }
```

### set_proposed_entities

Save the proposed entity type list.

```python
TOOL_SCHEMA = {
    "name": "set_proposed_entities",
    "description": "Save the proposed list of entity types to extract from text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of entity type names in PascalCase"
            }
        },
        "required": ["entity_types"]
    }
}

def handle_set_proposed_entities(state: dict, entity_types: list) -> dict:
    # Validate PascalCase
    for et in entity_types:
        if not et[0].isupper():
            return {
                "status": "error",
                "message": f"Entity type '{et}' should be in PascalCase (e.g., 'ProductIssue')"
            }
    
    state["proposed_entity_types"] = entity_types
    return {
        "status": "success",
        "message": f"Proposed {len(entity_types)} entity types. Present to user for approval.",
        "proposed_entity_types": entity_types
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
        "proposed_entity_types": state.get("proposed_entity_types", [])
    }
```

### approve_proposed_entities

Finalize after user approval.

```python
TOOL_SCHEMA = {
    "name": "approve_proposed_entities",
    "description": "Finalize entity types after user explicitly approves.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

def handle_approve_proposed_entities(state: dict) -> dict:
    if "proposed_entity_types" not in state:
        return {"status": "error", "message": "No proposed entities to approve."}
    
    state["approved_entity_types"] = state["proposed_entity_types"].copy()
    return {
        "status": "success",
        "message": "Entity types approved.",
        "approved_entity_types": state["approved_entity_types"]
    }
```

## Example Conversation

```
User: What entities can we extract from the product reviews?

Agent: Let me analyze the reviews in context of your goal. First, I'll check what 
entity types already exist in your graph schema.

[Calls get_approved_user_goal]
[Calls get_well_known_types]

Existing node types: Product, Assembly, Part, Supplier

Now let me sample some review files to discover additional entity types.

[Calls sample_file("product_reviews/gothenburg_table_reviews.md")]

I can see the reviews contain:
- Product names (matches existing "Product" type)
- Reviewer usernames
- Ratings (numeric - this is a property, not an entity)
- Issues mentioned (quality problems, assembly difficulty)
- Product features (design, materials, functionality)

Based on your root cause analysis goal, I propose these entity types:

[Calls set_proposed_entities(["Product", "Issue", "Feature", "Reviewer"])]

**Proposed Entity Types:**

1. **Product** (well-known) - Products mentioned in reviews
2. **Issue** (discovered) - Problems reported: "wobbly legs", "missing screws", "scratched surface"
3. **Feature** (discovered) - Product characteristics: "adjustable height", "solid wood", "modern design"
4. **Reviewer** (discovered) - People who wrote reviews

I excluded Location because it doesn't strongly support root cause analysis.

Would you like to adjust this list?

User: Looks good, but don't include Reviewer - we don't need to track who said what

Agent: Good point. Let me update:

[Calls set_proposed_entities(["Product", "Issue", "Feature"])]

Updated list:
1. **Product** - Products mentioned in reviews
2. **Issue** - Problems reported in reviews  
3. **Feature** - Product characteristics mentioned

Approve this?

User: Yes

Agent: [Calls approve_proposed_entities]

✅ Entity types approved: Product, Issue, Feature

Next step is to define how these entities relate to each other (fact types).
```

## Success Criteria

1. Agent retrieves existing well-known types from construction plan
2. Agent samples multiple markdown files to understand content
3. Proposed types are in PascalCase
4. Agent distinguishes entities from properties (no numeric/quantitative types)
5. Each proposed type has clear relevance to user's goal
6. Agent iterates based on user feedback
7. Final list supports meaningful knowledge extraction

## Common Issues

1. **Including quantities as entities** - "Rating", "Price", "Count" should be properties, not entities. Add explicit instruction.

2. **Confusing "Assembly" process with "Assembly" component** - The word appears in both domain (component) and text (process of assembling). Clarify in instructions.

3. **Too many discovered types** - Focus on types that support the stated goal. Fewer is better.

4. **Missing well-known types** - Agent should always include well-known types that appear in the text.
