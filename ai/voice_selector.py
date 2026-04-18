"""
ai/voice_selector.py — ElevenLabs voice selection based on detected language.

Supports two modes (configured via VOICE_MODE env var):
  - "multilingual"  → Single multilingual voice for all languages (MVP default).
                       Fastest, works well with mixed-language text.
  - "per_language"  → Separate ElevenLabs voice per language code.
                       More natural but requires separate voice IDs.

Voice switching guard:
  should_switch_voice() ensures we don't swap voices mid-sentence.
  A switch is only approved when:
    - The conversation language has been stable for >= LANGUAGE_SWITCH_TURNS turns
    - The last detection had confidence > LANGUAGE_SWITCH_CONFIDENCE
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import config

if TYPE_CHECKING:
    from state.conversation_state import ConversationState

logger = logging.getLogger(__name__)

# ─── Voice Map (per-language mode) ────────────────────────────────────────────

_VOICE_MAP: dict[str, str] = {
    "en":       config.ELEVENLABS_VOICE_ID_EN or config.ELEVENLABS_VOICE_ID_MULTILINGUAL,
    "hi":       config.ELEVENLABS_VOICE_ID_HI or config.ELEVENLABS_VOICE_ID_MULTILINGUAL,
    "gu":       config.ELEVENLABS_VOICE_ID_GU or config.ELEVENLABS_VOICE_ID_MULTILINGUAL,
    "hinglish": config.ELEVENLABS_VOICE_ID_HI or config.ELEVENLABS_VOICE_ID_MULTILINGUAL,
    "gujlish":  config.ELEVENLABS_VOICE_ID_GU or config.ELEVENLABS_VOICE_ID_MULTILINGUAL,
}

# ─── Public API ───────────────────────────────────────────────────────────────


def select_voice(language: str) -> str:
    """
    Return the ElevenLabs voice ID to use for the given language.

    In "multilingual" mode (MVP): always returns the single multilingual voice.
    In "per_language" mode: looks up language-specific voice, falls back to EN.

    Args:
        language: Language code (en/hi/gu/hinglish/gujlish).

    Returns:
        ElevenLabs voice ID string.
    """
    if config.VOICE_MODE == "multilingual":
        voice_id = config.ELEVENLABS_VOICE_ID_MULTILINGUAL
        if not voice_id:
            logger.error(
                "ELEVENLABS_VOICE_ID_MULTILINGUAL is not set! "
                "Add it to your .env file."
            )
        logger.debug("Voice mode=multilingual → voice_id=%s", voice_id)
        return voice_id

    # per_language mode
    voice_id = _VOICE_MAP.get(language)
    if not voice_id:
        logger.warning(
            "No voice configured for language '%s'. "
            "Falling back to multilingual voice.",
            language,
        )
        voice_id = config.ELEVENLABS_VOICE_ID_MULTILINGUAL

    logger.debug("Voice mode=per_language | lang=%s → voice_id=%s", language, voice_id)
    return voice_id


def should_switch_voice(state: "ConversationState") -> bool:
    """
    Determine whether it is safe to switch to a new voice.

    Designed to prevent jarring mid-sentence voice changes.
    Returns True only when:
      1. The conversation has had a confirmed stable language change.
      2. The last recorded detection had confidence > LANGUAGE_SWITCH_CONFIDENCE.
      3. The pending language counter is reset (switch already committed in state).

    In "multilingual" mode this always returns False (one voice, no switching needed).

    Args:
        state: Current ConversationState.

    Returns:
        True if voice should change, False to keep current voice.
    """
    if config.VOICE_MODE == "multilingual":
        return False

    if not state.language_history:
        return False

    last = state.language_history[-1]
    confident_enough = last.get("confidence", 0.0) >= config.LANGUAGE_SWITCH_CONFIDENCE

    # pending_lang_count == 0 means a switch was recently committed
    switch_was_committed = state.pending_lang is None and state.pending_lang_count == 0

    return confident_enough and switch_was_committed


def get_voice_config(language: str) -> dict:
    """
    Return the full ElevenLabs generation config for a given language.

    Includes voice_id and model_id.
    """
    return {
        "voice_id": select_voice(language),
        "model_id": config.ELEVENLABS_MODEL_ID,
    }
