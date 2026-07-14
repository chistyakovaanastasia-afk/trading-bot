"""Risk manager — the non-negotiable rules.

  1. Max 1% of equity at risk per trade (stop distance * size).
  2. ATR-based position sizing: stop sits `stop_atr_mult` ATRs from entry,
     so size = risk budget / stop distance.
  3. Correlation filter: no new position whose returns correlate above the
     threshold with an existing same-direction position (no doubling up on
     SPY + QQQ longs).
  4. Kill switch: if equity drops `max_drawdown` from its peak, close
     everything and halt until a human resets it.

Strategies propose; this module disposes.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from marketdata.feed import atr


@dataclass
class RiskDecision:
    approved: bool
    reason: str
    qty: float = 0.0
    stop_price: float = 0.0


class RiskManager:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    def stop_distance(self, df: pd.DataFrame) -> float:
        a = atr(df, self.cfg["atr_period"]).iloc[-1]
        if pd.isna(a) or a <= 0:
            return 0.0
        return float(a) * self.cfg["stop_atr_mult"]

    def check_drawdown(self, equity: float, peak_equity: float) -> bool:
        """True means the kill switch fires: close everything, halt."""
        if peak_equity <= 0:
            return False
        return equity <= peak_equity * (1.0 - self.cfg["max_drawdown"])

    def _correlation_block(self, symbol: str, direction: int,
                           open_positions: dict, history: dict) -> str | None:
        lookback = self.cfg["correlation_lookback"]
        cand = history[symbol]["Close"].pct_change().tail(lookback)
        for other, pos in open_positions.items():
            if other == symbol or pos["direction"] != direction:
                continue
            if other not in history:
                continue
            existing = history[other]["Close"].pct_change().tail(lookback)
            joined = pd.concat([cand, existing], axis=1, join="inner").dropna()
            if len(joined) < 20:
                continue
            corr = joined.iloc[:, 0].corr(joined.iloc[:, 1])
            if pd.notna(corr) and abs(corr) >= self.cfg["correlation_threshold"]:
                return (f"correlation {corr:.2f} with existing "
                        f"{'long' if direction > 0 else 'short'} {other}")
        return None

    def evaluate(self, symbol: str, direction: int, price: float, equity: float,
                 df: pd.DataFrame, open_positions: dict, history: dict,
                 halted: bool, fractional: bool = False) -> RiskDecision:
        if halted:
            return RiskDecision(False, "kill switch active — manual reset required")
        if symbol in open_positions:
            return RiskDecision(False, "position already open")
        if len(open_positions) >= self.cfg["max_open_positions"]:
            return RiskDecision(False, f"max {self.cfg['max_open_positions']} positions open")

        block = self._correlation_block(symbol, direction, open_positions, history)
        if block:
            return RiskDecision(False, block)

        dist = self.stop_distance(df)
        if dist <= 0:
            return RiskDecision(False, "ATR unavailable — cannot size position")

        risk_budget = equity * self.cfg["max_risk_per_trade"]
        qty = risk_budget / dist
        if not fractional:
            qty = float(int(qty))
        if qty <= 0:
            return RiskDecision(False, "risk budget too small for one unit at this ATR")

        # Never let the notional exceed equity (no leverage).
        if qty * price > equity:
            qty = equity / price
            if not fractional:
                qty = float(int(qty))
            if qty <= 0:
                return RiskDecision(False, "price exceeds available equity")

        stop = price - direction * dist
        return RiskDecision(True, f"sized to risk {self.cfg['max_risk_per_trade']:.0%} "
                                  f"of equity, stop {dist:.2f} away", qty, stop)
