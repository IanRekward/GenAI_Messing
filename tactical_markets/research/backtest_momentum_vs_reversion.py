"""
2026-06-10 review backtest — momentum vs reversion at the 5-day horizon.

Question: the live signal (5d sector momentum, buy winner / sell loser, hold 5-7d)
has been anti-predictive over its first ~5 weeks. Is the premise wrong always,
or just lately? This replicates the production selection logic over ~2 years and
measures forward 5-day pair returns under both directions.

Analysis only. Touches no production code. Run: python research/backtest_momentum_vs_reversion.py
"""
from __future__ import annotations

import statistics as st
from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf

BASE = Path(__file__).parent.parent
UNIVERSE = yaml.safe_load((BASE / "config" / "universe.yaml").read_text())
TH = yaml.safe_load((BASE / "config" / "thresholds.yaml").read_text())

TICKERS = UNIVERSE["sectors"] + UNIVERSE["broad"]
SPREAD = TH["spread_pct"] / 100          # 1.5%
MOM_W = TH["momentum_window"]            # 5
MA_W = TH["ma_window"]                   # 20
HOLD = TH["hold_days"]                   # 5  (forward window we score)

YEARS = "2y"


def pairs_for_day(closes: pd.DataFrame, i: int, apply_ma_filter: bool):
    """Replicate production greedy top-vs-bottom pairing as of row i.

    Returns list of (buy, sell, spread) using MOMENTUM convention (buy=winner).
    Reversion is the same pairs with legs swapped; handled by caller.
    """
    latest = closes.iloc[i]
    prev = closes.iloc[i - MOM_W]
    momentum = (latest / prev - 1).dropna()
    ma = closes.iloc[i - MA_W + 1 : i + 1].mean()
    ranked = momentum.sort_values(ascending=False)

    out, used_b, used_s = [], set(), set()
    while True:
        buy = next((t for t in ranked.index if t not in used_b), None)
        sell = next((t for t in reversed(ranked.index) if t not in used_s), None)
        if buy is None or sell is None or buy == sell:
            break
        spread = ranked[buy] - ranked[sell]
        if spread < SPREAD:
            break
        if apply_ma_filter and latest[buy] <= ma[buy]:
            used_b.add(buy)
            continue
        out.append((buy, sell, spread * 100))
        used_b.add(buy)
        used_s.add(sell)
    return out


def fwd_ret(closes: pd.DataFrame, i: int, ticker: str) -> float | None:
    if i + HOLD >= len(closes):
        return None
    p0, p1 = closes.iloc[i][ticker], closes.iloc[i + HOLD][ticker]
    if pd.isna(p0) or pd.isna(p1):
        return None
    return (p1 / p0 - 1) * 100


def summarize(label: str, rets: list[float]):
    if not rets:
        print(f"{label}: no trades")
        return
    wins = sum(1 for r in rets if r > 0)
    mean, sd = st.mean(rets), st.pstdev(rets)
    sharpe = mean / sd if sd else 0.0
    print(
        f"{label:34} n={len(rets):>4}  win={wins/len(rets)*100:>3.0f}%  "
        f"mean={mean:+.2f}%  med={st.median(rets):+.2f}%  "
        f"sd={sd:.2f}  sharpe/trade={sharpe:+.2f}  sum={sum(rets):+.0f}%"
    )


def run():
    raw = yf.download(TICKERS, period=YEARS, auto_adjust=True, progress=False)
    closes = raw["Close"].dropna(how="all")
    print(f"data: {closes.shape[0]} days  {closes.index.min().date()} -> {closes.index.max().date()}")
    print(f"universe: {len(TICKERS)} tickers  |  spread gate {SPREAD*100:.1f}%  mom {MOM_W}d  hold {HOLD}d  MA {MA_W}d\n")

    # collectors: (top_pair_only, all_pairs) x (momentum, reversion)
    mom_top, rev_top, mom_all, rev_all = [], [], [], []
    # non-overlapping (step = HOLD) top-pair, to cut autocorrelation
    mom_top_no, rev_top_no = [], []

    start = MA_W
    for i in range(start, len(closes)):
        ps = pairs_for_day(closes, i, apply_ma_filter=True)
        if not ps:
            continue
        nonoverlap = (i - start) % HOLD == 0
        for rank, (buy, sell, spread) in enumerate(ps):
            rb, rs = fwd_ret(closes, i, buy), fwd_ret(closes, i, sell)
            if rb is None or rs is None:
                continue
            mom_pair = rb - rs       # long winner / short loser
            rev_pair = rs - rb       # long loser  / short winner
            mom_all.append(mom_pair)
            rev_all.append(rev_pair)
            if rank == 0:            # production headline = strongest pair
                mom_top.append(mom_pair)
                rev_top.append(rev_pair)
                if nonoverlap:
                    mom_top_no.append(mom_pair)
                    rev_top_no.append(rev_pair)

    print("=== Top pair per day (closest to what gets read on the phone) ===")
    summarize("MOMENTUM  buy winner/sell loser", mom_top)
    summarize("REVERSION buy loser/sell winner", rev_top)
    print("\n=== Top pair, NON-OVERLAPPING (step=5d, ~independent) ===")
    summarize("MOMENTUM", mom_top_no)
    summarize("REVERSION", rev_top_no)
    print("\n=== All emitted pairs (multi-thesis days inflate n & correlation) ===")
    summarize("MOMENTUM", mom_all)
    summarize("REVERSION", rev_all)


if __name__ == "__main__":
    run()
