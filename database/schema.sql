-- ============================================
-- CockroachDB Schema for Support Agent Memory
-- Hackathon: CockroachDB × AWS
-- ============================================

-- Enable pgvector extension (CockroachDB 24.2+)
-- Note: CockroachDB has built-in vector support, no extension needed

-- ============================================
-- Table: users
-- Stores customer information
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================
-- Table: conversations
-- Groups messages into conversation sessions
-- ============================================
CREATE TABLE IF NOT EXISTS conversations (
    conv_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(user_id) ON DELETE CASCADE,
    title VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    status VARCHAR(50) DEFAULT 'active' -- active, resolved, archived
);

-- ============================================
-- Table: messages
-- Stores all user and agent messages with embeddings
-- CRITICAL: Uses VECTOR(1024) for Bedrock Titan Embeddings V2
-- ============================================
CREATE TABLE IF NOT EXISTS messages (
    msg_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conv_id UUID REFERENCES conversations(conv_id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(user_id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    embedding VECTOR(1024), -- Bedrock Titan Embeddings V2 (1024 dimensions)
    created_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb -- confidence scores, retrieval context, etc.
);

-- ============================================
-- Table: user_context
-- Consolidated knowledge about users (semantic memory)
-- ============================================
CREATE TABLE IF NOT EXISTS user_context (
    context_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(user_id) ON DELETE CASCADE,
    context_key VARCHAR(255) NOT NULL, -- e.g., "preferred_language", "past_issues", "product_tier"
    context_value TEXT NOT NULL,
    confidence FLOAT DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1), -- 0.0 to 1.0
    source_msg_id UUID REFERENCES messages(msg_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, context_key)
);

-- ============================================
-- Table: memory_audit
-- Logs every memory retrieval for observability
-- ============================================
CREATE TABLE IF NOT EXISTS memory_audit (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
    query_embedding VECTOR(1024),
    retrieved_msg_ids UUID[],
    retrieval_scores FLOAT[],
    query_text TEXT,
    response_text TEXT,
    retrieval_time_ms INT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================
-- INDEXES FOR PERFORMANCE
-- ============================================

-- Standard B-tree indexes for filtering and joins
CREATE INDEX IF NOT EXISTS idx_messages_conv_id ON messages(conv_id);
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_user_context_user_id ON user_context(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_audit_user_id ON memory_audit(user_id);

-- ============================================
-- 🚀 DISTRIBUTED VECTOR INDEX (Required Hackathon Tool #1)
-- CockroachDB Distributed HNSW Vector Indexing
-- Enables sub-second cosine similarity search at scale
-- ============================================
CREATE INDEX IF NOT EXISTS idx_messages_embedding
ON messages
USING HNSW (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Cosine similarity query pattern:
--   SELECT msg_id, content, (1 - (embedding <=> $1::vector)) AS similarity
--   FROM messages WHERE user_id = $2
--   ORDER BY embedding <=> $1::vector LIMIT 5;

-- ============================================
-- SAMPLE DATA (for testing Phase 0)
-- ============================================

-- Insert test user
INSERT INTO users (user_id, email, name) VALUES 
    ('00000000-0000-0000-0000-000000000001', 'demo@example.com', 'Demo User')
ON CONFLICT (email) DO NOTHING;

-- Insert test conversation
INSERT INTO conversations (conv_id, user_id, title, status) VALUES
    ('00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000001', 'Login Issues', 'active')
ON CONFLICT DO NOTHING;

-- Insert sample messages (without embeddings for now - Phase 1 will add them)
INSERT INTO messages (msg_id, conv_id, user_id, role, content) VALUES
    ('00000000-0000-0000-0000-000000000100', '00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000001', 'user', 'I cannot log in to my dashboard'),
    ('00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000001', 'assistant', 'I can help you with that. What error message are you seeing?'),
    ('00000000-0000-0000-0000-000000000102', '00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000001', 'user', 'It says AUTH_503 timeout error')
ON CONFLICT DO NOTHING;

-- Insert sample user context
INSERT INTO user_context (user_id, context_key, context_value, confidence) VALUES
    ('00000000-0000-0000-0000-000000000001', 'past_issues', 'Login timeout errors (AUTH_503)', 0.95),
    ('00000000-0000-0000-0000-000000000001', 'product_tier', 'Enterprise', 1.0),
    ('00000000-0000-0000-0000-000000000001', 'preferred_contact', 'email', 0.85)
ON CONFLICT (user_id, context_key) DO UPDATE SET
    context_value = EXCLUDED.context_value,
    confidence = EXCLUDED.confidence,
    updated_at = now();

-- ============================================
-- VECTOR SEARCH QUERY PATTERN
-- Use directly in application code (database.py)
-- ============================================
-- SELECT msg_id, content, role, created_at,
--        (1 - (embedding <=> $1::vector))::float AS similarity
-- FROM messages
-- WHERE user_id = $2::uuid
--   AND embedding IS NOT NULL
--   AND (1 - (embedding <=> $1::vector)) > 0.7
-- ORDER BY embedding <=> $1::vector
-- LIMIT 5;

-- ============================================
-- VERIFICATION QUERIES (for testing)
-- ============================================

-- Check tables exist
-- SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';

-- Check vector index exists
-- SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'messages';

-- Check sample data
-- SELECT * FROM users;
-- SELECT * FROM messages;
-- SELECT * FROM user_context;

-- ============================================
-- CLEANUP (use if you need to reset)
-- ============================================
-- DROP TABLE IF EXISTS memory_audit CASCADE;
-- DROP TABLE IF EXISTS user_context CASCADE;
-- DROP TABLE IF EXISTS messages CASCADE;
-- DROP TABLE IF EXISTS conversations CASCADE;
-- DROP TABLE IF EXISTS users CASCADE;
-- DROP FUNCTION IF EXISTS search_similar_messages;
