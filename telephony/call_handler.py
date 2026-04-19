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
from telephony.vad_handler import VADHandler
from database import sqlite_manager

logger = logging.getLogger(__name__)

# ─── App & Middleware ─────────────────────────────────────────────────────────

app = FastAPI(title="AI Auto Caller", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register ElevenLabs ConvAI bridge router (always included, activated via config flag)
from telephony import elevenlabs_bridge  # noqa: E402
app.include_router(elevenlabs_bridge.router)

# ─── Clients (default — used when no per-user creds exist) ───────────────────

twilio_client = TwilioClient(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
elevenlabs_client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)

# ─── Per-Call Session Clients ─────────────────────────────────────────────────
# call_sid → {"elevenlabs": ElevenLabs, "openai_key": str, "creds": dict}
_session_clients: dict[str, dict] = {}

# ─── Active Sessions ──────────────────────────────────────────────────────────

# call_sid → ConversationState
_active_calls: dict[str, conversation_state.ConversationState] = {}

# Bytes to skip at the start of a call to absorb the Twilio greeting echo
# 8000 bytes/sec * 3.5 sec = 28,000 bytes
_GREETING_SKIP_BYTES = 28_000

# Bytes to skip after AI finishes speaking to prevent response echo triggering a new turn
# 8000 bytes/sec * 1.5 sec = 12,000 bytes
_POST_RESPONSE_SKIP_BYTES = 12_000


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _synthesize_speech(text: str, language: str, call_sid: str = "") -> bytes:
    """
    Generate speech via ElevenLabs and return as μ-law bytes for Twilio.
    Uses per-call client if available, else falls back to default.
    Returns empty bytes on failure.
    """
    session = _session_clients.get(call_sid, {})
    client  = session.get("elevenlabs") or elevenlabs_client
    creds   = session.get("creds") or {}

    voice_id = creds.get("elevenlabs_voice_id") or config.ELEVENLABS_VOICE_ID_MULTILINGUAL
    model_id = config.ELEVENLABS_MODEL_ID

    try:
        audio_generator = client.text_to_speech.convert(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
        )
        mp3_bytes = b"".join(audio_generator)
        mulaw = mp3_to_mulaw(mp3_bytes)
        if not mulaw:
            logger.error("mp3_to_mulaw returned empty bytes.")
        return mulaw
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "ElevenLabs synthesis failed: %s. "
            "(Check API keys, Tier credits, or Voice/Model ID validity)",
            exc
        )
        return b""


