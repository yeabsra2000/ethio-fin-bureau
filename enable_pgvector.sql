-- Enable pgvector extension in Neon PostgreSQL
-- Run this in Neon's SQL editor or via psql

-- Create the pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify the extension is installed
SELECT * FROM pg_extension WHERE extname = 'vector';

-- Create a function to match the similarity search in database.py
CREATE OR REPLACE FUNCTION match_financial_records(
    query_embedding vector(384),
    match_threshold float,
    match_count int
)
RETURNS TABLE (
    id int,
    headline text,
    executive_summary text,
    sentiment text,
    impact_level text,
    created_at timestamptz,
    similarity float
)
LANGUAGE sql STABLE
AS $$
    SELECT
        financial_records.id,
        financial_records.headline,
        financial_records.executive_summary,
        financial_records.sentiment,
        financial_records.impact_level,
        financial_records.created_at,
        1 - (financial_records.embedding <=> query_embedding) AS similarity
    FROM financial_records
    WHERE financial_records.embedding IS NOT NULL
      AND 1 - (financial_records.embedding <=> query_embedding) > match_threshold
    ORDER BY financial_records.embedding <=> query_embedding
    LIMIT match_count;
$$;

-- Grant permissions (if needed)
GRANT USAGE ON SCHEMA public TO neondb_owner;
GRANT ALL ON ALL TABLES IN SCHEMA public TO neondb_owner;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO neondb_owner;