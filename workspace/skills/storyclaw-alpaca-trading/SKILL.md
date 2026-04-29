---
name: storyclaw-alpaca-trading
version: "0.1.0"
description: US stock and crypto trading via Alpaca API. Paper trading (simulated) and real trading supported. Real-time quotes, orders, positions, RSI strategy.
metadata:
  {
    "openclaw":
      {
        "emoji": "📈",
        "requires": { "bins": ["node"], "env": ["ALPACA_API_KEY", "ALPACA_API_SECRET"] },
        "primaryEnv": "ALPACA_API_KEY",
      },
  }
---

# Alpaca Trading - US Stock & Crypto Trading

Trade US stocks and crypto via Alpaca API. Supports both **paper trading** (simulated, free) and **real trading**.

## Critical Rules

1. NEVER execute a trade without showing a plan and getting explicit confirmation
2. NEVER set up cron jobs without proposing them first
3. NEVER make up prices or data — always query real data
4. NEVER assume what the user wants to trade — ask first

## Credential Setup

For OpenClaw, configure these as secrets so they are injected as environment variables:

```bash
ALPACA_API_KEY
ALPACA_API_SECRET
```

Optional endpoints can also be provided as secrets/env vars:

```bash
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_DATA_URL=https://data.alpaca.markets
```

For local development only, create a `.env` file from `.env.example`:

```bash
cp .env.example .env
```

Then fill in the local `.env` file:

```bash
ALPACA_API_KEY=YOUR_KEY
ALPACA_API_SECRET=YOUR_SECRET
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_DATA_URL=https://data.alpaca.markets
```

To switch to real trading, set `ALPACA_BASE_URL` to `https://api.alpaca.markets`.

## First-Time User Flow

1. Check credentials: `USER_ID=$TELEGRAM_USER_ID node {baseDir}/scripts/trading.js check`
2. Ask what they want to trade (stocks vs crypto, symbols, amount, risk)
3. Propose a concrete plan — WAIT FOR CONFIRMATION
4. Execute only after user confirms

## Commands

### Account & Positions

```bash
node {baseDir}/scripts/trading.js check              # Check config
node {baseDir}/scripts/trading.js account            # Balance
node {baseDir}/scripts/trading.js positions          # Current holdings
node {baseDir}/scripts/trading.js history            # Order history
node {baseDir}/scripts/trading.js portfolio-history  # Equity curve (1W default)
node {baseDir}/scripts/trading.js portfolio-history 1M  # 1D/1W/1M/3M/1A
```

### Market Data

```bash
node {baseDir}/scripts/trading.js quote AAPL         # Real-time quote
node {baseDir}/scripts/trading.js bars AAPL 30       # Price history
node {baseDir}/scripts/trading.js rsi AAPL 14        # RSI indicator
```

### Trading

```bash
node {baseDir}/scripts/trading.js buy AAPL 10        # Buy (market order)
node {baseDir}/scripts/trading.js sell AAPL 10       # Sell
```

### Strategy

```bash
node {baseDir}/scripts/trading.js strategy-rsi AAPL  # RSI mean reversion
# RSI < 30 + no position → BUY; RSI > 70 + has position → SELL
```

## Features

- US Stocks & Crypto (AAPL, TSLA, BTC, ETH, and more)
- Paper OR real trading (depends on credentials)
- Real-time quotes (15-min delayed on free tier)
- Market orders, technical indicators (RSI)
- Market hours: Stocks 9:30-16:00 ET Mon-Fri; Crypto 24/7

## Setup

1. Sign up at https://app.alpaca.markets/brokerage/new-account
2. Generate API key + secret (Paper Trading section)
3. Configure OpenClaw secrets or create a local `.env` from `.env.example`

## API Limits

| Tier      | Calls/min | Data delay |
| --------- | --------- | ---------- |
| Free      | 200       | 15 min     |
| Unlimited | Unlimited | Real-time  |
