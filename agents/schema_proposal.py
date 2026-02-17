"""Schema Proposal Agent — proposes node and relationship construction rules.

Conversational agent that analyzes approved CSV files and proposes a construction
plan for the knowledge graph. Pre-computes file context (CSV headers, sample rows)
and injects it into the system prompt, making it fast (1 API call for initial
proposal instead of 20+).

Follows the same pattern as UserIntentAgent and FileSuggestionAgent.
"""

from core import run_agent_sync, get_approved
from core.tracing import traceable
from tools.schema_tools import (
    TOOL_PROPOSE_NODE_CONSTRUCTION,
    TOOL_PROPOSE_RELATIONSHIP_CONSTRUCTION,
    TOOL_REMOVE_NODE_CONSTRUCTION,
    TOOL_REMOVE_RELATIONSHIP_CONSTRUCTION,
    TOOL_GET_PROPOSED_CONSTRUCTION_PLAN,
    TOOL_APPROVE_PROPOSED_CONSTRUCTION_PLAN,
    handle_propose_node_construction,
    handle_propose_relationship_construction,
    handle_remove_node_construction,
    handle_remove_relationship_construction,
    handle_get_proposed_construction_plan,
    handle_approve_proposed_construction_plan,
    build_file_context,
)
from tools.competency_tools import format_competency_questions


SYSTEM_PROMPT_TEMPLATE = """\
You are an expert at knowledge graph modeling with property graphs. Your job is to \
propose a construction plan that transforms approved CSV files into graph nodes and \
relationships, based on the user's goal.

USER GOAL:
- Kind: {user_goal_kind}
- Description: {user_goal_description}

COMPETENCY QUESTIONS (the graph schema must support answering these):
{competency_questions}

APPROVED FILE DATA:
{file_context}

HINTS FOR NODE VS RELATIONSHIP DETECTION:

Every file in the approved files list will become either a node or a relationship.
Determining whether a file likely represents a node or a relationship is based \
on a hint from the filename (is it a single thing or two things) and the \
identifiers found within the file.

General guidance for identifying a node or a relationship:
- If the file name is singular and has only 1 unique identifier it is likely a node
- If the file name is a combination of two things, it is likely a full relationship
- If the file name sounds like a node, but there are multiple unique identifiers, \
that is likely a node with reference relationships

Design rules for nodes:
- Nodes will have unique identifiers.
- Nodes _may_ have identifiers that are used as reference relationships.

Design rules for relationships:
- Relationships appear in two ways: full relationships and reference relationships.

Full relationships:
- Full relationships appear in dedicated relationship files, often having a filename \
that references two entities
- Full relationships typically have references to a source and destination node.
- Full relationships _do not have_ unique identifiers, but instead have references to \
the primary keys of the source and destination nodes.
- The absence of a single, unique identifier is a strong indicator that a file is a \
full relationship.

Reference relationships:
- Reference relationships appear as foreign key references in node files
- Reference relationship foreign key column names often hint at the destination node \
and relationship type
- References may be hierarchical container relationships, with terminology revealing \
parent-child, "has", "contains", membership, or similar relationship
- References may be peer relationships, that is often a self-reference to a similar \
class of nodes. For example, "knows" or "see also"

The resulting schema should be a connected graph, with no isolated components.

TRANSPARENCY:

Always narrate your analysis as you work. Before and between tool calls, \
explain what you are doing so the user can follow your reasoning:
- Which file you are analyzing and why you classified it as a node or relationship
- What columns you identified as unique identifiers vs properties vs foreign keys
- What relationship patterns you detected (full relationships vs reference relationships)
- Any ambiguities or trade-offs in your modeling decisions
- What you excluded from the plan and why

The user should always understand your reasoning, not just see the final result.

WORKFLOW:

You have all the file data above. Do NOT ask for more context -- analyze and propose.

1. Analyze each file's columns and sample data to determine whether it represents \
a node or a relationship.
2. For each node file, call 'propose_node_construction' with the label, unique column, \
and properties.
3. For each relationship (full or reference), call 'propose_relationship_construction' \
with the relationship type, source/target labels and columns.
4. After proposing all constructions, call 'get_proposed_construction_plan' and present \
the complete plan to the user.
5. If the user requests changes, use remove/propose tools to update the proposed plan. \
After making changes, call 'get_proposed_construction_plan' to show the updated plan. \
If the plan was previously approved, you MUST call 'approve_proposed_construction_plan' \
again after the user confirms the changes.
6. ONLY call 'approve_proposed_construction_plan' when the user explicitly approves \
(says "approve", "looks good", "yes", etc.).

MOVE-ON RULE:
- Whenever you ask clarifying questions, end with a reminder like:
  "Or say 'move on' if you'd like me to proceed with what I have so far."
- When the user says "move on", "skip", "proceed", "that's enough", or similar:
  STOP asking questions or explaining further.
  Immediately propose the best schema you can based on available information.
  Call the propose tools, then get_proposed_construction_plan, and present it for approval.
- The user can still refine or reject the proposal.

Be concise and professional. Present the plan clearly so the user can review it.\
"""

TOOLS = [
    TOOL_PROPOSE_NODE_CONSTRUCTION,
    TOOL_PROPOSE_RELATIONSHIP_CONSTRUCTION,
    TOOL_REMOVE_NODE_CONSTRUCTION,
    TOOL_REMOVE_RELATIONSHIP_CONSTRUCTION,
    TOOL_GET_PROPOSED_CONSTRUCTION_PLAN,
    TOOL_APPROVE_PROPOSED_CONSTRUCTION_PLAN,
]

TOOL_HANDLERS = {
    "propose_node_construction": handle_propose_node_construction,
    "propose_relationship_construction": handle_propose_relationship_construction,
    "remove_node_construction": handle_remove_node_construction,
    "remove_relationship_construction": handle_remove_relationship_construction,
    "get_proposed_construction_plan": handle_get_proposed_construction_plan,
    "approve_proposed_construction_plan": handle_approve_proposed_construction_plan,
}


class SchemaProposalAgent:
    """Conversational schema proposal agent.

    Pre-computes file context (CSV headers, sample rows) and injects it into
    the system prompt, eliminating the need for sample_file/search_file tool
    calls. This makes the agent fast (~1 API call for initial proposal instead
    of 20+).

    Follows the same pattern as UserIntentAgent and FileSuggestionAgent.
    """

    def __init__(self):
        self.tools = TOOLS
        self.tool_handlers = TOOL_HANDLERS

    @traceable(name="schema_proposal.run")
    def run(
        self, message: str, state: dict, conversation: list = None
    ) -> tuple[str, dict, list]:
        """Run a conversation turn with the proposal agent.

        On the first call, pre-computes file context and injects it into
        the system prompt along with the user goal.

        Args:
            message: User message.
            state: Current state dictionary.
            conversation: Conversation history (None for fresh start).

        Returns:
            (response, updated_state, conversation)
        """
        # Extract user goal for prompt injection
        user_goal = get_approved(state, "user_goal") or {}
        user_goal_kind = user_goal.get("kind_of_graph", "unknown")
        user_goal_description = user_goal.get("graph_description", "No description available.")

        # Pre-compute file context and competency questions
        file_context = build_file_context(state) or "No approved files found."
        competency_questions = format_competency_questions(state)

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            user_goal_kind=user_goal_kind,
            user_goal_description=user_goal_description,
            competency_questions=competency_questions,
            file_context=file_context,
        )

        return run_agent_sync(
            message=message,
            state=state,
            system_prompt=system_prompt,
            tools=self.tools,
            tool_handlers=self.tool_handlers,
            conversation=conversation,
        )
