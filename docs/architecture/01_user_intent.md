# Stage 1: User Intent Agent

## Purpose

Understand what kind of knowledge graph the user wants to build and why.
Produce a structured specification that downstream agents can consume.

## Input

- User conversation (natural language)
- No prior state required

## Output

```python
state["approved_user_goal"] = {
    "kind_of_graph": "supply chain analysis",
    "graph_description": "A multi-level bill of materials for manufactured products, useful for root cause analysis. Include product reviews to trace reported issues back through manufacturing."
}
```

## Agent Instructions

```
You are a knowledge graph design consultant. Your job is to understand what kind 
of knowledge graph the user wants to build and capture their requirements precisely.

Your goal is to produce a structured specification with:
- kind_of_graph: A short label (e.g., "supply chain", "social network", "product catalog")
- graph_description: A detailed description of what the graph should represent and its purpose

Workflow:
1. Ask clarifying questions to understand the user's domain and goals
2. When you have enough information, use the 'set_proposed_goal' tool to save your proposal
3. Present the proposal to the user and ask for their approval
4. If they approve, use the 'approve_proposed_goal' tool to finalize
5. If they want changes, update your proposal and ask again
```

## Tools

### set_proposed_goal

Saves the agent's proposed goal specification.

```python
TOOL_SCHEMA = {
    "name": "set_proposed_goal",
    "description": "Save the proposed knowledge graph goal. Call this when you have enough information to propose a goal specification.",
    "input_schema": {
        "type": "object",
        "properties": {
            "kind_of_graph": {
                "type": "string",
                "description": "Short label for the type of graph (e.g., 'supply chain', 'social network')"
            },
            "graph_description": {
                "type": "string", 
                "description": "Detailed description of what the graph represents and its intended use"
            }
        },
        "required": ["kind_of_graph", "graph_description"]
    }
}

def handle_set_proposed_goal(state: dict, kind_of_graph: str, graph_description: str) -> dict:
    state["proposed_user_goal"] = {
        "kind_of_graph": kind_of_graph,
        "graph_description": graph_description
    }
    return {
        "status": "success",
        "message": "Proposed goal saved. Please present it to the user for approval."
    }
```

### approve_proposed_goal

Finalizes the goal after user approval.

```python
TOOL_SCHEMA = {
    "name": "approve_proposed_goal",
    "description": "Finalize the proposed goal after the user explicitly approves it. Only call this when the user has clearly approved the proposal.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

def handle_approve_proposed_goal(state: dict) -> dict:
    if "proposed_user_goal" not in state:
        return {
            "status": "error",
            "message": "No proposed goal to approve. Use set_proposed_goal first."
        }
    
    state["approved_user_goal"] = state["proposed_user_goal"]
    return {
        "status": "success",
        "message": "Goal approved and saved.",
        "approved_user_goal": state["approved_user_goal"]
    }
```

## Example Conversation

```
User: I want to build a knowledge graph for supply chain analysis

Agent: That's a great use case! To design the right graph structure, I need to understand a bit more:

1. What industry or domain is this for? (e.g., manufacturing, retail, logistics)
2. What questions do you want the graph to answer? (e.g., find suppliers, trace defects, optimize inventory)
3. What data sources do you have available?

User: It's for furniture manufacturing. We have product data, supplier info, and assembly details. 
      We want to do root cause analysis when there are quality issues.

Agent: Perfect, that gives me a clear picture. For root cause analysis in furniture manufacturing, 
you'll want a graph that can trace from a product issue back through assemblies, parts, and suppliers.

Let me propose a goal specification:

[Calls set_proposed_goal with:
  kind_of_graph: "supply chain analysis"
  graph_description: "A multi-level bill of materials for furniture manufacturing, 
    connecting products to their assemblies, parts, and suppliers. Designed for 
    root cause analysis to trace quality issues back through the manufacturing process."]

Here's what I'm proposing:

**Kind of Graph:** Supply chain analysis

**Description:** A multi-level bill of materials for furniture manufacturing, connecting 
products to their assemblies, parts, and suppliers. Designed for root cause analysis 
to trace quality issues back through the manufacturing process.

Does this capture your needs? Would you like me to adjust anything?

User: Yes, but also add that we have product reviews we want to analyze

Agent: Good addition! Let me update the proposal:

[Calls set_proposed_goal with updated description including product reviews]

Updated proposal:

**Kind of Graph:** Supply chain analysis

**Description:** A multi-level bill of materials for furniture manufacturing, connecting 
products to their assemblies, parts, and suppliers. Includes product review analysis to 
identify quality issues from customer feedback. Designed for root cause analysis to trace 
issues back through the manufacturing process.

Does this look good?

User: Yes, approve it

Agent: [Calls approve_proposed_goal]

✅ Goal approved! Your knowledge graph specification is now finalized:

- **Kind:** supply chain analysis  
- **Description:** A multi-level bill of materials for furniture manufacturing...

The next step is to identify the data files that will feed into this graph.
```

## Test Script Outline

```python
# tests/test_01_user_intent.py

import asyncio
import json
from agents.user_intent import UserIntentAgent

async def main():
    state = {}
    agent = UserIntentAgent()
    
    print("=" * 60)
    print("USER INTENT AGENT - Interactive Test")
    print("=" * 60)
    print("\nThis agent helps define what kind of knowledge graph you want to build.")
    print("Commands: 'state' = show state, 'quit' = exit\n")
    
    while True:
        user_input = input("You: ").strip()
        
        if user_input.lower() == 'quit':
            break
        if user_input.lower() == 'state':
            print("\nCurrent State:")
            print(json.dumps(state, indent=2))
            continue
        if not user_input:
            continue
            
        response, state = await agent.run(user_input, state)
        print(f"\nAgent: {response}\n")
        
        if "approved_user_goal" in state:
            print("=" * 60)
            print("✅ SUCCESS: Goal approved!")
            print("=" * 60)
            print(json.dumps(state["approved_user_goal"], indent=2))
            
            save = input("\nSave state for next stage? (y/n): ")
            if save.lower() == 'y':
                with open("state_after_stage_1.json", "w") as f:
                    json.dump(state, f, indent=2)
                print("Saved to state_after_stage_1.json")
            break

if __name__ == "__main__":
    asyncio.run(main())
```

## Success Criteria

The agent is working correctly when:

1. It asks clarifying questions before proposing
2. It uses `set_proposed_goal` to save proposals (not just text responses)
3. It waits for explicit user approval before calling `approve_proposed_goal`
4. The final `approved_user_goal` accurately reflects the user's intent
5. The description is detailed enough for downstream agents to understand context

## Common Issues

1. **Agent approves without asking** - Add explicit instruction: "Only call approve_proposed_goal when the user explicitly says they approve"

2. **Proposals are too vague** - Add instruction to include specific details about domain, use cases, and data types

3. **Agent doesn't iterate** - Add instruction: "If the user suggests changes, update your proposal and present it again"
