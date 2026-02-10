"""Base agent runner for KG-Factory.

Provides the core agent execution loop that handles Claude API calls
and tool execution.
"""

import os
from typing import Callable

import anthropic

from .tools import execute_tool, format_tool_result, format_tool_error


async def run_agent(
    message: str,
    state: dict,
    system_prompt: str,
    tools: list[dict],
    tool_handlers: dict[str, Callable],
    conversation: list[dict] | None = None,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 4096
) -> tuple[str, dict, list[dict]]:
    """Run an agent conversation turn.

    Calls the Claude API with the given system prompt and tools, then
    executes any tool calls in a loop until the agent returns a text response.

    Args:
        message: User message to send to the agent.
        state: Current state dictionary (may be modified by tool handlers).
        system_prompt: System instructions for the agent.
        tools: List of tool schemas for the agent.
        tool_handlers: Dictionary mapping tool names to handler functions.
        conversation: Existing conversation history. If None, starts fresh.
        model: Claude model to use.
        max_tokens: Maximum tokens for response.

    Returns:
        Tuple of:
        - response: Final text response from the agent
        - state: Updated state dictionary
        - conversation: Updated conversation history for multi-turn
    """
    client = anthropic.Anthropic()

    # Initialize or continue conversation
    if conversation is None:
        conversation = []

    # Add user message
    conversation.append({
        "role": "user",
        "content": message
    })

    # Accumulate text blocks from all loop iterations (intermediate + final)
    all_text_blocks = []

    # Agent loop: continue until we get a text response (not tool_use)
    while True:
        # Build request parameters
        params = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": conversation,
        }

        # Only include tools if we have any
        if tools:
            params["tools"] = tools

        response = client.messages.create(**params)

        # Add assistant response to conversation
        conversation.append({
            "role": "assistant",
            "content": response.content
        })

        # Collect any text blocks from this response
        for block in response.content:
            if hasattr(block, 'text') and block.text.strip():
                all_text_blocks.append(block.text)

        # Check if we're done (no more tool calls)
        if response.stop_reason != "tool_use":
            break

        # Process tool calls
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                try:
                    result = execute_tool(
                        tool_handlers,
                        tool_name,
                        tool_input,
                        state
                    )
                    tool_results.append(format_tool_result(tool_id, result))
                except Exception as e:
                    tool_results.append(format_tool_error(tool_id, str(e)))

        # Add tool results to conversation
        conversation.append({
            "role": "user",
            "content": tool_results
        })

    # Join all text blocks from every iteration
    final_response = "\n\n".join(all_text_blocks) if all_text_blocks else ""

    return final_response, state, conversation


def run_agent_sync(
    message: str,
    state: dict,
    system_prompt: str,
    tools: list[dict],
    tool_handlers: dict[str, Callable],
    conversation: list[dict] | None = None,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 4096,
    max_turns: int = 50
) -> tuple[str, dict, list[dict]]:
    """Synchronous version of run_agent.

    Same as run_agent but runs synchronously. Useful for simple scripts
    and testing.

    Args:
        max_turns: Maximum number of API calls (turn limit). Prevents infinite loops.
            Default is 50 turns. Each tool use counts as one turn.

    See run_agent for full documentation.
    """
    client = anthropic.Anthropic()

    # Initialize or continue conversation
    if conversation is None:
        conversation = []

    # Add user message
    conversation.append({
        "role": "user",
        "content": message
    })

    # Accumulate text blocks from all loop iterations (intermediate + final)
    all_text_blocks = []

    # Agent loop: continue until we get a text response (not tool_use)
    turn_count = 0
    while turn_count < max_turns:
        turn_count += 1

        # Build request parameters
        params = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": conversation,
        }

        # Only include tools if we have any
        if tools:
            params["tools"] = tools

        response = client.messages.create(**params)

        # Add assistant response to conversation
        conversation.append({
            "role": "assistant",
            "content": response.content
        })

        # Collect any text blocks from this response
        for block in response.content:
            if hasattr(block, 'text') and block.text.strip():
                all_text_blocks.append(block.text)

        # Check if we're done (no more tool calls)
        if response.stop_reason != "tool_use":
            break

        # Process tool calls
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                try:
                    result = execute_tool(
                        tool_handlers,
                        tool_name,
                        tool_input,
                        state
                    )
                    tool_results.append(format_tool_result(tool_id, result))
                except Exception as e:
                    tool_results.append(format_tool_error(tool_id, str(e)))

        # Add tool results to conversation
        conversation.append({
            "role": "user",
            "content": tool_results
        })

    # Check if we hit max turns
    if turn_count >= max_turns:
        print(f"WARNING: Agent reached max_turns limit ({max_turns}). Forcing exit.")

    # Join all text blocks from every iteration
    final_response = "\n\n".join(all_text_blocks) if all_text_blocks else ""

    # If no text response due to max_turns, return a warning message
    if not final_response and turn_count >= max_turns:
        final_response = f"[Agent reached max_turns limit ({max_turns}) without completing response]"

    return final_response, state, conversation
