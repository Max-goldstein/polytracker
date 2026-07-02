from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timezone
import requests
import json
import time
import os

app = FastAPI(title="PolyTracker")

GAMMA = "https://gamma-api.polymarket.com"
CLOB  = "https://clob.polymarket.com"
UA    = {"User-Agent": "PolyTracker/1.0"}

CATEGORIES = [
    {"name": "All",         "slug": "",            "emoji": "🔥"},
    {"name": "Sports",      "slug": "sports",      "emoji": "⚽"},
    {"name": "Politics",    "slug": "politics",    "emoji": "🏛"},
    {"name": "Geopolitics", "slug": "geopolitics", "emoji": "🌍"},
    {"name": "Crypto",      "slug": "crypto",      "emoji": "₿"},
    {"name": "Economics",   "slug": "economics",   "emoji": "📊"},
    {"name": "Technology",  "slug": "technology",  "emoji": "💻"},
    {"name": "Science",     "slug": "science",     "emoji": "🔬"},
]

_cache: dict = {}
CACHE_TTL = 90  # seconds


def _cached(key: str, fn):
    now = time.time()
    if key in _cache and now - _cache[key][1] < CACHE_TTL:
        return _cache[key][0]
    data = fn()
    _cache[key] = (data, now)
    return data


def _get(base: str, path: str, params: dict = None):
    r = requests.get(f"{base}{path}", params=params, headers=UA, timeout=12)
    r.raise_for_status()
    return r.json()


def _f(val, default=0.0) -> float:
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return default


def _clob_ids(m: dict) -> list:
    ids = m.get("clobTokenIds", [])
    if isinstance(ids, str):
        try:
            ids = json.loads(ids)
        except Exception:
            ids = []
    return ids if isinstance(ids, list) else []


def _days_until(end_date: str):
    if not end_date:
        return None
    try:
        dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        return max((dt - datetime.now(timezone.utc)).days, 0)
    except Exception:
        return None


def _expires_within(end_date: str, hours: int) -> bool:
    if not end_date:
        return False
    try:
        dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        return (dt - datetime.now(timezone.utc)).total_seconds() < hours * 3600
    except Exception:
        return False


def _is_valid(m: dict) -> bool:
    """Exclude closed, archived, and near-resolved (0/100%) markets."""
    if not m.get("active", True):
        return False
    if m.get("closed", False) or m.get("archived", False):
        return False
    price = _f(m.get("lastTradePrice"))
    # Omit markets at 0% or 100% (resolved or trivially certain)
    if price <= 0.02 or price >= 0.98:
        return False
    return True


def _fmt(m: dict, score: int = None, signals: list = None) -> dict:
    p = _f(m.get("lastTradePrice"))
    rec = {
        "id":           m.get("id"),
        "conditionId":  m.get("conditionId"),
        "question":     m.get("question", ""),
        "slug":         m.get("slug", ""),
        "yesPrice":     round(p, 4),
        "noPrice":      round(1 - p, 4),
        "volume24h":    _f(m.get("volume24hr")),
        "volumeTotal":  _f(m.get("volume")) or _f(m.get("volumeClob")),
        "liquidity":    _f(m.get("liquidity")),
        "endDate":      m.get("endDate", ""),
        "daysLeft":     _days_until(m.get("endDate", "")),
        "clobTokenIds": _clob_ids(m),
    }
    if score is not None:
        rec["score"]   = score
        rec["signals"] = signals or []
    return rec


# ── category inference ────────────────────────────────────────────────────────

