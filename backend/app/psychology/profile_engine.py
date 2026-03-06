"""
ENCPServices - Psychological Profile Engine
Behavioral analysis and communication style detection for tile/remodel clients
Forked from AiSyster — adapted from spiritual to tile/remodel domain
"""

from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum


# ============================================
# ENUMS
# ============================================

class CommunicationStyle(Enum):
    """Communication styles based on user preferences"""
    DIRECT = "direct"          # Wants objective, practical answers
    REFLECTIVE = "reflective"  # Likes questions and reflection
    SUPPORTIVE = "supportive"  # Needs emotional validation first
    TECHNICAL = "technical"    # Prefers detailed technical explanations


class EmotionalState(Enum):
    """Detectable emotional states"""
    ANXIOUS = "anxious"
    FRUSTRATED = "frustrated"
    CONFUSED = "confused"
    RELIEVED = "relieved"
    GRATEFUL = "grateful"
    NEUTRAL = "neutral"
    WORRIED = "worried"
    UPSET = "upset"
    SATISFIED = "satisfied"
    URGENT = "urgent"


class ProcessingStyle(Enum):
    """How the person processes information"""
    ANALYTICAL = "analytical"  # Needs logic and data
    EMOTIONAL = "emotional"    # Processes through feelings
    PRACTICAL = "practical"    # Wants to know what to do
    NARRATIVE = "narrative"    # Learns from stories and examples


# ============================================
# MESSAGE ANALYZER
# ============================================

