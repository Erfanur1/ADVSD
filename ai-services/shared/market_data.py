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

CACHE_PATH = os.path.join(os.path.dirname(__file__), "market_cache.json")
CACHE_TTL_SECONDS = int(os.getenv("MARKET_CACHE_TTL", "300"))  # 5 min default

POLYMARKET_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
POLYMARKET_SEARCH_URL = "https://gamma-api.polymarket.com/public-search"
KALSHI_API_URL = "https://api.elections.kalshi.com/trade-api/v2"

KALSHI_EVENT_PAGES = 8        # 200 events per page
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

def keywords(text):
    """Lower-cased content words of a query, with a light plural strip."""
    words = re.findall(r"[a-z0-9$%.]+", (text or "").lower())
    out = []
    for w in words:
        w = w.strip(".")
        if not w or w in STOPWORDS or (len(w) < 3 and not w[0].isdigit()):
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
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
# Kalshi's API has no free-text search, so we page through the open events
# once, keep the flattened market list in memory for CACHE_TTL_SECONDS, and
# search it locally.

_kalshi_catalog = {"ts": 0.0, "markets": []}


def _kalshi_markets():
    if time.time() - _kalshi_catalog["ts"] < CACHE_TTL_SECONDS and _kalshi_catalog["markets"]:
        return _kalshi_catalog["markets"]
    markets, cursor = [], None
    try:
        for _ in range(KALSHI_EVENT_PAGES):
            params = {"limit": 200, "status": "open", "with_nested_markets": "true"}
            if cursor:
                params["cursor"] = cursor
            resp = requests.get(f"{KALSHI_API_URL}/events", params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            body = resp.json()
            for event in body.get("events") or []:
                if (event.get("event_ticker") or "").startswith(KALSHI_COMBO_PREFIX):
                    continue
                for m in event.get("markets") or []:
                    n = _normalise_kalshi(m, event)
                    if n:
                        markets.append(n)
            cursor = body.get("cursor")
            if not cursor:
                break
    except requests.RequestException:
        if _kalshi_catalog["markets"]:
            return _kalshi_catalog["markets"]  # stale copy beats nothing
        raise
    _kalshi_catalog.update(ts=time.time(), markets=markets)
    return markets


def _kalshi_by_ticker(ticker):
    for m in _kalshi_catalog["markets"]:
        if m["id"] == ticker:
            return m
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
            results.extend(_polymarket_search(terms, limit) if terms else _polymarket_top(limit))
        except Exception as exc:
            errors.append(f"polymarket: {exc}")

    if source in ("kalshi", "both"):
        try:
            results.extend(_kalshi_markets())
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
