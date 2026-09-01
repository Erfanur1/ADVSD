import os, sqlite3, importlib, pathlib
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

def test_list_news_seeded(client):
    rows = client.get("/news").get_json()
    assert len(rows) >= 10          # spec: >=10 records

def test_list_sources_seeded(client):
    rows = client.get("/sources").get_json()
    assert len(rows) >= 10

def test_notes_crud(client):
    # Create
    r = client.post("/notes", json={"article_id": 1, "title": "x", "content": "y", "tags": "t"})
    assert r.status_code == 201
    nid = r.get_json()["id"]
    # Read
    assert any(n["id"] == nid for n in client.get("/notes").get_json())
    # Update
    assert client.put(f"/notes/{nid}", json={"title": "x2", "content": "y2", "tags": "t2"}).status_code == 200
    # Delete
    assert client.delete(f"/notes/{nid}").status_code == 200
