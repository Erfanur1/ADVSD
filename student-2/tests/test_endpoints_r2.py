"""
Release 2 post-commit endpoint tests for Student 2 (Portfolio & Position Tracker).

Two endpoint functions are covered in depth, as required for Release 2:
  - GET /positions       (list, portfolio filter, response shape, unknown portfolio)
  - GET /trade-history   (list, newest-first order, joined ticker, cascade on delete)
Plus the Release 2 Multi-Agent routes, with the shared Multi-Agent Server mocked,
so CI never depends on a local non-containerised service.
"""
import importlib
import pathlib
import sqlite3

import pytest
import requests


def _make_client(tmp_path, monkeypatch, multi_agent_enabled):
    db_path = tmp_path / "t.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("MCP_ENABLED", "false")
    monkeypatch.setenv("RAG_ENABLED", "false")
    monkeypatch.setenv("MULTI_AGENT_ENABLED", "true" if multi_agent_enabled else "false")
    base = pathlib.Path(__file__).resolve().parent.parent / "database"
    conn = sqlite3.connect(db_path)
    for f in ("schema.sql", "seed.sql", "price_seed.sql"):
        conn.executescript((base / f).read_text())
    conn.commit()
    conn.close()
    import backend.app as appmod
    importlib.reload(appmod)
    appmod.app.config.update(TESTING=True)
    return appmod, appmod.app.test_client()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    return _make_client(tmp_path, monkeypatch, multi_agent_enabled=False)[1]


@pytest.fixture()
def ma(tmp_path, monkeypatch):
    """(app module, client) with Multi-Agent enabled, for mocking the shared server."""
    return _make_client(tmp_path, monkeypatch, multi_agent_enabled=True)


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


# ---------------- Endpoint 1: GET /positions ----------------
def test_positions_returns_seeded_rows_with_portfolio_name(client):
    resp = client.get("/positions")
    assert resp.status_code == 200
    rows = resp.get_json()
    assert len(rows) >= 10
    assert all(r["portfolio_name"] for r in rows)


def test_positions_have_expected_fields_and_types(client):
    row = client.get("/positions").get_json()[0]
    for field in ("id", "portfolio_id", "market_ticker", "side", "entry_price", "size"):
        assert field in row
    assert row["side"] in ("YES", "NO")
    assert 0 < row["entry_price"] < 1
    assert isinstance(row["size"], int) and row["size"] > 0


def test_positions_filter_by_portfolio_returns_only_that_portfolio(client):
    all_rows = client.get("/positions").get_json()
    expected = [r for r in all_rows if r["portfolio_id"] == 3]
    rows = client.get("/positions?portfolio_id=3").get_json()
    assert len(rows) == len(expected) > 0
    assert all(r["portfolio_id"] == 3 for r in rows)


def test_positions_unknown_portfolio_returns_empty_list(client):
    resp = client.get("/positions?portfolio_id=9999")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_positions_reflects_newly_opened_position(client):
    before = len(client.get("/positions").get_json())
    client.post("/positions", json={"portfolio_id": 1, "market_ticker": "TEST-R2",
                                    "side": "NO", "entry_price": 0.3, "size": 5})
    rows = client.get("/positions").get_json()
    assert len(rows) == before + 1
    assert any(r["market_ticker"] == "TEST-R2" for r in rows)


# ---------------- Endpoint 2: GET /trade-history ----------------
def test_trade_history_returns_seeded_trades(client):
    resp = client.get("/trade-history")
    assert resp.status_code == 200
    rows = resp.get_json()
    assert len(rows) >= 10
    assert {r["trade_type"] for r in rows} <= {"BUY", "SELL"}


def test_trade_history_is_newest_first(client):
    ids = [r["id"] for r in client.get("/trade-history").get_json()]
    assert ids == sorted(ids, reverse=True)


def test_trade_history_includes_joined_market_ticker(client):
    rows = client.get("/trade-history").get_json()
    sell = next(r for r in rows if r["trade_type"] == "SELL")
    assert sell["market_ticker"] == "POL-TRUMP-2026"
    assert sell["shares"] == 20 and sell["price"] == 0.58


def test_trade_history_drops_trades_of_a_closed_position(client):
    before = client.get("/trade-history").get_json()
    assert any(r["position_id"] == 1 for r in before)
    assert client.delete("/positions/1").status_code == 200
    after = client.get("/trade-history").get_json()
    assert not any(r["position_id"] == 1 for r in after)
    assert len(after) < len(before)


# ---------------- Release 2: Multi-Agent routes ----------------
def test_multi_agent_disabled_in_ci(client):
    resp = client.post("/multi-agent/validate", json={"portfolio_id": 1})
    assert resp.status_code == 503
    assert resp.get_json()["status"] == "disabled"


def test_multi_agent_validate_requires_integer_portfolio_id(client):
    assert client.post("/multi-agent/validate", json={}).status_code == 400
    assert client.post("/multi-agent/validate", json={"portfolio_id": "abc"}).status_code == 400


def test_multi_agent_validate_unknown_portfolio_404(client):
    assert client.post("/multi-agent/validate", json={"portfolio_id": 9999}).status_code == 404


def test_multi_agent_validate_returns_run_for_human_review(ma, monkeypatch):
    appmod, c = ma
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent.update(url=url, body=json)
        return FakeResponse({"run_id": "abc123", "status": "pending_human_review",
                             "review": {"recommendation": "approve_with_caution", "confidence": "Medium",
                                        "risks": ["BTC is 52% of cost"]},
                             "_evidence_log_path": "/local/path.json"}, 201)

    monkeypatch.setattr(appmod.requests, "post", fake_post)
    data = c.post("/multi-agent/validate", json={"portfolio_id": 2}).get_json()
    assert sent["url"].endswith("/multi-agent/run")
    assert sent["body"]["task_type"] == "review_portfolio"
    assert sent["body"]["params"]["portfolio_id"] == 2
    assert data["status"] == "ok" and data["run"]["status"] == "pending_human_review"
    assert "_evidence_log_path" not in data["run"]
    assert [t["stage"] for t in data["agentic_trace"]] == ["Plan", "Act", "Observe", "Adapt"]


def test_multi_agent_validate_unreachable_server_502(ma, monkeypatch):
    appmod, c = ma

    def boom(*a, **k):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(appmod.requests, "post", boom)
    resp = c.post("/multi-agent/validate", json={"portfolio_id": 1})
    assert resp.status_code == 502
    assert resp.get_json()["status"] == "unavailable"


def test_multi_agent_review_rejects_invalid_decision(ma):
    _, c = ma
    assert c.post("/multi-agent/review", json={"run_id": "abc123", "decision": "maybe"}).status_code == 400
    assert c.post("/multi-agent/review", json={"decision": "approve"}).status_code == 400


def test_multi_agent_review_passes_human_decision(ma, monkeypatch):
    appmod, c = ma
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent.update(url=url, body=json)
        return FakeResponse({"run_id": "abc123", "status": "approved",
                             "human_decision": {"decision": "approve", "notes": "ok"}})

    monkeypatch.setattr(appmod.requests, "post", fake_post)
    data = c.post("/multi-agent/review",
                  json={"run_id": "abc123", "decision": "approve", "notes": "ok"}).get_json()
    assert sent["url"].endswith("/multi-agent/review")
    assert sent["body"] == {"run_id": "abc123", "decision": "approve", "notes": "ok"}
    assert data["status"] == "ok" and data["run"]["status"] == "approved"
