-- The model that produced an evaluation run's responses. Optional: runs
-- submitted before this column existed, or without a model, stay NULL.
ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS model TEXT;
