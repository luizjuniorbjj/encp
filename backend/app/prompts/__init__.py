"""
ENCP Services Group - Prompts
Sistema de prompts para assistente de tile/remodel
"""

from app.prompts.persona import ENCP_PERSONA
from app.prompts.extraction import MEMORY_EXTRACTION_PROMPT, INSIGHT_EXTRACTION_PROMPT
from app.prompts.templates import USER_CONTEXT_TEMPLATE, ONBOARDING_PROMPT, build_user_context
from app.prompts.analysis import SUMMARY_PROMPT, CLIENT_ANALYSIS_PROMPT
from app.prompts.identity import ENCP_IDENTITY
