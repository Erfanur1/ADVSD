import os, sqlite3, importlib, pathlib
import pytest

@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "t.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    # CI/CD: MCP and RAG integration is kept but disabled
    monkeypatch.setenv("MCP_ENABLED", "false")
    monkeypatch.setenv("RAG_ENABLED", "false")
    base = pathlib.Path(__file__).resolve().parent.parent / "database"
    conn = sqlite3.connect(db_path)
    conn.executescript((base / "schema.sql").read_text())
    conn.executescript((base / "seed.sql").read_text())
    conn.executescript((base / "price_seed.sql").read_text())
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

def test_position_history(client):
    r = client.get("/positions/1/history")
    assert r.status_code == 200
    assert len(r.get_json()["points"]) == 30
    assert client.get("/positions/9999/history").status_code == 404

def test_ai_analyze_risk_has_trace(client):
    r = client.post("/ai/analyze-risk")
    assert r.status_code == 200
    data = r.get_json()
    assert "output" in data and "agentic_trace" in data
    stages = [t["stage"] for t in data["agentic_trace"]]
    assert stages[:3] == ["Plan", "Act", "Observe"]

# ---- Release 1: MCP/RAG retained but disabled in CI ----
def test_mcp_disabled_in_ci(client):
    r = client.post("/mcp/execute", json={"tool": "validate_portfolio", "parameters": {"portfolio_id": 1}})
    assert r.status_code == 503
    assert r.get_json()["status"] == "disabled"

def test_mcp_tool_boundary(client):
    r = client.post("/mcp/execute", json={"tool": "delete_everything", "parameters": {}})
    assert r.status_code == 400
    assert r.get_json()["status"] == "rejected"

def test_rag_disabled_in_ci(client):
    r = client.post("/rag/ask", json={"query": "Why is POL-TRUMP-2026 down?"})
    assert r.status_code == 503
    assert r.get_json()["status"] == "disabled"

def test_rag_rejects_empty_query(client):
    assert client.post("/rag/ask", json={"query": "  "}).status_code == 400

# ---- AI risk analysis: Observe/Adapt handles refusals ----
def _fake_ai(monkeypatch, replies):
    import backend.app as appmod
    calls = iter(replies)
    monkeypatch.setattr(appmod, "_call_ai", lambda task, ctx: (next(calls), True))
 
def test_risk_strips_disclaimer(client, monkeypatch):
    _fake_ai(monkeypatch, ["I can't provide financial advice, but I can help with general analysis. "
                           "The portfolio is concentrated in KALSHI markets at 45% of cost."])
    d = client.post("/ai/analyze-risk").get_json()
    assert "financial advice" not in d["output"] and "KALSHI" in d["output"]
    assert "disclaimer detected" in d["agentic_trace"][2]["detail"]
 
def test_risk_retries_on_pure_refusal(client, monkeypatch):
    _fake_ai(monkeypatch, ["I cannot provide financial advice.",
                           "The biggest category is KALSHI at 45% of cost."])
    d = client.post("/ai/analyze-risk").get_json()
    assert d["output"].startswith("The biggest category is KALSHI")
    assert "retried" in d["agentic_trace"][-1]["detail"]
 
def test_risk_falls_back_to_computed_summary(client, monkeypatch):
    _fake_ai(monkeypatch, ["I'm not a financial advisor.", "Sorry, I can't help with that."])
    d = client.post("/ai/analyze-risk").get_json()
    assert "maximum possible loss" in d["output"]
 
