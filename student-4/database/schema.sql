CREATE TABLE IF NOT EXISTS markets (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    title               TEXT NOT NULL,
    category            TEXT NOT NULL,
    current_probability REAL NOT NULL,   -- 0..1
    volume              INTEGER NOT NULL,
    close_date          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analyses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id   INTEGER NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
    verdict     TEXT NOT NULL,     -- 'overpriced' | 'underpriced' | 'fair'
    summary     TEXT NOT NULL,
    confidence  REAL DEFAULT 0.5,  -- 0..1
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id   INTEGER REFERENCES markets(id) ON DELETE SET NULL,
    role        TEXT NOT NULL,     -- 'user' | 'assistant'
    content     TEXT NOT NULL,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);
