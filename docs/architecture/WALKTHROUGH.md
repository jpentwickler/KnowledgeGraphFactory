# User Intent Agent - Complete Walkthrough

## Table of Contents
1. [Big Picture](#big-picture)
2. [Directory Structure](#directory-structure)
3. [Step-by-Step Implementation](#step-by-step)
4. [How Everything Connects](#connections)
5. [Running and Testing](#testing)
6. [Next Steps](#next-steps)

---

## Big Picture

### What Problem Are We Solving?

Building a knowledge graph requires:
1. Understanding what the user wants
2. Finding relevant data files
3. Designing the graph schema
4. Extracting entities and facts
5. Building the graph in Neo4j

The **User Intent Agent** handles step 1: capturing and validating user requirements.

### The Conversation Flow

```
User: "I want to build a supply chain knowledge graph"
  ↓
Agent: [Asks clarifying questions about domain, goals, data]
  ↓
User: "I want to track suppliers, products, components..."
  ↓
Agent: [Proposes structured goal] "Here's what I captured..."
  ↓
User: "Yes, approve it"
  ↓
Agent: [Saves approved goal to state]
  ↓
Output: approved_user_goal = {kind_of_graph, graph_description}
```

### The Propose → Approve Pattern

This is the **core pattern** used throughout KG-Factory:

1. **Propose**: Agent creates something → `state["proposed_X"]`
2. **Review**: User reviews and may request changes
3. **Iterate**: Agent updates proposal if needed
4. **Approve**: User explicitly approves → `state["approved_X"]`
5. **Handoff**: Next agent reads `approved_X`

---

## Directory Structure

```
kg-factory/
├── core/                          # Framework (US001 - already built)
│   ├── agent.py                   # Agent runner with agentic loop
│   ├── state.py                   # State management functions
│   └── tools.py                   # Tool schema utilities
│
├── tools/                         # NEW - Tool handlers
│   ├── __init__.py               # Package exports
│   └── intent_tools.py           # Handlers for User Intent Agent
│
├── agents/                        # NEW - Agent definitions
│   ├── __init__.py               # Package exports
│   └── user_intent.py            # User Intent Agent class
│
└── tests/                         # NEW - Test suite
    ├── unit/                      # Unit tests
    │   ├── __init__.py
    │   └── test_intent_tools.py  # Test tool handlers
    ├── test_01_user_intent.py    # Interactive test
    └── test_01_verify.py          # Automated test
```

---

## Step-by-Step Implementation

Let's build this from the ground up, starting with the smallest pieces.

---

### STEP 1: Tool Handlers (tools/intent_tools.py)

**What are tool handlers?**
- Functions that Claude can call during conversation
- They modify the state (our data store)
- They return results to Claude

**File: tools/intent_tools.py**

#### Part 1A: Imports

```python
from core import create_tool_schema, set_proposed, has_proposed, approve, get_approved
```

These are helper functions from the core framework:
- `create_tool_schema`: Creates tool definitions Claude understands
- `set_proposed`, `approve`: Manage the propose→approve workflow
- `has_proposed`, `get_approved`: Check state

#### Part 1B: Tool Schema - SET_PROPOSED_GOAL

```python
TOOL_SET_PROPOSED_GOAL = create_tool_schema(
    name="set_proposed_goal",
    description="Save the proposed user goal for the knowledge graph project. Use this after understanding the user's needs.",
    properties={
        "kind_of_graph": {
            "type": "string",
            "description": "Short label for the type of knowledge graph (e.g., 'supply chain', 'social network', 'medical ontology')"
        },
        "graph_description": {
            "type": "string",
            "description": "Detailed description of what the graph should represent, including domain, entities, relationships, and use cases. Should be detailed enough for downstream agents."
        }
    },
    required=["kind_of_graph", "graph_description"]
)
```

**What this does:**
- Tells Claude about the `set_proposed_goal` tool
- Specifies two parameters: `kind_of_graph` and `graph_description`
- Both parameters are required
- Includes clear descriptions so Claude knows when/how to use it

#### Part 1C: Tool Handler - handle_set_proposed_goal

```python
def handle_set_proposed_goal(state: dict, kind_of_graph: str, graph_description: str) -> dict:
    """Save the proposed user goal.

    Args:
        state: Current state dictionary
        kind_of_graph: Short label for the graph type
        graph_description: Detailed description of the graph

    Returns:
        Tool result dictionary
    """
    set_proposed(state, "user_goal", {
        "kind_of_graph": kind_of_graph,
        "graph_description": graph_description
    })

    return {
        "status": "proposed",
        "message": f"Proposed goal saved: {kind_of_graph}",
        "proposal": {
            "kind_of_graph": kind_of_graph,
            "graph_description": graph_description
        }
    }
```

**What this does:**
1. Takes the state dictionary and the two parameters
2. Calls `set_proposed()` to save to `state["proposed_user_goal"]`
3. Returns a result dict that Claude will see
4. The result confirms the proposal was saved

**Key insight:** This doesn't approve anything yet! It just saves a proposal.

#### Part 1D: Tool Schema - APPROVE_PROPOSED_GOAL

```python
TOOL_APPROVE_PROPOSED_GOAL = create_tool_schema(
    name="approve_proposed_goal",
    description="Approve the proposed goal after the user explicitly confirms it. Only use when user says 'approve', 'looks good', 'yes', or similar.",
    properties={},
    required=[]
)
```

**What this does:**
- Tells Claude about the `approve_proposed_goal` tool
- No parameters needed (it just approves whatever is already proposed)
- Description emphasizes "explicitly confirms" to prevent auto-approval

#### Part 1E: Tool Handler - handle_approve_proposed_goal

```python
def handle_approve_proposed_goal(state: dict) -> dict:
    """Approve the proposed goal, making it official.

    Args:
        state: Current state dictionary

    Returns:
        Tool result dictionary
    """
    if not has_proposed(state, "user_goal"):
        return {
            "status": "error",
            "message": "No proposed goal to approve. Please set a goal first."
        }

    approve(state, "user_goal")
    approved = get_approved(state, "user_goal")

    return {
        "status": "approved",
        "message": "Goal approved! Ready for downstream agents.",
        "approved_goal": approved
    }
```

**What this does:**
1. Checks if there's a proposal (error handling!)
2. If no proposal exists, returns error message
3. If proposal exists, calls `approve()` to copy proposed → approved
4. Returns success message with the approved goal

**Key insight:** This moves data from `state["proposed_user_goal"]` to `state["approved_user_goal"]`

---

### STEP 2: Package Exports (tools/__init__.py)

```python
from tools.intent_tools import (
    TOOL_SET_PROPOSED_GOAL,
    TOOL_APPROVE_PROPOSED_GOAL,
    handle_set_proposed_goal,
    handle_approve_proposed_goal,
)

__all__ = [
    "TOOL_SET_PROPOSED_GOAL",
    "TOOL_APPROVE_PROPOSED_GOAL",
    "handle_set_proposed_goal",
    "handle_approve_proposed_goal",
]
```

**What this does:**
- Makes tools importable from the `tools` package
- Other code can do: `from tools import TOOL_SET_PROPOSED_GOAL`
- Standard Python package pattern

---

### STEP 3: The Agent (agents/user_intent.py)

Now we tie everything together into an agent!

#### Part 3A: Imports

```python
from core import run_agent_sync
from tools import (
    TOOL_SET_PROPOSED_GOAL,
    TOOL_APPROVE_PROPOSED_GOAL,
    handle_set_proposed_goal,
    handle_approve_proposed_goal,
)
```

**What we're importing:**
- `run_agent_sync`: The agent runner from core (handles Claude API calls)
- Tool schemas and handlers we just created

#### Part 3B: System Prompt

```python
SYSTEM_PROMPT = """You are the User Intent Agent, a knowledge graph design consultant.

YOUR JOB:
1. Understand what knowledge graph the user wants to build through conversation
2. Ask clarifying questions about:
   - Domain/industry
   - Goals and use cases
   - What entities and relationships matter
   - What data sources they have
3. Once you understand, use set_proposed_goal to propose a structured goal
4. Present the proposal clearly and ask if it captures their needs
5. If they suggest changes, update the proposal using set_proposed_goal again
6. ONLY call approve_proposed_goal when user explicitly approves (says "approve", "looks good", "yes that's right", etc.)

WORKFLOW:
- First message: Ask clarifying questions (don't propose immediately)
- After user explains: Propose using set_proposed_goal
- Show proposal to user: "Here's what I captured: [kind + description]. Does this look good?"
- If user approves: Call approve_proposed_goal
- If user wants changes: Update and repeat

QUALITY GUIDELINES:
- kind_of_graph: Short, clear label (2-4 words)
- graph_description: Detailed, specific description including:
  * Domain and use case
  * Key entity types
  * Important relationships
  * What questions the graph should answer
- Make descriptions detailed enough for downstream agents to use

Be concise, professional, and ensure the user approves before finalizing."""
```

**What this does:**
- This is the "personality" and "instructions" for Claude
- Tells Claude its role (knowledge graph consultant)
- Specifies the workflow step by step
- Emphasizes quality guidelines
- Prevents auto-approval by saying "ONLY when user explicitly approves"

**Key insight:** The system prompt is how we control Claude's behavior!

#### Part 3C: Tool Configuration

```python
TOOLS = [
    TOOL_SET_PROPOSED_GOAL,
    TOOL_APPROVE_PROPOSED_GOAL,
]

TOOL_HANDLERS = {
    "set_proposed_goal": handle_set_proposed_goal,
    "approve_proposed_goal": handle_approve_proposed_goal,
}
```

**What this does:**
- `TOOLS`: List of tool schemas Claude can see
- `TOOL_HANDLERS`: Maps tool names to Python functions

When Claude calls "set_proposed_goal", the agent runner will:
1. Look up "set_proposed_goal" in TOOL_HANDLERS
2. Execute `handle_set_proposed_goal(state, **params)`
3. Return result to Claude

#### Part 3D: Agent Class

```python
class UserIntentAgent:
    """Agent that captures user's knowledge graph goals through conversation."""

    def __init__(self):
        self.system_prompt = SYSTEM_PROMPT
        self.tools = TOOLS
        self.tool_handlers = TOOL_HANDLERS

    def run(self, message: str, state: dict, conversation: list = None) -> tuple[str, dict, list]:
        """Run a conversation turn with the agent.

        Args:
            message: User's message
            state: Current state dictionary
            conversation: Conversation history (None to start fresh)

        Returns:
            (response, updated_state, conversation)
        """
        return run_agent_sync(
            message=message,
            state=state,
            system_prompt=self.system_prompt,
            tools=self.tools,
            tool_handlers=self.tool_handlers,
            conversation=conversation
        )
```

**What this does:**
1. `__init__`: Stores system prompt, tools, handlers as instance variables
2. `run()`: Main entry point for conversation
   - Takes: user message, current state, conversation history
   - Calls: `run_agent_sync()` from core framework
   - Returns: (agent response, updated state, conversation history)

**Key insight:** The agent is just a thin wrapper around `run_agent_sync()` with specific configuration!

---

### STEP 4: Package Exports (agents/__init__.py)

```python
from agents.user_intent import UserIntentAgent

__all__ = ["UserIntentAgent"]
```

Simple exports so we can do: `from agents import UserIntentAgent`

---

## How Everything Connects

Let's trace a full conversation through the system:

### Turn 1: User Asks Question

```
User: "I want to build a supply chain knowledge graph"
```

**What happens:**

1. **You call:**
   ```python
   agent = UserIntentAgent()
   response, state, conversation = agent.run(
       "I want to build a supply chain knowledge graph",
       state={},
       conversation=None
   )
   ```

2. **Agent runner (core/agent.py) does:**
   - Adds user message to conversation history
   - Calls Claude API with:
     * System prompt (the instructions)
     * Conversation history
     * Available tools (TOOL_SET_PROPOSED_GOAL, TOOL_APPROVE_PROPOSED_GOAL)

3. **Claude responds:**
   - Reads system prompt: "Ask clarifying questions first"
   - Generates text asking about domain, goals, entities, data sources
   - No tool calls yet!

4. **Agent runner returns:**
   - `response`: Claude's text (the clarifying questions)
   - `state`: Still empty (no tools called)
   - `conversation`: Updated with user message + Claude response

### Turn 2: User Provides Details

```
User: "I want to track suppliers, manufacturers, products, and components..."
```

**What happens:**

1. **You call:**
   ```python
   response, state, conversation = agent.run(
       "I want to track suppliers, manufacturers, products, and components...",
       state,
       conversation  # Pass previous conversation back!
   )
   ```

2. **Agent runner does:**
   - Adds new user message to conversation history
   - Calls Claude API with updated conversation

3. **Claude responds with:**
   - Text: "Here's what I captured..."
   - Tool call: `set_proposed_goal` with:
     ```json
     {
       "kind_of_graph": "supply chain analysis",
       "graph_description": "A knowledge graph representing..."
     }
     ```

4. **Agent runner sees tool call:**
   - Looks up "set_proposed_goal" in TOOL_HANDLERS
   - Calls `handle_set_proposed_goal(state, kind_of_graph="...", graph_description="...")`
   - Handler saves to `state["proposed_user_goal"]`
   - Handler returns result dict

5. **Agent runner sends tool result back to Claude:**
   - Claude sees: "Proposed goal saved: supply chain analysis"
   - Claude generates final response showing the proposal to user

6. **Agent runner returns:**
   - `response`: Claude's text showing the proposal
   - `state`: Now contains `proposed_user_goal`
   - `conversation`: Updated with all messages and tool calls

### Turn 3: User Approves

```
User: "Yes, approve it"
```

**What happens:**

1. **You call:**
   ```python
   response, state, conversation = agent.run("Yes, approve it", state, conversation)
   ```

2. **Agent runner does:**
   - Adds user message
   - Calls Claude API

3. **Claude responds with:**
   - Tool call: `approve_proposed_goal` (no parameters)

4. **Agent runner executes tool:**
   - Calls `handle_approve_proposed_goal(state)`
   - Handler checks: `has_proposed(state, "user_goal")` → True
   - Handler calls: `approve(state, "user_goal")`
   - This copies: `state["proposed_user_goal"]` → `state["approved_user_goal"]`
   - Handler returns success message

5. **Agent runner returns:**
   - `response`: Claude's confirmation message
   - `state`: Now contains both `proposed_user_goal` AND `approved_user_goal`
   - `conversation`: Complete conversation history

### Final State

```python
state = {
    "proposed_user_goal": {
        "kind_of_graph": "supply chain analysis",
        "graph_description": "A knowledge graph representing..."
    },
    "approved_user_goal": {
        "kind_of_graph": "supply chain analysis",
        "graph_description": "A knowledge graph representing..."
    }
}
```

The next agent will read `state["approved_user_goal"]` and continue the pipeline!

---

## Running and Testing

### Test 1: Unit Tests (Simplest)

Test individual tool handlers without Claude:

```bash
python -m tests.unit.test_intent_tools
```

**What it tests:**
- `handle_set_proposed_goal()` saves correctly
- `handle_approve_proposed_goal()` fails gracefully without proposal
- `handle_approve_proposed_goal()` works with proposal
- Can update proposals

**Why it's useful:** Fast, no API calls, tests core logic

### Test 2: Verification Test (Automated)

Simulates full conversation programmatically:

```bash
python -m tests.test_01_verify
```

**What it tests:**
- Full conversation flow with Claude
- Agent asks questions before proposing
- Agent doesn't auto-approve
- Approval workflow works
- Edge cases (approve without proposal)

**Why it's useful:** End-to-end test, automated, repeatable

### Test 3: Interactive Test (Manual)

Chat with the agent yourself:

```bash
python -m tests.test_01_user_intent
```

**What you can do:**
- Type messages naturally
- Type `state` to see current state
- Type `quit` to exit
- Test real conversation flows

**Why it's useful:** Feel how the agent behaves, find UX issues

---

## Next Steps

### Understanding the Core Framework

If you want to understand the foundation:

1. **Read core/state.py**: See how propose/approve works
2. **Read core/tools.py**: See how tool schemas are created
3. **Read core/agent.py**: See the agentic loop (this is the magic!)

### Building the Next Agent

The File Suggestion Agent (US003) will:
- **Input**: `state["approved_user_goal"]`
- **Output**: `state["approved_files"]`
- **Pattern**: Same as User Intent Agent!
  - Tool handlers in `tools/file_tools.py`
  - Agent class in `agents/file_suggestion.py`
  - Tests in `tests/test_02_*`

### Key Takeaways

1. **Tools = Functions Claude Can Call**
   - Tool schema tells Claude about the function
   - Tool handler implements the function
   - State is modified by handlers

2. **Agents = System Prompt + Tools + Conversation Loop**
   - System prompt controls behavior
   - Tools enable actions
   - Agent runner manages Claude API calls

3. **Propose → Approve = Collaboration Pattern**
   - Agent proposes solutions
   - Human reviews and iterates
   - Human explicitly approves
   - Next agent uses approved output

4. **State = Shared Memory Between Agents**
   - Each agent reads from previous agents
   - Each agent writes for next agents
   - Pipeline is: Agent1 → State → Agent2 → State → Agent3...

---

## Questions to Explore

1. **How does `run_agent_sync()` handle tool calls?**
   - Open `core/agent.py`, read the main loop
   - Look for the part that processes tool_use blocks

2. **How does `set_proposed()` work?**
   - Open `core/state.py`
   - See how it creates `state["proposed_X"]`

3. **What if Claude calls a tool we didn't expect?**
   - Agent runner checks TOOL_HANDLERS
   - If not found, returns error to Claude
   - Claude tries again with correct tool

4. **Can we have tools that call other tools?**
   - No! Tools should be simple
   - Complex logic goes in agents (which can call multiple tools)

5. **How do we add more tools to an agent?**
   - Add schema to `tools/intent_tools.py`
   - Add handler function
   - Add to `TOOLS` list and `TOOL_HANDLERS` dict
   - Update system prompt to tell Claude about new tool

---

That's the complete system! Start with the unit tests, then read the tool handlers, then the agent class, then trace a conversation through the code.
