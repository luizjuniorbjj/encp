-- ============================================
-- ENCP Services Group - Database Schema
-- Single company (NO multi-tenant, NO agency_id)
-- Tile/remodel services: leads, estimates, projects
-- ============================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================
-- TRIGGER: Auto-update updated_at
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- FUNCTION: normalize_text (for memory deduplication)
-- ============================================
CREATE OR REPLACE FUNCTION normalize_text(input_text text) RETURNS text
    LANGUAGE plpgsql IMMUTABLE
    AS $$
BEGIN
    RETURN LOWER(
        REGEXP_REPLACE(
            TRANSLATE(
                input_text,
                'áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ',
                'aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC'
            ),
            '[^a-z0-9 ]', '', 'gi'
        )
    );
END;
$$;

-- ============================================
-- TRIGGER: Auto-normalize memory facts
-- ============================================
CREATE OR REPLACE FUNCTION auto_normalize_fato() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.fato_normalizado := normalize_text(NEW.fato);
    RETURN NEW;
END;
$$;

-- ============================================
-- USERS (NO agency_id)
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    oauth_provider VARCHAR(20),
    oauth_id VARCHAR(255),
    role VARCHAR(20) DEFAULT 'client',  -- admin or client
    is_active BOOLEAN DEFAULT true,
    total_messages INTEGER DEFAULT 0,
    accepted_terms BOOLEAN DEFAULT false,
    accepted_terms_at TIMESTAMPTZ,
    phone VARCHAR(20),
    language VARCHAR(5) DEFAULT 'en',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_login TIMESTAMPTZ
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_phone ON users(phone);
CREATE INDEX idx_users_role ON users(role);

CREATE TRIGGER trigger_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- USER PROFILES
-- ============================================
CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    nome VARCHAR(100),
    phone VARCHAR(20),
    city VARCHAR(100),
    state VARCHAR(2) DEFAULT 'FL',
    zip_code VARCHAR(10),
    address_encrypted BYTEA,  -- Full address encrypted (CRITICAL)
    tom_preferido VARCHAR(30) DEFAULT 'friendly',
    language VARCHAR(5) DEFAULT 'en',
    profile_photo_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TRIGGER trigger_user_profiles_updated_at
    BEFORE UPDATE ON user_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- CONVERSATIONS
-- ============================================
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    last_message_at TIMESTAMPTZ DEFAULT NOW(),
    message_count INTEGER DEFAULT 0,
    resumo TEXT,
    temas JSONB DEFAULT '[]',
    is_archived BOOLEAN DEFAULT false,
    type VARCHAR(20) DEFAULT 'conversation',
    channel VARCHAR(20) DEFAULT 'web',  -- web, whatsapp, phone
    last_client_message_at TIMESTAMPTZ,
    followup_count INTEGER DEFAULT 0,
    followup_status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_conversations_user ON conversations(user_id);
CREATE INDEX idx_conversations_last_message ON conversations(last_message_at DESC);
CREATE INDEX idx_conversations_channel ON conversations(channel);

-- ============================================
-- MESSAGES
-- ============================================
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(10) NOT NULL,  -- user, assistant
    content_encrypted BYTEA NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    model_used VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_user ON messages(user_id);

-- ============================================
-- USER MEMORIES (Tile/remodel-adapted categories)
-- ============================================
CREATE TABLE IF NOT EXISTS user_memories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    categoria VARCHAR(30) NOT NULL,
    -- Categories: IDENTITY, PROPERTY, PROJECT, PREFERENCE, ESTIMATE, SCHEDULE, FEEDBACK, EVENT
    fato TEXT NOT NULL,
    detalhes TEXT,
    importancia INTEGER DEFAULT 5,
    mencoes INTEGER DEFAULT 1,
    confianca FLOAT DEFAULT 0.8,
    status VARCHAR(20) DEFAULT 'active',
    is_active BOOLEAN DEFAULT true,
    validado BOOLEAN DEFAULT false,
    pinned BOOLEAN DEFAULT false,
    fato_normalizado TEXT,
    origem_conversa_id UUID REFERENCES conversations(id),
    semantic_field VARCHAR(50),
    superseded_by UUID REFERENCES user_memories(id),
    ultima_mencao TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_user_memories_user ON user_memories(user_id);
