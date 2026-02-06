# Stage 3: Schema Proposal Agent

## Purpose

Design the graph schema (node types, relationship types) based on the approved files.
This is the most complex stage, involving iterative refinement.

## Complexity Note

In the Google ADK training, this stage uses a **LoopAgent** pattern with three sub-agents:
1. Schema Proposal Agent - proposes schema
2. Schema Critic Agent - validates proposal
3. Coordinator - decides when to stop iterating

**For our pure Python implementation, we have two options:**

### Option A: Human-as-Critic (Recommended for first implementation)
- Single agent proposes schema
- Human reviews and provides feedback
- Agent iterates based on feedback
- Simpler to implement, more control

### Option B: Automated Critic Loop (Advanced)
- Proposal agent proposes
- Critic agent validates
- Loop until valid or max iterations
- More autonomous, less human oversight

**This spec covers Option A. Option B is documented in `docs/03b_schema_loop.md`.**

## Input

```python
state["approved_user_goal"] = {...}
state["approved_files"] = ["products.csv", "suppliers.csv", ...]
```

## Output

```python
state["approved_construction_plan"] = {
    "Product": {
        "construction_type": "node",
        "source_file": "products.csv",
        "label": "Product",
        "unique_column_name": "product_id",
        "properties": ["product_name", "price", "description"]
    },
    "Supplier": {
        "construction_type": "node",
        "source_file": "suppliers.csv",
        "label": "Supplier",
        "unique_column_name": "supplier_id",
        "properties": ["name", "specialty", "city", "country"]
    },
    "SUPPLIED_BY": {
        "construction_type": "relationship",
        "source_file": "part_supplier_mapping.csv",
        "relationship_type": "SUPPLIED_BY",
        "from_node_label": "Part",
        "from_node_column": "part_id",
        "to_node_label": "Supplier",
        "to_node_column": "supplier_id",
        "properties": ["lead_time_days", "unit_cost"]
    }
}
```

## Agent Instructions

```
You are a knowledge graph schema designer. Your job is to analyze CSV files and propose 
a graph schema that will represent the data effectively.

For each CSV file, determine:
- Should it become nodes, relationships, or both?
- What should the node label or relationship type be?
- Which column uniquely identifies each row?
- What properties should be included?

Schema Design Rules:
1. Node labels should be singular nouns in PascalCase (Product, not Products)
2. Relationship types should be SCREAMING_SNAKE_CASE (SUPPLIED_BY, PART_OF)
3. Every node type needs a unique identifier column
4. Relationships need from_node and to_node references
5. Consider the user's goal when deciding what to include

Workflow:
1. Get the approved user goal and files
2. Sample each CSV file to understand its structure
3. For each file, use propose_node_construction or propose_relationship_construction
4. Use search_file to validate that referenced columns exist
5. Present the complete proposal to the user
6. If user requests changes, use remove_construction to remove items and re-propose
7. When user approves, call approve_construction_plan
```

## Tools

### get_approved_user_goal / get_approved_files

Same as Stage 2 - retrieve context from state.

### sample_file

Same as Stage 2 - preview file content.

### search_file

Search for patterns in a file (like grep). Useful to validate column names exist.

