"""
Blog Service - AI-powered blog generation using GPT-4o-mini
Generates SEO-optimized blog posts for tile/floor/remodel contractor niche
"""

import json
import re
import uuid
from datetime import datetime, timezone
from openai import AsyncOpenAI

from app.config import OPENAI_API_KEY
from app.database import get_db

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

BLOG_GENERATION_PROMPT = """You are a content writer for ENCP Services Group, a tile and flooring contractor in Boca Raton, FL.

VOICE: Write as Eusebio and Tulio — experienced, direct, proud of their craft. Not corporate. Not generic. Like a trusted contractor talking to a neighbor. Use "we" — this is written from ENCP's perspective.

Company info:
- Name: ENCP Services Group
- Owners: Eusebio and Tulio
- Phone: (561) 506-7035
- Location: Boca Raton, FL (serves Boca Raton, Delray Beach, Fort Lauderdale, Pompano Beach, Coral Springs, Coconut Creek, Weston, Deerfield Beach)
- Services: Tile Installation, Floor Installation, Bathroom Remodel, Kitchen Remodel, Backsplash, Laminate/Hardwood Flooring
- 16+ years experience, licensed and insured
- 5.0 star rating on Thumbtack (20 reviews, 100% 5-star)
- Free estimates, Mon-Sat 8AM-6PM
- Languages: English, Spanish, Portuguese

CONTENT TYPE: {content_type}

If content_type is "article":
  Write a standard blog post about: {topic}

If content_type is "podcast-interview":
  Write a WRITTEN PODCAST-STYLE INTERVIEW between Eusebio (ENCP owner) and a specialist/expert from a construction materials manufacturer (tile, grout, waterproofing, etc.). Format as Q&A dialogue. The interview should showcase:
  - Quality materials with warranty
  - Why pros choose specific brands
  - Real-world installation tips from Florida experience
  - How the right materials protect Florida homes from humidity/moisture
  Topic: {topic}

Target city (if applicable): {city}
Target service (if applicable): {service}
Target keywords: {keywords}

RULES:
- Mention at least 2 specific neighborhoods/areas in the target city
- Reference South Florida climate/humidity at least once
- Include one real problem/solution from tile/flooring work in Florida
- Include one specific price range for the local market
- Never use: "In conclusion", "It is important to note", "In today's world", "Look no further"
- No fluff. Every sentence earns its place.
- 800-1000 words
- Include H2 and H3 subheadings
- Include a CTA at the end with phone number (561) 506-7035
- Do NOT use markdown - use HTML tags (<h2>, <h3>, <p>, <ul>, <li>, <strong>)

Return ONLY a JSON object:
{{
    "title": "SEO-optimized title (50-60 chars)",
    "meta_description": "Compelling meta description (150-160 chars)",
    "content": "<h2>...</h2><p>...</p>...",
    "excerpt": "Brief 1-2 sentence summary for blog listing",
    "category": "one of: tips, guides, cost, seasonal, maintenance, trends, podcast",
    "tags": ["tag1", "tag2", "tag3"],
    "suggested_slug": "url-friendly-slug"
}}"""

# ============================================
# Auto-generate topics: 1 article per city+service (matches landing pages)
# + podcast interviews
# ============================================

_CITIES = ['Boca Raton', 'Delray Beach', 'Fort Lauderdale', 'Pompano Beach', 'Coral Springs', 'Coconut Creek', 'Weston', 'Deerfield Beach']

_SERVICES = {
    'Tile Installation': {
        'topic': 'Tile Installation in {city}: Costs, Tips, and What to Expect',
        'keywords': 'tile installation {city_lower}, tile contractor {city_lower}, floor tile {city_lower}',
        'service': 'Tile Installation',
    },
    'Bathroom Remodel': {
        'topic': 'Bathroom Remodel in {city}: Ideas, Costs, and Expert Advice',
        'keywords': 'bathroom remodel {city_lower}, bathroom renovation {city_lower}, bathroom contractor {city_lower}',
        'service': 'Bathroom Remodel',
    },
    'Kitchen Remodel': {
        'topic': 'Kitchen Remodel in {city}: Design Ideas and Cost Guide',
        'keywords': 'kitchen remodel {city_lower}, kitchen renovation {city_lower}, kitchen contractor {city_lower}',
        'service': 'Kitchen Remodel',
    },
}

