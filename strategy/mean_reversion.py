"""Mean reversion for index ETFs (SPY, QQQ).

Z-score of the close against its rolling mean: buy stretched-down markets,
short stretched-up ones, exit when price reverts to the mean or the trade
goes stale.
"""

from __future__ import annotations

import pandas as pd

from .base import Signal, Strategy


def zscore(close: pd.Series, lookback: int) -> float:
    window = close.tail(lookback)
    std = window.std()
    if std == 0 or pd.isna(std):
        return 0.0
    return float((close.iloc[-1] - window.mean()) / std)


class MeanReversion(Strategy):
    name = "mean_reversion"

    def warmup(self) -> int:
        return self.params["lookback"] + 5

    def entry(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        z = zscore(df["Close"], self.params["lookback"])
        if z <= -self.params["entry_z"]:
            return Signal(symbol, +1, f"z-score {z:.2f} below -{self.params['entry_z']}")
        if z >= self.params["entry_z"]:
            return Signal(symbol, -1, f"z-score {z:.2f} above +{self.params['entry_z']}")
        return None

    def exit_signal(self, symbol: str, df: pd.DataFrame, direction: int,
                    bars_held: int) -> str | None:
        z = zscore(df["Close"], self.params["lookback"])
        if direction > 0 and z >= -self.params["exit_z"]:
            return f"reverted to mean (z={z:.2f})"
        if direction < 0 and z <= self.params["exit_z"]:
            return f"reverted to mean (z={z:.2f})"
        if bars_held >= self.params["max_hold_days"]:
            return f"max hold {self.params['max_hold_days']} days reached"
        return None
