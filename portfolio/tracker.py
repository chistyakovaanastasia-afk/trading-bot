"""Portfolio tracker.

Holds cash, open positions, closed-trade log, and the daily equity curve.
Everything serializes to a JSON state file so the paper trader survives
restarts and the briefings can compare today against yesterday.
"""

from __future__ import annotations

import json
import os
from datetime import date


class PortfolioTracker:
    def __init__(self, starting_equity: float, state_file: str):
        self.state_file = state_file
        self.cash = starting_equity
        self.starting_equity = starting_equity
        self.peak_equity = starting_equity
        self.positions: dict[str, dict] = {}
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []
        self.halted = False

    # ---- persistence -------------------------------------------------

    @classmethod
    def load(cls, starting_equity: float, state_file: str) -> "PortfolioTracker":
        t = cls(starting_equity, state_file)
        if os.path.exists(state_file):
            with open(state_file) as f:
                s = json.load(f)
            t.cash = s["cash"]
            t.starting_equity = s["starting_equity"]
            t.peak_equity = s["peak_equity"]
            t.positions = s["positions"]
            t.trades = s["trades"]
            t.equity_curve = s["equity_curve"]
            t.halted = s["halted"]
        return t

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump({
                "cash": self.cash,
                "starting_equity": self.starting_equity,
                "peak_equity": self.peak_equity,
                "positions": self.positions,
                "trades": self.trades,
                "equity_curve": self.equity_curve,
                "halted": self.halted,
            }, f, indent=2, default=str)

    # ---- position lifecycle -------------------------------------------

    def open_position(self, symbol: str, direction: int, qty: float, price: float,
                      stop: float, strategy: str, reason: str, day: str,
                      commission: float = 0.0) -> None:
        self.cash -= direction * qty * price + commission
        self.positions[symbol] = {
            "direction": direction,
            "qty": qty,
            "entry_price": price,
            "stop_price": stop,
            "strategy": strategy,
            "reason": reason,
            "opened": day,
            "bars_held": 0,
        }

    def close_position(self, symbol: str, price: float, reason: str, day: str,
                       commission: float = 0.0) -> dict:
        pos = self.positions.pop(symbol)
        pnl = pos["direction"] * pos["qty"] * (price - pos["entry_price"]) - commission
        self.cash += pos["direction"] * pos["qty"] * price - commission
        trade = {
            "symbol": symbol,
            "strategy": pos["strategy"],
            "direction": pos["direction"],
            "qty": pos["qty"],
            "entry_price": pos["entry_price"],
            "exit_price": price,
            "pnl": round(pnl, 2),
            "opened": pos["opened"],
            "closed": day,
            "entry_reason": pos["reason"],
            "exit_reason": reason,
        }
        self.trades.append(trade)
        return trade

    # ---- valuation -----------------------------------------------------

    def equity(self, prices: dict[str, float]) -> float:
        value = self.cash
        for symbol, pos in self.positions.items():
            price = prices.get(symbol, pos["entry_price"])
            value += pos["direction"] * pos["qty"] * price
        return value

    def mark_day(self, prices: dict[str, float], day: str | None = None) -> float:
        eq = self.equity(prices)
        self.peak_equity = max(self.peak_equity, eq)
        day = day or date.today().isoformat()
        if self.equity_curve and self.equity_curve[-1]["date"] == day:
            self.equity_curve[-1]["equity"] = round(eq, 2)
        else:
            self.equity_curve.append({"date": day, "equity": round(eq, 2)})
        return eq

    def unrealized(self, prices: dict[str, float]) -> dict[str, float]:
        out = {}
        for symbol, pos in self.positions.items():
            price = prices.get(symbol, pos["entry_price"])
            out[symbol] = round(pos["direction"] * pos["qty"] * (price - pos["entry_price"]), 2)
        return out

    def trades_on(self, day: str) -> list[dict]:
        return [t for t in self.trades if t["closed"] == day]