# Build city+service topics dynamically (24 articles)
TOPIC_IDEAS = []
for city in _CITIES:
    city_lower = city.lower().replace(' ', '-')
    for svc_name, svc_data in _SERVICES.items():
        TOPIC_IDEAS.append({
            "topic": svc_data['topic'].format(city=city),
            "city": city,
            "service": svc_data['service'],
            "category": "guides",
            "keywords": svc_data['keywords'].format(city_lower=city_lower),
        })

# General articles (not city-specific, broader reach)
TOPIC_IDEAS += [
    {"topic": "How Much Does Tile Installation Cost in South Florida?", "category": "cost", "keywords": "tile installation cost florida, tile price per sqft, tile estimate"},
    {"topic": "Porcelain vs Ceramic Tile: Which Is Better for Florida Homes?", "category": "tips", "keywords": "porcelain vs ceramic, tile types, best tile florida"},
    {"topic": "Best Flooring Options for Florida's Humid Climate", "category": "tips", "keywords": "best flooring florida, humidity resistant flooring, florida floor options"},
    {"topic": "10 Signs Your Bathroom Needs a Remodel", "category": "tips", "keywords": "bathroom remodel signs, when to remodel bathroom, bathroom renovation"},
    {"topic": "How to Choose the Perfect Kitchen Backsplash", "category": "tips", "keywords": "kitchen backsplash ideas, backsplash tile, kitchen tile design"},
    {"topic": "Grout Maintenance Guide: Keep Your Tile Looking New", "category": "maintenance", "keywords": "grout maintenance, grout cleaning, grout sealing"},
    {"topic": "2026 Tile Trends: Popular Styles for South Florida Homes", "category": "trends", "keywords": "tile trends 2026, popular tile styles, modern tile design"},
    {"topic": "Hardwood vs Laminate vs Tile: Cost Comparison for Florida Homes", "category": "cost", "keywords": "flooring cost comparison, hardwood vs laminate cost, tile vs wood cost"},
]

# Podcast-style interviews (manufacturer experts)
TOPIC_IDEAS += [
    {"topic": "Interview: Choosing the Right Porcelain Tile for Florida Humidity", "category": "podcast", "content_type": "podcast-interview", "keywords": "porcelain tile florida, moisture resistant tile, tile for humid climate"},
    {"topic": "Interview: Waterproof Grout Technology - What Every Homeowner Should Know", "category": "podcast", "content_type": "podcast-interview", "keywords": "waterproof grout, grout technology, grout for showers"},
    {"topic": "Interview: Large Format Tile Installation - Expert Tips from a Tile Manufacturer", "category": "podcast", "content_type": "podcast-interview", "keywords": "large format tile, big tile installation, modern tile"},
    {"topic": "Interview: Natural Stone vs Porcelain - A Materials Expert Breaks It Down", "category": "podcast", "content_type": "podcast-interview", "keywords": "natural stone vs porcelain, marble tile, stone flooring"},
    {"topic": "Interview: Best Underlayment and Waterproofing for Florida Bathrooms", "category": "podcast", "content_type": "podcast-interview", "keywords": "bathroom waterproofing, underlayment tile, shower waterproofing"},
    {"topic": "Interview: LVP vs Hardwood vs Tile - Which Floor Wins in South Florida?", "category": "podcast", "content_type": "podcast-interview", "keywords": "LVP flooring, hardwood vs tile, best floor florida"},
]


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')[:100]


async def generate_blog_post(
    topic: str = None,
    city: str = None,
    service: str = None,
    keywords: str = None,
    content_type: str = "article",
    auto_publish: bool = False
) -> dict:
    """Generate a blog post using GPT-4o-mini"""

    # If no topic provided, pick next from ideas list
    if not topic:
        db = await get_db()
        existing = await db.fetch("SELECT slug FROM blog_posts")
        existing_slugs = {r['slug'] for r in existing}

        for idea in TOPIC_IDEAS:
            slug = _slugify(idea['topic'])
            if slug not in existing_slugs:
                topic = idea['topic']
                city = idea.get('city', city)
                keywords = idea.get('keywords', keywords)
                content_type = idea.get('content_type', 'article')
                break
        else:
            return {"error": "All pre-defined topics have been generated. Provide a custom topic."}

    prompt = BLOG_GENERATION_PROMPT.format(
        topic=topic,
        city=city or "Boca Raton",
        service=service or "General tile and flooring services",
        keywords=keywords or topic.lower(),
        content_type=content_type,
    )

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=3000,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    data = json.loads(raw)

    slug = _slugify(data.get('suggested_slug', '') or data['title'])
    status = 'published' if auto_publish else 'draft'
    published_at = datetime.now(timezone.utc) if auto_publish else None

    db = await get_db()
    row = await db.fetchrow("""
        INSERT INTO blog_posts (slug, title, meta_description, content, excerpt, category, tags, city, service, status, ai_model, ai_prompt, published_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        ON CONFLICT (slug) DO UPDATE SET
            slug = blog_posts.slug || '-' || substr(gen_random_uuid()::text, 1, 4)
        RETURNING id, slug, title, status, created_at
    """,
        slug,
        data['title'],
        data.get('meta_description', ''),
        data['content'],
        data.get('excerpt', ''),
        data.get('category', 'tips'),
        data.get('tags', []),
        city,
        service,
        status,
        'gpt-4o-mini',
        topic,
        published_at,
    )

    return {
        "id": str(row['id']),
        "slug": row['slug'],
        "title": row['title'],
        "status": row['status'],
        "created_at": row['created_at'].isoformat(),
        "tokens_used": response.usage.total_tokens,
        "cost_estimate": f"${response.usage.total_tokens * 0.00000015:.4f}",
    }


