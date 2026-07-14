#!/usr/bin/env python3
"""claude-fable-bot — multi-strategy paper trading bot.

Commands:
  backtest            Replay the last N months (default 6) through the engine.
  paper               Run one paper-trading daily cycle and persist state.
  brief --morning     Print/send the morning briefing.
  brief --evening     Print/send the evening report.
  status              Show current portfolio state.
  reset-halt          Clear the kill switch after a manual review.

Paper money only. There is intentionally no live-broker order routing here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import yaml

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from backtest.engine import run_backtest
from briefing.report import evening_report, morning_briefing
from briefing.telegram import send_telegram
from broker.paper import run_paper_cycle
from marketdata.feed import fetch_all
from portfolio.tracker import PortfolioTracker
from strategy import build


def load_config() -> dict:
    with open(os.path.join(BASE, "config.yaml")) as f:
        return yaml.safe_load(f)


def load_tracker(cfg: dict) -> PortfolioTracker:
    state_file = os.path.join(BASE, cfg["account"]["state_file"])
    return PortfolioTracker.load(cfg["account"]["starting_equity"], state_file)


def latest_prices(cfg: dict, refresh: bool) -> dict[str, float]:
    history = fetch_all(list(cfg["instruments"]), days=90, refresh=refresh)
    return {s: float(df["Close"].iloc[-1]) for s, df in history.items()}


def cmd_backtest(cfg: dict, args: argparse.Namespace) -> None:
    strategies = {name: build(name, params) for name, params in cfg["strategies"].items()}
    history = fetch_all(list(cfg["instruments"]), days=400, refresh=not args.offline)
    result = run_backtest(cfg, history, strategies, months=args.months,
                          verbose=args.verbose)

    trade_log = result.pop("trade_log")
    print("\n=== Backtest summary ===")
    for k, v in result.items():
        if k != "per_strategy":
            print(f"{k:20} {v}")
    print("\nPer strategy:")
    for name, s in result["per_strategy"].items():
        wr = 100 * s["wins"] / s["trades"] if s["trades"] else 0
        print(f"  {name:18} {s['trades']:3d} trades  win rate {wr:5.1f}%  "
              f"P&L {s['pnl']:+,.2f}")

    out = os.path.join(BASE, "state", "backtest_summary.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump({**result, "trade_log": trade_log}, f, indent=2)
    print(f"\nSaved to {out}")

    if result["sharpe"] < 0:
        print("\nWARNING: negative Sharpe ratio. The carousel rule applies: "
              "fix the strategy before going further. Do not paper trade this, "
              "and definitely do not fund it.")


def cmd_paper(cfg: dict, args: argparse.Namespace) -> None:
    tracker, events = run_paper_cycle(cfg, refresh=not args.offline)
    print(f"Paper cycle complete — {len(events)} event(s):")
    for e in events:
        print(f"  {e}")
    eq = tracker.equity_curve[-1]["equity"] if tracker.equity_curve else tracker.cash
    print(f"Equity: {eq:,.2f}  Open positions: {len(tracker.positions)}"
          f"{'  [HALTED]' if tracker.halted else ''}")


def cmd_brief(cfg: dict, args: argparse.Namespace) -> None:
    tracker = load_tracker(cfg)
    prices = latest_prices(cfg, refresh=not args.offline)
    if args.evening:
        summary_path = os.path.join(BASE, "state", "backtest_summary.json")
        summary = None
        if os.path.exists(summary_path):
            with open(summary_path) as f:
                summary = json.load(f)
        text = evening_report(tracker, prices, summary)
    else:
        text = morning_briefing(tracker, prices, cfg["risk"])
    if not send_telegram(text):
        print(text)
    else:
        print("Briefing sent to Telegram.")


def cmd_status(cfg: dict, args: argparse.Namespace) -> None:
    tracker = load_tracker(cfg)
    print(json.dumps({
        "cash": round(tracker.cash, 2),
        "positions": tracker.positions,
        "closed_trades": len(tracker.trades),
        "halted": tracker.halted,
        "equity_curve_tail": tracker.equity_curve[-5:],
    }, indent=2))


def cmd_reset_halt(cfg: dict, args: argparse.Namespace) -> None:
    tracker = load_tracker(cfg)
    if not tracker.halted:
        print("Kill switch is not active.")
        return
    tracker.halted = False
    tracker.peak_equity = tracker.equity({})  # re-anchor the drawdown peak
    tracker.save()
    print("Kill switch cleared. Peak equity re-anchored to current equity.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--offline", action="store_true",
                   help="use cached data only, no network fetch")
    sub = p.add_subparsers(dest="command", required=True)

    bt = sub.add_parser("backtest", help="run the historical backtest")
    bt.add_argument("--months", type=int, default=None)
    bt.add_argument("--verbose", action="store_true", help="print every fill")

    sub.add_parser("paper", help="run one paper-trading daily cycle")

    br = sub.add_parser("brief", help="morning briefing / evening report")
    g = br.add_mutually_exclusive_group(required=True)
    g.add_argument("--morning", action="store_true")
    g.add_argument("--evening", action="store_true")

    sub.add_parser("status", help="show portfolio state")
    sub.add_parser("reset-halt", help="clear the drawdown kill switch")

    args = p.parse_args()
    cfg = load_config()
    {
        "backtest": cmd_backtest,
        "paper": cmd_paper,
        "brief": cmd_brief,
        "status": cmd_status,
        "reset-halt": cmd_reset_halt,
    }[args.command](cfg, args)


if __name__ == "__main__":
    main()
