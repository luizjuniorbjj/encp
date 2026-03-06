"""
ENCP Services Group - Configuracoes
Variaveis de ambiente e configuracoes globais
Single-company system (NOT multi-tenant)
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ============================================
# API KEYS
# ============================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")  # Para STT (Whisper) e TTS

# ============================================
# DATABASE
# ============================================
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/enpcservices")

# ============================================
# REDIS
# ============================================
REDIS_URL = os.getenv("REDIS_URL", "")

# ============================================
# SECURITY
# ============================================
SECRET_KEY = os.getenv("SECRET_KEY", "encp-chave-secreta-alterar-em-producao")

# ENCRYPTION_KEY - CRITICO: Esta chave NUNCA pode mudar ou os dados serao perdidos!
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    raise RuntimeError(
        "[CRITICAL] ENCRYPTION_KEY nao configurada! "
        "Esta variavel e OBRIGATORIA para criptografia de dados. "
        "Configure no .env ou variaveis de ambiente antes de iniciar."
    )

JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_HOURS = 1
JWT_REFRESH_TOKEN_DAYS = 30

# ============================================
# APP SETTINGS
# ============================================
APP_NAME = "ENCPServices"
APP_VERSION = "1.0.0"
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

MAINTENANCE_MODE = os.getenv("MAINTENANCE_MODE", "False").lower() == "true"

# ============================================
# AI SETTINGS
# ============================================
AI_PROVIDER = os.getenv("AI_PROVIDER", "anthropic")

# Anthropic models
AI_MODEL_PRIMARY = "claude-sonnet-4-20250514"       # Chat principal
AI_MODEL_EXTRACTION = "claude-sonnet-4-20250514"    # Extracao de memorias - SEMPRE Sonnet

# OpenAI models (fallback when no Anthropic key)
OPENAI_MODEL_PRIMARY = "gpt-4o-mini"
OPENAI_MODEL_EXTRACTION = "gpt-4o-mini"

MAX_TOKENS_RESPONSE = 2000
MAX_CONTEXT_TOKENS = 4000

# Voice Settings
VOICE_ENABLED = os.getenv("VOICE_ENABLED", "True").lower() == "true"
STT_MODEL = "whisper-1"
STT_MAX_FILE_SIZE = 25 * 1024 * 1024
TTS_MODEL = "tts-1-hd"
TTS_VOICE = "nova"
TTS_SPEED = 1.0

# Edge TTS (free) — default voices per language
EDGE_TTS_VOICE_EN = os.getenv("EDGE_TTS_VOICE_EN", "en-US-JennyNeural")
EDGE_TTS_VOICE_ES = os.getenv("EDGE_TTS_VOICE_ES", "es-MX-DaliaNeural")
EDGE_TTS_VOICE_PT = os.getenv("EDGE_TTS_VOICE_PT", "pt-BR-FranciscaNeural")

# TTS Provider: "edge" (free) or "openai" ($15/1M chars)
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "openai")

# ============================================
# OAUTH SETTINGS
# ============================================
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8004/auth/google/callback")

# ============================================
# EVOLUTION API (WhatsApp) — Single instance
# ============================================
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8088")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "encp")
EVOLUTION_WEBHOOK_BASE_URL = os.getenv(
    "EVOLUTION_WEBHOOK_BASE_URL", "http://host.docker.internal:8004"
)
EVOLUTION_WEBHOOK_SECRET = os.getenv("EVOLUTION_WEBHOOK_SECRET", "")

# ============================================
# CORS SETTINGS
# ============================================
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CORS_ALLOW_HEADERS = ["*"]

PRODUCTION_ORIGINS = [
    "https://encpservices.com",
    "https://www.encpservices.com",
    "https://app.encpservices.com",
]

# ============================================
# EMAIL SETTINGS (Resend)
# ============================================
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
EMAIL_FROM = "ENCP Services <noreply@encpservices.com>"
EMAIL_REPLY_TO = "encpservicesgroup@gmail.com"
APP_URL = os.getenv("APP_URL", "https://app.encpservices.com")

# ============================================
# ADMIN SETTINGS
# ============================================
ADMIN_EMAILS = os.getenv("ADMIN_EMAILS", "admin@encpservices.com").split(",")
ADMIN_PANEL_PATH = os.getenv("ADMIN_PANEL_PATH", "/_internal/ops")

# ============================================
# FERRAMENTAS AUXILIARES (OpenAI)
# ============================================
MODERATION_MODEL = "omni-moderation-latest"
MODERATION_ENABLED = os.getenv("MODERATION_ENABLED", "True").lower() == "true"

# ============================================
# PUSH NOTIFICATIONS (VAPID)
# ============================================
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS_EMAIL = os.getenv("VAPID_CLAIMS_EMAIL", "encpservicesgroup@gmail.com")

# ============================================
# GOOGLE SEARCH CONSOLE
# ============================================
GSC_CREDENTIALS_JSON = os.getenv("GSC_CREDENTIALS_JSON", "")
GSC_SITE_URL = os.getenv("GSC_SITE_URL", "https://encpservices.com")
