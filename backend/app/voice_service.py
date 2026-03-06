"""
ENCPServices - Voice Service
STT (Speech-to-Text) via Whisper + TTS (Text-to-Speech) via Edge TTS / OpenAI
Forked from SegurIA, adapted for tile/remodel company (single-company, no agency_id)
"""

import io
import os
import tempfile
import logging
from typing import Optional, Tuple
from pathlib import Path

from app.config import (
    OPENAI_API_KEY,
    VOICE_ENABLED,
    STT_MODEL,
    STT_MAX_FILE_SIZE,
    TTS_MODEL,
    TTS_VOICE,
    TTS_SPEED,
    EDGE_TTS_VOICE_PT,
    EDGE_TTS_VOICE_EN,
    EDGE_TTS_VOICE_ES,
    TTS_PROVIDER
)

logger = logging.getLogger("encp.voice")


# ============================================
# EDGE TTS VOICE CATALOG
# ============================================

EDGE_TTS_VOICES = {
    "en-US": [
        {"id": "en-US-JennyNeural", "name": "Jenny", "gender": "female", "lang": "en-US"},
        {"id": "en-US-GuyNeural", "name": "Guy", "gender": "male", "lang": "en-US"},
    ],
    "pt-BR": [
        {"id": "pt-BR-FranciscaNeural", "name": "Francisca", "gender": "female", "lang": "pt-BR"},
        {"id": "pt-BR-AntonioNeural", "name": "Antonio", "gender": "male", "lang": "pt-BR"},
    ],
    "es-MX": [
        {"id": "es-MX-DaliaNeural", "name": "Dalia", "gender": "female", "lang": "es-MX"},
        {"id": "es-MX-JorgeNeural", "name": "Jorge", "gender": "male", "lang": "es-MX"},
    ],
}


