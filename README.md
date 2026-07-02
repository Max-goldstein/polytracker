# PolyTracker

A real-time web dashboard for monitoring trending [Polymarket](https://polymarket.com) prediction markets and flagging suspected insider trading activity.

---

## What It Does

PolyTracker pulls live data from Polymarket's public APIs and presents two views:

- **Trending** — top markets by 24-hour volume, organized by category (Sports, Politics, Crypto, etc.)
- **Insider Signals** — markets that exhibit statistically unusual patterns consistent with informed trading: sudden volume concentration, extreme price skew on high volume, and thin order books relative to trading activity

Markets with resolved or near-resolved prices (0% or 100% YES) are automatically filtered out, as are closed and archived markets.

---

## Project Structure

```
PolyTracker/
├── app.py              # FastAPI backend — data fetching, filtering, scoring, API routes
├── start.sh            # Launch script
├── requirements.txt    # Python dependencies
├── static/
│   └── index.html      # Single-file frontend (HTML + CSS + JS, no framework)
├── Api.py              # Original Iran war market script (legacy)
├── GenerateTop500.py   # Original top-500 market fetcher (legacy)
└── HighestSwings.py    # Original price swing tracker (legacy)
```

---

## Setup

**Requirements:** Python 3.11+

```bash
# Install dependencies
pip3 install -r requirements.txt

# Start the server
./start.sh
```

Then open **http://localhost:8765** in your browser.

The server runs with `--reload` by default, so changes to `app.py` or `static/index.html` take effect immediately without restarting.

---

## API Reference

All endpoints are served at `http://localhost:8765`.

### `GET /api/categories`
Returns the list of available category filters.

```json
{
  "categories": [
    { "name": "All",         "slug": "",            "emoji": "🔥" },
    { "name": "Sports",      "slug": "sports",      "emoji": "⚽" },
    { "name": "Politics",    "slug": "politics",    "emoji": "🏛"  },
    { "name": "Geopolitics", "slug": "geopolitics", "emoji": "🌍" },
    { "name": "Crypto",      "slug": "crypto",      "emoji": "₿"  },
    { "name": "Economics",   "slug": "economics",   "emoji": "📊" },
    { "name": "Technology",  "slug": "technology",  "emoji": "💻" },
    { "name": "Science",     "slug": "science",     "emoji": "🔬" }
  ]
}
```

---

### `GET /api/trending`
Top 50 active markets by 24-hour volume, with 0/100% markets excluded.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tag`     | string | `""` | Category slug (empty = All) |
| `limit`   | int | `50` | Max markets to return (1–200) |

**Response:**
```json
{
  "count": 50,
  "markets": [
    {
      "id": "...",
      "conditionId": "0x...",
      "question": "Will Argentina win the 2026 FIFA World Cup?",
      "slug": "will-argentina-win-the-2026-fifa-world-cup",
      "yesPrice": 0.12,
      "noPrice": 0.88,
      "volume24h": 142340.50,
      "volumeTotal": 890210.00,
      "liquidity": 45200.00,
      "endDate": "2026-07-20T00:00:00Z",
      "daysLeft": 32,
      "clobTokenIds": ["..."]
    }
  ]
}
```

---

### `GET /api/insider`
Markets flagged for suspicious activity, scored and sorted by risk score (highest first).

| Parameter   | Type | Default | Description |
|-------------|------|---------|-------------|
| `tag`       | string | `""` | Category slug |
| `limit`     | int | `100` | Markets to scan |
| `min_score` | int | `3`   | Minimum risk score to include |

**Response:**
```json
{
  "count": 12,
  "markets": [
    {
      "id": "...",
      "question": "Will Israel strike Iran before July?",
      "yesPrice": 0.91,
      "noPrice": 0.09,
      "volume24h": 145000,
      "volumeTotal": 167000,
      "score": 9,
      "signals": [
        {
          "type": "VOLUME_SURGE",
          "severity": "HIGH",
          "detail": "87% of all-time volume traded in last 24h ($145,000)"
        },
        {
          "type": "EXTREME_PRICING",
          "severity": "HIGH",
          "detail": "Market pinned to YES at 91% with $145,000 24h volume"
        }
      ]
    }
  ]
}
```

---

### `GET /api/trades/{condition_id}`
Recent trades for a specific market from the Polymarket CLOB, with wallet concentration analysis.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit`   | int | `100` | Max trades to fetch |

**Response:**
```json
{
  "total_trades": 47,
  "top3_share": 0.82,
  "concentration_signal": true,
  "wallets": [
    { "address": "0xabc...", "value": 58000.0, "trades": 3, "share": 0.61 }
  ],
  "trades": [
    {
      "side": "BUY",
      "maker_address": "0xabc...",
      "size": "5000",
      "price": "0.91",
      "match_time": 1718700000
    }
  ]
}
```

---

### `GET /api/stats`
Summary counts across the top 200 markets.

```json
{
  "markets_tracked": 55,
  "total_24h_volume": 47703803.25,
  "insider_signals": 42
}
```

---

## Insider Signal Detection

Each market is scored out of **12 points** across three independent signals. Markets scoring ≥ 3 appear in the Insider Signals tab.

### Signal 1 — Volume Surge (up to 5 pts)
Flags markets where an abnormally large fraction of all-time volume was traded in the last 24 hours.

| Condition | Score |
|-----------|-------|
| > 65% of all-time volume in 24h AND 24h vol > $15k | +5 (HIGH) |
| > 45% of all-time volume in 24h AND 24h vol > $5k  | +3 (MEDIUM) |
| > 30% of all-time volume in 24h AND 24h vol > $2k  | +1 (LOW) |

**Rationale:** An informed trader who knows something before the public will bet quickly, creating a disproportionate spike in recent volume relative to the market's history.

---

### Signal 2 — Extreme Pricing (up to 4 pts)
Flags markets where the consensus price is highly skewed (> 82% YES or < 18% NO) on significant recent volume. Markets expiring within 24 hours are excluded since extreme prices are expected near resolution.

| Condition | Score |
|-----------|-------|
| Price > 90% or < 10% AND 24h vol > $2k | +4 (HIGH) |
| Price > 82% or < 18% AND 24h vol > $2k | +2 (MEDIUM) |

**Rationale:** A market priced at 91% with heavy recent volume means traders are very confident — confidence that might stem from non-public information rather than publicly available analysis.

---

### Signal 3 — Thin Order Book (up to 3 pts)
Flags markets where available liquidity is extremely low relative to 24-hour trading volume, suggesting large one-directional bets have been placed rather than balanced two-sided market making.

| Condition | Score |
|-----------|-------|
| Liquidity < 3% of 24h volume AND 24h vol > $5k  | +3 (HIGH) |
| Liquidity < 10% of 24h volume AND 24h vol > $5k | +1 (LOW) |

**Rationale:** Market makers maintain liquidity in proportion to activity. When the order book is thin relative to volume, it suggests one side has been aggressively taken out — consistent with a directional whale bet.

---

### Score Interpretation

| Score | Risk Level | Meaning |
|-------|-----------|---------|
| 7–12  | HIGH (red)    | Multiple strong signals — warrants close attention |
| 4–6   | MEDIUM (orange) | Unusual but could have innocent explanations |
| 1–3   | LOW (yellow)  | Minor anomaly |

> **Note:** A high score does not prove insider trading. It flags statistical anomalies worth investigating. Sports and esports markets near resolution can occasionally score high due to rapid price convergence and thin books — use the category filter to focus on political, geopolitical, or economic markets for more signal-rich results.

---

## Market Filters Applied Everywhere

- `active = true` and `closed = false` — only live, open markets
- `archived = false` — no resolved markets
- `lastTradePrice` between 2% and 98% — eliminates effectively-resolved markets and bare 0/100 spreads
- Markets with no price data (price = 0) are excluded

---

## Data Sources

| API | Base URL | Used For |
|-----|----------|----------|
| Polymarket Gamma API | `https://gamma-api.polymarket.com` | Market metadata, volume, prices, events by category |
| Polymarket CLOB API | `https://clob.polymarket.com` | Individual trade records, order book midpoints |

Data is fetched on-demand and cached server-side for 90 seconds to reduce API load during the 60-second auto-refresh cycle.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.13, FastAPI, Uvicorn |
| HTTP client | `requests` |
| Frontend | Vanilla HTML/CSS/JavaScript (no framework, no build step) |
| Styling | Custom dark theme, CSS variables |

---

## Legacy Scripts

These scripts predate the web UI and target Iran war-related markets specifically. They are standalone and can still be run directly.

| Script | Purpose |
|--------|---------|
| `Api.py` | Fetch Iran war markets with YES/NO prices from CLOB |
| `GenerateTop500.py` | Fetch top 500 Iran-related markets using server-side search + pagination |
| `HighestSwings.py` | Duplicate of GenerateTop500 with same logic |
