#!/usr/bin/env python3
"""
Kalshi Journal - Obsidian-compatible trade logging.

Writes Markdown files with YAML frontmatter to a vault directory.
Designed for git-sync between a VPS (where the trader runs) and local Obsidian.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List


def get_vault_path() -> Path:
    """Resolve the vault path from env var or workspace-relative default."""
    explicit = os.getenv("KALSHI_VAULT_PATH")
    if explicit:
        return Path(explicit)
    script_dir = Path(__file__).resolve().parent
    workspace = script_dir.parent.parent  # skills/kalshi-trader -> skills -> workspace
    return workspace / "kalshi"


class KalshiJournal:
    """Writes Obsidian-compatible Markdown trade logs and daily notes."""

    def __init__(self, vault_path: Optional[str] = None):
        self.vault = Path(vault_path) if vault_path else get_vault_path()

    def ensure_dirs(self):
        for subdir in ["trades", "markets", "daily", "config", "performance"]:
            (self.vault / subdir).mkdir(parents=True, exist_ok=True)

    # -- Internal helpers --------------------------------------------------

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _today_str(self) -> str:
        return self._now().strftime("%Y-%m-%d")

    def _write_file(self, path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _append_file(self, path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)

    def _frontmatter(self, meta: Dict[str, Any]) -> str:
        lines = ["---"]
        for k, v in meta.items():
            if isinstance(v, list):
                lines.append(f"{k}: [{', '.join(str(i) for i in v)}]")
            elif isinstance(v, bool):
                lines.append(f"{k}: {'true' if v else 'false'}")
            else:
                lines.append(f"{k}: {v}")
        lines.append("---")
        return "\n".join(lines)

    def _append_to_daily(self, content: str):
        """Append content to today's daily note, creating it if needed."""
        today = self._today_str()
        path = self.vault / "daily" / f"{today}.md"

        if not path.exists():
            header_meta = {"date": today, "tags": "[kalshi, daily]"}
            header = self._frontmatter(header_meta)
            header += f"\n\n# Kalshi Daily Log - {today}\n\n## Activity\n\n"
            self._write_file(path, header)

        self._append_file(path, content)

    # -- Public API --------------------------------------------------------

    def log_trade(self, trade: Dict[str, Any]) -> Path:
        """Log a trade execution to trades/ and append a line to the daily note."""
        self.ensure_dirs()
        now = self._now()

        ticker = trade.get("ticker", "UNKNOWN")
        action = trade.get("action", "unknown")
        side = trade.get("side", "unknown")
        count = trade.get("count", 0)
        price = trade.get("price", 0)
        order_type = trade.get("type", "limit")
        dry_run = trade.get("dry_run", False)
        order_id = trade.get("order_id", "")

        cost_cents = price * count
        if action == "buy":
            max_payout = (100 - price) * count
        else:
            max_payout = price * count

        filename = f"{now:%Y-%m-%d_%H%M%S}_{action}_{ticker}.md"

        meta = {
            "ticker": ticker,
            "action": action,
            "side": side,
            "count": count,
            "price_cents": price,
            "cost_cents": cost_cents,
            "max_payout_cents": max_payout,
            "order_type": order_type,
            "order_id": order_id,
            "dry_run": dry_run,
            "date": now.strftime("%Y-%m-%d %H:%M UTC"),
            "tags": f"[kalshi, trade, {action}, {side}]",
        }

        status_label = "DRY RUN" if dry_run else "LIVE"
        body = (
            f"\n# {status_label}: {action.upper()} {count}x {side.upper()} @ {price}c\n\n"
            f"**Market:** `{ticker}`\n"
            f"**Cost:** ${cost_cents / 100:.2f}\n"
            f"**Max Payout:** ${max_payout / 100:.2f}\n"
            f"**Order Type:** {order_type}\n"
        )
        if order_id:
            body += f"**Order ID:** {order_id}\n"
        body += "\n## Context\n\n_Add notes about why this trade was made._\n"
        body += "\n## Outcome\n\n_Updated after settlement._\n"

        path = self.vault / "trades" / filename
        self._write_file(path, self._frontmatter(meta) + "\n" + body)

        daily_line = (
            f"- **{now:%H:%M}** [{status_label}] {action.upper()} {count}x "
            f"{side.upper()} @ {price}c on `{ticker}` (${cost_cents / 100:.2f})\n"
        )
        self._append_to_daily(daily_line)

        return path

    def log_scan(self, results: Dict[str, Any], strategy: str = "manual") -> Path:
        """Log a market scan summary to the daily note."""
        now = self._now()
        opportunities = results.get("opportunities", [])

        lines = [
            f"\n### Scan @ {now:%H:%M UTC} ({strategy})\n",
            f"- Markets checked: {results.get('markets_checked', '?')}\n",
            f"- Terms searched: {results.get('terms_searched', '?')}\n",
            f"- Opportunities: {len(opportunities)}\n",
        ]
        for opp in opportunities[:10]:
            lines.append(
                f"  - `{opp.get('ticker', '???')}`: "
                f"{opp.get('signal', '')} (score: {opp.get('score', 0)})\n"
            )

        self._append_to_daily("".join(lines))
        return self.vault / "daily" / f"{self._today_str()}.md"

    def log_decision(self, decision: Dict[str, Any]) -> None:
        """Log a trade decision (taken or skipped) to the daily note."""
        now = self._now()
        acted = decision.get("action_taken", False)
        icon = "TRADE" if acted else "SKIP"
        line = (
            f"- **{now:%H:%M}** [{icon}] "
            f"`{decision.get('ticker', '???')}`: {decision.get('reason', '')}\n"
        )
        self._append_to_daily(line)

    def write_market_analysis(self, ticker: str, analysis: Dict[str, Any]) -> Path:
        """Write or update an Obsidian note for a tracked market."""
        self.ensure_dirs()
        now = self._now()

        title = analysis.get("title", ticker)
        status = analysis.get("status", "open")
        yes_bid = analysis.get("yes_bid", 0) or 0
        yes_ask = analysis.get("yes_ask", 0) or 0
        volume = analysis.get("volume", 0) or 0
        category = analysis.get("category", "")
        close_time = analysis.get("close_time", "")
        notes = analysis.get("notes", "")
        spread = yes_ask - yes_bid

        meta = {
            "ticker": ticker,
            "title": title,
            "status": status,
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "spread": spread,
            "volume": volume,
            "category": category,
            "close_time": close_time,
            "last_updated": now.strftime("%Y-%m-%d %H:%M UTC"),
            "tags": f"[kalshi, market, {category}]",
        }

        body = (
            f"\n# {title}\n\n"
            f"**Ticker:** `{ticker}`\n"
            f"**Status:** {status}\n"
            f"**Category:** {category}\n"
            f"**Close Time:** {close_time}\n\n"
            f"## Current Pricing\n\n"
            f"| Metric | Value |\n"
            f"|--------|-------|\n"
            f"| Yes Bid | {yes_bid}c |\n"
            f"| Yes Ask | {yes_ask}c |\n"
            f"| Spread | {spread}c |\n"
            f"| Volume | {volume} |\n\n"
            f"## Analysis\n\n"
            f"{notes if notes else '_No analysis yet._'}\n\n"
            f"## My Notes\n\n"
            f"_Add your own observations here. The agent reads this section before trading._\n"
        )

        # Preserve user-written "My Notes" section if the file already exists
        safe_ticker = ticker.replace("/", "-")
        path = self.vault / "markets" / f"{safe_ticker}.md"
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            import re
            match = re.search(
                r"## My Notes\s*\n(.*)",
                existing,
                re.DOTALL,
            )
            if match:
                user_notes = match.group(1).strip()
                if user_notes and not (user_notes.startswith("_") and user_notes.endswith("_")):
                    body = body.rsplit("## My Notes", 1)[0]
                    body += f"## My Notes\n\n{user_notes}\n"

        self._write_file(path, self._frontmatter(meta) + "\n" + body)
        return path

    def write_daily_summary(self, summary: Dict[str, Any]) -> Path:
        """Append an end-of-day summary table to the daily note."""
        now = self._now()
        balance = summary.get("balance", 0)
        portfolio = summary.get("portfolio_value", 0)
        total = balance + portfolio
        trades = summary.get("trades_today", 0)
        positions = summary.get("open_positions", 0)
        pnl = summary.get("pnl", 0)

        content = (
            f"\n## Daily Summary ({now:%H:%M UTC})\n\n"
            f"| Metric | Value |\n"
            f"|--------|-------|\n"
            f"| Balance | ${balance / 100:.2f} |\n"
            f"| Portfolio Value | ${portfolio / 100:.2f} |\n"
            f"| Total | ${total / 100:.2f} |\n"
            f"| Trades Today | {trades} |\n"
            f"| Open Positions | {positions} |\n"
            f"| Est. P&L | ${pnl / 100:.2f} |\n\n"
        )
        self._append_to_daily(content)
        return self.vault / "daily" / f"{self._today_str()}.md"

    def write_performance_snapshot(self, data: Dict[str, Any]) -> Path:
        """Write a periodic performance snapshot to performance/."""
        self.ensure_dirs()
        now = self._now()

        balance = data.get("balance", 0)
        portfolio = data.get("portfolio_value", 0)
        total_trades = data.get("total_trades", 0)
        win_rate = data.get("win_rate", 0)

        meta = {
            "date": now.strftime("%Y-%m-%d"),
            "type": "performance",
            "balance_cents": balance,
            "portfolio_cents": portfolio,
            "tags": "[kalshi, performance]",
        }

        body = (
            f"\n# Performance Snapshot - {now:%Y-%m-%d %H:%M UTC}\n\n"
            f"## Portfolio\n\n"
            f"| Metric | Value |\n"
            f"|--------|-------|\n"
            f"| Balance | ${balance / 100:.2f} |\n"
            f"| Portfolio Value | ${portfolio / 100:.2f} |\n"
            f"| Total | ${(balance + portfolio) / 100:.2f} |\n\n"
            f"## Trading Stats\n\n"
            f"| Metric | Value |\n"
            f"|--------|-------|\n"
            f"| Total Trades | {total_trades} |\n"
            f"| Win Rate | {win_rate:.1f}% |\n\n"
            f"## Positions\n\n"
        )
        for pos in data.get("positions", []):
            ticker = pos.get("ticker", pos.get("market_ticker", "???"))
            qty = pos.get("position", pos.get("yes_contracts", 0))
            body += f"- `{ticker}`: {qty} contracts\n"

        if not data.get("positions"):
            body += "_No open positions._\n"

        path = self.vault / "performance" / f"{now:%Y-%m-%d}_snapshot.md"
        self._write_file(path, self._frontmatter(meta) + "\n" + body)
        return path


