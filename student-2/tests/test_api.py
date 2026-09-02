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

def test_list_portfolios_seeded(client):
    rows = client.get("/portfolios").get_json()
    assert len(rows) >= 10          # spec: >=10 records

def test_list_positions_seeded(client):
    rows = client.get("/positions").get_json()
    assert len(rows) >= 10

def test_list_trade_history_seeded(client):
    rows = client.get("/trade-history").get_json()
    assert len(rows) >= 10

def test_position_crud(client):
    r = client.post("/positions", json={
        "portfolio_id": 1, "market_ticker": "TEST-MKT", "side": "YES",
        "entry_price": 0.5, "size": 10,
    })
    assert r.status_code == 201
    pid = r.get_json()["id"]
    assert client.get(f"/positions/{pid}").status_code == 200
    assert client.put(f"/positions/{pid}", json={"size": 20, "entry_price": 0.6}).status_code == 200
    assert client.delete(f"/positions/{pid}").status_code == 200
    assert client.get(f"/positions/{pid}").status_code == 404

def test_ai_analyze_risk_has_trace(client):
    r = client.post("/ai/analyze-risk")
    assert r.status_code == 200
    data = r.get_json()
    assert "output" in data and "agentic_trace" in data
    stages = [t["stage"] for t in data["agentic_trace"]]
    assert stages[:3] == ["Plan", "Act", "Observe"]
