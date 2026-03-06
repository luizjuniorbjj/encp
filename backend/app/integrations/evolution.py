"""
ENCPServices - Evolution API Client (Single Instance)
==========================================================
HTTP client for Evolution API WhatsApp bridge.
Single-company: uses one fixed instance name from config (EVOLUTION_INSTANCE).
No multi-tenant instance management — just message sending and connection checks.

Forked from SegurIA, simplified for single-company use.
"""

import logging
from typing import Optional

import httpx

from app.config import EVOLUTION_INSTANCE

logger = logging.getLogger("encp.evolution")


class EvolutionAPI:
    """Single-instance Evolution API client for ENCPServices.

    Uses a fixed instance name (EVOLUTION_INSTANCE from config) for all
    operations. No per-agency instance management needed.
    """

    def __init__(self, base_url: str, api_key: str, instance_name: str = None):
        """
        Args:
            base_url: Evolution API base URL (e.g. "http://localhost:8087")
            api_key: Evolution API key
            instance_name: WhatsApp instance name (default: EVOLUTION_INSTANCE from config)
        """
        self.base = base_url.rstrip("/")
        self.api_key = api_key
        self.instance_name = instance_name or EVOLUTION_INSTANCE
        self.client = httpx.AsyncClient(timeout=30.0)
        self.headers = {"apikey": api_key, "Content-Type": "application/json"}

    # ============================================
    # CONNECTION
    # ============================================

    async def check_connection(self) -> dict:
        """Check connection status of the WhatsApp instance.

        Returns:
            dict with connection state (e.g. {"state": "open"} when connected)
        """
        resp = await self.client.get(
            f"{self.base}/instance/connectionState/{self.instance_name}",
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_qrcode(self) -> dict:
        """Get QR code for WhatsApp pairing.

        Returns:
            dict with QR code data for scanning with WhatsApp mobile app
        """
        resp = await self.client.get(
            f"{self.base}/instance/connect/{self.instance_name}",
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    # ============================================
    # SENDING MESSAGES
    # ============================================

    async def send_text_message(self, number: str, text: str) -> dict:
        """Send text message via WhatsApp.

        Args:
            number: Recipient phone number (with country code, e.g. "15551234567")
            text: Message text content
        """
        resp = await self.client.post(
            f"{self.base}/message/sendText/{self.instance_name}",
            headers=self.headers,
            json={"number": number, "text": text},
        )
        resp.raise_for_status()
        return resp.json()

    async def send_image(
        self,
        number: str,
        image_base64: str,
        caption: str = "",
        mimetype: str = "image/jpeg"
    ) -> dict:
        """Send image message via WhatsApp.

        Args:
            number: Recipient phone number
            image_base64: Base64-encoded image data
            caption: Optional image caption text
            mimetype: Image MIME type (default: image/jpeg)
        """
        payload = {
            "number": number,
            "mediaMessage": {
                "mediatype": "image",
                "media": f"data:{mimetype};base64,{image_base64}",
            },
        }
        if caption:
            payload["mediaMessage"]["caption"] = caption

        resp = await self.client.post(
            f"{self.base}/message/sendMedia/{self.instance_name}",
            headers=self.headers,
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def send_audio(self, number: str, audio_base64: str) -> dict:
        """Send audio message (as voice note) via WhatsApp.

        Args:
            number: Recipient phone number
            audio_base64: Base64-encoded audio data (mp3)
        """
        resp = await self.client.post(
            f"{self.base}/message/sendWhatsAppAudio/{self.instance_name}",
            headers=self.headers,
            json={
                "number": number,
                "audio": f"data:audio/mp3;base64,{audio_base64}",
            },
        )
        resp.raise_for_status()
        return resp.json()

    # ============================================
    # RECEIVING MEDIA
    # ============================================

    async def get_media_base64(self, full_message: dict) -> tuple:
        """Download media from a received message as base64.

        Args:
            full_message: Complete WAMessage object (with key + message fields)
                          needed by Baileys downloadMediaMessage.

        Returns:
            (base64_str, mimetype) tuple
        """
        resp = await self.client.post(
            f"{self.base}/chat/getBase64FromMediaMessage/{self.instance_name}",
            headers=self.headers,
            json={"message": full_message, "convertToMp4": False},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("base64", ""), data.get("mimetype", "")

    # ============================================
    # LIFECYCLE
    # ============================================

    async def close(self):
        """Close the underlying HTTP client."""
        await self.client.aclose()
