"""Backtest engine.

Replays daily bars through the exact same daily cycle the paper trader
uses: check stops intraday, ask strategies for exits and entries on the
close, size everything through the risk manager, fill with slippage and
commission. One code path means the backtest actually tests the bot you
run.
"""

from __future__ import annotations

import math

import pandas as pd

from portfolio.tracker import PortfolioTracker
from risk.manager import RiskManager
from strategy.base import Strategy


def _slip(price: float, direction: int, side: str, bps: float) -> float:
    """Fills move against you: buys fill higher, sells fill lower."""
    sign = direction if side == "entry" else -direction
    return price * (1 + sign * bps / 10000.0)


def daily_cycle(day: str, tracker: PortfolioTracker, strategies: dict[str, Strategy],
                risk: RiskManager, history: dict[str, pd.DataFrame],
                instruments: dict, exec_cfg: dict) -> list[str]:
    """Run one trading day. `history[symbol]` ends at `day`'s bar.

    Returns a list of human-readable events for logging/briefings.
    """
    events: list[str] = []
    commission = exec_cfg["commission_per_trade"]

    def bps_for(symbol: str) -> float:
        asset = instruments[symbol].get("asset_class", "equity")
        return exec_cfg["slippage_bps"].get(asset, 5)

    # 1. Manage open positions: hard stops first, then strategy exits.
    for symbol in list(tracker.positions):
        if symbol not in history or history[symbol].index[-1].strftime("%Y-%m-%d") != day:
            continue
        df = history[symbol]
        bar = df.iloc[-1]
        pos = tracker.positions[symbol]
        pos["bars_held"] += 1
        stop = pos["stop_price"]

        stop_hit = (pos["direction"] > 0 and bar["Low"] <= stop) or \
                   (pos["direction"] < 0 and bar["High"] >= stop)
        if stop_hit:
            fill = _slip(stop, pos["direction"], "exit", bps_for(symbol))
            trade = tracker.close_position(symbol, fill, "hard stop hit", day, commission)
            events.append(f"STOP {symbol} @ {fill:.2f} pnl {trade['pnl']:+.2f}")
            continue

        strat = strategies[pos["strategy"]]
        why = strat.exit_signal(symbol, df, pos["direction"], pos["bars_held"])
        if why:
            fill = _slip(float(bar["Close"]), pos["direction"], "exit", bps_for(symbol))
            trade = tracker.close_position(symbol, fill, why, day, commission)
            events.append(f"EXIT {symbol} @ {fill:.2f} pnl {trade['pnl']:+.2f} ({why})")

    # 2. Ratchet trailing stops for trend-following positions.
    for symbol, pos in tracker.positions.items():
        if symbol not in history:
            continue
        strat = strategies[pos["strategy"]]
        if strat.name == "trend_following":
            dist = risk.stop_distance(history[symbol]) \
                * strategies[pos["strategy"]].params.get("trail_atr_mult", 3.0) \
                / risk.cfg["stop_atr_mult"]
            close = float(history[symbol]["Close"].iloc[-1])
            candidate = close - pos["direction"] * dist
            if pos["direction"] > 0:
                pos["stop_price"] = max(pos["stop_price"], candidate)
            else:
                pos["stop_price"] = min(pos["stop_price"], candidate)

    # 3. New entries through the risk manager.
    closes = {s: float(h["Close"].iloc[-1]) for s, h in history.items()}
    for symbol, inst in instruments.items():
        if symbol not in history or history[symbol].index[-1].strftime("%Y-%m-%d") != day:
            continue
        df = history[symbol]
        strat = strategies[inst["strategy"]]
        if len(df) < strat.warmup():
            continue
        sig = strat.entry(symbol, df)
        if sig is None:
            continue
        equity = tracker.equity(closes)
        decision = risk.evaluate(symbol, sig.direction, closes[symbol], equity, df,
                                 tracker.positions, history, tracker.halted,
                                 fractional=inst.get("fractional", False))
        if not decision.approved:
            events.append(f"BLOCKED {symbol} {'long' if sig.direction > 0 else 'short'}: "
                          f"{decision.reason}")
            continue
        fill = _slip(closes[symbol], sig.direction, "entry", bps_for(symbol))
        tracker.open_position(symbol, sig.direction, decision.qty, fill,
                              decision.stop_price, inst["strategy"], sig.reason, day,
                              commission)
        events.append(f"OPEN {'LONG' if sig.direction > 0 else 'SHORT'} {symbol} "
                      f"{decision.qty:g} @ {fill:.2f} stop {decision.stop_price:.2f} "
                      f"({sig.reason})")

    # 4. Mark to market and check the kill switch.
    equity = tracker.mark_day(closes, day)
    if not tracker.halted and risk.check_drawdown(equity, tracker.peak_equity):
        for symbol in list(tracker.positions):
            price = closes.get(symbol, tracker.positions[symbol]["entry_price"])
            fill = _slip(price, tracker.positions[symbol]["direction"], "exit",
                         bps_for(symbol))
            tracker.close_position(symbol, fill, "kill switch: max drawdown", day,
                                   commission)
        tracker.halted = True
        tracker.mark_day(closes, day)
        events.append(f"KILL SWITCH: equity {equity:,.0f} is "
                      f"{risk.cfg['max_drawdown']:.0%} below peak "
                      f"{tracker.peak_equity:,.0f} — all positions closed, bot halted")
    return events


