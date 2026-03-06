"""
ENCPServices - Property Lookup
Busca dados do imovel por endereco usando fontes gratuitas.
Fonte primaria: HomeHarvest (scrape Realtor.com, sem API key)
Fallback: Zillow scraping direto
"""

import re
import logging
from typing import Optional, Dict

logger = logging.getLogger("encp.property")

# Property type classification
PROPERTY_TYPE_MAP = {
    "single_family": "casa",
    "single family": "casa",
    "detached": "casa",
    "house": "casa",
    "condo": "condo",
    "condominium": "condo",
    "apartment": "condo",
    "co-op": "condo",
    "townhouse": "townhouse",
    "townhome": "townhouse",
    "rowhouse": "townhouse",
    "row house": "townhouse",
    "multi_family": "predio_multifamiliar",
    "multi-family": "predio_multifamiliar",
    "duplex": "predio_multifamiliar",
    "triplex": "predio_multifamiliar",
    "quadplex": "predio_multifamiliar",
    "2-4 units": "predio_multifamiliar",
    "5+ units": "predio_multifamiliar",
    "land": "terreno",
    "lot": "terreno",
    "vacant land": "terreno",
}


def classify_property_type(raw_type: str) -> str:
    """Classify property type from raw string."""
    if not raw_type:
        return "INDISPONIVEL"
    raw_lower = raw_type.lower().strip()
    for key, value in PROPERTY_TYPE_MAP.items():
        if key in raw_lower:
            return value
    return "INDISPONIVEL"


def _extract_address_parts(address: str) -> dict:
    """Extract city, state, zip from address string."""
    parts = {"city": "", "state": "", "zip_code": ""}

    # Try to extract ZIP
    zip_match = re.search(r'\b(\d{5})(?:-\d{4})?\b', address)
    if zip_match:
        parts["zip_code"] = zip_match.group(1)

    # Try to extract state (2-letter code)
    state_match = re.search(r'\b([A-Z]{2})\b', address)
    if state_match:
        parts["state"] = state_match.group(1)

    # Try to extract city (between last comma and state)
    city_match = re.search(r',\s*([^,]+?)\s*,?\s*[A-Z]{2}\b', address)
    if city_match:
        parts["city"] = city_match.group(1).strip()

    return parts


async def lookup_property(address: str) -> Optional[Dict]:
    """
    Look up property data by address.
    Returns structured dict or None if not found.

    Uses HomeHarvest (free, no API key) to search Realtor.com.
    Falls back to basic address parsing if lookup fails.
    """
    if not address or len(address.strip()) < 5:
        return None

    address = address.strip()
    logger.info(f"[PROPERTY] Looking up: {address}")

    # Try HomeHarvest first
    result = await _lookup_homeharvest(address)

    if result:
        logger.info(f"[PROPERTY] Found via HomeHarvest: {result.get('beds')}BR/{result.get('baths')}BA, {result.get('sqft')} SF")
        return result

    logger.warning(f"[PROPERTY] No data found for: {address}")
    return None


async def _lookup_homeharvest(address: str) -> Optional[Dict]:
    """Search property using HomeHarvest (scrapes Realtor.com)."""
    try:
        import asyncio
        from homeharvest import scrape_property

        # Run sync scraper in thread pool to not block async
        loop = asyncio.get_event_loop()

        # Try "sold" listing type first (finds any property with history)
        for listing_type in ["sold", "for_sale", "for_rent"]:
            try:
                df = await loop.run_in_executor(
                    None,
                    lambda lt=listing_type: scrape_property(
                        location=address,
                        listing_type=lt,
                        radius=0.5,
                    )
                )

                if df is not None and not df.empty:
                    # Find best match (closest to the address)
                    row = df.iloc[0]
                    return _parse_homeharvest_row(row, address)

            except Exception as e:
                logger.debug(f"[PROPERTY] HomeHarvest {listing_type} failed: {e}")
                continue

    except ImportError:
        logger.warning("[PROPERTY] homeharvest not installed. Run: pip install homeharvest")
    except Exception as e:
        logger.error(f"[PROPERTY] HomeHarvest error: {e}")

    return None


