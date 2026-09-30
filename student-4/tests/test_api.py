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


# ---- Release 1: MCP/RAG retained but disabled in CI ----
def test_health_reports_mcp_rag_disabled(client):
    data = client.get("/health").get_json()
    assert data["mcp_enabled"] is False and data["rag_enabled"] is False

def test_mcp_disabled_in_ci(client):
    r = client.post("/mcp/execute", json={"tool": "compare_markets",
                                         "parameters": {"polymarket_id": "1", "kalshi_ticker": "KX-1"}})
    assert r.status_code == 503 and r.get_json()["status"] == "disabled"

def test_mcp_tool_boundary(client):
    for tool in ("validate_portfolio", "log_analysis_note", "drop_tables", None):
        r = client.post("/mcp/execute", json={"tool": tool, "parameters": {}})
        assert r.status_code == 400 and r.get_json()["status"] == "rejected"

def test_mispricing_save_disabled_in_ci(client):
    r = client.post("/mispricing/save", json={"polymarket_id": "1", "kalshi_ticker": "KX-1"})
    assert r.status_code == 503

def test_rag_disabled_in_ci(client):
    r = client.post("/rag/ask", json={"query": "Is the Fed market mispriced?"})
    assert r.status_code == 503 and r.get_json()["status"] == "disabled"

def test_rag_rejects_bad_queries(client):
    assert client.post("/rag/ask", json={"query": "   "}).status_code == 400
    assert client.post("/rag/ask", json={"query": "x" * 501}).status_code == 400


# ---- Release 1: live paths with the shared servers faked ----
class _Resp:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status
    def json(self):
        return self.body
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

POLY = {"source": "polymarket", "id": "555", "title": "Will the Fed cut in October?", "category": "Economy",
        "probability": 0.62, "yes_bid": 0.61, "yes_ask": 0.63, "volume": 12345.6, "close_date": "2026-10-29T00:00:00Z"}
KALSHI = {"source": "kalshi", "id": "KXFED-26OCT-C", "title": "Fed decision in October? — Cut",
          "category": "Economics", "probability": 0.52, "yes_bid": 0.50, "yes_ask": 0.54, "volume": 800, "close_date": ""}
COMPARISON = {"status": "mispriced", "gap": 0.10, "abs_gap_points": 10.0, "edge_after_spread": 0.07,
              "direction": "Polymarket prices YES higher than Kalshi", "basis": "order books (bid/ask)"}

@pytest.fixture()
def live(client, monkeypatch):
    import backend.app as appmod
    monkeypatch.setattr(appmod, "MCP_ENABLED", True)
    monkeypatch.setattr(appmod, "RAG_ENABLED", True)
    sent = []
    def fake_post(url, json=None, timeout=None):
        sent.append((url, json))
        if url.endswith("/mcp/call"):
            return _Resp({"tool": json["tool"], "result": {"polymarket": POLY, "kalshi": KALSHI, "comparison": COMPARISON}})
        if "zzqx" in json["question"]:
            return _Resp({"answer": "I don't have enough relevant context.", "citations": [],
                          "confidence": "Low", "insufficient_context": True})
        return _Resp({"answer": "Polymarket is 10 points above Kalshi.", "confidence": "High",
                      "insufficient_context": False,
                      "citations": [{"id": "market:555", "source": "polymarket", "excerpt": "Fed cut 0.62"}]})
    monkeypatch.setattr(appmod.requests, "post", fake_post)
    return client, sent

def test_mcp_execute_returns_result_and_trace(live):
    client, sent = live
    r = client.post("/mcp/execute", json={"tool": "compare_markets",
                                         "parameters": {"polymarket_id": "555", "kalshi_ticker": "KXFED-26OCT-C"}})
    data = r.get_json()
    assert r.status_code == 200 and data["status"] == "ok"
    assert data["result"]["comparison"]["status"] == "mispriced"
    assert [t["stage"] for t in data["agentic_trace"]] == ["Plan", "Act", "Observe", "Adapt"]
    assert sent[0][1] == {"tool": "compare_markets", "params": {"polymarket_id": "555", "kalshi_ticker": "KXFED-26OCT-C"}}

def test_mispricing_save_upserts_market_and_analysis(live):
    client, _ = live
    body = {"polymarket_id": "555", "kalshi_ticker": "KXFED-26OCT-C"}
    first = client.post("/mispricing/save", json=body).get_json()
    assert first["verdict"] == "overpriced" and first["confidence"] == 0.9
    market = client.get(f"/markets/{first['market_id']}").get_json()
    assert market["title"] == POLY["title"] and market["current_probability"] == 0.62
    assert market["close_date"] == "2026-10-29"
    saved = [a for a in client.get("/analyses").get_json() if a["id"] == first["analysis_id"]][0]
    assert "10.0 pts apart" in saved["summary"] and "KXFED-26OCT-C" in saved["summary"]
    # saving the same pair again reuses the market row instead of duplicating it
    second = client.post("/mispricing/save", json=body).get_json()
    assert second["market_id"] == first["market_id"] and second["analysis_id"] != first["analysis_id"]

def test_mcp_error_is_passed_through(client, monkeypatch):
    import backend.app as appmod
    monkeypatch.setattr(appmod, "MCP_ENABLED", True)
    monkeypatch.setattr(appmod.requests, "post", lambda *a, **k: _Resp({"error": "Kalshi market 'X' not found"}, 404))
    r = client.post("/mcp/execute", json={"tool": "get_market_price", "parameters": {"market_id": "X"}})
    assert r.status_code == 404 and "not found" in r.get_json()["error"]

def test_mcp_unreachable_returns_502(client, monkeypatch):
    import backend.app as appmod
    monkeypatch.setattr(appmod, "MCP_ENABLED", True)
    def down(*a, **k):
        raise ConnectionError("refused")
    monkeypatch.setattr(appmod.requests, "post", down)
    r = client.post("/mcp/execute", json={"tool": "search_markets", "parameters": {"query": "fed"}})
    assert r.status_code == 502 and r.get_json()["status"] == "unavailable"

def test_rag_grounded_answer_with_citations(live):
    client, sent = live
    data = client.post("/rag/ask", json={"query": "Why do the Fed markets differ?", "market_id": "555"}).get_json()
    assert data["status"] == "ok" and data["confidence"] == "High" and data["generated"] is True
    assert data["citations"][0] == {"id": "S1", "ref": "market:555", "source": "polymarket", "snippet": "Fed cut 0.62"}
    assert sent[-1][1] == {"question": "Why do the Fed markets differ?", "market_id": "555"}

def test_rag_insufficient_context(live):
    client, _ = live
    data = client.post("/rag/ask", json={"query": "What about zzqx?"}).get_json()
    assert data["status"] == "insufficient_context" and data["citations"] == []
    assert "insufficient-context" in data["agentic_trace"][-1]["detail"]
