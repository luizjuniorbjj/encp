"""
ENCPServices - Chat Routes
Main chat endpoint + conversation management
Forked from SegurIA, removed agency_id/multi-tenant
"""

import base64
import uuid
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks, Request
from pydantic import BaseModel

from app.auth import get_current_user
from app.database import get_db, Database
from app.ai_service import AIService
from app.security import rate_limiter

router = APIRouter(prefix="/chat", tags=["Chat"])


# ============================================
# MODELS
# ============================================

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    model_used: str
    tokens_used: int
    extraction: dict = None


class ConversationResponse(BaseModel):
    id: str
    started_at: str
    last_message_at: str
    message_count: int
    resumo: Optional[str] = None
    is_archived: bool = False


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class RenameRequest(BaseModel):
    resumo: str


# ============================================
# MAIN CHAT ENDPOINT
# ============================================

@router.post("/", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Send a message and get AI response"""
    user_id = current_user["user_id"]

    # Rate limiting
    if not rate_limiter.is_allowed(user_id, max_requests=30, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a moment.")

    # Validate message
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if len(request.message) > 5000:
        raise HTTPException(status_code=400, detail="Message too long (max 5000 characters)")

    # Call AI service
    ai_service = AIService(db)
    result = await ai_service.chat(
        user_id=user_id,
        message=request.message.strip(),
        conversation_id=request.conversation_id
    )

    # Schedule background post-processing
    if "_post_process" in result:
        background_tasks.add_task(ai_service.post_process_chat, result["_post_process"])

    # Audit log
    await db.log_audit(
        user_id=user_id,
        action="message_sent",
        details={"conversation_id": result["conversation_id"]}
    )

    return ChatResponse(
        response=result["response"],
        conversation_id=result["conversation_id"],
        model_used=result["model_used"],
        tokens_used=result["tokens_used"]
    )


# ============================================
# VOICE CHAT (audio in -> text + audio out)
# ============================================

@router.post("/voice", response_model=ChatResponse)
async def voice_chat(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    conversation_id: str = Form(None),
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Send voice message: transcribe -> AI chat -> return text response"""
    user_id = current_user["user_id"]

    if not rate_limiter.is_allowed(user_id, max_requests=10, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a moment.")

    from app.voice_service import VoiceService
    from app.config import STT_MAX_FILE_SIZE

    audio_bytes = await audio.read()
    if len(audio_bytes) > STT_MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"Audio too large (max {STT_MAX_FILE_SIZE // (1024*1024)}MB)")

    vs = VoiceService()
    success, transcription = await vs.speech_to_text(
        audio_bytes=audio_bytes,
        filename=audio.filename or "audio.ogg"
    )

    if not success:
        raise HTTPException(status_code=422, detail="Could not transcribe audio. Please try again.")

    # Chat with transcribed text
    ai_service = AIService(db)
    result = await ai_service.chat(
        user_id=user_id,
        message=transcription,
        conversation_id=conversation_id
    )

    if "_post_process" in result:
        background_tasks.add_task(ai_service.post_process_chat, result["_post_process"])

    await db.log_audit(
        user_id=user_id,
        action="voice_message_sent",
        details={"conversation_id": result["conversation_id"], "transcription_length": len(transcription)}
    )

    return ChatResponse(
        response=result["response"],
        conversation_id=result["conversation_id"],
        model_used=result["model_used"],
        tokens_used=result["tokens_used"]
    )


# ============================================
# CHAT WITH FILE (images)
# ============================================

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

@router.post("/with-file", response_model=ChatResponse)
async def send_message_with_file(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    message: str = Form(""),
    conversation_id: str = Form(None),
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """
    Send message with image attachments.
    Useful for clients sending photos of rooms, walls, color swatches, etc.
    """
    user_id = current_user["user_id"]

    if not rate_limiter.is_allowed(user_id, max_requests=10, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a moment.")

    if len(files) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 files per request")

    images = []
    for file in files:
        content_type = file.content_type or ""

        if content_type in ALLOWED_IMAGE_TYPES:
            file_bytes = await file.read()
            if len(file_bytes) > MAX_IMAGE_SIZE:
                raise HTTPException(status_code=400, detail=f"Image too large: {file.filename} (max 5MB)")
            img_b64 = base64.b64encode(file_bytes).decode("utf-8")
            images.append((img_b64, content_type))
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {content_type}. Allowed: JPEG, PNG, GIF, WebP"
            )

    if not images:
        raise HTTPException(status_code=400, detail="No valid files uploaded")

    # Default message if none provided
    if not message.strip():
        message = f"What do you see in these {len(images)} images?" if len(images) > 1 else "What do you see in this image?"

    ai_service = AIService(db)
    result = await ai_service.chat(
        user_id=user_id,
        message=message.strip(),
        conversation_id=conversation_id,
        images=images
    )

    if "_post_process" in result:
        background_tasks.add_task(ai_service.post_process_chat, result["_post_process"])

    await db.log_audit(
        user_id=user_id,
        action="message_with_files_sent",
        details={
            "conversation_id": result["conversation_id"],
            "file_count": len(images)
        }
    )

    return ChatResponse(
        response=result["response"],
        conversation_id=result["conversation_id"],
        model_used=result["model_used"],
        tokens_used=result["tokens_used"]
    )


# ============================================
# CONVERSATION HISTORY
# ============================================

@router.get("/history")
async def get_chat_history(
    conversation_id: Optional[str] = None,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """
    Get conversation history.
    If conversation_id is provided, returns messages for that conversation.
    Otherwise, returns list of recent conversations.
    """
    user_id = current_user["user_id"]

    if conversation_id:
        # Get messages for specific conversation
        messages = await db.get_messages(
            conversation_id,
            user_id,
            limit=min(limit, 200)
        )
        return {
            "conversation_id": conversation_id,
            "messages": [
                {
                    "id": str(m["id"]),
                    "role": m["role"],
                    "content": m["content"],
                    "created_at": m["created_at"].isoformat() if m.get("created_at") else None
                }
                for m in messages
            ]
        }
    else:
        # List recent conversations
        conversations = await db.get_conversations(user_id, limit=min(limit, 50))
        return {
            "conversations": [
                {
                    "id": str(c["id"]),
                    "started_at": c["started_at"].isoformat() if c.get("started_at") else None,
                    "last_message_at": c["last_message_at"].isoformat() if c.get("last_message_at") else None,
                    "message_count": c.get("message_count", 0),
                    "resumo": c.get("resumo"),
                    "is_archived": c.get("is_archived", False)
                }
                for c in conversations
            ]
        }


# ============================================
# CONVERSATION MANAGEMENT
# ============================================

@router.get("/conversations")
async def list_conversations(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """List recent conversations"""
    conversations = await db.get_conversations(
        current_user["user_id"],
        limit=min(limit, 50)
    )

    return [
        {
            "id": str(c["id"]),
            "started_at": c["started_at"].isoformat() if c.get("started_at") else None,
            "last_message_at": c["last_message_at"].isoformat() if c.get("last_message_at") else None,
            "message_count": c.get("message_count", 0),
            "resumo": c.get("resumo"),
            "is_archived": c.get("is_archived", False)
        }
        for c in conversations
    ]


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Get messages for a conversation (decrypted)"""
    messages = await db.get_messages(
        conversation_id,
        current_user["user_id"],
        limit=min(limit, 200)
    )

    return [
        {
            "id": str(m["id"]),
            "role": m["role"],
            "content": m["content"],
            "created_at": m["created_at"].isoformat() if m.get("created_at") else None
        }
        for m in messages
    ]


@router.post("/conversations/{conversation_id}/archive")
async def archive_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Archive a conversation"""
    await db.update_conversation(conversation_id, is_archived=True)

    return {"message": "Conversation archived"}


@router.patch("/conversations/{conversation_id}/rename")
async def rename_conversation(
    conversation_id: str,
    request: RenameRequest,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Rename/update conversation summary"""
    await db.update_conversation(conversation_id, resumo=request.resumo)

    return {"message": "Conversation updated"}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Delete conversation and all its messages"""
    await db.execute(
        "DELETE FROM messages WHERE conversation_id = $1",
        conversation_id
    )
    await db.execute(
        "DELETE FROM conversations WHERE id = $1 AND user_id = $2",
        conversation_id, current_user["user_id"]
    )

    await db.log_audit(
        user_id=current_user["user_id"],
        action="conversation_deleted",
        details={"conversation_id": conversation_id}
    )

    return {"message": "Conversation deleted"}


# ============================================
# GUEST CHAT (no auth required — landing page widget)
# ============================================

class GuestChatRequest(BaseModel):
    message: str
    guest_id: Optional[str] = None
    conversation_id: Optional[str] = None


@router.post("/guest")
async def guest_chat(
    request: GuestChatRequest,
    req: Request,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_db)
):
    """
    Public chat endpoint for landing page widget.
    No authentication required. Auto-creates guest user.
    Uses GPT-4o-mini to reduce costs.
    """
    # Rate limit by IP
    client_ip = req.client.host if req.client else "unknown"
    if not rate_limiter.is_allowed(f"guest_{client_ip}", max_requests=20, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a moment.")

    # Validate message
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if len(request.message) > 2000:
        raise HTTPException(status_code=400, detail="Message too long (max 2000 characters)")

    # Get or create guest user
    guest_id = request.guest_id
    user_id = None

    if guest_id:
        # Try to find existing guest user
        guest_email = f"{guest_id}@guest.encp"
        user = await db.get_user_by_email(guest_email)
        if user:
            user_id = str(user["id"])

    if not user_id:
        # Create new guest user
        guest_id = str(uuid.uuid4())[:12]
        guest_email = f"{guest_id}@guest.encp"
        user = await db.create_user(
            email=guest_email,
            role="guest",
            accepted_terms=True
        )
        user_id = str(user["id"])

    # Force OpenAI provider for guest chat (cheaper)
    ai_service = AIService(db)
    ai_service.provider = "openai"

    # Ensure OpenAI client is initialized
    if not ai_service.openai_client:
        from app.config import OPENAI_API_KEY
        import openai
        ai_service.openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

    result = await ai_service.chat(
        user_id=user_id,
        message=request.message.strip(),
        conversation_id=request.conversation_id,
        channel="web_widget"
    )

    # Background post-processing
    if "_post_process" in result:
        background_tasks.add_task(ai_service.post_process_chat, result["_post_process"])

    return {
        "response": result["response"],
        "conversation_id": result["conversation_id"],
        "guest_id": guest_id,
        "model_used": result["model_used"],
        "tokens_used": result["tokens_used"]
    }