_SPORTS_STRONG = [
    ' vs ', 'vs.', 'halftime', 'half time', 'score:', 'leading at', 'win on ',
    'nfl ', 'nba ', 'mlb ', 'nhl ', 'mls ', 'bo3', 'bo5', 'esport', 'cs2',
    'dota ', 'valorant', 'league of legends', 'exact score', 'at halftime',
    'overtime', 'shutout', 'hat trick', 'pga ', 'lpga ', 'u.s. open',
    'us open golf', 'super bowl', 'champions league', 'world cup',
    'wimbledon', 'grand slam', 'tour de france',
    'quarterback', 'touchdown', 'strikeout', 'batting',
    ' match', 'game winner', 'win the series', 'win the game',
    'goal scorer', 'top scorer', 'top goalscorer',
]
_SPORTS_SOFT = [
    'nba', 'nfl', 'mlb', 'nhl', 'fifa', 'soccer', 'basketball', 'baseball',
    'football', 'tennis', 'golf', 'hockey', 'cricket', 'rugby', 'boxing',
    'playoff', 'championship', 'pennant', 'stanley cup', 'world series',
    'regular season', 'open?', ' open ', 'rookie of the year', 'mvp award',
    'doubles for the', 'home runs', 'innings', 'yards', 'sacks', 'touchdowns',
    'ipl ', 'premier league', 'bundesliga', 'serie a', 'la liga',
    'esports', ' iem ', 'cologne major', 'blast', 'furia', '9z',
    'win the 2026', 'win the 2025', 'win the 2024',
]
_GEO = [
    'war', 'ceasefire', 'missile', 'nuclear', 'invasion', 'troops',
    'capture ', 'occupy', 'bomb', 'sanction', 'peace deal', 'peace agreement',
    'signing ceremony', 'diplomatic meeting', 'iran', 'russia ', 'ukraine',
    'israel', 'taiwan', 'north korea', 'nato ', 'hamas', 'hezbollah',
    'military strike', 'military operation', 'armed', 'warhead', 'drone strike',
    'geopolit',
]
_POL = [
    'election', 'president', 'senator', 'congress', 'vote ', 'democrat',
    'republican', 'trump', 'biden', 'harris', 'prime minister', 'parliament',
    'governor', 'polling', 'primary ', 'cabinet', 'legislation', 'bill pass',
    'impeach', 'resign', 'nominee',
]
_CRYPTO = [
    'bitcoin', 'btc ', '$btc', 'ethereum', 'eth ', '$eth', 'solana', 'sol ',
    'doge', 'xrp ', 'crypto', 'blockchain', 'defi', 'token ', 'altcoin',
    'nft ', 'web3', 'stablecoin', 'coinbase', 'binance', 'uniswap',
]
_ECON = [
    'gdp', 'inflation', 'federal reserve', 'interest rate', 'recession',
    'unemployment', 'tariff', 'brics', 'oil price', 'dollarize', 'ipo ',
    's&p ', 'dow jones', 'nasdaq', 'treasury', 'cpi ', 'ppi ', 'trade war',
]
_TECH = [
    'openai', 'gpt-', ' llm', 'artificial intelligence', ' ai model',
    'eip-', 'semiconductor', 'apple stock', 'google stock', 'microsoft',
    'chatgpt', 'gemini', 'anthropic', 'chip ', 'data center',
]
_SCI = [
    'alien', 'ufo', 'pandemic', 'vaccine', 'nasa ', 'mars ', 'cancer ',
    'genome', 'protein ', 'climate goal', 'asteroid', 'spacex', 'moon landing',
]


def _infer_cat(question: str) -> str:
    q = question.lower()
    # Strong sports indicators first — largest source of false positives
    if any(w in q for w in _SPORTS_STRONG):
        return 'sports'
    # Geopolitics before politics (more specific)
    if any(w in q for w in _GEO):
        return 'geopolitics'
    # Remaining categories
    if any(w in q for w in _CRYPTO):
        return 'crypto'
    if any(w in q for w in _ECON):
        return 'economics'
    if any(w in q for w in _TECH):
        return 'technology'
    if any(w in q for w in _SCI):
        return 'science'
    if any(w in q for w in _POL):
        return 'politics'
    # Soft sports check last
    if any(w in q for w in _SPORTS_SOFT):
        return 'sports'
    return 'other'


_CAT_CONF_BONUS = {
    'geopolitics': 20, 'politics': 18, 'economics': 13,
    'crypto': 11,      'technology': 9, 'science': 7,
    'other': 4,        'sports': 0,
}


