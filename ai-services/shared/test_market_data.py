"""Offline tests for the shared market data layer (upstream APIs are faked)."""
import json
import pytest
import requests

import market_data as md


class FakeResp:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status
        self.ok = status < 400

    def json(self):
        return self.body

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"HTTP {self.status_code}")


POLY_SEARCH = {"events": [{
    "title": "What price will Bitcoin hit?",
    "tags": [{"label": "Crypto"}],
    "markets": [
        {"id": "101", "question": "Will Bitcoin reach $150k?", "bestBid": 0.20, "bestAsk": 0.22,
         "lastTradePrice": 0.21, "volume": "5000", "endDate": "2026-12-31", "closed": False},
        {"id": "102", "question": "Will Bitcoin reach $90k?", "closed": True, "lastTradePrice": 1},
    ],
}, {
    # a fuzzy upstream hit that shares no keyword with the query
    "title": "Xi Jinping out before 2027?",
    "markets": [{"id": "103", "question": "Xi Jinping out before 2027?", "lastTradePrice": 0.03,
                 "volume": "9999999", "closed": False}],
}]}

KALSHI_SERIES = {"series": [
    {"ticker": "KXBTC", "title": "Bitcoin price", "category": "Crypto", "tags": ["BTC"]},
    {"ticker": "KXFEDDECISION", "title": "Fed decision", "category": "Economics", "tags": []},
    {"ticker": "KXMVECROSS", "title": "Bitcoin combo parlay", "category": "Sports", "tags": []},
]}

KALSHI_FED = {"events": [
    {"event_ticker": "KXFEDDECISION-26OCT", "title": "Fed decision in Oct 2026?", "category": "Economics",
     "markets": [{"ticker": "KXFEDDECISION-26OCT-H0", "yes_sub_title": "Fed maintains rate", "status": "active",
                  "yes_bid_dollars": "0.66", "yes_ask_dollars": "0.67", "last_price_dollars": "0.66"}]},
]}

KALSHI_EVENTS = {"cursor": "", "events": [
    {"event_ticker": "KXBTC-26", "title": "Bitcoin price at end of 2026", "category": "Crypto",
     "markets": [{"ticker": "KXBTC-26-150K", "yes_sub_title": "Above $150k", "status": "active",
                  "yes_bid_dollars": "0.3000", "yes_ask_dollars": "0.3200",
                  "last_price_dollars": "0.3100", "volume_fp": "800", "close_time": "2026-12-31"},
                 {"ticker": "KXBTC-26-DEAD", "yes_sub_title": "Above $1m", "status": "active",
                  "yes_bid_dollars": "0", "yes_ask_dollars": "1", "last_price_dollars": "0"}]},
    {"event_ticker": "KXMVECROSS-1", "title": "Bitcoin combo parlay", "category": "Sports",
     "markets": [{"ticker": "KXMVECROSS-1-A", "status": "active", "yes_bid_dollars": "0.1",
                  "yes_ask_dollars": "0.2", "last_price_dollars": "0.1"}]},
]}


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(md, "CACHE_PATH", str(tmp_path / "cache.json"))
    md._kalshi_series.update(ts=0.0, items=[])
    md._kalshi_index.update(ts=0.0, events=[], building=False)
    md._kalshi_seen.clear()
    monkeypatch.setattr(md, "warm_up", lambda: None)  # no background threads in tests
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        if url == md.POLYMARKET_SEARCH_URL:
            return FakeResp(POLY_SEARCH)
        if url == f"{md.KALSHI_API_URL}/series":
            return FakeResp(KALSHI_SERIES)
        if url == f"{md.KALSHI_API_URL}/events" and "with_nested_markets" not in (params or {}):
            # index build: two pages of titles only
            page2 = (params or {}).get("cursor") == "p2"
            evs = KALSHI_FED["events"] if page2 else KALSHI_EVENTS["events"]
            return FakeResp({"cursor": "" if page2 else "p2",
                             "events": [{k: v for k, v in e.items() if k != "markets"} for e in evs]})
        if url == f"{md.KALSHI_API_URL}/events":
            series = (params or {}).get("series_ticker")
            return FakeResp(KALSHI_FED if series == "KXFEDDECISION" else
                            KALSHI_EVENTS if series in (None, "KXBTC") else {"events": []})
        if url.startswith(f"{md.KALSHI_API_URL}/events/"):
            ticker = url.rsplit("/", 1)[1]
            for e in KALSHI_FED["events"] + KALSHI_EVENTS["events"]:
                if e["event_ticker"] == ticker:
                    return FakeResp({"event": {k: v for k, v in e.items() if k != "markets"},
                                     "markets": e["markets"]})
        if url == f"{md.POLYMARKET_MARKETS_URL}/101":
            return FakeResp(POLY_SEARCH["events"][0]["markets"][0])
        return FakeResp({}, status=404)

    monkeypatch.setattr(md.requests, "get", fake_get)
    return calls


