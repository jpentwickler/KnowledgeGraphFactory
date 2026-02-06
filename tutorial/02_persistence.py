"""
Tutorial 02: Persistence - Saving State to JSON

Tutorial 01 kept everything in memory. This tutorial shows how to
PERSIST state to disk so agents can pick up where they left off.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import (
    set_proposed, approve, get_approved,
    save_state, load_state  # NEW: persistence functions
)

print("=" * 70)
print("PERSISTENCE: Saving and Loading State")
print("=" * 70)

# ============================================================================
# SESSION 1: Agent proposes, human approves, then SAVES
# ============================================================================
print("\n--- SESSION 1: Agent Work ---")

state = {}
set_proposed(state, "user_goal", {
    "goal": "Build furniture supply chain KG",
    "domain": "furniture"
})

print("[AGENT] Proposed a goal")
print("[HUMAN] Looks good, approve it")
approve(state, "user_goal")

print("\nState in memory:")
print(state)

# SAVE to disk
STATE_FILE = "tutorial/temp_state.json"
save_state(state, STATE_FILE)
print(f"\n[OK] Saved state to {STATE_FILE}")
print("(You can look at this file - it's just JSON!)")

# ============================================================================
# SESSION 2: New Python process, LOADS previous state
# ============================================================================
print("\n" + "=" * 70)
print("--- SESSION 2: Next Agent (new process) ---")

# Pretend this is a new Python session - we have no state variable
state = None  # Simulate fresh start

# LOAD from disk
state = load_state(STATE_FILE)
print(f"[OK] Loaded state from {STATE_FILE}")

print("\nState restored:")
print(state)

# The next agent can now read the approved goal
approved_goal = get_approved(state, "user_goal")
print(f"\n[AGENT] I can see the approved goal: '{approved_goal['goal']}'")
print("[AGENT] I'll now suggest files based on this goal...")

# Agent proposes files
set_proposed(state, "files", {
    "files": ["products.csv", "suppliers.csv"]
})

# Save again
save_state(state, STATE_FILE)
print(f"\n[OK] Saved updated state with proposed files")

# ============================================================================
# KEY INSIGHT
# ============================================================================
print("\n" + "=" * 70)
print("KEY INSIGHT:")
print("=" * 70)
print("""
In a REAL agent system:
  1. Each agent runs as a separate conversation
  2. Before exiting, agent saves state with save_state()
  3. Next agent starts fresh, loads state with load_state()
  4. Reads approved_X from previous agents
  5. Does work, writes proposed_Y
  6. Saves state again

The JSON file is the "memory" that connects all agents together.
Without it, each agent would start from scratch!
""")

print("\nCheck out tutorial/temp_state.json to see the state on disk!")