```python
TOOL_SCHEMA = {
    "name": "search_file",
    "description": "Search for a pattern in a file. Useful to verify column names or data patterns.",
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file"
            },
            "pattern": {
                "type": "string",
                "description": "Text pattern to search for"
            }
        },
        "required": ["file_path", "pattern"]
    }
}

def handle_search_file(state: dict, file_path: str, pattern: str) -> dict:
    import os
    import re
    
    data_dir = os.environ.get("NEO4J_IMPORT_DIR", "./data")
    full_path = os.path.join(data_dir, file_path)
    
    matches = []
    try:
        with open(full_path, 'r') as f:
            for i, line in enumerate(f):
                if re.search(pattern, line, re.IGNORECASE):
                    matches.append({"line": i + 1, "content": line.strip()})
                if len(matches) >= 10:  # Limit results
                    break
        
        return {
            "status": "success",
            "pattern": pattern,
            "matches": matches,
            "found": len(matches) > 0
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

### propose_node_construction

Propose how a CSV file should be converted to nodes.

```python
TOOL_SCHEMA = {
    "name": "propose_node_construction",
    "description": "Propose that a CSV file should be converted to graph nodes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Unique name for this construction rule (usually same as label)"
            },
            "source_file": {
                "type": "string",
                "description": "CSV file path"
            },
            "label": {
                "type": "string",
                "description": "Node label in PascalCase"
            },
            "unique_column_name": {
                "type": "string",
                "description": "Column that uniquely identifies each row"
            },
            "properties": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of columns to include as node properties"
            }
        },
        "required": ["name", "source_file", "label", "unique_column_name", "properties"]
    }
}

def handle_propose_node_construction(state: dict, name: str, source_file: str, 
                                     label: str, unique_column_name: str, 
                                     properties: list) -> dict:
    if "proposed_construction_plan" not in state:
        state["proposed_construction_plan"] = {}
    
    state["proposed_construction_plan"][name] = {
        "construction_type": "node",
        "source_file": source_file,
        "label": label,
        "unique_column_name": unique_column_name,
        "properties": properties
    }
    
    return {
        "status": "success",
        "message": f"Node construction '{name}' added to proposal.",
        "construction": state["proposed_construction_plan"][name]
    }
```

### propose_relationship_construction

Propose how a CSV file should be converted to relationships.

```python
TOOL_SCHEMA = {
    "name": "propose_relationship_construction",
    "description": "Propose that a CSV file should be used to create relationships between nodes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Unique name for this construction rule"
            },
            "source_file": {
                "type": "string",
                "description": "CSV file path"
            },
            "relationship_type": {
                "type": "string",
                "description": "Relationship type in SCREAMING_SNAKE_CASE"
            },
            "from_node_label": {
                "type": "string",
                "description": "Label of the source node"
            },
            "from_node_column": {
                "type": "string",
                "description": "Column containing the source node ID"
            },
            "to_node_label": {
                "type": "string",
                "description": "Label of the target node"
            },
            "to_node_column": {
                "type": "string",
                "description": "Column containing the target node ID"
            },
            "properties": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of columns to include as relationship properties"
            }
        },
        "required": ["name", "source_file", "relationship_type", 
                     "from_node_label", "from_node_column",
                     "to_node_label", "to_node_column"]
    }
}

def handle_propose_relationship_construction(state: dict, name: str, source_file: str,
                                             relationship_type: str,
                                             from_node_label: str, from_node_column: str,
                                             to_node_label: str, to_node_column: str,
                                             properties: list = None) -> dict:
    if "proposed_construction_plan" not in state:
        state["proposed_construction_plan"] = {}
    
    state["proposed_construction_plan"][name] = {
        "construction_type": "relationship",
        "source_file": source_file,
        "relationship_type": relationship_type,
        "from_node_label": from_node_label,
        "from_node_column": from_node_column,
        "to_node_label": to_node_label,
        "to_node_column": to_node_column,
        "properties": properties or []
    }
    
    return {
        "status": "success",
        "message": f"Relationship construction '{name}' added to proposal.",
        "construction": state["proposed_construction_plan"][name]
    }
```

### remove_construction

Remove a proposed construction rule.

```python
TOOL_SCHEMA = {
    "name": "remove_construction",
    "description": "Remove a construction rule from the proposal.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the construction rule to remove"
            }
        },
        "required": ["name"]
    }
}

def handle_remove_construction(state: dict, name: str) -> dict:
    if "proposed_construction_plan" not in state:
        return {"status": "error", "message": "No construction plan exists."}
    
    if name not in state["proposed_construction_plan"]:
        return {"status": "error", "message": f"Construction '{name}' not found."}
    
    del state["proposed_construction_plan"][name]
    return {"status": "success", "message": f"Removed '{name}' from proposal."}
