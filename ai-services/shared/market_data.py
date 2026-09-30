"""
Shared live market data layer (Release 1, Task 1).

Fetches live market data from Polymarket and Kalshi -- the two largest
real-money prediction exchanges -- through their public, no-authentication
APIs, and caches results locally to protect against rate limits, downtime,
or slow responses.

Used by:
  - ai-services/mcp-server/app.py  (tools: get_market_price, search_markets, get_market_history)
  - ai-services/rag-server/app.py  (retrieval context for grounded answers)

This module is NOT its own HTTP service -- it's a plain Python module
imported directly by the MCP and RAG servers, since both run on the
same local host and don't need network isolation from each other.

Every market is normalised to one common shape:
  {source, id, title, category, probability, yes_bid, yes_ask, volume,
   close_date, relevance}
where probability is the bid/ask midpoint when a live order book exists,
otherwise the last traded price. yes_bid/yes_ask are None when unknown.
"""
import json
import os
import re
import time
import requests
import threading
from concurrent.futures import ThreadPoolExecutor

CACHE_PATH = os.path.join(os.path.dirname(__file__), "market_cache.json")
CACHE_TTL_SECONDS = int(os.getenv("MARKET_CACHE_TTL", "300"))  # 5 min default

POLYMARKET_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
POLYMARKET_SEARCH_URL = "https://gamma-api.polymarket.com/public-search"
KALSHI_API_URL = "https://api.elections.kalshi.com/trade-api/v2"

KALSHI_SERIES_TTL = int(os.getenv("KALSHI_SERIES_TTL", "21600"))  # series list changes rarely: 6h
KALSHI_SERIES_TIMEOUT = 30     # the series list is one ~18 MB response
KALSHI_MAX_SERIES = 8          # fallback: best-matching series whose open events are fetched
KALSHI_INDEX_TTL = int(os.getenv("KALSHI_INDEX_TTL", "1800"))  # event-title index refresh: 30 min
KALSHI_MAX_EVENTS = 10         # best-matching events whose live prices are fetched per search
KALSHI_COMBO_PREFIX = "KXMVE"  # multivariate "combo" parlays -- not real single-outcome markets

REQUEST_TIMEOUT = 8  # seconds

# A result must contain at least this share of the query's keywords, so an
# unrelated market is never returned (and never cited by RAG) just because
# an upstream fuzzy search ranked it first.
MIN_RELEVANCE = 0.5

# Id formats, also used to reject malformed ids before they reach a URL path.
POLYMARKET_ID_RE = re.compile(r"^\d{1,12}$")
KALSHI_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{1,79}$")

# Words that say nothing about WHICH market is meant.
STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for", "by", "with", "from",
    "is", "are", "was", "were", "be", "been", "will", "would", "could", "should", "can", "does",
    "do", "did", "has", "have", "had", "it", "its", "this", "that", "these", "those", "there",
    "what", "whats", "why", "how", "who", "when", "which", "where", "about", "any", "some",
    "my", "our", "your", "me", "we", "you", "i", "tell", "show", "give", "explain",
    "market", "markets", "price", "prices", "probability", "odds", "chance", "chances",
    "likely", "trending", "trend", "sentiment", "driving", "happening", "latest", "current",
    "currently", "right", "now", "today", "news", "outlook", "view", "think", "expect",
    "analysis", "analyse", "analyze", "look", "looks", "going", "mispriced", "priced",
}


# ---------------- cache ----------------

def _load_cache():
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache):
    try:
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f)
    except OSError:
        pass  # cache write failures should never break a request


def _cache_get(key):
    cache = _load_cache()
    entry = cache.get(key)
    if entry and (time.time() - entry["ts"]) < CACHE_TTL_SECONDS:
        return entry["data"], True  # (data, was_fresh)
    if entry:
        return entry["data"], False  # stale but usable as a fallback
    return None, False


def _cache_set(key, data):
    cache = _load_cache()
    cache[key] = {"ts": time.time(), "data": data}
    _save_cache(cache)


# ---------------- keyword relevance ----------------

MONTHS = {"january": "jan", "february": "feb", "march": "mar", "april": "apr", "june": "jun",
          "july": "jul", "august": "aug", "september": "sep", "sept": "sep", "october": "oct",
          "november": "nov", "december": "dec"}


