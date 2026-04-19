"""
ai/gpt_handler.py — GPT conversation handler with dynamic language-aware prompts.

Injects a language-specific system prompt based on conversation state,
then calls OpenAI Chat Completions to generate the AI caller's response.

Language → System Prompt mapping:
  en        → English only, professional
  hi        → Hindi only (Devanagari/Roman-script natural)
  gu        → Gujarati only
  hinglish  → Natural Hinglish mix, mirrors user style
  gujlish   → Natural Gujarati-English mix
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from openai import OpenAI, APIError, RateLimitError
from openai.types.chat import ChatCompletionMessage

import config
from ai import tools

if TYPE_CHECKING:
    from state.conversation_state import ConversationState

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Lazy-initialize the OpenAI client."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


# ─── System Prompts ───────────────────────────────────────────────────────────

# We add explicit instructions about tools to each prompt.
_TOOL_INSTRUCTIONS = (
    "CONVERSATION RULE: If the user greets you (hello, hi, hey), respond with a friendly greeting and ask how you can help. Do not jump immediately into a product explanation.\n\n"
    "You have the ability to send product brochures/documents (Fan or Wire) "
    "via WhatsApp or Email using your tools. "
    "If the user asks for a brochure, catalog, or details about products, "
    "proactively ask them which one they want (Fan or Wire) and how they want it (WhatsApp or Email). "
    "Once they confirm, USE THE 'send_document' TOOL to send it. Do not pretend to send it, actually use the tool."
)

SYSTEM_PROMPTS: dict[str, str] = {
    "en": (
        "You are an AI caller assistant. "
        "Respond ONLY in English. "
        "Be concise, professional, and natural — like a real human agent on the phone. "
        "Keep responses under 3 sentences unless more detail is necessary. "
        "Never sound robotic or scripted.\n\n"
        f"INSTRUCTIONS: {_TOOL_INSTRUCTIONS}"
    ),
    "hi": (
        "Aap ek AI caller assistant hain. "
        "Sirf Hindi mein jawaab dijiye — chahe Roman script ho ya Devanagari. "
        "Seedha, professional aur natural boliye jaise asli insaan phone par baat karta hai. "
        "Jawaab 3 sentence se zyada lamba mat karo jab tak zaruri na ho. "
        "Robotic ya scripted mat lagiye.\n\n"
        f"INSTRUCTIONS: {_TOOL_INSTRUCTIONS}"
    ),
    "gu": (
        "Tame ek AI caller assistant cho. "
        "Faqt Gujarati ma jawab apo — chahe Roman script hoy ke Gujarati lipi. "
        "Saral, professional ane svabhavik raho jeva ke phone par sacho manushya hoy. "
        "3 vakyathi vadhu lambo jawab na apo jyare jaruri na hoy. "
        "Robotic ke scripted na lagvo.\n\n"
        f"INSTRUCTIONS: {_TOOL_INSTRUCTIONS}"
    ),
    "hinglish": (
        "You are an AI caller assistant. "
        "Respond in Hinglish — a natural, fluid mix of Hindi and English "
        "just like an educated Indian speaker would on a phone call. "
        "Mirror the user's language style: if they say 'bhai rate kya hai?', "
        "you reply naturally like 'Haan bhai, rate hai ₹500 per unit — aur discount bhi milega.' "
        "Keep it conversational, warm, and human. Do NOT sound robotic or formal. "
        "Avoid forcing pure Hindi or pure English — mix naturally. "
        "Keep responses under 3 sentences unless more detail is needed.\n\n"
        f"INSTRUCTIONS: {_TOOL_INSTRUCTIONS}"
    ),
    "gujlish": (
        "You are an AI caller assistant. "
        "Respond in a natural Gujarati-English mix (Gujlish), "
        "just like a Gujarati speaker would naturally converse on a phone call. "
        "Mirror the user's language style: if they mix Gujarati and English, you do the same. "
        "Keep it warm, conversational, and human. Do NOT sound robotic. "
        "Keep responses under 3 sentences unless more detail is needed.\n\n"
        f"INSTRUCTIONS: {_TOOL_INSTRUCTIONS}"
    ),
}

_DEFAULT_PROMPT = SYSTEM_PROMPTS["en"]


# ─── Public API ───────────────────────────────────────────────────────────────


def get_system_prompt(language: str) -> str:
    """
    Return the system prompt for the given language code.
    Falls back to English if the language is unsupported.
    """
    prompt = SYSTEM_PROMPTS.get(language, _DEFAULT_PROMPT)
    if language not in SYSTEM_PROMPTS:
        logger.warning(
            "Unknown language '%s' for system prompt, falling back to English.", language
        )
    return prompt


def generate_response(state: "ConversationState") -> str:
    """
    Generate an AI response for the current conversation turn.

    Handles tool calls inside a loop. If GPT decides to call a tool,
    it executes the tool, feeds the result back, and calls GPT again
    so it can speak the result.

    Args:
        state: Current ConversationState (contains language + message history).

    Returns:
        Assistant reply as a plain string.
        Returns a safe fallback message on API failure.
    """
    system_prompt = get_system_prompt(state.current_language)
    messages = [{"role": "system", "content": system_prompt}] + list(state.messages)

    client = _get_client()
    max_loops = 3
    loop_count = 0

    while loop_count < max_loops:
        loop_count += 1
        logger.info(
            "[%s] Calling GPT (Loop %d | lang=%s | turns=%d)",
            state.call_sid,
            loop_count,
            state.current_language,
            state.turn_count,
        )

        try:
            response = client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=messages, # type: ignore
                temperature=config.GPT_TEMPERATURE,
                max_tokens=config.GPT_MAX_TOKENS,
                tools=tools.OPENAI_TOOLS,
                tool_choice="auto",
            )
        except RateLimitError:
            logger.error("[%s] GPT rate limit hit.", state.call_sid)
            return _safe_fallback(state.current_language, "rate_limit")
        except APIError as exc:
            logger.error("[%s] GPT API error: %s.", state.call_sid, exc)
            return _safe_fallback(state.current_language, "api_error")
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] Unexpected GPT error: %s", state.call_sid, exc)
            return _safe_fallback(state.current_language, "unknown")

        message: ChatCompletionMessage = response.choices[0].message
        
        # --- Handle Tool Calls ---
        if message.tool_calls:
            logger.info("[%s] GPT called %d tools.", state.call_sid, len(message.tool_calls))
            
            # Need to append the assistant's message with tool_calls exactly as it came
            # to maintain conversation history validity
            msg_dict = message.model_dump(exclude_unset=True)
            messages.append(msg_dict)
            state.messages.append(msg_dict)

            parsed_calls = tools.parse_tool_calls(message)
            for tc in parsed_calls:
                # Execute tool safely
                try:
                    result_str = tools.execute_tool(tc["name"], tc["arguments"], state)
                except Exception as exc:  # noqa: BLE001
                    logger.error("[%s] Error executing tool %s: %s", state.call_sid, tc["name"], exc)
                    result_str = f"Error: Tool execution failed due to an internal error ({exc}). Please apologize to the user and offer an alternative."
                
                # Append tool result to messages
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["name"],
                    "content": result_str,
                }
                messages.append(tool_msg)
                state.messages.append(tool_msg)
            
            # Loop continues to call GPT again with the new tool context
            continue

        # --- Normal Response ---
        reply = message.content or ""
        reply = reply.strip()
        logger.info("[%s] GPT reply (%d chars): %s", state.call_sid, len(reply), reply[:80])
        return reply

    # If we hit max_loops
    logger.warning("[%s] Max tool loops reached.", state.call_sid)
    return "Okay, I think I've sorted that out for you."


def _safe_fallback(language: str, reason: str) -> str:
    """Return a language-appropriate fallback message when GPT fails."""
    logger.warning("Using fallback response. Reason: %s, Language: %s", reason, language)
    fallbacks = {
        "en":       "I'm sorry, I didn't catch that. Could you please repeat?",
        "hi":       "Mujhe samajh nahi aaya. Kya aap dobara bol sakte hain?",
        "gu":       "Mane samjayu nahi. Krupaya fari kehso?",
        "hinglish": "Sorry yaar, samjha nahi. Ek baar phir bologe?",
        "gujlish":  "Sorry, samjyun nahi. Ek vaar fari kehso?",
    }
    return fallbacks.get(language, fallbacks["en"])
