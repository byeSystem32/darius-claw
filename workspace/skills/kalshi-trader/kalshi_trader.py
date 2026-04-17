#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kalshi Trader CLI - Trade prediction markets on Kalshi via API v2.

Usage:
    python kalshi_trader.py <command> [args...] [--flags]

Environment Variables:
    KALSHI_EMAIL       Your Kalshi login email
    KALSHI_PASSWORD    Your Kalshi login password
    KALSHI_API_BASE    (Optional) API base URL
    KALSHI_DEMO        (Optional) Set to 'true' for demo environment

Commands:
    balance                          Show account balance
    positions                        List open positions
    orders                           List open orders
    fills                            Show recent fills
    history                          Show settlement history
    search <query>                   Search markets
    events                           List active events
    event <event_ticker>             Get event details
    market <ticker>                  Get market details
    orderbook <ticker>               Show orderbook
    series                           List event series
    buy <ticker> <side> <qty> <price>   Place buy order
    sell <ticker> <side> <qty> <price>  Place sell order
    cancel <order_id>                Cancel an order
    cancel-all                       Cancel all open orders
"""

import os
import sys
import json
import time
import argparse
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

try:
    from kalshi_journal import KalshiJournal
except ImportError:
    KalshiJournal = None  # type: ignore[assignment,misc]


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

PROD_API_BASE = "https://trading-api.kalshi.com/trade-api/v2"
DEMO_API_BASE = "https://demo-api.kalshi.co/trade-api/v2"

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


def get_api_base(use_demo: bool = False) -> str:
    """Get the API base URL based on environment or flags."""
    if use_demo or os.getenv("KALSHI_DEMO", "").lower() == "true":
        return DEMO_API_BASE
    return os.getenv("KALSHI_API_BASE", PROD_API_BASE)


# -----------------------------------------------------------------------------
# API Client
# -----------------------------------------------------------------------------

class KalshiClient:
    """Kalshi API v2 client with session-based authentication."""

    def __init__(self, email: str, password: str, api_base: str):
        self.email = email
        self.password = password
        self.api_base = api_base.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self.token: Optional[str] = None
        self.member_id: Optional[str] = None

    def _url(self, path: str) -> str:
        return f"{self.api_base}{path}"

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Make an authenticated request with retry logic."""
        if not self.token:
            self.login()

        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.request(method, self._url(path), **kwargs)

                # Re-authenticate on 401
                if resp.status_code == 401 and attempt < MAX_RETRIES - 1:
                    print("[INFO] Session expired, re-authenticating...")
                    self.login()
                    continue

                # Rate limit handling
                if resp.status_code == 429:
                    wait = RETRY_DELAY * (attempt + 1)
                    print(f"[WARN] Rate limited. Waiting {wait}s...")
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                return resp

            except requests.exceptions.ConnectionError as e:
                if attempt < MAX_RETRIES - 1:
                    print(f"[WARN] Connection error, retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
                else:
                    raise

        raise RuntimeError(f"Request failed after {MAX_RETRIES} retries")

    def login(self):
        """Authenticate with Kalshi and store session token."""
        print(f"[INFO] Logging in to Kalshi ({self.api_base})...")
        resp = self.session.post(
            self._url("/log-in"),
            json={"email": self.email, "password": self.password}
        )
        resp.raise_for_status()
        data = resp.json()
        self.token = data.get("token")
        self.member_id = data.get("member_id")
        self.session.headers["Authorization"] = f"Bearer {self.token}"
        print(f"[INFO] Logged in successfully (member: {self.member_id})")

    # -- Account ----------------------------------------------------------

    def get_balance(self) -> Dict[str, Any]:
        """Get account balance."""
        resp = self._request("GET", "/portfolio/balance")
        return resp.json()

    def get_positions(self, limit: int = 100, settlement_status: str = "unsettled") -> Dict[str, Any]:
        """Get portfolio positions."""
        params = {
            "limit": limit,
            "settlement_status": settlement_status
        }
        resp = self._request("GET", "/portfolio/positions", params=params)
        return resp.json()

    def get_orders(self, status: str = "resting") -> Dict[str, Any]:
        """Get open orders."""
        params = {"status": status}
        resp = self._request("GET", "/portfolio/orders", params=params)
        return resp.json()

    def get_fills(self, limit: int = 50) -> Dict[str, Any]:
        """Get recent fills."""
        params = {"limit": limit}
        resp = self._request("GET", "/portfolio/fills", params=params)
        return resp.json()

    def get_settlements(self, limit: int = 50) -> Dict[str, Any]:
        """Get settlement history."""
        params = {"limit": limit}
        resp = self._request("GET", "/portfolio/settlements", params=params)
        return resp.json()

    # -- Discovery --------------------------------------------------------

    def search_markets(self, query: str, limit: int = 20) -> Dict[str, Any]:
        """Search for markets by keyword."""
        params = {
            "limit": limit,
            "status": "open",
        }
        # Kalshi v2 uses the events endpoint with a search query
        resp = self._request("GET", "/events", params=params)
        data = resp.json()

        # Filter events by query text
        query_lower = query.lower()
        events = data.get("events", [])
        filtered = [
            e for e in events
            if query_lower in e.get("title", "").lower()
            or query_lower in e.get("category", "").lower()
            or query_lower in e.get("sub_title", "").lower()
            or query_lower in json.dumps(e.get("mutually_exclusive", False)).lower()
        ]
        return {"events": filtered, "total": len(filtered)}

    def get_events(self, limit: int = 20, status: str = "open") -> Dict[str, Any]:
        """List active events."""
        params = {"limit": limit, "status": status}
        resp = self._request("GET", "/events", params=params)
        return resp.json()

    def get_event(self, event_ticker: str) -> Dict[str, Any]:
        """Get event details including its markets."""
        resp = self._request("GET", f"/events/{event_ticker}")
        return resp.json()

    def get_event_markets(self, event_ticker: str) -> Dict[str, Any]:
        """Get all markets for an event."""
        params = {"event_ticker": event_ticker}
        resp = self._request("GET", "/markets", params=params)
        return resp.json()

    def get_market(self, ticker: str) -> Dict[str, Any]:
        """Get detailed market info."""
        resp = self._request("GET", f"/markets/{ticker}")
        return resp.json()

    def get_orderbook(self, ticker: str, depth: int = 10) -> Dict[str, Any]:
        """Get market orderbook."""
        params = {"depth": depth}
        resp = self._request("GET", f"/markets/{ticker}/orderbook", params=params)
        return resp.json()

    def get_series(self) -> Dict[str, Any]:
        """List event series (categories)."""
        resp = self._request("GET", "/series")
        return resp.json()

    # -- Trading ----------------------------------------------------------

    def place_order(
        self,
        ticker: str,
        side: str,      # "yes" or "no"
        action: str,     # "buy" or "sell"
        count: int,      # number of contracts
        price: int,      # price in cents (1-99)
        order_type: str = "limit",
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Place a buy or sell order."""

        # Validate inputs
        if side.lower() not in ("yes", "no"):
            raise ValueError(f"Side must be 'yes' or 'no', got '{side}'")
        if action.lower() not in ("buy", "sell"):
            raise ValueError(f"Action must be 'buy' or 'sell', got '{action}'")
        if not 1 <= price <= 99:
            raise ValueError(f"Price must be 1-99 cents, got {price}")
        if count < 1:
            raise ValueError(f"Count must be >= 1, got {count}")

        cost_cents = price * count
        max_payout = (100 - price) * count if action == "buy" else price * count

        order_info = {
            "ticker": ticker,
            "action": action,
            "side": side.lower(),
            "count": count,
            "price_cents": price,
            "type": order_type,
            "cost": f"${cost_cents / 100:.2f}",
            "max_payout": f"${max_payout / 100:.2f}",
        }

        if dry_run:
            return {"dry_run": True, "order": order_info, "message": "Order NOT placed (dry run)"}

        payload = {
            "ticker": ticker,
            "action": action.lower(),
            "side": side.lower(),
            "count": count,
            "type": order_type,
        }

        # For limit orders, include the price
        if order_type == "limit":
            payload["yes_price"] = price if side.lower() == "yes" else (100 - price)
            payload["no_price"] = price if side.lower() == "no" else (100 - price)

        resp = self._request("POST", "/portfolio/orders", json=payload)
        result = resp.json()
        result["_order_summary"] = order_info
        return result

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel a specific order."""
        resp = self._request("DELETE", f"/portfolio/orders/{order_id}")
        if resp.status_code == 204:
            return {"success": True, "message": f"Order {order_id} cancelled"}
        return resp.json()

    def cancel_all_orders(self) -> Dict[str, Any]:
        """Cancel all open orders."""
        # Get all resting orders first
        orders = self.get_orders(status="resting")
        order_list = orders.get("orders", [])

        if not order_list:
            return {"message": "No open orders to cancel"}

        results = []
        for order in order_list:
            oid = order.get("order_id", order.get("id", ""))
            try:
                result = self.cancel_order(oid)
                results.append({"order_id": oid, **result})
            except Exception as e:
                results.append({"order_id": oid, "error": str(e)})

        return {"cancelled": len(results), "results": results}


# -----------------------------------------------------------------------------
# Display Helpers
# -----------------------------------------------------------------------------

def fmt_cents(cents: Any) -> str:
    """Format cents as dollars."""
    if cents is None:
        return "N/A"
    try:
        return f"${int(cents) / 100:.2f}"
    except (ValueError, TypeError):
        return str(cents)


def fmt_timestamp(ts: Any) -> str:
    """Format a timestamp string."""
    if not ts:
        return "N/A"
    try:
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(ts)


def print_json(data: Any):
    """Pretty print JSON."""
    print(json.dumps(data, indent=2, default=str))


def print_balance(data: Dict):
    """Display balance info."""
    balance = data.get("balance", 0)
    portfolio = data.get("portfolio_value", 0)
    payout = data.get("payout", 0)
    print("\n=== Account Balance ===")
    print(f"  Available Balance:  {fmt_cents(balance)}")
    print(f"  Portfolio Value:    {fmt_cents(portfolio)}")
    print(f"  Total Payout:       {fmt_cents(payout)}")
    print(f"  -----------------------------")
    total = (balance or 0) + (portfolio or 0)
    print(f"  Total:              {fmt_cents(total)}")
    print()


def print_positions(data: Dict):
    """Display positions."""
    positions = data.get("market_positions", data.get("positions", []))
    if not positions:
        print("\nNo open positions.\n")
        return

    print(f"\n=== Open Positions ({len(positions)}) ===")
    for pos in positions:
        ticker = pos.get("ticker", pos.get("market_ticker", "???"))
        yes_qty = pos.get("position", pos.get("yes_contracts", 0))
        no_qty = pos.get("no_position", pos.get("no_contracts", 0))
        avg_price = pos.get("average_price", None)
        market_price = pos.get("market_price", None)

        print(f"\n  Ticker: {ticker}")
        if yes_qty:
            print(f"    Yes contracts: {yes_qty}  (avg: {fmt_cents(avg_price)})")
        if no_qty:
            print(f"    No contracts:  {no_qty}")
        if market_price:
            print(f"    Current price: {fmt_cents(market_price)}")
    print()


def print_orders(data: Dict):
    """Display orders."""
    orders = data.get("orders", [])
    if not orders:
        print("\nNo open orders.\n")
        return

    print(f"\n=== Open Orders ({len(orders)}) ===")
    for order in orders:
        oid = order.get("order_id", order.get("id", "???"))
        ticker = order.get("ticker", "???")
        side = order.get("side", "???")
        action = order.get("action", order.get("type", "???"))
        price = order.get("yes_price", order.get("price", 0))
        remaining = order.get("remaining_count", order.get("count", 0))
        status = order.get("status", "???")
        created = fmt_timestamp(order.get("created_time", order.get("created_at", "")))

        print(f"\n  Order ID: {oid}")
        print(f"    {action.upper()} {remaining}x {side.upper()} @ {fmt_cents(price)}")
        print(f"    Ticker: {ticker}")
        print(f"    Status: {status}")
        print(f"    Created: {created}")
    print()


def print_fills(data: Dict):
    """Display fills."""
    fills = data.get("fills", [])
    if not fills:
        print("\nNo recent fills.\n")
        return

    print(f"\n=== Recent Fills ({len(fills)}) ===")
    for fill in fills:
        ticker = fill.get("ticker", "???")
        side = fill.get("side", "???")
        action = fill.get("action", "???")
        count = fill.get("count", 0)
        price = fill.get("yes_price", fill.get("price", 0))
        ts = fmt_timestamp(fill.get("created_time", fill.get("created_at", "")))

        print(f"  [{ts}] {action.upper()} {count}x {side.upper()} @ {fmt_cents(price)} - {ticker}")
    print()


def print_market(data: Dict):
    """Display market details."""
    market = data.get("market", data)
    ticker = market.get("ticker", "???")
    title = market.get("title", market.get("subtitle", "???"))
    status = market.get("status", "???")
    yes_bid = market.get("yes_bid", None)
    yes_ask = market.get("yes_ask", None)
    no_bid = market.get("no_bid", None)
    no_ask = market.get("no_ask", None)
    last_price = market.get("last_price", None)
    volume = market.get("volume", None)
    open_interest = market.get("open_interest", None)
    close_time = fmt_timestamp(market.get("close_time", market.get("expiration_time", "")))
    category = market.get("category", "")
    result = market.get("result", "")

    print(f"\n=== Market: {ticker} ===")
    print(f"  Title:          {title}")
    print(f"  Status:         {status}")
    print(f"  Category:       {category}")
    print(f"  Close Time:     {close_time}")
    if result:
        print(f"  Result:         {result}")
    print(f"  -----------------------------")
    print(f"  Yes Bid/Ask:    {fmt_cents(yes_bid)} / {fmt_cents(yes_ask)}")
    print(f"  No  Bid/Ask:    {fmt_cents(no_bid)} / {fmt_cents(no_ask)}")
    print(f"  Last Price:     {fmt_cents(last_price)}")
    print(f"  Volume:         {volume}")
    print(f"  Open Interest:  {open_interest}")
    print()


def print_orderbook(data: Dict):
    """Display orderbook."""
    ob = data.get("orderbook", data)
    yes_bids = ob.get("yes", [])
    no_bids = ob.get("no", [])

    print("\n=== Orderbook ===")
    print("\n  YES side:")
    if yes_bids:
        for level in yes_bids:
            price = level if isinstance(level, (int, float)) else level.get("price", 0)
            qty = "" if isinstance(level, (int, float)) else f" x{level.get('quantity', '')}"
            print(f"    {fmt_cents(price)}{qty}")
    else:
        print("    (empty)")

    print("\n  NO side:")
    if no_bids:
        for level in no_bids:
            price = level if isinstance(level, (int, float)) else level.get("price", 0)
            qty = "" if isinstance(level, (int, float)) else f" x{level.get('quantity', '')}"
            print(f"    {fmt_cents(price)}{qty}")
    else:
        print("    (empty)")
    print()


def print_events(data: Dict):
    """Display events list."""
    events = data.get("events", [])
    if not events:
        print("\nNo events found.\n")
        return

    print(f"\n=== Events ({len(events)}) ===")
    for event in events:
        ticker = event.get("event_ticker", event.get("ticker", "???"))
        title = event.get("title", "???")
        category = event.get("category", "")
        markets_count = event.get("markets_count", len(event.get("markets", [])))
        status = event.get("status", "")

        print(f"\n  [{ticker}] {title}")
        if category:
            print(f"    Category: {category}")
        print(f"    Markets: {markets_count} | Status: {status}")
    print()


def print_search_results(data: Dict):
    """Display search results."""
    events = data.get("events", [])
    total = data.get("total", len(events))

    if not events:
        print("\nNo markets found matching your search.\n")
        return

    print(f"\n=== Search Results ({total} matches) ===")
    for event in events:
        ticker = event.get("event_ticker", event.get("ticker", "???"))
        title = event.get("title", "???")
        category = event.get("category", "")

        print(f"\n  [{ticker}] {title}")
        if category:
            print(f"    Category: {category}")

        # Show child markets if available
        markets = event.get("markets", [])
        for m in markets[:5]:  # Show first 5 markets
            mticker = m.get("ticker", "???")
            mtitle = m.get("title", m.get("subtitle", ""))
            yes_bid = m.get("yes_bid", None)
            print(f"    -> {mticker}: {mtitle} (Yes: {fmt_cents(yes_bid)})")
    print()


def print_order_result(data: Dict):
    """Display order placement result."""
    if data.get("dry_run"):
        print("\n=== DRY RUN (Order NOT placed) ===")
        order = data.get("order", {})
        print(f"  {order.get('action', '').upper()} {order.get('count', 0)}x "
              f"{order.get('side', '').upper()} @ {order.get('price_cents', 0)}c")
        print(f"  Ticker: {order.get('ticker', '???')}")
        print(f"  Cost:       {order.get('cost', 'N/A')}")
        print(f"  Max Payout: {order.get('max_payout', 'N/A')}")
        print()
        return

    summary = data.get("_order_summary", {})
    order = data.get("order", data)
    oid = order.get("order_id", order.get("id", "???"))
    status = order.get("status", "submitted")

    print(f"\n=== Order Placed ===")
    print(f"  Order ID: {oid}")
    print(f"  Status:   {status}")
    if summary:
        print(f"  {summary.get('action', '').upper()} {summary.get('count', 0)}x "
              f"{summary.get('side', '').upper()} @ {summary.get('price_cents', 0)}c")
        print(f"  Ticker:     {summary.get('ticker', '???')}")
        print(f"  Cost:       {summary.get('cost', 'N/A')}")
        print(f"  Max Payout: {summary.get('max_payout', 'N/A')}")
    print()


# -----------------------------------------------------------------------------
# CLI Entry Point
# -----------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kalshi Trader CLI - Trade prediction markets on Kalshi",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python kalshi_trader.py balance
  python kalshi_trader.py search "bitcoin"
  python kalshi_trader.py market KXBTC-25APR15-T100000
  python kalshi_trader.py buy KXBTC-25APR15-T100000 yes 5 65
  python kalshi_trader.py positions
  python kalshi_trader.py cancel <order_id>
        """
    )

    parser.add_argument("command", help="Command to execute")
    parser.add_argument("args", nargs="*", help="Command arguments")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without executing")
    parser.add_argument("--demo", action="store_true", help="Use Kalshi demo environment")
    parser.add_argument("--type", default="limit", choices=["limit", "market"],
                        help="Order type (default: limit)")
    parser.add_argument("--limit", type=int, default=20, help="Result limit")
    parser.add_argument("--vault-path", default=None,
                        help="Path to Obsidian vault kalshi/ dir (or set KALSHI_VAULT_PATH)")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Validate credentials
    email = os.getenv("KALSHI_EMAIL")
    password = os.getenv("KALSHI_PASSWORD")

    if not email or not password:
        print("[ERROR] KALSHI_EMAIL and KALSHI_PASSWORD environment variables must be set.")
        print("  export KALSHI_EMAIL='your@email.com'")
        print("  export KALSHI_PASSWORD='yourpassword'")
        sys.exit(1)

    # Initialize client
    api_base = get_api_base(use_demo=args.demo)
    client = KalshiClient(email, password, api_base)

    cmd = args.command.lower()
    cmd_args = args.args

    try:
        # -- Account commands -----------------------------------------
        if cmd == "balance":
            data = client.get_balance()
            if args.json:
                print_json(data)
            else:
                print_balance(data)

        elif cmd == "positions":
            data = client.get_positions(limit=args.limit)
            if args.json:
                print_json(data)
            else:
                print_positions(data)

        elif cmd == "orders":
            data = client.get_orders()
            if args.json:
                print_json(data)
            else:
                print_orders(data)

        elif cmd == "fills":
            data = client.get_fills(limit=args.limit)
            if args.json:
                print_json(data)
            else:
                print_fills(data)

        elif cmd == "history":
            data = client.get_settlements(limit=args.limit)
            if args.json:
                print_json(data)
            else:
                print_json(data)  # settlements don't have a dedicated formatter

        # -- Discovery commands ---------------------------------------
        elif cmd == "search":
            if not cmd_args:
                print("[ERROR] Usage: search <query>")
                sys.exit(1)
            query = " ".join(cmd_args)
            data = client.search_markets(query, limit=args.limit)
            if args.json:
                print_json(data)
            else:
                print_search_results(data)

        elif cmd == "events":
            data = client.get_events(limit=args.limit)
            if args.json:
                print_json(data)
            else:
                print_events(data)

        elif cmd == "event":
            if not cmd_args:
                print("[ERROR] Usage: event <event_ticker>")
                sys.exit(1)
            event_ticker = cmd_args[0]
            event_data = client.get_event(event_ticker)
            markets_data = client.get_event_markets(event_ticker)
            if args.json:
                print_json({"event": event_data, "markets": markets_data})
            else:
                event = event_data.get("event", event_data)
                print(f"\n=== Event: {event.get('event_ticker', event_ticker)} ===")
                print(f"  Title:    {event.get('title', '???')}")
                print(f"  Category: {event.get('category', '')}")
                print(f"  Status:   {event.get('status', '')}")
                markets = markets_data.get("markets", [])
                print(f"\n  Markets ({len(markets)}):")
                for m in markets:
                    mt = m.get("ticker", "???")
                    mtitle = m.get("title", m.get("subtitle", ""))
                    yes_bid = m.get("yes_bid", None)
                    status = m.get("status", "")
                    print(f"    [{mt}] {mtitle}")
                    print(f"      Yes: {fmt_cents(yes_bid)} | Status: {status}")
                print()

        elif cmd == "market":
            if not cmd_args:
                print("[ERROR] Usage: market <ticker>")
                sys.exit(1)
            data = client.get_market(cmd_args[0])
            if args.json:
                print_json(data)
            else:
                print_market(data)

        elif cmd == "orderbook":
            if not cmd_args:
                print("[ERROR] Usage: orderbook <ticker>")
                sys.exit(1)
            data = client.get_orderbook(cmd_args[0])
            if args.json:
                print_json(data)
            else:
                print_orderbook(data)

        elif cmd == "series":
            data = client.get_series()
            if args.json:
                print_json(data)
            else:
                series_list = data.get("series", [])
                print(f"\n=== Event Series ({len(series_list)}) ===")
                for s in series_list:
                    print(f"  [{s.get('ticker', '???')}] {s.get('title', '???')}")
                    if s.get('category'):
                        print(f"    Category: {s['category']}")
                print()

        # -- Trading commands -----------------------------------------
        elif cmd in ("buy", "sell"):
            if len(cmd_args) < 4:
                print(f"[ERROR] Usage: {cmd} <ticker> <yes|no> <count> <price_cents>")
                print(f"  Example: {cmd} KXBTC-25APR15-T100000 yes 5 65")
                sys.exit(1)

            ticker = cmd_args[0]
            side = cmd_args[1]
            count = int(cmd_args[2])
            price = int(cmd_args[3])

            # Safety confirmation for large orders
            cost = price * count
            if cost > 5000 and not args.dry_run:  # > $50
                print(f"\n[WARNING] Large order: {cmd.upper()} {count}x {side.upper()} @ {price}c "
                      f"(cost: ${cost/100:.2f})")
                confirm = input("  Confirm? (yes/no): ").strip().lower()
                if confirm != "yes":
                    print("  Order cancelled.")
                    sys.exit(0)

            data = client.place_order(
                ticker=ticker,
                side=side,
                action=cmd,
                count=count,
                price=price,
                order_type=args.type,
                dry_run=args.dry_run
            )
            if args.json:
                print_json(data)
            else:
                print_order_result(data)

            if KalshiJournal is not None:
                try:
                    journal = KalshiJournal(args.vault_path)
                    order = data.get("order", data)
                    path = journal.log_trade({
                        "ticker": ticker,
                        "action": cmd,
                        "side": side,
                        "count": count,
                        "price": price,
                        "type": args.type,
                        "dry_run": args.dry_run,
                        "order_id": order.get("order_id", order.get("id", "")),
                    })
                    print(f"[JOURNAL] Logged to {path}")
                except Exception as je:
                    print(f"[WARN] Journal logging failed: {je}")

        elif cmd == "cancel":
            if not cmd_args:
                print("[ERROR] Usage: cancel <order_id>")
                sys.exit(1)
            data = client.cancel_order(cmd_args[0])
            if args.json:
                print_json(data)
            else:
                print(f"\nOrder {cmd_args[0]} cancelled successfully.\n")

        elif cmd == "cancel-all":
            data = client.cancel_all_orders()
            if args.json:
                print_json(data)
            else:
                cancelled = data.get("cancelled", 0)
                if cancelled:
                    print(f"\nCancelled {cancelled} order(s).\n")
                else:
                    print(f"\n{data.get('message', 'No orders to cancel.')}\n")

        else:
            print(f"[ERROR] Unknown command: {cmd}")
            print("  Run with --help for usage information.")
            sys.exit(1)

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        body = ""
        try:
            body = e.response.json() if e.response is not None else ""
        except Exception:
            body = e.response.text if e.response is not None else ""
        print(f"\n[ERROR] HTTP {status}: {e}")
        if body:
            print(f"  Response: {json.dumps(body, indent=2) if isinstance(body, dict) else body}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
