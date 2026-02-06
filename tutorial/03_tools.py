"""
Tutorial 03: How Tools Work

Tools are how Claude agents DO things. Claude can't directly call Python
functions, so we use a tool system:

  1. Tool Schema - Describes the tool to Claude (JSON)
  2. Tool Handler - The actual Python function that executes
  3. Tool Execution - We call the handler and return results to Claude
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import create_tool_schema, execute_tool

print("=" * 70)
print("TOOLS: How Agents Do Things")
print("=" * 70)

# ============================================================================
# PART 1: Creating a Tool Schema
# ============================================================================
print("\n--- PART 1: Tool Schema ---")
print("This is what we tell Claude about the tool\n")

# Let's create the "set_proposed_goal" tool
tool_schema = create_tool_schema(
    name="set_proposed_goal",
    description="Save the proposed user goal for the knowledge graph project.",
    properties={
        "goal": {
            "type": "string",
            "description": "The main goal statement"
        },
        "domain": {
            "type": "string",
            "description": "The domain/industry for the knowledge graph"
        }
    },
    required=["goal", "domain"]
)

print("Tool Schema (what Claude sees):")
import json
print(json.dumps(tool_schema, indent=2))

print("\nClaude reads this and knows:")
print("  - Tool name: set_proposed_goal")
print("  - What it does: Save the proposed user goal...")
print("  - What parameters it needs: goal (required), domain (required)")

# ============================================================================
# PART 2: Creating a Tool Handler
# ============================================================================
print("\n" + "=" * 70)
print("--- PART 2: Tool Handler ---")
print("This is the actual Python function that executes\n")

def set_proposed_goal_handler(state, goal, domain):
    """
    The actual function that runs when Claude calls this tool.

    IMPORTANT: Handler signature is always:
      def handler(state, **tool_parameters):

    The handler:
      1. Receives state (can modify it)
      2. Receives the parameters Claude provided
      3. Does the work
      4. Returns a result (will be sent back to Claude)
    """
    # Do the work
    state["proposed_user_goal"] = {
        "goal": goal,
        "domain": domain
    }

    # Return result
    return {
        "status": "success",
        "message": f"Saved proposed goal: {goal}"
    }

print("Handler function:")
print("  def set_proposed_goal_handler(state, goal, domain):")
print("      state['proposed_user_goal'] = {'goal': goal, 'domain': domain}")
print("      return {'status': 'success', ...}")

# ============================================================================
# PART 3: Executing a Tool
# ============================================================================
print("\n" + "=" * 70)
print("--- PART 3: Tool Execution ---")
print("Simulating what happens when Claude calls the tool\n")

# Create state
state = {}

# Claude decides to call the tool with these parameters
tool_call_from_claude = {
    "goal": "Build a furniture supply chain knowledge graph",
    "domain": "furniture manufacturing"
}

print("[CLAUDE] I want to call 'set_proposed_goal' with:")
print(f"  goal: {tool_call_from_claude['goal']}")
print(f"  domain: {tool_call_from_claude['domain']}")

# We execute the handler
tool_handlers = {
    "set_proposed_goal": set_proposed_goal_handler
}

result = execute_tool(
    tool_handlers=tool_handlers,
    tool_name="set_proposed_goal",
    tool_input=tool_call_from_claude,
    state=state
)

print("\n[SYSTEM] Executed handler, got result:")
print(f"  {result}")

print("\n[SYSTEM] State was modified:")
print(f"  {state}")

print("\n[SYSTEM] Sending result back to Claude...")
print("[CLAUDE] Got it! The goal has been saved.")

# ============================================================================
# PART 4: Multiple Tools
# ============================================================================
print("\n" + "=" * 70)
print("--- PART 4: Multiple Tools ---")
print("An agent can have many tools\n")

# Tool 2: Get proposed goal
get_tool_schema = create_tool_schema(
    name="get_proposed_goal",
    description="Retrieve the proposed goal to show the user.",
    properties={},
    required=[]
)

def get_proposed_goal_handler(state):
    """Handler with no parameters except state."""
    if "proposed_user_goal" in state:
        return state["proposed_user_goal"]
    else:
        return {"error": "No proposed goal found"}

# Add to handlers
tool_handlers["get_proposed_goal"] = get_proposed_goal_handler

print("Now we have TWO tools:")
print("  1. set_proposed_goal - saves a goal")
print("  2. get_proposed_goal - retrieves the goal")

# Claude calls the second tool
print("\n[CLAUDE] Let me retrieve the goal...")
result = execute_tool(
    tool_handlers=tool_handlers,
    tool_name="get_proposed_goal",
    tool_input={},  # No parameters
    state=state
)

print(f"[SYSTEM] Result: {result}")
print("[CLAUDE] Great! I can see the goal is: " + result['goal'])

# ============================================================================
# KEY INSIGHT
# ============================================================================
print("\n" + "=" * 70)
print("KEY INSIGHT:")
print("=" * 70)
print("""
Every tool has TWO parts:
  1. SCHEMA - JSON description for Claude
  2. HANDLER - Python function that does the work

The agent runner (core/agent.py) handles the flow:
  - Sends schemas to Claude
  - Claude decides which tools to call
  - We execute the handlers
  - Send results back to Claude
  - Claude continues or responds

This is how propose/approve works under the hood!
  - set_proposed() is just a tool handler
  - approve() is just a tool handler
  - The agent calls these tools through Claude
""")

print("\n[OK] Tutorial complete!")
print("\nNext: See how the Agent Runner orchestrates this with Claude API")