# -- Vault initialization -------------------------------------------------

def init_vault(vault_path: Optional[str] = None):
    """Create the vault directory structure and template config files."""
    journal = KalshiJournal(vault_path)
    journal.ensure_dirs()

    _write_template(
        journal.vault / "config" / "risk-limits.md",
        _RISK_LIMITS_TEMPLATE,
    )
    _write_template(
        journal.vault / "config" / "watchlist.md",
        _WATCHLIST_TEMPLATE,
    )
    _write_template(
        journal.vault / "dashboard.md",
        _DASHBOARD_TEMPLATE,
    )

    print(f"[OK] Vault initialized at: {journal.vault}")
    print("  config/risk-limits.md  - Edit risk parameters")
    print("  config/watchlist.md    - Edit tracked markets and search terms")
    print("  dashboard.md           - Dataview dashboard (install Dataview plugin)")
    print("  trades/                - Trade logs (auto-generated)")
    print("  markets/               - Market analysis notes (auto-generated)")
    print("  daily/                 - Daily activity logs (auto-generated)")
    print("  performance/           - Performance snapshots (auto-generated)")


def _write_template(path: Path, content: str):
    """Write a template file only if it does not already exist."""
    if path.exists():
        print(f"  [SKIP] {path.name} already exists")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [NEW]  {path.name}")