def test_keywords_drop_filler_words():
    assert md.keywords("What is driving sentiment in election markets right now?") == ["election"]
    assert md.keywords("Fed rate cuts") == ["fed", "rate", "cut"]


def test_month_names_match_both_spellings():
    assert md.keywords("fed decision October 2026") == ["fed", "decision", "oct", "2026"]
    assert md.keywords("October", shorten_months=False) == ["october"]
    markets, _ = md.fetch_markets(source="kalshi", query="Fed decision October 2026")
    assert [m["id"] for m in markets] == ["KXFEDDECISION-26OCT-H0"]


def test_search_returns_both_sources_and_drops_unrelated():
    markets, meta = md.fetch_markets(query="bitcoin price", limit=10)
    ids = [m["id"] for m in markets]
    assert meta["source"] == "live"
    assert "101" in ids and "KXBTC-26-150K" in ids
    assert "103" not in ids               # fuzzy upstream hit filtered out
    assert "102" not in ids               # closed market skipped
    assert "KXBTC-26-DEAD" not in ids     # no real price
    assert not any(i.startswith("KXMVE") for i in ids)  # combo parlays skipped
    assert all(not k.startswith("_") for m in markets for k in m)


def test_probability_is_bid_ask_midpoint():
    markets, _ = md.fetch_markets(source="kalshi", query="bitcoin")
    m = markets[0]
    assert (m["yes_bid"], m["yes_ask"], m["probability"]) == (0.30, 0.32, 0.31)
    assert m["title"] == "Bitcoin price at end of 2026 — Above $150k"


def test_no_relevant_market_returns_nothing():
    markets, meta = md.fetch_markets(query="zzqx nonsense")
    assert markets == [] and meta["source"] == "none"


def test_kalshi_event_index_search(offline):
    md.refresh_kalshi_index()
    assert [e["ticker"] for e in md._kalshi_index["events"]] == ["KXBTC-26", "KXFEDDECISION-26OCT"]  # combo skipped
    offline.clear()
    markets, _ = md.fetch_markets(source="kalshi", query="fed decision october")
    assert [m["id"] for m in markets] == ["KXFEDDECISION-26OCT-H0"]
    assert offline == [f"{md.KALSHI_API_URL}/events/KXFEDDECISION-26OCT"]  # only the matching event fetched


def test_kalshi_index_keeps_previous_copy_when_kalshi_down(monkeypatch):
    md.refresh_kalshi_index()
    before = list(md._kalshi_index["events"])

    def down(*a, **k):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(md.requests, "get", down)
    md.refresh_kalshi_index()
    assert md._kalshi_index["events"] == before and not md._kalshi_index["building"]


def test_kalshi_series_list_is_cached(offline):
    md.fetch_markets(source="kalshi", query="bitcoin")
    md.fetch_markets(source="kalshi", query="fed decision")
    assert offline.count(f"{md.KALSHI_API_URL}/series") == 1


def test_falls_back_to_cache_when_upstream_down(monkeypatch):
    fresh, _ = md.fetch_markets(query="bitcoin")
    md._kalshi_series.update(ts=0.0, items=[])

    def down(*a, **k):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(md.requests, "get", down)
    cached, meta = md.fetch_markets(query="bitcoin")
    assert meta["source"] == "cache" and cached == fresh


def test_get_market_by_id_routes_by_format():
    assert md.get_market_by_id("101")[0]["source"] == "polymarket"
    md.fetch_markets(source="kalshi", query="bitcoin")  # seen in a search -> no extra call
    assert md.get_market_by_id("KXBTC-26-150K")[0]["source"] == "kalshi"
    assert md.get_market_by_id("999")[0] is None


@pytest.mark.parametrize("bad", ["../../etc/passwd", "abc def", "", "x" * 200])
def test_get_market_by_id_rejects_malformed_ids(bad, offline):
    market, meta = md.get_market_by_id(bad)
    assert market is None and meta["errors"]
    assert not offline  # never reached an upstream URL


def test_source_filter_respected():
    assert md.get_market_by_id("101", source="kalshi")[0] is None
    markets, _ = md.fetch_markets(source="polymarket", query="bitcoin")
    assert {m["source"] for m in markets} == {"polymarket"}
