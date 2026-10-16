"""
Release 2 endpoint tests for Student 1 (pre-commit pytest validation).

Two endpoints are covered in depth, as required for Release 2:
  - GET  /markets      (list, filter, search)
  - POST /watchlist    (create, defaults, validation, unknown market)
Plus the Multi-Agent routes added in Task A, with the shared server mocked.
"""
import pytest
import requests


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


# ---------------- GET /markets ----------------
def test_markets_sorted_by_volume_descending(client):
    rows = client.get("/markets").get_json()
    volumes = [r["volume"] for r in rows]
    assert len(rows) >= 10
    assert volumes == sorted(volumes, reverse=True)


def test_markets_category_filter_returns_only_that_category(client):
    all_rows = client.get("/markets").get_json()
    category = all_rows[0]["category"]
    expected = [r for r in all_rows if r["category"] == category]
    filtered = client.get(f"/markets?category={category}").get_json()
    assert len(filtered) == len(expected)
    assert all(r["category"] == category for r in filtered)


def test_markets_search_finds_a_known_title(client):
    all_rows = client.get("/markets").get_json()
    target = all_rows[0]
    word = target["title"].split()[0]
    found = client.get(f"/markets?q={word}").get_json()
    assert target["id"] in [r["id"] for r in found]


def test_markets_search_with_no_match_returns_empty_list(client):
    resp = client.get("/markets?q=zzzz-no-such-market")
    assert resp.status_code == 200
    assert resp.get_json() == []


# ---------------- POST /watchlist ----------------
def test_add_watchlist_creates_and_persists_item(client):
    resp = client.post("/watchlist", json={"market_id": 1, "note": "watch", "priority": 3})
    assert resp.status_code == 201
    wid = resp.get_json()["id"]
    item = next(w for w in client.get("/watchlist").get_json() if w["id"] == wid)
    assert item["market_id"] == 1
    assert item["note"] == "watch"
    assert item["priority"] == 3


def test_add_watchlist_uses_defaults_for_note_and_priority(client):
    wid = client.post("/watchlist", json={"market_id": 2}).get_json()["id"]
    item = next(w for w in client.get("/watchlist").get_json() if w["id"] == wid)
    assert item["note"] == ""
    assert item["priority"] == 0


def test_add_watchlist_requires_market_id(client):
    resp = client.post("/watchlist", json={"note": "no market"})
    assert resp.status_code == 400
    assert "market_id" in resp.get_json()["error"]


def test_add_watchlist_rejects_unknown_market(client):
    resp = client.post("/watchlist", json={"market_id": 999999})
    assert resp.status_code == 404


# ---------------- Multi-Agent routes (Task A) ----------------
def _first_watchlist_id(client):
    return client.get("/watchlist").get_json()[0]["id"]


def test_multi_agent_validate_requires_watchlist_id(client):
    assert client.post("/multi-agent/validate", json={}).status_code == 400


def test_multi_agent_validate_unknown_watchlist_item(client):
    assert client.post("/multi-agent/validate", json={"watchlist_id": 999999}).status_code == 404


def test_multi_agent_validate_falls_back_when_server_unreachable(client, monkeypatch):
    import backend.app as appmod

    def boom(*args, **kwargs):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(appmod.requests, "post", boom)
    body = client.post("/multi-agent/validate", json={"watchlist_id": _first_watchlist_id(client)}).get_json()
    assert body["available"] is False
    assert body["run"] is None
    assert [s["stage"] for s in body["agentic_trace"]] == ["Plan", "Act", "Observe", "Adapt"]


def test_multi_agent_validate_returns_run_for_human_review(client, monkeypatch):
    import backend.app as appmod

    fake_run = {"run_id": "abc123", "status": "pending_human_review", "review": {"recommendation": "approve"}}
    monkeypatch.setattr(appmod.requests, "post", lambda *a, **k: FakeResponse(fake_run, 201))
    body = client.post("/multi-agent/validate", json={"watchlist_id": _first_watchlist_id(client)}).get_json()
    assert body["available"] is True
    assert body["run"]["run_id"] == "abc123"
    assert body["run"]["status"] == "pending_human_review"


def test_multi_agent_review_requires_run_id_and_decision(client):
    assert client.post("/multi-agent/review", json={"run_id": "x"}).status_code == 400


def test_multi_agent_review_returns_503_when_server_unreachable(client, monkeypatch):
    import backend.app as appmod

    def boom(*args, **kwargs):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(appmod.requests, "post", boom)
    resp = client.post("/multi-agent/review", json={"run_id": "x", "decision": "approve"})
    assert resp.status_code == 503