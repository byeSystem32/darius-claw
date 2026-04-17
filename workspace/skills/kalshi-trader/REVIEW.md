Skill: Kalshi Trader

Confirmation: I had it do a dry-run buy order on a test market. It responded with:

=== DRY RUN (Order NOT placed) ===
  BUY 5x YES @ 65c
  Ticker: KXTEST-25APR15
  Cost:       $3.25
  Max Payout: $1.75

It correctly calculated the cost (5 contracts x 65 cents = $3.25) and max payout (5 x 35 cents = $1.75). The --help flag also works cleanly, showing all available commands for account management, market discovery, and trading.

Issues: The previous Kalshi skill in .agents/skills/kalshi was read-only — it could look up sports markets and prices using the sports-skills CLI, but it could not actually place trades, manage orders, or check your portfolio balance. It also depended on the sports-skills package and was scoped narrowly to sports events. The new kalshi-trader skill is a standalone Python script with only the `requests` library as a dependency. It covers the full Kalshi API v2: authentication, balance checks, market search, orderbook viewing, buy/sell order placement, order cancellation, and position tracking. It also includes safety features like --dry-run simulation, large order confirmation prompts (>$50), automatic retry on rate limits and expired sessions, and a --demo flag for the Kalshi sandbox environment. The original file had Unicode characters (em dashes, arrows, emoji) that caused encoding errors on Windows — these were replaced with pure ASCII to ensure cross-platform compatibility.

Reflection: The old skill was useful for checking odds but useless for actually trading. Now the agent can go from searching markets to placing real trades in a single session. The --dry-run flag is critical for safety — it lets you preview exactly what an order will cost before committing real money. No additional dependencies beyond requests, which is already installed. The skill follows the same SKILL.md frontmatter format as agent-browser so OpenClaw picks it up automatically.
