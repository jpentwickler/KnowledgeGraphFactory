"""Tool handlers for the User Intent Agent."""

from core import create_tool_schema, set_proposed, has_proposed, approve, get_approved


# Tool Schemas for Claude

TOOL_SET_PROPOSED_GOAL = create_tool_schema(
    name="set_proposed_goal",
    description="Save the proposed user goal for the knowledge graph project. Use this after understanding the user's needs.",
    properties={
        "kind_of_graph": {
            "type": "string",
            "description": "Short label for the type of knowledge graph (e.g., 'supply chain', 'social network', 'medical ontology')"
        },
        "graph_description": {
            "type": "string",
            "description": "Detailed description of what the graph should represent, including domain, entities, relationships, and use cases. Should be detailed enough for downstream agents."
        }
    },
    required=["kind_of_graph", "graph_description"]
)

TOOL_APPROVE_PROPOSED_GOAL = create_tool_schema(
    name="approve_proposed_goal",
    description="Approve the proposed goal after the user explicitly confirms it. Only use when user says 'approve', 'looks good', 'yes', or similar.",
    properties={},
    required=[]
)


# Tool Handlers

def handle_set_proposed_goal(state: dict, kind_of_graph: str, graph_description: str) -> dict:
    """Save the proposed user goal.

    Args:
        state: Current state dictionary
        kind_of_graph: Short label for the graph type
        graph_description: Detailed description of the graph

    Returns:
        Tool result dictionary
    """
    set_proposed(state, "user_goal", {
        "kind_of_graph": kind_of_graph,
        "graph_description": graph_description
    })

    return {
        "status": "proposed",
        "message": f"Proposed goal saved: {kind_of_graph}",
        "proposal": {
            "kind_of_graph": kind_of_graph,
            "graph_description": graph_description
        }
    }


def handle_approve_proposed_goal(state: dict) -> dict:
    """Approve the proposed goal, making it official.

    Args:
        state: Current state dictionary

    Returns:
        Tool result dictionary
    """
    if not has_proposed(state, "user_goal"):
        return {
            "status": "error",
            "message": "No proposed goal to approve. Please set a goal first."
        }

    approve(state, "user_goal")
    approved = get_approved(state, "user_goal")

    return {
        "status": "approved",
        "message": "Goal approved! Ready for downstream agents.",
        "approved_goal": approved
    }
