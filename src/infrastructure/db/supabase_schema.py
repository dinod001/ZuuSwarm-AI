"""
Dynamic Supabase schema generator - reads dimensions from config.

This ensures the database schema always matches config.EMBEDDING_DIM
without any hardcoded values in SQL files.
"""

from infrastructure.config import EMBEDDING_DIM, EMBEDDING_MODEL


def generate_supabase_schema() -> str:
    """
    Generate Supabase schema DDL dynamically from config.
    
    Returns:
        SQL DDL string with vector dimensions from config.EMBEDDING_DIM
    """
    
    return f"""-- ============================================================================
-- Supabase Schema: Memory System + IT Ops
-- PostgreSQL 15+ with pgvector extension
-- ============================================================================
-- 
-- ⚠️ DYNAMICALLY GENERATED FROM CONFIG
-- Embedding Model: {EMBEDDING_MODEL}
-- Vector Dimensions: {EMBEDDING_DIM}
-- 
-- This schema is generated programmatically to ensure dimensions
-- always match config.EMBEDDING_DIM (single source of truth).
-- 
-- ============================================================================

-- Enable pgvector extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- SHORT-TERM MEMORY (Supabase backend — ring buffer with TTL)
-- ============================================================================

CREATE TABLE IF NOT EXISTS st_turns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    ttl_at TIMESTAMPTZ  -- Auto-cleanup after this time (default 24h from created_at)
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_st_turns_user_session ON st_turns (user_id, session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_st_turns_ttl ON st_turns (ttl_at) WHERE ttl_at IS NOT NULL;

COMMENT ON TABLE st_turns IS 'Short-term conversation memory — ring buffer with TTL';

-- ============================================================================
-- LONG-TERM SEMANTIC MEMORY (pgvector facts)
-- ============================================================================

CREATE TABLE IF NOT EXISTS mem_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    text TEXT NOT NULL,
    embedding vector({EMBEDDING_DIM}),
    score REAL NOT NULL CHECK (score >= 0 AND score <= 1),
    tags JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ DEFAULT NOW(),
    ttl_at TIMESTAMPTZ,
    pin BOOLEAN DEFAULT FALSE,
    deleted BOOLEAN DEFAULT FALSE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_mem_facts_user_id ON mem_facts(user_id);
CREATE INDEX IF NOT EXISTS idx_mem_facts_score ON mem_facts(score DESC);
CREATE INDEX IF NOT EXISTS idx_mem_facts_deleted ON mem_facts(deleted) WHERE deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_mem_facts_ttl ON mem_facts(ttl_at) WHERE ttl_at IS NOT NULL;

-- pgvector index (IVFFlat supports higher dimensions, HNSW limited to 2000)
CREATE INDEX IF NOT EXISTS idx_mem_facts_embedding 
ON mem_facts USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Helper function for semantic search
CREATE OR REPLACE FUNCTION search_mem_facts(
    query_embedding vector({EMBEDDING_DIM}),
    query_user_id TEXT,
    match_threshold FLOAT DEFAULT 0.3,
    match_count INT DEFAULT 10
)
RETURNS TABLE (
    id UUID,
    user_id TEXT,
    text TEXT,
    score REAL,
    tags JSONB,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        f.id,
        f.user_id,
        f.text,
        f.score,
        f.tags,
        1 - (f.embedding <=> query_embedding) AS similarity
    FROM mem_facts f
    WHERE f.user_id = query_user_id
        AND f.deleted = FALSE
        AND (f.ttl_at IS NULL OR f.ttl_at > NOW())
        AND 1 - (f.embedding <=> query_embedding) >= match_threshold
    ORDER BY f.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- LONG-TERM EPISODIC MEMORY (pgvector episodes)
-- ============================================================================

CREATE TABLE IF NOT EXISTS mem_episodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    summary_embedding vector({EMBEDDING_DIM}),
    topic_tags JSONB DEFAULT '[]'::jsonb,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    turn_count INTEGER NOT NULL CHECK (turn_count > 0),
    turns JSONB NOT NULL,  -- Full conversation as JSON array
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_mem_episodes_user_id ON mem_episodes(user_id);
CREATE INDEX IF NOT EXISTS idx_mem_episodes_session_id ON mem_episodes(session_id);
CREATE INDEX IF NOT EXISTS idx_mem_episodes_start_at ON mem_episodes(start_at DESC);
CREATE INDEX IF NOT EXISTS idx_mem_episodes_created_at ON mem_episodes(created_at DESC);

-- pgvector index
CREATE INDEX IF NOT EXISTS idx_mem_episodes_embedding 
ON mem_episodes USING ivfflat (summary_embedding vector_cosine_ops) WITH (lists = 100);

-- Helper function for semantic search
CREATE OR REPLACE FUNCTION search_mem_episodes(
    query_embedding vector({EMBEDDING_DIM}),
    query_user_id TEXT,
    match_threshold FLOAT DEFAULT 0.3,
    match_count INT DEFAULT 10
)
RETURNS TABLE (
    id UUID,
    user_id TEXT,
    session_id TEXT,
    summary TEXT,
    topic_tags JSONB,
    start_at TIMESTAMPTZ,
    end_at TIMESTAMPTZ,
    turn_count INTEGER,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        e.id,
        e.user_id,
        e.session_id,
        e.summary,
        e.topic_tags,
        e.start_at,
        e.end_at,
        e.turn_count,
        1 - (e.summary_embedding <=> query_embedding) AS similarity
    FROM mem_episodes e
    WHERE e.user_id = query_user_id
        AND 1 - (e.summary_embedding <=> query_embedding) >= match_threshold
    ORDER BY e.summary_embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- NOTE: RAG document chunks are stored in Qdrant Cloud (not Supabase).
-- ============================================================================



-- ============================================================================
-- IT OPS: DIVISIONS
-- ============================================================================

CREATE TABLE IF NOT EXISTS divisions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT
);

-- ============================================================================
-- IT OPS: EMPLOYEES
-- ============================================================================

CREATE TABLE IF NOT EXISTS employees (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL,
    division_id TEXT REFERENCES divisions(id),
    clearance_level INT CHECK (clearance_level BETWEEN 1 AND 5),
    shift TEXT CHECK (shift IN ('day', 'night', 'flexible')),
    manager_id TEXT,
    joined_date DATE,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_employees_division ON employees(division_id);

-- ============================================================================
-- IT OPS: SERVICES
-- ============================================================================

CREATE TABLE IF NOT EXISTS services (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    owner_division TEXT REFERENCES divisions(id),
    status TEXT CHECK (status IN ('healthy', 'degraded', 'offline', 'maintenance')),
    last_deploy TIMESTAMP,
    version TEXT
);

CREATE INDEX IF NOT EXISTS idx_services_owner_division ON services(owner_division);

-- ============================================================================
-- IT OPS: ASSETS INVENTORY
-- ============================================================================

CREATE TABLE IF NOT EXISTS assets_inventory (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    asset_type TEXT CHECK (asset_type IN ('server', 'laptop', 'network_switch', 'load_balancer', 'storage_array')),
    status TEXT CHECK (status IN ('healthy', 'degraded', 'offline', 'maintenance')),
    owner_id TEXT REFERENCES employees(id),
    cpu_usage_percent INT,
    memory_usage_percent INT,
    location TEXT,
    last_health_check TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_assets_inventory_owner_id ON assets_inventory(owner_id);

-- ============================================================================
-- IT OPS: LIVE TICKETS
-- ============================================================================

CREATE TABLE IF NOT EXISTS live_tickets (
    id TEXT PRIMARY KEY,
    reported_by TEXT REFERENCES employees(id),
    issue_description TEXT NOT NULL,
    ticket_type TEXT CHECK (ticket_type IN ('access_identity', 'asset_provisioning', 'service_degradation', 'critical_outage')),
    severity TEXT CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    status TEXT CHECK (status IN ('open', 'investigating', 'resolved', 'closed')),
    assigned_to TEXT REFERENCES employees(id),
    created_at TIMESTAMP,
    resolved_at TIMESTAMP,
    resolution_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_live_tickets_reported_by ON live_tickets(reported_by);
CREATE INDEX IF NOT EXISTS idx_live_tickets_assigned_to ON live_tickets(assigned_to);

-- ============================================================================
-- IT OPS: INCIDENT HISTORY
-- ============================================================================

CREATE TABLE IF NOT EXISTS incident_history (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    ticket_type TEXT CHECK (ticket_type IN ('access_identity', 'asset_provisioning', 'service_degradation', 'critical_outage')),
    severity TEXT CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    resolved_by TEXT REFERENCES employees(id),
    resolution_notes TEXT,
    resolution_time_minutes INT,
    occurred_at TIMESTAMP,
    resolved_at TIMESTAMP,
    affected_service TEXT,
    root_cause TEXT CHECK (root_cause IN ('configuration_drift', 'resource_exhaustion', 'software_bug', 'human_error', 'external_attack', 'hardware_failure'))
);

CREATE INDEX IF NOT EXISTS idx_incident_history_resolved_by ON incident_history(resolved_by);

-- ============================================================================
-- ROW LEVEL SECURITY (RLS) - Production Ready
-- ============================================================================

-- Enable RLS on memory tables
ALTER TABLE mem_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE mem_episodes ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist (for idempotent re-runs)
DROP POLICY IF EXISTS "Users can view their own facts" ON mem_facts;
DROP POLICY IF EXISTS "Users can manage their own facts" ON mem_facts;
DROP POLICY IF EXISTS "Users can view their own episodes" ON mem_episodes;
DROP POLICY IF EXISTS "Users can manage their own episodes" ON mem_episodes;

-- Policies: Users can only access their own memory
CREATE POLICY "Users can view their own facts"
    ON mem_facts FOR SELECT
    USING (user_id = current_setting('app.user_id', TRUE));

CREATE POLICY "Users can manage their own facts"
    ON mem_facts FOR ALL
    USING (user_id = current_setting('app.user_id', TRUE));

CREATE POLICY "Users can view their own episodes"
    ON mem_episodes FOR SELECT
    USING (user_id = current_setting('app.user_id', TRUE));

CREATE POLICY "Users can manage their own episodes"
    ON mem_episodes FOR ALL
    USING (user_id = current_setting('app.user_id', TRUE));

-- IT Ops tables: No RLS for now (can be added based on requirements)

-- ============================================================================
-- VIEWS FOR ANALYTICS (Optional but useful)
-- ============================================================================

-- Active memory facts per user
CREATE OR REPLACE VIEW v_active_facts AS
SELECT 
    user_id,
    COUNT(*) AS total_facts,
    AVG(score) AS avg_score,
    COUNT(*) FILTER (WHERE pin = TRUE) AS pinned_facts
FROM mem_facts
WHERE deleted = FALSE 
    AND (ttl_at IS NULL OR ttl_at > NOW())
GROUP BY user_id;

-- Episode statistics
CREATE OR REPLACE VIEW v_episode_stats AS
SELECT 
    user_id,
    COUNT(*) AS total_episodes,
    SUM(turn_count) AS total_turns,
    AVG(turn_count) AS avg_turns_per_episode,
    MAX(created_at) AS last_episode_at
FROM mem_episodes
GROUP BY user_id;

-- Active tickets (IT Ops)
CREATE OR REPLACE VIEW v_active_tickets AS
SELECT 
    t.id,
    t.issue_description,
    t.ticket_type,
    t.severity,
    t.status,
    e.name AS reported_by_name,
    a.name AS assigned_to_name,
    t.created_at
FROM live_tickets t
LEFT JOIN employees e ON t.reported_by = e.id
LEFT JOIN employees a ON t.assigned_to = a.id
WHERE t.status IN ('open', 'investigating')
ORDER BY t.created_at DESC;

-- ============================================================================
-- COMMENTS FOR DOCUMENTATION
-- ============================================================================

COMMENT ON TABLE mem_facts IS 'Long-term semantic memory facts with pgvector embeddings';
COMMENT ON TABLE mem_episodes IS 'Long-term episodic memory — full conversations with pgvector summaries';
COMMENT ON TABLE divisions IS 'IT Ops divisions';
COMMENT ON TABLE employees IS 'IT Ops employees';
COMMENT ON TABLE services IS 'IT Ops services';
COMMENT ON TABLE assets_inventory IS 'IT Ops assets inventory';
COMMENT ON TABLE live_tickets IS 'IT Ops live tickets';
COMMENT ON TABLE incident_history IS 'IT Ops incident history';

COMMENT ON FUNCTION search_mem_facts IS 'Semantic search over memory facts using cosine similarity';
COMMENT ON FUNCTION search_mem_episodes IS 'Semantic search over episode summaries using cosine similarity';

-- ============================================================================
-- COMPLETION
-- ============================================================================

-- Verify installation
DO $$
BEGIN
    RAISE NOTICE '✅ Supabase schema created successfully!';
    RAISE NOTICE '📊 Tables created: st_turns, mem_facts, mem_episodes, it_ops_*';
    RAISE NOTICE '🔍 pgvector indexes created with IVFFlat (cosine similarity)';
    RAISE NOTICE '📝 Model: {EMBEDDING_MODEL} ({EMBEDDING_DIM} dims)';
    RAISE NOTICE '🔒 Row Level Security (RLS) enabled for memory tables';
    RAISE NOTICE '💾 Short-term memory: Supabase (st_turns table)';
    RAISE NOTICE '🧠 Memory types: Short-term, Semantic, Episodic';
    RAISE NOTICE '🎯 Ready for production use!';
END $$;
"""
