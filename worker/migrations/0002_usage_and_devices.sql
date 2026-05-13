-- Influentia 1.0 — usage caps + device caps
-- Adds two tables. Run with:
--   wrangler d1 execute outreach-pilot-db --remote --file=./migrations/0002_usage_and_devices.sql

-- Per-license token usage, bucketed by day (YYYY-MM-DD) and month (YYYY-MM).
-- Each Anthropic-proxied call records the input + output tokens it consumed.
-- We enforce a daily cap (default 1M tokens) and a monthly cap (default 3M).
CREATE TABLE IF NOT EXISTS license_usage (
  license_key   TEXT    NOT NULL,
  period_key    TEXT    NOT NULL,   -- e.g. '2026-05-01' or '2026-05'
  period_type   TEXT    NOT NULL,   -- 'day' or 'month'
  tokens_in     INTEGER NOT NULL DEFAULT 0,
  tokens_out    INTEGER NOT NULL DEFAULT 0,
  request_count INTEGER NOT NULL DEFAULT 0,
  updated_at    INTEGER NOT NULL,
  PRIMARY KEY (license_key, period_key, period_type)
);

CREATE INDEX IF NOT EXISTS idx_license_usage_lookup
  ON license_usage(license_key, period_type, period_key);

-- Per-license active device tracking. Each Influentia install generates a
-- stable device_id (local UUID) and registers it on first license validate.
-- We allow up to 3 distinct device_ids per license to prevent casual sharing
-- without punishing legitimate "I have a laptop and a desktop" usage.
CREATE TABLE IF NOT EXISTS license_devices (
  license_key   TEXT    NOT NULL,
  device_id     TEXT    NOT NULL,
  device_name   TEXT,                -- optional, hostname or "Mac · Apple Silicon"
  first_seen_at INTEGER NOT NULL,
  last_seen_at  INTEGER NOT NULL,
  PRIMARY KEY (license_key, device_id)
);

CREATE INDEX IF NOT EXISTS idx_license_devices_key
  ON license_devices(license_key);