CREATE INDEX idx_user_memories_categoria ON user_memories(categoria);
CREATE INDEX idx_user_memories_status ON user_memories(status);

CREATE TRIGGER trigger_user_memories_updated_at
    BEFORE UPDATE ON user_memories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trigger_user_memories_normalize
    BEFORE INSERT OR UPDATE OF fato ON user_memories
    FOR EACH ROW EXECUTE FUNCTION auto_normalize_fato();

-- ============================================
-- LEADS (Core business — tile/remodel lead pipeline)
-- ============================================
CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    conversation_id UUID REFERENCES conversations(id),
    name VARCHAR(200),
    phone VARCHAR(20),
    email VARCHAR(255),
    address_encrypted BYTEA,  -- Full address encrypted
    city VARCHAR(100),
    state VARCHAR(2) DEFAULT 'FL',
    zip_code VARCHAR(10),
    property_type VARCHAR(30) DEFAULT 'residential',  -- residential, commercial, hoa
    service_type VARCHAR(50),  -- interior, exterior, both, commercial, pressure_wash, drywall, other
    rooms_areas TEXT,  -- Description of rooms/areas
    timeline VARCHAR(30) DEFAULT 'flexible',  -- asap, 1_week, 2_weeks, 1_month, flexible
    budget_range VARCHAR(30),  -- under_1k, 1k_3k, 3k_5k, 5k_10k, 10k_plus, unsure
    sqft_estimate INTEGER,
    status VARCHAR(30) DEFAULT 'new',
    -- Pipeline: new → contacted → estimate_scheduled → estimate_given → accepted → in_progress → completed → closed_lost
    source VARCHAR(20) DEFAULT 'whatsapp',  -- whatsapp, web, referral, phone
    priority VARCHAR(10) DEFAULT 'normal',  -- low, normal, high, urgent
    assigned_to VARCHAR(100),
    notes TEXT,
    loss_reason VARCHAR(200),
    next_followup_at TIMESTAMPTZ,
    followup_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_leads_status ON leads(status);
CREATE INDEX idx_leads_source ON leads(source);
CREATE INDEX idx_leads_created ON leads(created_at DESC);
CREATE INDEX idx_leads_followup ON leads(next_followup_at)
    WHERE status NOT IN ('completed', 'closed_lost');

CREATE TRIGGER trigger_leads_updated_at
    BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- ESTIMATES (Tile/remodel quotes/proposals)
-- ============================================
CREATE TABLE IF NOT EXISTS estimates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    scope_description TEXT,
    rooms_areas JSONB DEFAULT '[]',
    material_type VARCHAR(30),  -- porcelain, ceramic, marble, laminate, hardwood
    prep_work_needed TEXT,
    estimated_hours INTEGER,
    estimated_cost_low DECIMAL(12,2),
    estimated_cost_high DECIMAL(12,2),
    final_quote DECIMAL(12,2),
    status VARCHAR(20) DEFAULT 'draft',  -- draft, sent, accepted, rejected, expired
    valid_until DATE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_estimates_lead ON estimates(lead_id);
CREATE INDEX idx_estimates_status ON estimates(status);

CREATE TRIGGER trigger_estimates_updated_at
    BEFORE UPDATE ON estimates
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- PROJECTS (Active tile/remodel jobs)
-- ============================================
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id UUID REFERENCES leads(id),
    estimate_id UUID REFERENCES estimates(id),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    address_encrypted BYTEA,  -- Full address encrypted
    city VARCHAR(100),
    state VARCHAR(2) DEFAULT 'FL',
    description TEXT,
    stage VARCHAR(30) DEFAULT 'prep',
    -- Stages: scheduled → prep → in_progress → installation → grouting → inspection → completed
    start_date DATE,
    estimated_end_date DATE,
    actual_end_date DATE,
    crew_assigned VARCHAR(200),
    total_cost DECIMAL(12,2),
    payment_status VARCHAR(20) DEFAULT 'pending',  -- pending, partial, paid
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_projects_stage ON projects(stage);
CREATE INDEX idx_projects_lead ON projects(lead_id);

