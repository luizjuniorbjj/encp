"""
ENCPServices - Continuous Learning System
Engine that improves AI responses with each interaction
Forked from AiSyster — adapted from spiritual to tile/remodel domain
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum

logger = logging.getLogger("encp.learning")


# ============================================
# FEEDBACK TYPES
# ============================================

class FeedbackType(Enum):
    """Types of implicit and explicit feedback"""
    POSITIVE_EXPLICIT = "positive_explicit"      # User said they liked it
    NEGATIVE_EXPLICIT = "negative_explicit"      # User said they didn't like it
    ENGAGEMENT_HIGH = "engagement_high"          # Long response, continued conversation
    ENGAGEMENT_LOW = "engagement_low"            # Short response, abandoned
    EMOTIONAL_IMPROVEMENT = "emotional_improvement"  # Mood improved
    EMOTIONAL_DECLINE = "emotional_decline"      # Mood worsened
    RETURNED_SOON = "returned_soon"              # Came back soon (satisfaction)
    LONG_ABSENCE = "long_absence"                # Disappeared for a long time
    # Sales-specific feedback
    BUYING_SIGNAL = "buying_signal"              # Client showed purchase intent
    OBJECTION_RAISED = "objection_raised"        # Client pushed back on offer
    PRICE_CONCERN = "price_concern"              # Client mentioned price sensitivity
    ESTIMATE_ACCEPTED = "estimate_accepted"      # Client accepted an estimate
    ESTIMATE_REJECTED = "estimate_rejected"      # Client rejected/abandoned estimate


class ResponseStrategy(Enum):
    """Response strategies that can be adjusted per client"""
    EMPATHY_FIRST = "empathy_first"        # Comfort before advising
    DIRECT_ADVICE = "direct_advice"        # Go straight to the advice
    QUESTION_BASED = "question_based"      # Ask clarifying questions
    PROJECT_FOCUSED = "project_focused"    # Reference project details/scope specifics
    PRACTICAL_STEPS = "practical_steps"    # Step-by-step guidance
    TECHNICAL_DEPTH = "technical_depth"    # Detailed tile/remodel terminology
    STORY_BASED = "story_based"            # Use examples and scenarios
    BRIEF = "brief"                        # Short responses
    DETAILED = "detailed"                  # Comprehensive responses


# ============================================
# IMPLICIT FEEDBACK DETECTOR
# ============================================

class ImplicitFeedbackDetector:
    """
    Detects user feedback without asking directly.
    Multilingual: EN + PT + ES
    """

    # Positive feedback indicators
    POSITIVE_INDICATORS = [
        # English
        "thank you", "thanks", "that helped", "makes sense",
        "you're right", "exactly", "perfect", "great",
        "understood", "got it", "clear now", "helpful",
        # Portuguese
        "obrigado", "obrigada", "valeu", "isso ajudou", "faz sentido",
        "entendi", "voce tem razao", "verdade", "exatamente",
        "perfeito", "maravilhoso", "otimo", "claro agora",
        # Spanish
        "gracias", "eso ayudo", "tiene sentido", "exacto",
        "perfecto", "entendi", "genial", "excelente"
    ]

    # Negative feedback indicators
    NEGATIVE_INDICATORS = [
        # English
        "that's not it", "you didn't understand", "not helpful",
        "doesn't help", "wrong", "incorrect", "that's not what I asked",
        "I disagree", "no that's wrong", "not what I meant",
        # Portuguese
        "nao e isso", "voce nao entendeu", "nao ajuda", "nao adianta",
        "errado", "nao concordo", "nao foi isso que perguntei",
        # Spanish
        "no es eso", "no entendiste", "no ayuda", "incorrecto",
        "no estoy de acuerdo", "equivocado"
    ]

    # Disengagement indicators
    DISENGAGEMENT_INDICATORS = [
        # English
        "ok", "k", "fine", "whatever", "never mind", "forget it",
        # Portuguese
        "ta", "sei", "hm", "tanto faz", "deixa pra la", "esquece",
        # Spanish
        "bueno", "da igual", "olvidalo", "no importa"
    ]

    # Sales buying signal indicators
    BUYING_INDICATORS = [
        # English
        "let's do it", "let's go", "sign me up", "i want to proceed",
        "how do i start", "where do i sign", "sounds good", "i'll take it",
        "how much is it", "what's the price", "can you start",
        "i'm ready", "let's move forward", "send me the contract",
        "when can you start", "book me in", "schedule me",
        # Portuguese
        "vamos fechar", "quero contratar", "como faco", "quanto fica",
        "vamos la", "pode comecar", "quero esse", "manda o contrato",
        # Spanish
        "vamos", "quiero contratar", "cuanto es", "me interesa",
        "como empiezo", "listo", "hagamoslo"
    ]

    # Price objection indicators
    PRICE_OBJECTION_INDICATORS = [
        # English
        "too expensive", "too much", "can't afford", "cheaper",
        "lower price", "budget", "discount", "better deal",
        "comparing prices", "other quotes", "cheaper option",
        "other estimates", "got a lower bid",
        # Portuguese
        "muito caro", "nao tenho condicoes", "mais barato", "desconto",
        "comparando precos", "orcamento", "valor alto",
        # Spanish
        "muy caro", "mas barato", "descuento", "precio alto",
        "no puedo pagar", "comparando precios"
    ]

    @classmethod
    def detect_feedback(cls, user_message: str, ai_response: str,
                       user_response: str, time_to_respond: float) -> List[FeedbackType]:
        """
        Detect implicit feedback based on user's follow-up response
        """
        feedbacks = []
        response_lower = user_response.lower()

        # Check positive indicators
        positive_count = sum(1 for ind in cls.POSITIVE_INDICATORS if ind in response_lower)
        if positive_count >= 2:
            feedbacks.append(FeedbackType.POSITIVE_EXPLICIT)

        # Check negative indicators
        negative_count = sum(1 for ind in cls.NEGATIVE_INDICATORS if ind in response_lower)
        if negative_count >= 2:
            feedbacks.append(FeedbackType.NEGATIVE_EXPLICIT)

        # Check engagement by response length
        if len(user_response) > 100:
            feedbacks.append(FeedbackType.ENGAGEMENT_HIGH)
        elif len(user_response) < 20:
            if any(ind in response_lower for ind in cls.DISENGAGEMENT_INDICATORS):
                feedbacks.append(FeedbackType.ENGAGEMENT_LOW)

        # Very fast response to long AI message = probably didn't read
        if time_to_respond < 2.0 and len(ai_response) > 200:
            feedbacks.append(FeedbackType.ENGAGEMENT_LOW)

        # Sales signals
        buying_count = sum(1 for ind in cls.BUYING_INDICATORS if ind in response_lower)
        if buying_count >= 1:
            feedbacks.append(FeedbackType.BUYING_SIGNAL)

        price_count = sum(1 for ind in cls.PRICE_OBJECTION_INDICATORS if ind in response_lower)
        if price_count >= 1:
            feedbacks.append(FeedbackType.PRICE_CONCERN)

        return feedbacks

    @classmethod
    def detect_emotional_shift(cls, emotion_before: str, emotion_after: str) -> Optional[FeedbackType]:
        """Detect emotional change after AI response"""
        positive_states = ["relieved", "grateful", "satisfied", "neutral"]
        negative_states = ["anxious", "frustrated", "confused", "worried", "upset", "urgent"]

        was_negative = emotion_before in negative_states
        is_positive = emotion_after in positive_states
        is_negative = emotion_after in negative_states
        was_positive = emotion_before in positive_states

        if was_negative and is_positive:
            return FeedbackType.EMOTIONAL_IMPROVEMENT
        elif was_positive and is_negative:
            return FeedbackType.EMOTIONAL_DECLINE

        return None


# ============================================
# LEARNING ENGINE
# ============================================

class LearningEngine:
    """
    Engine that adjusts AI behavior based on feedback.
    Works with database layer for persistence.
    """

    def __init__(self, db):
        self.db = db

    async def record_interaction(
        self,
        user_id: str,
        conversation_id: str,
        user_message: str,
        ai_response: str,
        strategy_used: ResponseStrategy,
        emotion_before: str,
        emotion_after: str,
        response_time: float
    ):
        """Record an interaction for learning"""
        interaction = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "user_message_length": len(user_message),
            "ai_response_length": len(ai_response),
            "strategy_used": strategy_used.value if hasattr(strategy_used, 'value') else str(strategy_used),
            "emotion_before": emotion_before,
            "emotion_after": emotion_after,
            "response_time": response_time,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Detect emotional shift
        emotional_feedback = ImplicitFeedbackDetector.detect_emotional_shift(
            emotion_before, emotion_after
        )

        if emotional_feedback:
            interaction["emotional_feedback"] = emotional_feedback.value

        await self._save_interaction(user_id, interaction)

    async def process_user_response(
        self,
        user_id: str,
        original_ai_response: str,
        user_response: str,
        time_to_respond: float,
        original_user_message: str
    ) -> List[FeedbackType]:
        """Process user's follow-up to extract feedback"""
        feedbacks = ImplicitFeedbackDetector.detect_feedback(
            original_user_message,
            original_ai_response,
            user_response,
            time_to_respond
        )

        for feedback in feedbacks:
            await self._save_feedback(user_id, feedback, original_ai_response)

        return feedbacks

    async def get_optimal_strategy(self, user_id: str, current_context: Dict) -> ResponseStrategy:
        """
        Determine the best response strategy based on history.
        Tile/remodel-domain adapted: no scripture strategy.
        """
        strategy_scores = await self._get_strategy_scores(user_id)

        emotional_state = current_context.get("emotional_state", "neutral")
        communication_style = current_context.get("communication_style", "supportive")
        urgency = current_context.get("urgency", 0)

        # High urgency -> always empathy first + practical steps
        if urgency > 0.7:
            return ResponseStrategy.EMPATHY_FIRST

        # Based on communication style
        if communication_style == "direct":
            preferred = [ResponseStrategy.DIRECT_ADVICE, ResponseStrategy.PRACTICAL_STEPS]
        elif communication_style == "technical":
            preferred = [ResponseStrategy.TECHNICAL_DEPTH, ResponseStrategy.PROJECT_FOCUSED]
        elif communication_style == "reflective":
            preferred = [ResponseStrategy.QUESTION_BASED, ResponseStrategy.STORY_BASED]
        else:  # supportive
            preferred = [ResponseStrategy.EMPATHY_FIRST, ResponseStrategy.PRACTICAL_STEPS]

        # Pick the best preferred strategy that has good history
        for strategy in preferred:
            if strategy_scores.get(strategy.value, 0.5) > 0.4:
                return strategy

        return ResponseStrategy.EMPATHY_FIRST

    async def adjust_profile(self, user_id: str, feedbacks: List[FeedbackType]):
        """Adjust user profile based on feedback"""
        profile = await self.db.get_user_profile(user_id)
        if not profile:
            return

        adjustments = {}

        for feedback in feedbacks:
            if feedback == FeedbackType.POSITIVE_EXPLICIT:
                adjustments["style_confidence_boost"] = 0.1
            elif feedback == FeedbackType.NEGATIVE_EXPLICIT:
                adjustments["style_confidence_decrease"] = 0.15
            elif feedback == FeedbackType.EMOTIONAL_IMPROVEMENT:
                adjustments["effective_interaction"] = True
            elif feedback == FeedbackType.EMOTIONAL_DECLINE:
                adjustments["ineffective_interaction"] = True
            elif feedback == FeedbackType.ENGAGEMENT_LOW:
                adjustments["prefer_brief"] = True
            elif feedback == FeedbackType.ENGAGEMENT_HIGH:
                adjustments["prefer_detailed"] = True

        await self._apply_adjustments(user_id, adjustments)

    async def detect_patterns(self, user_id: str) -> Dict:
        """Detect behavioral patterns from interaction history"""
        interactions = await self._get_interaction_history(user_id, days=30)

        if len(interactions) < 5:
            return {}

        patterns = {}

        # Activity hour pattern
        hours = {}
        for i in interactions:
            ts = i.get("created_at") or i.get("timestamp")
            if ts:
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)
                hours[ts.hour] = hours.get(ts.hour, 0) + 1

        if hours:
            patterns["peak_activity_hour"] = max(hours, key=hours.get)

        # Day of week pattern
        days = {}
        for i in interactions:
            ts = i.get("created_at") or i.get("timestamp")
            if ts:
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)
                day = ts.strftime("%A")
                days[day] = days.get(day, 0) + 1

        if days:
            patterns["peak_activity_day"] = max(days, key=days.get)

        # Recurring themes
        themes = {}
        for i in interactions:
            for theme in i.get("themes", []):
                themes[theme] = themes.get(theme, 0) + 1

        patterns["recurring_themes"] = themes

        return patterns

    # ============================================
    # PRIVATE METHODS
    # ============================================

    async def _save_interaction(self, user_id: str, interaction: Dict):
        """Save interaction to database"""
        await self.db.save_learning_interaction(
            user_id=user_id,
            conversation_id=interaction.get("conversation_id"),
            strategy_used=interaction.get("strategy_used"),
            emotion_before=interaction.get("emotion_before"),
            emotion_after=interaction.get("emotion_after"),
            response_time_ms=int(interaction.get("response_time", 0))
        )

    async def _save_feedback(self, user_id: str, feedback: FeedbackType, context: str):
        """Save feedback to database"""
        import uuid as uuid_module
        strategy = None
        try:
            user_uuid = uuid_module.UUID(user_id) if isinstance(user_id, str) else user_id
            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT strategy_used FROM learning_interactions
                    WHERE user_id = $1
                    ORDER BY created_at DESC LIMIT 1
                """, user_uuid)
                if row:
                    strategy = row["strategy_used"]
        except Exception as e:
            logger.error("Error getting strategy: %s", e)

        await self.db.save_learning_feedback(
            user_id=user_id,
            feedback_type=feedback.value,
            strategy_used=strategy,
            context=context
        )

    async def _get_strategy_scores(self, user_id: str) -> Dict[str, float]:
        """Get strategy effectiveness scores"""
        return await self.db.get_strategy_scores(user_id)

    async def _apply_adjustments(self, user_id: str, adjustments: Dict):
        """Apply adjustments to user profile"""
        await self.db.update_user_preferred_style(user_id, adjustments)

    async def _get_interaction_history(self, user_id: str, days: int) -> List[Dict]:
        """Get interaction history from database"""
        import uuid as uuid_module
        try:
            user_uuid = uuid_module.UUID(user_id) if isinstance(user_id, str) else user_id
            async with self.db.pool.acquire() as conn:
                table_exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'learning_interactions'
                    )
                """)

                if not table_exists:
                    return []

                rows = await conn.fetch("""
                    SELECT * FROM learning_interactions
                    WHERE user_id = $1 AND created_at > NOW() - INTERVAL '%s days'
                    ORDER BY created_at DESC
                """ % days, user_uuid)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error("Error getting interaction history: %s", e)
            return []


