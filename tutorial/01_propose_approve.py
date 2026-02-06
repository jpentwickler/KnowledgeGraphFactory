"""
Tutorial 01: The Propose -> Approve Pattern

This is the CORE pattern that makes KG-Factory work.

WHY: We want Claude to suggest things, but WE (humans) approve them before
     the next agent uses them.

PATTERN:
  1. Agent proposes something -> state["proposed_X"]
  2. Human reviews it
  3. Human says "approve" -> state["approved_X"] = state["proposed_X"]
  4. Next agent reads state["approved_X"]

This prevents agents from making decisions without human oversight.
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import core
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import set_proposed, get_proposed, approve, get_approved, has_approved

# ============================================================================
# SCENARIO: User Intent Agent proposes a goal
# ============================================================================

print("=" * 70)
print("SCENARIO: Building a Knowledge Graph")
print("=" * 70)

# Start with empty state
state = {}

# ----------------------------------------------------------------------------
# STEP 1: Agent proposes a goal
# ----------------------------------------------------------------------------
print("\n[AGENT] I understand you want to build a knowledge graph.")
print("[AGENT] Let me propose a formal goal...\n")

# Agent uses set_proposed to save its suggestion
set_proposed(state, "user_goal", {
    "goal": "Build a knowledge graph for furniture supply chain analysis",
    "domain": "furniture manufacturing",
    "focus": "suppliers, products, and relationships"
})

print("[OK] Agent stored proposed goal in state['proposed_user_goal']")

# ----------------------------------------------------------------------------
# STEP 2: Human reviews the proposal
# ----------------------------------------------------------------------------
print("\n" + "-" * 70)
print("HUMAN REVIEW TIME")
print("-" * 70)

# Get what the agent proposed
proposal = get_proposed(state, "user_goal")
print(f"\nThe agent proposed:")
print(f"  Goal: {proposal['goal']}")
print(f"  Domain: {proposal['domain']}")
print(f"  Focus: {proposal['focus']}")

# Check approval status
print(f"\nIs it approved yet? {has_approved(state, 'user_goal')}")  # False

# ----------------------------------------------------------------------------
# STEP 3: Human approves
# ----------------------------------------------------------------------------
print("\n[HUMAN] Yes, this looks good! Approve it.\n")

# Approve copies proposed_user_goal -> approved_user_goal
approve(state, "user_goal")

print("[OK] Approved! Copied to state['approved_user_goal']")
print(f"Is it approved now? {has_approved(state, 'user_goal')}")  # True

# ----------------------------------------------------------------------------
# STEP 4: Next agent reads the approved goal
# ----------------------------------------------------------------------------
print("\n" + "-" * 70)
print("NEXT AGENT (File Suggestion Agent)")
print("-" * 70)

# The next agent ONLY reads approved_ artifacts
approved_goal = get_approved(state, "user_goal")
print(f"\n[AGENT] I see the approved goal: '{approved_goal['goal']}'")
print("[AGENT] Based on this, let me suggest which files to analyze...\n")

# ============================================================================
# KEY INSIGHT
# ============================================================================
print("\n" + "=" * 70)
print("KEY INSIGHT:")
print("=" * 70)
print("""
Agents follow this pattern:
  1. Read approved_X from previous agents (downstream input)
  2. Do their work
  3. Write proposed_Y as their output
  4. Wait for human approval
  5. Human approves -> proposed_Y becomes approved_Y
  6. Next agent can now read approved_Y

This creates a HUMAN-IN-THE-LOOP pipeline where nothing proceeds
without your explicit approval.
""")

# ============================================================================
# YOUR TURN: Try it yourself
# ============================================================================
print("\n" + "=" * 70)
print("YOUR TURN")
print("=" * 70)
print("""
Uncomment the code below and run this script again.
Try proposing and approving a file suggestion.
""")

# UNCOMMENT THIS:
# state2 = {"approved_user_goal": approved_goal}  # Start with approved goal
#
# # Next agent proposes files
# set_proposed(state2, "files", {
#     "files": ["data/products.csv", "data/suppliers.csv"],
#     "reason": "These contain product and supplier information"
# })
#
# print("\n[AGENT] I propose using these files:")
# print(get_proposed(state2, "files"))
#
# # You review and approve
# print("\n[HUMAN] Looks good, approve!")
# approve(state2, "files")
#
# print("\n[NEXT AGENT] Files I should analyze:")
# print(get_approved(state2, "files")["files"])

print("\n[OK] Tutorial complete! Run this script to see the pattern in action.")
print("\nReady for the next tutorial? Let me know!")
