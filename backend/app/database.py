"""
ENCPServices - Database Layer
PostgreSQL abstraction via asyncpg — Single company (NO agency_id)
Forked from SegurIA, adapted for tile/remodel domain
"""

import json
from contextlib import asynccontextmanager
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from uuid import UUID

import asyncpg
from app.config import DATABASE_URL
from app.security import encrypt_data, decrypt_data


class UUIDEncoder(json.JSONEncoder):
    """JSON Encoder that supports UUID serialization"""
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


def _uuid(value) -> UUID:
    """Convert string to UUID if needed"""
    return UUID(value) if isinstance(value, str) else value


# ============================================
# MEMORY SYSTEM CONSTANTS
# ============================================

PINNED_CATEGORIES = {"IDENTITY", "PROPERTY", "PROJECT", "PREFERENCE"}

CATEGORY_CAPS = {
    "ESTIMATE": 5,
    "SCHEDULE": 8,
    "FEEDBACK": 10,
    "EVENT": 15,
}

SEMANTIC_CONFLICT_FIELDS = {
    "IDENTITY": {
        "name": ["name", "nome", "my name", "call me"],
        "phone": ["phone", "number", "cell", "telefone"],
        "email": ["email", "e-mail"],
    },
    "PROPERTY": {
        "address": ["address", "live", "house", "home", "property"],
        "type": ["residential", "commercial", "condo", "hoa"],
        "sqft": ["sqft", "square feet", "sq ft", "footage"],
    },
    "PROJECT": {
        "service": ["tile", "floor", "remodel", "bathroom", "kitchen", "backsplash"],
        "timeline": ["when", "deadline", "asap", "week", "month"],
        "rooms": ["room", "bedroom", "bathroom", "kitchen", "living"],
    },
    "PREFERENCE": {
        "color": ["color", "colour", "shade", "tone"],
        "brand": ["brand", "daltile", "marazzi", "mohawk", "porcelanosa"],
        "availability": ["available", "free", "morning", "afternoon", "weekend"],
    },
}


