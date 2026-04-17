#!/usr/bin/env python3
"""
Kalshi Config - Read trader configuration from Obsidian vault Markdown files.

Parses YAML frontmatter and bullet-list sections from config files
that the user maintains in Obsidian.  No PyYAML dependency required.
"""

import re
import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from kalshi_journal import get_vault_path


# -- Frontmatter parser (no PyYAML) ---------------------------------------

def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """Parse YAML-style frontmatter delimited by --- markers.

    Supports: strings, ints, floats, booleans, and inline [lists].
    """
    if not content.startswith("---"):
        return {}, content

    end = content.find("---", 3)
    if end == -1:
        return {}, content

    raw = content[3:end].strip()
    body = content[end + 3:].strip()
    meta: Dict[str, Any] = {}

    for line in raw.split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip()

        if val.lower() == "true":
            meta[key] = True
        elif val.lower() == "false":
            meta[key] = False
        elif val.startswith("[") and val.endswith("]"):
            items = [i.strip().strip("'\"") for i in val[1:-1].split(",")]
            meta[key] = [i for i in items if i]
        else:
            try:
                meta[key] = int(val)
            except ValueError:
                try:
                    meta[key] = float(val)
                except ValueError:
                    meta[key] = val

    return meta, body


def parse_bullet_list(body: str, section_heading: str) -> List[str]:
    """Extract bullet-point items from under a ## heading."""
    pattern = rf"##\s+{re.escape(section_heading)}\s*\n(.*?)(?=\n##|\Z)"
    match = re.search(pattern, body, re.DOTALL)
    if not match:
        return []

    section = match.group(1)
    items = []
    for line in section.split("\n"):
        line = line.strip()
        if line.startswith("- ") and len(line) > 2:
            item = line[2:].strip()
            if item.startswith("_") and item.endswith("_"):
                continue
            item = item.strip("`")
            if item:
                items.append(item)
    return items


# -- Config reader ---------------------------------------------------------

class VaultConfig:
    """Reads trader configuration from Obsidian vault Markdown files."""

    _DEFAULT_RISK = {
        "max_trade_cents": 500,
        "max_daily_spend_cents": 2000,
        "max_open_orders": 10,
        "max_portfolio_cents": 5000,
        "min_balance_reserve_cents": 1000,
        "allowed_categories": "all",
        "stop_loss_pct": 20,
        "auto_trade": False,
    }

    def __init__(self, vault_path: Optional[str] = None):
        self.vault = Path(vault_path) if vault_path else get_vault_path()
        self.config_dir = self.vault / "config"

    def _read_file(self, filename: str) -> Optional[str]:
        path = self.config_dir / filename
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def load_risk_limits(self) -> Dict[str, Any]:
        """Load risk limits from config/risk-limits.md frontmatter."""
        content = self._read_file("risk-limits.md")
        if content is None:
            print("[WARN] risk-limits.md not found, using defaults")
            return dict(self._DEFAULT_RISK)

        meta, _ = parse_frontmatter(content)
        merged = dict(self._DEFAULT_RISK)
        merged.update(meta)
        return merged

    def load_watchlist(self) -> Dict[str, Any]:
        """Load watchlist from config/watchlist.md.

        Returns dict with keys:
            events, markets, search_terms, instructions, scan_interval_minutes
        """
        content = self._read_file("watchlist.md")
        if content is None:
            print("[WARN] watchlist.md not found, using empty watchlist")
            return {
                "events": [],
                "markets": [],
                "search_terms": [],
                "instructions": "",
                "scan_interval_minutes": 15,
            }

        meta, body = parse_frontmatter(content)

        events = parse_bullet_list(body, "Tracked Events")
        markets = parse_bullet_list(body, "Tracked Markets")
        search_terms = parse_bullet_list(body, "Search Terms")

        instructions = ""
        instr_match = re.search(
            r"##\s+Instructions\s*\n(.*?)(?=\n##|\Z)", body, re.DOTALL
        )
        if instr_match:
            text = instr_match.group(1).strip()
            if not (text.startswith("_") and text.endswith("_")):
                instructions = text

        return {
            "events": events,
            "markets": markets,
            "search_terms": search_terms,
            "instructions": instructions,
            "scan_interval_minutes": meta.get("scan_interval_minutes", 15),
        }

    def load_market_notes(self, ticker: str) -> Optional[str]:
        """Read user-added notes from a market analysis file's 'My Notes' section."""
        safe_ticker = ticker.replace("/", "-")
        path = self.vault / "markets" / f"{safe_ticker}.md"
        if not path.exists():
            return None

        content = path.read_text(encoding="utf-8")
        match = re.search(r"## My Notes\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
        if match:
            notes = match.group(1).strip()
            if notes and not (notes.startswith("_") and notes.endswith("_")):
                return notes
        return None


if __name__ == "__main__":
    vault = sys.argv[1] if len(sys.argv) > 1 else None
    config = VaultConfig(vault)

    print("=== Risk Limits ===")
    print(json.dumps(config.load_risk_limits(), indent=2))

    print("\n=== Watchlist ===")
    print(json.dumps(config.load_watchlist(), indent=2))
