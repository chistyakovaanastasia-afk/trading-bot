"""Strategy interface.

A strategy looks at price history and answers two questions:
  - should we open a position today? (`entry`)
  - should an existing position be closed today? (`exit_signal`)

Position sizing and stops are NOT the strategy's job — the risk manager
owns those.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Signal:
    symbol: str
    direction: int  # +1 long, -1 short
    reason: str


class Strategy:
    name = "base"

    def __init__(self, params: dict):
        self.params = params

    def warmup(self) -> int:
        """Bars of history needed before signals are meaningful."""
        raise NotImplementedError

    def entry(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        """Called once per day with history up to and including today's bar."""
        raise NotImplementedError

    def exit_signal(self, symbol: str, df: pd.DataFrame, direction: int,
                    bars_held: int) -> str | None:
        """Return a reason string to close the position, or None to hold."""
        raise NotImplementedError
