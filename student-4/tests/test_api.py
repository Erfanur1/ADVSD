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

def test_list_markets_seeded(client):
    rows = client.get("/markets").get_json()
    assert len(rows) >= 10          # spec: >=10 records

def test_list_analyses_seeded(client):
    rows = client.get("/analyses").get_json()
    assert len(rows) >= 10

def test_list_chat_seeded(client):
    rows = client.get("/chat").get_json()
    assert len(rows) >= 10

def test_market_crud(client):
    r = client.post("/markets", json={
        "title": "Test market", "category": "Test",
        "current_probability": 0.5, "volume": 1000, "close_date": "2027-01-01",
    })
    assert r.status_code == 201
    mid = r.get_json()["id"]
    assert client.get(f"/markets/{mid}").status_code == 200
    assert client.put(f"/markets/{mid}", json={"volume": 2000}).status_code == 200
    assert client.delete(f"/markets/{mid}").status_code == 200
    assert client.get(f"/markets/{mid}").status_code == 404

def test_analysis_crud(client):
    r = client.post("/analyses", json={"market_id": 1, "verdict": "fair", "summary": "x"})
    assert r.status_code == 201
    aid = r.get_json()["id"]
    assert any(a["id"] == aid for a in client.get("/analyses").get_json())
    assert client.put(f"/analyses/{aid}", json={"verdict": "overpriced"}).status_code == 200
    assert client.delete(f"/analyses/{aid}").status_code == 200

def test_ai_analyze_falls_back_when_ai_mode_unreachable(client):
    r = client.post("/ai/analyze", json={"market_id": 1})
    assert r.status_code == 200
    data = r.get_json()
    assert "output" in data and "agentic_trace" in data
    stages = [t["stage"] for t in data["agentic_trace"]]
    assert stages[:3] == ["Plan", "Act", "Observe"]