async def generate_batch(count: int = 5, auto_publish: bool = False) -> list:
    """Generate multiple blog posts at once"""
    results = []
    for i in range(count):
        try:
            result = await generate_blog_post(auto_publish=auto_publish)
            if "error" in result:
                results.append(result)
                break
            results.append(result)
        except Exception as e:
            results.append({"error": str(e), "post_number": i + 1})
    return results


async def list_posts(status: str = None, limit: int = 50, offset: int = 0) -> list:
    """List blog posts with optional status filter"""
    db = await get_db()
    if status:
        rows = await db.fetch(
            "SELECT id, slug, title, excerpt, category, city, service, status, views, published_at, created_at "
            "FROM blog_posts WHERE status = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            status, limit, offset
        )
    else:
        rows = await db.fetch(
            "SELECT id, slug, title, excerpt, category, city, service, status, views, published_at, created_at "
            "FROM blog_posts ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset
        )
    return [dict(r) for r in rows]


async def get_post(slug: str) -> dict:
    """Get a single blog post by slug, increment views"""
    db = await get_db()
    row = await db.fetchrow(
        "UPDATE blog_posts SET views = views + 1 WHERE slug = $1 "
        "RETURNING id, slug, title, meta_description, content, excerpt, featured_image, "
        "category, tags, city, service, status, views, published_at, created_at",
        slug
    )
    if not row:
        return None
    return dict(row)


async def update_post(post_id: str, updates: dict) -> dict:
    """Update a blog post (title, content, status, etc.)"""
    db = await get_db()
    allowed = ['title', 'content', 'meta_description', 'excerpt', 'category', 'tags', 'status', 'slug', 'featured_image']
    sets = []
    values = []
    idx = 1

    for key, val in updates.items():
        if key in allowed:
            sets.append(f"{key} = ${idx}")
            values.append(val)
            idx += 1

    if 'status' in updates and updates['status'] == 'published':
        sets.append(f"published_at = ${idx}")
        values.append(datetime.now(timezone.utc))
        idx += 1

    if not sets:
        return {"error": "No valid fields to update"}

    values.append(uuid.UUID(post_id))
    query = f"UPDATE blog_posts SET {', '.join(sets)} WHERE id = ${idx} RETURNING id, slug, title, status"
    row = await db.fetchrow(query, *values)
    if not row:
        return {"error": "Post not found"}
    return dict(row)


async def delete_post(post_id: str) -> bool:
    """Delete a blog post"""
    db = await get_db()
    result = await db.execute("DELETE FROM blog_posts WHERE id = $1", uuid.UUID(post_id))
    return "DELETE 1" in result


async def get_stats() -> dict:
    """Blog statistics for admin dashboard"""
    db = await get_db()
    stats = await db.fetchrow("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status = 'published') as published,
            COUNT(*) FILTER (WHERE status = 'draft') as drafts,
            COALESCE(SUM(views), 0) as total_views
        FROM blog_posts
    """)
    return dict(stats)


async def get_topic_suggestions() -> list:
    """Return unused topic ideas"""
    db = await get_db()
    existing = await db.fetch("SELECT ai_prompt FROM blog_posts WHERE ai_prompt IS NOT NULL")
    used_topics = {r['ai_prompt'] for r in existing}

    available = []
    for idea in TOPIC_IDEAS:
        if idea['topic'] not in used_topics:
            available.append(idea)
    return available
