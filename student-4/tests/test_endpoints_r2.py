"""
Release 2 tests for Student 4 (AI Market Analyst Assistant): the new
Multi-Agent routes (Planner -> Worker -> Reviewer -> Human Review), with
the shared Multi-Agent Server mocked, so CI never depends on a local
non-containerised service. The two required Release 2 endpoint functions
(/mcp/execute, /mispricing/save) already have dedicated coverage in
tests/test_api.py; this file covers the Multi-Agent integration on top.
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
    conn.executescript((base / "schema.sql").read_text())
    conn.executescript((base / "seed.sql").read_text())
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


def test_multi_agent_disabled_in_ci(client):
    resp = client.post("/multi-agent/validate", json={"polymarket_id": "1", "kalshi_ticker": "KX-1"})
    assert resp.status_code == 503
    assert resp.get_json()["status"] == "disabled"


def test_multi_agent_validate_requires_both_ids(ma):
    _, c = ma
    assert c.post("/multi-agent/validate", json={}).status_code == 400
    assert c.post("/multi-agent/validate", json={"polymarket_id": "1"}).status_code == 400
    assert c.post("/multi-agent/validate", json={"kalshi_ticker": "KX-1"}).status_code == 400


def test_multi_agent_validate_returns_run_for_human_review(ma, monkeypatch):
    appmod, c = ma
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent.update(url=url, body=json)
        return FakeResponse({"run_id": "abc123", "status": "pending_human_review",
                             "review": {"recommendation": "approve", "confidence": "High", "risks": []},
                             "_evidence_log_path": "/local/path.json"}, 201)

    monkeypatch.setattr(appmod.requests, "post", fake_post)
    data = c.post("/multi-agent/validate",
                  json={"polymarket_id": "1", "kalshi_ticker": "KX-1"}).get_json()
    assert sent["url"].endswith("/multi-agent/run")
    assert sent["body"]["task_type"] == "review_mispricing_analysis"
    assert sent["body"]["params"] == {"feature": "market-analyst", "polymarket_id": "1", "kalshi_ticker": "KX-1"}
    assert data["status"] == "ok" and data["run"]["status"] == "pending_human_review"
    assert "_evidence_log_path" not in data["run"]
    assert [t["stage"] for t in data["agentic_trace"]] == ["Plan", "Act", "Observe", "Adapt"]


def test_multi_agent_validate_unreachable_server_502(ma, monkeypatch):
    appmod, c = ma

    def boom(*a, **k):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(appmod.requests, "post", boom)
    resp = c.post("/multi-agent/validate", json={"polymarket_id": "1", "kalshi_ticker": "KX-1"})
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
