-- ============================================
-- ENCP Services Group - Marketing Automation Tables
-- SEO Monitor, Review Responder, Content Generator
-- ============================================

-- ============================================
-- SEO SEARCH TERMS (terms to track)
-- ============================================
CREATE TABLE IF NOT EXISTS seo_search_terms (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    term VARCHAR(300) NOT NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(2) DEFAULT 'FL',
    target_url VARCHAR(500) DEFAULT 'https://encpservices.com',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_seo_terms_active ON seo_search_terms(is_active);
CREATE INDEX IF NOT EXISTS idx_seo_terms_city ON seo_search_terms(city);

CREATE TRIGGER trigger_seo_terms_updated_at
    BEFORE UPDATE ON seo_search_terms
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- SEO RANKINGS (weekly snapshots)
-- ============================================
CREATE TABLE IF NOT EXISTS seo_rankings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    search_term_id UUID NOT NULL REFERENCES seo_search_terms(id) ON DELETE CASCADE,
    position INTEGER,          -- NULL = not found
    page INTEGER,              -- which page of results
    snippet TEXT,              -- text snippet from search result
    clicks INTEGER DEFAULT 0,
    impressions INTEGER DEFAULT 0,
    ctr NUMERIC(5,4) DEFAULT 0,
    source VARCHAR(20) DEFAULT 'scrape',  -- 'scrape' or 'gsc'
    checked_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_seo_rankings_term ON seo_rankings(search_term_id);
CREATE INDEX IF NOT EXISTS idx_seo_rankings_checked ON seo_rankings(checked_at DESC);

-- ============================================
-- REVIEW RESPONSES (AI-generated)
-- ============================================
CREATE TABLE IF NOT EXISTS review_responses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    platform VARCHAR(50) NOT NULL,      -- google, yelp, facebook
    reviewer_name VARCHAR(200),
    review_text TEXT NOT NULL,
    rating INTEGER,                      -- 1-5
    ai_response TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'draft',  -- draft, approved, posted
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reviews_status ON review_responses(status);
CREATE INDEX IF NOT EXISTS idx_reviews_platform ON review_responses(platform);
CREATE INDEX IF NOT EXISTS idx_reviews_created ON review_responses(created_at DESC);

CREATE TRIGGER trigger_reviews_updated_at
    BEFORE UPDATE ON review_responses
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- MARKETING CONTENT (social media posts)
-- ============================================
CREATE TABLE IF NOT EXISTS marketing_content (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content_type VARCHAR(50) NOT NULL,    -- social_post, blog, caption
    city VARCHAR(100),
    service VARCHAR(100),                 -- interior, exterior, commercial
    platform VARCHAR(50),                 -- instagram, facebook, google
    content_text TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'draft',   -- draft, approved, posted
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_content_status ON marketing_content(status);
CREATE INDEX IF NOT EXISTS idx_content_type ON marketing_content(content_type);
CREATE INDEX IF NOT EXISTS idx_content_created ON marketing_content(created_at DESC);

CREATE TRIGGER trigger_content_updated_at
    BEFORE UPDATE ON marketing_content
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
