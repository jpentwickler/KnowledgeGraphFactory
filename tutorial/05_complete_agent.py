"""
Tutorial 05: Building a Complete Agent

Now we put it all together. This tutorial shows you how to build
a complete agent from scratch using everything you've learned.

We'll build the USER INTENT AGENT - the first agent in the pipeline.

JOB: Capture what the user wants to build and save it as approved_user_goal
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from core import (
    create_tool_schema,
    run_agent_sync,
    set_proposed,
    get_proposed,
    approve,
    has_proposed,
    has_approved
)

print("=" * 70)
print("BUILDING A COMPLETE AGENT: User Intent Agent")
print("=" * 70)

# ============================================================================
# STEP 1: Define the Agent's Job (System Prompt)
# ============================================================================
print("\n--- STEP 1: System Prompt (Agent's Instructions) ---\n")

SYSTEM_PROMPT = """You are the User Intent Agent for a knowledge graph construction system.

YOUR JOB:
1. Understand what knowledge graph the user wants to build
2. Extract:
   - Goal: What they want to accomplish
   - Domain: The industry/area (e.g., "furniture supply chain")
   - Data focus: What entities/relationships they care about
3. Use set_proposed_goal to save your understanding
4. Show the user what you captured and ask for confirmation

WORKFLOW:
- If user describes their intent -> extract and propose goal
- If user says "approve" or "looks good" -> use approve_goal
- If user wants changes -> listen and update the proposal