class MessageAnalyzer:
    """
    Analyzes messages to extract psychological information
    for adapting AI communication style
    """

    # Keywords to detect emotional states (EN + PT + ES)
    EMOTION_KEYWORDS = {
        EmotionalState.ANXIOUS: [
            "anxious", "worried", "nervous", "stressed", "can't stop thinking",
            "what if", "scared", "afraid", "panic",
            "ansioso", "ansiosa", "preocupado", "preocupada", "nervoso",
            "estressado", "nao consigo parar de pensar",
            "ansioso", "preocupado", "nervioso", "estresado"
        ],
        EmotionalState.FRUSTRATED: [
            "frustrated", "angry", "furious", "unfair", "ridiculous",
            "can't believe", "terrible", "worst", "unacceptable", "hate",
            "irritado", "irritada", "raiva", "absurdo", "injusto",
            "frustrado", "frustrada", "enojado", "furioso"
        ],
        EmotionalState.CONFUSED: [
            "confused", "don't understand", "lost", "what does that mean",
            "not sure", "unclear", "makes no sense", "explain",
            "confuso", "confusa", "nao entendo", "perdido", "perdida",
            "no entiendo", "confundido"
        ],
        EmotionalState.WORRIED: [
            "worried", "concern", "what happens if", "afraid of",
            "will they", "are they going to", "might lose",
            "preocupado", "medo de", "e se", "sera que",
            "que pasa si", "me preocupa"
        ],
        EmotionalState.URGENT: [
            "urgent", "emergency", "right now", "immediately", "asap",
            "just happened", "need help now",
            "urgente", "emergencia", "agora", "preciso de ajuda",
            "urgente", "emergencia", "ahora mismo"
        ],
        EmotionalState.RELIEVED: [
            "relieved", "thank god", "finally", "that's a relief",
            "good to know", "weight off", "feel better",
            "aliviado", "aliviada", "finalmente", "que alivio",
            "aliviado", "por fin", "que alivio"
        ],
        EmotionalState.GRATEFUL: [
            "thank you", "thanks", "appreciate", "helpful", "great help",
            "you helped", "grateful", "wonderful",
            "obrigado", "obrigada", "valeu", "agradeco",
            "gracias", "agradecido", "muchas gracias"
        ],
        EmotionalState.UPSET: [
            "upset", "disappointed", "let down", "unhappy",
            "not satisfied", "complaint", "complain",
            "chateado", "chateada", "desapontado", "insatisfeito",
            "molesto", "decepcionado", "insatisfecho"
        ],
        EmotionalState.SATISFIED: [
            "satisfied", "happy with", "good service", "well done",
            "impressed", "excellent", "perfect",
            "satisfeito", "satisfeita", "feliz", "otimo",
            "satisfecho", "contento", "excelente"
        ]
    }

    # Communication style indicators
    STYLE_INDICATORS = {
        CommunicationStyle.DIRECT: [
            "just tell me", "bottom line", "cut to the chase", "what do I do",
            "give me the answer", "in short", "quickly", "fast",
            "resumindo", "direto ao ponto", "me diz logo", "rapido",
            "directo", "al grano", "rapido"
        ],
        CommunicationStyle.REFLECTIVE: [
            "do you think", "what would you suggest", "is it worth",
            "should I consider", "what are my options", "pros and cons",
            "voce acha", "sera que", "vale a pena", "quais opcoes",
            "que opinas", "deberia considerar"
        ],
        CommunicationStyle.SUPPORTIVE: [
            "I'm scared", "I don't know what to do", "help me",
            "feeling overwhelmed", "this is too much", "need guidance",
            "estou com medo", "nao sei o que fazer", "me ajuda",
            "tengo miedo", "no se que hacer", "ayudame"
        ],
        CommunicationStyle.TECHNICAL: [
            "specifically", "details", "technically", "exactly how",
            "what are the specs", "finish type", "product brand", "square footage",
            "especificamente", "detalhes", "tecnicamente", "especificacoes",
            "especificamente", "detalles", "tecnicamente", "especificaciones"
        ]
    }

    # Processing style indicators
    PROCESSING_INDICATORS = {
        ProcessingStyle.ANALYTICAL: [
            "numbers", "data", "percentage", "statistics", "compare",
            "breakdown", "calculation", "how is it calculated",
            "numeros", "dados", "porcentagem", "comparar", "calcular",
            "numeros", "datos", "porcentaje", "comparar"
        ],
        ProcessingStyle.EMOTIONAL: [
            "feel", "feeling", "heart", "soul", "hurts",
            "painful", "emotional", "scared",
            "sinto", "senti", "coracao", "dor", "medo",
            "siento", "corazon", "dolor", "miedo"
        ],
        ProcessingStyle.PRACTICAL: [
            "what to do", "next steps", "how to", "steps",
            "action", "practical", "procedure", "process",
            "o que fazer", "proximo passo", "como", "procedimento",
            "que hacer", "siguiente paso", "como", "procedimiento"
        ],
        ProcessingStyle.NARRATIVE: [
            "what happened was", "the story is", "for example",
            "imagine", "like when", "situation", "scenario",
            "o que aconteceu", "a historia", "por exemplo", "imagine",
            "lo que paso", "la historia", "por ejemplo"
        ]
    }

    @classmethod
    def detect_emotional_state(cls, message: str) -> tuple:
        """
        Detect emotional state from message.
        Returns (EmotionalState, confidence)
        """
        message_lower = message.lower()
        scores = {}

        for state, keywords in cls.EMOTION_KEYWORDS.items():
            count = sum(1 for kw in keywords if kw in message_lower)
            if count > 0:
                scores[state] = count

        if not scores:
            return EmotionalState.NEUTRAL, 0.5

        best_state = max(scores, key=scores.get)
        confidence = min(1.0, scores[best_state] / 3)

        return best_state, confidence

    @classmethod
    def detect_communication_style(cls, message: str) -> tuple:
        """Detect preferred communication style"""
        message_lower = message.lower()
        scores = {}

        for style, indicators in cls.STYLE_INDICATORS.items():
            count = sum(1 for ind in indicators if ind in message_lower)
            if count > 0:
                scores[style] = count

        if not scores:
            return CommunicationStyle.SUPPORTIVE, 0.3

        best_style = max(scores, key=scores.get)
        confidence = min(1.0, scores[best_style] / 2)

        return best_style, confidence

    @classmethod
    def detect_processing_style(cls, message: str) -> tuple:
        """Detect information processing style"""
        message_lower = message.lower()
        scores = {}

        for style, indicators in cls.PROCESSING_INDICATORS.items():
            count = sum(1 for ind in indicators if ind in message_lower)
            if count > 0:
                scores[style] = count

        if not scores:
            return ProcessingStyle.PRACTICAL, 0.3

        best_style = max(scores, key=scores.get)
        confidence = min(1.0, scores[best_style] / 2)

        return best_style, confidence

    @classmethod
    def extract_themes(cls, message: str) -> List[str]:
        """Extract tile/remodel-domain themes from message"""
        themes = []
        message_lower = message.lower()

        theme_keywords = {
            "tile_installation": ["tile", "tiling", "porcelain", "ceramic", "marble", "granite", "azulejo", "ceramica", "marmol", "granito"],
            "floor_installation": ["floor", "flooring", "laminate", "hardwood", "vinyl", "piso", "laminado", "madera", "vinilo"],
            "bathroom_remodel": ["bathroom", "shower", "tub", "bathtub", "vanity", "banheiro", "chuveiro", "banheira", "bano", "ducha"],
            "kitchen_remodel": ["kitchen", "countertop", "backsplash", "cozinha", "bancada", "cocina", "encimera"],
            "estimate": ["estimate", "quote", "price", "cost", "how much", "orcamento", "preco", "cuanto cuesta", "presupuesto"],
            "prep_work": ["prep", "preparation", "demolition", "removal", "subfloor", "leveling", "waterproof", "preparacao", "demolicao", "preparacion"],
            "timeline": ["how long", "when will", "timeline", "schedule", "start date", "finish date", "quanto tempo", "quando", "cuanto tiempo", "cuando"],
            "material_type": ["material", "porcelain", "ceramic", "natural stone", "travertine", "slate", "mosaic", "material", "pedra natural", "mosaico"],
            "rooms": ["room", "rooms", "bedroom", "bathroom", "kitchen", "living room", "dining room", "hallway", "basement", "quarto", "sala", "cozinha", "habitacion"],
            "damage_repair": ["damage", "water damage", "cracking", "chipping", "mold", "mildew", "uneven", "dano", "rachadura", "mofo", "dano", "humedad"],
            "grouting": ["grout", "grouting", "regrout", "grout repair", "rejunte", "lechada"],
            "payment": ["pay", "payment", "deposit", "financing", "pagar", "pagamento", "deposito", "pago", "deposito"],
        }

        for theme, keywords in theme_keywords.items():
            if any(kw in message_lower for kw in keywords):
                themes.append(theme)

        return themes

    @classmethod
    def detect_urgency(cls, message: str) -> float:
        """
        Detect urgency level (0-1).
        Tile/remodel-specific: water damage, move-in deadline, etc.
        """
        message_lower = message.lower()

        urgency_indicators = [
            ("just happened", 0.9),
            ("right now", 0.8),
            ("emergency", 0.9),
            ("need help immediately", 0.9),
            ("asap", 0.7),
            ("urgent", 0.8),
            ("water damage", 0.8),
            ("mold", 0.7),
            ("moving in", 0.8),
            ("move-in date", 0.9),
            ("closing date", 0.9),
            ("tenant moving in", 0.9),
            ("open house", 0.7),
            ("listing soon", 0.7),
            ("deadline", 0.8),
            ("this week", 0.6),
            ("tomorrow", 0.8),
            ("today", 0.9),
            ("acabou de acontecer", 0.9),
            ("agora mesmo", 0.8),
            ("urgente", 0.8),
            ("emergencia", 0.9),
            ("preciso de ajuda agora", 0.9),
            ("acaba de pasar", 0.9),
            ("ahora mismo", 0.8),
        ]

        max_urgency = 0.0
        for phrase, urgency in urgency_indicators:
            if phrase in message_lower:
                max_urgency = max(max_urgency, urgency)

        return max_urgency

    @classmethod
    def analyze_message(cls, message: str) -> Dict:
        """Full message analysis for psychological profiling"""
        emotional_state, emotion_confidence = cls.detect_emotional_state(message)
        comm_style, comm_confidence = cls.detect_communication_style(message)
        proc_style, proc_confidence = cls.detect_processing_style(message)
        themes = cls.extract_themes(message)
        urgency = cls.detect_urgency(message)

        return {
            "emotional_state": emotional_state.value,
            "emotion_confidence": emotion_confidence,
            "communication_style": comm_style.value,
            "communication_confidence": comm_confidence,
            "processing_style": proc_style.value,
            "processing_confidence": proc_confidence,
            "themes": themes,
            "urgency": urgency,
            "message_length": len(message),
            "timestamp": datetime.utcnow().isoformat()
        }