def _build_suggestion(m: dict, insider_score: int, signals: list):
    question  = m.get('question', '')
    days_left = _days_until(m.get('endDate', ''))
    yes_price = _f(m.get('lastTradePrice'))
    vol24     = _f(m.get('volume24hr'))
    category  = _infer_cat(question)

    # Hard exclusions
    if category == 'sports':
        return None
    if days_left is not None and days_left < 3:
        return None

    # ── Confidence score (0–100) ───────────────────────────────────────────────
    conf = insider_score * 5
    conf += _CAT_CONF_BONUS.get(category, 4)
    if days_left is not None:
        if 7 <= days_left <= 45:     conf += 15
        elif 45 < days_left <= 120:  conf += 10
        elif 3 <= days_left < 7:     conf += 4
        else:                        conf += 7   # > 120 days
    if vol24 > 50_000:   conf += 5
    elif vol24 > 10_000: conf += 3
    elif vol24 > 2_000:  conf += 1
    if yes_price > 0.88 or yes_price < 0.12:
        conf = int(conf * 0.72)

    conf = min(int(conf), 100)
    if conf < 40:
        return None

    # ── Direction: follow the smart money ─────────────────────────────────────
    direction   = 'YES' if yes_price >= 0.5 else 'NO'
    entry_price = yes_price if direction == 'YES' else 1 - yes_price

    # ── Half-Kelly sizing ──────────────────────────────────────────────────────
    edge      = max(0.0, (conf - 40) / 60 * 0.10)
    est_prob  = min(0.95, entry_price + edge)
    net_odds  = (1 - entry_price) / entry_price if 0 < entry_price < 1 else 0
    if net_odds > 0:
        kelly_full = (net_odds * est_prob - (1 - est_prob)) / net_odds
    else:
        kelly_full = 0
    half_kelly_pct = round(min(max(kelly_full / 2, 0.0), 0.20) * 100, 1)

    if half_kelly_pct < 1.0:
        return None

    if half_kelly_pct >= 10:   risk = 'Aggressive'
    elif half_kelly_pct >= 5:  risk = 'Moderate'
    else:                      risk = 'Conservative'

    return {
        'id':            m.get('id'),
        'conditionId':   m.get('conditionId'),
        'question':      question,
        'slug':          m.get('slug', ''),
        'category':      category,
        'confidence':    conf,
        'direction':     direction,
        'yesPrice':      round(yes_price, 4),
        'noPrice':       round(1 - yes_price, 4),
        'entryPrice':    round(entry_price, 4),
        'estimatedProb': round(est_prob, 4),
        'edge':          round(edge, 4),
        'halfKellyPct':  half_kelly_pct,
        'risk':          risk,
        'daysLeft':      days_left,
        'endDate':       m.get('endDate', ''),
        'volume24h':     vol24,
        'volumeTotal':   _f(m.get('volume')) or _f(m.get('volumeClob')),
        'signals':       signals,
        'clobTokenIds':  _clob_ids(m),
    }


def _score(m: dict):
    vol24     = _f(m.get("volume24hr"))
    vol_total = _f(m.get("volume")) or _f(m.get("volumeClob"))
    liquidity = _f(m.get("liquidity"))
    last_px   = _f(m.get("lastTradePrice"))
    end_date  = m.get("endDate", "")

    if vol24 < 500 or vol_total < 1000:
        return 0, []

    score, signals = 0, []
    soon = _expires_within(end_date, 24)

    # 1. Volume concentration
    if vol_total > 0:
        ratio = vol24 / vol_total
        if ratio > 0.65 and vol24 > 15_000:
            score += 5
            signals.append({"type": "VOLUME_SURGE", "severity": "HIGH",
                "detail": f"{ratio*100:.0f}% of all-time volume traded in last 24h (${vol24:,.0f})"})
        elif ratio > 0.45 and vol24 > 5_000:
            score += 3
            signals.append({"type": "VOLUME_SURGE", "severity": "MEDIUM",
                "detail": f"{ratio*100:.0f}% of all-time volume in last 24h (${vol24:,.0f})"})
        elif ratio > 0.30 and vol24 > 2_000:
            score += 1
            signals.append({"type": "VOLUME_SURGE", "severity": "LOW",
                "detail": f"{ratio*100:.0f}% of all-time volume in last 24h"})

    # 2. Extreme pricing (skip near-expiry — it's natural for prices to be extreme then)
    if last_px > 0 and vol24 > 2_000 and not soon:
        if last_px > 0.90 or last_px < 0.10:
            score += 4
            d = "YES" if last_px > 0.5 else "NO"
            signals.append({"type": "EXTREME_PRICING", "severity": "HIGH",
                "detail": f"Market pinned to {d} at {last_px*100:.0f}% with ${vol24:,.0f} 24h volume"})
        elif last_px > 0.82 or last_px < 0.18:
            score += 2
            d = "YES" if last_px > 0.5 else "NO"
            signals.append({"type": "EXTREME_PRICING", "severity": "MEDIUM",
                "detail": f"Strong {d} lean ({last_px*100:.0f}%) with ${vol24:,.0f} 24h volume"})

    # 3. Thin order book vs volume
    if liquidity > 0 and vol24 > 5_000:
        r = liquidity / vol24
        if r < 0.03:
            score += 3
            signals.append({"type": "THIN_BOOK", "severity": "HIGH",
                "detail": f"Order book (${liquidity:,.0f}) is {r:.1%} of 24h volume — suggests whale directional bets"})
        elif r < 0.10:
            score += 1
            signals.append({"type": "THIN_BOOK", "severity": "LOW",
                "detail": f"Low liquidity-to-volume ratio ({r:.1%})"})

    return score, signals


