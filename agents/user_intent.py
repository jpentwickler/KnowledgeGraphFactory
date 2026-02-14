"""User Intent Agent - captures user's knowledge graph goals through conversation."""

from core import run_agent_sync
from core.tracing import traceable
from tools import (
    TOOL_SET_PROPOSED_GOAL,
    TOOL_APPROVE_PROPOSED_GOAL,
    handle_set_proposed_goal,
    handle_approve_proposed_goal,
)


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
5. If they suggest changes, update the proposal using set_proposed_goal again.
   If the goal was previously approved, you MUST call approve_proposed_goal
   again after the user confirms the updated proposal.
6. ONLY call approve_proposed_goal when user explicitly approves (says "approve", "looks good", "yes that's right", etc.)

WORKFLOW:
- First message: Ask clarifying questions (don't propose immediately)
- After user explains: Propose using set_proposed_goal
- Show proposal to user: "Here's what I captured: [kind + description]. Does this look good?"
- If user approves: Call approve_proposed_goal
- If user wants changes: Update and repeat

MOVE-ON RULE:
- Whenever you ask clarifying questions, end with a reminder like:
  "Or say 'move on' if you'd like me to proceed with what I have so far."
- When the user says "move on", "skip", "proceed", "that's enough", or similar:
  STOP asking questions immediately.
  Use your best judgment to fill in gaps with reasonable defaults.
  Call set_proposed_goal with your best proposal and present it for approval.
- The user can still refine or reject the proposal.

QUALITY GUIDELINES:
- kind_of_graph: Short, clear label (2-4 words)
- graph_description: Detailed, specific description including:
  * Domain and use case
  * Key entity types
  * Important relationships
  * What questions the graph should answer
- Make descriptions detailed enough for downstream agents to use

Be concise, professional, and ensure the user approves before finalizing."""


TOOLS = [
    TOOL_SET_PROPOSED_GOAL,
    TOOL_APPROVE_PROPOSED_GOAL,
]

TOOL_HANDLERS = {
    "set_proposed_goal": handle_set_proposed_goal,
    "approve_proposed_goal": handle_approve_proposed_goal,
}


class UserIntentAgent:
    """Agent that captures user's knowledge graph goals through conversation."""

    def __init__(self):
        self.system_prompt = SYSTEM_PROMPT
        self.tools = TOOLS
        self.tool_handlers = TOOL_HANDLERS

    @traceable(name="user_intent.run")
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