def keywords(text, shorten_months=True):
    """
    Lower-cased content words of a query, with a light plural strip. Month
    names are shortened to their 3-letter prefix so one term matches both
    Polymarket's "October" and Kalshi's "Oct" (matching is by word prefix).
    """
    words = re.findall(r"[a-z0-9$%.]+", (text or "").lower())
    out = []
    for w in words:
        w = w.strip(".")
        if not w or w in STOPWORDS or (len(w) < 3 and not w[0].isdigit()):
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        if shorten_months:
            w = MONTHS.get(w, w)
        if w not in out:
            out.append(w)
    return out


def relevance(terms, text):
    """Share of terms that start a word in text (0..1). No terms -> 1."""
    if not terms:
        return 1.0
    text = (text or "").lower()
    hits = sum(1 for t in terms if re.search(r"(?<![a-z0-9])" + re.escape(t), text))
    return hits / len(terms)


# ---------------- normalisation ----------------

def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _probability(bid, ask, last):
    """Bid/ask midpoint when a real two-sided book exists, else last trade."""
    if bid and ask and 0 < bid < ask < 1:
        return round((bid + ask) / 2, 4)
    if last and 0 < last < 1:
        return round(last, 4)
    return None


def _normalise_polymarket(m, event=None):
    """Map a raw Polymarket market (optionally with its parent event) to our common shape."""
    if m.get("closed"):
        return None
    last = _num(m.get("lastTradePrice"))
    if last is None:
        try:
            last = _num(json.loads(m.get("outcomePrices") or "[]")[0])
        except (ValueError, TypeError, IndexError):
            last = None
    bid, ask = _num(m.get("bestBid")), _num(m.get("bestAsk"))
    prob = _probability(bid, ask, last)
    if prob is None:
        return None
    tags = [t.get("label") for t in (event or {}).get("tags") or [] if t.get("label")]
    return {
        "source": "polymarket",
        "id": str(m.get("id", "")),
        "title": m.get("question") or (event or {}).get("title") or "Untitled market",
        "category": m.get("category") or (tags[0] if tags else "General"),
        "probability": prob,
        "yes_bid": bid,
        "yes_ask": ask,
        "volume": _num(m.get("volume")) or 0.0,
        "close_date": m.get("endDate", ""),
        "_search_text": " ".join([m.get("question") or "", (event or {}).get("title") or "",
                                  m.get("groupItemTitle") or "", " ".join(tags)]),
    }


def _normalise_kalshi(m, event):
    """Map a raw Kalshi market plus its parent event to our common shape."""
    if m.get("status") not in (None, "active", "open"):
        return None
    bid, ask = _num(m.get("yes_bid_dollars")), _num(m.get("yes_ask_dollars"))
    prob = _probability(bid, ask, _num(m.get("last_price_dollars")))
    if prob is None:
        return None
    title = event.get("title") or m.get("title") or "Untitled market"
    outcome = m.get("yes_sub_title") or ""
    if outcome and outcome.lower() not in title.lower():
        title = f"{title} — {outcome}"
    return {
        "source": "kalshi",
        "id": m.get("ticker", ""),
        "title": title,
        "category": event.get("category") or "General",
        "probability": prob,
        "yes_bid": bid if bid else None,
        "yes_ask": ask if ask and ask < 1 else None,
        "volume": _num(m.get("volume_fp")) or _num(m.get("volume")) or 0.0,
        "close_date": m.get("close_time", ""),
        "_search_text": " ".join([title, event.get("sub_title") or "", event.get("category") or ""]),
    }


# ---------------- Polymarket ----------------

