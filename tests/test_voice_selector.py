"""
tests/test_voice_selector.py — Unit tests for ai/voice_selector.py

Tests:
  - Multilingual mode always returns single voice ID
  - Per-language mode returns correct voice per language
  - Hinglish falls back to Hindi voice
  - Gujlish falls back to Gujarati voice
  - Unknown language falls back to multilingual/EN voice
  - should_switch_voice() respects stable-switch logic
"""

from unittest.mock import patch, MagicMock

import pytest

import config
from ai import voice_selector
from state.conversation_state import ConversationState


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_state(
    current_language: str = "en",
    pending_lang: str | None = None,
    pending_count: int = 0,
    last_confidence: float = 0.90,
) -> ConversationState:
    state = ConversationState(call_sid="test-call-001")
    state.current_language = current_language
    state.pending_lang = pending_lang
    state.pending_lang_count = pending_count
    if last_confidence is not None:
        state.language_history = [{"language": current_language, "confidence": last_confidence, "source": "langdetect", "turn": 0}]
    return state


# ─── Multilingual Mode Tests ──────────────────────────────────────────────────


class TestMultilingualMode:
    def setup_method(self):
        self._orig_mode = config.VOICE_MODE
        config.VOICE_MODE = "multilingual"
        config.ELEVENLABS_VOICE_ID_MULTILINGUAL = "multilingual-voice-abc123"

    def teardown_method(self):
        config.VOICE_MODE = self._orig_mode

    def test_english_returns_multilingual_voice(self):
        voice_id = voice_selector.select_voice("en")
        assert voice_id == "multilingual-voice-abc123"

    def test_hindi_returns_multilingual_voice(self):
        voice_id = voice_selector.select_voice("hi")
        assert voice_id == "multilingual-voice-abc123"

    def test_hinglish_returns_multilingual_voice(self):
        voice_id = voice_selector.select_voice("hinglish")
        assert voice_id == "multilingual-voice-abc123"

    def test_gujarati_returns_multilingual_voice(self):
        voice_id = voice_selector.select_voice("gu")
        assert voice_id == "multilingual-voice-abc123"

    def test_unknown_language_returns_multilingual_voice(self):
        voice_id = voice_selector.select_voice("xyz-unknown")
        assert voice_id == "multilingual-voice-abc123"

    def test_should_switch_voice_always_false_in_multilingual_mode(self):
        state = _make_state()
        assert voice_selector.should_switch_voice(state) is False


# ─── Per-Language Mode Tests ──────────────────────────────────────────────────


class TestPerLanguageMode:
    def setup_method(self):
        self._orig_mode = config.VOICE_MODE
        config.VOICE_MODE = "per_language"
        config.ELEVENLABS_VOICE_ID_EN = "voice-en-001"
        config.ELEVENLABS_VOICE_ID_HI = "voice-hi-002"
        config.ELEVENLABS_VOICE_ID_GU = "voice-gu-003"
        config.ELEVENLABS_VOICE_ID_MULTILINGUAL = "voice-multi-000"
        # Rebuild VOICE_MAP for tests
        voice_selector._VOICE_MAP.update({
            "en":       "voice-en-001",
            "hi":       "voice-hi-002",
            "gu":       "voice-gu-003",
            "hinglish": "voice-hi-002",
            "gujlish":  "voice-gu-003",
        })

    def teardown_method(self):
        config.VOICE_MODE = self._orig_mode

    def test_english_voice_returned(self):
        assert voice_selector.select_voice("en") == "voice-en-001"

    def test_hindi_voice_returned(self):
        assert voice_selector.select_voice("hi") == "voice-hi-002"

    def test_gujarati_voice_returned(self):
        assert voice_selector.select_voice("gu") == "voice-gu-003"

    def test_hinglish_falls_back_to_hindi_voice(self):
        assert voice_selector.select_voice("hinglish") == "voice-hi-002"

    def test_gujlish_falls_back_to_gujarati_voice(self):
        assert voice_selector.select_voice("gujlish") == "voice-gu-003"

    def test_unknown_language_falls_back_to_multilingual(self):
        """Unknown language codes should not crash — fall back to multilingual."""
        voice_id = voice_selector.select_voice("martian")
        # Should fall back to multilingual
        assert voice_id == "voice-multi-000"


# ─── Voice Config Tests ───────────────────────────────────────────────────────


class TestGetVoiceConfig:
    def setup_method(self):
        self._orig_mode = config.VOICE_MODE
        config.VOICE_MODE = "multilingual"
        config.ELEVENLABS_VOICE_ID_MULTILINGUAL = "voice-multi-xyz"
        config.ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"

    def teardown_method(self):
        config.VOICE_MODE = self._orig_mode

    def test_voice_config_has_voice_id_and_model_id(self):
        cfg = voice_selector.get_voice_config("en")
        assert "voice_id" in cfg
        assert "model_id" in cfg
        assert cfg["model_id"] == "eleven_multilingual_v2"
        assert cfg["voice_id"] == "voice-multi-xyz"


# ─── Switching Guard Tests ────────────────────────────────────────────────────


class TestShouldSwitchVoice:
    def setup_method(self):
        self._orig_mode = config.VOICE_MODE
        config.VOICE_MODE = "per_language"
        config.LANGUAGE_SWITCH_CONFIDENCE = 0.80

    def teardown_method(self):
        config.VOICE_MODE = self._orig_mode

    def test_no_switch_when_pending_lang_still_set(self):
        """If pending_lang is still set, switch not yet committed."""
        state = _make_state(pending_lang="hi", pending_count=1, last_confidence=0.90)
        assert voice_selector.should_switch_voice(state) is False

    def test_switch_approved_after_commit(self):
        """pending_lang=None + pending_count=0 = switch was committed."""
        state = _make_state(pending_lang=None, pending_count=0, last_confidence=0.92)
        assert voice_selector.should_switch_voice(state) is True

    def test_no_switch_on_low_confidence(self):
        """Even if committed, low confidence means no switch."""
        state = _make_state(pending_lang=None, pending_count=0, last_confidence=0.70)
        assert voice_selector.should_switch_voice(state) is False

    def test_no_switch_empty_history(self):
        state = ConversationState(call_sid="test-empty")
        assert voice_selector.should_switch_voice(state) is False
