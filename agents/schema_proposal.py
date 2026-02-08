"""Schema Proposal Agent — proposes node and relationship construction rules.

Inner agent of the refinement loop. Analyzes approved CSV files and proposes
a construction plan for the knowledge graph. Receives critic feedback
injected into its system prompt via {feedback} placeholder.

This agent has NO approval tool — only the coordinator can approve.
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
    TOOL_PROPOSE_NODE_CONSTRUCTION,
    TOOL_PROPOSE_RELATIONSHIP_CONSTRUCTION,
    TOOL_REMOVE_NODE_CONSTRUCTION,
    TOOL_REMOVE_RELATIONSHIP_CONSTRUCTION,
    handle_get_approved_files,
    handle_search_file,
    handle_get_proposed_construction_plan,
    handle_propose_node_construction,
    handle_propose_relationship_construction,
    handle_remove_node_construction,
    handle_remove_relationship_construction,
)


SYSTEM_PROMPT_TEMPLATE = """\
You are an expert at knowledge graph modeling with property graphs. Propose an appropriate \
schema by specifying construction rules which transform approved files into nodes or relationships. \
The resulting schema should describe a knowledge graph based on the user goal.

Consider feedback if it is available:
<feedback>
{feedback}
</feedback>

HINTS FOR NODE VS RELATIONSHIP DETECTION:

Every file in the approved files list will become either a node or a relationship.
Determining whether a file likely represents a node or a relationship is based \
on a hint from the filename (is it a single thing or two things) and the \
identifiers found within the file.

Because unique identifiers are so important for determining the structure of the graph, \
always verify the uniqueness of suspected unique identifiers using the 'search_file' tool.

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

CHAIN OF THOUGHT DIRECTIONS:

Prepare for the task:
- get the user goal using the 'get_approved_user_goal' tool
- get the list of approved files using the 'get_approved_files' tool
- get the current construction plan using the 'get_proposed_construction_plan' tool

Think carefully, using tools to perform actions and reconsidering your actions when \
a tool returns an error:
1. For each approved file, consider whether it represents a node or relationship. \
Check the content for potential unique identifiers using the 'sample_file' tool.
2. For each identifier, verify that it is unique by using the 'search_file' tool.
3. Use the node vs relationship guidance for deciding whether the file represents \
a node or a relationship.
4. For a node file, propose a node construction using the 'propose_node_construction' tool.
5. If the node contains a reference relationship, use the 'propose_relationship_construction' \
tool to propose a relationship construction.
6. For a relationship file, propose a relationship construction using the \
'propose_relationship_construction' tool.
7. If you need to remove a construction, use the 'remove_node_construction' or \
'remove_relationship_construction' tool.
8. When you are done with construction proposals, use the 'get_proposed_construction_plan' \
tool to present the plan to the user.\
"""


TOOLS = [
    TOOL_GET_APPROVED_USER_GOAL,
    TOOL_GET_APPROVED_FILES,
    TOOL_GET_PROPOSED_CONSTRUCTION_PLAN,
    TOOL_SAMPLE_FILE,
    TOOL_SEARCH_FILE,
    TOOL_PROPOSE_NODE_CONSTRUCTION,
    TOOL_PROPOSE_RELATIONSHIP_CONSTRUCTION,
    TOOL_REMOVE_NODE_CONSTRUCTION,
    TOOL_REMOVE_RELATIONSHIP_CONSTRUCTION,
]

TOOL_HANDLERS = {
    "get_approved_user_goal": handle_get_approved_user_goal,
    "get_approved_files": handle_get_approved_files,
    "get_proposed_construction_plan": handle_get_proposed_construction_plan,
    "sample_file": handle_sample_file,
    "search_file": handle_search_file,
    "propose_node_construction": handle_propose_node_construction,
    "propose_relationship_construction": handle_propose_relationship_construction,
    "remove_node_construction": handle_remove_node_construction,
    "remove_relationship_construction": handle_remove_relationship_construction,
}


class SchemaProposalAgent:
    """Inner agent that proposes graph schema constructions.

    This agent does NOT have an approval tool. It only proposes node
    and relationship construction rules. The coordinator handles approval.

    Feedback from the critic is injected into the system prompt via
    the {feedback} placeholder.
    """

    def __init__(self):
        self.tools = TOOLS
        self.tool_handlers = TOOL_HANDLERS

    def run(
        self, message: str, state: dict, conversation: list = None
    ) -> tuple[str, dict, list]:
        """Run a conversation turn with the proposal agent.

        Args:
            message: User or orchestrator message.
            state: Current state dictionary (contains feedback from critic).
            conversation: Conversation history (None for fresh start).

        Returns:
            (response, updated_state, conversation)
        """
        # Inject feedback into system prompt
        feedback = state.get("feedback", "")
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(feedback=feedback)

        return run_agent_sync(
            message=message,
            state=state,
            system_prompt=system_prompt,
            tools=self.tools,
            tool_handlers=self.tool_handlers,
            conversation=conversation,
        )
