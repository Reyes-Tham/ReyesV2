"""
modules/watchlist.py
--------------------
Manages stockwatch.json
Commands: /stockwatch add /stockwatch remove /stockwatch list
"""

import json
from pathlib import Path
from datetime import datetime

WATCHLIST_FILE = "data/stockwatch.json"


def _load() -> dict:
    path = Path(WATCHLIST_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return {"stocks": []}
    try:
        content = path.read_text().strip()
        return json.loads(content) if content else {"stocks": []}
    except json.JSONDecodeError:
        return {"stocks": []}


def _save(data: dict) -> None:
    Path(WATCHLIST_FILE).write_text(json.dumps(data, indent=2))


def add_stock(ticker: str, shares: float, avg_price: float) -> dict:
    """Add or update a stock. If ticker exists, updates it."""
    data = _load()
    for s in data["stocks"]:
        if s["ticker"] == ticker.upper():
            s["shares"]    = shares
            s["avg_price"] = avg_price
            s["updated"]   = datetime.now().strftime("%Y-%m-%d")
            _save(data)
            return s
    item = {
        "ticker":    ticker.upper(),
        "shares":    shares,
        "avg_price": avg_price,
        "added":     datetime.now().strftime("%Y-%m-%d"),
    }
    data["stocks"].append(item)
    _save(data)
    return item


def remove_stock(ticker: str) -> bool:
    data   = _load()
    before = len(data["stocks"])
    data["stocks"] = [s for s in data["stocks"] if s["ticker"] != ticker.upper()]
    if len(data["stocks"]) < before:
        _save(data)
        return True
    return False


def list_stocks() -> list:
    return _load()["stocks"]


def get_watchlist_text() -> str:
    """
    Convert watchlist to readable text for injection into prompts.
    Fetches live prices and calculates P&L for each stock.
    """
    import yfinance as yf
    stocks = list_stocks()
    if not stocks:
        return "Watchlist is empty."

    lines  = ["STOCK WATCHLIST WITH LIVE DATA:\n"]
    total_invested = 0
    total_value    = 0

    for s in stocks:
        try:
            info  = yf.Ticker(s["ticker"]).info
            price = info.get("currentPrice") or info.get("regularMarketPrice") or s["avg_price"]
        except Exception:
            price = s["avg_price"]

        invested  = round(s["shares"] * s["avg_price"], 2)
        value     = round(s["shares"] * price, 2)
        pnl       = round(value - invested, 2)
        pnl_pct   = round((pnl / invested) * 100, 2) if invested else 0
        sign      = "+" if pnl >= 0 else ""

        total_invested += invested
        total_value    += value

        lines.append(
            f"{s['ticker']}: {s['shares']} shares | "
            f"Bought @ ${s['avg_price']} | "
            f"Now @ ${price} | "
            f"P&L: {sign}${pnl} ({sign}{pnl_pct}%)"
        )

    total_pnl     = round(total_value - total_invested, 2)
    total_pnl_pct = round((total_pnl / total_invested) * 100, 2) if total_invested else 0
    sign          = "+" if total_pnl >= 0 else ""

    lines.append(
        f"\nPORTFOLIO TOTAL: "
        f"Invested ${total_invested:,.2f} | "
        f"Value ${total_value:,.2f} | "
        f"P&L {sign}${total_pnl:,.2f} ({sign}{total_pnl_pct}%)"
    )
    return "\n".join(lines)