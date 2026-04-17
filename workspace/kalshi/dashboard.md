---
tags: [kalshi, dashboard]
---

# Kalshi Trading Dashboard

> Requires the **Dataview** Obsidian plugin for live tables.

## Recent Trades

```dataview
TABLE action, side, price_cents AS "Price", count AS "Qty", cost_cents AS "Cost", date
FROM "kalshi/trades"
SORT date DESC
LIMIT 20
```

## Tracked Markets

```dataview
TABLE status, yes_bid, yes_ask, spread, volume, last_updated
FROM "kalshi/markets"
WHERE status = "open"
SORT last_updated DESC
```

## Daily Logs

```dataview
LIST
FROM "kalshi/daily"
SORT file.name DESC
LIMIT 14
```

## Performance Snapshots

```dataview
TABLE date, balance_cents, portfolio_cents
FROM "kalshi/performance"
SORT date DESC
LIMIT 10
```

## Quick Links

- [[kalshi/config/risk-limits|Risk Limits]]
- [[kalshi/config/watchlist|Watchlist]]
