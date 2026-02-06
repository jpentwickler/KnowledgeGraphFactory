# Deep Dive: core/agent.py

This file contains the **heart of the system** - the agent runner that orchestrates everything.

## Overview

The file provides two nearly identical functions:
- `run_agent()` - Async version (for future use)
- `run_agent_sync()` - Synchronous version (what we use now)

Both implement the **agentic loop**: message → Claude → tool calls → handlers → results → repeat → final response

---

## Line-by-Line Analysis

### Lines 1-12: Imports and Setup

```python
import anthropic
from .tools import execute_tool, format_tool_result, format_tool_error
```

**Key imports:**
- `anthropic` - The Claude API client
- `execute_tool` - Runs tool handlers
- `format_tool_result` - Formats successful tool results for Claude
- `format_tool_error` - Formats errors for Claude

---

### Lines 15-24: Function Signature

```python
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
```

**Parameters breakdown:**

| Parameter | Type | Purpose | Example |
|-----------|------|---------|---------|
| `message` | str | User's input | "I want to build a KG" |
| `state` | dict | Shared state (modified by tools) | `{}` or `{"approved_goal": {...}}` |
| `system_prompt` | str | Agent instructions | "You are the User Intent Agent..." |
| `tools` | list[dict] | Tool schemas (what Claude sees) | `[{name: "set_goal", ...}]` |
| `tool_handlers` | dict | Tool implementations | `{"set_goal": handler_func}` |
| `conversation` | list[dict] \| None | Message history for multi-turn | `None` starts fresh |
| `model` | str | Claude model ID | Default: Sonnet 4 |
| `max_tokens` | int | Max response length | Default: 4096 |

**Returns:**
- `final_response` (str) - Claude's final text response
- `state` (dict) - Updated state after tool calls
- `conversation` (list) - Full message history

---

### Lines 46-56: Initialization

```python
client = anthropic.Anthropic()

# Initialize or continue conversation
if conversation is None:
    conversation = []

# Add user message
conversation.append({
    "role": "user",
    "content": message
})
```

**What's happening:**
1. Create Claude API client (reads `ANTHROPIC_API_KEY` from env)
2. If no conversation history, start fresh with empty list
3. Add user's message to conversation

**Why conversation is a list:**
The conversation follows Claude's message format:
```python
[
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": [...]},
    {"role": "user", "content": [tool_results]},
    {"role": "assistant", "content": "Final response"}
]
```

---

### Lines 58-82: The Main Loop

```python
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

    # Check if we're done (no more tool calls)
    if response.stop_reason != "tool_use":
        break
```

**The Agentic Loop:**

This `while True` loop is the **core magic**. Here's what happens:

1. **Build request** - Prepare parameters for Claude API
2. **Conditional tools** (lines 68-70) - Only include `tools` if we have any
   - **Why?** Empty list causes API error (you discovered this!)
   - Without tools, Claude just responds with text
3. **Call Claude** (line 72) - Send everything to Claude API
4. **Save response** (lines 75-78) - Add Claude's response to conversation
5. **Check if done** (lines 81-82):
   - If `stop_reason != "tool_use"` → Claude returned text, we're done!
   - If `stop_reason == "tool_use"` → Claude wants to call tools, continue loop

**stop_reason values:**
- `"end_turn"` - Normal completion (text response)
- `"tool_use"` - Claude wants to use a tool
- `"max_tokens"` - Hit token limit
- `"stop_sequence"` - Hit a stop sequence

---

### Lines 84-107: Tool Execution

```python
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
```

**What's happening:**

1. **Loop through response blocks** - Claude's response can contain multiple blocks
   - Text blocks: `block.type == "text"`
   - Tool use blocks: `block.type == "tool_use"`

2. **Extract tool info** (lines 88-90):
   - `tool_name` - Which tool Claude wants ("set_proposed_goal")
   - `tool_input` - Parameters Claude provided `{goal: "...", domain: "..."}`
   - `tool_id` - Unique ID for this tool call

3. **Execute tool** (lines 92-101):
   - **Try:** Run the handler function
   - **Catch:** If handler fails, format error instead
   - **Why catch?** We want to tell Claude about errors, not crash

4. **Send results back** (lines 104-107):
   - Add tool results as a "user" message
   - **Why "user"?** In Claude's API, tool results come from the "user" role
   - Loop continues, Claude sees results and responds again

**Claude's response structure:**
```python
response.content = [
    TextBlock(text="Let me save that goal..."),
    ToolUseBlock(
        type="tool_use",
        name="set_proposed_goal",
        id="toolu_123",
        input={"goal": "...", "domain": "..."}
    )
]
```

---

### Lines 109-115: Extract Final Response

```python
# Extract final text response
final_response = ""
for block in response.content:
    if hasattr(block, 'text'):
        final_response += block.text

return final_response, state, conversation
```

**What's happening:**
1. Loop through the final response blocks
2. Concatenate all text blocks (Claude might return multiple)
3. **Why `hasattr(block, 'text')`?**
   - TextBlock has `.text` attribute
   - ToolUseBlock doesn't
   - This safely extracts only text

4. Return the tuple:
   - `final_response` - What to show the user
   - `state` - Updated by tool handlers
   - `conversation` - For continuing the conversation

