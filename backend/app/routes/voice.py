"""
ENCPServices - Voice Routes
STT/TTS endpoints for voice chat — no agency_id
"""

import base64
import logging

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional

from app.auth import get_current_user
from app.database import get_db, Database
from app.ai_service import AIService
from app.voice_service import VoiceService
from app.security import rate_limiter
from app.config import VOICE_ENABLED, STT_MAX_FILE_SIZE

logger = logging.getLogger("encp.voice")

router = APIRouter(prefix="/voice", tags=["Voice"])

ALLOWED_AUDIO_TYPES = {
    "audio/webm", "audio/ogg", "audio/mpeg", "audio/mp3",
    "audio/wav", "audio/x-wav", "audio/mp4", "audio/m4a",
    "audio/x-m4a", "audio/opus", "video/webm"
}


# ============================================
# MODELS
# ============================================

class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None
    speed: Optional[float] = None
    provider: Optional[str] = None  # "edge" (free) or "openai"


class VoiceChatResponse(BaseModel):
    success: bool
    user_text: str = ""
    response_text: str = ""
    response_audio_base64: Optional[str] = None
    conversation_id: Optional[str] = None
    error: str = ""


# ============================================
# STATUS
# ============================================

@router.get("/status")
async def voice_status():
    """Check if voice service is available"""
    vs = VoiceService()
    return {
        "enabled": vs.enabled,
        "stt": "whisper" if vs.enabled else "disabled",
        "tts": "edge (free)" if VOICE_ENABLED else "disabled",
        "openai_tts": bool(vs.openai_client)
    }


# ============================================
# AVAILABLE VOICES
# ============================================

@router.get("/voices")
async def list_voices():
    """List available TTS voices (Edge TTS + OpenAI)"""
    vs = VoiceService()
    return vs.get_available_voices()


# ============================================
# SPEECH TO TEXT (upload audio, get text)
# ============================================

@router.post("/stt")
async def speech_to_text(
    audio: UploadFile = File(...),
    language: str = Form(None),
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Transcribe audio to text using Whisper"""
    user_id = current_user["user_id"]

    if not rate_limiter.is_allowed(user_id, max_requests=10, window_seconds=60):
        raise HTTPException(429, "Too many requests")

    content_type = audio.content_type or ""
    if content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(400, f"Unsupported audio format: {content_type}")

    audio_bytes = await audio.read()
    if len(audio_bytes) > STT_MAX_FILE_SIZE:
        raise HTTPException(400, f"Audio too large (max {STT_MAX_FILE_SIZE // (1024*1024)}MB)")

    vs = VoiceService()
    success, text = await vs.speech_to_text(
        audio_bytes=audio_bytes,
        filename=audio.filename or "audio.ogg",
        language=language
    )

    if not success:
        raise HTTPException(422, text)

    await db.log_audit(
        user_id=user_id,
        action="voice_stt",
        details={"chars": len(text), "language": language}
    )

    return {"text": text, "language": language or "auto"}


# ============================================
# TEXT TO SPEECH (send text, get MP3)
# ============================================

@router.post("/tts")
async def text_to_speech(
    request: TTSRequest,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Convert text to speech (returns MP3 audio)"""
    user_id = current_user["user_id"]

    if not rate_limiter.is_allowed(user_id, max_requests=10, window_seconds=60):
        raise HTTPException(429, "Too many requests")

    if not request.text.strip():
        raise HTTPException(400, "Text cannot be empty")

    vs = VoiceService()
    success, audio_bytes, error = await vs.text_to_speech(
        text=request.text,
        voice=request.voice,
        speed=request.speed,
        provider=request.provider
    )

    if not success:
        raise HTTPException(422, error)

    await db.log_audit(
        user_id=user_id,
        action="voice_tts",
        details={"chars": len(request.text), "provider": request.provider or "edge"}
    )

    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={"Content-Disposition": "attachment; filename=encp_response.mp3"}
    )


# ============================================
# FULL VOICE CHAT (audio in -> text + audio out)
# ============================================

@router.post("/chat", response_model=VoiceChatResponse)
async def voice_chat(
    audio: UploadFile = File(...),
    conversation_id: str = Form(None),
    language: str = Form(None),
    voice: str = Form(None),
    tts_provider: str = Form(None),
    return_audio: bool = Form(True),
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """
    Full voice chat: upload audio -> transcribe -> AI chat -> TTS response.
    Returns text response + optional audio (base64).
    """
    user_id = current_user["user_id"]

    if not rate_limiter.is_allowed(user_id, max_requests=10, window_seconds=60):
        raise HTTPException(429, "Too many requests")

    content_type = audio.content_type or ""
    if content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(400, f"Unsupported audio format: {content_type}")

    audio_bytes = await audio.read()
    if len(audio_bytes) > STT_MAX_FILE_SIZE:
        raise HTTPException(400, f"Audio too large (max {STT_MAX_FILE_SIZE // (1024*1024)}MB)")

    vs = VoiceService()
    ai_service = AIService(db)

    result = await vs.chat_with_voice(
        audio_bytes=audio_bytes,
        filename=audio.filename or "audio.ogg",
        chat_callback=ai_service.chat,
        user_id=user_id,
        conversation_id=conversation_id,
        return_audio=return_audio,
        language=language,
        voice=voice,
        tts_provider=tts_provider
    )

    # Encode audio to base64 for JSON response
    audio_b64 = None
    if result.get("response_audio"):
        audio_b64 = base64.b64encode(result["response_audio"]).decode("utf-8")

    await db.log_audit(
        user_id=user_id,
        action="voice_chat",
        details={
            "conversation_id": result.get("conversation_id"),
            "stt_chars": len(result.get("user_text", "")),
            "tts_generated": audio_b64 is not None
        }
    )

    return VoiceChatResponse(
        success=result["success"],
        user_text=result.get("user_text", ""),
        response_text=result.get("response_text", ""),
        response_audio_base64=audio_b64,
        conversation_id=result.get("conversation_id"),
        error=result.get("error", "")
    )