def _polymarket_search(terms, limit):
    """Keyword search via Polymarket's public-search endpoint."""
    resp = requests.get(POLYMARKET_SEARCH_URL, params={
        "q": " ".join(terms), "limit_per_type": limit, "events_status": "active",
    }, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    out = []
    for event in resp.json().get("events") or []:
        for m in event.get("markets") or []:
            n = _normalise_polymarket(m, event)
            if n:
                out.append(n)
    return out


def _polymarket_top(limit):
    resp = requests.get(POLYMARKET_MARKETS_URL, params={
        "limit": limit, "active": "true", "closed": "false",
        "order": "volume24hr", "ascending": "false",
    }, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return [n for n in (_normalise_polymarket(m) for m in resp.json()) if n]


def _polymarket_by_id(market_id):
    resp = requests.get(f"{POLYMARKET_MARKETS_URL}/{market_id}", timeout=REQUEST_TIMEOUT)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return _normalise_polymarket(resp.json())


# ---------------- Kalshi ----------------
# Kalshi's API has no free-text search and ~12k open events. The MCP/RAG
# servers call warm_up() at start, which indexes every open event's title in
# the background (~35s, refreshed every KALSHI_INDEX_TTL). A search matches
# event titles locally, then fetches live prices only for the best
# KALSHI_MAX_EVENTS events. Until the first index is ready, searches fall back
# to matching Kalshi's shorter (but coarser) series list.

_kalshi_index = {"ts": 0.0, "events": [], "building": False}
_index_lock = threading.Lock()
_kalshi_series = {"ts": 0.0, "items": []}
_kalshi_seen = {}  # ticker -> normalised market, from recent searches


def _build_kalshi_index():
    events, cursor = [], None
    while True:
        params = {"limit": 200, "status": "open"}
        if cursor:
            params["cursor"] = cursor
        resp = requests.get(f"{KALSHI_API_URL}/events", params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        body = resp.json()
        for e in body.get("events") or []:
            ticker = e.get("event_ticker") or ""
            if ticker and not ticker.startswith(KALSHI_COMBO_PREFIX):
                events.append({"ticker": ticker, "text": " ".join(
                    [e.get("title") or "", e.get("sub_title") or "", e.get("category") or ""])})
        cursor = body.get("cursor")
        if not cursor or not body.get("events"):
            return events


def refresh_kalshi_index():
    """Rebuild the Kalshi event index; keeps the previous one if Kalshi is unreachable."""
    with _index_lock:
        if _kalshi_index["building"]:
            return
        _kalshi_index["building"] = True
    try:
        _kalshi_index.update(ts=time.time(), events=_build_kalshi_index())
    except requests.RequestException:
        pass
    finally:
        _kalshi_index["building"] = False


def warm_up():
    """Start (re)building the Kalshi event index in the background. Call at server start."""
    threading.Thread(target=refresh_kalshi_index, daemon=True).start()


def _kalshi_series_list():
    if time.time() - _kalshi_series["ts"] < KALSHI_SERIES_TTL and _kalshi_series["items"]:
        return _kalshi_series["items"]
    try:
        resp = requests.get(f"{KALSHI_API_URL}/series", timeout=KALSHI_SERIES_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException:
        if _kalshi_series["items"]:
            return _kalshi_series["items"]  # stale copy beats nothing
        raise
    items = [{"ticker": x.get("ticker", ""),
              "text": " ".join([x.get("title") or "", x.get("category") or "", " ".join(x.get("tags") or [])])}
             for x in resp.json().get("series") or []
             if x.get("ticker") and not x["ticker"].startswith(KALSHI_COMBO_PREFIX)]
    _kalshi_series.update(ts=time.time(), items=items)
    return items


def _kalshi_normalise_events(events):
    markets = []
    for event in events:
        if (event.get("event_ticker") or "").startswith(KALSHI_COMBO_PREFIX):
            continue
        for m in event.get("markets") or []:
            n = _normalise_kalshi(m, event)
            if n:
                markets.append(n)
                _kalshi_seen[n["id"]] = n
    return markets


def _kalshi_events(params):
    resp = requests.get(f"{KALSHI_API_URL}/events", params=dict(params, status="open", with_nested_markets="true"),
                        timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return _kalshi_normalise_events(resp.json().get("events") or [])


def _kalshi_event(ticker):
    resp = requests.get(f"{KALSHI_API_URL}/events/{ticker}", params={"with_nested_markets": "true"},
                        timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    body = resp.json()
    event = body.get("event") or {}
    event.setdefault("markets", body.get("markets") or [])
    return _kalshi_normalise_events([event])


def _best(items, terms, n):
    scored = [(relevance(terms, x["text"]), len(x["text"]), x["ticker"]) for x in items]
    scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: (-x[0], x[1]))  # most terms matched, then most specific
    return [t for _, _, t in scored[:n]]


def _parallel(fn, tickers):
    if not tickers:
        return []
    with ThreadPoolExecutor(max_workers=len(tickers)) as pool:
        return [m for batch in pool.map(fn, tickers) for m in batch]


def _kalshi_search(terms):
    if _kalshi_index["events"]:
        if time.time() - _kalshi_index["ts"] > KALSHI_INDEX_TTL:
            warm_up()  # refresh in the background; keep serving the current index
        return _parallel(_kalshi_event, _best(_kalshi_index["events"], terms, KALSHI_MAX_EVENTS))
    if not _kalshi_index["building"]:
        warm_up()
    series = _best(_kalshi_series_list(), terms, KALSHI_MAX_SERIES)
    return _parallel(lambda t: _kalshi_events({"series_ticker": t}), series)


def _kalshi_top():
    return _kalshi_events({"limit": 200})


def _kalshi_by_ticker(ticker):
    if ticker in _kalshi_seen:
        return _kalshi_seen[ticker]
    resp = requests.get(f"{KALSHI_API_URL}/markets/{ticker}", timeout=REQUEST_TIMEOUT)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    m = resp.json().get("market") or {}
    event = {"title": m.get("title"), "category": None}
    try:
        er = requests.get(f"{KALSHI_API_URL}/events/{m.get('event_ticker')}", timeout=REQUEST_TIMEOUT)
        if er.ok:
            event = er.json().get("event") or event
    except requests.RequestException:
        pass
    return _normalise_kalshi(m, event)


# ---------------- public API ----------------

def _rank(markets, terms, limit):
    """
    Keep relevant markets only, best match first. Volume is only compared
    within a source (Polymarket reports dollars, Kalshi contracts), so equally
    relevant results alternate between sources instead of one swamping the other.
    """
    scored = []
    for m in markets:
        score = relevance(terms, m.get("_search_text") or m["title"])
        if score >= MIN_RELEVANCE:
            scored.append(dict(m, relevance=round(score, 2)))
    scored.sort(key=lambda m: (-m["relevance"], -m["volume"]))
    seen = {}
    for m in scored:
        key = (m["relevance"], m["source"])
        m["_source_rank"] = seen[key] = seen.get(key, -1) + 1
    scored.sort(key=lambda m: (-m["relevance"], m["_source_rank"]))
    return scored[:limit]


def _public(markets):
    return [{k: v for k, v in m.items() if not k.startswith("_")} for m in markets]


def fetch_markets(source="both", query=None, category=None, limit=20):
    """
    Fetch a list of markets from Polymarket, Kalshi, or both.
    With a query, only markets containing at least MIN_RELEVANCE of its
    keywords are returned, so callers never receive unrelated markets.
    Falls back to the most recent cached copy if a live fetch fails.
    Returns: (markets: list[dict], meta: dict) where meta describes freshness.
    """
    terms = keywords(query)
    cache_key = f"markets:{source}:{' '.join(terms)}:{category}:{limit}"
    results = []
    errors = []

    if source in ("polymarket", "both"):
        try:
            results.extend(_polymarket_search(keywords(query, shorten_months=False), limit)
                           if terms else _polymarket_top(limit))
        except Exception as exc:
            errors.append(f"polymarket: {exc}")

    if source in ("kalshi", "both"):
        try:
            results.extend(_kalshi_search(terms) if terms else _kalshi_top())
        except Exception as exc:
            errors.append(f"kalshi: {exc}")

    if category:
        results = [m for m in results if category.lower() in (m["category"] or "").lower()]

    results = _public(_rank(results, terms, limit))

    if results:
        _cache_set(cache_key, results)
        return results, {"fresh": True, "source": "live", "errors": errors}

    # Nothing live (fetch failed, or no relevant market) -- fall back to cache
    cached, _ = _cache_get(cache_key)
    if cached:
        return cached, {"fresh": False, "source": "cache", "errors": errors}

    return [], {"fresh": False, "source": "none", "errors": errors}


def get_market_by_id(market_id, source="both"):
    """
    Look up one market directly. Polymarket ids are numeric; Kalshi ids are
    tickers such as KXNEWPOPE-70-PPIZ. Malformed ids are rejected before
    they reach an upstream URL.
    """
    market_id = str(market_id or "").strip()
    meta = {"fresh": True, "source": "live", "errors": []}
    try:
        if POLYMARKET_ID_RE.match(market_id) and source in ("polymarket", "both"):
            market = _polymarket_by_id(market_id)
        elif KALSHI_TICKER_RE.match(market_id) and source in ("kalshi", "both"):
            market = _kalshi_by_ticker(market_id)
        else:
            meta["errors"].append("id is not a valid Polymarket id or Kalshi ticker for this source")
            return None, meta
    except requests.RequestException as exc:
        return None, {"fresh": False, "source": "none", "errors": [str(exc)]}
    return (_public([market])[0] if market else None), meta


if __name__ == "__main__":
    # Quick manual test: python market_data.py [query]
    import sys
    q = " ".join(sys.argv[1:]) or None
    data, meta = fetch_markets(source="both", query=q, limit=5)
    print(f"meta: {meta}")
    for m in data:
        print(f"  [{m['source']}] {m['title']} (p={m['probability']:.2f}, "
              f"bid={m['yes_bid']}, ask={m['yes_ask']}, vol={m['volume']:.0f})")