class VoiceService:
    """
    Voice service for ENCPServices
    - STT: Whisper (OpenAI) — converts client audio to text
    - TTS: Edge TTS (free) or OpenAI TTS (premium) — converts response to audio
    """

    def __init__(self):
        self.openai_client = None
        if OPENAI_API_KEY:
            from openai import OpenAI
            self.openai_client = OpenAI(api_key=OPENAI_API_KEY)
        self.enabled = VOICE_ENABLED and bool(OPENAI_API_KEY)

    # ============================================
    # SPEECH TO TEXT (Whisper)
    # ============================================

    async def speech_to_text(
        self,
        audio_bytes: bytes,
        filename: str = "audio.ogg",
        language: str = None
    ) -> Tuple[bool, str]:
        """
        Convert audio to text using OpenAI Whisper.

        Args:
            audio_bytes: Raw audio file bytes
            filename: Filename with extension (for format detection)
            language: Language code (None = auto-detect, "pt", "en", "es")

        Returns:
            Tuple[bool, str]: (success, transcribed_text or error_message)
        """
        if not self.enabled or not self.openai_client:
            return False, "Voice service disabled (no OpenAI API key)"

        if len(audio_bytes) > STT_MAX_FILE_SIZE:
            return False, f"Audio too large. Max {STT_MAX_FILE_SIZE // (1024*1024)}MB"

        if len(audio_bytes) < 100:
            return False, "Audio too short or empty"

        try:
            # Create temp file with correct extension
            suffix = Path(filename).suffix or ".ogg"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            try:
                with open(tmp_path, "rb") as audio_file:
                    kwargs = {
                        "model": STT_MODEL,
                        "file": audio_file,
                        "response_format": "text"
                    }
                    if language:
                        kwargs["language"] = language

                    transcript = self.openai_client.audio.transcriptions.create(**kwargs)

                text = transcript.strip() if isinstance(transcript, str) else str(transcript).strip()

                if not text:
                    return False, "Could not understand the audio. Please try again or type your message."

                logger.info(f"[STT] Transcribed: {text[:100]}...")
                return True, text

            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        except Exception as e:
            logger.error(f"[STT] Error: {e}")
            return False, f"Transcription error: {str(e)}"

    # ============================================
    # TEXT TO SPEECH — EDGE TTS (FREE)
    # ============================================

    async def text_to_speech_edge(
        self,
        text: str,
        voice: str = None,
        speed: float = None
    ) -> Tuple[bool, bytes, str]:
        """
        Convert text to speech using Edge TTS (free, no API key needed).

        Args:
            text: Text to convert
            voice: Edge TTS voice ID (e.g. "en-US-JennyNeural")
            speed: Speed multiplier (default 1.0)

        Returns:
            Tuple[bool, bytes, str]: (success, mp3_bytes, error_message)
        """
        if not text or not text.strip():
            return False, b"", "Empty text"

        # Limit text length
        max_chars = 4000
        if len(text) > max_chars:
            text = text[:max_chars] + "..."

        try:
            import edge_tts

            voice = voice or EDGE_TTS_VOICE_EN
            rate_str = "+0%" if not speed or speed == 1.0 else f"+{int((speed - 1) * 100)}%"

            communicate = edge_tts.Communicate(text, voice, rate=rate_str)
            audio_bytes = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_bytes += chunk["data"]

            if not audio_bytes:
                return False, b"", "Edge TTS returned empty audio"

            logger.info(f"[TTS-Edge] Generated {len(audio_bytes)} bytes with voice {voice}")
            return True, audio_bytes, ""

        except ImportError:
            return False, b"", "edge-tts package not installed"
        except Exception as e:
            logger.error(f"[TTS-Edge] Error: {e}")
            return False, b"", f"Edge TTS error: {str(e)}"

    # ============================================
    # TEXT TO SPEECH — OPENAI (PREMIUM)
    # ============================================

    async def text_to_speech_openai(
        self,
        text: str,
        voice: str = None,
        speed: float = None
    ) -> Tuple[bool, bytes, str]:
        """
        Convert text to speech using OpenAI TTS ($15/1M chars).

        Returns:
            Tuple[bool, bytes, str]: (success, mp3_bytes, error_message)
        """
        if not self.openai_client:
            return False, b"", "OpenAI client not available"

        if not text or not text.strip():
            return False, b"", "Empty text"

        max_chars = 4000
        if len(text) > max_chars:
            text = text[:max_chars] + "..."

        try:
            response = self.openai_client.audio.speech.create(
                model=TTS_MODEL,
                voice=voice or TTS_VOICE,
                input=text,
                speed=speed or TTS_SPEED,
                response_format="mp3"
            )

            audio_bytes = response.content
            logger.info(f"[TTS-OpenAI] Generated {len(audio_bytes)} bytes")
            return True, audio_bytes, ""

        except Exception as e:
            logger.error(f"[TTS-OpenAI] Error: {e}")
            return False, b"", f"OpenAI TTS error: {str(e)}"

    # ============================================
    # UNIFIED TTS DISPATCHER
    # ============================================

    async def text_to_speech(
        self,
        text: str,
        voice: str = None,
        speed: float = None,
        provider: str = None
    ) -> Tuple[bool, bytes, str]:
        """
        Convert text to speech. Provider: "edge" (free) or "openai" (premium).
        """
        provider = provider or TTS_PROVIDER
        if provider == "openai":
            return await self.text_to_speech_openai(text, voice, speed)
        return await self.text_to_speech_edge(text, voice, speed)

    # ============================================
    # FULL VOICE CHAT PIPELINE
    # ============================================

    async def chat_with_voice(
        self,
        audio_bytes: bytes,
        filename: str,
        chat_callback,
        user_id: str,
        conversation_id: Optional[str] = None,
        return_audio: bool = True,
        language: str = None,
        voice: str = None,
        tts_provider: str = None
    ) -> dict:
        """
        Full voice pipeline: Audio in -> STT -> Chat -> TTS -> Audio out

        Args:
            audio_bytes: Client's audio
            filename: Audio filename (for format detection)
            chat_callback: Async chat function (ai_service.chat)
            user_id: Client user ID
            conversation_id: Existing conversation (optional)
            return_audio: Whether to generate TTS response
            language: STT language (None = auto-detect)
            voice: TTS voice ID
            tts_provider: "edge" or "openai"
        """
        result = {
            "success": False,
            "user_text": "",
            "response_text": "",
            "response_audio": None,
            "conversation_id": conversation_id,
            "error": ""
        }

        # 1. Transcribe client audio
        stt_success, user_text = await self.speech_to_text(audio_bytes, filename, language=language)

        if not stt_success:
            result["error"] = user_text
            return result

        result["user_text"] = user_text

        # 2. Chat with AI (add voice mode instruction for concise response)
        voice_instruction = "[VOICE MODE - Respond in 1-2 short, direct sentences. Be concise.]\n"
        try:
            chat_result = await chat_callback(
                user_id=user_id,
                message=voice_instruction + user_text,
                conversation_id=conversation_id
            )
            result["response_text"] = chat_result["response"]
            result["conversation_id"] = chat_result["conversation_id"]
        except Exception as e:
            result["error"] = f"Chat error: {str(e)}"
            return result

        # 3. Generate audio response (if requested)
        if return_audio and result["response_text"]:
            tts_success, audio, tts_error = await self.text_to_speech(
                result["response_text"],
                voice=voice,
                provider=tts_provider
            )
            if tts_success:
                result["response_audio"] = audio
            else:
                logger.warning(f"[VOICE] TTS failed: {tts_error}")

        result["success"] = True
        return result

    # ============================================
    # AVAILABLE VOICES
    # ============================================

    def get_available_voices(self) -> dict:
        """Return available voices for both Edge TTS and OpenAI TTS"""
        voices = {
            "edge": EDGE_TTS_VOICES,
            "openai": [
                {"id": "alloy", "name": "Alloy", "gender": "neutral"},
                {"id": "echo", "name": "Echo", "gender": "male"},
                {"id": "fable", "name": "Fable", "gender": "neutral"},
                {"id": "nova", "name": "Nova", "gender": "female"},
                {"id": "onyx", "name": "Onyx", "gender": "male"},
                {"id": "shimmer", "name": "Shimmer", "gender": "female"},
            ],
            "default_provider": TTS_PROVIDER,
            "default_voice": EDGE_TTS_VOICE_EN if TTS_PROVIDER == "edge" else TTS_VOICE
        }
        return voices
