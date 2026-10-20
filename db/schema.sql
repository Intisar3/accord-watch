-- accord-watch database schema (SQLite)

CREATE TABLE IF NOT EXISTS listings (
    id              TEXT PRIMARY KEY,          -- "<site>:<site_listing_id>"
    site            TEXT NOT NULL,
    site_listing_id TEXT NOT NULL,
    url             TEXT NOT NULL,
    title           TEXT,
    price_omr       REAL,
    location        TEXT,
    posted_at       TEXT,
    description     TEXT,
    seller_name     TEXT,
    phone_hash      TEXT,                      -- sha256 of digits only, used to link listings by the same seller
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',   -- active | gone
    duplicate_of    TEXT,                      -- id of the main listing when the same car is posted twice
    content_hash    TEXT,                      -- changes when price, text or photos change
    attrs           TEXT NOT NULL DEFAULT '{}' -- JSON: extracted + inferred fields, pricer + ranker outputs
);

CREATE TABLE IF NOT EXISTS price_history (
    listing_id TEXT NOT NULL,
    day        TEXT NOT NULL,
    price_omr  REAL,
    PRIMARY KEY (listing_id, day)
);

CREATE TABLE IF NOT EXISTS photos (
    listing_id TEXT NOT NULL,
    idx        INTEGER NOT NULL,
    url        TEXT NOT NULL,
    local_path TEXT,
    sha256     TEXT,
    ahash      TEXT,                           -- 64-bit average hash (hex) for near-duplicate detection
    PRIMARY KEY (listing_id, idx)
);

CREATE TABLE IF NOT EXISTS findings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id   TEXT NOT NULL,
    stage        TEXT NOT NULL,                -- text | visual | crosscheck | inference | price | archive
    severity     TEXT NOT NULL,                -- info | warn | critical
    kind         TEXT,                         -- e.g. mileage_mismatch, repaint, vague_claim, reused_photo
    field        TEXT,
    claim        TEXT,                         -- what the ad says
    evidence     TEXT,                         -- what was observed / reasoning
    confidence   REAL,                         -- 0..1
    content_hash TEXT,
    created      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stage_runs (
    listing_id   TEXT NOT NULL,
    stage        TEXT NOT NULL,
    content_hash TEXT,
    day          TEXT NOT NULL,
    PRIMARY KEY (listing_id, stage)
);

CREATE TABLE IF NOT EXISTS scores (
    listing_id TEXT NOT NULL,
    day        TEXT NOT NULL,
    total      REAL,
    parts      TEXT,                           -- JSON breakdown
    rank       INTEGER,
    PRIMARY KEY (listing_id, day)
);

CREATE TABLE IF NOT EXISTS runs (
    day     TEXT PRIMARY KEY,
    summary TEXT                               -- JSON written by the Reporter
);