def _fetch_markets(tag: str, limit: int = 1000) -> list:
    """Return up to `limit` valid markets. API is capped at 100 records per page."""
    PAGE = 100  # Polymarket API hard cap per request

    if not tag:
        valid, offset = [], 0
        while len(valid) < limit:
            batch = _get(GAMMA, "/markets", {
                "active": "true", "limit": PAGE, "offset": offset,
                "order": "volume24hr", "ascending": "false",
            })
            if not batch:
                break
            valid.extend(m for m in batch if _is_valid(m))
            if len(batch) < PAGE:
                break
            offset += PAGE
        valid.sort(key=lambda x: _f(x.get("volume24hr")), reverse=True)
        return valid[:limit]
    else:
        seen, markets, offset = set(), [], 0
        while len(markets) < limit:
            events = _get(GAMMA, "/events", {
                "tag_slug": tag, "active": "true",
                "limit": PAGE, "offset": offset,
                "order": "volume24hr", "ascending": "false",
            })
            if not events:
                break
            for ev in events:
                for m in ev.get("markets", []):
                    mid = m.get("id")
                    if mid and mid not in seen and _is_valid(m):
                        seen.add(mid)
                        markets.append(m)
            if len(events) < PAGE:
                break
            offset += PAGE
        markets.sort(key=lambda x: _f(x.get("volume24hr")), reverse=True)
        return markets[:limit]


# ── routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/api/categories")
def categories():
    return {"categories": CATEGORIES}


@app.get("/api/trending")
def trending(
    tag:   str = Query(""),
    limit: int = Query(1000, ge=1, le=1000),
):
    try:
        markets = _cached(f"t:{tag}:{limit}", lambda: _fetch_markets(tag, limit))
        return {"markets": [_fmt(m) for m in markets], "count": len(markets)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/insider")
def insider(
    tag:       str = Query(""),
    limit:     int = Query(1000),
    min_score: int = Query(3),
):
    def _run():
        markets = _fetch_markets(tag, limit)
        flagged = []
        for m in markets:
            score, sigs = _score(m)
            if score >= min_score:
                flagged.append(_fmt(m, score, sigs))
        flagged.sort(key=lambda x: x["score"], reverse=True)
        return flagged[:200]

    try:
        return {"markets": _cached(f"i:{tag}:{min_score}", _run), "count": 0}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/suggestions")
def suggestions(
    tag:            str = Query(""),
    min_confidence: int = Query(40),
):
    def _run():
        markets = _fetch_markets(tag, 1000)
        results = []
        for m in markets:
            score, sigs = _score(m)
            if score < 2:
                continue
            s = _build_suggestion(m, score, sigs)
            if s and s['confidence'] >= min_confidence:
                results.append(s)
        results.sort(key=lambda x: x['confidence'], reverse=True)
        return results[:100]

    try:
        data = _cached(f"sugg:{tag}:{min_confidence}", _run)
        return {"suggestions": data, "count": len(data)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/stats")
def stats():
    def _run():
        valid = _fetch_markets("", 1000)
        return {
            "markets_tracked":  len(valid),
            "total_24h_volume": sum(_f(m.get("volume24hr")) for m in valid),
            "insider_signals":  sum(1 for m in valid if _score(m)[0] >= 3),
        }
    try:
        return _cached("stats", _run)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/trades/{condition_id}")
def trades(condition_id: str, limit: int = 100):
    try:
        data  = _get(CLOB, "/trades", {"market": condition_id, "limit": limit})
        rows  = data if isinstance(data, list) else data.get("data", [])
        wallets: dict = {}
        for t in rows:
            for key in ("maker_address", "taker_address"):
                addr = t.get(key, "")
                if not addr or addr == "0x" + "0" * 40:
                    continue
                size  = _f(t.get("size"))
                price = _f(t.get("price"))
                val   = size * price if 0 < price <= 1 else size * price / 100
                if addr not in wallets:
                    wallets[addr] = {"address": addr, "value": 0.0, "trades": 0}
                wallets[addr]["value"]  += val
                wallets[addr]["trades"] += 1

        top = sorted(wallets.values(), key=lambda x: x["value"], reverse=True)[:10]
        total_val = sum(w["value"] for w in top)
        if total_val > 0:
            for w in top:
                w["share"] = round(w["value"] / total_val, 4)
        top3 = sum(w.get("share", 0) for w in top[:3])
        return {
            "trades": rows[:50], "wallets": top,
            "total_trades": len(rows),
            "top3_share": round(top3, 4),
            "concentration_signal": top3 > 0.70,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

