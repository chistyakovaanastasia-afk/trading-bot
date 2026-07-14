"""Paper broker.

Fake money, real market data. Runs the same daily cycle as the backtest
against the latest completed daily bars, and persists the portfolio to the
JSON state file between runs. Schedule this once per day after the US
close (e.g. via cron or a Claude Cowork automation).

There is deliberately no live-broker integration in this repo: the
carousel's own rule applies — never run a bot on real money without a
backtest and two weeks of paper trading.
"""

from __future__ import annotations

import os

from backtest.engine import daily_cycle
from marketdata.feed import fetch_all
from portfolio.tracker import PortfolioTracker
from risk.manager import RiskManager
from strategy import build


def run_paper_cycle(cfg: dict, refresh: bool = True) -> tuple[PortfolioTracker, list[str]]:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    state_file = os.path.join(base, cfg["account"]["state_file"])
    tracker = PortfolioTracker.load(cfg["account"]["starting_equity"], state_file)

    strategies = {name: build(name, params) for name, params in cfg["strategies"].items()}
    risk = RiskManager(cfg["risk"])
    history = fetch_all(list(cfg["instruments"]), days=400, refresh=refresh)

    # Trade the most recent completed bar; feeds that lag (holidays, stale
    # cache) are skipped inside the cycle rather than traded on old prices.
    day = max(df.index[-1] for df in history.values()).strftime("%Y-%m-%d")
    events = daily_cycle(day, tracker, strategies, risk, history,
                         cfg["instruments"], cfg["execution"])
    tracker.save()
    return tracker, events
