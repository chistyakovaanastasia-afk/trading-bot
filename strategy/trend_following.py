"""Trend following for gold and oil.

EMA crossover defines the trend; positions ride it with an ATR trailing
stop enforced by the risk manager, and flip out when the cross reverses.
"""

from __future__ import annotations

import pandas as pd

from .base import Signal, Strategy


def emas(close: pd.Series, fast: int, slow: int) -> tuple[float, float, float, float]:
    f = close.ewm(span=fast, adjust=False).mean()
    s = close.ewm(span=slow, adjust=False).mean()
    return float(f.iloc[-1]), float(s.iloc[-1]), float(f.iloc[-2]), float(s.iloc[-2])


class TrendFollowing(Strategy):
    name = "trend_following"

    def warmup(self) -> int:
        return self.params["slow_ema"] + 10

    def entry(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        fast, slow = self.params["fast_ema"], self.params["slow_ema"]
        f_now, s_now, f_prev, s_prev = emas(df["Close"], fast, slow)
        if f_prev <= s_prev and f_now > s_now:
            return Signal(symbol, +1, f"EMA{fast} crossed above EMA{slow}")
        if f_prev >= s_prev and f_now < s_now:
            return Signal(symbol, -1, f"EMA{fast} crossed below EMA{slow}")
        return None

    def exit_signal(self, symbol: str, df: pd.DataFrame, direction: int,
                    bars_held: int) -> str | None:
        fast, slow = self.params["fast_ema"], self.params["slow_ema"]
        f_now, s_now, _, _ = emas(df["Close"], fast, slow)
        if direction > 0 and f_now < s_now:
            return "trend reversed (fast EMA below slow)"
        if direction < 0 and f_now > s_now:
            return "trend reversed (fast EMA above slow)"
        return None
