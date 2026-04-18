"""
state/conversation_state.py — Per-call conversation memory.

Tracks:
  - Current language (with stable-switch logic)
  - Language history (rolling detections)
  - GPT message history (user/assistant turns)

Language switching rules (prevents jarring mid-call switches):
  - New detection must have confidence > LANGUAGE_SWITCH_CONFIDENCE
  - Same new language must be detected for >= LANGUAGE_SWITCH_TURNS consecutive turns
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import config

if TYPE_CHECKING:
    from ai.language_detector import DetectionResult

logger = logging.getLogger(__name__)


# ─── Data Model ───────────────────────────────────────────────────────────────


@dataclass
class ConversationState:
    """
    Holds all per-call state for a single phone call session.

    Attributes:
        call_sid:              Unique Twilio call SID.
        current_language:      Active language code (en/hi/gu/hinglish/gujlish).
        language_history:      Rolling list of per-turn DetectionResult objects.
        messages:              GPT message history [{role, content}, ...].
        pending_lang:          Language code being evaluated for stable switch.
        pending_lang_count:    How many consecutive turns pending_lang was seen.
        turn_count:            Total number of completed conversation turns.
    """

    call_sid: str
    current_language: str = field(default_factory=lambda: config.DEFAULT_LANGUAGE)
    language_history: list[dict] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    pending_lang: str | None = None
    pending_lang_count: int = 0
    turn_count: int = 0


# ─── Factory ──────────────────────────────────────────────────────────────────


def create_state(call_sid: str) -> ConversationState:
    """Create a fresh ConversationState for a new call."""
    logger.info("Creating conversation state for call: %s", call_sid)
    return ConversationState(call_sid=call_sid)


# ─── State Mutations ──────────────────────────────────────────────────────────


def update_language(state: ConversationState, result: "DetectionResult") -> bool:
    """
    Evaluate a DetectionResult and potentially update state.current_language.

    Switching logic:
      1. Always record the detection in history.
      2. Skip if result.source == "skipped" (short text fallback).
      3. If new language == current → reset pending counter.
      4. If new language != current:
           - If confidence < LANGUAGE_SWITCH_CONFIDENCE → ignore.
           - If same as pending_lang → increment counter.
           - If counter >= LANGUAGE_SWITCH_TURNS → commit switch.
           - Else → start tracking as pending.

    Returns:
        True if current_language was changed, False otherwise.
    """
    detection_record = {
        "language": result.language,
        "confidence": result.confidence,
        "source": result.source,
        "turn": state.turn_count,
    }
    state.language_history.append(detection_record)

    # Skipped detection (short text) — trust current language
    if result.source == "skipped":
        logger.debug("[%s] Skipped detection, keeping: %s", state.call_sid, state.current_language)
        return False

    new_lang = result.language

    # ── Same as current language → stable, reset pending ─────────────────────
    if new_lang == state.current_language:
        state.pending_lang = None
        state.pending_lang_count = 0
        return False

    # ── Confidence too low → ignore ───────────────────────────────────────────
    if result.confidence < config.LANGUAGE_SWITCH_CONFIDENCE:
        logger.debug(
            "[%s] Low confidence (%.2f) for '%s', ignoring switch.",
            state.call_sid,
            result.confidence,
            new_lang,
        )
        return False

    # ── Track pending switch ──────────────────────────────────────────────────
    if state.pending_lang == new_lang:
        state.pending_lang_count += 1
    else:
        # New candidate language
        state.pending_lang = new_lang
        state.pending_lang_count = 1

    logger.debug(
        "[%s] Pending language '%s' count: %d/%d",
        state.call_sid,
        state.pending_lang,
        state.pending_lang_count,
        config.LANGUAGE_SWITCH_TURNS,
    )

    # ── Commit switch if stable ───────────────────────────────────────────────
    if state.pending_lang_count >= config.LANGUAGE_SWITCH_TURNS:
        old_lang = state.current_language
        state.current_language = new_lang
        state.pending_lang = None
        state.pending_lang_count = 0
        logger.info(
            "[%s] Language switched: %s → %s (confidence: %.2f)",
            state.call_sid,
            old_lang,
            new_lang,
            result.confidence,
        )
        return True

    return False


def add_message(state: ConversationState, role: str, content: str) -> None:
    """
    Append a message to GPT conversation history.

    Args:
        state:   The ConversationState to modify.
        role:    "user" or "assistant"
        content: Message text
    """
    state.messages.append({"role": role, "content": content})
    logger.debug("[%s] Added %s message (%d chars)", state.call_sid, role, len(content))


def increment_turn(state: ConversationState) -> None:
    """Increment the turn counter. Call after each complete user → assistant exchange."""
    state.turn_count += 1


def reset(state: ConversationState) -> None:
    """Reset state for reuse (e.g., if call reconnects with same SID)."""
    state.current_language = config.DEFAULT_LANGUAGE
    state.language_history.clear()
    state.messages.clear()
    state.pending_lang = None
    state.pending_lang_count = 0
    state.turn_count = 0
    logger.info("[%s] State reset.", state.call_sid)


def get_summary(state: ConversationState) -> dict:
    """Return a loggable summary of the conversation state."""
    return {
        "call_sid": state.call_sid,
        "current_language": state.current_language,
        "turn_count": state.turn_count,
        "message_count": len(state.messages),
        "last_detection": state.language_history[-1] if state.language_history else None,
    }
