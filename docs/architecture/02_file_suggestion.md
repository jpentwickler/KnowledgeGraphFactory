# Stage 2: File Suggestion Agent

## Purpose

Identify and recommend data files that are relevant for building the knowledge graph.
Analyzes file structure and content to suggest which files to include.

## Input

```python
state["approved_user_goal"] = {
    "kind_of_graph": "supply chain analysis",
    "graph_description": "..."
}
```

Plus access to file system (CSV files, markdown files in a configured directory).

## Output

```python
state["approved_files"] = [
    "products.csv",
    "assemblies.csv",
    "parts.csv",
    "suppliers.csv",
    "part_supplier_mapping.csv",
    "product_reviews/gothenburg_table_reviews.md",
    "product_reviews/stockholm_chair_reviews.md",
    # ... more files
]
```

## Agent Instructions

```
You are a data analyst helping to identify relevant files for knowledge graph construction.

Your job is to:
1. Understand the user's goal (from the approved_user_goal in context)
2. Explore available files using the list_available_files tool
3. Sample file contents using the sample_file tool to understand their structure
4. Propose a list of files that would be useful for the knowledge graph
5. Get user approval before finalizing

Guidelines:
- For structured data (CSV), look at column headers to understand content
- For unstructured data (markdown, text), sample content to assess relevance
- Explain WHY each file is relevant to the user's goal
- Group files logically (e.g., "structured data files", "review documents")
```

## Tools

### get_approved_user_goal

Retrieves the approved goal from state.

```python
TOOL_SCHEMA = {
    "name": "get_approved_user_goal",
    "description": "Get the approved user goal that defines what kind of knowledge graph we're building.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

def handle_get_approved_user_goal(state: dict) -> dict:
    if "approved_user_goal" not in state:
        return {
            "status": "error",
            "message": "No approved user goal found. Run the User Intent Agent first."
        }
    return {
        "status": "success",
        "approved_user_goal": state["approved_user_goal"]
    }
```

### list_available_files

Lists files in the data directory.

```python
TOOL_SCHEMA = {
    "name": "list_available_files",
    "description": "List all available data files that could be used for knowledge graph construction.",
    "input_schema": {
        "type": "object",
        "properties": {
            "file_type": {
                "type": "string",
                "enum": ["all", "csv", "markdown", "json"],
                "description": "Filter by file type. Default is 'all'."
            }
        },
        "required": []
    }
}

def handle_list_available_files(state: dict, file_type: str = "all") -> dict:
    import os
    from pathlib import Path
    
    data_dir = os.environ.get("NEO4J_IMPORT_DIR", "./data")
    files = []
    
    for root, dirs, filenames in os.walk(data_dir):
        for filename in filenames:
            rel_path = os.path.relpath(os.path.join(root, filename), data_dir)
            
            if file_type == "all":
                files.append(rel_path)
            elif file_type == "csv" and filename.endswith(".csv"):
                files.append(rel_path)
            elif file_type == "markdown" and filename.endswith(".md"):
                files.append(rel_path)
            elif file_type == "json" and filename.endswith(".json"):
                files.append(rel_path)
    
    return {
        "status": "success",
        "files": sorted(files),
        "count": len(files)
    }
```

### sample_file

Reads the first N lines of a file to preview content.

```python
TOOL_SCHEMA = {
    "name": "sample_file",
    "description": "Read a sample of a file's content to understand its structure and relevance.",
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file (relative to data directory)"
            },
            "num_lines": {
                "type": "integer",
                "description": "Number of lines to sample. Default is 10.",
                "default": 10
            }
        },
        "required": ["file_path"]
    }
}

def handle_sample_file(state: dict, file_path: str, num_lines: int = 10) -> dict:
    import os
    
    data_dir = os.environ.get("NEO4J_IMPORT_DIR", "./data")
    full_path = os.path.join(data_dir, file_path)
    
    if not os.path.exists(full_path):
        return {
            "status": "error",
            "message": f"File not found: {file_path}"
        }
    
    try:
        with open(full_path, 'r') as f:
            lines = []
            for i, line in enumerate(f):
                if i >= num_lines:
                    break
                lines.append(line.rstrip())
        
        return {
            "status": "success",
            "file_path": file_path,
            "content": "\n".join(lines),
            "lines_sampled": len(lines)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error reading file: {str(e)}"
        }
```

### set_suggested_files

Saves the proposed list of files.

