"""Momentum breakout for BTC.

Long when today's close takes out the N-day high on above-average volume;
exit on a close below the M-day low. Long-only — crypto downside moves are
handled by staying out, not by shorting.
"""

from __future__ import annotations

import pandas as pd

from .base import Signal, Strategy


class Momentum(Strategy):
    name = "momentum"

    def warmup(self) -> int:
        return max(self.params["breakout_days"], 20) + 5

    def entry(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        n = self.params["breakout_days"]
        close = df["Close"]
        prior_high = close.iloc[-(n + 1):-1].max()
        if close.iloc[-1] <= prior_high:
            return None
        vol = df["Volume"]
        vol_avg = vol.iloc[-21:-1].mean()
        if vol_avg > 0 and vol.iloc[-1] < self.params["volume_factor"] * vol_avg:
            return None
        return Signal(symbol, +1,
                      f"close {close.iloc[-1]:.0f} broke {n}-day high {prior_high:.0f} on volume")

    def exit_signal(self, symbol: str, df: pd.DataFrame, direction: int,
                    bars_held: int) -> str | None:
        m = self.params["exit_days"]
        close = df["Close"]
        prior_low = close.iloc[-(m + 1):-1].min()
        if close.iloc[-1] < prior_low:
            return f"close below {m}-day low {prior_low:.0f}"
        return None
