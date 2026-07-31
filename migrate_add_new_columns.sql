-- Migration: Add new intelligence columns to existing financial_records table
-- Run this in Neon SQL Editor if you get "column does not exist" errors after deploying
-- This adds the enhanced fields from the new MarketIntelligenceReport schema

-- Add new columns (all nullable for backward compatibility)
ALTER TABLE financial_records ADD COLUMN IF NOT EXISTS event_type VARCHAR(50);
ALTER TABLE financial_records ADD COLUMN IF NOT EXISTS time_horizon VARCHAR(20);
ALTER TABLE financial_records ADD COLUMN IF NOT EXISTS confidence_score FLOAT;
ALTER TABLE financial_records ADD COLUMN IF NOT EXISTS key_metrics TEXT;  -- JSON array
ALTER TABLE financial_records ADD COLUMN IF NOT EXISTS actionable_signals TEXT;  -- JSON array
ALTER TABLE financial_records ADD COLUMN IF NOT EXISTS synthesized_market_impact TEXT;
ALTER TABLE financial_records ADD COLUMN IF NOT EXISTS historical_connections TEXT;  -- JSON array

-- Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_financial_records_event_type 
ON financial_records(event_type);

CREATE INDEX IF NOT EXISTS idx_financial_records_time_horizon 
ON financial_records(time_horizon);

CREATE INDEX IF NOT EXISTS idx_financial_records_confidence_score 
ON financial_records(confidence_score);

-- Verify the columns were added
SELECT column_name, data_type, is_nullable
FROM information_schema.columns 
WHERE table_name = 'financial_records' 
ORDER BY ordinal_position;

-- Expected: 7 new columns added (event_type, time_horizon, confidence_score, 
-- key_metrics, actionable_signals, synthesized_market_impact, historical_connections)