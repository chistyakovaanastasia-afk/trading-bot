#!/usr/bin/env python3
"""Wöchentlicher Trend-Scanner (deutsch).

Durchsucht das Universum grosser US-Aktien (scanner_universe.txt) und
ordnet sie nach Trendstärke. Das ist reine Mustererkennung auf Kursen:
"Was ist zuletzt stabil gestiegen?" — nicht "Was ist ein gutes
Unternehmen?" und erst recht kein Blick in die Zukunft.

Kriterien (klassisches Momentum):
  - 12-Monats-Rendite ohne den letzten Monat (Gewicht 50%)
  - 6-Monats-Rendite (Gewicht 30%)
  - Abstand über dem 200-Tage-Durchschnitt (Gewicht 20%)
Qualifikation: Kurs über dem 200-Tage-Durchschnitt und positive
6-Monats-Rendite — sonst kein Aufwärtstrend, keine Aufnahme.
"""

from __future__ import annotations

import os
import sys
import time

import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from marketdata.feed import fetch_history

TOP_N = 10


def load_universe() -> list[str]:
    path = os.path.join(BASE, "scanner_universe.txt")
    with open(path) as f:
        return [ln.strip() for ln in f
                if ln.strip() and not ln.strip().startswith("#")]


def metrics(df: pd.DataFrame) -> dict | None:
    close = df["Close"]
    if len(close) < 260:
        return None
    last = float(close.iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1])
    ret_12_1 = float(close.iloc[-21] / close.iloc[-252] - 1)
    ret_6m = float(last / close.iloc[-126] - 1)
    above_ma = last / ma200 - 1
    daily = close.pct_change().tail(126)
    vol = float(daily.std() * (252 ** 0.5))
    return {"price": last, "ret_12_1": ret_12_1, "ret_6m": ret_6m,
            "above_ma200": above_ma, "vol": vol}


def scan(refresh: bool = True) -> pd.DataFrame:
    rows = {}
    for i, sym in enumerate(load_universe()):
        try:
            df = fetch_history(sym, days=420, refresh=refresh)
            m = metrics(df)
            if m:
                rows[sym] = m
        except Exception as exc:
            print(f"[scanner] {sym} übersprungen: {exc}", file=sys.stderr)
        if refresh:
            time.sleep(0.4)  # Yahoo nicht hämmern
        if (i + 1) % 20 == 0:
            print(f"[scanner] {i + 1} Aktien geprüft...", file=sys.stderr)

    t = pd.DataFrame(rows).T
    qualified = t[(t["above_ma200"] > 0) & (t["ret_6m"] > 0)].copy()
    for col, w in [("ret_12_1", 0.5), ("ret_6m", 0.3), ("above_ma200", 0.2)]:
        qualified[f"rank_{col}"] = qualified[col].rank(pct=True) * w
    qualified["score"] = qualified[[c for c in qualified.columns
                                    if c.startswith("rank_")]].sum(axis=1)
    return qualified.sort_values("score", ascending=False)


def main() -> None:
    refresh = "--offline" not in sys.argv
    ranked = scan(refresh=refresh)
    total = len(load_universe())

    print(f"\nTREND-SCANNER — Top {TOP_N} von {total} geprüften US-Aktien")
    print("(sortiert nach Trendstärke der letzten 6-12 Monate)\n")
    if ranked.empty:
        print("Aktuell qualifiziert sich keine Aktie — der breite Markt ist "
              "in keinem Aufwärtstrend. Empfehlung: abwarten.")
    for i, (sym, r) in enumerate(ranked.head(TOP_N).iterrows(), 1):
        print(f"{i:2}. {sym:6}  Kurs {r['price']:10,.2f}   "
              f"12M {r['ret_12_1']:+7.1%}   6M {r['ret_6m']:+7.1%}   "
              f"über 200-Tage-Schnitt {r['above_ma200']:+6.1%}   "
              f"Schwankung {r['vol']:5.1%}/Jahr")

    print(f"\nSo liest du das: Diese {TOP_N} Aktien sind zuletzt am stabilsten "
          "gestiegen. Das sagt NICHT, dass sie weiter steigen — Trends brechen, "
          "oft abrupt. Hohe 'Schwankung' bedeutet: entsprechend heftige "
          "Verluste sind jederzeit möglich.")
    print("Keine Anlageberatung. Wer einzelne Aktien kauft, sollte nur Geld "
          "einsetzen, dessen Verlust er verkraftet — die Basis bleibt ein "
          "breit gestreuter ETF-Sparplan.")


if __name__ == "__main__":
    main()
