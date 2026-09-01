CREATE TABLE IF NOT EXISTS sources (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL UNIQUE,
    reliability_score   REAL NOT NULL   -- 0..1
);

CREATE TABLE IF NOT EXISTS news_articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    headline        TEXT NOT NULL,
    source_id       INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    category        TEXT NOT NULL,
    published_date  TEXT NOT NULL,
    summary         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id  INTEGER NOT NULL REFERENCES news_articles(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    content     TEXT DEFAULT '',
    tags        TEXT DEFAULT '',
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);
