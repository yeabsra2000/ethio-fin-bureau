-- Migration: Add embedding column to existing financial_records table
-- Run this in Neon SQL Editor if you get "column financial_records.embedding does not exist" error

-- Add the embedding column (nullable for backward compatibility)
ALTER TABLE financial_records ADD COLUMN IF NOT EXISTS embedding vector(384);

-- Create index for vector similarity search (improves performance)
CREATE INDEX IF NOT EXISTS financial_records_embedding_idx 
ON financial_records USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Verify the column was added
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'financial_records' 
AND column_name = 'embedding';

-- Expected result: 1 row with column_name='embedding', data_type='user-defined'