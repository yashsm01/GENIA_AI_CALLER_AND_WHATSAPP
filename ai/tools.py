"""
ai/tools.py — OpenAI Tool Calling schema and execution router.

Defines the tool "contracts" that GPT-4o can call during a conversation.
The AI can choose to call these tools when it needs to take an action.

Current tools:
  - send_document: Ask the Master Manager to send a brochure via WhatsApp or Email.
  - ask_for_email:  Signal that the AI needs the user to provide their email address.

Flow:
  1. GPT decides to call a tool → returns finish_reason="tool_calls".
  2. gpt_handler.py extracts the arguments from the response.
  3. execute_tool() is called here → routes to services/messaging.py.
  4. The result is fed back to GPT as a tool message.
  5. GPT generates a spoken response acknowledging the action.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from services import messaging

if TYPE_CHECKING:
    from state.conversation_state import ConversationState

logger = logging.getLogger(__name__)

# ─── Available Documents (built dynamically from Master Catalog) ───────────────

_AVAILABLE_DOCS = messaging.get_available_documents()

# ─── OpenAI Tool Schemas ─────────────────────────────────────────────────────
#
# These JSON structures are passed to OpenAI's API.
# They define what tools the AI is aware of and what arguments it can pass.

OPENAI_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "send_document",
            "description": (
                "Send a product brochure or document to the user via WhatsApp or Email. "
                "Use this when the user requests a brochure, catalog, or document. "
                "Always confirm the document type and delivery method before calling this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_type": {
                        "type": "string",
                        "description": f"The type of document to send. Must be one of: {', '.join(_AVAILABLE_DOCS)}.",
                        "enum": _AVAILABLE_DOCS,
                    },
                    "method": {
                        "type": "string",
                        "description": "Delivery method — 'whatsapp' sends to the caller's phone, 'email' sends to their email address.",
                        "enum": ["whatsapp", "email"],
                    },
                    "email_address": {
                        "type": "string",
                        "description": "Required only when method is 'email'. The user's email address.",
                    },
                },
                "required": ["document_type", "method"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end_call_gracefully",
            "description": (
                "Signal that the conversation is complete and the call should be ended. "
                "Use this when the user says goodbye, thank you, or indicates they are done. "
                "Do NOT use this unless you are sure the user wants to end the call."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Brief reason the call is ending (e.g. 'User said goodbye').",
                    },
                },
                "required": ["reason"],
            },
        },
    },
]


# ─── Tool Execution Router ────────────────────────────────────────────────────


def execute_tool(
    tool_name: str,
    arguments: dict,
    state: "ConversationState",
) -> str:
    """
    Route a GPT tool call to the correct Python function.

    Args:
        tool_name:  Name of the tool (must match one of OPENAI_TOOLS function names).
        arguments:  Arguments dict parsed from the GPT tool call JSON.
        state:      Current ConversationState (provides caller_number, call_sid, etc.)

    Returns:
        String result to feed back to GPT as the tool response message.
    """
    logger.info(
        "[%s] Executing tool: '%s' with args: %s",
        state.call_sid, tool_name, arguments,
    )

    if tool_name == "send_document":
        return _handle_send_document(arguments, state)

    elif tool_name == "end_call_gracefully":
        reason = arguments.get("reason", "User requested end of call.")
        logger.info("[%s] End call requested. Reason: %s", state.call_sid, reason)
        # Signal to call_handler via a special return value
        state.actions_taken.append({"action": "end_call", "reason": reason})
        return f"Call end signaled. Reason: {reason}"

    else:
        logger.warning("[%s] Unknown tool called: '%s'", state.call_sid, tool_name)
        return f"Error: Unknown tool '{tool_name}'."


def _handle_send_document(arguments: dict, state: "ConversationState") -> str:
    """Handle the send_document tool call."""
    document_type = arguments.get("document_type", "").lower().strip()
    method = arguments.get("method", "whatsapp").lower().strip()
    email_address = arguments.get("email_address", "").strip()

    if not document_type:
        return "Error: No document type specified."

    if method == "whatsapp":
        result = messaging.send_whatsapp(state, document_type)
    elif method == "email":
        if not email_address:
            return "Error: Email address is required for email delivery. Please ask the user for their email address first."
        result = messaging.send_email(state, document_type, email_address)
    else:
        return f"Error: Unknown delivery method '{method}'. Use 'whatsapp' or 'email'."

    # Log to state
    from state.conversation_state import log_action
    log_action(
        state,
        action=f"send_document:{document_type}:{method}",
        result="success" if result["success"] else "failed",
    )

    return result["message"]


def parse_tool_calls(response_message) -> list[dict]:
    """
    Parse tool calls from a GPT response message object.

    Returns a list of dicts: [{"id": ..., "name": ..., "arguments": {...}}, ...]
    """
    tool_calls = []
    if not hasattr(response_message, "tool_calls") or not response_message.tool_calls:
        return tool_calls

    for tc in response_message.tool_calls:
        try:
            args = json.loads(tc.function.arguments)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse tool call arguments: %s | Raw: %s", exc, tc.function.arguments)
            args = {}

        tool_calls.append({
            "id": tc.id,
            "name": tc.function.name,
            "arguments": args,
        })

    return tool_calls
