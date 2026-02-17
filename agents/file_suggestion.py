"""File Suggestion Agent - classifies data files for the knowledge graph pipeline."""

from core import run_agent_sync
from core.tracing import traceable
from tools import (
    TOOL_GET_APPROVED_USER_GOAL,
    TOOL_LIST_AVAILABLE_FILES,
    TOOL_GET_FILE_INFO,
    TOOL_SAMPLE_FILE,
    TOOL_SET_PROPOSED_FILES,
    TOOL_APPROVE_PROPOSED_FILES,
    handle_get_approved_user_goal,
    handle_list_available_files,
    handle_get_file_info,
    handle_sample_file,
    handle_set_proposed_files,
    handle_approve_proposed_files,
)
from tools.file_tools import (
    TOOL_GET_APPROVED_COMPETENCY_QUESTIONS,
    handle_get_approved_competency_questions,
)


SYSTEM_PROMPT = """\
You are the File Suggestion Agent, a data classification specialist for knowledge graph construction.

YOUR JOB:
Examine available data files and classify them for the knowledge graph pipeline:
- Structured files (CSV) -> used for the domain/entity graph
- Unstructured files (markdown/text) -> used for the lexical/subject graph

WORKFLOW:
1. FIRST: Call get_approved_user_goal to understand what the user wants to build.
   If there is no approved goal, tell the user Stage 1 must be completed first.
   Also call get_approved_competency_questions to see what questions the graph must answer.
2. Call list_available_files to see what data is available.
3. Call get_file_info for EACH file to understand its contents (columns, headings, etc.).
4. Only call sample_file if get_file_info is not enough to classify a file.
5. Call set_proposed_files with your classification, explaining why each file is relevant.
6. Present the proposal clearly to the user and ask for feedback.
7. If the user suggests changes, update with set_proposed_files again.
   If the files were previously approved, you MUST call approve_proposed_files
   again after the user confirms the updated classification.
8. ONLY call approve_proposed_files when the user explicitly approves
   (says "approve", "looks good", "yes", or similar).

CLASSIFICATION RULES:
- CSV files -> structured (used for entity/relationship extraction)
- Markdown/text files -> unstructured (used for NER and lexical analysis)
- For each file, explain HOW it connects to the user's goal
- If a file seems irrelevant, still include it but note that

MOVE-ON RULE:
- Whenever you ask clarifying questions, end with a reminder like:
  "Or say 'move on' if you'd like me to proceed with what I have so far."
- When the user says "move on", "skip", "proceed", "that's enough", or similar:
  STOP asking questions immediately.
  Use your best judgment to classify files based on what you already know.
  Call set_proposed_files with your best classification and present it for approval.
- The user can still refine or reject the proposal.

QUALITY GUIDELINES:
- Every file entry must have a 'path' and a 'reason'
- Reasons should reference the user's goal specifically
- Be concise but informative in explanations
- Group files logically when presenting to the user

Be professional and ensure the user approves before finalizing."""


TOOLS = [
    TOOL_GET_APPROVED_USER_GOAL,
    TOOL_GET_APPROVED_COMPETENCY_QUESTIONS,
    TOOL_LIST_AVAILABLE_FILES,
    TOOL_GET_FILE_INFO,
    TOOL_SAMPLE_FILE,
    TOOL_SET_PROPOSED_FILES,
    TOOL_APPROVE_PROPOSED_FILES,
]

TOOL_HANDLERS = {
    "get_approved_user_goal": handle_get_approved_user_goal,
    "get_approved_competency_questions": handle_get_approved_competency_questions,
    "list_available_files": handle_list_available_files,
    "get_file_info": handle_get_file_info,
    "sample_file": handle_sample_file,
    "set_proposed_files": handle_set_proposed_files,
    "approve_proposed_files": handle_approve_proposed_files,
}


class FileSuggestionAgent:
    """Agent that classifies data files for the knowledge graph pipeline."""

    def __init__(self):
        self.system_prompt = SYSTEM_PROMPT
        self.tools = TOOLS
        self.tool_handlers = TOOL_HANDLERS

    @traceable(name="file_suggestion.run")
    def run(self, message: str, state: dict, conversation: list = None) -> tuple[str, dict, list]:
        """Run a conversation turn with the agent.

        Args:
            message: User's message.
            state: Current state dictionary.
            conversation: Conversation history (None to start fresh).

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
