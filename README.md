# claude-fable-bot

A multi-strategy **paper trading** bot for five instruments, built after the
@raycfu "How to build a Claude Fable trading bot" carousel. One bot, three
strategies, five instruments:

| Instrument | Ticker | Strategy |
|---|---|---|
| S&P 500 ETF | `SPY` | Mean reversion (z-score vs 20-day mean) |
| Nasdaq 100 ETF | `QQQ` | Mean reversion |
| Bitcoin | `BTC-USD` | Momentum breakout (20-day high + volume) |
| Gold futures | `GC=F` | Trend following (20/50 EMA cross, ATR trail) |
| WTI Crude futures | `CL=F` | Trend following |

## The non-negotiable risk rules

Enforced in `risk/manager.py`, not in the strategies:

- **1% max risk per trade** — position size = 1% of equity / stop distance.
- **ATR-based sizing** — stops sit 2 ATRs from entry, so size adapts to volatility.
- **Correlation filter** — no new position that correlates > 0.80 with an
  existing same-direction position (no SPY + QQQ double-long).
- **Kill switch** — if equity drops 10% from its peak, everything is closed
  and the bot halts until you run `reset-halt` after a manual review.

## Setup

```bash
git clone https://github.com/chistyakovaanastasia-afk/trading-bot && cd trading-bot
pip install -r requirements.txt
```

## The workflow (in this order)

**Step 1 — review the code.** Read every file before running anything.

**Step 2 — backtest first.** Never run a bot on real money without this.

```bash
python main.py backtest            # last 6 months, slippage + commission included
python main.py backtest --verbose  # print every fill
```

If any strategy shows a negative Sharpe ratio, fix it before going further.

**Step 3 — paper trade for two weeks.** Fake money, real market data. Run one
cycle per day after the US close (cron, or a Claude Cowork / Code automation):

```bash
python main.py paper
```

State persists in `state/portfolio.json` between runs. This catches what
backtesting cannot: stale data, fill assumptions, and edge cases during
volatile swings.

**Step 4 — daily briefings.** Two messages a day. With `TELEGRAM_BOT_TOKEN`
and `TELEGRAM_CHAT_ID` set they go to Telegram; otherwise they print to stdout.

```bash
python main.py brief --morning   # open positions, yesterday's P&L, risk flags
python main.py brief --evening   # trades executed, best/worst, backtest comparison
```

Other commands: `python main.py status`, `python main.py reset-halt`,
`--offline` to use cached data only.

## What this deliberately does not do

There is **no live-broker integration** and no order routing to real money.
Backtest results are hypothetical, subject to overfitting, and not investment
advice. If you ever take a system like this live, that is your decision and
your risk — the two-week paper trading rule exists precisely so you have
evidence before committing a single real dollar.

## Layout

```
main.py                  CLI: backtest / paper / brief / status / reset-halt
config.yaml              instruments, strategy params, risk limits
strategy/                mean_reversion.py, momentum.py, trend_following.py
risk/manager.py          sizing, correlation filter, drawdown kill switch
portfolio/tracker.py     positions, cash, trade log, equity curve (JSON state)
marketdata/feed.py       Yahoo Finance daily bars with CSV cache + ATR
backtest/engine.py       daily-bar replay; same code path the paper trader uses
broker/paper.py          one persistent paper-trading cycle per day
briefing/                morning/evening reports, optional Telegram delivery
```
