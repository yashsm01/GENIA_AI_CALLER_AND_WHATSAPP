"""
telephony/audio_utils.py — Audio format utilities for Twilio ↔ ElevenLabs bridge.

Handles:
  - Decoding base64 μ-law audio from Twilio's Media Stream WebSocket
  - Encoding responses back to Twilio's expected format
  - Converting ElevenLabs MP3 output to μ-law for Twilio playback

Twilio Media Streams use:
  - Encoding: audio/x-mulaw
  - Sample rate: 8000 Hz
  - Channels: 1 (mono)
  - Payload: base64-encoded μ-law bytes
"""

from __future__ import annotations

import audioop
import base64
import io
import logging

logger = logging.getLogger(__name__)

_MULAW_SAMPLE_RATE = 8000
_SAMPLE_WIDTH = 2  # 16-bit PCM
_CHANNELS = 1


def decode_twilio_audio(b64_payload: str) -> bytes:
    """
    Decode a base64-encoded μ-law audio payload from Twilio.

    Args:
        b64_payload: Base64 string from Twilio 'media' WebSocket event.

    Returns:
        Raw μ-law audio bytes.
    """
    try:
        return base64.b64decode(b64_payload)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to decode Twilio audio payload: %s", exc)
        return b""


def encode_audio_for_twilio(mulaw_bytes: bytes) -> str:
    """
    Encode already-converted μ-law bytes to base64 for sending back to Twilio.

    IMPORTANT: This function expects μ-law bytes as input (NOT raw PCM).
    Use mp3_to_mulaw() first to convert MP3 → μ-law, then pass the result here.

    Args:
        mulaw_bytes: μ-law encoded audio bytes (8kHz, mono).

    Returns:
        Base64-encoded string suitable for Twilio Media Stream payload.
    """
    try:
        if not mulaw_bytes:
            logger.error("encode_audio_for_twilio: received empty bytes.")
            return ""
        return base64.b64encode(mulaw_bytes).decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to encode audio for Twilio: %s", exc)
        return ""


def mp3_to_mulaw(mp3_bytes: bytes) -> bytes:
    """
    Convert ElevenLabs MP3 output to 8kHz μ-law PCM for Twilio playback.

    Uses pydub for MP3 decoding (requires ffmpeg on PATH).

    Args:
        mp3_bytes: Raw MP3 audio bytes from ElevenLabs API.

    Returns:
        μ-law encoded PCM bytes at 8kHz, or empty bytes on failure.
    """
    try:
        from pydub import AudioSegment  # type: ignore

        audio = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")

        # Normalize to 8kHz mono
        audio = audio.set_frame_rate(_MULAW_SAMPLE_RATE)
        audio = audio.set_channels(_CHANNELS)
        audio = audio.set_sample_width(_SAMPLE_WIDTH)

        pcm_bytes = audio.raw_data
        return audioop.lin2ulaw(pcm_bytes, _SAMPLE_WIDTH)

    except ImportError:
        logger.error(
            "pydub not installed or ffmpeg not found. "
            "Install: pip install pydub && install ffmpeg"
        )
        return b""

    except Exception as exc:  # noqa: BLE001
        logger.error("MP3 to μ-law conversion failed: %s", exc)
        return b""


def build_twilio_media_message(mulaw_b64: str, stream_sid: str) -> dict:
    """
    Build a Twilio Media Stream WebSocket message to play audio.

    Args:
        mulaw_b64:  Base64 μ-law audio string.
        stream_sid: The Twilio stream SID from the connected event.

    Returns:
        Dict formatted as a Twilio 'media' WebSocket message.
    """
    return {
        "event": "media",
        "streamSid": stream_sid,
        "media": {
            "payload": mulaw_b64,
        },
    }