def _parse_homeharvest_row(row, original_address: str) -> Dict:
    """Parse a HomeHarvest DataFrame row into our standard format."""

    def safe_get(field, default=None):
        try:
            val = row.get(field)
            if val is not None and str(val) not in ("nan", "NaN", "None", ""):
                return val
            return default
        except Exception:
            return default

    def safe_int(field):
        val = safe_get(field)
        if val is not None:
            try:
                return int(float(val))
            except (ValueError, TypeError):
                pass
        return None

    def safe_float(field):
        val = safe_get(field)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
        return None

    # Build normalized address
    street = safe_get("street_address", "")
    city = safe_get("city", "")
    state = safe_get("state", "")
    zip_code = safe_get("zip_code", "")

    address_parts = [p for p in [street, city, state, zip_code] if p]
    address_normalized = ", ".join(address_parts) if address_parts else original_address

    # Get property type
    raw_type = safe_get("style", safe_get("property_type", ""))
    property_type = classify_property_type(str(raw_type)) if raw_type else "INDISPONIVEL"

    # Get stories
    stories = safe_int("stories")

    # Build result
    result = {
        "address_input": original_address,
        "address_normalized": address_normalized,
        "property_type": property_type,
        "beds": safe_int("beds"),
        "baths": safe_int("full_baths"),
        "half_baths": safe_int("half_baths"),
        "sqft": safe_int("sqft") or safe_int("square_feet"),
        "year_built": safe_int("year_built"),
        "lot_sqft": safe_int("lot_sqft") or safe_int("lot_area_value"),
        "stories": stories,
        "price_last_sold": safe_float("sold_price") or safe_float("last_sold_price"),
        "list_price": safe_float("list_price"),
        "price_per_sqft": safe_float("price_per_sqft"),
        "city": city,
        "state": state,
        "zip_code": str(zip_code),
    }

    # Build source links
    result["source_links"] = {}
    if city and state:
        addr_query = f"{street} {city} {state} {zip_code}".strip()
        result["source_links"]["google_maps"] = f"https://maps.google.com/?q={addr_query.replace(' ', '+')}"

    # Add Zillow/Redfin search links
    if street and city and state:
        addr_slug = f"{street}-{city}-{state}-{zip_code}".replace(" ", "-").replace(",", "")
        result["source_links"]["zillow"] = f"https://www.zillow.com/homes/{addr_slug.replace(' ', '-')}"
        result["source_links"]["redfin"] = f"https://www.redfin.com/search?q={street.replace(' ', '+')}+{city.replace(' ', '+')}+{state}"

    return result


def format_property_for_context(data: Dict) -> str:
    """
    Format property data as context string for the AI prompt.
    This gets injected into the conversation context.
    """
    if not data:
        return ""

    lines = ["PROPERTY DATA (from public records):"]

    if data.get("address_normalized"):
        # Only show city/state for privacy
        city = data.get("city", "")
        state = data.get("state", "")
        if city and state:
            lines.append(f"  Location: {city}, {state}")

    if data.get("property_type") and data["property_type"] != "INDISPONIVEL":
        lines.append(f"  Type: {data['property_type']}")

    if data.get("beds"):
        baths_str = str(data["baths"] or "?")
        if data.get("half_baths"):
            baths_str += f".5"
        lines.append(f"  Size: {data['beds']} bed / {baths_str} bath")

    if data.get("sqft"):
        lines.append(f"  Square Feet: {data['sqft']:,} SF")

    if data.get("year_built"):
        lines.append(f"  Year Built: {data['year_built']}")

    if data.get("stories"):
        lines.append(f"  Stories: {data['stories']}")

    if data.get("lot_sqft"):
        lines.append(f"  Lot Size: {data['lot_sqft']:,} SF")

    if len(lines) <= 1:
        return ""

    return "\n".join(lines)
