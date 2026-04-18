"""
tests/test_language_detector.py — Unit tests for ai/language_detector.py

Tests:
  - English-only text detection
  - Hindi detection (Devanagari)
  - Hinglish (mixed Hindi + English)
  - Gujarati detection
  - Short text (<3 words) → skipped, returns current_language
  - GPT fallback triggered on low-confidence text
  - Fallback result is a valid supported language code
"""

from unittest.mock import patch, MagicMock

import pytest

from ai.language_detector import detect, DetectionResult, SUPPORTED_LANGUAGES


# ─── Fixtures ─────────────────────────────────────────────────────────────────


def make_lang_result(lang: str, prob: float):
    """Create a mock langdetect language probability object."""
    m = MagicMock()
    m.lang = lang
    m.prob = prob
    return m


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestEnglishDetection:
    def test_clear_english_text(self):
        with patch("ai.language_detector.detect_langs") as mock_detect:
            mock_detect.return_value = [make_lang_result("en", 0.98)]
            result = detect("Hello, what is the rate for the product?")

        assert result.language == "en"
        assert result.confidence >= 0.90
        assert result.source == "langdetect"

    def test_english_returns_no_gpt_call(self):
        with (
            patch("ai.language_detector.detect_langs") as mock_detect,
            patch("ai.language_detector._call_gpt_fallback") as mock_gpt,
        ):
            mock_detect.return_value = [make_lang_result("en", 0.99)]
            detect("Good morning, I need information about your services.")

        mock_gpt.assert_not_called()


class TestHindiDetection:
    def test_devanagari_hindi(self):
        with patch("ai.language_detector.detect_langs") as mock_detect:
            mock_detect.return_value = [make_lang_result("hi", 0.95)]
            result = detect("नमस्ते, आपकी सेवा के बारे में बताइए।")

        assert result.language == "hi"
        assert result.confidence >= 0.85
        assert result.source == "langdetect"

    def test_roman_hindi_low_confidence_triggers_gpt(self):
        """Roman-script Hindi often has low confidence — should trigger GPT fallback."""
        with (
            patch("ai.language_detector.detect_langs") as mock_detect,
            patch("ai.language_detector._call_gpt_fallback") as mock_gpt,
        ):
            mock_detect.return_value = [make_lang_result("hi", 0.55)]
            mock_gpt.return_value = DetectionResult(language="hi", confidence=0.80, source="gpt")
            result = detect("Bhai rate kya hai aapka?", current_language="en")

        mock_gpt.assert_called_once()
        assert result.language == "hi"


class TestHinglishDetection:
    def test_classic_hinglish(self):
        """Both EN and HI scores above threshold → hinglish."""
        with patch("ai.language_detector.detect_langs") as mock_detect:
            mock_detect.return_value = [
                make_lang_result("en", 0.52),
                make_lang_result("hi", 0.40),
            ]
            result = detect("Hello bhai kya rate hai?")

        assert result.language == "hinglish"
        assert result.source == "langdetect"

    def test_hinglish_confidence_is_combined(self):
        with patch("ai.language_detector.detect_langs") as mock_detect:
            mock_detect.return_value = [
                make_lang_result("en", 0.45),
                make_lang_result("hi", 0.45),
            ]
            result = detect("Ek minute yaar, main check karta hoon the details.")

        assert result.language == "hinglish"
        assert result.confidence > 0.0


class TestGujlishDetection:
    def test_gujarati_english_mix(self):
        with patch("ai.language_detector.detect_langs") as mock_detect:
            mock_detect.return_value = [
                make_lang_result("en", 0.40),
                make_lang_result("gu", 0.35),
            ]
            result = detect("Kem cho bhai, rate su che product no?")

        assert result.language == "gujlish"
        assert result.source == "langdetect"


class TestGujaratiDetection:
    def test_pure_gujarati(self):
        with patch("ai.language_detector.detect_langs") as mock_detect:
            mock_detect.return_value = [make_lang_result("gu", 0.92)]
            result = detect("નમસ્તે, આ પ્રોડક્ટ નો ભાવ શું છે?")

        assert result.language == "gu"
        assert result.confidence >= 0.85


class TestShortTextHandling:
    def test_single_word_returns_current_language(self):
        result = detect("OK", current_language="hinglish")
        assert result.language == "hinglish"
        assert result.source == "skipped"
        assert result.confidence == 1.0

    def test_two_words_returns_current_language(self):
        result = detect("Sure yaar", current_language="hi")
        assert result.language == "hi"
        assert result.source == "skipped"

    def test_empty_string_returns_current_language(self):
        result = detect("", current_language="en")
        assert result.language == "en"
        assert result.source == "skipped"

    def test_whitespace_only_returns_current_language(self):
        result = detect("   ", current_language="gu")
        assert result.language == "gu"
        assert result.source == "skipped"


class TestGPTFallback:
    def test_gpt_fallback_triggered_on_low_confidence(self):
        with (
            patch("ai.language_detector.detect_langs") as mock_detect,
            patch("ai.language_detector._call_gpt_fallback") as mock_gpt,
        ):
            mock_detect.return_value = [make_lang_result("af", 0.45)]  # Afrikaans? Low conf
            mock_gpt.return_value = DetectionResult(language="en", confidence=0.75, source="gpt")
            result = detect("Something unclear that langdetect cannot classify well.")

        mock_gpt.assert_called_once()
        assert result.source == "gpt"

    def test_gpt_fallback_returns_valid_language(self):
        with (
            patch("ai.language_detector.detect_langs") as mock_detect,
            patch("ai.language_detector._call_gpt_fallback") as mock_gpt,
        ):
            mock_detect.return_value = [make_lang_result("tl", 0.40)]
            mock_gpt.return_value = DetectionResult(language="hinglish", confidence=0.88, source="gpt")
            result = detect("Something that langdetect misclassifies significantly.")

        assert result.language in SUPPORTED_LANGUAGES

    def test_gpt_fallback_unknown_language_defaults_to_en(self):
        """If GPT returns an unknown code, it should be sanitized to 'en'."""
        with (
            patch("ai.language_detector.detect_langs") as mock_detect,
            patch("ai.language_detector.OpenAI") as mock_openai,
        ):
            mock_detect.return_value = [make_lang_result("xx", 0.30)]

            # GPT returns a garbage language code
            mock_response = MagicMock()
            mock_response.choices[0].message.content = "xyz 0.99"
            mock_openai.return_value.chat.completions.create.return_value = mock_response

            result = detect("Xyzzy plugh foobar baz something garbage text here.")

        assert result.language in SUPPORTED_LANGUAGES