---

## The Complete Flow (Example)

Let's trace a real example:

```python
response, state, conversation = run_agent_sync(
    message="I want to build a furniture KG",
    state={},
    system_prompt="You are User Intent Agent...",
    tools=[set_proposed_goal_schema],
    tool_handlers={"set_proposed_goal": handler}
)
```

### Iteration 1 (Lines 58-107)

**Request to Claude:**
```python
{
    "system": "You are User Intent Agent...",
    "messages": [
        {"role": "user", "content": "I want to build a furniture KG"}
    ],
    "tools": [set_proposed_goal_schema]
}
```

**Claude responds:**
```python
{
    "stop_reason": "tool_use",
    "content": [
        TextBlock("Let me capture that goal..."),
        ToolUseBlock(
            name="set_proposed_goal",
            input={"goal": "Build furniture KG", "domain": "furniture"}
        )
    ]
}
```

**Agent runner:**
1. Adds response to conversation (line 75-78)
2. Checks stop_reason = "tool_use" → continue loop (line 81)
3. Extracts tool call (lines 86-90)
4. Executes handler (lines 92-98):
   ```python
   handler(state, goal="Build furniture KG", domain="furniture")
   # state now = {"proposed_user_goal": {...}}
   ```
5. Formats result (line 99)
6. Adds result to conversation as "user" message (lines 104-107)

**Conversation now:**
```python
[
    {"role": "user", "content": "I want to build a furniture KG"},
    {"role": "assistant", "content": [TextBlock(...), ToolUseBlock(...)]},
    {"role": "user", "content": [ToolResult(...)]}
]
```

### Iteration 2 (Lines 58-107 again)

**Request to Claude:**
```python
{
    "system": "You are User Intent Agent...",
    "messages": [... full conversation with tool result ...],
    "tools": [set_proposed_goal_schema]
}
```

**Claude responds:**
```python
{
    "stop_reason": "end_turn",
    "content": [
        TextBlock("I've captured your goal: Build furniture KG (domain: furniture)")
    ]
}
```

**Agent runner:**
1. Adds response to conversation
2. Checks stop_reason = "end_turn" → **break loop!** (line 81)
3. Extracts final text (lines 109-115)
4. Returns: `("I've captured your goal...", state, conversation)`

---

## Key Design Decisions

### 1. Why a `while True` loop?
- Claude might call multiple tools in sequence
- We don't know ahead of time how many iterations needed
- Loop until Claude returns text (not tools)

### 2. Why save full conversation?
- Enables multi-turn conversations
- Next call can pass `conversation=conversation` to continue
- Claude maintains context across turns

### 3. Why both async and sync versions?
- `run_agent()` (async) - For future integration with async frameworks
- `run_agent_sync()` - For simple scripts and tests (what we use now)
- **Note:** Both have identical logic (could be DRY'd up)

### 4. Why modify `state` in-place?
- Tool handlers receive `state` and can modify it
- Changes persist across tool calls within the same agent run
- Caller gets updated state back

### 5. Why catch tool exceptions?
- If handler crashes, we want to tell Claude about the error
- Claude can handle errors gracefully (retry, ask user, etc.)
- Better than crashing the entire agent

---

## Edge Cases Handled

### 1. No tools provided
```python
if tools:
    params["tools"] = tools
```
- If `tools=[]` or `tools=None`, don't include in request
- Claude just responds with text, no tool calls possible

### 2. Tool handler fails
```python
except Exception as e:
    tool_results.append(format_tool_error(tool_id, str(e)))
```
- Error sent back to Claude as tool result with `is_error: True`
- Claude sees the error and can respond appropriately

### 3. Multiple text blocks
```python
for block in response.content:
    if hasattr(block, 'text'):
        final_response += block.text
```
- Concatenates all text blocks
- Handles cases where Claude returns multiple text segments

### 4. Continuing conversations
```python
if conversation is None:
    conversation = []
```
- If `None`, start fresh
- If list provided, continue from that point

---

## What Could Be Improved?

### 1. Infinite loop protection
- No max iteration count
- If Claude keeps calling tools, could loop forever
- **Fix:** Add `max_iterations` parameter

### 2. DRY violation
- `run_agent()` and `run_agent_sync()` are identical
- Could extract common logic

### 3. Token limit handling
- If `stop_reason == "max_tokens"`, we still return response
- Might want to warn user or handle differently

### 4. Multiple tool calls in one response
- Current code handles this correctly (loops through blocks)
- But no explicit documentation of this capability

---

## Summary

**agent.py implements the agentic loop:**

```
User message
    ↓
┌─────────────────────┐
│  Send to Claude     │
└─────────────────────┘
    ↓
┌─────────────────────┐
│  Claude responds    │
└─────────────────────┘
    ↓
   Tool call? ──No──> Return response
    ↓ Yes
┌─────────────────────┐
│  Execute handlers   │
└─────────────────────┘
    ↓
┌─────────────────────┐
│  Send results back  │
└─────────────────────┘
    ↓
   (Loop back to top)
```

**This simple loop enables:**
- Autonomous tool use
- Multi-step reasoning
- Error recovery
- Conversational agents
- The entire propose→approve workflow

**It's ~70 lines that power the entire system!**
