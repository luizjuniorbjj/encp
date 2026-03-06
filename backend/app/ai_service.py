"""
ENCP Services Group - AI Service
Chat pipeline with Claude + Memory System
Single-company tile/remodel business assistant
"""

import json
import re
import time
import logging
from typing import Optional, List, Dict
from datetime import datetime

import httpx

from app.config import (
    ANTHROPIC_API_KEY,
    OPENAI_API_KEY,
    AI_PROVIDER,
    AI_MODEL_PRIMARY,
    AI_MODEL_EXTRACTION,
    OPENAI_MODEL_PRIMARY,
    OPENAI_MODEL_EXTRACTION,
    MAX_TOKENS_RESPONSE,
    MAX_CONTEXT_TOKENS
)
from app.prompts.persona import ENCP_PERSONA
from app.prompts.identity import ENCP_IDENTITY
from app.prompts.extraction import MEMORY_EXTRACTION_PROMPT, INSIGHT_EXTRACTION_PROMPT
from app.prompts.templates import USER_CONTEXT_TEMPLATE, build_user_context
from app.prompts.analysis import CLIENT_ANALYSIS_PROMPT, SUMMARY_PROMPT
from app.database import Database
from app.psychology.profile_engine import MessageAnalyzer, PsychologicalContextBuilder
from app.utils.response_filter import filter_response
from app.learning.continuous_learning import (
    LearningEngine,
    ImplicitFeedbackDetector,
    LearningContextBuilder,
    ResponseStrategy,
    FeedbackType
)

logger = logging.getLogger("encp.ai")


