"""
ai/language_detector.py — Automatic language detection module.

Detects language from transcribed speech text and returns a structured
DetectionResult. Supports English, Hindi, Gujarati, Hinglish (mixed),
and Gujlish (Gujarati-English mixed).

Detection pipeline:
  1. Short text (<3 words) → skip, return current conversation language
  2. langdetect (primary) → if confidence >= threshold, return result
  3. GPT-3.5-turbo fallback → for low-confidence or ambiguous text
  4. Hard default → "en" if everything fails

Hinglish heuristic:
  If both "en" and "hi" score > HINGLISH_THRESHOLD in langdetect output,
  classify as "hinglish".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from langdetect import detect_langs, LangDetectException
from openai import OpenAI

import config

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

# langdetect code → internal app language code
_LANGDETECT_MAP: dict[str, str] = {
    "en": "en",
    "hi": "hi",
    "gu": "gu",
}

# Supported language codes (internal)
SUPPORTED_LANGUAGES = {"en", "hi", "gu", "hinglish", "gujlish"}

# If both EN and HI scores exceed this, classify as Hinglish
_HINGLISH_THRESHOLD = 0.20

# If both EN and GU scores exceed this, classify as Gujlish
_GUJLISH_THRESHOLD = 0.20

# GPT model to use for fallback classification (cheaper/faster)
_GPT_FALLBACK_MODEL = "gpt-3.5-turbo"

# Minimum words required to attempt detection
_MIN_WORDS_FOR_DETECTION = 3

# ─── Data Model ───────────────────────────────────────────────────────────────


@dataclass
class DetectionResult:
    """Result of a language detection operation."""

    language: str
    """Detected language code: en | hi | gu | hinglish | gujlish"""

    confidence: float
    """Confidence score between 0.0 and 1.0."""

    raw_scores: dict[str, float] = field(default_factory=dict)
    """Raw per-language probability scores from langdetect."""

    source: str = "langdetect"
    """Which detector produced this result: 'langdetect' | 'gpt' | 'default' | 'skipped'"""


# ─── Internal Helpers ─────────────────────────────────────────────────────────

def _run_langdetect(text: str) -> list[tuple[str, float]]:
    """
    Run langdetect on text.

    Returns list of (lang_code, probability) sorted by probability desc.
    Returns empty list on failure.
    """
    try:
        results = detect_langs(text)
        return [(r.lang, round(r.prob, 4)) for r in results]
    except LangDetectException as exc:
        logger.warning("langdetect failed: %s", exc)
        return []


def _apply_hinglish_heuristic(
    scores: dict[str, float]
) -> str | None:
    """
    Check for code-switching patterns.

    Returns "hinglish", "gujlish", or None if no mixed language detected.
    """
    en_score = scores.get("en", 0.0)
    hi_score = scores.get("hi", 0.0)
    gu_score = scores.get("gu", 0.0)

    if en_score > _HINGLISH_THRESHOLD and hi_score > _HINGLISH_THRESHOLD:
        return "hinglish"

    if en_score > _GUJLISH_THRESHOLD and gu_score > _GUJLISH_THRESHOLD:
        return "gujlish"

    return None


def _call_gpt_fallback(text: str) -> DetectionResult:
    """
    Use GPT-3.5-turbo to classify language when langdetect is inconclusive.

    Expected GPT response format: "<language_code> <confidence>"
    Example: "hinglish 0.88"
    """
    client = OpenAI(api_key=config.OPENAI_API_KEY)

    prompt = (
        "You are a language classification assistant.\n"
        "Classify the following text into EXACTLY ONE of these codes: "
        "en, hi, gu, hinglish, gujlish\n\n"
        "- en       = English only\n"
        "- hi       = Hindi only (may use Devanagari or Roman script)\n"
        "- gu       = Gujarati only\n"
        "- hinglish = Mixed Hindi + English (most common in Indian conversations)\n"
        "- gujlish  = Mixed Gujarati + English\n\n"
        "Reply with ONLY: <language_code> <confidence_0_to_1>\n"
        "Example: hinglish 0.92\n\n"
        f"Text: {text!r}"
    )

    try:
        response = client.chat.completions.create(
            model=_GPT_FALLBACK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=20,
        )
        raw = response.choices[0].message.content.strip().lower()
        parts = raw.split()

        lang = parts[0] if parts else config.DEFAULT_LANGUAGE
        conf = float(parts[1]) if len(parts) > 1 else 0.75

        # Sanitize
        if lang not in SUPPORTED_LANGUAGES:
            logger.warning("GPT returned unknown language '%s', defaulting to 'en'", lang)
            lang = config.DEFAULT_LANGUAGE
        conf = max(0.0, min(1.0, conf))

        logger.info("GPT fallback: '%s' → %s (%.2f)", text[:50], lang, conf)
        return DetectionResult(language=lang, confidence=conf, source="gpt")

    except Exception as exc:  # noqa: BLE001
        logger.error("GPT fallback failed: %s", exc)
        return DetectionResult(
            language=config.DEFAULT_LANGUAGE,
            confidence=0.5,
            source="default",
        )


# ─── Public API ───────────────────────────────────────────────────────────────


def detect(text: str, current_language: str = "en") -> DetectionResult:
    """
    Detect the language of a transcribed speech segment.

    Args:
        text:             Transcribed text from Whisper STT.
        current_language: The conversation's current language code.
                          Used as fallback for short/unclear text.

    Returns:
        DetectionResult with language, confidence, raw_scores, and source.

    Flow:
        1. Short text → return current_language with high confidence (no API call).
        2. Run langdetect; apply Hinglish/Gujlish heuristic.
        3. If confidence >= LANGDETECT_MIN_CONFIDENCE → return result.
        4. Call GPT fallback for low-confidence cases.
        5. Default to "en" if everything fails.
    """
    if not text or not text.strip():
        logger.debug("Empty text, returning current language: %s", current_language)
        return DetectionResult(
            language=current_language,
            confidence=1.0,
            source="skipped",
        )

    word_count = len(text.strip().split())
    if word_count < _MIN_WORDS_FOR_DETECTION:
        logger.debug(
            "Text too short (%d words), returning current language: %s",
            word_count,
            current_language,
        )
        return DetectionResult(
            language=current_language,
            confidence=1.0,
            source="skipped",
        )

    # ── Step 1: Run langdetect ────────────────────────────────────────────────
    raw_scores_list = _run_langdetect(text)

    if not raw_scores_list:
        logger.warning("langdetect returned no results, falling back to GPT.")
        return _call_gpt_fallback(text)

    # Build score dict (map to internal lang codes)
    raw_scores: dict[str, float] = {}
    for lang_code, prob in raw_scores_list:
        internal = _LANGDETECT_MAP.get(lang_code, lang_code)
        raw_scores[internal] = prob

    top_lang, top_conf = raw_scores_list[0]
    top_lang_internal = _LANGDETECT_MAP.get(top_lang, top_lang)

    # ── Step 2: Apply Hinglish / Gujlish heuristic ───────────────────────────
    mixed = _apply_hinglish_heuristic(raw_scores)
    if mixed:
        conf = max(raw_scores.get("en", 0.0) + raw_scores.get("hi", 0.0),
                   raw_scores.get("en", 0.0) + raw_scores.get("gu", 0.0))
        conf = min(conf, 1.0)
        logger.info(
            "Hinglish/Gujlish detected: '%s' → %s (%.2f)", text[:50], mixed, conf
        )
        return DetectionResult(
            language=mixed,
            confidence=round(conf, 4),
            raw_scores=raw_scores,
            source="langdetect",
        )

    # ── Step 3: Check confidence threshold ───────────────────────────────────
    if top_conf >= config.LANGDETECT_MIN_CONFIDENCE:
        logger.info(
            "Language detected: '%s' → %s (%.2f)", text[:50], top_lang_internal, top_conf
        )
        return DetectionResult(
            language=top_lang_internal,
            confidence=top_conf,
            raw_scores=raw_scores,
            source="langdetect",
        )

    # ── Step 4: GPT fallback ─────────────────────────────────────────────────
    logger.info(
        "Low confidence (%.2f) for '%s', using GPT fallback.", top_conf, text[:50]
    )
    return _call_gpt_fallback(text)
