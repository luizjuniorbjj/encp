"""
ENCP Services Group - Template Prompts
Client context templates and onboarding
"""

# ============================================
# CLIENT CONTEXT TEMPLATE
# ============================================

USER_CONTEXT_TEMPLATE = """
=== WHO IS {name} ===
Name: {name}
{phone_line}
{city_line}

=== PROPERTY ===
{property_line}

=== ACTIVE PROJECT ===
{project_line}

=== LEAD STATUS ===
{lead_line}

=== PAST ESTIMATES ===
{estimate_line}

=== SCHEDULE ===
{schedule_line}

=== SERVICE PROFILE ===
{psychological_context}

=== CONTEXT (use with discretion) ===
Relevant history: {history_summary}
(DO NOT assume past situations remain the same)
Preferred tone: {preferred_tone}

=== CONTINUOUS LEARNING ===
{learning_context}

=== GUIDELINES FOR THIS CONVERSATION ===
- Use the name "{nickname}" naturally (but not in every sentence)
- Communication tone: {preferred_tone}
- You may use name and property data naturally (like a contractor who remembers)
- DO NOT repeat the client's full address even if you have it — use City only
- Be natural, don't sound like you're "reading a file" about the client
"""

# ============================================
# ONBOARDING TEMPLATE
# ============================================

ONBOARDING_PROMPT = """Hi! I'm the virtual assistant for ENCP Services Group.

I can help you with:
- Floor & Tile Installation
- Bathroom & Kitchen Remodeling
- Free Estimates
- Project Updates

What can I help you with today?
"""

# ============================================
# ESTIMATE VISIT CONFIRMATION
# ============================================

ESTIMATE_VISIT_TEMPLATE = """Just to confirm your free estimate visit:

Date: {date}
Time: {time}
Location: {city}, FL
Service: {service_type}

Our team will assess the job and provide a detailed estimate on the spot. Please make sure someone is available at the property.

Need to reschedule? Just let me know!
"""


# ============================================
# BUILD USER CONTEXT (for AI prompt)
# ============================================

def build_user_context(
    profile: dict = None,
    lead: dict = None,
    project: dict = None,
    estimates: list = None,
    history_summary: str = "",
    psychological_context: str = "",
    learning_context: str = "",
    schedule_info: str = "",
    property_memories: list = None
) -> str:
    """
    Builds the user context block for the AI system prompt.
    Uses data from profile, lead, project, and estimates.
    """
    if not profile:
        return ""

    name = profile.get("nome") or "Client"
    nickname = name.split()[0] if name != "Client" else "Client"
    phone = profile.get("phone", "")
    city = profile.get("city", "")
    state = profile.get("state", "FL")
    preferred_tone = profile.get("tom_preferido", "friendly")

    phone_line = f"Phone: {phone}" if phone else "Phone: not provided"
    city_line = f"Location: {city}, {state}" if city else "Location: not provided"

    # Property info from lead, memories, or public records lookup
    property_line = "No property info"
    property_parts = []

    # From lead record
    if lead:
        if lead.get("property_type"):
            property_parts.append(f"Type: {lead['property_type']}")
        if lead.get("rooms_areas"):
            property_parts.append(f"Areas: {lead['rooms_areas']}")
        if lead.get("sqft_estimate"):
            property_parts.append(f"~{lead['sqft_estimate']} sqft")

    # From property lookup memories (public records)
    if property_memories:
        for mem in property_memories:
            fato = mem.get("fato", "")
            if fato and fato not in property_parts:
                property_parts.append(fato)

    if property_parts:
        property_line = "\n  ".join(property_parts)

    # Active project
    project_line = "No active project"
    if project:
        stage = project.get("stage", "unknown")
        desc = project.get("description", "")
        project_line = f"Stage: {stage}"
        if desc:
            project_line += f" — {desc[:100]}"
        if project.get("crew_assigned"):
            project_line += f" (Crew: {project['crew_assigned']})"

    # Lead status
    lead_line = "No lead record"
    if lead:
        status = lead.get("status", "unknown")
        service = lead.get("service_type", "")
        lead_line = f"Status: {status}"
        if service:
            lead_line += f", Service: {service}"
        if lead.get("timeline"):
            lead_line += f", Timeline: {lead['timeline']}"

    # Estimates
    estimate_line = "No estimates"
    if estimates:
        est_parts = []
        for e in estimates[:3]:
            est_status = e.get("status", "draft")
            low = e.get("estimated_cost_low")
            high = e.get("estimated_cost_high")
            if low and high:
                est_parts.append(f"${low:,.0f}-${high:,.0f} ({est_status})")
            else:
                est_parts.append(f"({est_status})")
        estimate_line = " | ".join(est_parts)

    # Schedule
    schedule_line = schedule_info or "No appointments scheduled"

    return USER_CONTEXT_TEMPLATE.format(
        name=name,
        nickname=nickname,
        phone_line=phone_line,
        city_line=city_line,
        property_line=property_line,
        project_line=project_line,
        lead_line=lead_line,
        estimate_line=estimate_line,
        schedule_line=schedule_line,
        psychological_context=psychological_context or "Not enough data yet",
        history_summary=history_summary or "First interaction",
        preferred_tone=preferred_tone,
        learning_context=learning_context or "No learning data yet"
    )
