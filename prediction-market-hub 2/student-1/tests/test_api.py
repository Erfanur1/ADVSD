import os, sqlite3, importlib, pathlib, tempfile
import pytest

@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "t.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    base = pathlib.Path(__file__).resolve().parent.parent / "database"
    conn = sqlite3.connect(db_path)
    conn.executescript((base / "schema.sql").read_text())
    conn.executescript((base / "seed.sql").read_text())
    conn.commit(); conn.close()
    import backend.app as appmod
    importlib.reload(appmod)
    appmod.app.config.update(TESTING=True)
    return appmod.app.test_client()

def test_health(client):
    assert client.get("/health").status_code == 200

def test_list_markets_seeded(client):
    rows = client.get("/markets").get_json()
    assert len(rows) >= 10          # spec: >=10 records

def test_watchlist_crud(client):
    # Create
    r = client.post("/watchlist", json={"market_id": 1, "note": "x", "priority": 2})
    assert r.status_code == 201
    wid = r.get_json()["id"]
    # Read
    assert any(w["id"] == wid for w in client.get("/watchlist").get_json())
    # Update
    assert client.put(f"/watchlist/{wid}", json={"note": "y", "priority": 5}).status_code == 200
    # Delete
    assert client.delete(f"/watchlist/{wid}").status_code == 200
