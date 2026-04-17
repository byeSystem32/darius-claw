---
name: kalshi-trader
description: Trade prediction markets on Kalshi autonomously. Use when the user wants to browse events, check market prices, place orders (buy/sell yes/no contracts), view portfolio positions, check balances, manage trades, run autonomous scans, or review trading performance. Triggers include "buy on Kalshi", "sell on Kalshi", "check Kalshi markets", "what's my Kalshi balance", "place a trade", "show my positions", "find markets about...", "what are the odds of...", "scan for opportunities", "run the trader", "show trading report", or any prediction market trading task.
allowed-tools: Bash(python *kalshi*.py*), Bash(python *kalshi_trader*), Bash(python *kalshi_runner*), Bash(python *kalshi_journal*), Bash(python *kalshi_config*), Bash(curl *)
---

# Kalshi Trader Skill

Trade prediction markets on Kalshi using the Kalshi API v2.
Supports manual trading, autonomous scanning, Obsidian-based journaling, and configurable risk management.

## Prerequisites

1. **Python 3.8+** with `requests` installed (`pip install requests`)
2. **Kalshi account** with API access
3. **Environment variables** set:
   - `KALSHI_EMAIL` -- Your Kalshi login email
   - `KALSHI_PASSWORD` -- Your Kalshi login password
   - (Optional) `KALSHI_API_BASE` -- defaults to `https://trading-api.kalshi.com/trade-api/v2`
   - (Optional) `KALSHI_DEMO` -- set to `true` to use demo environment
   - (Optional) `KALSHI_VAULT_PATH` -- path to the Obsidian vault `kalshi/` directory (defaults to `../../kalshi` relative to this skill, i.e. `workspace/kalshi/`)

## Architecture

```
kalshi-trader/
  kalshi_trader.py    # Manual CLI: balance, search, buy, sell, cancel, etc.
  kalshi_runner.py    # Autonomous loop: scan, decide, execute, journal
  kalshi_journal.py   # Obsidian-compatible Markdown trade logging
  kalshi_config.py    # Read config from Obsidian vault Markdown files
  SKILL.md            # This file
```

The autonomous runner reads configuration from Obsidian vault files, scans markets, evaluates opportunities, optionally places trades (when `auto_trade: true`), and logs all activity back to the vault as Markdown with YAML frontmatter. This enables a git-sync workflow between the VPS and local Obsidian for review and control.

## Quick Start

```bash
# Set credentials
export KALSHI_EMAIL="your@email.com"
export KALSHI_PASSWORD="yourpassword"

# Initialize the Obsidian vault structure
python kalshi_runner.py init

# Manual trading (unchanged from before)
python kalshi_trader.py balance
python kalshi_trader.py search "bitcoin"
python kalshi_trader.py buy KXBTC-25APR15-T100000 yes 5 65

# Autonomous scanning
python kalshi_runner.py status       # Check current config
python kalshi_runner.py scan         # Single scan cycle
python kalshi_runner.py run          # Continuous loop
python kalshi_runner.py report       # Generate performance report
```

## Obsidian Vault Structure

After running `python kalshi_runner.py init`, the vault directory looks like:

```
workspace/kalshi/
  dashboard.md                        # Dataview dashboard (install Dataview plugin)
  config/
    risk-limits.md                    # Risk parameters (edit in Obsidian)
    watchlist.md                      # Tracked markets and search terms (edit in Obsidian)
  trades/                             # Auto-generated trade logs
    2026-04-17_143022_buy_KXBTC.md
  markets/                            # Auto-generated market analysis notes
    KXBTC-25APR15-T100000.md
  daily/                              # Auto-generated daily activity logs
    2026-04-17.md
  performance/                        # Auto-generated performance snapshots
    2026-04-17_snapshot.md
```

### Git-Sync Workflow

The vault is designed for git-sync between VPS and local Obsidian:

1. **VPS:** The trader writes Markdown logs to `workspace/kalshi/`
2. **VPS:** A cron job or post-action hook runs `git add kalshi/ && git commit && git push`
3. **Local:** Obsidian Git plugin auto-pulls changes
4. **Local:** You review trades, edit `risk-limits.md` and `watchlist.md` in Obsidian
5. **Local:** Obsidian Git pushes your edits
6. **VPS:** Next scan cycle picks up your config changes

### Configuring Risk Limits

Edit `kalshi/config/risk-limits.md` frontmatter in Obsidian:

```yaml
---
max_trade_cents: 500          # Max $5 per trade
max_daily_spend_cents: 2000   # Max $20/day
max_open_orders: 10
max_portfolio_cents: 5000     # Max $50 portfolio
min_balance_reserve_cents: 1000
allowed_categories: all       # or "crypto, politics"
stop_loss_pct: 20
auto_trade: false             # Set true to enable autonomous trading
---
```

