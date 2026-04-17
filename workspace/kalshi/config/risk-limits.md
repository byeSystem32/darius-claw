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
