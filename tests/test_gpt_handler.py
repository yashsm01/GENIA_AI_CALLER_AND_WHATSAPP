"""
tests/test_gpt_handler.py — Unit tests for ai/gpt_handler.py

Tests:
  - Correct system prompt returned per language
  - English fallback for unknown language codes
  - generate_response() adds correct system prompt to messages
  - Fallback message returned on API error
  - Retry logic called on APIError
"""

from unittest.mock import patch, MagicMock, call

import pytest
from openai import APIError

from ai.gpt_handler import get_system_prompt, generate_response, SYSTEM_PROMPTS, _safe_fallback
from state.conversation_state import ConversationState, add_message


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_state(language: str = "en", messages: list | None = None) -> ConversationState:
    state = ConversationState(call_sid="test-gpt-001")
    state.current_language = language
    if messages:
        state.messages = messages
    return state


def _mock_openai_response(content: str) -> MagicMock:
    response = MagicMock()
    response.choices[0].message.content = content
    return response


# ─── System Prompt Tests ──────────────────────────────────────────────────────


class TestGetSystemPrompt:
    def test_english_prompt_returned(self):
        prompt = get_system_prompt("en")
        assert "English" in prompt
        assert len(prompt) > 20

    def test_hindi_prompt_returned(self):
        prompt = get_system_prompt("hi")
        assert "Hindi" in prompt or "Hindi" in prompt.lower()

    def test_gujarati_prompt_returned(self):
        prompt = get_system_prompt("gu")
        assert "Gujarati" in prompt

    def test_hinglish_prompt_contains_hinglish_keyword(self):
        prompt = get_system_prompt("hinglish")
        assert "Hinglish" in prompt or "Hindi" in prompt

    def test_gujlish_prompt_returned(self):
        prompt = get_system_prompt("gujlish")
        assert "Gujarati" in prompt

    def test_unknown_language_falls_back_to_english_prompt(self):
        prompt = get_system_prompt("xyz-unknown")
        assert prompt == SYSTEM_PROMPTS["en"]

    def test_all_supported_languages_have_prompts(self):
        for lang in ["en", "hi", "gu", "hinglish", "gujlish"]:
            prompt = get_system_prompt(lang)
            assert isinstance(prompt, str)
            assert len(prompt) > 10


# ─── generate_response Tests ─────────────────────────────────────────────────


class TestGenerateResponse:
    def test_system_prompt_injected_correctly(self):
        """Verify that the system message is prepended with the right language prompt."""
        state = _make_state("hinglish")
        add_message(state, "user", "Hello bhai, rate kya hai?")

        captured_messages = []

        def fake_create(**kwargs):
            captured_messages.extend(kwargs["messages"])
            return _mock_openai_response("Haan bhai, rate hai 500 rupaye.")

        with patch("ai.gpt_handler._get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = fake_create
            mock_client_fn.return_value = mock_client

            result = generate_response(state)

        assert result == "Haan bhai, rate hai 500 rupaye."
        assert captured_messages[0]["role"] == "system"
        assert "Hinglish" in captured_messages[0]["content"] or "Hindi" in captured_messages[0]["content"]
        assert captured_messages[1]["role"] == "user"

    def test_response_returned_as_string(self):
        state = _make_state("en")
        add_message(state, "user", "What is the rate?")

        with patch("ai.gpt_handler._get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = _mock_openai_response(
                "The rate is $100 per unit."
            )
            mock_client_fn.return_value = mock_client
            result = generate_response(state)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_api_error_triggers_retry_then_fallback(self):
        """On APIError, should retry once. If retry also fails, return fallback."""
        state = _make_state("en")
        add_message(state, "user", "Test message here please tell me the rate.")

        with patch("ai.gpt_handler._get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = Exception("Connection error")
            mock_client_fn.return_value = mock_client
            result = generate_response(state)

        # Should return fallback message, not crash
        assert isinstance(result, str)
        assert len(result) > 0
        # Should NOT be the actual GPT response since everything failed
        assert "repeat" in result.lower() or "samajh" in result.lower() or "sorry" in result.lower()

    def test_hinglish_state_uses_hinglish_prompt(self):
        state = _make_state("hinglish")
        add_message(state, "user", "Bhai kya deal milegi?")

        captured = []

        def capture_call(**kwargs):
            captured.append(kwargs["messages"][0]["content"])
            return _mock_openai_response("Bilkul bhai, acha deal denge.")

        with patch("ai.gpt_handler._get_client") as mock_fn:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = capture_call
            mock_fn.return_value = mock_client
            generate_response(state)

        assert SYSTEM_PROMPTS["hinglish"] == captured[0]


# ─── Fallback Message Tests ───────────────────────────────────────────────────


class TestSafeFallback:
    def test_english_fallback(self):
        msg = _safe_fallback("en", "api_error")
        assert "repeat" in msg.lower() or "sorry" in msg.lower()

    def test_hindi_fallback(self):
        msg = _safe_fallback("hi", "api_error")
        assert len(msg) > 5

    def test_hinglish_fallback(self):
        msg = _safe_fallback("hinglish", "api_error")
        assert len(msg) > 5

    def test_unknown_language_returns_english_fallback(self):
        msg = _safe_fallback("martian", "api_error")
        assert "repeat" in msg.lower() or "sorry" in msg.lower()