# ============================================
# LEARNING CONTEXT BUILDER
# ============================================

class LearningContextBuilder:
    """
    Builds learning context string for the AI system prompt.
    Tile/remodel-domain strategies (no scripture references).
    """

    @staticmethod
    def build_learning_context(
        optimal_strategy: ResponseStrategy,
        patterns: Dict,
        recent_feedbacks: List[FeedbackType]
    ) -> str:
        """Build learning context for the prompt"""
        context_parts = []

        # Recommended strategy
        strategy_descriptions = {
            ResponseStrategy.EMPATHY_FIRST: "Comfort first, validate feelings before advising on next steps.",
            ResponseStrategy.DIRECT_ADVICE: "Be direct and objective. Get to the point quickly.",
            ResponseStrategy.QUESTION_BASED: "Use clarifying questions to guide the conversation.",
            ResponseStrategy.PROJECT_FOCUSED: "Reference project details, scope, and tile/remodel specifics.",
            ResponseStrategy.PRACTICAL_STEPS: "Provide clear, actionable step-by-step guidance.",
            ResponseStrategy.TECHNICAL_DEPTH: "Use precise tile/remodel terminology when appropriate.",
            ResponseStrategy.STORY_BASED: "Use examples and scenarios to illustrate points.",
            ResponseStrategy.BRIEF: "Keep responses concise and to the point.",
            ResponseStrategy.DETAILED: "Provide comprehensive, detailed responses."
        }

        context_parts.append(
            f"RECOMMENDED STRATEGY: {strategy_descriptions.get(optimal_strategy, '')}"
        )

        # Recent feedback signals
        if FeedbackType.NEGATIVE_EXPLICIT in recent_feedbacks:
            context_parts.append(
                "Last response was NOT well received. Adjust your approach."
            )
        elif FeedbackType.POSITIVE_EXPLICIT in recent_feedbacks:
            context_parts.append(
                "Last response was well received. Continue this approach."
            )

        if FeedbackType.ENGAGEMENT_LOW in recent_feedbacks:
            context_parts.append(
                "Client seems disengaged. Try a different approach or be more concise."
            )

        # Sales-specific learning
        if FeedbackType.BUYING_SIGNAL in recent_feedbacks:
            context_parts.append(
                "Client showed buying intent! Guide them to scheduling an estimate naturally."
            )
        if FeedbackType.PRICE_CONCERN in recent_feedbacks:
            context_parts.append(
                "Client is price-sensitive. Lead with value, show most affordable option."
            )
        if FeedbackType.OBJECTION_RAISED in recent_feedbacks:
            context_parts.append(
                "Client raised objection. Acknowledge, don't push. Offer alternatives."
            )

        # Detected patterns
        if patterns.get("recurring_themes"):
            themes = patterns["recurring_themes"]
            top_themes = sorted(themes.items(), key=lambda x: x[1], reverse=True)[:2]
            if top_themes:
                context_parts.append(
                    f"Recurring topics: {', '.join([t[0] for t in top_themes])}"
                )

        return "\n".join(context_parts)
