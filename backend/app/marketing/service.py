"""
ENCPServices - Marketing Service
SEO monitoring, review responses, content generation
"""

import json
import logging
import re
from typing import Optional, List, Dict
from datetime import datetime, timedelta, date
from uuid import UUID

import httpx
import anthropic

from app.config import ANTHROPIC_API_KEY, AI_MODEL_PRIMARY, GSC_CREDENTIALS_JSON, GSC_SITE_URL
from app.database import Database
from app.prompts.marketing import REVIEW_RESPONSE_PROMPT, CONTENT_GENERATION_PROMPT

logger = logging.getLogger("encp.marketing")


class MarketingService:
    """Marketing automation: SEO, reviews, content generation."""

    def __init__(self, db: Database):
        self.db = db
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # ============================================
    # AI CALL HELPER
    # ============================================

    def _call_claude(self, system: str, user_message: str, max_tokens: int = 1000) -> str:
        """Call Claude and return response text."""
        response = self.client.messages.create(
            model=AI_MODEL_PRIMARY,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}]
        )
        return response.content[0].text

    # ============================================
    # SEO MONITOR
    # ============================================

    async def add_search_term(self, term: str, city: str, state: str = "FL") -> dict:
        """Add a search term to track."""
        async with self.db._conn() as conn:
            row = await conn.fetchrow(
                """INSERT INTO seo_search_terms (term, city, state)
                   VALUES ($1, $2, $3) RETURNING *""",
                term, city, state
            )
            return _serialize_row(row)

    async def get_search_terms(self, active_only: bool = True) -> List[dict]:
        """Get all tracked search terms."""
        async with self.db._conn() as conn:
            if active_only:
                rows = await conn.fetch(
                    "SELECT * FROM seo_search_terms WHERE is_active = true ORDER BY city, term"
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM seo_search_terms ORDER BY city, term"
                )
            return [_serialize_row(r) for r in rows]

    async def delete_search_term(self, term_id: str) -> bool:
        """Delete a search term."""
        async with self.db._conn() as conn:
            result = await conn.execute(
                "DELETE FROM seo_search_terms WHERE id = $1",
                UUID(term_id)
            )
            return result == "DELETE 1"

    async def check_ranking(self, term_id: str) -> dict:
        """Check Google ranking for a specific search term."""
        async with self.db._conn() as conn:
            term_row = await conn.fetchrow(
                "SELECT * FROM seo_search_terms WHERE id = $1", UUID(term_id)
            )
            if not term_row:
                return {"error": "Term not found"}

            query = f"{term_row['term']} {term_row['city']} {term_row['state']}"
            position, page, snippet = await self._search_google(query, term_row['target_url'])

            row = await conn.fetchrow(
                """INSERT INTO seo_rankings (search_term_id, position, page, snippet)
                   VALUES ($1, $2, $3, $4) RETURNING *""",
                UUID(term_id), position, page, snippet
            )
            return {
                "term": term_row['term'],
                "city": term_row['city'],
                "position": position,
                "page": page,
                "snippet": snippet,
                "checked_at": row['checked_at'].isoformat() if row else None
            }

    async def check_all_rankings(self) -> Dict:
        """Check rankings — uses GSC if available, falls back to scraping."""
        if GSC_CREDENTIALS_JSON:
            try:
                return await self.sync_from_gsc()
            except Exception as e:
                logger.error(f"[SEO] GSC sync failed, falling back to scrape: {e}")

        # Fallback: scraping
        terms = await self.get_search_terms(active_only=True)
        results = []
        alerts = []

        for term in terms:
            result = await self.check_ranking(term["id"])
            results.append(result)

            drop = await self._check_ranking_drop(term["id"])
            if drop:
                alerts.append(drop)

        return {
            "checked": len(results),
            "results": results,
            "alerts": alerts,
            "source": "scrape",
            "checked_at": datetime.utcnow().isoformat()
        }

    # ============================================
    # GOOGLE SEARCH CONSOLE
    # ============================================

    def _get_gsc_service(self):
        """Create authenticated Google Search Console API service."""
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds_data = json.loads(GSC_CREDENTIALS_JSON)
        credentials = service_account.Credentials.from_service_account_info(
            creds_data,
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
        )
        return build("searchconsole", "v1", credentials=credentials)

    async def sync_from_gsc(self) -> Dict:
        """Sync SEO data from Google Search Console API."""
        import asyncio

        if not GSC_CREDENTIALS_JSON:
            return {"error": "GSC credentials not configured", "checked": 0}

        service = await asyncio.to_thread(self._get_gsc_service)

        # Query last 28 days, grouped by query
        end_date = date.today()
        start_date = end_date - timedelta(days=28)

        request_body = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "dimensions": ["query"],
            "rowLimit": 1000
        }

        response = await asyncio.to_thread(
            lambda: service.searchanalytics().query(
                siteUrl=GSC_SITE_URL,
                body=request_body
            ).execute()
        )

        gsc_rows = response.get("rows", [])
        logger.info(f"[SEO] GSC returned {len(gsc_rows)} query rows")

        # Get tracked terms
        terms = await self.get_search_terms(active_only=True)
        results = []
        matched = 0

        # Build lookup: normalize GSC queries for matching
        gsc_lookup = {}
        for row in gsc_rows:
            query = row["keys"][0].lower().strip()
            gsc_lookup[query] = {
                "clicks": row.get("clicks", 0),
                "impressions": row.get("impressions", 0),
                "ctr": round(row.get("ctr", 0), 4),
                "position": round(row.get("position", 0), 1)
            }

        async with self.db._conn() as conn:
            for term in terms:
                search_key = f"{term['term']} {term['city']} {term.get('state', 'FL')}".lower()
                # Try exact match first, then partial
                data = gsc_lookup.get(search_key)
                if not data:
                    # Try matching just the term
                    data = gsc_lookup.get(term["term"].lower())
                if not data:
                    # Try fuzzy: any GSC query containing both term and city
                    term_lower = term["term"].lower()
                    city_lower = term["city"].lower()
                    for q, d in gsc_lookup.items():
                        if term_lower in q and city_lower in q:
                            data = d
                            break
                if not data:
                    # Try just term match
                    term_lower = term["term"].lower()
                    for q, d in gsc_lookup.items():
                        if term_lower in q:
                            data = d
                            break

                if data:
                    matched += 1
                    position = int(data["position"]) if data["position"] else None
                    page = ((position - 1) // 10 + 1) if position else None

                    await conn.fetchrow(
                        """INSERT INTO seo_rankings
                           (search_term_id, position, page, clicks, impressions, ctr, source)
                           VALUES ($1, $2, $3, $4, $5, $6, 'gsc') RETURNING id""",
                        UUID(term["id"]), position, page,
                        data["clicks"], data["impressions"], data["ctr"]
                    )

                    results.append({
                        "term": term["term"],
                        "city": term["city"],
                        "position": position,
                        "page": page,
                        "clicks": data["clicks"],
                        "impressions": data["impressions"],
                        "ctr": data["ctr"]
                    })
                else:
                    results.append({
                        "term": term["term"],
                        "city": term["city"],
                        "position": None,
                        "clicks": 0,
                        "impressions": 0,
                        "ctr": 0
                    })

        return {
            "checked": len(terms),
            "matched": matched,
            "gsc_queries": len(gsc_rows),
            "results": results,
            "source": "gsc",
            "checked_at": datetime.utcnow().isoformat()
        }

    async def get_seo_dashboard(self) -> Dict:
        """Get SEO dashboard with latest rankings and trends."""
        async with self.db._conn() as conn:
            # Latest ranking per term
            rows = await conn.fetch("""
                SELECT DISTINCT ON (st.id)
                    st.id, st.term, st.city, st.state, st.is_active,
                    sr.position, sr.page, sr.snippet, sr.checked_at,
                    sr.clicks, sr.impressions, sr.ctr, sr.source
                FROM seo_search_terms st
                LEFT JOIN seo_rankings sr ON sr.search_term_id = st.id
                WHERE st.is_active = true
                ORDER BY st.id, sr.checked_at DESC NULLS LAST
            """)

            rankings = []
            total_clicks = 0
            total_impressions = 0
            for r in rows:
                clicks = r["clicks"] or 0
                impressions = r["impressions"] or 0
                total_clicks += clicks
                total_impressions += impressions
                item = {
                    "term_id": str(r["id"]),
                    "term": r["term"],
                    "city": r["city"],
                    "position": r["position"],
                    "page": r["page"],
                    "clicks": clicks,
                    "impressions": impressions,
                    "ctr": float(r["ctr"]) if r["ctr"] else 0,
                    "source": r["source"] or "scrape",
                    "last_checked": r["checked_at"].isoformat() if r["checked_at"] else None
                }
                rankings.append(item)

            # Summary stats
            found = [r for r in rankings if r["position"] is not None]
            first_page = [r for r in found if r["page"] == 1]
            avg_position = round(sum(r["position"] for r in found) / len(found), 1) if found else None

            return {
                "total_terms": len(rankings),
                "terms_found": len(found),
                "first_page": len(first_page),
                "total_clicks": total_clicks,
                "total_impressions": total_impressions,
                "avg_position": avg_position,
                "gsc_connected": bool(GSC_CREDENTIALS_JSON),
                "rankings": rankings
            }

    async def _check_ranking_drop(self, term_id: str) -> Optional[dict]:
        """Check if ranking dropped compared to previous check."""
        async with self.db._conn() as conn:
            rows = await conn.fetch(
                """SELECT position, checked_at FROM seo_rankings
                   WHERE search_term_id = $1
                   ORDER BY checked_at DESC LIMIT 2""",
                UUID(term_id)
            )
            if len(rows) < 2:
                return None

            current = rows[0]["position"]
            previous = rows[1]["position"]

            if current is None and previous is not None:
                return {"term_id": term_id, "alert": "disappeared", "previous": previous}
            if current and previous and current > previous + 5:
                return {
                    "term_id": term_id,
                    "alert": "dropped",
                    "previous": previous,
                    "current": current,
                    "drop": current - previous
                }
            return None

    async def _search_google(self, query: str, target_url: str) -> tuple:
        """
        Search Google and find target URL position.
        Returns (position, page, snippet) or (None, None, None) if not found.
        """
        import re

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Referer": "https://www.google.com/",
        }
        domain = target_url.replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://www.google.com/search",
                    params={"q": query, "num": 20, "hl": "en", "gl": "us"},
                    headers=headers,
                    follow_redirects=True
                )
                if resp.status_code != 200:
                    logger.warning(f"[SEO] Google returned {resp.status_code} for: {query}")
                    return None, None, None

                text = resp.text

                # Multiple URL extraction patterns
                urls = []

                # Pattern 1: /url?q= redirects
                urls.extend(re.findall(r'/url\?q=(https?://[^"&]+)', text))

                # Pattern 2: data-href attributes
                if not urls:
                    urls.extend(re.findall(r'data-href="(https?://[^"]+)"', text))

                # Pattern 3: cite tags (Google shows URL in green text)
                if not urls:
                    urls.extend(re.findall(r'<cite[^>]*>(https?://[^<]+)</cite>', text))
                    urls.extend(re.findall(r'<cite[^>]*>([^<]+)</cite>', text))

                # Pattern 4: Generic href with domain filtering
                if not urls:
                    all_hrefs = re.findall(r'href="(https?://(?!www\.google|accounts\.google|support\.google|maps\.google|policies\.google|consent\.google)[^"]+)"', text)
                    urls.extend(all_hrefs)

                # Deduplicate while preserving order
                seen = set()
                unique_urls = []
                for u in urls:
                    normalized = u.lower().split("?")[0].rstrip("/")
                    if normalized not in seen:
                        seen.add(normalized)
                        unique_urls.append(u)

                # Find target domain
                for i, url in enumerate(unique_urls, 1):
                    if domain in url.lower():
                        position = i
                        page = (i - 1) // 10 + 1
                        return position, page, None

                # Fallback: check raw text for domain mention
                if domain in text.lower():
                    logger.info(f"[SEO] Domain '{domain}' found in HTML but not in parsed results for: {query}")

                return None, None, None

        except Exception as e:
            logger.error(f"[SEO] Search error for '{query}': {e}")
            return None, None, None

    # ============================================
    # REVIEW RESPONDER
    # ============================================

    async def generate_review_response(
        self,
        platform: str,
        review_text: str,
        rating: int,
        reviewer_name: str = "Customer",
        created_by: Optional[str] = None
    ) -> dict:
        """Generate AI response to a customer review."""
        user_message = (
            f"Platform: {platform}\n"
            f"Reviewer: {reviewer_name}\n"
            f"Rating: {rating}/5 stars\n"
            f"Review: {review_text}\n\n"
            f"Write a professional response to this review."
        )

        ai_response = self._call_claude(REVIEW_RESPONSE_PROMPT, user_message, max_tokens=500)

        async with self.db._conn() as conn:
            row = await conn.fetchrow(
                """INSERT INTO review_responses
                   (platform, reviewer_name, review_text, rating, ai_response, created_by)
                   VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
                platform, reviewer_name, review_text, rating, ai_response,
                UUID(created_by) if created_by else None
            )
            return _serialize_row(row)

    async def get_review_responses(
        self, status: Optional[str] = None, limit: int = 50
    ) -> List[dict]:
        """Get generated review responses."""
        async with self.db._conn() as conn:
            if status:
                rows = await conn.fetch(
                    """SELECT * FROM review_responses
                       WHERE status = $1
                       ORDER BY created_at DESC LIMIT $2""",
                    status, limit
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM review_responses ORDER BY created_at DESC LIMIT $1",
                    limit
                )
            return [_serialize_row(r) for r in rows]

    async def update_review_status(self, review_id: str, status: str) -> Optional[dict]:
        """Update review response status (draft -> approved -> posted)."""
        async with self.db._conn() as conn:
            row = await conn.fetchrow(
                """UPDATE review_responses SET status = $1
                   WHERE id = $2 RETURNING *""",
                status, UUID(review_id)
            )
            return _serialize_row(row) if row else None

    # ============================================
    # CONTENT GENERATOR
    # ============================================

    async def generate_content(
        self,
        content_type: str,
        city: str,
        service: str,
        platform: str,
        created_by: Optional[str] = None
    ) -> dict:
        """Generate social media content."""
        user_message = (
            f"Content type: {content_type}\n"
            f"Platform: {platform}\n"
            f"City: {city}, FL\n"
            f"Service: {service}\n\n"
            f"Generate a {content_type} for {platform} about {service} services in {city}."
        )

        content_text = self._call_claude(CONTENT_GENERATION_PROMPT, user_message, max_tokens=800)

        async with self.db._conn() as conn:
            row = await conn.fetchrow(
                """INSERT INTO marketing_content
                   (content_type, city, service, platform, content_text, created_by)
                   VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
                content_type, city, service, platform, content_text,
                UUID(created_by) if created_by else None
            )
            return _serialize_row(row)

    async def get_content(
        self, status: Optional[str] = None, content_type: Optional[str] = None, limit: int = 50
    ) -> List[dict]:
        """Get generated marketing content."""
        async with self.db._conn() as conn:
            conditions = []
            params = []
            idx = 1

            if status:
                conditions.append(f"status = ${idx}")
                params.append(status)
                idx += 1
            if content_type:
                conditions.append(f"content_type = ${idx}")
                params.append(content_type)
                idx += 1

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            params.append(limit)

            rows = await conn.fetch(
                f"SELECT * FROM marketing_content {where} ORDER BY created_at DESC LIMIT ${idx}",
                *params
            )
            return [_serialize_row(r) for r in rows]

    async def update_content_status(self, content_id: str, status: str) -> Optional[dict]:
        """Update content status (draft -> approved -> posted)."""
        async with self.db._conn() as conn:
            row = await conn.fetchrow(
                """UPDATE marketing_content SET status = $1
                   WHERE id = $2 RETURNING *""",
                status, UUID(content_id)
            )
            return _serialize_row(row) if row else None


# ============================================
# HELPERS
# ============================================

def _serialize_row(row) -> dict:
    """Convert asyncpg Record to JSON-serializable dict."""
    if not row:
        return {}
    result = dict(row)
    for key, value in result.items():
        if isinstance(value, UUID):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
    return result