def run_backtest(cfg: dict, history: dict[str, pd.DataFrame],
                 strategies: dict[str, Strategy], months: int | None = None,
                 verbose: bool = False) -> dict:
    months = months or cfg["backtest"]["months"]
    risk = RiskManager(cfg["risk"])
    tracker = PortfolioTracker(cfg["account"]["starting_equity"], state_file="/dev/null")

    all_days = sorted({d.strftime("%Y-%m-%d") for df in history.values() for d in df.index})
    cutoff = pd.Timestamp.today() - pd.DateOffset(months=months)
    test_days = [d for d in all_days if pd.Timestamp(d) >= cutoff]

    for day in test_days:
        sliced = {s: df[df.index <= day] for s, df in history.items()}
        sliced = {s: df for s, df in sliced.items() if len(df) > 0}
        events = daily_cycle(day, tracker, strategies, risk, sliced,
                             cfg["instruments"], cfg["execution"])
        if verbose:
            for e in events:
                if not e.startswith("BLOCKED"):
                    print(f"{day}  {e}")

    return summarize(tracker, cfg)


def summarize(tracker: PortfolioTracker, cfg: dict) -> dict:
    curve = pd.Series({e["date"]: e["equity"] for e in tracker.equity_curve})
    returns = curve.pct_change().dropna()
    rf_daily = cfg["backtest"]["risk_free_rate"] / 252

    sharpe = 0.0
    if len(returns) > 1 and returns.std() > 0:
        sharpe = float((returns.mean() - rf_daily) / returns.std() * math.sqrt(252))

    peak = curve.cummax()
    max_dd = float(((curve - peak) / peak).min()) if len(curve) else 0.0

    per_strategy: dict[str, dict] = {}
    for t in tracker.trades:
        s = per_strategy.setdefault(t["strategy"], {"trades": 0, "wins": 0, "pnl": 0.0})
        s["trades"] += 1
        s["wins"] += 1 if t["pnl"] > 0 else 0
        s["pnl"] = round(s["pnl"] + t["pnl"], 2)

    total = curve.iloc[-1] if len(curve) else tracker.starting_equity
    wins = sum(1 for t in tracker.trades if t["pnl"] > 0)
    return {
        "starting_equity": tracker.starting_equity,
        "final_equity": round(float(total), 2),
        "total_return_pct": round((float(total) / tracker.starting_equity - 1) * 100, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "trades": len(tracker.trades),
        "win_rate_pct": round(100 * wins / len(tracker.trades), 1) if tracker.trades else 0.0,
        "halted": tracker.halted,
        "per_strategy": per_strategy,
        "trade_log": tracker.trades,
    }