class AIService:
    """
    AI service with memory, personalization, and learning.
    Single-company mode — no multi-tenant isolation.
    NO agency_id anywhere.
    """

    def __init__(self, db: Database):
        self.db = db
        self.provider = AI_PROVIDER
        self.learning_engine = LearningEngine(db)
        self.message_analyzer = MessageAnalyzer()
        # Cache last response per user for implicit feedback detection
        self._last_responses: Dict[str, dict] = {}

        if self.provider == "openai":
            import openai
            self.openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
            self.anthropic_client = None
            logger.info("[AI] Using OpenAI provider (GPT-4o-mini)")
        else:
            import anthropic
            self.anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            self.openai_client = None
            logger.info("[AI] Using Anthropic provider (Claude)")

    # ============================================
    # LOW-LEVEL AI CALL WRAPPER
    # ============================================

    def _call_ai(self, system: str, messages: list, model: str = None, max_tokens: int = None) -> tuple:
        """
        Unified AI call — abstracts Anthropic vs OpenAI.
        Returns (response_text, tokens_used, model_used).
        """
        max_tokens = max_tokens or MAX_TOKENS_RESPONSE

        if self.provider == "openai":
            oai_model = model if model and model.startswith("gpt") else OPENAI_MODEL_PRIMARY
            oai_messages = [{"role": "system", "content": system}]
            for msg in messages:
                if isinstance(msg.get("content"), list):
                    # Convert Anthropic image format to OpenAI format
                    oai_content = []
                    for part in msg["content"]:
                        if part.get("type") == "text":
                            oai_content.append({"type": "text", "text": part["text"]})
                        elif part.get("type") == "image":
                            src = part.get("source", {})
                            oai_content.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{src.get('media_type', 'image/jpeg')};base64,{src.get('data', '')}"
                                }
                            })
                    oai_messages.append({"role": msg["role"], "content": oai_content})
                else:
                    oai_messages.append({"role": msg["role"], "content": msg["content"]})

            response = self.openai_client.chat.completions.create(
                model=oai_model,
                messages=oai_messages,
                max_tokens=max_tokens
            )
            text = response.choices[0].message.content
            tokens = (response.usage.prompt_tokens + response.usage.completion_tokens) if response.usage else 0
            return text, tokens, oai_model
        else:
            response = self.anthropic_client.messages.create(
                model=model or AI_MODEL_PRIMARY,
                max_tokens=max_tokens,
                system=system,
                messages=messages
            )
            text = response.content[0].text
            tokens = response.usage.input_tokens + response.usage.output_tokens
            return text, tokens, model or AI_MODEL_PRIMARY

    # ============================================
    # MAIN CHAT METHOD
    # ============================================

    async def chat(
        self,
        user_id: str,
        message: str,
        conversation_id: Optional[str] = None,
        image_data: Optional[str] = None,
        image_media_type: Optional[str] = None,
        images: Optional[List[tuple]] = None,
        channel: Optional[str] = None
    ) -> Dict:
        """
        Process user message with full context pipeline.

        Flow:
        1. Get/create conversation
        2. Fetch context (profile, memories, psych)
        3. Select model
        4. Build system prompt (persona + identity + date)
        5. Build context message (memories + profile)
        6. Prepare API messages (context + history + current)
        7. Call Claude
        8. Apply response filter
        9. Save messages
        10. Return result with _post_process data
        """
        start_time = time.time()

        # 1. Get or create conversation
        # When no conversation_id is provided (e.g., WhatsApp), find the most
        # recent active conversation to maintain context continuity.
        is_new_conversation = False
        conversation = None
        if conversation_id:
            conversation = await self.db.get_conversation(
                conversation_id, user_id=user_id
            )
            if not conversation:
                conversation = await self.db.create_conversation(user_id)
                conversation_id = str(conversation["id"])
                is_new_conversation = True
        else:
            # Look for recent active conversation (within 2 hours)
            recent = await self.db.get_conversations(user_id, limit=1)
            if recent:
                last_conv = recent[0]
                last_msg_at = last_conv.get("last_message_at")
                if last_msg_at:
                    from datetime import datetime, timezone, timedelta
                    now = datetime.now(timezone.utc)
                    if last_msg_at.tzinfo is None:
                        last_msg_at = last_msg_at.replace(tzinfo=timezone.utc)
                    elapsed = (now - last_msg_at).total_seconds()
                    if elapsed < 7200:  # 2 hours
                        conversation = last_conv
                        conversation_id = str(conversation["id"])
                        logger.info(f"[CHAT] Resuming conversation {conversation_id[:8]} (last msg {int(elapsed)}s ago)")
            if not conversation_id:
                conversation = await self.db.create_conversation(user_id, channel=channel)
                conversation_id = str(conversation["id"])
                is_new_conversation = True

        # 2. Fetch context
        profile = await self.db.get_user_profile(user_id)
        user = await self.db.get_user_by_id(user_id)

        # Conversation history
        messages_history = await self.db.get_conversation_messages(
            conversation_id, user_id
        )

        # Permanent memory (scored by relevance to current message)
        permanent_memory = await self.db.get_all_memories_formatted(
            user_id,
            current_message=message,
            top_k=20
        )

        # Property memories (from public records lookup)
        # IMPORTANT: If current message contains an address, do lookup NOW
        # (before AI call) so property data is available for this response.
        address_in_msg = self._extract_address_from_text(message)
        if address_in_msg:
            try:
                await self._property_lookup_if_needed(user_id, message)
            except Exception as e:
                logger.error(f"[PROPERTY] Inline lookup error: {e}")

        all_memories = await self.db.get_user_memories(user_id)
        property_memories = [
            m for m in all_memories
            if m.get("categoria", "").upper() == "PROPERTY"
            and any(kw in (m.get("fato", "") or "").lower() for kw in
                    ["beds", "baths", "sqft", "square feet", "year built", "stories", "lot size", "property type", "property has", "property is", "property was", "property located"])
        ]

        # If address was detected but no property data found, flag it for the AI
        # so it can apologize and ask for basic info instead of ignoring the address
        property_lookup_failed = bool(address_in_msg and not property_memories)

        # Psychological context (from DB — updated every 30 messages)
        psychological_context = await self.db.get_psychological_context(user_id)

        # Recent conversations (for history summary)
        recent_conversations = await self.db.get_conversations(
            user_id, limit=5
        )

        # 2.5 ACTIVE INTELLIGENCE: Analyze current message + detect feedback

        # 2.5a Real-time message analysis (emotional state, style, urgency)
        try:
            msg_analysis = self.message_analyzer.analyze_message(message)
            # Build psych profile dict from DB context + current analysis
            psych_profile = {
                "communication_style": msg_analysis.get("communication_style", "supportive"),
                "processing_style": msg_analysis.get("processing_style", "practical"),
                "recurring_themes": {},
                "openness_level": 0.5,
                "correction_receptivity": 0.5
            }
            # Merge with stored profile if available
            if profile:
                psych_profile["recurring_themes"] = profile.get("recurring_themes", {})
                psych_profile["openness_level"] = profile.get("openness_level", 0.5)
                psych_profile["correction_receptivity"] = profile.get("correction_receptivity", 0.5)

            active_psych = PsychologicalContextBuilder.build_context(
                profile=psych_profile,
                current_analysis=msg_analysis
            )
            # Merge active analysis with stored profile
            if active_psych:
                psychological_context = (
                    f"{psychological_context}\n\n[CURRENT MESSAGE ANALYSIS]\n{active_psych}"
                    if psychological_context else active_psych
                )
        except Exception as e:
            logger.warning(f"[PSYCH] Message analysis error: {e}")
            msg_analysis = {}

        # 2.5b Implicit feedback detection (from previous message exchange)
        recent_feedbacks = []
        optimal_strategy = ResponseStrategy.EMPATHY_FIRST  # default
        try:
            if user_id in self._last_responses:
                last = self._last_responses[user_id]
                time_to_respond = time.time() - last.get("timestamp", time.time())
                feedbacks = ImplicitFeedbackDetector.detect_feedback(
                    last.get("user_message", ""),
                    last.get("ai_response", ""),
                    message,
                    time_to_respond
                )
                recent_feedbacks = feedbacks

                # Save feedbacks and adjust profile
                for fb in feedbacks:
                    await self.learning_engine.process_user_response(
                        user_id=user_id,
                        original_ai_response=last.get("ai_response", ""),
                        user_response=message,
                        time_to_respond=time_to_respond,
                        original_user_message=last.get("user_message", "")
                    )
                if feedbacks:
                    await self.learning_engine.adjust_profile(user_id, feedbacks)
        except Exception as e:
            logger.warning(f"[LEARNING] Feedback detection error: {e}")

        # 2.5c Select optimal strategy for this user
        try:
            current_context = {
                "emotional_state": msg_analysis.get("emotional_state", "neutral"),
                "communication_style": msg_analysis.get("communication_style", "supportive"),
                "urgency": msg_analysis.get("urgency", 0.3)
            }
            optimal_strategy = await self.learning_engine.get_optimal_strategy(
                user_id, current_context
            )
        except Exception as e:
            logger.warning(f"[LEARNING] Strategy selection error: {e}")

        # 2.5d Build learning context for the prompt
        learning_context = ""
        try:
            patterns = await self.learning_engine.detect_patterns(user_id)
            learning_context = LearningContextBuilder.build_learning_context(
                optimal_strategy=optimal_strategy,
                patterns=patterns,
                recent_feedbacks=recent_feedbacks
            )
        except Exception as e:
            logger.warning(f"[LEARNING] Context build error: {e}")

        # 3. Detect language (with persistence) and select model
        stored_lang = profile.get("language") if profile else None
        detected_lang = self._detect_language(message)
        # Use stored language if current message is short/ambiguous.
        # Short messages like "ok", "yes", "interior", "3" should NOT
        # switch away from the client's established language.
        if stored_lang and detected_lang != stored_lang:
            msg_lower = message.lower().strip()
            word_count = len(message.split())
            # Universal words that exist in ALL languages — never trigger a switch
            universal_words = {
                "ok", "okay", "yes", "no", "si", "sim", "not",
                "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
                "interior", "exterior", "color",
            }
            msg_words = set(msg_lower.split())
            if msg_words and msg_words <= universal_words:
                # All words are universal — keep stored language
                detected_lang = stored_lang
            elif word_count <= 3:
                # Short message — only switch if there's a STRONG signal
                strong_signals = {
                    "en": ["hello", "hi", "hey", "good morning", "good afternoon",
                           "thank", "please", "bedroom", "bathroom", "ceiling",
                           "house", "tile", "remodel", "estimate"],
                    "pt": ["oi", "ola", "obrigado", "quarto", "banheiro", "teto",
                           "voce", "preciso", "quero", "azulejo", "piso"],
                    "es": ["hola", "gracias", "cuarto", "bano", "techo",
                           "necesito", "quiero", "usted", "azulejo", "piso"],
                }
                has_strong = any(w in msg_lower for w in strong_signals.get(detected_lang, []))
                if not has_strong:
                    detected_lang = stored_lang
        language = detected_lang
        # Persist language if changed (UPSERT — guest users may not have profile row)
        if language != stored_lang:
            try:
                await self.db.execute(
                    """INSERT INTO user_profiles (user_id, language)
                    VALUES ($2, $1)
                    ON CONFLICT (user_id) DO UPDATE SET language = $1""",
                    language, user_id
                )
            except Exception:
                pass  # Non-critical
        model = self._select_model()

        # 4. Build system prompt (ENCP_PERSONA + ENCP_IDENTITY + context)
        is_first = len(recent_conversations) <= 1 and len(messages_history) == 0
        system_prompt = self._build_system_prompt(
            is_first_conversation=is_first,
            language=language
        )

        # 5. Build context message (now with learning context)
        history_summary = "; ".join([
            c.get("resumo", "")
            for c in recent_conversations[:3]
            if c.get("resumo") and str(c["id"]) != str(conversation_id)
        ]) or ""

        context_message = self._build_context_message(
            profile=profile,
            permanent_memory=permanent_memory,
            psychological_context=psychological_context,
            history_summary=history_summary,
            learning_context=learning_context,
            property_memories=property_memories,
            property_lookup_failed=property_lookup_failed
        )

        # 5b. Detect response delay (for natural apology)
        try:
            if messages_history:
                last_msg = messages_history[-1]
                if last_msg.get("role") == "user" and last_msg.get("created_at"):
                    from datetime import datetime as _dt, timezone as _tz
                    now_utc = _dt.now(_tz.utc)
                    msg_time = last_msg["created_at"]
                    if msg_time.tzinfo is None:
                        msg_time = msg_time.replace(tzinfo=_tz.utc)
                    gap_seconds = (now_utc - msg_time).total_seconds()
                    if gap_seconds > 300:  # 5+ minutes since client's last message
                        delay_flag = (
                            "\n\n[DELAYED_RESPONSE] The client sent their last message "
                            f"{int(gap_seconds // 60)} minutes ago and is still waiting. "
                            "Apologize briefly for the wait and continue naturally."
                        )
                        system_prompt += delay_flag
        except Exception as e:
            logger.debug(f"[CHAT] Delay detection error: {e}")

        # 6. Prepare API messages
        api_messages = []

        # Context as first exchange (keeps system prompt cacheable)
        if context_message:
            api_messages.append({
                "role": "user",
                "content": f"[CLIENT CONTEXT]\n{context_message}"
            })
            api_messages.append({
                "role": "assistant",
                "content": "Understood, I'll use this information naturally in our conversation."
            })

        # Conversation history (last 20 messages)
        for msg in messages_history[-20:]:
            api_messages.append({"role": msg["role"], "content": msg["content"]})

        # Current message (with optional images)
        has_images = image_data or images
        if has_images:
            user_content = []
            if images:
                for img_data, img_type in images:
                    user_content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img_type,
                            "data": img_data
                        }
                    })
            elif image_data and image_media_type:
                user_content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image_media_type,
                        "data": image_data
                    }
                })
            user_content.append({
                "type": "text",
                "text": message if message else "What do you see in this image?"
            })
            api_messages.append({"role": "user", "content": user_content})
        else:
            api_messages.append({"role": "user", "content": message})

        # 7. Call AI (Anthropic or OpenAI)
        max_tokens = MAX_TOKENS_RESPONSE * 2 if has_images else MAX_TOKENS_RESPONSE
        reply, tokens_used, model_used = self._call_ai(
            system=system_prompt,
            messages=api_messages,
            model=model,
            max_tokens=max_tokens
        )

        # 8. Apply response filter before returning
        reply, filter_warnings = filter_response(reply)
        if filter_warnings:
            logger.warning(f"[FILTER] Warnings for user {user_id[:8]}: {filter_warnings}")

        # 9. Save messages
        if images:
            saved_content = f"[PDF/Images: {len(images)} pages]\n{message}"
        elif image_data:
            saved_content = f"[Image attached]\n{message}"
        else:
            saved_content = message

        await self.db.save_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role="user",
            content=saved_content
        )
        await self.db.save_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role="assistant",
            content=reply,
            tokens_used=tokens_used,
            model_used=model_used
        )
        await self.db.increment_message_count(user_id)

        # 10. Cache response for next-message feedback detection
        self._last_responses[user_id] = {
            "user_message": message,
            "ai_response": reply,
            "timestamp": time.time(),
            "strategy": optimal_strategy.value if hasattr(optimal_strategy, 'value') else str(optimal_strategy)
        }

        # 11. Build result
        message_count = len(messages_history) + 2
        total_messages = user.get("total_messages", 0) if user else 0
        elapsed_ms = int((time.time() - start_time) * 1000)

        result = {
            "response": reply,
            "conversation_id": str(conversation_id),
            "model_used": model_used,
            "tokens_used": tokens_used,
            "_post_process": {
                "user_id": user_id,
                "message": message,
                "reply": reply,
                "conversation_id": str(conversation_id),
                "message_count": message_count,
                "total_messages": total_messages,
                "elapsed_ms": elapsed_ms,
                "strategy_used": optimal_strategy.value if hasattr(optimal_strategy, 'value') else str(optimal_strategy),
                "emotional_state": msg_analysis.get("emotional_state", ("neutral", 0.5))
            }
        }

        return result

    # ============================================
    # POST-PROCESS (background)
    # ============================================

    async def post_process_chat(self, post_data: dict):
        """
        Background processing after response is returned to user.
        Runs: memory extraction, summary, insights, psych profile, auto-lead.
        """
        try:
            user_id = post_data["user_id"]
            message = post_data["message"]
            conversation_id = post_data["conversation_id"]
            message_count = post_data["message_count"]
            total_messages = post_data["total_messages"]
            elapsed_ms = post_data["elapsed_ms"]

            uid_short = user_id[:8] if user_id else "?"
            logger.info(f"[BG] Post-process for user {uid_short}...")

            # 1. Extract memories (every message)
            ai_reply = post_data.get("reply", "")
            try:
                await self._extract_memories(user_id, message, conversation_id, ai_reply=ai_reply)
            except Exception as e:
                logger.error(f"[BG] Memory extraction error: {e}")

            # 2. Update summary (every 5 messages)
            if message_count % 5 == 0:
                try:
                    await self._update_conversation_summary(
                        conversation_id, user_id
                    )
                except Exception as e:
                    logger.error(f"[BG] Summary error: {e}")

            # 3. Extract insights (every 20 messages)
            if message_count % 20 == 0:
                try:
                    await self._extract_insights(conversation_id, user_id)
                except Exception as e:
                    logger.error(f"[BG] Insight error: {e}")

            # 4. Analyze psychological profile (every 30 messages)
            if total_messages > 0 and total_messages % 30 == 0:
                try:
                    await self._analyze_psychological_profile(user_id)
                except Exception as e:
                    logger.error(f"[BG] Psych profile error: {e}")

            # 5. Record learning interaction with actual strategy used
            try:
                strategy_str = post_data.get("strategy_used", "empathy_first")
                try:
                    strategy_enum = ResponseStrategy(strategy_str)
                except (ValueError, KeyError):
                    strategy_enum = ResponseStrategy.EMPATHY_FIRST
                emotion_state = post_data.get("emotional_state", ("neutral", 0.5))
                emotion_str = emotion_state[0] if isinstance(emotion_state, tuple) else str(emotion_state)
                await self.learning_engine.record_interaction(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    user_message=message,
                    ai_response=post_data.get("reply", ""),
                    strategy_used=strategy_enum,
                    emotion_before=emotion_str,
                    emotion_after="neutral",
                    response_time=elapsed_ms
                )
            except Exception as e:
                logger.error(f"[BG] Learning record error: {e}")

            # 6. Property lookup (when address detected in conversation)
            # NOTE: If address was in the message, lookup already ran inline
            # before the AI call. This catches addresses from stored memories.
            try:
                await self._property_lookup_if_needed(user_id, message)
            except Exception as e:
                logger.error(f"[BG] Property lookup error: {e}")

            # 7. Auto-create lead if enough info collected
            try:
                await self._auto_create_lead(user_id, conversation_id)
            except Exception as e:
                logger.error(f"[BG] Auto-lead creation error: {e}")

            logger.info(f"[BG] Post-process done for user {uid_short}")

        except Exception as e:
            logger.error(f"[BG] Post-process general error: {e}")

    # ============================================
    # AUTO-LEAD CREATION
    # ============================================

    async def _auto_create_lead(self, user_id: str, conversation_id: str):
        """
        Auto-create a lead when the bot has collected enough info:
        name + phone + service_type.
        """
        memories = await self.db.get_user_memories(user_id)

        name = None
        phone = None
        service_type = None
        email = None
        city = None
        property_type = None
        timeline = None

        for mem in memories:
            cat = mem.get("categoria", "").upper()
            fato = mem.get("fato", "").lower()
            fato_raw = mem.get("fato", "")

            if cat == "IDENTITY":
                if any(kw in fato for kw in ["name is", "name:", "called", "nome"]):
                    name = fato_raw
                elif any(kw in fato for kw in ["phone", "number", "cell", "telefone"]):
                    phone = fato_raw
                elif any(kw in fato for kw in ["email", "e-mail"]):
                    email = fato_raw

            elif cat == "PROJECT":
                if any(kw in fato for kw in ["tile", "floor", "remodel", "bathroom", "kitchen", "backsplash", "laminate"]):
                    service_type = fato_raw

            elif cat == "PROPERTY":
                if any(kw in fato for kw in ["lives in", "located in", "city"]):
                    city = fato_raw
                if any(kw in fato for kw in ["house", "condo", "commercial", "residential", "townhouse"]):
                    property_type = fato_raw

            elif cat == "SCHEDULE":
                if any(kw in fato for kw in ["timeline", "asap", "week", "month", "flexible"]):
                    timeline = fato_raw

        # Only create lead if we have the minimum: name + phone + service_type
        if not (name and phone and service_type):
            return

        # Check if lead already exists for this user
        profile = await self.db.get_user_profile(user_id)
        user_phone = profile.get("phone") if profile else None

        # Check existing leads by user_id
        existing_leads = await self.db.get_leads(limit=5)
        for lead in existing_leads:
            if lead.get("user_id") and str(lead["user_id"]) == str(user_id):
                return  # Lead already exists

        # Create the lead
        await self.db.create_lead(
            name=name,
            phone=phone,
            email=email,
            city=city,
            property_type=property_type or "residential",
            service_type=service_type,
            timeline=timeline or "flexible",
            source="chat",
            user_id=user_id,
            conversation_id=conversation_id
        )
        logger.info(f"[LEAD] Auto-created lead for user {user_id[:8]}: {name}")

    # ============================================
    # PROPERTY LOOKUP (background)
    # ============================================

    # Regex patterns to detect US addresses in messages
    _ADDRESS_PATTERN = re.compile(
        r'\b\d{1,5}\s+[\w\s]{2,40}\b'        # street number + name
        r'(?:\s*,\s*[\w\s]+)?'                 # optional city
        r'(?:\s*,?\s*[A-Z]{2})?'               # optional state
        r'(?:\s*,?\s*\d{5}(?:-\d{4})?)?\b',    # optional zip
        re.IGNORECASE
    )

    _ZIP_PATTERN = re.compile(r'\b\d{5}(?:-\d{4})?\b')

    async def _property_lookup_if_needed(self, user_id: str, message: str):
        """
        If the user's message or memories contain an address, look up property data
        from public records (HomeHarvest/Realtor.com) and save as PROPERTY memories.
        """
        # Check if we already have property data for this user
        memories = await self.db.get_user_memories(user_id)
        has_property_data = False
        stored_address = None

        for mem in memories:
            cat = mem.get("categoria", "").upper()
            fato = (mem.get("fato", "") or "").lower()
            if cat == "PROPERTY":
                if any(kw in fato for kw in ["beds", "baths", "sqft", "square feet", "year built"]):
                    has_property_data = True
                    break
                if any(kw in fato for kw in ["address", "lives at", "located at", "property at"]):
                    stored_address = mem.get("fato", "")

        if has_property_data:
            return  # Already have property data

        # Try to find address in the current message
        address = self._extract_address_from_text(message)

        # If no address in message, try from stored memories
        if not address and stored_address:
            address = stored_address

        if not address:
            return  # No address found

        # Validate: must have at least a street number + name pattern
        if not re.search(r'\d{1,5}\s+\w', address):
            return

        logger.info(f"[PROPERTY] Attempting lookup for user {user_id[:8]}")

        from app.utils.property_lookup import lookup_property, format_property_for_context

        data = await lookup_property(address)
        if not data:
            return

        # Save property data as individual PROPERTY memories
        property_facts = []

        if data.get("property_type") and data["property_type"] != "INDISPONIVEL":
            property_facts.append(f"Property type: {data['property_type']}")

        if data.get("beds"):
            baths_str = str(data.get("baths") or "unknown")
            if data.get("half_baths"):
                baths_str += ".5"
            property_facts.append(f"Property has {data['beds']} bedrooms and {baths_str} bathrooms")

        if data.get("sqft"):
            property_facts.append(f"Property is {data['sqft']:,} square feet")

        if data.get("year_built"):
            property_facts.append(f"Property was built in {data['year_built']}")

        if data.get("stories"):
            property_facts.append(f"Property has {data['stories']} stories")

        if data.get("lot_sqft"):
            property_facts.append(f"Lot size is {data['lot_sqft']:,} square feet")

        if data.get("city") and data.get("state"):
            property_facts.append(f"Property located in {data['city']}, {data['state']}")

        if not property_facts:
            return

        # Save each fact as a PROPERTY memory
        for fact in property_facts:
            await self.db.save_memory(
                user_id=user_id,
                categoria="PROPERTY",
                fato=fact,
                detalhes="Auto-detected from public records (Realtor.com)",
                importancia=8,
                confianca=0.85,
                semantic_field=fact.split(":")[0].strip().lower().replace(" ", "_") if ":" in fact else None
            )

        logger.info(f"[PROPERTY] Saved {len(property_facts)} property facts for user {user_id[:8]}")

    def _extract_address_from_text(self, text: str) -> Optional[str]:
        """Extract a US address from text. Returns the best candidate or None."""
        if not text:
            return None

        # Look for patterns like "123 Main Street, City, FL 33067"
        # Full address with ZIP
        full_pattern = re.compile(
            r'\b(\d{1,5}\s+[\w\s\.]{2,30}'       # street number + name
            r'(?:\s*,\s*[\w\s]+)'                  # city (required)
            r'(?:\s*,?\s*[A-Z]{2})'                # state (required)
            r'(?:\s*,?\s*\d{5}(?:-\d{4})?)?)\b',   # zip (optional)
            re.IGNORECASE
        )
        match = full_pattern.search(text)
        if match:
            return match.group(1).strip()

        # Simpler: street + city + state
        simple_pattern = re.compile(
            r'\b(\d{1,5}\s+[\w\s\.]{2,30}'
            r'\s*,\s*[\w\s]+'
            r'\s*,?\s*[A-Z]{2})\b',
            re.IGNORECASE
        )
        match = simple_pattern.search(text)
        if match:
            return match.group(1).strip()

        # Just street + ZIP
        zip_pattern = re.compile(
            r'\b(\d{1,5}\s+[\w\s\.]{2,30}\s+\d{5})\b'
        )
        match = zip_pattern.search(text)
        if match:
            return match.group(1).strip()

        return None

    # ============================================
    # MEMORY EXTRACTION (background)
    # ============================================

    # Tile/remodel-domain trigger keywords for memory extraction gating
    TRIGGER_KEYWORDS = [
        "tile", "tiling", "floor", "flooring", "remodel", "remodeling",
        "bathroom", "kitchen", "backsplash", "laminate", "hardwood", "porcelain",
        "ceramic", "marble", "granite", "grout", "grouting", "mortar",
        "estimate", "quote", "price", "cost", "budget", "square", "sqft",
        "schedule", "appointment", "available", "when", "start", "finish",
        "married", "divorced", "single", "spouse", "husband", "wife",
        "moved", "address", "zip", "florida", "texas", "california",
        "work", "job", "retired", "occupation", "employer",
        "name", "called", "live", "bought", "sold", "switched",
        "repair", "damage", "water", "mold", "crack", "chip", "subfloor",
        "demolition", "layout", "pattern", "waterproof", "underlayment",
        # Identity/personal data triggers
        "birthday", "born", "birth", "age", "old", "years",
        "son", "daughter", "child", "kids", "family",
        "my name", "i am", "i'm", "we are", "esposa", "marido",
        "nascimento", "nasceu", "anos", "idade", "filho", "filha",
    ]

    async def extract_memories(self, user_id: str, conversation_text: str) -> list:
        """
        Public method: Use Claude EXTRACTION model to extract memories from conversation.
        Model: AI_MODEL_EXTRACTION (Sonnet) — NEVER Haiku for extraction.
        Returns list of extracted memory dicts.
        """
        # Fetch current memories for conflict detection
        current_memories = await self.db.get_user_memories(user_id)
        memories_context = ""
        if current_memories:
            memories_context = "\n\nCLIENT'S CURRENT MEMORIES:\n"
            for mem in current_memories:
                memories_context += f"- [{mem['categoria']}] {mem['fato']}"
                if mem.get("id"):
                    memories_context += f" (id: {mem['id']})"
                memories_context += "\n"

        extraction_model = OPENAI_MODEL_EXTRACTION if self.provider == "openai" else AI_MODEL_EXTRACTION
        result_text, _, _ = self._call_ai(
            system="You are a memory extraction engine. Return JSON only.",
            messages=[{
                "role": "user",
                "content": MEMORY_EXTRACTION_PROMPT.format(
                    existing_memories=memories_context or "No existing memories.",
                    conversation=conversation_text
                )
            }],
            model=extraction_model,
            max_tokens=500
        )

        result = self._parse_json_response(result_text)
        if not result:
            return []

        return result.get("memories", [])

    async def _extract_memories(
        self,
        user_id: str,
        user_message: str,
        conversation_id: str,
        ai_reply: str = ""
    ):
        """
        Extract important facts from user message for permanent memory.
        Runs on every message. Uses Sonnet for extraction (never Haiku).
        """
        message_lower = user_message.lower()
        has_trigger = any(kw in message_lower for kw in self.TRIGGER_KEYWORDS)

        # Also check AI reply for triggers (AI asked about name/DOB -> user answered)
        if not has_trigger and ai_reply:
            reply_lower = ai_reply.lower()
            has_trigger = any(kw in reply_lower for kw in self.TRIGGER_KEYWORDS)

        # Skip very short messages without triggers
        if len(user_message) < 5 and not has_trigger:
            return

        # Build conversation context with AI's question for better extraction
        conversation_text = ""
        if ai_reply:
            conversation_text += f"Assistant (previous message): {ai_reply[:500]}\n"
        conversation_text += f"Client: {user_message}"

        # Extract memories via public method
        memories = await self.extract_memories(user_id, conversation_text)

        if memories:
            logger.info(f"Extracted {len(memories)} memories: {[m.get('category', '?') for m in memories]}")

        for mem in memories:
            fact = mem.get("fact") or mem.get("fato")
            if not fact:
                continue

            # Skip if marked as sensitive
            if mem.get("sensitive", False):
                continue

            category = (mem.get("category") or mem.get("categoria", "EVENT")).upper()
            action = mem.get("action", "new")
            semantic_field = mem.get("semantic_field")
            importance = mem.get("importance", mem.get("importancia", 5))
            confidence = mem.get("confidence", mem.get("confianca", 0.8))
            details = mem.get("details") or mem.get("detalhes")

            # Normalize fact for duplicate detection
            fato_normalizado = re.sub(r'\s+', ' ', fact.strip().lower())

            # Check for duplicates
            duplicate = await self.db.find_duplicate_memory(
                user_id, category, fato_normalizado
            )
            if duplicate:
                # Already exists — just increment mention count
                await self.db.increment_memory_mention(str(duplicate["id"]))
                continue

            # Check for semantic conflict (e.g., name changed)
            if semantic_field and action == "supersede":
                conflict = await self.db.find_semantic_conflict(
                    user_id, category, semantic_field
                )
                if conflict:
                    # Save new memory first
                    new_mem = await self.db.save_memory(
                        user_id=user_id,
                        categoria=category,
                        fato=fact,
                        detalhes=details,
                        importancia=importance,
                        confianca=confidence,
                        origem_conversa_id=conversation_id,
                        semantic_field=semantic_field
                    )
                    # Then supersede the old one
                    await self.db.supersede_memory(
                        str(conflict["id"]), str(new_mem["id"])
                    )
                    logger.info(f"[MEM] Superseded memory {str(conflict['id'])[:8]} with {str(new_mem['id'])[:8]}")
                    continue

            # Save new memory
            await self.db.save_memory(
                user_id=user_id,
                categoria=category,
                fato=fact,
                detalhes=details,
                importancia=importance,
                confianca=confidence,
                origem_conversa_id=conversation_id,
                semantic_field=semantic_field
            )

            # Enforce category caps for scored categories
            await self.db.enforce_category_cap(user_id, category)

    # ============================================
    # CONVERSATION SUMMARY (background)
    # ============================================

    async def _update_conversation_summary(
        self, conversation_id: str, user_id: str
    ):
        """Generate conversation summary using AI"""
        messages = await self.db.get_conversation_messages(
            conversation_id, user_id, limit=100
        )

        if len(messages) < 5:
            return

        conversation_text = "\n".join([
            f"{'Client' if m['role'] == 'user' else 'ENCPServices'}: {m['content']}"
            for m in messages
        ])

        resumo, _, _ = self._call_ai(
            system="Summarize conversations concisely.",
            messages=[{"role": "user", "content": SUMMARY_PROMPT.format(
                conversation=conversation_text
            )}],
            max_tokens=500
        )

        await self.db.update_conversation_summary(
            conversation_id=conversation_id,
            resumo=resumo
        )

    # ============================================
    # INSIGHT EXTRACTION (background)
    # ============================================

    async def _extract_insights(
        self, conversation_id: str, user_id: str
    ):
        """Extract insights about the client from conversation"""
        messages = await self.db.get_conversation_messages(
            conversation_id, user_id, limit=100
        )

        if len(messages) < 10:
            return

        conversation_text = "\n".join([
            f"{'Client' if m['role'] == 'user' else 'ENCPServices'}: {m['content']}"
            for m in messages
        ])

        result_text, _, _ = self._call_ai(
            system="Extract client insights. Return JSON only.",
            messages=[{"role": "user", "content": INSIGHT_EXTRACTION_PROMPT.format(
                conversation=conversation_text
            )}],
            max_tokens=500
        )

        result = self._parse_json_response(result_text)
        if not result:
            return

        for insight in result.get("insights", []):
            await self.db.save_insight(
                user_id=user_id,
                categoria=insight.get("category", "NEED"),
                insight=insight.get("description", ""),
                confianca=insight.get("confidence", 0.7),
                conversa_id=conversation_id
            )

    # ============================================
    # PSYCHOLOGICAL PROFILE (background)
    # ============================================

    async def _analyze_psychological_profile(self, user_id: str):
        """Analyze client communication profile from recent conversations"""
        conversations = await self.db.get_conversations(user_id, limit=5)

        if not conversations:
            return

        all_messages = []
        for conv in conversations:
            msgs = await self.db.get_conversation_messages(
                str(conv["id"]), user_id, limit=30
            )
            for msg in msgs:
                if msg["role"] == "user":
                    all_messages.append(msg["content"])

        if len(all_messages) < 20:
            return

        conversations_text = "\n".join([
            f"- {msg[:500]}" for msg in all_messages[-50:]
        ])

        extraction_model = OPENAI_MODEL_EXTRACTION if self.provider == "openai" else AI_MODEL_EXTRACTION
        result_text, _, _ = self._call_ai(
            system="Analyze client communication patterns. Return JSON only.",
            messages=[{"role": "user", "content": CLIENT_ANALYSIS_PROMPT.format(
                conversation_history=conversations_text
            )}],
            model=extraction_model,
            max_tokens=1000
        )

        result = self._parse_json_response(result_text)
        if result:
            await self.db.save_psychological_profile(user_id, result)
            logger.info(f"[PSYCH] Profile updated for user {user_id[:8]}...")

    # ============================================
    # LANGUAGE DETECTION
    # ============================================

    def _detect_language(self, message: str) -> str:
        """
        Detect message language. Returns 'en', 'pt', or 'es'.
        Default: English (US tile/remodel business).

        Priority:
        1. Explicit language requests ("em portugues", "in English", "en espanol")
        2. Portuguese-specific characters
        3. Keyword scoring
        4. Default: English
        """
        message_lower = message.lower()

        # --- Priority 1: Explicit language requests (override everything) ---
        pt_explicit = [
            "em portugues", "em portugues", "falar portugues", "falar portugues",
            "fala portugues", "fala portugues", "pode falar portugues",
            "in portuguese", "speak portuguese", "portuguese please",
        ]
        es_explicit = [
            "en espanol", "en espanol", "hablar espanol", "hablar espanol",
            "habla espanol", "habla espanol",
            "in spanish", "speak spanish", "spanish please",
        ]
        en_explicit = [
            "in english", "speak english", "english please",
            "em ingles", "em ingles", "en ingles", "en ingles",
        ]
        for phrase in pt_explicit:
            if phrase in message_lower:
                return "pt"
        for phrase in es_explicit:
            if phrase in message_lower:
                return "es"
        for phrase in en_explicit:
            if phrase in message_lower:
                return "en"

        # --- Priority 2: Character-based detection ---
        pt_chars = sum(1 for c in message if c in '\u00e3\u00f5\u00e7\u00ea\u00e2\u00f4\u00c3\u00d5\u00c7\u00ca\u00c2\u00d4')
        es_chars = sum(1 for c in message if c in '\u00f1\u00bf\u00a1\u00d1')

        # --- Priority 3: Keyword scoring ---
        # NOTE: Words that exist in multiple languages (interior, exterior, color)
        # are included in ALL relevant language lists to avoid false EN detection.
        # Use word boundary matching (\b) for short words to avoid false positives
        # e.g., "ola" matching inside "hola", "no" matching inside "anotar"
        pt_indicators = [
            "voce", " oi ", " oi,", "bom dia", "boa tarde", "boa noite",
            "obrigado", "obrigada", "tudo bem", "tudo certo",
            "meu ", "minha ", "dele ", "dela ", "nosso", "nossa",
            "pode ", "posso", "quero", "preciso", "tenho", "estou",
            "falar", "fazer", "saber", "quanto", "quando", "onde",
            "por favor", "com licenca", "desculpa", "entendi",
            "azulejo", "piso", "revestimento", "rejunte", "quarto",
            "banheiro", "cozinha", "reforma",
            " eu ", " ele ", " ela ", " do ", " da ", " no ", " na ",
            " um ", " uma ", " os ", " as ", " em ",
            "qual", "quais", "porque", "pra ",
        ]
        es_indicators = [
            "hola", "buenos", "buenas", "gracias", "claro", "verdad",
            "quiero", "necesito", "puedo", "tengo", "estoy", "esta",
            "tambien", "tambien", "pero", "ahora", "muy", "aqui", "aqui",
            "usted", "ustedes", "nosotros", "ellos", "ellas",
            "donde", "donde", "cuanto", "cuanto", "como", "como",
            "azulejo", "piso", "baldosa", "lechada", "habitacion",
            "bano", "cocina", "remodelacion",
            "cuartos", "banos", "cocina", "sala", "techo", "paredes",
        ]
        en_indicators = [
            "hello", "hey", "good morning", "good afternoon",
            "thank", "thanks", "please", "okay",
            "my", "your", "the", "this", "that", "what", "when", "how",
            "tile", "floor", "remodel", "house", "room", "estimate",
            "bathroom", "kitchen", "backsplash", "laminate",
            "want", "need", "have", "looking",
            "bedroom", "bathroom", "kitchen", "ceiling", "baseboard",
        ]
        # Remove ambiguous words from EN that exist identically in PT/ES
        # "interior", "exterior", "color" are the same in all 3 languages
        # They should NOT bias toward English

        pt_count = sum(1 for w in pt_indicators if w in message_lower) + (pt_chars * 3)
        es_count = sum(1 for w in es_indicators if w in message_lower) + (es_chars * 3)
        en_count = sum(1 for w in en_indicators if w in message_lower)

        # If all scores are 0 or all equal, default to EN (will be overridden by stored_lang)
        if pt_count == 0 and es_count == 0 and en_count == 0:
            return "en"

        # Clear winner
        if pt_count > es_count and pt_count > en_count:
            return "pt"
        if es_count > pt_count and es_count > en_count:
            return "es"
        if en_count > pt_count and en_count > es_count:
            return "en"

        # Tie-breaking: PT vs ES (both > EN) — use character hints or default to ES
        # (South Florida has more Spanish speakers than Portuguese)
        if pt_count == es_count and pt_count > en_count:
            if pt_chars > es_chars:
                return "pt"
            return "es"  # Default tie-break: Spanish (larger FL population)

        # PT vs EN tie or ES vs EN tie
        if pt_count == en_count and pt_count > es_count:
            return "pt" if pt_chars > 0 else "en"
        if es_count == en_count and es_count > pt_count:
            return "es" if es_chars > 0 else "en"

        return "en"

    # ============================================
    # MODEL SELECTION
    # ============================================

    def _select_model(self) -> str:
        """
        Select model based on provider:
        - OpenAI: always gpt-4o-mini
        - Anthropic: always Sonnet (primary)
        """
        if self.provider == "openai":
            return OPENAI_MODEL_PRIMARY

        # Always use Sonnet for chat
        return AI_MODEL_PRIMARY

    # ============================================
    # SYSTEM PROMPT
    # ============================================

    def _build_system_prompt(
        self,
        is_first_conversation: bool = False,
        language: str = "en"
    ) -> str:
        """
        Build system prompt: date + ENCP_PERSONA + ENCP_IDENTITY.
        Memories/context go in separate messages for better caching.
        """
        now = datetime.now()

        # Date context by language
        if language == "pt":
            meses = {1: "janeiro", 2: "fevereiro", 3: "marco", 4: "abril",
                     5: "maio", 6: "junho", 7: "julho", 8: "agosto",
                     9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"}
            date_context = f"DATA DE HOJE: {now.day} de {meses[now.month]} de {now.year}\n\n"
        elif language == "es":
            meses = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
                     5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
                     9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}
            date_context = f"FECHA DE HOY: {now.day} de {meses[now.month]} de {now.year}\n\n"
        else:
            months = ["January", "February", "March", "April", "May", "June",
                      "July", "August", "September", "October", "November", "December"]
            date_context = f"TODAY'S DATE: {months[now.month - 1]} {now.day}, {now.year}\n\n"

        # Build: date + persona + identity
        prompt = date_context + ENCP_PERSONA + "\n\n" + ENCP_IDENTITY

        # Language instruction
        lang_instructions = {
            "en": "\nRESPOND IN ENGLISH. The client wrote in English.\n",
            "pt": "\nRESPONDA EM PORTUGUES. O cliente escreveu em portugues.\n",
            "es": "\nRESPONDE EN ESPANOL. El cliente escribio en espanol.\n"
        }
        prompt += lang_instructions.get(language, "")

        if is_first_conversation:
            prompt += "\n\nFIRST INTERACTION: Greet naturally. If new client, start collecting basic info conversationally."

        return prompt

    # ============================================
    # CONTEXT MESSAGE
    # ============================================

    def _build_context_message(
        self,
        profile: dict = None,
        permanent_memory: str = "",
        psychological_context: str = "",
        history_summary: str = "",
        learning_context: str = "",
        property_memories: list = None,
        property_lookup_failed: bool = False
    ) -> str:
        """
        Build context message (separate from system prompt for caching).
        Includes: memories + profile + psych + learning.
        """
        parts = []

        # If client provided address but lookup returned no data
        if property_lookup_failed:
            parts.append(
                "[PROPERTY LOOKUP FAILED] The client provided an address but we couldn't "
                "retrieve property details from public records. Acknowledge that you received "
                "the address, apologize briefly that you couldn't pull up the property details "
                "automatically, and ask the basic fallback questions (rooms, sqft, stories) "
                "to give them a ballpark estimate. Do NOT ignore the address."
            )

        # Permanent memory (most important — scored by relevance)
        if permanent_memory:
            parts.append(permanent_memory)

        # Profile context
        if profile:
            user_context = build_user_context(
                profile=profile,
                history_summary=history_summary,
                psychological_context=psychological_context,
                learning_context=learning_context,
                property_memories=property_memories
            )
            parts.append(user_context)

        # Psychological context (fallback if no profile)
        if psychological_context and not profile:
            parts.append(psychological_context)

        # Learning context (fallback if no profile)
        if learning_context and not profile:
            parts.append(learning_context)

        return "\n\n".join(parts) if parts else ""

    # ============================================
    # JSON PARSING UTILITY
    # ============================================

    @staticmethod
    def _parse_json_response(text: str) -> Optional[dict]:
        """Parse JSON from AI response with fallback strategies"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Strategy 1: Find JSON block in text
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    # Strategy 2: Clean trailing commas
                    cleaned = re.sub(r',\s*([}\]])', r'\1', json_match.group())
                    try:
                        return json.loads(cleaned)
                    except json.JSONDecodeError:
                        pass
            return None
