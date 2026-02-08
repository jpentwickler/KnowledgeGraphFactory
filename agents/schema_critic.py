"""Schema Critic Agent — validates the proposed construction plan.

Inner agent of the refinement loop. Has read-only tools plus a structured
submit_review tool. Cannot modify the construction plan directly.

The critic calls submit_review(verdict, problems) to record a structured
verdict. The refinement loop reads state["_critic_verdict"] to decide
whether to stop or iterate.
"""

from core import run_agent_sync
from tools.file_tools import (
    TOOL_GET_APPROVED_USER_GOAL,
    TOOL_SAMPLE_FILE,
    handle_get_approved_user_goal,
    handle_sample_file,
)
from tools.schema_tools import (
    TOOL_GET_APPROVED_FILES,
    TOOL_SEARCH_FILE,
    TOOL_GET_PROPOSED_CONSTRUCTION_PLAN,
    TOOL_SUBMIT_REVIEW,
    handle_get_approved_files,
    handle_search_file,
    handle_get_proposed_construction_plan,
    handle_submit_review,
)


SYSTEM_PROMPT = """\
You are an expert at knowledge graph modeling with property graphs. \
Criticize the proposed schema for relevance to the user goal and approved files.

VALIDATION RULES:

Criticize the proposed schema for relevance and correctness:
- Are unique identifiers actually unique? Use the 'search_file' tool to validate. \
Composite identifiers are not acceptable.
- Could any nodes be relationships instead? Double-check that unique identifiers are \
unique and not references to other nodes. Use the 'search_file' tool to validate.
- Can you manually trace through the source data to find the necessary information for \
answering a hypothetical question?
- Is every node in the schema connected? What relationships could be missing? \
Every node should connect to at least one other node.
- Are hierarchical container relationships missing?
- Are any relationships redundant? A relationship between two nodes is redundant if it \
is semantically equivalent to or the inverse of another relationship between those two nodes.

CHAIN OF THOUGHT DIRECTIONS:

Prepare for the task:
- get the user goal using the 'get_approved_user_goal' tool
- get the list of approved files using the 'get_approved_files' tool
- get the construction plan using the 'get_proposed_construction_plan' tool
- use the 'sample_file' and 'search_file' tools to validate the schema design

Think carefully, using tools to perform actions and reconsidering your actions when \
a tool returns an error:
1. Analyze each construction rule in the proposed construction plan.
2. Use tools to validate the construction rules for relevance and correctness.
3. When you have completed your analysis, you MUST call the 'submit_review' tool:
   - If the schema is correct, call submit_review with verdict "valid" and an empty \
problems list.
   - If the schema has problems, call submit_review with verdict "retry" and a list \
of specific problems to fix.\
"""


TOOLS = [
    TOOL_GET_APPROVED_USER_GOAL,
    TOOL_GET_APPROVED_FILES,
    TOOL_GET_PROPOSED_CONSTRUCTION_PLAN,
    TOOL_SAMPLE_FILE,
    TOOL_SEARCH_FILE,
    TOOL_SUBMIT_REVIEW,
]

TOOL_HANDLERS = {
    "get_approved_user_goal": handle_get_approved_user_goal,
    "get_approved_files": handle_get_approved_files,
    "get_proposed_construction_plan": handle_get_proposed_construction_plan,
    "sample_file": handle_sample_file,
    "search_file": handle_search_file,
    "submit_review": handle_submit_review,
}


class SchemaCriticAgent:
    """Agent that validates proposed schema constructions.

    Read-only tools only (cannot modify the construction plan).
    Uses submit_review tool to record a structured verdict.
    """

    def __init__(self):
        self.system_prompt = SYSTEM_PROMPT
        self.tools = TOOLS
        self.tool_handlers = TOOL_HANDLERS

    def run(
        self, message: str, state: dict, conversation: list = None
    ) -> tuple[str, dict, list]:
        """Run a conversation turn with the critic agent.

        Args:
            message: User or orchestrator message.
            state: Current state dictionary.
            conversation: Conversation history (None for fresh start).

        Returns:
            (response, updated_state, conversation)
        """
        return run_agent_sync(
            message=message,
            state=state,
            system_prompt=self.system_prompt,
            tools=self.tools,
            tool_handlers=self.tool_handlers,
            conversation=conversation,
        )
