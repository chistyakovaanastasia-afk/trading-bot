"""Daily briefings.

Morning: open positions, yesterday's P&L, risk flags.
Evening: trades executed today, best and worst trade, and whether live
performance is tracking the backtest.
"""

from __future__ import annotations

from datetime import date

from portfolio.tracker import PortfolioTracker


def _fmt_pos(symbol: str, pos: dict, unreal: float) -> str:
    side = "LONG" if pos["direction"] > 0 else "SHORT"
    return (f"  {side} {symbol}  {pos['qty']:g} @ {pos['entry_price']:.2f}  "
            f"stop {pos['stop_price']:.2f}  P&L {unreal:+,.2f}  [{pos['strategy']}]")


def morning_briefing(tracker: PortfolioTracker, prices: dict[str, float],
                     risk_cfg: dict) -> str:
    today = date.today().isoformat()
    lines = [f"Good morning — trading brief for {today}", ""]

    equity = tracker.equity(prices)
    lines.append(f"Equity: {equity:,.2f}  (peak {tracker.peak_equity:,.2f})")

    curve = tracker.equity_curve
    if len(curve) >= 2:
        change = curve[-1]["equity"] - curve[-2]["equity"]
        lines.append(f"Yesterday's P&L: {change:+,.2f}")
    lines.append("")

    if tracker.positions:
        lines.append(f"Open positions ({len(tracker.positions)}):")
        unreal = tracker.unrealized(prices)
        for symbol, pos in tracker.positions.items():
            lines.append(_fmt_pos(symbol, pos, unreal.get(symbol, 0.0)))
    else:
        lines.append("No open positions.")
    lines.append("")

    # Risk flags.
    flags = []
    if tracker.halted:
        flags.append("KILL SWITCH ACTIVE — bot is halted, manual reset required "
                     "(python main.py reset-halt)")
    dd = 1 - equity / tracker.peak_equity if tracker.peak_equity else 0
    if dd > risk_cfg["max_drawdown"] * 0.5:
        flags.append(f"Drawdown {dd:.1%} — more than half way to the "
                     f"{risk_cfg['max_drawdown']:.0%} kill switch")
    if len(tracker.positions) >= risk_cfg["max_open_positions"]:
        flags.append("At max position count — new signals will be blocked")
    lines.append("Risk flags: " + ("; ".join(flags) if flags else "none"))
    return "\n".join(lines)


def evening_report(tracker: PortfolioTracker, prices: dict[str, float],
                   backtest_summary: dict | None = None) -> str:
    today = date.today().isoformat()
    lines = [f"Evening report for {today}", ""]

    todays = tracker.trades_on(today)
    if todays:
        lines.append(f"Trades closed today ({len(todays)}):")
        for t in todays:
            side = "LONG" if t["direction"] > 0 else "SHORT"
            lines.append(f"  {side} {t['symbol']}  {t['entry_price']:.2f} -> "
                         f"{t['exit_price']:.2f}  P&L {t['pnl']:+,.2f}  ({t['exit_reason']})")
        best = max(todays, key=lambda t: t["pnl"])
        worst = min(todays, key=lambda t: t["pnl"])
        lines.append(f"Best: {best['symbol']} {best['pnl']:+,.2f}   "
                     f"Worst: {worst['symbol']} {worst['pnl']:+,.2f}")
    else:
        lines.append("No trades closed today.")
    lines.append("")

    equity = tracker.equity(prices)
    ret = (equity / tracker.starting_equity - 1) * 100
    lines.append(f"Equity: {equity:,.2f}  ({ret:+.2f}% since start)")

    if backtest_summary:
        bt = backtest_summary
        lines.append("")
        lines.append(f"Backtest comparison: backtest returned "
                     f"{bt['total_return_pct']:+.2f}% over {len(bt['trade_log'])} trades "
                     f"(Sharpe {bt['sharpe']}, max DD {bt['max_drawdown_pct']}%). "
                     f"{'On track.' if ret >= 0 or ret > bt['max_drawdown_pct'] * -1 else 'Lagging the backtest — review before continuing.'}")
    return "\n".join(lines)
