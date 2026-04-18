"""
config.py — Centralized configuration loader.

Reads all environment variables from .env and provides
typed constants for the rest of the application.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── OpenAI ───────────────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_WHISPER_MODEL: str = os.getenv("OPENAI_WHISPER_MODEL", "whisper-1")

# ─── ElevenLabs ───────────────────────────────────────────────────────────────
ELEVENLABS_API_KEY: str = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_MODEL_ID: str = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

# "multilingual" → single voice for all languages (MVP)
# "per_language"  → separate voice per language code
VOICE_MODE: str = os.getenv("VOICE_MODE", "multilingual")

ELEVENLABS_VOICE_ID_MULTILINGUAL: str = os.getenv("ELEVENLABS_VOICE_ID_MULTILINGUAL", "")
ELEVENLABS_VOICE_ID_EN: str = os.getenv("ELEVENLABS_VOICE_ID_EN", "")
ELEVENLABS_VOICE_ID_HI: str = os.getenv("ELEVENLABS_VOICE_ID_HI", "")
ELEVENLABS_VOICE_ID_GU: str = os.getenv("ELEVENLABS_VOICE_ID_GU", "")

# ─── Twilio ───────────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER: str = os.getenv("TWILIO_PHONE_NUMBER", "")

# ─── Server ───────────────────────────────────────────────────────────────────
SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))
PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")

# ─── Language Detection ───────────────────────────────────────────────────────
DEFAULT_LANGUAGE: str = os.getenv("DEFAULT_LANGUAGE", "en")
LANGDETECT_MIN_CONFIDENCE: float = float(os.getenv("LANGDETECT_MIN_CONFIDENCE", "0.70"))
LANGUAGE_SWITCH_CONFIDENCE: float = float(os.getenv("LANGUAGE_SWITCH_CONFIDENCE", "0.80"))
LANGUAGE_SWITCH_TURNS: int = int(os.getenv("LANGUAGE_SWITCH_TURNS", "2"))

# ─── GPT Call Settings ────────────────────────────────────────────────────────
GPT_TEMPERATURE: float = 0.7
GPT_MAX_TOKENS: int = 300