class Database:
    """
    Single-company database abstraction layer.
    NO agency_id filtering — all data belongs to ENCPServices.
    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @asynccontextmanager
    async def _conn(self):
        """Acquire connection from pool"""
        conn = await self.pool.acquire()
        try:
            yield conn
        finally:
            await self.pool.release(conn)

    # ============================================
    # GENERIC DATABASE METHODS
    # ============================================

    async def fetch(self, query: str, *args):
        async with self._conn() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        async with self._conn() as conn:
            return await conn.fetchrow(query, *args)

    async def execute(self, query: str, *args):
        async with self._conn() as conn:
            return await conn.execute(query, *args)

    # ============================================
    # USERS
    # ============================================

    async def create_user(
        self,
        email: str,
        password_hash: Optional[str] = None,
        nome: Optional[str] = None,
        phone: Optional[str] = None,
        oauth_provider: Optional[str] = None,
        oauth_id: Optional[str] = None,
        role: str = "client",
        accepted_terms: bool = False
    ) -> dict:
        async with self._conn() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (
                    email, password_hash, oauth_provider, oauth_id,
                    role, phone, accepted_terms,
                    accepted_terms_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, CASE WHEN $7 THEN NOW() ELSE NULL END)
                RETURNING id, email, role, is_active, created_at
                """,
                email, password_hash, oauth_provider, oauth_id,
                role, phone, accepted_terms
            )
            return dict(row)

    async def get_user_by_email(self, email: str) -> Optional[dict]:
        async with self._conn() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE email = $1",
                email
            )
            return dict(row) if row else None

    async def get_user_by_phone(self, phone: str) -> Optional[dict]:
        async with self._conn() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE phone = $1",
                phone
            )
            return dict(row) if row else None

    async def get_user_by_id(self, user_id: str) -> Optional[dict]:
        async with self._conn() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1",
                _uuid(user_id)
            )
            return dict(row) if row else None

    async def update_last_login(self, user_id: str):
        async with self._conn() as conn:
            await conn.execute(
                "UPDATE users SET last_login = NOW() WHERE id = $1",
                _uuid(user_id)
            )

    async def increment_message_count(self, user_id: str):
        async with self._conn() as conn:
            await conn.execute(
                "UPDATE users SET total_messages = total_messages + 1 WHERE id = $1",
                _uuid(user_id)
            )

    async def update_user_password(self, user_id: str, password_hash: str):
        async with self._conn() as conn:
            await conn.execute(
                "UPDATE users SET password_hash = $2 WHERE id = $1",
                _uuid(user_id), password_hash
            )

    # ============================================
    # USER PROFILES
    # ============================================

    async def create_user_profile(
        self,
        user_id: str,
        nome: Optional[str] = None,
        phone: Optional[str] = None,
        language: str = "en"
    ) -> dict:
        async with self._conn() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO user_profiles (user_id, nome, phone, language, tom_preferido)
                VALUES ($1, $2, $3, $4, 'friendly')
                RETURNING *
                """,
                _uuid(user_id), nome, phone, language
            )
            return dict(row)

    async def get_user_profile(self, user_id: str) -> Optional[dict]:
        async with self._conn() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM user_profiles WHERE user_id = $1",
                _uuid(user_id)
            )
            if not row:
                return None

            profile = dict(row)

            # Decrypt address
            if profile.get("address_encrypted"):
                try:
                    profile["address"] = decrypt_data(profile["address_encrypted"], user_id)
                except Exception:
                    profile["address"] = None
            else:
                profile["address"] = None
            profile.pop("address_encrypted", None)

            return profile

    async def update_user_profile(self, user_id: str, **kwargs) -> dict:
        user_uuid = _uuid(user_id)

        # Encrypt address if provided
        if "address" in kwargs:
            value = kwargs.pop("address")
            if value:
                kwargs["address_encrypted"] = encrypt_data(value, user_id)
            else:
                kwargs["address_encrypted"] = None

        if not kwargs:
            return {}

        set_clauses = []
        values = []
        for i, (key, value) in enumerate(kwargs.items(), 1):
            set_clauses.append(f"{key} = ${i}")
            values.append(value)

        values.append(user_uuid)

        async with self._conn() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE user_profiles
                SET {', '.join(set_clauses)}
                WHERE user_id = ${len(values)}
                RETURNING *
                """,
                *values
            )
            return dict(row) if row else {}

    # ============================================
    # CONVERSATIONS
    # ============================================

    async def create_conversation(
        self,
        user_id: str,
        conv_type: str = "conversation",
        channel: str = "web"
    ) -> dict:
        async with self._conn() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO conversations (user_id, type, channel)
                VALUES ($1, $2, $3)
                RETURNING *
                """,
                _uuid(user_id), conv_type, channel
            )
            return dict(row)

    async def get_active_conversation(self, user_id: str) -> Optional[dict]:
        async with self._conn() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM conversations
                WHERE user_id = $1 AND is_archived = false
                ORDER BY last_message_at DESC LIMIT 1
                """,
                _uuid(user_id)
            )
            return dict(row) if row else None

    async def get_conversations(self, user_id: str, limit: int = 20) -> list:
        async with self._conn() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM conversations
                WHERE user_id = $1
                ORDER BY last_message_at DESC LIMIT $2
                """,
                _uuid(user_id), limit
            )
            return [dict(r) for r in rows]

    async def get_all_conversations(self, limit: int = 50, offset: int = 0) -> list:
        """Admin: get all conversations"""
        async with self._conn() as conn:
            rows = await conn.fetch(
                """
                SELECT c.*, u.email, u.phone, up.nome
                FROM conversations c
                LEFT JOIN users u ON c.user_id = u.id
                LEFT JOIN user_profiles up ON c.user_id = up.user_id
                ORDER BY c.last_message_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit, offset
            )
            return [dict(r) for r in rows]

    async def update_conversation(self, conv_id: str, **kwargs):
        if not kwargs:
            return
        set_clauses = []
        values = []
        for i, (key, value) in enumerate(kwargs.items(), 1):
            set_clauses.append(f"{key} = ${i}")
            values.append(value)
        values.append(_uuid(conv_id))

        async with self._conn() as conn:
            await conn.execute(
                f"UPDATE conversations SET {', '.join(set_clauses)} WHERE id = ${len(values)}",
                *values
            )

    # ============================================
    # MESSAGES
    # ============================================

    async def save_message(
        self,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
        tokens_used: int = 0,
        model_used: str = None
    ) -> dict:
        encrypted_content = encrypt_data(content, user_id)

        async with self._conn() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO messages (conversation_id, user_id, role, content_encrypted, tokens_used, model_used)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, conversation_id, role, tokens_used, created_at
                """,
                _uuid(conversation_id), _uuid(user_id), role,
                encrypted_content, tokens_used, model_used
            )

            # Update conversation
            await conn.execute(
                """
                UPDATE conversations
                SET last_message_at = NOW(),
                    message_count = message_count + 1,
                    last_client_message_at = CASE WHEN $2 = 'user' THEN NOW() ELSE last_client_message_at END
                WHERE id = $1
                """,
                _uuid(conversation_id), role
            )

            return dict(row)

    async def get_messages(self, conversation_id: str, user_id: str, limit: int = 50) -> list:
        async with self._conn() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM messages
                WHERE conversation_id = $1
                ORDER BY created_at ASC LIMIT $2
                """,
                _uuid(conversation_id), limit
            )

            messages = []
            for row in rows:
                msg = dict(row)
                if msg.get("content_encrypted"):
                    msg["content"] = decrypt_data(msg["content_encrypted"], user_id)
                msg.pop("content_encrypted", None)
                messages.append(msg)

            return messages

    # ============================================
    # MEMORIES
    # ============================================

    async def get_user_memories(
        self,
        user_id: str,
        categoria: str = None,
        active_only: bool = True
    ) -> list:
        async with self._conn() as conn:
            if categoria:
                rows = await conn.fetch(
                    """
                    SELECT * FROM user_memories
                    WHERE user_id = $1 AND categoria = $2
                    AND ($3 = false OR (status = 'active' AND is_active = true))
                    ORDER BY pinned DESC, importancia DESC, ultima_mencao DESC
                    """,
                    _uuid(user_id), categoria, active_only
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM user_memories
                    WHERE user_id = $1
                    AND ($2 = false OR (status = 'active' AND is_active = true))
                    ORDER BY pinned DESC, importancia DESC, ultima_mencao DESC
                    """,
                    _uuid(user_id), active_only
                )
            return [dict(r) for r in rows]

    async def save_memory(
        self,
        user_id: str,
        categoria: str,
        fato: str,
        detalhes: str = None,
        importancia: int = 5,
        confianca: float = 0.8,
        origem_conversa_id: str = None,
        semantic_field: str = None
    ) -> dict:
        pinned = categoria in PINNED_CATEGORIES

        async with self._conn() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO user_memories (
                    user_id, categoria, fato, detalhes,
                    importancia, confianca, pinned,
                    origem_conversa_id, semantic_field
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING *
                """,
                _uuid(user_id), categoria, fato, detalhes,
                importancia, confianca, pinned,
                _uuid(origem_conversa_id) if origem_conversa_id else None,
                semantic_field
            )
            return dict(row)

    async def find_duplicate_memory(
        self,
        user_id: str,
        categoria: str,
        fato_normalizado: str
    ) -> Optional[dict]:
        async with self._conn() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM user_memories
                WHERE user_id = $1 AND categoria = $2
                AND fato_normalizado = $3
                AND status = 'active' AND is_active = true
                """,
                _uuid(user_id), categoria, fato_normalizado
            )
            return dict(row) if row else None

    async def find_semantic_conflict(
        self,
        user_id: str,
        categoria: str,
        semantic_field: str
    ) -> Optional[dict]:
        async with self._conn() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM user_memories
                WHERE user_id = $1 AND categoria = $2 AND semantic_field = $3
                AND status = 'active' AND is_active = true
                ORDER BY created_at DESC LIMIT 1
                """,
                _uuid(user_id), categoria, semantic_field
            )
            return dict(row) if row else None

    async def supersede_memory(self, old_memory_id: str, new_memory_id: str):
        async with self._conn() as conn:
            await conn.execute(
                """
                UPDATE user_memories
                SET status = 'superseded', superseded_by = $2, is_active = false
                WHERE id = $1
                """,
                _uuid(old_memory_id), _uuid(new_memory_id)
            )

    async def increment_memory_mention(self, memory_id: str):
        async with self._conn() as conn:
            await conn.execute(
                """
                UPDATE user_memories
                SET mencoes = mencoes + 1, ultima_mencao = NOW()
                WHERE id = $1
                """,
                _uuid(memory_id)
            )

    async def delete_user_memories(self, user_id: str):
        """Delete ALL memories for a user (GDPR/privacy compliance)"""
        async with self._conn() as conn:
            await conn.execute(
                "DELETE FROM user_memories WHERE user_id = $1",
                _uuid(user_id)
            )

    async def enforce_category_cap(self, user_id: str, categoria: str):
        """Enforce cap on scored categories — remove oldest when over cap"""
        cap = CATEGORY_CAPS.get(categoria)
        if not cap:
            return

        async with self._conn() as conn:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM user_memories
                WHERE user_id = $1 AND categoria = $2
                AND status = 'active' AND is_active = true
                """,
                _uuid(user_id), categoria
            )

            if count > cap:
                excess = count - cap
                await conn.execute(
                    """
                    DELETE FROM user_memories
                    WHERE id IN (
                        SELECT id FROM user_memories
                        WHERE user_id = $1 AND categoria = $2
                        AND status = 'active' AND is_active = true
                        AND pinned = false
                        ORDER BY importancia ASC, ultima_mencao ASC
                        LIMIT $3
                    )
                    """,
                    _uuid(user_id), categoria, excess
                )

    # ============================================
    # LEADS
    # ============================================

    async def create_lead(
        self,
        name: str = None,
        phone: str = None,
        email: str = None,
        address: str = None,
        city: str = None,
        state: str = "FL",
        zip_code: str = None,
        property_type: str = "residential",
        service_type: str = None,
        rooms_areas: str = None,
        timeline: str = "flexible",
        budget_range: str = None,
        source: str = "whatsapp",
        user_id: str = None,
        conversation_id: str = None
    ) -> dict:
        address_encrypted = encrypt_data(address, user_id or "") if address else None

        async with self._conn() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO leads (
                    user_id, conversation_id, name, phone, email,
                    address_encrypted, city, state, zip_code,
                    property_type, service_type, rooms_areas,
                    timeline, budget_range, source
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                RETURNING *
                """,
                _uuid(user_id) if user_id else None,
                _uuid(conversation_id) if conversation_id else None,
                name, phone, email,
                address_encrypted, city, state, zip_code,
                property_type, service_type, rooms_areas,
                timeline, budget_range, source
            )
            return dict(row)

    async def get_leads(
        self,
        status: str = None,
        source: str = None,
        limit: int = 50,
        offset: int = 0
    ) -> list:
        async with self._conn() as conn:
            conditions = []
            values = []
            idx = 1

            if status:
                conditions.append(f"status = ${idx}")
                values.append(status)
                idx += 1
            if source:
                conditions.append(f"source = ${idx}")
                values.append(source)
                idx += 1

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            values.extend([limit, offset])
            rows = await conn.fetch(
                f"""
                SELECT * FROM leads {where}
                ORDER BY created_at DESC
                LIMIT ${idx} OFFSET ${idx + 1}
                """,
                *values
            )
            return [dict(r) for r in rows]

    async def get_lead_by_id(self, lead_id: str) -> Optional[dict]:
        async with self._conn() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM leads WHERE id = $1",
                _uuid(lead_id)
            )
            return dict(row) if row else None

    async def update_lead(self, lead_id: str, **kwargs) -> dict:
        if "address" in kwargs:
            value = kwargs.pop("address")
            if value:
                kwargs["address_encrypted"] = encrypt_data(value, str(lead_id))
            else:
                kwargs["address_encrypted"] = None

        if not kwargs:
            return {}

        set_clauses = []
        values = []
        for i, (key, value) in enumerate(kwargs.items(), 1):
            set_clauses.append(f"{key} = ${i}")
            values.append(value)
        values.append(_uuid(lead_id))

        async with self._conn() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE leads SET {', '.join(set_clauses)}
                WHERE id = ${len(values)}
                RETURNING *
                """,
                *values
            )
            return dict(row) if row else {}

    async def get_lead_pipeline(self) -> dict:
        """Get lead counts by status for pipeline view"""
        async with self._conn() as conn:
            rows = await conn.fetch(
                """
                SELECT status, COUNT(*) as count
                FROM leads
                GROUP BY status
                ORDER BY
                    CASE status
                        WHEN 'new' THEN 1
                        WHEN 'contacted' THEN 2
                        WHEN 'estimate_scheduled' THEN 3
                        WHEN 'estimate_given' THEN 4
                        WHEN 'accepted' THEN 5
                        WHEN 'in_progress' THEN 6
                        WHEN 'completed' THEN 7
                        WHEN 'closed_lost' THEN 8
                    END
                """
            )
            return {str(r["status"]): r["count"] for r in rows}

    async def get_lead_stats(self) -> dict:
        """Get lead statistics"""
        async with self._conn() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM leads")
            this_week = await conn.fetchval(
                "SELECT COUNT(*) FROM leads WHERE created_at >= NOW() - INTERVAL '7 days'"
            )
            converted = await conn.fetchval(
                "SELECT COUNT(*) FROM leads WHERE status IN ('accepted', 'in_progress', 'completed')"
            )
            return {
                "total": total,
                "this_week": this_week,
                "converted": converted,
                "conversion_rate": round(converted / total * 100, 1) if total > 0 else 0
            }

    # ============================================
    # ESTIMATES
    # ============================================

    async def create_estimate(
        self,
        lead_id: str,
        user_id: str = None,
        scope_description: str = None,
        rooms_areas: list = None,
        material_type: str = None,
        prep_work_needed: str = None,
        estimated_hours: int = None,
        estimated_cost_low: float = None,
        estimated_cost_high: float = None,
        notes: str = None
    ) -> dict:
        async with self._conn() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO estimates (
                    lead_id, user_id, scope_description, rooms_areas,
                    material_type, prep_work_needed, estimated_hours,
                    estimated_cost_low, estimated_cost_high, notes
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING *
                """,
                _uuid(lead_id),
                _uuid(user_id) if user_id else None,
                scope_description,
                json.dumps(rooms_areas or [], cls=UUIDEncoder),
                material_type, prep_work_needed, estimated_hours,
                estimated_cost_low, estimated_cost_high, notes
            )
            return dict(row)

    async def get_estimates(self, lead_id: str = None, status: str = None, limit: int = 50) -> list:
        async with self._conn() as conn:
            conditions = []
            values = []
            idx = 1

            if lead_id:
                conditions.append(f"lead_id = ${idx}")
                values.append(_uuid(lead_id))
                idx += 1
            if status:
                conditions.append(f"status = ${idx}")
                values.append(status)
                idx += 1

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            values.append(limit)

            rows = await conn.fetch(
                f"SELECT * FROM estimates {where} ORDER BY created_at DESC LIMIT ${idx}",
                *values
            )
            return [dict(r) for r in rows]

    async def get_estimate_by_id(self, estimate_id: str) -> Optional[dict]:
        async with self._conn() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM estimates WHERE id = $1",
                _uuid(estimate_id)
            )
            return dict(row) if row else None

    async def update_estimate(self, estimate_id: str, **kwargs) -> dict:
        if not kwargs:
            return {}

        set_clauses = []
        values = []
        for i, (key, value) in enumerate(kwargs.items(), 1):
            set_clauses.append(f"{key} = ${i}")
            values.append(value)
        values.append(_uuid(estimate_id))

        async with self._conn() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE estimates SET {', '.join(set_clauses)}
                WHERE id = ${len(values)}
                RETURNING *
                """,
                *values
            )
            return dict(row) if row else {}

    # ============================================
    # PROJECTS
    # ============================================

    async def create_project(
        self,
        lead_id: str = None,
        estimate_id: str = None,
        user_id: str = None,
        address: str = None,
        city: str = None,
        state: str = "FL",
        description: str = None,
        start_date: date = None,
        estimated_end_date: date = None,
        crew_assigned: str = None,
        total_cost: float = None
    ) -> dict:
        address_encrypted = encrypt_data(address, user_id or "") if address else None

        async with self._conn() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO projects (
                    lead_id, estimate_id, user_id,
                    address_encrypted, city, state, description,
                    start_date, estimated_end_date, crew_assigned, total_cost
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING *
                """,
                _uuid(lead_id) if lead_id else None,
                _uuid(estimate_id) if estimate_id else None,
                _uuid(user_id) if user_id else None,
                address_encrypted, city, state, description,
                start_date, estimated_end_date, crew_assigned, total_cost
            )
            return dict(row)

    async def get_projects(self, stage: str = None, limit: int = 50) -> list:
        async with self._conn() as conn:
            if stage:
                rows = await conn.fetch(
                    "SELECT * FROM projects WHERE stage = $1 ORDER BY created_at DESC LIMIT $2",
                    stage, limit
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM projects ORDER BY created_at DESC LIMIT $1",
                    limit
                )
            return [dict(r) for r in rows]

    async def get_active_projects(self) -> list:
        async with self._conn() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM projects
                WHERE stage NOT IN ('completed')
                ORDER BY start_date ASC
                """
            )
            return [dict(r) for r in rows]

    async def get_project_by_id(self, project_id: str) -> Optional[dict]:
        async with self._conn() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM projects WHERE id = $1",
                _uuid(project_id)
            )
            return dict(row) if row else None

    async def update_project(self, project_id: str, **kwargs) -> dict:
        if "address" in kwargs:
            value = kwargs.pop("address")
            if value:
                kwargs["address_encrypted"] = encrypt_data(value, str(project_id))

        if not kwargs:
            return {}

        set_clauses = []
        values = []
        for i, (key, value) in enumerate(kwargs.items(), 1):
            set_clauses.append(f"{key} = ${i}")
            values.append(value)
        values.append(_uuid(project_id))

        async with self._conn() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE projects SET {', '.join(set_clauses)}
                WHERE id = ${len(values)}
                RETURNING *
                """,
                *values
            )
            return dict(row) if row else {}

    # ============================================
    # SERVICE AREAS
    # ============================================

    async def check_service_area(self, zip_code: str) -> Optional[dict]:
        async with self._conn() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM service_areas WHERE zip_code = $1 AND is_active = true",
                zip_code
            )
            return dict(row) if row else None

    async def get_service_areas(self) -> list:
        async with self._conn() as conn:
            rows = await conn.fetch(
                "SELECT * FROM service_areas WHERE is_active = true ORDER BY city"
            )
            return [dict(r) for r in rows]

    # ============================================
    # ADMIN / DASHBOARD
    # ============================================

    async def get_dashboard_stats(self) -> dict:
        async with self._conn() as conn:
            leads_week = await conn.fetchval(
                "SELECT COUNT(*) FROM leads WHERE created_at >= NOW() - INTERVAL '7 days'"
            )
            active_projects = await conn.fetchval(
                "SELECT COUNT(*) FROM projects WHERE stage NOT IN ('completed')"
            )
            total_conversations = await conn.fetchval(
                "SELECT COUNT(*) FROM conversations WHERE created_at >= NOW() - INTERVAL '30 days'"
            )
            total_leads = await conn.fetchval("SELECT COUNT(*) FROM leads")
            converted = await conn.fetchval(
                "SELECT COUNT(*) FROM leads WHERE status IN ('accepted', 'in_progress', 'completed')"
            )

            return {
                "leads_this_week": leads_week,
                "active_projects": active_projects,
                "conversations_30d": total_conversations,
                "total_leads": total_leads,
                "converted_leads": converted,
                "conversion_rate": round(converted / total_leads * 100, 1) if total_leads > 0 else 0
            }

    async def search_customers(self, query: str, limit: int = 20) -> list:
        async with self._conn() as conn:
            search = f"%{query}%"
            rows = await conn.fetch(
                """
                SELECT u.id, u.email, u.phone, u.created_at,
                       up.nome, up.city, up.state
                FROM users u
                LEFT JOIN user_profiles up ON u.id = up.user_id
                WHERE u.role = 'client'
                AND (
                    u.email ILIKE $1
                    OR u.phone ILIKE $1
                    OR up.nome ILIKE $1
                )
                ORDER BY u.created_at DESC
                LIMIT $2
                """,
                search, limit
            )
            return [dict(r) for r in rows]

    # ============================================
    # PSYCHOLOGICAL PROFILE
    # ============================================

    async def get_psychological_profile(self, user_id: str) -> Optional[dict]:
        async with self._conn() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM user_psychological_profile WHERE user_id = $1",
                _uuid(user_id)
            )
            return dict(row) if row else None

    async def upsert_psychological_profile(self, user_id: str, **kwargs) -> dict:
        async with self._conn() as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM user_psychological_profile WHERE user_id = $1",
                _uuid(user_id)
            )

            if existing:
                set_clauses = []
                values = []
                for i, (key, value) in enumerate(kwargs.items(), 1):
                    set_clauses.append(f"{key} = ${i}")
                    values.append(value if not isinstance(value, (list, dict)) else json.dumps(value, cls=UUIDEncoder))
                values.append(_uuid(user_id))

                row = await conn.fetchrow(
                    f"""
                    UPDATE user_psychological_profile
                    SET {', '.join(set_clauses)}
                    WHERE user_id = ${len(values)}
                    RETURNING *
                    """,
                    *values
                )
            else:
                row = await conn.fetchrow(
                    """
                    INSERT INTO user_psychological_profile (user_id, communication_style, processing_style)
                    VALUES ($1, $2, $3)
                    RETURNING *
                    """,
                    _uuid(user_id),
                    kwargs.get("communication_style", "neutral"),
                    kwargs.get("processing_style", "balanced")
                )

            return dict(row) if row else {}

    # ============================================
    # LEARNING INTERACTIONS
    # ============================================

    async def save_learning_interaction(
        self,
        user_id: str,
        conversation_id: str,
        strategy_used: str,
        emotion_before: str = None,
        emotion_after: str = None,
        response_time_ms: int = None
    ):
        async with self._conn() as conn:
            await conn.execute(
                """
                INSERT INTO learning_interactions (
                    user_id, conversation_id, strategy_used,
                    emotion_before, emotion_after, response_time_ms
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                _uuid(user_id), _uuid(conversation_id), strategy_used,
                emotion_before, emotion_after, response_time_ms
            )

    # ============================================
    # AUDIT LOG
    # ============================================

    async def log_audit(
        self,
        user_id: str = None,
        action: str = "",
        details: dict = None,
        ip_address: str = None,
        user_agent: str = None
    ):
        async with self._conn() as conn:
            await conn.execute(
                """
                INSERT INTO audit_log (user_id, action, details, ip_address, user_agent)
                VALUES ($1, $2, $3, $4, $5)
                """,
                _uuid(user_id) if user_id else None,
                action,
                json.dumps(details or {}, cls=UUIDEncoder),
                ip_address,
                user_agent
            )

    # ============================================
    # PASSWORD RESET
    # ============================================

    async def save_reset_token(self, user_id: str, token: str, expires_at: datetime):
        async with self._conn() as conn:
            await conn.execute(
                """
                INSERT INTO password_reset_tokens (user_id, token, expires_at)
                VALUES ($1, $2, $3)
                """,
                _uuid(user_id), token, expires_at
            )

    async def verify_reset_token(self, token: str) -> Optional[dict]:
        async with self._conn() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM password_reset_tokens
                WHERE token = $1 AND expires_at > NOW() AND used_at IS NULL
                """,
                token
            )
            return dict(row) if row else None

    async def use_reset_token(self, token: str):
        async with self._conn() as conn:
            await conn.execute(
                "UPDATE password_reset_tokens SET used_at = NOW() WHERE token = $1",
                token
            )

    # ============================================
    # DATA EXPORT (Privacy compliance)
    # ============================================

    async def export_user_data(self, user_id: str) -> dict:
        """Export all user data for privacy compliance"""
        uid = _uuid(user_id)
        async with self._conn() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE id = $1", uid)
            profile = await conn.fetchrow("SELECT * FROM user_profiles WHERE user_id = $1", uid)
            memories = await conn.fetch(
                "SELECT * FROM user_memories WHERE user_id = $1 AND is_active = true", uid
            )
            conversations = await conn.fetch("SELECT * FROM conversations WHERE user_id = $1", uid)

        return {
            "user": dict(user) if user else None,
            "profile": dict(profile) if profile else None,
            "memories": [dict(m) for m in memories],
            "conversations": [dict(c) for c in conversations],
            "exported_at": datetime.utcnow().isoformat()
        }

    # ============================================
    # ALIASES (for ai_service.py compatibility)
    # ============================================

    async def get_conversation_messages(self, conversation_id: str, user_id: str, limit: int = 50) -> list:
        """Alias for get_messages"""
        return await self.get_messages(conversation_id, user_id, limit)

    async def get_conversation(self, conversation_id: str, user_id: str = None) -> Optional[dict]:
        """Get a single conversation by ID (optionally filtered by user_id)"""
        async with self._conn() as conn:
            if user_id:
                row = await conn.fetchrow(
                    "SELECT * FROM conversations WHERE id = $1 AND user_id = $2",
                    _uuid(conversation_id), _uuid(user_id)
                )
            else:
                row = await conn.fetchrow(
                    "SELECT * FROM conversations WHERE id = $1",
                    _uuid(conversation_id)
                )
            return dict(row) if row else None

    async def update_conversation_summary(self, conversation_id: str, summary: str):
        """Update conversation summary/resumo"""
        await self.update_conversation(conversation_id, resumo=summary)

    async def get_psychological_context(self, user_id: str) -> str:
        """Get formatted psychological context string for AI prompt"""
        profile = await self.get_psychological_profile(user_id)
        if not profile:
            return ""
        parts = []
        if profile.get("communication_style"):
            parts.append(f"Communication: {profile['communication_style']}")
        if profile.get("processing_style"):
            parts.append(f"Processing: {profile['processing_style']}")
        if profile.get("emotional_tendency"):
            parts.append(f"Emotional tendency: {profile['emotional_tendency']}")
        if profile.get("decision_style"):
            parts.append(f"Decision style: {profile['decision_style']}")
        return ", ".join(parts) if parts else ""

    async def get_all_memories_formatted(
        self, user_id: str, current_message: str = "", top_k: int = 20
    ) -> str:
        """Get all active memories formatted as a string for the AI prompt"""
        memories = await self.get_user_memories(user_id, active_only=True)
        if not memories:
            return ""

        # Sort by importance (pinned first, then by importance score)
        pinned_cats = {"IDENTITY", "PROPERTY", "PROJECT", "PREFERENCE"}
        pinned = [m for m in memories if m.get("categoria", "").upper() in pinned_cats]
        scored = [m for m in memories if m.get("categoria", "").upper() not in pinned_cats]

        # Sort scored by importance descending
        scored.sort(key=lambda m: m.get("importancia", 0), reverse=True)

        selected = pinned + scored[:top_k - len(pinned)]

        lines = ["CLIENT MEMORIES:"]
        for m in selected:
            cat = m.get("categoria", "?")
            fato = m.get("fato", "")
            if fato:
                lines.append(f"[{cat}] {fato}")

        return "\n".join(lines) if len(lines) > 1 else ""

    async def save_insight(self, user_id: str, insight_type: str, content: str, **kwargs):
        """Save a client insight (stored as a high-importance memory)"""
        await self.save_memory(
            user_id=user_id,
            categoria="EVENT",
            fato=f"[{insight_type}] {content}",
            detalhes=kwargs.get("details", ""),
            importancia=kwargs.get("importance", 7),
            confianca=kwargs.get("confidence", 0.8)
        )

    async def save_psychological_profile(self, user_id: str, **kwargs):
        """Alias for upsert_psychological_profile"""
        return await self.upsert_psychological_profile(user_id, **kwargs)


# ============================================
# CONNECTION POOL
# ============================================

_pool: Optional[asyncpg.Pool] = None
_db: Optional[Database] = None


async def init_db():
    """Initialize database connection pool"""
    global _pool, _db
    _pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,
        max_size=10,
        command_timeout=30
    )
    _db = Database(_pool)
    print(f"[DB] Pool created: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else 'local'}")


async def close_db():
    """Close database connection pool"""
    global _pool, _db
    if _pool:
        await _pool.close()
        _pool = None
        _db = None


async def get_db() -> Database:
    """FastAPI dependency — returns Database instance"""
    if not _db:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db
