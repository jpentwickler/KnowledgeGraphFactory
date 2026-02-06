"""Integration tests for core framework.

These tests make actual Claude API calls to verify the agent runner works
end-to-end. Requires ANTHROPIC_API_KEY environment variable.
"""

import os
import pytest
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from core import (
    run_agent_sync,
    create_tool_schema,
    set_proposed,
    get_proposed,
    approve,
    get_approved,
)


# Skip if no API key
pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set"
)


class TestAgentIntegration:
    """Integration tests that make actual API calls."""

    def test_simple_echo_agent(self):
        """Test a simple agent that uses an echo tool."""
        # Define a simple echo tool
        echo_tool = create_tool_schema(
            name="echo",
            description="Echo the provided text back. Use this to respond to the user.",
            properties={
                "text": {
                    "type": "string",
                    "description": "The text to echo"
                }
            },
            required=["text"]
        )

        def echo_handler(state, text):
            state["last_echo"] = text
            return {"echoed": text}

        # Run the agent
        response, state, conversation = run_agent_sync(
            message="Please echo the word 'hello'",
            state={},
            system_prompt="You are a simple test agent. When asked to echo something, use the echo tool.",
            tools=[echo_tool],
            tool_handlers={"echo": echo_handler}
        )

        # Verify the tool was called
        assert "last_echo" in state
        assert state["last_echo"] == "hello"

    def test_propose_approve_agent(self):
        """Test an agent that proposes a goal for approval."""
        # Define tools for propose/approve workflow
        propose_tool = create_tool_schema(
            name="set_proposed_goal",
            description="Set the proposed goal for the knowledge graph project.",
            properties={
                "goal": {
                    "type": "string",
                    "description": "The goal statement"
                },
                "domain": {
                    "type": "string",
                    "description": "The domain for the knowledge graph"
                }
            },
            required=["goal", "domain"]
        )

        def propose_handler(state, goal, domain):
            set_proposed(state, "user_goal", {"goal": goal, "domain": domain})
            return {"status": "proposed", "goal": goal, "domain": domain}

        # Run the agent to propose
        response, state, conversation = run_agent_sync(
            message="I want to build a knowledge graph about furniture supply chains.",
            state={},
            system_prompt="""You are a goal-setting agent. When the user describes what they want to build,
use the set_proposed_goal tool to capture their goal and domain.""",
            tools=[propose_tool],
            tool_handlers={"set_proposed_goal": propose_handler}
        )

        # Verify proposal was captured
        proposed = get_proposed(state, "user_goal")
        assert proposed is not None
        assert "furniture" in proposed["goal"].lower() or "furniture" in proposed["domain"].lower()

        # Simulate approval
        approve(state, "user_goal")
        approved = get_approved(state, "user_goal")
        assert approved == proposed

    def test_multi_turn_conversation(self):
        """Test that conversation history is maintained across turns."""
        counter_tool = create_tool_schema(
            name="increment",
            description="Increment the counter and return the new value.",
            properties={},
            required=[]
        )

        def increment_handler(state):
            state["counter"] = state.get("counter", 0) + 1
            return {"counter": state["counter"]}

        tools = [counter_tool]
        handlers = {"increment": increment_handler}
        system_prompt = "You are a counter agent. When asked to increment, use the increment tool."

        # First turn
        response1, state, conversation = run_agent_sync(
            message="Please increment the counter.",
            state={},
            system_prompt=system_prompt,
            tools=tools,
            tool_handlers=handlers
        )
        assert state.get("counter") == 1

        # Second turn (continue conversation)
        response2, state, conversation = run_agent_sync(
            message="Increment again.",
            state=state,
            system_prompt=system_prompt,
            tools=tools,
            tool_handlers=handlers,
            conversation=conversation
        )
        assert state.get("counter") == 2

    def test_agent_without_tools(self):
        """Test that agent works without any tools."""
        response, state, conversation = run_agent_sync(
            message="What is 2 + 2?",
            state={},
            system_prompt="You are a helpful assistant. Answer briefly.",
            tools=[],
            tool_handlers={}
        )

        # Should get a response mentioning 4
        assert "4" in response


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
