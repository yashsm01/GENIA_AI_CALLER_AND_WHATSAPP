"""
telephony/elevenlabs_bridge.py — ElevenLabs Conversational AI Bridge.

Replaces the manual Whisper->GPT->TTS pipeline with ElevenLabs ConvAI.

Architecture:
  1. Twilio call comes in -> /call/inbound returns TwiML pointing to /call/stream/el/{call_sid}
  2. Twilio streams audio to our WebSocket bridge at /call/stream/el/{call_sid}
  3. Bridge relays audio bidirectionally to ElevenLabs ConvAI WebSocket
  4. ElevenLabs calls our /elevenlabs/llm endpoint (Custom LLM webhook)
  5. We call GPT-4o + tools, return SSE-streamed text
  6. ElevenLabs synthesizes speech and streams audio back to Twilio

Requires:
  - ELEVENLABS_AGENT_ID in .env (create agent at elevenlabs.io/app/conversational-ai)
  - USE_ELEVENLABS_CONVAI=true in .env
  - ElevenLabs paid plan (Starter or above)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

import websockets
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

import config
from ai import gpt_handler
from state import conversation_state

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
router = APIRouter()

# Shared call state registry (populated by call_handler on inbound call)
# call_sid -> ConversationState
_bridge_calls: dict[str, conversation_state.ConversationState] = {}

ELEVENLABS_CONVAI_WS = "wss://api.elevenlabs.io/v1/convai/conversation"


def register_call(call_sid: str, state: "conversation_state.ConversationState") -> None:
    """Register a call state with the bridge. Called by call_handler on inbound."""
    _bridge_calls[call_sid] = state
    logger.info("[%s] Registered in ElevenLabs bridge.", call_sid)


def unregister_call(call_sid: str) -> None:
    """Remove call state when session ends."""
    _bridge_calls.pop(call_sid, None)


# ─── Custom LLM Webhook ──────────────────────────────────────────────────────
# ElevenLabs calls this endpoint when it needs an AI response.
# Must implement OpenAI-compatible /v1/chat/completions with SSE streaming.

@router.post("/elevenlabs/llm")
async def elevenlabs_llm_webhook(request: Request) -> StreamingResponse:
    """
    Custom LLM webhook called by ElevenLabs Conversational AI.

    ElevenLabs sends an OpenAI-compatible chat completion request.
    We run GPT-4o with tool-calling, then return the spoken reply as SSE.
    """
    body = await request.json()
    messages = body.get("messages", [])
    call_sid = body.get("call_sid", "")  # injected via custom_llm_extra_body

    logger.info(f"[{call_sid}] ElevenLabs LLM webhook called ({len(messages)} messages)")
    logger.info(f"[{call_sid}] | [LLM] User said: {messages[-1].get('content', '')!r}" if messages else "")

    # Get or create conversation state
    state = _bridge_calls.get(call_sid)
    if state is None:
        logger.warning(f"[{call_sid}] No bridge state found — creating minimal state")
        state = conversation_state.create_state(call_sid=call_sid)
        _bridge_calls[call_sid] = state

    # Sync ElevenLabs message history into state
    # ElevenLabs sends the full conversation. Pull out the latest user message.
    user_turns = [m for m in messages if m.get("role") == "user"]
    if user_turns:
        latest_user_msg = user_turns[-1].get("content", "")
        if latest_user_msg:
            conversation_state.add_message(state, "user", latest_user_msg)

    # Run our GPT tool-calling loop (runs synchronously, wrap in thread)
    logger.info(f"[{call_sid}] | [LLM] Calling GPT-4o with tools...")
    reply = await asyncio.to_thread(gpt_handler.generate_response, state)

    # Save assistant reply to history
    conversation_state.add_message(state, "assistant", reply)
    conversation_state.increment_turn(state)

    logger.info(f"[{call_sid}] | [LLM] AI reply: {reply!r}")

    # Return SSE stream (OpenAI format) for ElevenLabs to consume
    async def sse_stream():
        # Stream in small chunks for responsive TTS
        chunk_size = 5  # words per chunk
        words = reply.split()
        chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]

        for i, chunk in enumerate(chunks):
            text = chunk + (" " if i < len(chunks) - 1 else "")
            payload = {
                "id": f"chatcmpl-el-{call_sid[:8]}",
                "object": "chat.completion.chunk",
                "choices": [{"delta": {"content": text}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0.01)

        # Final stop chunk
        stop_payload = {
            "id": f"chatcmpl-el-{call_sid[:8]}",
            "object": "chat.completion.chunk",
            "choices": [{"delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(stop_payload)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        sse_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ─── Twilio <-> ElevenLabs Audio Bridge ──────────────────────────────────────

@router.websocket("/call/stream/el/{call_sid}")
async def elevenlabs_stream_bridge(websocket: WebSocket, call_sid: str) -> None:
    """
    Bidirectional WebSocket bridge: Twilio Media Stream <-> ElevenLabs ConvAI.

    Relays:
      - Twilio -> mu-law audio -> ElevenLabs user_audio_chunk
      - ElevenLabs audio -> base64 mu-law -> Twilio media payload
      - ElevenLabs interruption -> Twilio clear buffer
    """
    await websocket.accept()
    logger.info(f"[{call_sid}] +--- ElevenLabs Bridge WS connected ---")

    state = _bridge_calls.get(call_sid)
    if state is None:
        logger.error(f"[{call_sid}] No state found for bridge — closing WebSocket.")
        await websocket.close(code=1011, reason="No call state found")
        return

    if not config.ELEVENLABS_AGENT_ID:
        logger.error(f"[{call_sid}] ELEVENLABS_AGENT_ID not set in .env — cannot connect ConvAI.")
        await websocket.close(code=1011, reason="ELEVENLABS_AGENT_ID missing")
        return

    stream_sid: str | None = None
    el_ws_url = f"{ELEVENLABS_CONVAI_WS}?agent_id={config.ELEVENLABS_AGENT_ID}"

    try:
        async with websockets.connect(
            el_ws_url,
            additional_headers={"xi-api-key": config.ELEVENLABS_API_KEY},
        ) as el_ws:
            logger.info(f"[{call_sid}] Connected to ElevenLabs ConvAI.")

            # ── Init message: inject call_sid + system prompt ─────────────────
            system_prompt = gpt_handler.get_system_prompt(state.current_language)
            init_msg = {
                "type": "conversation_initiation_client_data",
                "custom_llm_extra_body": {
                    "call_sid": call_sid,
                },
                "conversation_config_override": {
                    "agent": {
                        "prompt": {"prompt": system_prompt},
                        "language": state.current_language,
                    },
                    "tts": {
                        "voice_id": config.ELEVENLABS_VOICE_ID_MULTILINGUAL or None,
                    },
                },
            }
            await el_ws.send(json.dumps(init_msg))
            logger.info(f"[{call_sid}] Sent ConvAI init (lang={state.current_language})")

            # ── Relay: Twilio -> ElevenLabs ───────────────────────────────────
            async def relay_twilio_to_el():
                nonlocal stream_sid
                try:
                    async for message in websocket.iter_text():
                        data = json.loads(message)
                        event = data.get("event")

                        if event == "connected":
                            logger.info(f"[{call_sid}] | Twilio stream: connected")

                        elif event == "start":
                            stream_sid = data["start"]["streamSid"]
                            logger.info(f"[{call_sid}] | Twilio stream started: {stream_sid}")

                        elif event == "media":
                            # Forward raw mu-law base64 audio to ElevenLabs
                            audio_b64 = data["media"]["payload"]
                            await el_ws.send(json.dumps({"user_audio_chunk": audio_b64}))

                        elif event == "stop":
                            logger.info(f"[{call_sid}] | Twilio stream stopped.")
                            break

                except WebSocketDisconnect:
                    logger.info(f"[{call_sid}] Twilio WebSocket disconnected.")
                except Exception as exc:
                    logger.error(f"[{call_sid}] Twilio relay error: {exc}")

            # ── Relay: ElevenLabs -> Twilio ───────────────────────────────────
            async def relay_el_to_twilio():
                try:
                    async for raw in el_ws:
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        msg_type = msg.get("type")

                        if msg_type == "audio":
                            # Forward ElevenLabs TTS audio back to Twilio
                            audio_b64 = msg.get("audio_event", {}).get("audio_base_64", "")
                            if audio_b64 and stream_sid:
                                await websocket.send_text(json.dumps({
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {"payload": audio_b64},
                                }))

                        elif msg_type == "interruption":
                            # User cut off the AI — clear Twilio audio buffer
                            if stream_sid:
                                await websocket.send_text(json.dumps({
                                    "event": "clear",
                                    "streamSid": stream_sid,
                                }))
                            logger.info(f"[{call_sid}] | [!] User interrupted AI — buffer cleared.")

                        elif msg_type == "user_transcript":
                            txt = msg.get("user_transcription_event", {}).get("user_transcript", "")
                            logger.info(f"[{call_sid}] |      USER SAID  >> {txt!r}")

                        elif msg_type == "agent_response":
                            txt = msg.get("agent_response_event", {}).get("agent_response", "")
                            logger.info(f"[{call_sid}] |      AI REPLY  << {txt!r}")

                        elif msg_type == "ping":
                            # Keepalive
                            event_id = msg.get("ping_event", {}).get("event_id")
                            await el_ws.send(json.dumps({"type": "pong", "event_id": event_id}))

                        elif msg_type in ("conversation_initiation_metadata",):
                            el_conv_id = msg.get("conversation_initiation_metadata_event", {}).get("conversation_id", "")
                            logger.info(f"[{call_sid}] ElevenLabs conversation_id: {el_conv_id}")

                except Exception as exc:
                    logger.info(f"[{call_sid}] ElevenLabs relay ended: {exc}")

            # Run both directions concurrently
            await asyncio.gather(
                relay_twilio_to_el(),
                relay_el_to_twilio(),
                return_exceptions=True,
            )

    except Exception as exc:
        logger.error(f"[{call_sid}] Bridge connection error: {exc}")
    finally:
        logger.info(f"[{call_sid}] +--- ElevenLabs Bridge session ended ---")
        unregister_call(call_sid)
