"""
main.py — AI Auto Caller entry point.

Starts the FastAPI/uvicorn server and prints a startup configuration summary.

Usage:
    python main.py

Or with uvicorn directly:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

For telephony testing (expose local server to Twilio/internet):
    ngrok http 8000
    Then set PUBLIC_BASE_URL in .env to your ngrok URL.
"""

import logging
import sys

import uvicorn
try:
    import debugpy
except ImportError:
    debugpy = None

import config
from telephony.call_handler import app  # noqa: F401  (imported for uvicorn)

# ─── Logging Setup ────────────────────────────────────────────────────────────

# Force UTF-8 output so terminal doesn't mangle characters
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


# ─── Startup Banner ───────────────────────────────────────────────────────────

def _print_banner() -> None:
    """Print startup configuration summary (masks sensitive keys)."""

    def mask(value: str) -> str:
        if not value:
            return "⚠️  NOT SET"
        if len(value) <= 8:
            return "****"
        return value[:4] + "****" + value[-4:]

    print("\n" + "=" * 60)
    print("  AI AUTO CALLER — Starting Up")
    print("=" * 60)
    print(f"  Server        : {config.SERVER_HOST}:{config.SERVER_PORT}")
    print(f"  Public URL    : {config.PUBLIC_BASE_URL}")
    print(f"  GPT Model     : {config.OPENAI_MODEL}")
    print(f"  Whisper Model : {config.OPENAI_WHISPER_MODEL}")
    print(f"  Voice Mode    : {config.VOICE_MODE}")
    print(f"  Default Lang  : {config.DEFAULT_LANGUAGE}")
    print(f"  OpenAI Key    : {mask(config.OPENAI_API_KEY)}")
    print(f"  ElevenLabs Key: {mask(config.ELEVENLABS_API_KEY)}")
    print(f"  Twilio SID    : {mask(config.TWILIO_ACCOUNT_SID)}")
    print(f"  Twilio Phone  : {config.TWILIO_PHONE_NUMBER or '⚠️  NOT SET'}")

    if config.VOICE_MODE == "multilingual":
        print(f"  Voice ID      : {mask(config.ELEVENLABS_VOICE_ID_MULTILINGUAL)}")
    else:
        print(f"  Voice EN      : {mask(config.ELEVENLABS_VOICE_ID_EN)}")
        print(f"  Voice HI      : {mask(config.ELEVENLABS_VOICE_ID_HI)}")
        print(f"  Voice GU      : {mask(config.ELEVENLABS_VOICE_ID_GU)}")

    print("=" * 60 + "\n")


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _print_banner()

    # --- Debugging Support ---
    if "--debug" in sys.argv:
        if debugpy:
            logger.info("Debugger enabled. Listening on port 5678...")
            debugpy.listen(("0.0.0.0", 5678))
            logger.info("Waiting for debugger to attach...")
            debugpy.wait_for_client()
            logger.info("Debugger attached!")
        else:
            logger.error("debugpy is not installed. Debugging will not be available.")

    uvicorn.run(
        "telephony.call_handler:app",
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        reload=False,
        log_level="info",
    )
