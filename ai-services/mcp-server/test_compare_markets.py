"""Offline tests for the Student 4 compare_markets MCP tool (market lookups are faked)."""
import pytest

import app as mcp


def market(source, prob, bid=None, ask=None, mid="1"):
    return {"source": source, "id": mid, "title": f"{source} market", "category": "Test",
            "probability": prob, "yes_bid": bid, "yes_ask": ask, "volume": 1.0, "close_date": ""}


def test_books_not_overlapping_is_mispriced():
    c = mcp.compare_prices(market("polymarket", 0.62, 0.61, 0.63), market("kalshi", 0.52, 0.50, 0.54))
    assert c["status"] == "mispriced"
    assert c["edge_after_spread"] == pytest.approx(0.07)   # poly bid 0.61 - kalshi ask 0.54
    assert c["abs_gap_points"] == 10.0
    assert c["direction"].startswith("Polymarket prices YES higher")


def test_overlapping_books_with_big_gap_is_watch():
    c = mcp.compare_prices(market("polymarket", 0.40, 0.30, 0.50), market("kalshi", 0.47, 0.44, 0.50))
    assert c["status"] == "watch" and c["edge_after_spread"] == 0.0
    assert c["direction"].startswith("Kalshi prices YES higher")


def test_small_gap_is_fair():
    c = mcp.compare_prices(market("polymarket", 0.50, 0.49, 0.51), market("kalshi", 0.52, 0.51, 0.53))
    assert c["status"] == "fair" and c["direction"] == "prices agree"


def test_incomplete_book_falls_back_to_last_trade():
    c = mcp.compare_prices(market("polymarket", 0.90), market("kalshi", 0.50, 0.49, 0.51))
    assert c["status"] == "watch"  # never "mispriced" without both books
    assert c["basis"].startswith("last-trade")


@pytest.fixture()
def client(monkeypatch):
    found = {("123", "polymarket"): market("polymarket", 0.62, 0.61, 0.63, "123"),
             ("KXTEST-1", "kalshi"): market("kalshi", 0.52, 0.50, 0.54, "KXTEST-1")}
    monkeypatch.setattr(mcp.market_data, "get_market_by_id",
                        lambda mid, source="both": (found.get((mid, source)), {"errors": []}))
    return mcp.app.test_client()


def test_tool_returns_structured_result(client):
    r = client.post("/mcp/call", json={"tool": "compare_markets",
                                       "params": {"polymarket_id": "123", "kalshi_ticker": "KXTEST-1"}})
    body = r.get_json()
    assert r.status_code == 200 and body["tool"] == "compare_markets"
    assert set(body["result"]) == {"polymarket", "kalshi", "comparison"}
    assert body["result"]["comparison"]["status"] == "mispriced"


def test_tool_requires_both_ids(client):
    r = client.post("/mcp/call", json={"tool": "compare_markets", "params": {"polymarket_id": "123"}})
    assert r.status_code == 400


def test_tool_rejects_swapped_sources(client):
    # a Kalshi ticker passed as the Polymarket id must not be looked up as Polymarket
    r = client.post("/mcp/call", json={"tool": "compare_markets",
                                       "params": {"polymarket_id": "KXTEST-1", "kalshi_ticker": "123"}})
    assert r.status_code == 404


def test_tool_is_registered():
    assert "compare_markets" in mcp.app.test_client().get("/mcp/tools").get_json()