async def _process_turn(
    state: conversation_state.ConversationState,
    audio_buffer: bytes,
    websocket: WebSocket,
    stream_sid: str,
) -> bool:
    """
    Run one full conversation turn:
    Whisper → Detect → GPT → ElevenLabs → Twilio stream.
    """
    sid = state.call_sid

    # -- Pipeline Header -------------------------------------------------------
    logger.info(f"[{sid}] +--- Turn {state.turn_count + 1} START --- (lang={state.current_language} | audio={len(audio_buffer)} bytes)")

    # -- 1. Transcribe ---------------------------------------------------------
    logger.info(f"[{sid}] | [1/6] Whisper: transcribing {len(audio_buffer)} bytes of mulaw audio...")
    transcript = whisper_handler.transcribe(audio_buffer, audio_format="mulaw", call_sid=sid)
    if not transcript:
        logger.info(f"[{sid}] +--- Turn END (empty transcript - no speech detected)")
        return False

    logger.info(f"[{sid}] |      USER SAID  >> {transcript!r}")

    # -- 2. Detect language ----------------------------------------------------
    logger.info(f"[{sid}] | [2/6] Language Detector: analyzing...")
    result = language_detector.detect(transcript, state.current_language)
    before_lang = state.current_language
    conversation_state.update_language(state, result)
    after_lang = state.current_language
    if before_lang != after_lang:
        logger.info(f"[{sid}] |      LANG SWITCH  {before_lang} -> {after_lang}  (confidence={result.confidence:.2f})")
    else:
        logger.info(f"[{sid}] |      LANG STABLE  {after_lang}  (confidence={result.confidence:.2f})")

    # -- 3. Add user message to history ----------------------------------------
    conversation_state.add_message(state, "user", transcript)
    logger.info(f"[{sid}] | [3/6] History: user message appended (total {len(state.messages)} messages)")

    # -- 4. Generate response (Greeting skip or GPT) ---------------------------
    
    # Clean transcript for greeting detection (remove punctuation)
    import string
    cleaned_transcript = transcript.lower().translate(str.maketrans('', '', string.punctuation)).strip()
    GREETING_WORDS = {"hello", "hi", "hey", "hii", "heya"}
    
    is_greeting = cleaned_transcript in GREETING_WORDS
    
    if is_greeting:
        logger.info(f"[{sid}] | [4/6] Greeting detected! Skipping GPT-4o...")
        if state.turn_count == 0:
            reply = "Hello! Welcome to SM01. How can I assist you today?"
        else:
            reply = "Hi again! What can I do for you?"
    else:
        logger.info(f"[{sid}] | [4/6] GPT-4o: generating response...")
        reply = gpt_handler.generate_response(state)
    conversation_state.add_message(state, "assistant", reply)
    conversation_state.increment_turn(state)

    logger.info(f"[{sid}] |      AI REPLY   << {reply!r}")

    # Log if any tools were called during this turn
    if state.actions_taken:
        last_action = state.actions_taken[-1]
        logger.info(f"[{sid}] |      TOOL USED  [*] {last_action.get('action', 'unknown')}")

    # -- 5. Synthesize voice ---------------------------------------------------
    logger.info(f"[{sid}] | [5/6] ElevenLabs: synthesizing speech ({len(reply)} chars)...")
    mulaw_audio = _synthesize_speech(reply, state.current_language, call_sid=sid)
    if not mulaw_audio:
        logger.error(f"[{sid}] |      [!] Voice synthesis FAILED - caller will hear silence this turn.")
        logger.info(f"[{sid}] +--- Turn {state.turn_count} END (synthesis fail)")
        return False

    logger.info(f"[{sid}] |      [OK] Speech synthesized ({len(mulaw_audio)} mulaw bytes)")

    # -- 6. Stream audio back to Twilio ----------------------------------------
    logger.info(f"[{sid}] | [6/6] Twilio: encoding and streaming audio...")
    b64_audio = encode_audio_for_twilio(mulaw_audio)
    if not b64_audio:
        logger.error(f"[{sid}] |      [!] Audio encoding FAILED - skipping send.")
        logger.info(f"[{sid}] +--- Turn {state.turn_count} END (encoding fail)")
        return False

    media_msg = build_twilio_media_message(b64_audio, stream_sid)
    await websocket.send_text(json.dumps(media_msg))

    logger.info(f"[{sid}] |      [OK] Audio streamed to caller ({len(b64_audio)} b64 chars)")
    logger.info(f"[{sid}] +--- Turn {state.turn_count} COMPLETE --- (lang={state.current_language} | reply={len(reply)} chars)")

    # Check if any tools executed in this turn requested a call termination
    should_end = any(a.get("action") == "end_call" for a in state.actions_taken)
    return should_end


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

    call_sid      = form.get("CallSid", "unknown")
    caller_number = form.get("From", "")
    called_number = form.get("To", "")

    logger.info("Inbound call received: %s (From: %s)", call_sid, caller_number)

    # ── Dynamic credential lookup from SQLite hot cache ──────────────────────
    creds = sqlite_manager.get_credentials_by_phone(called_number)
    if creds:
        logger.info("[%s] Loaded per-user credentials for %s", call_sid, called_number)
        from openai import OpenAI as _OpenAI
        _session_clients[call_sid] = {
            "elevenlabs": ElevenLabs(api_key=creds["elevenlabs_key"]),
            "openai_key": creds["openai_key"],
            "creds":      creds,
        }
        # Patch the whisper handler key for this session
        whisper_handler._override_api_key(call_sid, creds["openai_key"])
        gpt_handler._override_api_key(call_sid, creds["openai_key"])
    else:
        logger.info("[%s] No per-user creds found for %s — using .env defaults.", call_sid, called_number)

    # Initialize conversation state for this call
    state = conversation_state.create_state(
        call_sid=call_sid,
        caller_number=caller_number,
        called_number=called_number,
    )
    _active_calls[call_sid] = state

    # Build TwiML
    twiml = VoiceResponse()
    ws_url = config.PUBLIC_BASE_URL.replace("https://", "wss://").replace("http://", "ws://")

    if config.USE_ELEVENLABS_CONVAI:
        # ElevenLabs ConvAI mode — register state with bridge and skip greeting
        elevenlabs_bridge.register_call(call_sid, state)
        logger.info("[%s] Using ElevenLabs ConvAI bridge.", call_sid)
        stream_url = f"{ws_url}/call/stream/el/{call_sid}"
    else:
        # Legacy pipeline mode — greet via Twilio TTS and use our manual pipeline
        twiml.say(
            "Hello! AI caller connected. How can I help you today?",
            voice="alice",
            language="en-IN",
        )
        stream_url = f"{ws_url}/call/stream/{call_sid}"

    connect = Connect()
    stream = Stream(url=stream_url)
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
    # Skip the first N bytes of audio to ignore echo from the Twilio greeting
    skip_bytes = _GREETING_SKIP_BYTES
    
    # Initialize our new smart VAD
    vad = VADHandler(call_sid=call_sid)

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            event = data.get("event")

            if event == "connected":
                logger.info("[%s] Stream connected.", call_sid)

            elif event == "start":
                stream_sid = data.get("streamSid", "")
                logger.info("[%s] Stream started. streamSid=%s | Greeting cooldown: %d bytes", call_sid, stream_sid, skip_bytes)

            elif event == "media":
                payload = data.get("media", {}).get("payload", "")
                chunk = decode_twilio_audio(payload)

                # -- Cooldown / deaf period: ignore audio during echo windows --
                if skip_bytes > 0:
                    skip_bytes -= len(chunk)
                    continue

                # Pass chunk to VAD for speech/silence detection
                audio_buffer += chunk
                
                if vad.process_pcm_chunk(chunk):
                    # VAD detected that the user has stopped speaking!
                    buffer_to_process = audio_buffer
                    
                    # Reset buffer and VAD state immediately for the next turn
                    audio_buffer = b""  
                    vad.is_speaking = False
                    
                    should_hangup = await _process_turn(state, buffer_to_process, websocket, stream_sid)

                    if should_hangup:
                        logger.info("[%s] AI requested call end. Queuing teardown marker.", call_sid)
                        mark_msg = {
                            "event": "mark",
                            "streamSid": stream_sid,
                            "mark": {"name": "ai_goodbye_complete"}
                        }
                        await websocket.send_text(json.dumps(mark_msg))

                    # After AI speaks, ignore audio for POST_RESPONSE window (response echo)
                    skip_bytes = _POST_RESPONSE_SKIP_BYTES
                    logger.info("[%s] Post-response cooldown started (%d bytes).", call_sid, _POST_RESPONSE_SKIP_BYTES)

            elif event == "mark":
                mark_name = data.get("mark", {}).get("name", "")
                if mark_name == "ai_goodbye_complete":
                    logger.info("[%s] Goodbye message finished playing. Disconnecting call.", call_sid)
                    try:
                        twilio_client.calls(call_sid).update(status="completed")
                    except Exception as exc:  # noqa: BLE001
                        logger.error("[%s] Failed to hang up call via Twilio REST API: %s", call_sid, exc)

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
        # Cleanup session client cache
    _session_clients.pop(call_sid, None)
    whisper_handler._clear_override(call_sid)
    gpt_handler._clear_override(call_sid)
    logger.info("[%s] Session cleaned up.", call_sid)