# ============================================
# PSYCHOLOGICAL CONTEXT BUILDER
# ============================================

class PsychologicalContextBuilder:
    """
    Builds psychological context string for the AI system prompt.
    Helps the AI adapt its communication style to each client.
    """

    @staticmethod
    def build_context(profile: Dict, current_analysis: Dict) -> str:
        """
        Build psychological context to inject into the AI prompt.
        """
        context_parts = []

        # Current emotional state
        emotional_state = current_analysis.get("emotional_state", "neutral")
        context_parts.append(f"Current emotional state: {emotional_state}")

        # Urgency level
        urgency = current_analysis.get("urgency", 0)
        if urgency > 0.7:
            context_parts.append(
                "HIGH URGENCY — Possible time-sensitive project. Be extremely helpful and clear. "
                "Prioritize immediate availability and next steps."
            )
        elif urgency > 0.4:
            context_parts.append(
                "Elevated attention — Client may have a tight deadline. "
                "Be patient and thorough."
            )

        # Preferred communication style
        comm_style = profile.get("communication_style", "supportive")
        style_instructions = {
            "direct": "Prefers concise, objective answers. Get to the point quickly.",
            "reflective": "Likes to weigh options. Present alternatives and let them decide.",
            "supportive": "Needs reassurance first. Acknowledge their concern before advising.",
            "technical": "Appreciates detailed, technical explanations. Use precise terminology."
        }
        instruction = style_instructions.get(comm_style, "")
        if instruction:
            context_parts.append(f"Communication preference: {instruction}")

        # Processing style
        proc_style = profile.get("processing_style", "practical")
        proc_instructions = {
            "analytical": "Processes through logic and data. Use numbers and comparisons.",
            "emotional": "Processes through feelings. Connect empathetically first.",
            "practical": "Wants actionable steps. Provide clear next actions.",
            "narrative": "Learns from examples. Use scenarios to illustrate points."
        }
        instruction = proc_instructions.get(proc_style, "")
        if instruction:
            context_parts.append(f"Processing style: {instruction}")

        # Recurring themes
        recurring = profile.get("recurring_themes", {})
        if recurring:
            top_themes = sorted(recurring.items(), key=lambda x: x[1], reverse=True)[:3]
            themes_str = ", ".join([t[0] for t in top_themes])
            context_parts.append(f"Recurring topics for this client: {themes_str}")

        # Openness level
        openness = profile.get("openness_level", 0.5)
        if openness < 0.3:
            context_parts.append("This client is reserved. Don't push for details.")
        elif openness > 0.7:
            context_parts.append("This client is open. Can ask follow-up questions freely.")

        # Correction receptivity
        correction = profile.get("correction_receptivity", 0.5)
        if correction < 0.3:
            context_parts.append("Sensitive to correction. Be very gentle when correcting.")
        elif correction > 0.7:
            context_parts.append("Receptive to correction. Can be more direct if needed.")

        return "\n".join(context_parts)
