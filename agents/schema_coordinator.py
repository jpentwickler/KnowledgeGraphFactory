"""Schema Proposal Coordinator — user-facing agent for schema proposal workflow.

Top-level agent that wraps the refinement loop as a tool and manages
user interaction: presents results, handles feedback, and records approval.
"""

from core import run_agent_sync
from tools.schema_tools import (
    TOOL_RUN_REFINEMENT_LOOP,
    TOOL_GET_PROPOSED_CONSTRUCTION_PLAN,
    TOOL_APPROVE_PROPOSED_CONSTRUCTION_PLAN,
    handle_run_refinement_loop,
    handle_get_proposed_construction_plan,
    handle_approve_proposed_construction_plan,
)


SYSTEM_PROMPT = """\
You are a coordinator for the schema proposal process. Use tools to propose a schema to the user.

WORKFLOW:
1. Use the 'run_refinement_loop' tool to produce or update a proposed schema with construction rules.
2. Use the 'get_proposed_construction_plan' tool to get the construction rules.
3. Present the proposed schema and construction rules to the user for approval.
4. If the user disapproves, consider their feedback and use 'run_refinement_loop' again \
with their feedback in the user_feedback parameter.
5. If the user approves, use the 'approve_proposed_construction_plan' tool to record the approval.

GUIDANCE:
- Always run the refinement loop first before presenting results
- Present the schema clearly: list nodes with their labels, unique identifiers, and properties, \
then list relationships with their types, source nodes, target nodes, and properties
- Ask the user explicitly if they approve the schema
- Only call approve_proposed_construction_plan when the user explicitly says \
'approve', 'looks good', 'yes', or similar
- If the user wants changes, note their feedback and run the refinement loop again\
"""


TOOLS = [
    TOOL_RUN_REFINEMENT_LOOP,
    TOOL_GET_PROPOSED_CONSTRUCTION_PLAN,
    TOOL_APPROVE_PROPOSED_CONSTRUCTION_PLAN,
]

TOOL_HANDLERS = {
    "run_refinement_loop": handle_run_refinement_loop,
    "get_proposed_construction_plan": handle_get_proposed_construction_plan,
    "approve_proposed_construction_plan": handle_approve_proposed_construction_plan,
}


class SchemaProposalCoordinator:
    """Top-level agent for schema proposal workflow.

    Wraps the refinement loop as a tool and manages user interaction:
    presents results, handles feedback/approval.
    """

    def __init__(self):
        self.system_prompt = SYSTEM_PROMPT
        self.tools = TOOLS
        self.tool_handlers = TOOL_HANDLERS

    def run(
        self, message: str, state: dict, conversation: list = None
    ) -> tuple[str, dict, list]:
        """Run a conversation turn with the coordinator.

        Args:
            message: User's message.
            state: Current state dictionary.
            conversation: Conversation history (None to start fresh).

        Returns:
            (response, updated_state, conversation)
        """
        # Initialize feedback (equivalent to before_agent_callback)
        if "feedback" not in state:
            state["feedback"] = ""

        return run_agent_sync(
            message=message,
            state=state,
            system_prompt=self.system_prompt,
            tools=self.tools,
            tool_handlers=self.tool_handlers,
            conversation=conversation,
        )
