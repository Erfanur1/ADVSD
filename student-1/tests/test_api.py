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

def test_mcp_search_disabled_in_ci_gracefully(monkeypatch):
    # In CI, no live MCP server is running, so this should return a
    # clean, structured fallback -- not a crash. This IS the
    # "disabled during CI/CD" behaviour required by the R1 spec.
    monkeypatch.setenv("MCP_URL", "http://localhost:9999")
    import backend.app as appmod
    importlib.reload(appmod)
    client = appmod.app.test_client()

    r = client.post("/mcp/search", json={"query": "election"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["markets"] == []
    assert any(step["stage"] == "Adapt" for step in body["agentic_trace"])

def test_rag_ask_disabled_in_ci_gracefully(monkeypatch):
    monkeypatch.setenv("RAG_URL", "http://localhost:9998")
    import backend.app as appmod
    importlib.reload(appmod)
    client = appmod.app.test_client()

    r = client.post("/rag/ask", json={"question": "whats trending"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["insufficient_context"] is True
    assert "unavailable" in body["answer"].lower()