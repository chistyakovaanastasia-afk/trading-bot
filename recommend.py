#!/usr/bin/env python3
"""Tages-Empfehlungsreport (deutsch).

Übersetzt die Signale des Bots in konkrete Handlungsempfehlungen:
was kaufen/verkaufen, wie viel (passend zum Kapital), wo der Stop liegt,
und was die Strategie historisch pro Trade gebracht hat.

Simulation/Statistik, keine Anlageberatung — steht auch unter jedem Report.
"""

from __future__ import annotations

import json
import os
import sys

import pandas as pd
import yaml

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from marketdata.feed import fetch_all
from portfolio.tracker import PortfolioTracker
from risk.manager import RiskManager
from strategy import build

EXIT_RULE = {
    "mean_reversion": "verkaufen, sobald der Preis zum 20-Tage-Mittel zurückkehrt "
                      "(oder nach spätestens 10 Handelstagen)",
    "momentum": "verkaufen, wenn der Schlusskurs unter das 10-Tage-Tief fällt",
    "trend_following": "halten, solange der Trend läuft; verkaufen beim "
                       "Trendbruch (EMA20 kreuzt EMA50) oder am nachgezogenen Stop",
}


def strategy_stats(summary: dict | None, name: str) -> str:
    if not summary:
        return "keine Backtest-Statistik vorhanden"
    trades = [t for t in summary.get("trade_log", []) if t["strategy"] == name]
    if not trades:
        return "im 6-Monats-Backtest kein Trade dieser Strategie"
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] <= 0]
    holds = []
    for t in trades:
        try:
            holds.append((pd.Timestamp(t["closed"]) - pd.Timestamp(t["opened"])).days)
        except Exception:
            pass
    parts = [f"{len(trades)} Trades im 6-Monats-Backtest",
             f"Trefferquote {100 * len(wins) / len(trades):.0f}%"]
    if wins:
        parts.append(f"Ø Gewinn-Trade +{sum(wins) / len(wins):,.0f}")
    if losses:
        parts.append(f"Ø Verlust-Trade {sum(losses) / len(losses):,.0f}")
    if holds:
        parts.append(f"typische Haltedauer {sum(holds) / len(holds):.0f} Tage")
    return ", ".join(parts)


def main() -> None:
    offline = "--offline" in sys.argv
    with open(os.path.join(BASE, "config.yaml")) as f:
        cfg = yaml.safe_load(f)

    tracker = PortfolioTracker.load(
        cfg["account"]["starting_equity"],
        os.path.join(BASE, cfg["account"]["state_file"]))
    risk = RiskManager(cfg["risk"])
    strategies = {n: build(n, p) for n, p in cfg["strategies"].items()}
    history = fetch_all(list(cfg["instruments"]), days=400, refresh=not offline)
    closes = {s: float(df["Close"].iloc[-1]) for s, df in history.items()}
    equity = tracker.equity(closes)

    summary_path = os.path.join(BASE, "state", "backtest_summary.json")
    summary = None
    if os.path.exists(summary_path):
        with open(summary_path) as f:
            summary = json.load(f)

    day = max(df.index[-1] for df in history.values()).date()
    print(f"EMPFEHLUNGEN — Datenstand {day}")
    print(f"Simuliertes Kapital: {equity:,.0f}\n")

    if tracker.halted:
        print("!! NOTBREMSE AKTIV: Der Bot hat wegen zu hohen Verlusts alles "
              "verkauft und pausiert. Empfehlung: Strategie prüfen, nichts kaufen.\n")

    # Offene Positionen: Halten/Verkaufen-Empfehlung.
    if tracker.positions:
        print("BESTEHENDE POSITIONEN:")
        unreal = tracker.unrealized(closes)
        for sym, pos in tracker.positions.items():
            name = cfg["instruments"][sym]["name"]
            side = "Long" if pos["direction"] > 0 else "Short"
            print(f"- {name} ({sym}), {side}, {pos['qty']:g} Stück zu "
                  f"{pos['entry_price']:,.2f} gekauft. Aktuell: {closes[sym]:,.2f} "
                  f"({unreal.get(sym, 0):+,.0f}).")
            print(f"  Empfehlung: HALTEN. Verkaufen bei {pos['stop_price']:,.2f} "
                  f"(Absicherung) — oder {EXIT_RULE[pos['strategy']]}.")
        print()

    # Neue Signale: Kaufempfehlungen mit Größe und Stop.
    recs = 0
    for sym, inst in cfg["instruments"].items():
        df = history[sym]
        strat = strategies[inst["strategy"]]
        if len(df) < strat.warmup():
            continue
        sig = strat.entry(sym, df)
        if sig is None:
            continue
        decision = risk.evaluate(sym, sig.direction, closes[sym], equity, df,
                                 tracker.positions, history, tracker.halted,
                                 fractional=inst.get("fractional", False))
        name = inst["name"]
        action = "KAUFEN (Long)" if sig.direction > 0 else "LEERVERKAUFEN (Short)"
        if not decision.approved:
            print(f"SIGNAL OHNE EMPFEHLUNG: {name} ({sym}) hätte ein "
                  f"{action}-Signal ({sig.reason}), aber der Risikomanager "
                  f"blockiert: {decision.reason}.\n")
            continue
        recs += 1
        per10k = decision.qty / equity * 10000
        print(f"EMPFEHLUNG {recs}: {action} — {name} ({sym})")
        print(f"  Warum: {sig.reason}")
        print(f"  Wann: zum nächsten Kurs, ca. {closes[sym]:,.2f}")
        print(f"  Wie viel: {decision.qty:g} Stück bei {equity:,.0f} Kapital "
              f"(≈ {per10k:.2f} Stück je 10'000 Kapital) — riskiert 1% des Kapitals")
        print(f"  Verkaufen: spätestens bei {decision.stop_price:,.2f} "
              f"(Stop-Loss) — oder {EXIT_RULE[inst['strategy']]}")
        print(f"  Historie: {strategy_stats(summary, inst['strategy'])}\n")

    if recs == 0 and not tracker.positions:
        print("HEUTE KEINE KAUFEMPFEHLUNG. Keiner der fünf Märkte gibt aktuell "
              "ein Einstiegssignal — die beste Position ist Abwarten.\n")

    print("Hinweis: Alle Zahlen stammen aus einer Simulation mit Spielgeld und "
          "historischen Daten. Vergangene Ergebnisse garantieren keine künftigen "
          "Gewinne. Keine Anlageberatung.")


if __name__ == "__main__":
    main()
