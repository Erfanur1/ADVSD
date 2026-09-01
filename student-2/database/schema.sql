-- TODO(Student 2): define tables for "Portfolio & Position Tracker" (>=3 tables, >=10 rows each). See student-1/database/schema.sql.
CREATE TABLE IF NOT EXISTS portfolios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    currency TEXT DEFAULT 'USD'
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER,
    market_ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price REAL NOT NULL,
    size INTEGER NOT NULL,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
);

CREATE TABLE IF NOT EXISTS trade_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER,
    trade_type TEXT,
    shares INTEGER,
    price REAL,
    FOREIGN KEY (position_id) REFERENCES positions(id)
);