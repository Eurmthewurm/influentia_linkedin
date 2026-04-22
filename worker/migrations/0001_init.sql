CREATE TABLE licenses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT NOT NULL UNIQUE,
  email TEXT NOT NULL,
  stripe_customer_id TEXT,
  stripe_subscription_id TEXT,
  stripe_checkout_session_id TEXT,
  tier TEXT NOT NULL DEFAULT 'trial',
  trial_ends_at INTEGER,
  current_period_end INTEGER,
  subscription_status TEXT,
  created_at INTEGER NOT NULL,
  last_seen_at INTEGER
);

CREATE INDEX idx_licenses_stripe_sub ON licenses(stripe_subscription_id);
CREATE INDEX idx_licenses_email ON licenses(email);
CREATE INDEX idx_licenses_session ON licenses(stripe_checkout_session_id);
CREATE INDEX idx_licenses_key ON licenses(key);
