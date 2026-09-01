"""Create the SQLite DB from schema.sql + seed.sql (idempotent-ish)."""
import os, sqlite3, pathlib
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "/data/student3.db")
HERE = pathlib.Path(__file__).resolve().parent.parent / "database"

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
conn = sqlite3.connect(DB_PATH)
conn.executescript((HERE / "schema.sql").read_text())
# Only seed if empty
count = conn.execute("SELECT COUNT(*) FROM news_articles").fetchone()[0]
if count == 0:
    conn.executescript((HERE / "seed.sql").read_text())
    print("seeded")
else:
    print(f"already has {count} articles; skipping seed")
conn.commit()
conn.close()
