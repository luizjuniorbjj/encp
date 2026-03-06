"""
ENCP Services Group - Analysis Prompts
Prompts for client profile analysis and summaries
"""

# ============================================
# CLIENT PROFILE ANALYSIS PROMPT
# ============================================

CLIENT_ANALYSIS_PROMPT = """Analyze this remodel/tile service client's conversation history and create a service-oriented psychological profile.

EVALUATE:
1. **Communication style** (DIRECT, REFLECTIVE, ANXIOUS, TECHNICAL)
   - DIRECT: Wants quick, objective answers
   - REFLECTIVE: Likes to understand before deciding
   - ANXIOUS: Worried about cost, timeline, or quality
   - TECHNICAL: Understands materials, tile types, wants details

2. **Processing style** (ANALYTICAL, EMOTIONAL, PRACTICAL, NARRATIVE)
   - ANALYTICAL: Compares prices, wants itemized estimates
   - EMOTIONAL: Decides based on trust and comfort
   - PRACTICAL: Wants quick resolution, no fuss
   - NARRATIVE: Tells stories about their home, needs to feel heard

3. **Primary needs** (list up to 3)
   - E.g.: "fair price", "quality finish", "fast turnaround", "reliability", "material advice"

4. **Emotional triggers** (what causes frustration or anxiety)
   - E.g.: "slow response", "unexpected costs", "schedule changes", "mess/disruption"

5. **Confidence level** (0.0 to 1.0) - how much they trust the interaction

History:
{conversation_history}

Respond in JSON:
{{
  "communication_style": "DIRECT|REFLECTIVE|ANXIOUS|TECHNICAL",
  "processing_style": "ANALYTICAL|EMOTIONAL|PRACTICAL|NARRATIVE",
  "primary_needs": ["need1", "need2"],
  "emotional_triggers": ["trigger1", "trigger2"],
  "confidence_score": 0.7
}}
"""

# ============================================
# CONVERSATION SUMMARY PROMPT
# ============================================

SUMMARY_PROMPT = """Summarize this conversation between a client and the ENCP Services assistant (tile/remodel contractor) in 2-3 sentences.

Focus on:
- What the client wanted (estimate, scheduling, project update, question)
- What was resolved
- What is still pending

Conversation:
{conversation}
"""
