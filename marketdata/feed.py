"""Market data feed.

Fetches daily OHLCV bars from the Yahoo Finance chart API and caches them
as CSV so backtests are reproducible and work offline. If the network is
down and no cache exists, raises a clear error instead of trading on
garbage.
"""

from __future__ import annotations

import os
import time

import pandas as pd
import requests

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "cache")
COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


def _cache_path(symbol: str) -> str:
    safe = symbol.replace("=", "_").replace("/", "_")
    return os.path.join(CACHE_DIR, f"{safe}.csv")


def _fetch_yahoo(symbol: str, days: int) -> pd.DataFrame:
    # Yahoo ranges are coarse; 2y comfortably covers days<=500 plus warmup.
    rng = "1y" if days <= 200 else "2y"
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.get(
                CHART_URL.format(symbol=symbol),
                params={"range": rng, "interval": "1d", "events": "history"},
                headers=HEADERS,
                timeout=30,
            )
            if resp.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            result = resp.json()["chart"]["result"][0]
            quote = result["indicators"]["quote"][0]
            df = pd.DataFrame(
                {
                    "Open": quote["open"],
                    "High": quote["high"],
                    "Low": quote["low"],
                    "Close": quote["close"],
                    "Volume": quote["volume"],
                },
                index=pd.to_datetime(result["timestamp"], unit="s").normalize(),
            )
            df.index.name = "Date"
            return df.dropna(subset=["Close"])
        except Exception as exc:
            last_err = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Yahoo fetch failed for {symbol}: {last_err}")


def fetch_history(symbol: str, days: int = 400, refresh: bool = True) -> pd.DataFrame:
    """Return daily OHLCV history for `symbol`, newest row last.

    Tries the live API first and updates the local cache; falls back to the
    cache when the network is unavailable.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(symbol)

    if refresh:
        try:
            df = _fetch_yahoo(symbol, days)
            if len(df) > 0:
                df.to_csv(path)
                return df.tail(days)
        except Exception as exc:
            print(f"[feed] live fetch failed for {symbol}: {exc}; trying cache")

    if os.path.exists(path):
        df = pd.read_csv(path, index_col="Date", parse_dates=True)
        return df.tail(days)

    raise RuntimeError(
        f"No market data for {symbol}: live fetch failed and no cache at {path}"
    )


def fetch_all(symbols: list[str], days: int = 400, refresh: bool = True) -> dict[str, pd.DataFrame]:
    return {s: fetch_history(s, days=days, refresh=refresh) for s in symbols}


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range, used for position sizing and stops."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(period).mean()
