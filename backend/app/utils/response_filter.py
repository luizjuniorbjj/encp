"""
ENCPServices - Response Filter
===================================
Filters AI responses before sending to clients:
- Flags sensitive data leaks (API keys, credit cards, addresses)
- Strips markdown for natural TTS output
- Catches off-topic or inappropriate content

Forked from SegurIA, adapted for tile/remodel company domain.
"""

import re

# Domain-irrelevant terms that might leak from AI hallucination -> corrections
TERM_REPLACEMENTS = {
    # If the AI accidentally uses insurance terms (from training data)
    "insurance policy": "service agreement",
    "Insurance policy": "Service agreement",
    "insurance claim": "service request",
    "Insurance claim": "Service request",
    "policyholder": "client",
    "Policyholder": "Client",
    "premium": "project cost",
    "deductible": "deposit",
    "Deductible": "Deposit",
    "coverage": "service scope",
    "Coverage": "Service scope",
}

# Patterns to flag in AI responses (for audit logging)
FLAGGED_PATTERNS = [
    # API key leaks — any key format that should never appear in responses
    (r'sk-[a-zA-Z0-9]{20,}', "LEAK: possible API key (sk-...)"),
    (r'key-[a-zA-Z0-9]{20,}', "LEAK: possible API key (key-...)"),
    (r'api[_-]?key["\s:=]+["\']?[a-zA-Z0-9]{10,}', "LEAK: possible API key assignment"),

    # Credit card numbers (basic pattern: 4 groups of 4 digits)
    (r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', "LEAK: possible credit card number"),

    # Full SSN pattern
    (r'\b\d{3}-\d{2}-\d{4}\b', "LEAK: possible SSN"),

    # Full address exposure (street number + street name + city/state/zip)
    (r'\b\d{1,5}\s+\w+\s+(St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Rd|Road|Ln|Lane|Ct|Court|Way|Pl|Place)\b.*\b(FL|CA|TX|NY|GA|NC|SC|AL|OH|PA|IL|NJ|VA|WA|OR|AZ|CO|MI|MN|WI|MD|MA|IN|MO|TN|KY|LA|OK|CT|IA|MS|AR|KS|NV|NE|NM|WV|ID|HI|ME|NH|RI|MT|DE|SD|ND|AK|VT|WY|DC)\s+\d{5}',
     "LEAK: possible full address with state and ZIP"),

    # Bank routing numbers (9 digits starting with valid ABA prefix)
    (r'\brouting\s*#?\s*:?\s*\d{9}\b', "LEAK: possible bank routing number"),
    (r'\baccount\s*#?\s*:?\s*\d{6,17}\b', "LEAK: possible bank account number"),

    # Off-topic: insurance jargon that shouldn't appear in tile/remodel context
    (r'\b(underwriting|actuarial|indemnity|subrogation)\b', "OFF_TOPIC: insurance jargon detected"),

    # Off-topic: medical/legal advice
    (r'\b(medical advice|legal advice|I am not a (doctor|lawyer|attorney))\b', "OFF_TOPIC: medical/legal disclaimer"),
]


def filter_response(text: str) -> tuple[str, list[str]]:
    """Filter AI response before sending to client.

    Returns:
        (filtered_text, warnings) — warnings list for audit logging
    """
    warnings = []
    filtered = text

    # Apply term replacements
    for term, replacement in TERM_REPLACEMENTS.items():
        if term in filtered:
            filtered = filtered.replace(term, replacement)
            warnings.append(f"REPLACED: '{term}' -> '{replacement}'")

    # Check for flagged patterns
    for pattern, description in FLAGGED_PATTERNS:
        if re.search(pattern, filtered, re.IGNORECASE):
            warnings.append(f"FLAG: {description}")

    return filtered, warnings


def strip_markdown_for_tts(text: str) -> str:
    """Strip markdown/formatting so TTS reads natural speech, not syntax."""
    t = text
    # Remove bold/italic markers: **text** -> text, *text* -> text
    t = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', t)
    # Remove underline: __text__ -> text
    t = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', t)
    # Remove strikethrough: ~~text~~ -> text
    t = re.sub(r'~~([^~]+)~~', r'\1', t)
    # Remove markdown links: [text](url) -> text
    t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', t)
    # Remove bullet points: - item -> item, * item -> item
    t = re.sub(r'^[\s]*[-*•]\s+', '', t, flags=re.MULTILINE)
    # Remove numbered lists: 1. item -> item
    t = re.sub(r'^[\s]*\d+[.)]\s+', '', t, flags=re.MULTILINE)
    # Remove headers: ## Title -> Title
    t = re.sub(r'^#{1,6}\s+', '', t, flags=re.MULTILINE)
    # Remove emojis (common Unicode ranges)
    t = re.sub(r'[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]', '', t)
    # Clean up extra whitespace
    t = re.sub(r'\n{3,}', '\n\n', t)
    t = re.sub(r'  +', ' ', t)
    return t.strip()
