"""
telephony/call_handler.py — FastAPI app with Twilio webhooks and WebSocket media stream.

Endpoints:
  POST /call/inbound      — Twilio webhook; returns TwiML to start <Stream>
  POST /call/outbound     — Initiate outbound call via Twilio REST API
  WS   /call/stream/{call_sid} — Bidirectional Twilio Media Stream handler
  GET  /health            — Health check endpoint

Conversation pipeline (per WebSocket turn):
  1. Buffer Twilio μ-law audio frames
  2. Once sufficient audio accumulated → transcribe via Whisper
  3. Detect language from transcript
  4. Update conversation state
  5. Generate GPT response (language-aware)
  6. Synthesize voice via ElevenLabs
  7. Convert to μ-law → stream back to Twilio
"""

from __future__ import annotations

import base64
import json
import logging
from collections import defaultdict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from elevenlabs import ElevenLabs

import config
from ai import language_detector, gpt_handler, whisper_handler, voice_selector
from state import conversation_state
from telephony.audio_utils import (
    decode_twilio_audio,
    mp3_to_mulaw,
    encode_audio_for_twilio,
    build_twilio_media_message,
)

logger = logging.getLogger(__name__)

# ─── App & Middleware ─────────────────────────────────────────────────────────

app = FastAPI(title="AI Auto Caller", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Clients ──────────────────────────────────────────────────────────────────

twilio_client = TwilioClient(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
elevenlabs_client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)

# ─── Active Sessions ──────────────────────────────────────────────────────────

# call_sid → ConversationState
_active_calls: dict[str, conversation_state.ConversationState] = {}

# Minimum μ-law bytes to accumulate before transcribing (≈1.5 seconds at 8kHz)
_AUDIO_BUFFER_MIN_BYTES = 12_000


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _synthesize_speech(text: str, language: str) -> bytes:
    """
    Generate speech via ElevenLabs and return as μ-law bytes for Twilio.

    Returns empty bytes on failure (call continues silently).
    """
    voice_cfg = voice_selector.get_voice_config(language)
    try:
        audio_generator = elevenlabs_client.text_to_speech.convert(
            text=text,
            voice_id=voice_cfg["voice_id"],
            model_id=voice_cfg["model_id"],
        )
        mp3_bytes = b"".join(audio_generator)
        mulaw = mp3_to_mulaw(mp3_bytes)
        if not mulaw:
            logger.error("mp3_to_mulaw returned empty bytes.")
        return mulaw
    except Exception as exc:  # noqa: BLE001
        logger.error("ElevenLabs synthesis failed: %s", exc)
        return b""


async def _process_turn(
    state: conversation_state.ConversationState,
    audio_buffer: bytes,
    websocket: WebSocket,
    stream_sid: str,
) -> None:
    """
    Run one full conversation turn:
    Whisper → Detect → GPT → ElevenLabs → Twilio stream.
    """
    # ── 1. Transcribe ────────────────────────────────────────────────────────
    transcript = whisper_handler.transcribe(audio_buffer, audio_format="mulaw")
    if not transcript:
        logger.debug("[%s] Empty transcript, skipping turn.", state.call_sid)
        return

    logger.info("[%s] User said: %r", state.call_sid, transcript)

    # ── 2. Detect language ───────────────────────────────────────────────────
    result = language_detector.detect(transcript, state.current_language)
    conversation_state.update_language(state, result)

    # ── 3. Add user message to history ──────────────────────────────────────
    conversation_state.add_message(state, "user", transcript)

    # ── 4. Generate GPT response ─────────────────────────────────────────────
    reply = gpt_handler.generate_response(state)
    conversation_state.add_message(state, "assistant", reply)
    conversation_state.increment_turn(state)

    logger.info("[%s] AI reply: %r", state.call_sid, reply)

    # ── 5. Synthesize voice ──────────────────────────────────────────────────
    mulaw_audio = _synthesize_speech(reply, state.current_language)
    if not mulaw_audio:
        logger.error("[%s] Voice synthesis failed, turn skipped.", state.call_sid)
        return

    # ── 6. Stream audio back to Twilio ───────────────────────────────────────
    b64_audio = encode_audio_for_twilio(mulaw_audio)
    media_msg = build_twilio_media_message(b64_audio, stream_sid)
    await websocket.send_text(json.dumps(media_msg))

    logger.info(
        "[%s] Turn %d complete | lang=%s | reply_len=%d",
        state.call_sid,
        state.turn_count,
        state.current_language,
        len(reply),
    )


# ─── HTTP Endpoints ───────────────────────────────────────────────────────────


@app.get("/health")
async def health_check() -> JSONResponse:
    """Health check — returns server status and active call count."""
    return JSONResponse({
        "status": "ok",
        "active_calls": len(_active_calls),
        "voice_mode": config.VOICE_MODE,
        "default_language": config.DEFAULT_LANGUAGE,
    })


@app.post("/call/inbound")
async def handle_inbound_call(request: Request) -> Response:
    """
    Twilio inbound call webhook.

    Returns TwiML that:
    1. Greets the caller with a brief message.
    2. Connects to a bidirectional Media Stream WebSocket.
    """
    try:
        form = await request.form()
    except AssertionError as exc:
        raise HTTPException(status_code=400, detail="multipart form parse error") from exc

    call_sid = form.get("CallSid", "unknown")
    caller_number = form.get("From", "")
    called_number = form.get("To", "")

    logger.info("Inbound call received: %s (From: %s)", call_sid, caller_number)

    # Initialize conversation state for this call
    state = conversation_state.create_state(
        call_sid=call_sid,
        caller_number=caller_number,
        called_number=called_number,
    )
    _active_calls[call_sid] = state

    # Build TwiML
    twiml = VoiceResponse()
    twiml.say(
        "Hello! AI caller connected. How can I help you today?",
        voice="alice",
        language="en-IN",
    )
    connect = Connect()
    ws_url = config.PUBLIC_BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
    stream = Stream(url=f"{ws_url}/call/stream/{call_sid}")
    stream.parameter(name="callSid", value=call_sid)
    connect.append(stream)
    twiml.append(connect)

    return Response(content=str(twiml), media_type="application/xml")


@app.post("/call/outbound")
async def initiate_outbound_call(request: Request) -> JSONResponse:
    """
    Initiate an outbound call via Twilio REST API.

    Expected body:
      {
        "to": "+91XXXXXXXXXX",
        "language": "en"   (optional, default from config)
      }
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    to_number = body.get("to")
    if not to_number:
        raise HTTPException(status_code=400, detail="'to' phone number is required.")

    initial_language = body.get("language", config.DEFAULT_LANGUAGE)

    try:
        call = twilio_client.calls.create(
            to=to_number,
            from_=config.TWILIO_PHONE_NUMBER,
            url=f"{config.PUBLIC_BASE_URL}/call/inbound",
        )
        logger.info("Outbound call initiated: %s → %s", call.sid, to_number)

        # Pre-initialize state so we know the recipient number when webhook hits
        state = conversation_state.create_state(
            call_sid=call.sid,
            caller_number=to_number,  # The AI is calling *them*, so they are the "caller" target for WhatsApp
            called_number=config.TWILIO_PHONE_NUMBER,
        )
        _active_calls[call.sid] = state

        return JSONResponse({
            "status": "initiated",
            "call_sid": call.sid,
            "to": to_number,
            "initial_language": initial_language,
        })
    except Exception as exc:  # noqa: BLE001
        logger.error("Outbound call failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Call failed: {exc}")


# ─── WebSocket — Twilio Media Stream ─────────────────────────────────────────


@app.websocket("/call/stream/{call_sid}")
async def media_stream(websocket: WebSocket, call_sid: str) -> None:
    """
    Bidirectional Twilio Media Stream WebSocket handler.

    Receives:
      - 'connected' event: stream started
      - 'start'     event: call metadata
      - 'media'     event: base64 μ-law audio chunk
      - 'stop'      event: call ended

    Sends:
      - 'media' events: base64 μ-law AI voice response
    """
    await websocket.accept()
    logger.info("[%s] WebSocket connected.", call_sid)

    # Get or create state (inbound handler should have created it)
    state = _active_calls.get(call_sid)
    if state is None:
        state = conversation_state.create_state(call_sid)
        _active_calls[call_sid] = state

    audio_buffer = b""
    stream_sid = ""

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            event = data.get("event")

            if event == "connected":
                logger.info("[%s] Stream connected.", call_sid)

            elif event == "start":
                stream_sid = data.get("streamSid", "")
                logger.info("[%s] Stream started. streamSid=%s", call_sid, stream_sid)

            elif event == "media":
                # Accumulate audio frames
                payload = data.get("media", {}).get("payload", "")
                chunk = decode_twilio_audio(payload)
                audio_buffer += chunk

                # Process when buffer is large enough
                if len(audio_buffer) >= _AUDIO_BUFFER_MIN_BYTES:
                    buffer_to_process = audio_buffer
                    audio_buffer = b""  # Reset immediately to avoid overlap

                    await _process_turn(state, buffer_to_process, websocket, stream_sid)

            elif event == "stop":
                logger.info(
                    "[%s] Stream stopped. Summary: %s",
                    call_sid,
                    conversation_state.get_summary(state),
                )
                break

    except WebSocketDisconnect:
        logger.info("[%s] WebSocket disconnected.", call_sid)

    except Exception as exc:  # noqa: BLE001
        logger.error("[%s] Unexpected WebSocket error: %s", call_sid, exc)

    finally:
        # Clean up session
        _active_calls.pop(call_sid, None)
        logger.info("[%s] Session cleaned up.", call_sid)
