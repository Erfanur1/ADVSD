"""Create the SQLite DB from schema.sql + seed.sql (idempotent-ish)."""
import os, sqlite3, pathlib

DB_PATH = os.getenv("DB_PATH", "/data/student1.db")
HERE = pathlib.Path(__file__).resolve().parent.parent / "database"

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
conn = sqlite3.connect(DB_PATH)
conn.executescript((HERE / "schema.sql").read_text())
# Only seed if empty
count = conn.execute("SELECT COUNT(*) FROM markets").fetchone()[0]
if count == 0:
    conn.executescript((HERE / "seed.sql").read_text())
    print("seeded")
else:
    print(f"already has {count} markets; skipping seed")
conn.commit()
conn.close()