# -- Templates ------------------------------------------------------------

_RISK_LIMITS_TEMPLATE = """\
---
max_trade_cents: 500
max_daily_spend_cents: 2000
max_open_orders: 10
max_portfolio_cents: 5000
min_balance_reserve_cents: 1000
allowed_categories: all
stop_loss_pct: 20
auto_trade: false
---

# Risk Limits

These limits control the autonomous trader. Edit the values in the frontmatter above.
Obsidian reads them as metadata; the trader reads them before each cycle.

## Parameter Reference

- **max_trade_cents** - Maximum cost of any single trade in cents (500 = $5.00)
- **max_daily_spend_cents** - Maximum total new spending per day in cents
- **max_open_orders** - Maximum concurrent resting limit orders
- **max_portfolio_cents** - Maximum total portfolio exposure in cents
- **min_balance_reserve_cents** - Never let balance drop below this (cents)
- **allowed_categories** - Comma-separated categories, or "all"
- **stop_loss_pct** - Pause all trading if portfolio drops this % in one day
- **auto_trade** - Set to `true` to allow the runner to place orders autonomously
"""

_WATCHLIST_TEMPLATE = """\
---
scan_interval_minutes: 15
---

# Watchlist

Markets and topics the autonomous trader should monitor.
Edit these lists in Obsidian; the agent reads them before each scan.

## Tracked Events

_Add event tickers as bullet points:_

## Tracked Markets

_Add market tickers as bullet points:_

## Search Terms

_Keywords the scanner will search for:_

- bitcoin
- fed rate

## Instructions

_Any extra context or instructions for the agent. It reads this section before each cycle._
"""

_DASHBOARD_TEMPLATE = """\
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
"""


if __name__ == "__main__":
    vault = sys.argv[1] if len(sys.argv) > 1 else None
    init_vault(vault)
