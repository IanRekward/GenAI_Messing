"""Historical replay: what would top-N multi-thesis output have looked like?

Answers the M1 (multi-thesis) question from bot-integration-asks.md:
  "Would top-3 distinct pairs diversify, or would they all collapse to 3x XLK?"

Runs offline against yfinance. Does not touch live code path.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf

ROOT = Path(__file__).parent.parent.parent
UNIVERSE = yaml.safe_load((ROOT / "config" / "universe.yaml").read_text())
THRESH = yaml.safe_load((ROOT / "config" / "thresholds.yaml").read_text())

TICKERS = UNIVERSE["sectors"] + UNIVERSE["broad"]
MOM_WINDOW = THRESH["momentum_window"]
MA_WINDOW = THRESH["ma_window"]
SPREAD_GATE = THRESH["spread_pct"] / 100
TOP_N = 3


def main() -> None:
    raw = yf.download(TICKERS, period="60d", auto_adjust=True, progress=False)
    closes: pd.DataFrame = raw["Close"].dropna(how="all")

    last_n_days = 10
    trading_days = closes.index[-last_n_days:]

    print(f"Replaying top-{TOP_N} multi-thesis over last {last_n_days} trading days\n")
    print(f"{'date':<12} {'rank':<6} {'buy':<6} {'sell':<6} {'spread':>8} {'buy_mom':>8} {'sell_mom':>9} {'distinct?':>10}")
    print("-" * 80)

    diversification_stats = {"distinct_buys": [], "distinct_pairs": []}

    for day in trading_days:
        idx = closes.index.get_loc(day)
        if idx < MOM_WINDOW or idx < MA_WINDOW - 1:
            continue

        latest = closes.iloc[idx]
        prev_mom = closes.iloc[idx - MOM_WINDOW]
        ma = closes.iloc[idx - MA_WINDOW + 1 : idx + 1].mean()

        momentum = (latest / prev_mom - 1).dropna()
        ranked = momentum.sort_values(ascending=False)

        passing_pairs = []
        used_buys = set()
        used_sells = set()

        for rank in range(TOP_N):
            available_buys = [t for t in ranked.index if t not in used_buys]
            available_sells = [t for t in ranked.index[::-1] if t not in used_sells]
            if not available_buys or not available_sells:
                break

            buy = available_buys[0]
            sell = available_sells[0]
            if buy == sell:
                break

            buy_mom = ranked[buy]
            sell_mom = ranked[sell]
            spread = buy_mom - sell_mom

            if spread < SPREAD_GATE:
                break
            if latest[buy] <= ma[buy]:
                continue

            passing_pairs.append({
                "rank": rank + 1,
                "buy": buy, "sell": sell,
                "spread_pct": spread * 100,
                "buy_mom_pct": buy_mom * 100,
                "sell_mom_pct": sell_mom * 100,
            })
            used_buys.add(buy)
            used_sells.add(sell)

        distinct_buys = len({p["buy"] for p in passing_pairs})
        distinct_pairs = len({(p["buy"], p["sell"]) for p in passing_pairs})
        diversification_stats["distinct_buys"].append(distinct_buys)
        diversification_stats["distinct_pairs"].append(distinct_pairs)

        date_str = day.strftime("%Y-%m-%d")
        if not passing_pairs:
            print(f"{date_str:<12} (no pairs passed gate)")
            continue

        for p in passing_pairs:
            marker = "yes" if distinct_buys == len(passing_pairs) else "OVERLAP"
            print(f"{date_str:<12} #{p['rank']:<5} {p['buy']:<6} {p['sell']:<6} "
                  f"{p['spread_pct']:>7.2f}% {p['buy_mom_pct']:>+7.2f}% {p['sell_mom_pct']:>+8.2f}%   {marker}")

    print()
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    avg_distinct_buys = sum(diversification_stats["distinct_buys"]) / max(len(diversification_stats["distinct_buys"]), 1)
    days_full_diversification = sum(1 for n in diversification_stats["distinct_buys"] if n == TOP_N)
    days_total = len(diversification_stats["distinct_buys"])
    print(f"Avg distinct buy-side tickers per day (target = {TOP_N}): {avg_distinct_buys:.2f}")
    print(f"Days with full {TOP_N}-way diversification: {days_full_diversification}/{days_total}")


if __name__ == "__main__":
    main()