```

### get_proposed_construction_plan

Retrieve the current proposal for display.

```python
TOOL_SCHEMA = {
    "name": "get_proposed_construction_plan",
    "description": "Get the current proposed construction plan to review or present to user.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

def handle_get_proposed_construction_plan(state: dict) -> dict:
    plan = state.get("proposed_construction_plan", {})
    return {
        "status": "success",
        "proposed_construction_plan": plan,
        "node_count": sum(1 for v in plan.values() if v["construction_type"] == "node"),
        "relationship_count": sum(1 for v in plan.values() if v["construction_type"] == "relationship")
    }
```

### approve_construction_plan

Finalize after user approval.

```python
TOOL_SCHEMA = {
    "name": "approve_construction_plan",
    "description": "Finalize the construction plan after user explicitly approves.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

def handle_approve_construction_plan(state: dict) -> dict:
    if "proposed_construction_plan" not in state:
        return {"status": "error", "message": "No proposed plan to approve."}
    
    if not state["proposed_construction_plan"]:
        return {"status": "error", "message": "Proposed plan is empty."}
    
    state["approved_construction_plan"] = state["proposed_construction_plan"].copy()
    return {
        "status": "success",
        "message": "Construction plan approved.",
        "approved_construction_plan": state["approved_construction_plan"]
    }
```

## Example Conversation

```
User: Design the schema for our supply chain graph

Agent: I'll analyze the approved files and design a schema. Let me start by examining each file.

[Calls get_approved_user_goal]
[Calls get_approved_files]
[Calls sample_file("products.csv")]

Products.csv has columns: product_id, product_name, price, description
This should be a Product node.

[Calls propose_node_construction(
    name="Product",
    source_file="products.csv",
    label="Product",
    unique_column_name="product_id",
    properties=["product_name", "price", "description"]
)]

[Continues analyzing other files...]

Here's my proposed schema:

**Nodes:**
1. Product (from products.csv) - id: product_id
2. Assembly (from assemblies.csv) - id: assembly_id
3. Part (from parts.csv) - id: part_id
4. Supplier (from suppliers.csv) - id: supplier_id

**Relationships:**
1. Product -[CONTAINS]-> Assembly (from assemblies.csv)
2. Assembly -[HAS_PART]-> Part (from parts.csv)
3. Part -[SUPPLIED_BY]-> Supplier (from part_supplier_mapping.csv)

This creates a hierarchy: Product → Assembly → Part → Supplier

Does this look correct? Would you like any changes?

User: The relationship should be PART_OF not HAS_PART, and direction should be Assembly -[PART_OF]-> Product

Agent: You're right, let me fix that.

[Calls remove_construction("CONTAINS")]
[Calls propose_relationship_construction with corrected direction and name]

Updated schema shows Assembly -[PART_OF]-> Product.

Is this better?

User: Yes, approve it

Agent: [Calls approve_construction_plan]

✅ Construction plan approved!

- 4 node types: Product, Assembly, Part, Supplier
- 3 relationship types: PART_OF, HAS_PART, SUPPLIED_BY

Ready for entity extraction from unstructured data.
```

## Success Criteria

1. Agent analyzes ALL approved CSV files
2. Agent validates column names exist before proposing
3. Schema follows naming conventions (PascalCase nodes, SCREAMING_SNAKE_CASE relationships)
4. Every node type has a unique identifier
5. Relationships correctly reference existing node types
6. Agent iterates based on user feedback
7. Final schema is logically complete for the stated goal

## Common Issues

1. **Missing relationships** - Agent may create nodes but forget relationships. Instruction should emphasize completeness.

2. **Wrong relationship direction** - Common mistake. Agent should state direction clearly and confirm with user.

3. **Column name typos** - Use search_file to validate columns exist before proposing.

4. **Inconsistent naming** - Add validation in tool handlers for naming conventions.
