CREATE TABLE IF NOT EXISTS categories (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS markets (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    title               TEXT NOT NULL,
    category            TEXT NOT NULL,
    current_probability REAL NOT NULL,   -- 0..1
    volume              INTEGER NOT NULL,
    close_date          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id   INTEGER NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
    note        TEXT DEFAULT '',
    priority    INTEGER DEFAULT 0,
    added_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