CREATE TRIGGER trigger_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- SERVICE AREAS (ZIP codes served)
-- ============================================
CREATE TABLE IF NOT EXISTS service_areas (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    zip_code VARCHAR(10) UNIQUE NOT NULL,
    city VARCHAR(100),
    county VARCHAR(100),
    state VARCHAR(2) DEFAULT 'FL',
    is_active BOOLEAN DEFAULT true,
    travel_surcharge DECIMAL(8,2) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_service_areas_zip ON service_areas(zip_code);
CREATE INDEX idx_service_areas_active ON service_areas(is_active);

-- ============================================
-- USER PSYCHOLOGICAL PROFILE
-- ============================================
CREATE TABLE IF NOT EXISTS user_psychological_profile (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    communication_style VARCHAR(30),
    processing_style VARCHAR(30),
    primary_needs JSONB DEFAULT '[]',
    emotional_triggers JSONB DEFAULT '[]',
    baseline_anxiety DECIMAL(3,2) DEFAULT 0.30,
    confidence_score DECIMAL(3,2) DEFAULT 0.50,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- LEARNING INTERACTIONS
-- ============================================
CREATE TABLE IF NOT EXISTS learning_interactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES conversations(id),
    strategy_used VARCHAR(50),
    emotion_before VARCHAR(30),
    emotion_after VARCHAR(30),
    response_time_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- AUDIT LOG
-- ============================================
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,
    action VARCHAR(50) NOT NULL,
    ip_address INET,
    user_agent TEXT,
    details JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_log_created ON audit_log(created_at DESC);
CREATE INDEX idx_audit_log_user ON audit_log(user_id);

-- ============================================
-- NOTIFICATIONS
-- ============================================
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    target_audience VARCHAR(20) DEFAULT 'all',
    status VARCHAR(20) DEFAULT 'pending',
    total_recipients INTEGER DEFAULT 0,
    sent_count INTEGER DEFAULT 0,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    sent_at TIMESTAMPTZ
);

-- ============================================
-- PUSH SUBSCRIPTIONS
-- ============================================
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    endpoint TEXT NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- PASSWORD RESET TOKENS
-- ============================================
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(255) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- DEFAULT ADMIN USER (development only)
-- ============================================
-- Create via: python -c "from app.security import hash_password; print(hash_password('admin123'))"
-- Then: INSERT INTO users (email, password_hash, role) VALUES ('admin@encpservices.com', '<hash>', 'admin');

-- ============================================
-- DEFAULT SERVICE AREAS (South Florida)
-- ============================================
INSERT INTO service_areas (zip_code, city, county, state) VALUES
    ('33467', 'Lake Worth', 'Palm Beach', 'FL'),
    ('33442', 'Deerfield Beach', 'Broward', 'FL'),
    ('33432', 'Boca Raton', 'Palm Beach', 'FL'),
    ('33301', 'Fort Lauderdale', 'Broward', 'FL'),
    ('33071', 'Coral Springs', 'Broward', 'FL'),
    ('33327', 'Weston', 'Broward', 'FL'),
    ('33435', 'Boynton Beach', 'Palm Beach', 'FL'),
    ('33444', 'Delray Beach', 'Palm Beach', 'FL'),
    ('33060', 'Pompano Beach', 'Broward', 'FL'),
    ('33317', 'Plantation', 'Broward', 'FL'),
    ('33351', 'Sunrise', 'Broward', 'FL'),
    ('33321', 'Tamarac', 'Broward', 'FL'),
    ('33073', 'Coconut Creek', 'Broward', 'FL'),
    ('33067', 'Parkland', 'Broward', 'FL'),
    ('33063', 'Margate', 'Broward', 'FL'),
    ('33314', 'Davie', 'Broward', 'FL'),
    ('33019', 'Hollywood', 'Broward', 'FL')
ON CONFLICT (zip_code) DO NOTHING;