Be concise and clear."""

print("System Prompt defines:")
print("  - Agent's role")
print("  - What to extract from user")
print("  - Which tools to use when")
print("  - Workflow (propose -> approve)")

# ============================================================================
# STEP 2: Define the Tools (What the Agent Can Do)
# ============================================================================
print("\n--- STEP 2: Tools (Agent's Capabilities) ---\n")

# Tool 1: Propose a goal
TOOL_SET_PROPOSED_GOAL = create_tool_schema(
    name="set_proposed_goal",
    description="Save the proposed user goal for the knowledge graph project.",
    properties={
        "goal": {
            "type": "string",
            "description": "Clear statement of what the user wants to accomplish"
        },
        "domain": {
            "type": "string",
            "description": "The industry/domain (e.g., 'furniture manufacturing', 'social network')"
        },
        "data_focus": {
            "type": "string",
            "description": "What entities and relationships to focus on"
        }
    },
    required=["goal", "domain", "data_focus"]
)

# Tool 2: Approve the goal
TOOL_APPROVE_GOAL = create_tool_schema(
    name="approve_goal",
    description="Approve the proposed goal, making it official for downstream agents.",
    properties={},
    required=[]
)

# Tool 3: Get the current proposal
TOOL_GET_PROPOSED_GOAL = create_tool_schema(
    name="get_proposed_goal",
    description="Retrieve the currently proposed goal to show the user.",
    properties={},
    required=[]
)

TOOLS = [
    TOOL_SET_PROPOSED_GOAL,
    TOOL_APPROVE_GOAL,
    TOOL_GET_PROPOSED_GOAL
]

print("Tools defined:")
print("  1. set_proposed_goal - capture user's intent")
print("  2. approve_goal - finalize the goal")
print("  3. get_proposed_goal - retrieve current proposal")

# ============================================================================
# STEP 3: Define Tool Handlers (What Actually Executes)
# ============================================================================
print("\n--- STEP 3: Tool Handlers (The Python Functions) ---\n")

def handle_set_proposed_goal(state, goal, domain, data_focus):
    """Save the proposed goal."""
    set_proposed(state, "user_goal", {
        "goal": goal,
        "domain": domain,
        "data_focus": data_focus
    })
    return {
        "status": "proposed",
        "message": f"Proposed goal saved. User should review and approve."
    }

def handle_approve_goal(state):
    """Approve the proposed goal."""
    if not has_proposed(state, "user_goal"):
        return {
            "status": "error",
            "message": "No proposed goal to approve. Set a goal first."
        }

    approve(state, "user_goal")
    return {
        "status": "approved",
        "message": "Goal approved! Ready for next agent."
    }

def handle_get_proposed_goal(state):
    """Get the current proposal."""
    proposal = get_proposed(state, "user_goal")
    if proposal:
        return {
            "status": "success",
            "proposal": proposal
        }
    else:
        return {
            "status": "not_found",
            "message": "No proposed goal yet."
        }

TOOL_HANDLERS = {
    "set_proposed_goal": handle_set_proposed_goal,
    "approve_goal": handle_approve_goal,
    "get_proposed_goal": handle_get_proposed_goal
}

print("Handlers implement the actual logic:")
print("  - set_proposed_goal -> calls set_proposed()")
print("  - approve_goal -> calls approve()")
print("  - get_proposed_goal -> calls get_proposed()")

# ============================================================================
# STEP 4: Run the Agent (Interactive Session)
# ============================================================================
print("\n" + "=" * 70)
print("STEP 4: Running the Agent")
print("=" * 70)

state = {}
conversation = None

print("\nThis is an interactive agent session.")
print("The agent will help you define your knowledge graph goal.\n")
print("Type your messages. Type 'quit' to exit, 'state' to see state.\n")

# Start with an initial message
user_message = "I want to build a knowledge graph for analyzing furniture supply chains. I care about suppliers, products, and the relationships between them."

print(f"You: {user_message}\n")

try:
    response, state, conversation = run_agent_sync(
        message=user_message,
        state=state,
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_handlers=TOOL_HANDLERS,
        conversation=conversation
    )

    print(f"Agent: {response}\n")

    # Show state
    if has_proposed(state, "user_goal"):
        print("[INFO] Proposed goal is in state")
        print(f"       State keys: {list(state.keys())}\n")

    # Continue conversation - user approves
    print("-" * 70)
    user_message = "Yes, that looks perfect! Please approve it."
    print(f"You: {user_message}\n")

    response, state, conversation = run_agent_sync(
        message=user_message,
        state=state,
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_handlers=TOOL_HANDLERS,
        conversation=conversation
    )

    print(f"Agent: {response}\n")

    # Check if approved
    if has_approved(state, "user_goal"):
        print("=" * 70)
        print("SUCCESS: Goal Approved!")
        print("=" * 70)
        print("\nApproved goal:")
        import json
        print(json.dumps(state["approved_user_goal"], indent=2))
        print("\nThis is now ready for the next agent (File Suggestion Agent)")

except Exception as e:
    print(f"Error: {e}")
    print("\nMake sure ANTHROPIC_API_KEY is set in your .env file")

# ============================================================================
# STEP 5: The Pattern
# ============================================================================
print("\n" + "=" * 70)
print("THE AGENT PATTERN")
print("=" * 70)
print("""
Every agent follows this structure:

1. SYSTEM PROMPT
   - Defines the agent's role and workflow
   - Instructions on when to use which tools

2. TOOLS (schemas)
   - What the agent can do
   - Usually includes:
     * set_proposed_X (agent's output)
     * approve_X (finalize for next agent)
     * get_X (retrieve current state)
     * Maybe read tools (get_approved_Y from previous agents)

3. TOOL HANDLERS
   - Python functions that implement the tools
   - Modify state using core functions
   - Return results to Claude

4. RUN THE AGENT
   - Call run_agent_sync() with all the pieces
   - Agent handles the conversation loop
   - Returns response, updated state, conversation

That's it! This pattern works for ALL agents:
  - User Intent Agent (this example)
  - File Suggestion Agent
  - Schema Proposal Agent
  - etc.

Same structure, different:
  - System prompts (different jobs)
  - Tools (different capabilities)
  - Handlers (different logic)
""")

print("\n[OK] Tutorial Complete!")
print("\nYou now know how to build agents from scratch!")
print("\nNext steps:")
print("  - Look at agents/ directory structure")
print("  - Implement the real User Intent Agent (US002)")
print("  - Build the pipeline of agents")
