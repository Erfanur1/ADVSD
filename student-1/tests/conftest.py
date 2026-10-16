import sqlite3
import importlib
import pathlib

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Flask test client backed by a fresh, seeded SQLite database."""
    db_path = tmp_path / "t.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    base = pathlib.Path(__file__).resolve().parent.parent / "database"
    conn = sqlite3.connect(db_path)
    conn.executescript((base / "schema.sql").read_text())
    conn.executescript((base / "seed.sql").read_text())
    conn.commit()
    conn.close()
    import backend.app as appmod
    importlib.reload(appmod)
    appmod.app.config.update(TESTING=True)
    return appmod.app.test_client()