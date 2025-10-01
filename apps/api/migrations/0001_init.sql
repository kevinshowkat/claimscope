CREATE TABLE IF NOT EXISTS claims (
  id TEXT PRIMARY KEY,
  model TEXT NOT NULL,
  domain TEXT NOT NULL,
  task TEXT NOT NULL,
  metric TEXT NOT NULL,
  settings JSONB NOT NULL,
  reference_score DOUBLE PRECISION,
  source_url TEXT,
  confidence DOUBLE PRECISION,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  claim_id TEXT REFERENCES claims(id) ON DELETE CASCADE,
  model_config JSONB NOT NULL,
  status TEXT NOT NULL,
  score_value DOUBLE PRECISION,
  ci_lower DOUBLE PRECISION,
  ci_upper DOUBLE PRECISION,
  ops JSONB,
  diffs JSONB,
  status_label TEXT,
  trace_id TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS artifacts (
  id TEXT PRIMARY KEY,
  run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
  name TEXT, url TEXT, sha256 TEXT, bytes BIGINT,
  content_type TEXT, created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS traces (
  id TEXT PRIMARY KEY,
  run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
  harness_cmd TEXT, harness_commit_sha TEXT,
  dataset_id TEXT, dataset_commit_sha TEXT, dataset_hash TEXT,
  docker_image_sha TEXT,
  params JSONB, seeds JSONB,
  tokens_prompt BIGINT, tokens_output BIGINT,
  latency_breakdown JSONB, cost_usd DOUBLE PRECISION,
  errors JSONB, created_at TIMESTAMPTZ DEFAULT now()
);
