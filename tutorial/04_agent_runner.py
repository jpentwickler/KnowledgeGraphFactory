"""
Tutorial 04: The Agent Runner - Orchestrating Everything

This is where it all comes together. The agent runner:
  1. Sends your message + tool schemas to Claude
  2. Claude responds (either text or tool calls)
  3. If tool call -> execute handler -> send result back -> loop
  4. If text -> return response to user

This creates the "agentic loop" that makes everything work.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()  # Load API key from .env file

from core import create_tool_schema, run_agent_sync

print("=" * 70)
print("THE AGENT RUNNER: Orchestrating Everything")
print("=" * 70)

# ============================================================================
# PART 1: The Concept
# ============================================================================
print("""
THE AGENT LOOP:

  User: "I want to build a furniture supply chain KG"
    |
    v
  ┌─────────────────────────────────────────────────────┐
  │ Agent Runner sends to Claude:                       │
  │   - System prompt (instructions)                    │
  │   - User message                                    │
  │   - Available tools (schemas)                       │
  └─────────────────────────────────────────────────────┘
    |
    v
  ┌─────────────────────────────────────────────────────┐
  │ Claude thinks and responds:                         │
  │   "I'll capture that goal using set_proposed_goal"  │
  │   [tool_use: set_proposed_goal, params: {...}]     │
  └─────────────────────────────────────────────────────┘
    |
    v
  ┌─────────────────────────────────────────────────────┐
  │ Agent Runner:                                        │
  │   - Executes the tool handler                       │
  │   - Gets result                                     │
  │   - Sends result back to Claude                     │
  └─────────────────────────────────────────────────────┘
    |
    v
  ┌─────────────────────────────────────────────────────┐
  │ Claude sees result and responds:                    │
  │   "I've captured your goal. Here's what I saved..." │
  └─────────────────────────────────────────────────────┘
    |
    v
  User gets final response

This loop continues until Claude returns text (not a tool call).
""")

input("\nPress ENTER to see a real example with Claude API...")

# ============================================================================
# PART 2: Real Example with Claude
# ============================================================================
print("\n" + "=" * 70)
print("REAL EXAMPLE: Agent that captures user goals")
print("=" * 70)

# Define the system prompt
SYSTEM_PROMPT = """You are a goal-setting agent for knowledge graph projects.

When the user describes what they want to build:
1. Use set_proposed_goal to capture their goal and domain
2. Confirm what you captured

Be concise and friendly."""

# Define tools
tools = [
    create_tool_schema(
        name="set_proposed_goal",
        description="Save the proposed user goal for the knowledge graph project.",
        properties={
            "goal": {
                "type": "string",
                "description": "The main goal statement"
            },
            "domain": {
                "type": "string",
                "description": "The domain/industry"
            }
        },
        required=["goal", "domain"]
    )
]

# Define tool handlers
def set_proposed_goal_handler(state, goal, domain):
    state["proposed_user_goal"] = {
        "goal": goal,
        "domain": domain
    }
    return {
        "status": "success",
        "message": f"Saved: {goal} (domain: {domain})"
    }

tool_handlers = {
    "set_proposed_goal": set_proposed_goal_handler
}

# ============================================================================
# Run the agent!
# ============================================================================
print("\nRunning agent with Claude API...\n")

state = {}

try:
    response, updated_state, conversation = run_agent_sync(
        message="I want to build a knowledge graph about furniture supply chains, focusing on suppliers and products.",
        state=state,
        system_prompt=SYSTEM_PROMPT,
        tools=tools,
        tool_handlers=tool_handlers
    )

    print("=" * 70)
    print("RESULT")
    print("=" * 70)
    print(f"\nClaude's Response:\n{response}")
    print(f"\nUpdated State:\n{updated_state}")
    print(f"\nConversation Length: {len(conversation)} messages")

    # ========================================================================
    # PART 3: What Just Happened
    # ========================================================================
    print("\n" + "=" * 70)
    print("WHAT JUST HAPPENED (Behind the Scenes)")
    print("=" * 70)
    print("""
1. run_agent_sync() was called with:
   - Your message
   - System prompt (agent instructions)
   - Tool schemas (what Claude can do)
   - Tool handlers (actual Python functions)

2. Agent runner sent to Claude API:
   - system: "You are a goal-setting agent..."
   - message: "I want to build a knowledge graph..."
   - tools: [set_proposed_goal schema]

3. Claude responded with:
   - tool_use: "set_proposed_goal"
   - parameters: {goal: "...", domain: "furniture"}

4. Agent runner:
   - Executed set_proposed_goal_handler(state, goal, domain)
   - Got result: {"status": "success", ...}
   - Sent result back to Claude

5. Claude saw the result and responded:
   - Final text response (what you see above)

6. Agent runner returned:
   - response (text)
   - updated_state (with proposed_user_goal)
   - conversation (full message history)
    """)

    # ========================================================================
    # PART 4: The Conversation History
    # ========================================================================
    print("\n" + "=" * 70)
    print("THE CONVERSATION (what was actually sent)")
    print("=" * 70)

    for i, msg in enumerate(conversation):
        print(f"\n--- Message {i+1}: {msg['role']} ---")
        if isinstance(msg['content'], str):
            print(msg['content'][:200])
        elif isinstance(msg['content'], list):
            for block in msg['content']:
                if hasattr(block, 'type'):
                    print(f"  [{block.type}]")
                elif isinstance(block, dict):
                    print(f"  [{block.get('type', 'unknown')}]")

except Exception as e:
    print(f"\nError: {e}")
    print("\nThis requires ANTHROPIC_API_KEY to be set.")
    print("The tutorial shows the concept even without running Claude.")

# ============================================================================
# KEY INSIGHT
# ============================================================================
print("\n" + "=" * 70)
print("KEY INSIGHT")
print("=" * 70)
print("""
The agent runner (run_agent_sync) does ALL the orchestration:

  ✓ Manages conversation with Claude API
  ✓ Handles tool call loop automatically
  ✓ Executes your tool handlers
  ✓ Returns final response + updated state

YOU just provide:
  - System prompt (what is the agent's job?)
  - Tools (what can it do?)
  - Tool handlers (how does it do it?)
  - Initial message

The agent runner makes it all work together!

This is how EVERY agent in the system works:
  - User Intent Agent
  - File Suggestion Agent
  - Schema Proposal Agent
  - etc.

Same pattern, different tools and prompts.
""")

print("\n[OK] Tutorial complete!")
print("\nYou now understand the complete architecture:")
print("  1. Propose/Approve pattern")
print("  2. Tool system (schema + handler)")
print("  3. Agent runner orchestration")
print("\nReady to see a COMPLETE working agent? (User Intent Agent)")
