"""
Release 2 endpoint tests for Student 3 (pre-commit pytest validation).

Two endpoints are covered in depth, as required for Release 2:
  - GET  /news    (list, category filter, headline search, ordering)
  - POST /notes   (create, defaults, validation, unknown article)
Plus the Multi-Agent routes added in Task A, with the shared server mocked.
"""
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


def _boom(*args, **kwargs):
    raise requests.ConnectionError("down")


# ---------------- GET /news ----------------
def test_news_sorted_by_published_date_descending(client):
    rows = client.get("/news").get_json()
    dates = [r["published_date"] for r in rows]
    assert len(rows) >= 10
    assert dates == sorted(dates, reverse=True)


def test_news_rows_include_source_name(client):
    rows = client.get("/news").get_json()
    assert all(r["source_name"] for r in rows)


def test_news_category_filter_returns_only_that_category(client):
    all_rows = client.get("/news").get_json()
    category = all_rows[0]["category"]
    expected = [r for r in all_rows if r["category"] == category]
    filtered = client.get(f"/news?category={category}").get_json()
    assert len(filtered) == len(expected)
    assert all(r["category"] == category for r in filtered)


def test_news_search_finds_a_known_headline(client):
    target = client.get("/news").get_json()[0]
    word = target["headline"].split()[0]
    found = client.get(f"/news?q={word}").get_json()
    assert target["id"] in [r["id"] for r in found]


def test_news_search_with_no_match_returns_empty_list(client):
    resp = client.get("/news?q=zzzz-no-such-headline")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_news_category_and_search_combine(client):
    target = client.get("/news").get_json()[0]
    word = target["headline"].split()[0]
    rows = client.get(f"/news?category={target['category']}&q={word}").get_json()
    assert target["id"] in [r["id"] for r in rows]
    assert client.get("/news?category=no-such-category&q=" + word).get_json() == []


# ---------------- POST /notes ----------------
def test_add_note_creates_and_persists(client):
    resp = client.post("/notes", json={"article_id": 1, "title": "t", "content": "c", "tags": "a,b"})
    assert resp.status_code == 201
    nid = resp.get_json()["id"]
    note = next(n for n in client.get("/notes").get_json() if n["id"] == nid)
    assert note["article_id"] == 1
    assert note["title"] == "t"
    assert note["content"] == "c"
    assert note["tags"] == "a,b"
    assert note["headline"]


def test_add_note_uses_defaults_for_optional_fields(client):
    nid = client.post("/notes", json={"article_id": 2}).get_json()["id"]
    note = next(n for n in client.get("/notes").get_json() if n["id"] == nid)
    assert note["title"] == ""
    assert note["content"] == ""
    assert note["tags"] == ""


def test_add_note_requires_article_id(client):
    resp = client.post("/notes", json={"title": "no article"})
    assert resp.status_code == 400
    assert "article_id" in resp.get_json()["error"]


def test_add_note_rejects_unknown_article(client):
    resp = client.post("/notes", json={"article_id": 999999})
    assert resp.status_code == 404


def test_add_note_does_not_change_other_notes(client):
    before = client.get("/notes").get_json()
    client.post("/notes", json={"article_id": 1, "title": "new"})
    after = client.get("/notes").get_json()
    assert len(after) == len(before) + 1
    for old in before:
        assert next(n for n in after if n["id"] == old["id"]) == old


# ---------------- Multi-Agent routes (Task A) ----------------
def _validate(client, **overrides):
    body = {"note_id": 1, "market_id": "2491900"}
    body.update(overrides)
    return client.post("/multi-agent/validate", json=body)


def test_multi_agent_validate_requires_note_id(client):
    assert client.post("/multi-agent/validate", json={"market_id": "x"}).status_code == 400


def test_multi_agent_validate_requires_market_id(client):
    assert client.post("/multi-agent/validate", json={"note_id": 1}).status_code == 400


def test_multi_agent_validate_unknown_note(client):
    assert _validate(client, note_id=999999).status_code == 404


def test_multi_agent_validate_rejects_out_of_range_probability(client):
    assert _validate(client, claimed_probability=7).status_code == 400
    assert _validate(client, claimed_probability="abc").status_code == 400


def test_multi_agent_validate_falls_back_when_server_unreachable(client, monkeypatch):
    import backend.app as appmod

    monkeypatch.setattr(appmod.requests, "post", _boom)
    body = _validate(client).get_json()
    assert body["available"] is False
    assert body["run"] is None
    assert [s["stage"] for s in body["agentic_trace"]] == ["Plan", "Act", "Observe", "Adapt"]


def test_multi_agent_validate_returns_run_for_human_review(client, monkeypatch):
    import backend.app as appmod

    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent["url"], sent["json"] = url, json
        return FakeResponse({"run_id": "abc123", "status": "pending_human_review", "review": {"recommendation": "approve"}}, 201)

    monkeypatch.setattr(appmod.requests, "post", fake_post)
    body = _validate(client, claimed_probability="0.45").get_json()
    assert body["available"] is True
    assert body["run"]["run_id"] == "abc123"
    assert body["run"]["status"] == "pending_human_review"
    assert sent["url"].endswith("/multi-agent/run")
    assert sent["json"]["task_type"] == "validate_market_action"
    assert sent["json"]["params"]["feature"] == "research-notes"
    assert sent["json"]["params"]["submitted_value"] == 0.45


def test_multi_agent_review_requires_run_id_and_decision(client):
    assert client.post("/multi-agent/review", json={"run_id": "x"}).status_code == 400


def test_multi_agent_review_returns_503_when_server_unreachable(client, monkeypatch):
    import backend.app as appmod

    monkeypatch.setattr(appmod.requests, "post", _boom)
    resp = client.post("/multi-agent/review", json={"run_id": "x", "decision": "approve"})
    assert resp.status_code == 503


def test_multi_agent_review_passes_through_decision_result(client, monkeypatch):
    import backend.app as appmod

    monkeypatch.setattr(appmod.requests, "post", lambda *a, **k: FakeResponse({"run_id": "abc123", "status": "approved"}, 200))
    resp = client.post("/multi-agent/review", json={"run_id": "abc123", "decision": "approve"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "approved"
