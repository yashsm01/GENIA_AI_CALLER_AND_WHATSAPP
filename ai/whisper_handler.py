"""
ai/whisper_handler.py — Speech-to-text via OpenAI Whisper.

Accepts raw audio bytes from Twilio's media stream (μ-law encoded),
converts to WAV format, and transcribes using the Whisper API.

Audio conversion pipeline:
  Twilio μ-law (8kHz, mono) → WAV (16kHz, mono) → Whisper API → transcript text

Dependencies:
  - openai (whisper-1 model)
  - pydub (audio format conversion)
  - ffmpeg must be installed on the system (used by pydub)
"""

from __future__ import annotations

import audioop
import io
import logging
import wave

from openai import OpenAI, APIError

import config

logger = logging.getLogger(__name__)

_client: OpenAI | None = None

# Twilio μ-law stream parameters
_TWILIO_SAMPLE_RATE = 8000   # Hz
_TWILIO_CHANNELS = 1         # Mono
_TWILIO_SAMPLE_WIDTH = 2     # bytes (16-bit PCM after decode)

# Target WAV parameters for Whisper
_WHISPER_SAMPLE_RATE = 16000  # Hz — Whisper performs best at 16kHz

# Minimum audio duration to attempt transcription (in seconds)
# Shorter clips often produce empty or noisy transcripts
_MIN_AUDIO_DURATION_SECS = 0.5


def _get_client() -> OpenAI:
    """Lazy-initialize the OpenAI client."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


# ─── Audio Conversion Helpers ─────────────────────────────────────────────────


def mulaw_to_pcm(mulaw_bytes: bytes) -> bytes:
    """
    Decode μ-law encoded audio bytes to 16-bit linear PCM.

    Twilio sends audio as 8-bit μ-law. This converts to 16-bit PCM
    which is then wrapped in a WAV container for the Whisper API.

    Args:
        mulaw_bytes: Raw μ-law audio bytes from Twilio.

    Returns:
        16-bit linear PCM audio bytes.
    """
    return audioop.ulaw2lin(mulaw_bytes, _TWILIO_SAMPLE_WIDTH)


def upsample_pcm(pcm_bytes: bytes, from_rate: int, to_rate: int) -> bytes:
    """
    Upsample PCM audio from from_rate to to_rate using audioop.

    Args:
        pcm_bytes:  16-bit PCM audio bytes.
        from_rate:  Source sample rate (e.g. 8000).
        to_rate:    Target sample rate (e.g. 16000).

    Returns:
        Resampled PCM bytes.
    """
    if from_rate == to_rate:
        return pcm_bytes
    resampled, _ = audioop.ratecv(
        pcm_bytes, _TWILIO_SAMPLE_WIDTH, _TWILIO_CHANNELS,
        from_rate, to_rate, None
    )
    return resampled


def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = _WHISPER_SAMPLE_RATE) -> bytes:
    """
    Wrap raw PCM bytes in a WAV container.

    Args:
        pcm_bytes:   16-bit mono PCM audio.
        sample_rate: Sample rate of the PCM data.

    Returns:
        WAV file as bytes (in-memory).
    """
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(_TWILIO_CHANNELS)
        wf.setsampwidth(_TWILIO_SAMPLE_WIDTH)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buffer.getvalue()


def mulaw_to_wav(mulaw_bytes: bytes) -> bytes:
    """
    Full conversion: μ-law bytes → WAV bytes at 16kHz.

    This is the main conversion function used before sending to Whisper.

    Args:
        mulaw_bytes: Raw μ-law bytes from Twilio.

    Returns:
        WAV file bytes ready for the Whisper API.
    """
    pcm = mulaw_to_pcm(mulaw_bytes)
    pcm_16k = upsample_pcm(pcm, _TWILIO_SAMPLE_RATE, _WHISPER_SAMPLE_RATE)
    return pcm_to_wav(pcm_16k)


def _is_audio_long_enough(wav_bytes: bytes) -> bool:
    """Check that the WAV audio is long enough to transcribe meaningfully."""
    try:
        buffer = io.BytesIO(wav_bytes)
        with wave.open(buffer, "rb") as wf:
            duration = wf.getnframes() / wf.getframerate()
        return duration >= _MIN_AUDIO_DURATION_SECS
    except Exception:  # noqa: BLE001
        return True  # Don't block on unexpected formats


# ─── Public API ───────────────────────────────────────────────────────────────


def transcribe(audio_bytes: bytes, audio_format: str = "mulaw") -> str:
    """
    Transcribe speech audio to text using OpenAI Whisper.

    Args:
        audio_bytes:  Raw audio bytes.
        audio_format: "mulaw" (Twilio default) or "wav" (pre-converted).

    Returns:
        Transcribed text string, or empty string on failure/short audio.
    """
    if not audio_bytes:
        logger.debug("Empty audio bytes received, skipping transcription.")
        return ""

    # ── Convert to WAV if needed ──────────────────────────────────────────────
    if audio_format == "mulaw":
        try:
            wav_bytes = mulaw_to_wav(audio_bytes)
        except Exception as exc:  # noqa: BLE001
            logger.error("Audio conversion failed: %s", exc)
            return ""
    else:
        wav_bytes = audio_bytes

    # ── Check minimum duration ────────────────────────────────────────────────
    if not _is_audio_long_enough(wav_bytes):
        logger.debug("Audio too short (<%.1fs), skipping transcription.", _MIN_AUDIO_DURATION_SECS)
        return ""

    # ── Call Whisper API ──────────────────────────────────────────────────────
    client = _get_client()
    audio_file = io.BytesIO(wav_bytes)
    audio_file.name = "audio.wav"

    try:
        result = client.audio.transcriptions.create(
            model=config.OPENAI_WHISPER_MODEL,
            file=audio_file,
            response_format="text",
        )
        transcript = result.strip() if isinstance(result, str) else str(result).strip()
        logger.info("Whisper transcript: %r (%d chars)", transcript[:80], len(transcript))
        return transcript

    except APIError as exc:
        logger.error("Whisper API error: %s", exc)
        return ""

    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected Whisper error: %s", exc)
        return ""
