"""
Shared live market data layer (Release 1, Task 1).

Fetches live market data from Polymarket and Manifold Markets' public,
no-authentication APIs, and caches results locally to protect against
rate limits, downtime, or slow responses.

Used by:
  - ai-services/mcp-server/app.py  (tools: get_market_price, search_markets, get_market_history)
  - ai-services/rag-server/app.py  (retrieval context for grounded answers)

This module is NOT its own HTTP service -- it's a plain Python module
imported directly by the MCP and RAG servers, since both run on the
same local host and don't need network isolation from each other.
"""
import json
import os
import time
import requests

CACHE_PATH = os.path.join(os.path.dirname(__file__), "market_cache.json")
CACHE_TTL_SECONDS = int(os.getenv("MARKET_CACHE_TTL", "300"))  # 5 min default

POLYMARKET_URL = "https://gamma-api.polymarket.com/markets"
MANIFOLD_URL = "https://api.manifold.markets/v0/markets"
MANIFOLD_SEARCH_URL = "https://api.manifold.markets/v0/search-markets"

REQUEST_TIMEOUT = 8  # seconds


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


def _normalise_polymarket(raw):
    """Map a raw Polymarket market object to our common shape."""
    out = []
    for m in raw:
        try:
            out.append({
                "source": "polymarket",
                "id": m.get("id") or m.get("conditionId", ""),
                "title": m.get("question") or m.get("title", "Untitled market"),
                "category": m.get("category", "General"),
                "probability": float(m.get("lastTradePrice") or m.get("outcomePrices", [0])[0] or 0),
                "volume": float(m.get("volume") or 0),
                "close_date": m.get("endDate", ""),
            })
        except (ValueError, TypeError, IndexError):
            continue
    return out


def _normalise_manifold(raw):
    """Map a raw Manifold market object to our common shape."""
    out = []
    for m in raw:
        try:
            out.append({
                "source": "manifold",
                "id": m.get("id", ""),
                "title": m.get("question", "Untitled market"),
                "category": (m.get("groupSlugs") or ["General"])[0],
                "probability": float(m.get("probability") or 0),
                "volume": float(m.get("volume") or 0),
                "close_date": m.get("closeTime", ""),
            })
        except (ValueError, TypeError, IndexError):
            continue
    return out


def fetch_markets(source="both", query=None, category=None, limit=20):
    """
    Fetch a list of markets from Polymarket, Manifold, or both.
    Falls back to the most recent cached copy if a live fetch fails.
    Returns: (markets: list[dict], meta: dict) where meta describes freshness.
    """
    cache_key = f"markets:{source}:{query}:{category}:{limit}"
    results = []
    errors = []

    def try_polymarket():
        params = {"limit": limit, "active": "true"}
        if query:
            params["search"] = query
        resp = requests.get(POLYMARKET_URL, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return _normalise_polymarket(resp.json())

    def try_manifold():
        if query:
            resp = requests.get(MANIFOLD_SEARCH_URL, params={"term": query, "limit": limit}, timeout=REQUEST_TIMEOUT)
        else:
            resp = requests.get(MANIFOLD_URL, params={"limit": limit}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return _normalise_manifold(resp.json())

    if source in ("polymarket", "both"):
        try:
            results.extend(try_polymarket())
        except Exception as exc:
            errors.append(f"polymarket: {exc}")

    if source in ("manifold", "both"):
        try:
            results.extend(try_manifold())
        except Exception as exc:
            errors.append(f"manifold: {exc}")

    if category:
        results = [m for m in results if category.lower() in (m["category"] or "").lower()]

    if results:
        _cache_set(cache_key, results)
        return results, {"fresh": True, "source": "live", "errors": errors}

    # Live fetch failed or returned nothing -- fall back to cache
    cached, _ = _cache_get(cache_key)
    if cached:
        return cached, {"fresh": False, "source": "cache", "errors": errors}

    return [], {"fresh": False, "source": "none", "errors": errors}


def get_market_by_id(market_id, source="both"):
    """Find a single market by id across the fetched set (best-effort)."""
    markets, meta = fetch_markets(source=source, limit=100)
    for m in markets:
        if str(m["id"]) == str(market_id):
            return m, meta
    return None, meta


if __name__ == "__main__":
    # Quick manual test: python market_data.py
    data, meta = fetch_markets(source="both", limit=5)
    print(f"meta: {meta}")
    for m in data:
        print(f"  [{m['source']}] {m['title']} (p={m['probability']:.2f}, vol={m['volume']})")