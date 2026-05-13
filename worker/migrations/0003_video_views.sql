CREATE TABLE video_views (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  token            TEXT    NOT NULL UNIQUE,
  license_key      TEXT    NOT NULL,
  lead_name        TEXT    NOT NULL,
  lead_company     TEXT,
  lead_linkedin_url TEXT,
  video_url        TEXT    NOT NULL,
  created_at       INTEGER NOT NULL,
  clicked_at       INTEGER,
  click_count      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_video_token   ON video_views(token);
CREATE INDEX idx_video_license ON video_views(license_key);
