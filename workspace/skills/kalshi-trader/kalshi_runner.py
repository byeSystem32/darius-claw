#!/usr/bin/env python3
"""
Kalshi Runner - Autonomous trading loop.

Reads config from an Obsidian vault, scans markets, evaluates opportunities,
optionally executes trades, and journals everything back to the vault.

Usage:
    python kalshi_runner.py init                Initialize vault structure
    python kalshi_runner.py scan                Single scan cycle (read-only)
    python kalshi_runner.py run  [--cycles N]   Continuous autonomous loop
    python kalshi_runner.py report              Generate performance report
    python kalshi_runner.py status              Show current config and state
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kalshi_trader import KalshiClient, get_api_base, fmt_cents
from kalshi_journal import KalshiJournal, init_vault
from kalshi_config import VaultConfig


class AutonomousRunner:
    """Scan-decide-execute-journal loop for Kalshi prediction markets."""

    def __init__(
        self,
        client: Optional[KalshiClient] = None,
        vault_path: Optional[str] = None,
    ):
        self.client = client
        self.journal = KalshiJournal(vault_path)
        self.config = VaultConfig(vault_path)
        self.daily_spend = 0
        self.cycle_count = 0

    # -- Scanning ----------------------------------------------------------

    def scan_once(self) -> Dict[str, Any]:
        """Run a single scan cycle: read watchlist, query markets, log results."""
        assert self.client is not None, "Client required for scanning"
        print("\n[SCAN] Loading watchlist...")
        watchlist = self.config.load_watchlist()
        risk = self.config.load_risk_limits()

        all_opportunities: List[Dict[str, Any]] = []

        for ticker in watchlist.get("markets", []):
            try:
                print(f"[SCAN] Checking market: {ticker}")
                data = self.client.get_market(ticker)
                market = data.get("market", data)
                opp = self._evaluate_market(market, risk)
                if opp:
                    all_opportunities.append(opp)
                self._update_market_note(market)
            except Exception as e:
                print(f"[WARN] Failed to check {ticker}: {e}")

        for event_ticker in watchlist.get("events", []):
            try:
                print(f"[SCAN] Checking event: {event_ticker}")
                markets_data = self.client.get_event_markets(event_ticker)
                for market in markets_data.get("markets", []):
                    opp = self._evaluate_market(market, risk)
                    if opp:
                        all_opportunities.append(opp)
                    self._update_market_note(market)
            except Exception as e:
                print(f"[WARN] Failed to check event {event_ticker}: {e}")

        for term in watchlist.get("search_terms", []):
            try:
                print(f"[SCAN] Searching: {term}")
                results = self.client.search_markets(term, limit=10)
                for event in results.get("events", []):
                    for market in event.get("markets", []):
                        opp = self._evaluate_market(market, risk)
                        if opp:
                            all_opportunities.append(opp)
            except Exception as e:
                print(f"[WARN] Search failed for '{term}': {e}")

        # Deduplicate and rank
        seen: set = set()
        unique: List[Dict[str, Any]] = []
        for opp in all_opportunities:
            if opp["ticker"] not in seen:
                seen.add(opp["ticker"])
                unique.append(opp)
        unique.sort(key=lambda x: x.get("score", 0), reverse=True)

        scan_result = {
            "opportunities": unique,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "markets_checked": len(watchlist.get("markets", [])),
            "terms_searched": len(watchlist.get("search_terms", [])),
        }

        self.journal.log_scan(scan_result, strategy="watchlist")

        if unique:
            print(f"\n[SCAN] {len(unique)} opportunities:")
            for opp in unique[:10]:
                print(f"  {opp['ticker']}: {opp['signal']} (score: {opp['score']})")
        else:
            print("\n[SCAN] No opportunities this cycle.")

        return scan_result

    def _evaluate_market(
        self, market: Dict[str, Any], risk: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Score a market for opportunity quality. Returns None if uninteresting."""
        ticker = market.get("ticker", "")
        if market.get("status") != "open":
            return None

        yes_bid = market.get("yes_bid", 0) or 0
        yes_ask = market.get("yes_ask", 0) or 0
        volume = market.get("volume", 0) or 0
        open_interest = market.get("open_interest", 0) or 0

        if yes_bid == 0 and yes_ask == 0:
            return None

        # Category filter
        category = market.get("category", "")
        allowed = risk.get("allowed_categories", "all")
        if allowed != "all":
            allowed_list = [c.strip().lower() for c in str(allowed).split(",")]
            if category.lower() not in allowed_list:
                return None

        spread = yes_ask - yes_bid
        mid = (
            (yes_bid + yes_ask) / 2
            if (yes_bid and yes_ask)
            else (yes_bid or yes_ask)
        )

        score = 0
        signals = []

        if 0 < spread <= 5:
            score += 30
            signals.append(f"tight spread ({spread}c)")
        elif 0 < spread <= 10:
            score += 15
            signals.append(f"moderate spread ({spread}c)")

        if volume > 1000:
            score += 25
            signals.append(f"high volume ({volume})")
        elif volume > 100:
            score += 10
            signals.append(f"decent volume ({volume})")

        if mid <= 15 or mid >= 85:
            score += 20
            signals.append(f"extreme price ({mid:.0f}c)")

        if open_interest > 500:
            score += 10

        # Incorporate user notes if available
        user_notes = self.config.load_market_notes(ticker)
        if user_notes:
            score += 15
            signals.append("has user notes")

        if score < 20:
            return None

        return {
            "ticker": ticker,
            "title": market.get("title", market.get("subtitle", "")),
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "spread": spread,
            "mid": mid,
            "volume": volume,
            "category": category,
            "score": score,
            "signal": "; ".join(signals),
        }

    def _update_market_note(self, market: Dict[str, Any]):
        ticker = market.get("ticker", "")
        if not ticker:
            return
        self.journal.write_market_analysis(ticker, {
            "title": market.get("title", market.get("subtitle", "")),
            "status": market.get("status", ""),
            "yes_bid": market.get("yes_bid", 0),
            "yes_ask": market.get("yes_ask", 0),
            "volume": market.get("volume", 0),
            "category": market.get("category", ""),
            "close_time": market.get(
                "close_time", market.get("expiration_time", "")
            ),
        })

    # -- Decision & execution ----------------------------------------------

    def decide_and_execute(
        self,
        opportunities: List[Dict[str, Any]],
        risk: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Evaluate opportunities against risk limits and optionally trade."""
        assert self.client is not None

        if not risk.get("auto_trade", False):
            print("[DECIDE] auto_trade is OFF - logging opportunities only")
            for opp in opportunities:
                self.journal.log_decision({
                    "ticker": opp["ticker"],
                    "action_taken": False,
                    "reason": (
                        f"auto_trade disabled. "
                        f"Signal: {opp['signal']} (score: {opp['score']})"
                    ),
                })
            return []

        # Pre-flight checks
        try:
            balance_data = self.client.get_balance()
            balance = balance_data.get("balance", 0)
        except Exception as e:
            print(f"[ERROR] Could not check balance: {e}")
            return []

        reserve = risk.get("min_balance_reserve_cents", 1000)
        available = balance - reserve
        if available <= 0:
            print(
                f"[DECIDE] Insufficient balance: {fmt_cents(balance)} "
                f"(reserve: {fmt_cents(reserve)})"
            )
            return []

        max_daily = risk.get("max_daily_spend_cents", 2000)
        if self.daily_spend >= max_daily:
            print(
                f"[DECIDE] Daily spend limit reached: "
                f"{fmt_cents(self.daily_spend)} / {fmt_cents(max_daily)}"
            )
            return []

        try:
            orders_data = self.client.get_orders()
            open_orders = len(orders_data.get("orders", []))
        except Exception:
            open_orders = 0

        max_orders = risk.get("max_open_orders", 10)
        if open_orders >= max_orders:
            print(f"[DECIDE] Max open orders reached: {open_orders}/{max_orders}")
            return []

        max_trade = risk.get("max_trade_cents", 500)
        executed: List[Dict[str, Any]] = []

        for opp in opportunities[:3]:
            remaining_daily = max_daily - self.daily_spend
            spent_this_cycle = sum(t.get("cost_cents", 0) for t in executed)
            remaining_balance = available - spent_this_cycle
            trade_budget = min(max_trade, remaining_daily, remaining_balance)

            if trade_budget <= 0:
                break

            # Simple heuristic: buy the side that looks underpriced
            price = opp["yes_bid"] if opp["mid"] >= 50 else opp["yes_ask"]
            if price <= 0 or price >= 100:
                continue

            count = max(1, trade_budget // price)
            cost = price * count
            side = "yes" if opp["mid"] < 50 else "no"
            action = "buy"

            try:
                print(
                    f"[TRADE] {action.upper()} {count}x {side.upper()} "
                    f"@ {price}c on {opp['ticker']}"
                )
                result = self.client.place_order(
                    ticker=opp["ticker"],
                    side=side,
                    action=action,
                    count=count,
                    price=price,
                )
                order = result.get("order", result)

                trade_record = {
                    "ticker": opp["ticker"],
                    "action": action,
                    "side": side,
                    "count": count,
                    "price": price,
                    "type": "limit",
                    "dry_run": False,
                    "order_id": order.get("order_id", order.get("id", "")),
                }
                path = self.journal.log_trade(trade_record)
                print(f"[TRADE] Logged to {path}")

                self.journal.log_decision({
                    "ticker": opp["ticker"],
                    "action_taken": True,
                    "reason": (
                        f"{action} {count}x {side} @ {price}c. "
                        f"Signal: {opp['signal']}"
                    ),
                })
                self.daily_spend += cost
                executed.append({"cost_cents": cost, **trade_record})

            except Exception as e:
                print(f"[ERROR] Trade failed for {opp['ticker']}: {e}")
                self.journal.log_decision({
                    "ticker": opp["ticker"],
                    "action_taken": False,
                    "reason": f"Trade failed: {e}",
                })

        return executed

    # -- Reporting ---------------------------------------------------------

    def generate_report(self) -> Dict[str, Any]:
        """Gather portfolio data and write summary + snapshot to the vault."""
        assert self.client is not None
        print("[REPORT] Gathering portfolio data...")

        balance_data = self.client.get_balance()
        positions_data = self.client.get_positions()
        fills_data = self.client.get_fills(limit=100)

        balance = balance_data.get("balance", 0)
        portfolio = balance_data.get("portfolio_value", 0)
        positions = positions_data.get(
            "market_positions", positions_data.get("positions", [])
        )
        fills = fills_data.get("fills", [])

        report = {
            "balance": balance,
            "portfolio_value": portfolio,
            "total_trades": len(fills),
            "win_rate": 0,
            "positions": positions,
        }

        self.journal.write_daily_summary({
            "balance": balance,
            "portfolio_value": portfolio,
            "trades_today": len(fills),
            "pnl": 0,
            "open_positions": len(positions),
        })

        snap_path = self.journal.write_performance_snapshot(report)
        print(f"[REPORT] Snapshot written to {snap_path}")

        print(f"\n=== Portfolio Report ===")
        print(f"  Balance:         {fmt_cents(balance)}")
        print(f"  Portfolio Value:  {fmt_cents(portfolio)}")
        print(f"  Total:           {fmt_cents(balance + portfolio)}")
        print(f"  Open Positions:  {len(positions)}")
        print(f"  Recent Fills:    {len(fills)}")
        print()

        return report

    # -- Status ------------------------------------------------------------

    def show_status(self):
        """Print current config and vault state."""
        risk = self.config.load_risk_limits()
        watchlist = self.config.load_watchlist()

        print("\n=== Kalshi Runner Status ===")
        print(f"\n  Vault: {self.journal.vault}")

        print(f"\n  Risk Limits:")
        for k, v in risk.items():
            print(f"    {k}: {v}")

        print(f"\n  Watchlist:")
        print(f"    Scan interval: {watchlist.get('scan_interval_minutes', 15)} min")
        print(f"    Events:  {watchlist.get('events', [])}")
        print(f"    Markets: {watchlist.get('markets', [])}")
        print(f"    Search:  {watchlist.get('search_terms', [])}")

        instructions = watchlist.get("instructions", "")
        if instructions:
            print(f"    Instructions: {instructions[:200]}")
        print()

    # -- Main loop ---------------------------------------------------------

    def run_loop(self, max_cycles: int = 0):
        """Run the continuous scan-decide-execute loop.

        Reloads config from the vault at the start of each cycle so that
        edits made in Obsidian take effect without restarting.
        """
        watchlist = self.config.load_watchlist()
        risk = self.config.load_risk_limits()
        interval = watchlist.get("scan_interval_minutes", 15) * 60

        print("[RUNNER] Starting autonomous loop")
        print(f"  Scan interval: {interval // 60} minutes")
        print(
            f"  Auto-trade: "
            f"{'ON' if risk.get('auto_trade') else 'OFF (scan only)'}"
        )
        print(f"  Max trade: {fmt_cents(risk.get('max_trade_cents', 500))}")
        print(f"  Max daily: {fmt_cents(risk.get('max_daily_spend_cents', 2000))}")

        while True:
            self.cycle_count += 1
            if 0 < max_cycles < self.cycle_count:
                print(f"\n[RUNNER] Completed {max_cycles} cycles, stopping.")
                break

            now = datetime.now(timezone.utc)
            print(f"\n{'=' * 50}")
            print(f"[RUNNER] Cycle {self.cycle_count} @ {now:%Y-%m-%d %H:%M UTC}")
            print(f"{'=' * 50}")

            # Hot-reload config
            watchlist = self.config.load_watchlist()
            risk = self.config.load_risk_limits()
            interval = watchlist.get("scan_interval_minutes", 15) * 60

            scan_result = self.scan_once()
            opportunities = scan_result.get("opportunities", [])

            if opportunities:
                self.decide_and_execute(opportunities, risk)

            if self.cycle_count % 4 == 0:
                try:
                    self.generate_report()
                except Exception as e:
                    print(f"[WARN] Report generation failed: {e}")

            if 0 < max_cycles <= self.cycle_count:
                break

            print(
                f"\n[RUNNER] Sleeping {interval // 60} minutes "
                f"until next cycle..."
            )
            time.sleep(interval)


# -- CLI -------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kalshi Autonomous Runner - scan, decide, trade, journal",
    )
    parser.add_argument(
        "command",
        choices=["init", "scan", "run", "report", "status"],
        help="Command to execute",
    )
    parser.add_argument(
        "--vault-path",
        default=None,
        help="Path to Obsidian vault kalshi/ directory (or set KALSHI_VAULT_PATH)",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=0,
        help="Max cycles for 'run' command (0 = unlimited)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use Kalshi demo environment",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # init and status don't need API credentials
    if args.command == "init":
        init_vault(args.vault_path)
        return

    if args.command == "status":
        runner = AutonomousRunner(vault_path=args.vault_path)
        runner.show_status()
        return

    # Everything else needs a live Kalshi client
    email = os.getenv("KALSHI_EMAIL")
    password = os.getenv("KALSHI_PASSWORD")

    if not email or not password:
        print(
            "[ERROR] KALSHI_EMAIL and KALSHI_PASSWORD "
            "environment variables must be set."
        )
        sys.exit(1)

    api_base = get_api_base(use_demo=args.demo)
    client = KalshiClient(email, password, api_base)
    runner = AutonomousRunner(client, args.vault_path)

    try:
        if args.command == "scan":
            result = runner.scan_once()
            if args.json:
                print(json.dumps(result, indent=2, default=str))

        elif args.command == "run":
            runner.run_loop(max_cycles=args.cycles)

        elif args.command == "report":
            result = runner.generate_report()
            if args.json:
                print(json.dumps(result, indent=2, default=str))

    except KeyboardInterrupt:
        print("\n[INFO] Interrupted. Generating final report...")
        try:
            runner.generate_report()
        except Exception:
            pass
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
