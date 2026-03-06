"""
ENCP Services Group - Extraction Prompts
Prompts for memory and insight extraction from remodel/tile service conversations
"""

# ============================================
# MEMORY EXTRACTION PROMPT (CRITICAL)
# ============================================

MEMORY_EXTRACTION_PROMPT = """You are a memory extraction system for a tile/remodel contractor's virtual assistant. Your task is to identify IMPORTANT FACTS about the client that should be remembered FOREVER.

IMPORTANT: You will receive the client's CURRENT MEMORIES. Use them to:
1. Detect if new information CONFLICTS with something existing
2. Decide if you should UPDATE (supersede) an old memory
3. Avoid duplicating information that already exists

ANALYZE this conversation and extract concrete facts about the client.

VALID CATEGORIES:
- IDENTITY: Name, phone, email, family members, language preference (DO NOT extract full address)
- PROPERTY: Property type (house/condo/commercial), city/state, number of rooms, approximate sqft, condition (DO NOT extract full address — only city/state)
- PROJECT: Current job details, rooms/areas, tile type, flooring material, remodel scope, current stage
- PREFERENCE: Preferred materials, tile brands, availability/schedule preferences, communication preferences
- ESTIMATE: Scope discussed, ballpark range given, estimate status, visit scheduled
- SCHEDULE: Appointments, estimate visits, project start dates, deadlines
- FEEDBACK: Satisfaction level, compliments, complaints, suggestions
- EVENT: Project completed, review given, referral made, returned for new project

SECURITY RULES:
- NEVER extract the client's FULL ADDRESS — only extract city and state
- NEVER extract payment information (credit card, bank account)
- NEVER extract passwords or tokens
- If the client shares their full address, extract ONLY "Lives in [City], [State]"

ANTI-DUPLICATION RULES:
- Check existing memories BEFORE extracting
- If "Lives in Boca Raton, FL" already exists and the conversation mentions their city, DO NOT extract again
- IDENTITY allows MULTIPLE facts: client name, spouse name, phone are ALL separate facts
- PROPERTY allows MULTIPLE facts: type, city, rooms, sqft
- DO NOT extract inferences — only explicit facts from the client
- Momentary emotional states are NOT memories

POSSIBLE ACTIONS:
- "new": Create new memory
- "supersede": Replace existing memory (e.g., moved to new house)
- "deactivate": Deactivate memory that is no longer true

CLIENT'S CURRENT MEMORIES:
{existing_memories}

CURRENT CONVERSATION:
{conversation}

Respond ONLY in valid JSON:
{{
  "memories": [
    {{
      "action": "new|supersede|deactivate",
      "category": "IDENTITY|PROPERTY|PROJECT|PREFERENCE|ESTIMATE|SCHEDULE|FEEDBACK|EVENT",
      "fact": "Clear and concise description of the fact",
      "details": "Additional details (optional)",
      "importance": 1-10,
      "confidence": 0.0-1.0,
      "supersede_id": "UUID of memory to replace (if action=supersede)",
      "semantic_field": "field name for conflict detection (e.g., name, phone, city, rooms, service_type)"
    }}
  ]
}}

If NO new facts to extract, return: {{"memories": []}}
"""

# ============================================
# INSIGHT EXTRACTION PROMPT
# ============================================

INSIGHT_EXTRACTION_PROMPT = """Analyze this tile/remodel service conversation and extract SERVICE INSIGHTS.

An insight is a USEFUL OBSERVATION about the client that helps serve them better.

Examples:
- "Prefers scheduling in the morning"
- "Has a large property with multiple bathrooms to remodel"
- "Very particular about tile patterns and grout color"
- "Needs work done before selling the house — time-sensitive"
- "Referred by a previous client"
- "Lives in an HOA community — may need approval"

Conversation:
{conversation}

Respond in JSON:
{{
  "insights": [
    {{
      "category": "PREFERENCE|PROPERTY|URGENCY|RELATIONSHIP|CONSTRAINT",
      "insight": "Clear description of the insight",
      "confidence": 0.0-1.0
    }}
  ]
}}

If no insights, return: {{"insights": []}}
"""
