"""
ENCPServices - Webhook Routes
WhatsApp message ingestion via Evolution API — single instance (no multi-tenant)
Supports: text, images, and voice messages

Includes:
  - POST /webhook/evolution — receive WhatsApp messages from single instance
"""

import asyncio
import base64
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.database import get_db, Database
from app.ai_service import AIService
from app.voice_service import VoiceService
from app.config import (
    EVOLUTION_API_URL,
    EVOLUTION_API_KEY,
    EVOLUTION_INSTANCE,
    EVOLUTION_WEBHOOK_SECRET
)

logger = logging.getLogger("encp.webhook")

router = APIRouter(prefix="/webhook", tags=["Webhook"])


# ============================================
# MODELS
# ============================================

class WebhookResponse(BaseModel):
    reply: str
    user_id: str
    conversation_id: str
    is_new_client: bool
    audio_reply_base64: Optional[str] = None


# ============================================
# MEDIA DOWNLOAD UTILITY
# ============================================

MAX_MEDIA_SIZE = 10 * 1024 * 1024  # 10MB


async def download_media(url: str, max_size: int = MAX_MEDIA_SIZE) -> bytes:
    """Download media from WhatsApp URL with size limit"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        if len(response.content) > max_size:
            raise ValueError(f"Media too large: {len(response.content)} bytes (max {max_size})")
        return response.content


# ============================================
# COMMON: Resolve client from phone number
# ============================================

async def _resolve_client(db: Database, phone: str, sender_name: str = None):
    """Get or create client by phone. Returns (user_id, is_new)"""
    # Check if user with this phone exists
    client = await db.get_user_by_phone(phone)

    if client:
        user_id = str(client["id"])
        return user_id, False

    # Auto-create user from phone number
    email_placeholder = f"{phone.replace('+', '')}@whatsapp.placeholder"
    client = await db.create_user(
        email=email_placeholder,
        phone=phone,
        nome=sender_name,
        role="client"
    )
    user_id = str(client["id"])

    # Create initial profile
    await db.create_user_profile(
        user_id=user_id,
        nome=sender_name,
        phone=phone
    )

    return user_id, True


# ============================================
# COMMON: Process media message
# ============================================

async def _process_media_message(
    ai: AIService,
    user_id: str,
    message: str,
    media_url: str,
    media_type: str,
    is_voice: bool,
    channel: str = None
) -> dict:
    """
    Process a media message (image or voice).
    Returns dict with: response, conversation_id, audio_reply_base64
    """
    result = {
        "response": "",
        "conversation_id": None,
        "audio_reply_base64": None
    }

    try:
        media_bytes = await download_media(media_url)
    except Exception as e:
        logger.error(f"[MEDIA] Download failed: {e}")
        chat_result = await ai.chat(
            user_id=user_id,
            message=message or "I tried to send a file but it didn't work.",
            channel=channel
        )
        result["response"] = chat_result["response"]
        result["conversation_id"] = chat_result["conversation_id"]
        return result

    # IMAGE: Chat with vision
    if media_type and media_type.startswith("image/"):
        img_b64 = base64.b64encode(media_bytes).decode("utf-8")

        if not message.strip():
            message = "What do you see in this image? Is this related to a tile, flooring, or remodeling project?"

        chat_result = await ai.chat(
            user_id=user_id,
            message=message,
            image_data=img_b64,
            image_media_type=media_type,
            channel=channel
        )

        result["response"] = chat_result["response"]
        result["conversation_id"] = chat_result["conversation_id"]

        if chat_result.get("_post_process"):
            await ai.post_process_chat(chat_result["_post_process"])

    # AUDIO: Transcribe + chat + optional TTS response
    elif (media_type and media_type.startswith("audio/")) or is_voice:
        vs = VoiceService()
        stt_success, transcription = await vs.speech_to_text(
            audio_bytes=media_bytes,
            filename="voice.ogg"
        )

        if stt_success:
            logger.info(f"[STT] Transcribed: {transcription[:80]}...")
            chat_result = await ai.chat(
                user_id=user_id,
                message=transcription,
                channel=channel
            )
            result["response"] = chat_result["response"]
            result["conversation_id"] = chat_result["conversation_id"]

            if chat_result.get("_post_process"):
                await ai.post_process_chat(chat_result["_post_process"])

            # Generate voice response
            tts_success, audio_reply, _ = await vs.text_to_speech(result["response"])
            if tts_success:
                result["audio_reply_base64"] = base64.b64encode(audio_reply).decode("utf-8")
        else:
            result["response"] = "I couldn't understand the audio. Could you try again or type your message?"

    else:
        # Unknown media type — treat as text
        chat_result = await ai.chat(
            user_id=user_id,
            message=message or "I sent a file.",
            channel=channel
        )
        result["response"] = chat_result["response"]
        result["conversation_id"] = chat_result["conversation_id"]

    return result


# ============================================
# WEBHOOK VERIFICATION
# ============================================

def _verify_evolution_webhook(request: Request) -> bool:
    """Verify Evolution API webhook authenticity.
    Checks the apikey header against EVOLUTION_WEBHOOK_SECRET.
    If no secret is configured, accepts all requests (dev mode).
    """
    if not EVOLUTION_WEBHOOK_SECRET:
        return True  # No secret configured — dev mode
    incoming_key = request.headers.get("apikey", "")
    return incoming_key == EVOLUTION_WEBHOOK_SECRET


# ============================================
# PHONE EXTRACTION
# ============================================

def _extract_phone_from_jid(jid: str) -> str:
    """Extract phone number from WhatsApp JID and normalize to E.164.
    e.g., '5511999999999@s.whatsapp.net' -> '+5511999999999'
    """
    raw = jid.split("@")[0] if "@" in jid else jid
    digits = "".join(c for c in raw if c.isdigit())
    if not digits:
        return raw
    return f"+{digits}"


# ============================================
# EVOLUTION API MESSAGE HANDLER
# ============================================

async def _handle_evolution_message(
    db: Database,
    evo_client,
    data: dict,
):
    """Process a single Evolution API message event (runs as background task)."""
    key = data.get("key", {})
    full_message = data.get("_fullMessage")
    jid = key.get("remoteJid", "")
    phone = data.get("phone") or _extract_phone_from_jid(jid)
    if not phone.startswith("+"):
        phone = f"+{phone}"
    push_name = data.get("pushName", "")
    message = data.get("message", {})
    msg_type = data.get("messageType", "")

    logger.info(f"[EVO] {push_name} ({phone[:6]}***) type={msg_type}")

    # Resolve client
    user_id, is_new = await _resolve_client(db, phone, push_name)

    if is_new:
        logger.info(f"[EVO] New lead from {phone[:6]}***")
        # Auto-create lead for new WhatsApp contacts
        try:
            await db.create_lead(
                name=push_name or None,
                phone=phone,
                source="whatsapp",
                user_id=user_id
            )
        except Exception as e:
            logger.warning(f"[EVO] Could not auto-create lead: {e}")

    ai = AIService(db)

    async def _send_reply(text: str):
        """Send text reply via Evolution API."""
        reply_jid = jid
        chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
        for chunk in chunks:
            try:
                await evo_client.send_text(EVOLUTION_INSTANCE, reply_jid, chunk)
            except Exception as e:
                logger.error(f"[EVO:SEND] Failed to send to {phone[:6]}***: {e}")

    try:
        # === TEXT ===
        if msg_type in ("conversation", "extendedTextMessage"):
            text = message.get("conversation", "") or message.get(
                "extendedTextMessage", {}
            ).get("text", "")
            if text:
                result = await ai.chat(
                    user_id=user_id, message=text,
                    channel="whatsapp"
                )
                await _send_reply(result["response"])
                if result.get("_post_process"):
                    await ai.post_process_chat(result["_post_process"])

        # === IMAGE ===
        elif msg_type == "imageMessage":
            caption = message.get("imageMessage", {}).get("caption", "")
            try:
                media_b64, mimetype = await evo_client.get_media_base64(
                    EVOLUTION_INSTANCE, full_message or {"key": key, "message": message}
                )
                if not media_b64:
                    raise ValueError("Empty media")
            except Exception as e:
                logger.error(f"[EVO:IMAGE] Media download failed: {e}")
                await _send_reply("I couldn't process the image. Could you try sending it again?")
                return

            context = caption.strip() if caption.strip() else (
                "The client sent a photo. It might be of a room, floor, "
                "or area they want tiled or remodeled. Describe what you see and ask "
                "how you can help with their tile or remodeling project."
            )

            result = await ai.chat(
                user_id=user_id,
                message=context,
                image_data=media_b64,
                image_media_type=mimetype or "image/jpeg",
                channel="whatsapp",
            )
            await _send_reply(result["response"])
            if result.get("_post_process"):
                await ai.post_process_chat(result["_post_process"])

        # === AUDIO ===
        elif msg_type in ("audioMessage", "pttMessage"):
            try:
                media_b64, mimetype = await evo_client.get_media_base64(
                    EVOLUTION_INSTANCE, full_message or {"key": key, "message": message}
                )
                if not media_b64:
                    raise ValueError("Empty media")
                audio_bytes = base64.b64decode(media_b64)
            except Exception as e:
                logger.error(f"[EVO:AUDIO] Media download failed: {e}")
                await _send_reply("I couldn't process the audio. Could you try again or type your message?")
                return

            vs = VoiceService()
            stt_ok, transcription = await vs.speech_to_text(audio_bytes, "voice.ogg")

            if not stt_ok:
                await _send_reply("I couldn't understand the audio. Could you try again or type your message?")
                return

            result = await ai.chat(
                user_id=user_id, message=transcription,
                channel="whatsapp"
            )
            await _send_reply(result["response"])

            # TTS reply
            try:
                tts_ok, audio_reply, _ = await vs.text_to_speech(result["response"])
                if tts_ok and audio_reply:
                    audio_b64 = base64.b64encode(audio_reply).decode("utf-8")
                    await evo_client.send_audio(EVOLUTION_INSTANCE, jid, audio_b64)
            except Exception as e:
                logger.warning(f"[EVO:TTS] Failed: {e}")

            if result.get("_post_process"):
                await ai.post_process_chat(result["_post_process"])

        # === DOCUMENT (image sent as file) ===
        elif msg_type == "documentMessage":
            mime = message.get("documentMessage", {}).get("mimetype", "")
            if mime.startswith("image/"):
                data["messageType"] = "imageMessage"
                await _handle_evolution_message(db, evo_client, data)
            else:
                await _send_reply(
                    "I can process text, photos, and voice messages. "
                    "Feel free to send me a photo of the area you'd like tiled or remodeled!"
                )
        else:
            logger.info(f"[EVO] Unsupported message type: {msg_type}")

    except Exception as e:
        logger.error(f"[EVO] Error handling message: {e}", exc_info=True)
        await _send_reply("Sorry, something went wrong. Please try again.")


# ============================================
# EVOLUTION API WEBHOOK ENDPOINT
# ============================================

@router.post("/evolution")
async def evolution_webhook(request: Request):
    """
    Evolution API webhook — single instance.
    Receives WhatsApp events and processes messages.
    """
    # Verify webhook authenticity
    if not _verify_evolution_webhook(request):
        logger.warning("[EVO] Rejected: invalid webhook apikey")
        return {"status": "ok"}

    try:
        payload = await request.json()
    except Exception:
        return {"status": "ok"}

    event = payload.get("event", "")
    logger.info(f"[EVO] event={event}")

    # Import db instance directly for webhook (no auth context)
    from app.database import _db as db
    if not db:
        logger.error("[EVO] Database not available")
        return {"status": "ok"}

    # === CONNECTION UPDATE ===
    if event.upper() == "CONNECTION_UPDATE":
        state_data = payload.get("data", {})
        state = state_data.get("state", "").lower()

        if state == "open":
            await db.log_audit(
                action="whatsapp_connected",
                details={"instance": EVOLUTION_INSTANCE},
            )
            logger.info(f"[EVO] WhatsApp CONNECTED")
        elif state in ("close", "closed"):
            await db.log_audit(
                action="whatsapp_disconnected",
                details={"instance": EVOLUTION_INSTANCE},
            )
            logger.warning(f"[EVO] WhatsApp DISCONNECTED")
        return {"status": "ok"}

    # === MESSAGE ===
    if event.upper() in ("MESSAGES.UPSERT", "MESSAGES_UPSERT"):
        data = payload.get("data", {})
        key = data.get("key", {})

        # Skip own messages and group messages
        if key.get("fromMe", False):
            return {"status": "ok"}
        jid = key.get("remoteJid", "")
        if "@g.us" in jid:
            return {"status": "ok"}

        # Lazy-init Evolution client for replies
        from app.integrations.evolution import EvolutionAPI
        evo_client = EvolutionAPI(EVOLUTION_API_URL, EVOLUTION_API_KEY)

        # Process async so we respond 200 immediately
        asyncio.create_task(
            _handle_evolution_message(db, evo_client, data)
        )

    return {"status": "ok"}