### Configuring Watchlist

Edit `kalshi/config/watchlist.md` in Obsidian:

```yaml
---
scan_interval_minutes: 15
---
```

Add tickers and search terms as bullet points under the relevant headings:

```markdown
## Tracked Markets
- KXBTC-25APR15-T100000

## Search Terms
- bitcoin
- fed rate
- election
```

The `## Instructions` section lets you write free-text guidance the agent reads each cycle.

## Manual Trading Commands

### Account
| Command | Description |
|---------|-------------|
| `balance` | Show account balance and portfolio value |
| `positions` | List all open positions |
| `orders` | List all open/pending orders |
| `fills` | Show recent trade fills/executions |
| `history` | Show settlement history |

### Discovery
| Command | Description |
|---------|-------------|
| `search <query>` | Search markets by keyword |
| `events` | List active events |
| `event <ticker>` | Get event details and its markets |
| `market <ticker>` | Get detailed market info |
| `orderbook <ticker>` | Show current orderbook |
| `series` | List event series |

### Trading
| Command | Description |
|---------|-------------|
| `buy <ticker> <side> <qty> <price>` | Place a buy order |
| `sell <ticker> <side> <qty> <price>` | Place a sell order |
| `cancel <order_id>` | Cancel a specific order |
| `cancel-all` | Cancel all open orders |

### Options
| Flag | Description |
|------|-------------|
| `--type market` | Place a market order instead of limit |
| `--dry-run` | Simulate the trade without executing |
| `--json` | Output raw JSON response |
| `--demo` | Use Kalshi demo environment |
| `--vault-path <path>` | Override vault directory |

## Autonomous Runner Commands

All via `kalshi_runner.py`:

| Command | Description |
|---------|-------------|
| `init` | Create vault directories and template config files |
| `status` | Show current risk limits, watchlist, and vault path |
| `scan` | Run a single scan cycle (read-only, logs to vault) |
| `run` | Start the continuous scan-decide-execute loop |
| `report` | Generate a performance report and snapshot |

### Runner Options
| Flag | Description |
|------|-------------|
| `--cycles N` | Limit `run` to N cycles (0 = unlimited) |
| `--vault-path <path>` | Override vault directory |
| `--demo` | Use Kalshi demo environment |
| `--json` | Output raw JSON |

## How the Autonomous Loop Works

Each cycle of `kalshi_runner.py run`:

1. **Reload config** -- reads `risk-limits.md` and `watchlist.md` from the vault (hot-reload, so Obsidian edits take effect without restart)
2. **Scan** -- checks tracked markets/events, searches by keywords
3. **Evaluate** -- scores each market on spread tightness, volume, price extremity, and user notes
4. **Decide** -- checks risk limits (balance, daily spend, open orders) before acting
5. **Execute** -- if `auto_trade: true` and within limits, places limit orders on top-scored opportunities
6. **Journal** -- logs everything (scans, decisions, trades) to the vault as Markdown
7. **Report** -- every 4th cycle, writes a performance snapshot
8. **Sleep** -- waits `scan_interval_minutes` then repeats

When `auto_trade: false` (the default), the loop does everything except place orders -- it scans, evaluates, logs opportunities, but only observes.

## Safety

- **auto_trade defaults to false** -- the runner only observes until you explicitly enable it
- **All risk limits are configurable** in Obsidian and checked before every trade
- **Every action is journaled** -- full audit trail in `trades/` and `daily/` notes
- **Hot-reload** -- change risk limits mid-run by editing in Obsidian; next cycle picks them up
- **--dry-run** on manual trades previews without executing
- **--demo** flag for the Kalshi sandbox environment
- **Market notes** -- the agent reads your "My Notes" annotations from market files before trading
- **Never store credentials in files** -- use environment variables only

## Examples

### Autonomous scan-only (observe markets)
```bash
python kalshi_runner.py init
python kalshi_runner.py scan
python kalshi_runner.py run --cycles 4
```

### Enable autonomous trading
Edit `kalshi/config/risk-limits.md` in Obsidian and set `auto_trade: true`, then:
```bash
python kalshi_runner.py run
```

### Manual trade with journaling
```bash
python kalshi_trader.py buy KXBTC-25APR15-T100000 yes 5 60
# Trade is automatically logged to kalshi/trades/ and kalshi/daily/
```

### Generate a report
```bash
python kalshi_runner.py report
# Writes to kalshi/daily/ and kalshi/performance/
```