```python
TOOL_SCHEMA = {
    "name": "set_suggested_files",
    "description": "Save the list of suggested files for knowledge graph construction.",
    "input_schema": {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of file paths to include"
            }
        },
        "required": ["files"]
    }
}

def handle_set_suggested_files(state: dict, files: list) -> dict:
    state["proposed_files"] = files
    return {
        "status": "success",
        "message": f"Saved {len(files)} suggested files. Present to user for approval.",
        "suggested_files": files
    }
```

### approve_suggested_files

Finalizes the file list after user approval.

```python
TOOL_SCHEMA = {
    "name": "approve_suggested_files",
    "description": "Finalize the suggested files after user approval. Only call when user explicitly approves.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

def handle_approve_suggested_files(state: dict) -> dict:
    if "proposed_files" not in state:
        return {
            "status": "error",
            "message": "No files have been suggested yet. Use set_suggested_files first."
        }
    
    state["approved_files"] = state["proposed_files"]
    return {
        "status": "success",
        "message": "Files approved.",
        "approved_files": state["approved_files"]
    }
```

## Example Conversation

```
User: What files can we use for the knowledge graph?

Agent: Let me first check what goal we're working towards, then explore the available files.

[Calls get_approved_user_goal]
[Calls list_available_files]

I found several files. Based on your goal of building a supply chain graph for root cause analysis, 
let me examine the relevant ones:

[Calls sample_file("products.csv")]
[Calls sample_file("suppliers.csv")]
[Calls sample_file("product_reviews/gothenburg_table_reviews.md")]

Here's what I found:

**Structured Data (CSV):**
- `products.csv` - Contains product IDs, names, prices, descriptions
- `assemblies.csv` - Assembly components with product references
- `parts.csv` - Individual parts with assembly references  
- `suppliers.csv` - Supplier information
- `part_supplier_mapping.csv` - Links parts to their suppliers

**Unstructured Data (Markdown):**
- `product_reviews/*.md` - 10 review files with customer feedback

These files together can build your supply chain graph with review analysis.

[Calls set_suggested_files with all relevant files]

Should I include all of these, or would you like to adjust the selection?

User: Yes, include all of them

Agent: [Calls approve_suggested_files]

✅ Files approved! Here's the final list:
- 5 CSV files for structured data
- 10 markdown files for product reviews

Ready to proceed to schema design.
```

## Test Script Outline

```python
# tests/test_02_file_suggestion.py

import asyncio
import json
from agents.file_suggestion import FileSuggestionAgent

async def main():
    # Load state from previous stage
    try:
        with open("state_after_stage_1.json") as f:
            state = json.load(f)
        print("Loaded state from stage 1")
    except FileNotFoundError:
        # Use default state for testing
        state = {
            "approved_user_goal": {
                "kind_of_graph": "supply chain analysis",
                "graph_description": "A multi-level BOM for furniture manufacturing with product reviews for root cause analysis."
            }
        }
        print("Using default test state")
    
    agent = FileSuggestionAgent()
    
    print("=" * 60)
    print("FILE SUGGESTION AGENT - Interactive Test")
    print("=" * 60)
    print(f"\nGoal: {state['approved_user_goal']['kind_of_graph']}")
    print("Commands: 'state' = show state, 'quit' = exit\n")
    
    while True:
        user_input = input("You: ").strip()
        
        if user_input.lower() == 'quit':
            break
        if user_input.lower() == 'state':
            print(json.dumps(state, indent=2))
            continue
        if not user_input:
            continue
            
        response, state = await agent.run(user_input, state)
        print(f"\nAgent: {response}\n")
        
        if "approved_files" in state:
            print("=" * 60)
            print("✅ SUCCESS: Files approved!")
            print("=" * 60)
            for f in state["approved_files"]:
                print(f"  - {f}")
            
            save = input("\nSave state for next stage? (y/n): ")
            if save.lower() == 'y':
                with open("state_after_stage_2.json", "w") as f:
                    json.dump(state, f, indent=2)
                print("Saved to state_after_stage_2.json")
            break

if __name__ == "__main__":
    asyncio.run(main())
```

## Success Criteria

1. Agent retrieves and understands the approved user goal
2. Agent explores files systematically (list → sample → understand)
3. Agent explains relevance of each suggested file
4. Agent groups files logically in presentation
5. Agent waits for explicit approval before finalizing
6. Final list includes all necessary files for the graph

## Common Issues

1. **Agent doesn't check user goal first** - Add instruction to always start by checking the goal

2. **Agent samples too many files** - Add guidance on sampling strategy (sample representatives, not all)

3. **Agent suggests irrelevant files** - Add instruction to explain relevance to the stated goal

4. **Missing files** - Ensure NEO4J_IMPORT_DIR environment variable points to correct location
