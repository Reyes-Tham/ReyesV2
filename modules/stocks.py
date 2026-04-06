import requests
import yfinance as yf
from datetime import date, timedelta
from config import FINNHUB_API_KEY


def _fmt_cap(v):
    if not v:
        return "N/A"
    if v >= 1_000_000_000_000:
        return f"{v / 1_000_000_000_000:.2f}T"
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.2f}B"
    return f"{v / 1_000_000:.2f}M"


def get_price(ticker: str) -> dict | None:
    try:
        stock = yf.Ticker(ticker.upper())
        info = stock.info
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose") or info.get("open")
        if not price:
            return {"error": f"No price data found for {ticker.upper()}"}
        pe = info.get("trailingPE")
        return {
            "name":        info.get("shortName", ticker),
            "ticker":      ticker.upper(),
            "price":       round(price, 2),
            "currency":    info.get("currency", "USD"),
            "day_low":     info.get("dayLow"),
            "day_high":    info.get("dayHigh"),
            "week52_low":  info.get("fiftyTwoWeekLow"),
            "week52_high": info.get("fiftyTwoWeekHigh"),
            "market_cap":  _fmt_cap(info.get("marketCap")),
            "pe_ratio":    round(pe, 2) if pe else "N/A",
        }
    except Exception as e:
        return {"error": str(e)}


def get_news(ticker: str, count: int = 3) -> list[dict]:
    if not FINNHUB_API_KEY:
        return []
    try:
        to_date = date.today()
        from_date = to_date - timedelta(days=7)
        url = (
            f"https://finnhub.io/api/v1/company-news"
            f"?symbol={ticker.upper()}"
            f"&from={from_date}"
            f"&to={to_date}"
            f"&token={FINNHUB_API_KEY}"
        )
        resp = requests.get(url, timeout=5)
        articles = resp.json()
        return [
            {
                "headline": a.get("headline", ""),
                "source":   a.get("source", ""),
                "date":     date.fromtimestamp(a.get("datetime", 0)).isoformat(),
                "url":      a.get("url", ""),
            }
            for a in articles[:count]
        ]
    except Exception:
        return []
