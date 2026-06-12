"""
2026-06-12 follow-up — does a regime-adaptive switch actually work?

Ian's question: momentum is wrong *now* but not *always*. Instead of a static flip,
can we detect which regime we're in and trade that direction?

This tests the simplest honest version: "trade whichever direction made money over
the trailing K realized trades." It does NOT cheat — at entry day t it only uses
trades whose 5-day outcome is already known (entry <= t - HOLD).

If regimes persist, adaptive beats both static rules. If they whipsaw, adaptive
lags and loses to both. The diagnostic at the bottom answers *why* directly.

Analysis only. Run: python research/backtest_adaptive_switch.py
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
SPREAD = TH["spread_pct"] / 100
MOM_W, MA_W, HOLD = TH["momentum_window"], TH["ma_window"], TH["hold_days"]


def top_pair(closes, i):
    latest, prev = closes.iloc[i], closes.iloc[i - MOM_W]
    momentum = (latest / prev - 1).dropna()
    ma = closes.iloc[i - MA_W + 1 : i + 1].mean()
    ranked = momentum.sort_values(ascending=False)
    used_b = set()
    while True:
        buy = next((t for t in ranked.index if t not in used_b), None)
        sell = next((t for t in reversed(ranked.index)), None)
        if buy is None or sell is None or buy == sell:
            return None
        if ranked[buy] - ranked[sell] < SPREAD:
            return None
        if latest[buy] <= ma[buy]:
            used_b.add(buy)
            continue
        return buy, sell


def fwd(closes, i, tk):
    if i + HOLD >= len(closes):
        return None
    p0, p1 = closes.iloc[i][tk], closes.iloc[i + HOLD][tk]
    if pd.isna(p0) or pd.isna(p1):
        return None
    return (p1 / p0 - 1) * 100


def stats(label, rets):
    if not rets:
        print(f"{label}: none"); return
    sd = st.pstdev(rets)
    print(f"{label:32} n={len(rets):>4}  win={sum(r>0 for r in rets)/len(rets)*100:>3.0f}%  "
          f"mean={st.mean(rets):+.3f}%  sharpe/trade={st.mean(rets)/sd if sd else 0:+.3f}  "
          f"sum={sum(rets):+.0f}%")


def run():
    closes = yf.download(TICKERS, period="2y", auto_adjust=True, progress=False)["Close"].dropna(how="all")
    print(f"data: {len(closes)} days  {closes.index.min().date()} -> {closes.index.max().date()}\n")

    # Build the trade tape: each entry's MOMENTUM pair return, realized HOLD days later.
    trades = []  # (entry_idx, realize_idx, mom_ret)
    for i in range(MA_W, len(closes) - HOLD):
        p = top_pair(closes, i)
        if not p:
            continue
        rb, rs = fwd(closes, i, p[0]), fwd(closes, i, p[1])
        if rb is None or rs is None:
            continue
        trades.append((i, i + HOLD, rb - rs))

    mom = [t[2] for t in trades]
    rev = [-t[2] for t in trades]

    print("=== Static baselines (top pair, daily/overlapping) ===")
    stats("MOMENTUM (as built)", mom)
    stats("REVERSION (static flip)", rev)
    stats("ORACLE (always right dir)", [abs(x) for x in mom])  # unachievable ceiling

    print("\n=== ADAPTIVE: follow the recently-winning direction ===")
    print("(at entry t, use only trades realized by t; pick dir = sign of trailing-K mean)")
    for K in (5, 10, 20, 40):
        chosen = []
        for idx, (ei, ri, mr) in enumerate(trades):
            known = [t[2] for t in trades[:idx] if t[1] <= ei]   # causal: outcome already known
            if len(known) < K:
                continue
            trail = st.mean(known[-K:])
            chosen.append(mr if trail > 0 else -mr)              # follow recent winner
        stats(f"adaptive K={K}", chosen)

    print("\n=== WHY: does the regime persist (is it detectable)? ===")
    # Lag-1 autocorrelation of per-trade momentum return, and sign-persistence hit rate.
    if len(mom) > 2:
        m = st.mean(mom)
        num = sum((mom[i]-m)*(mom[i+1]-m) for i in range(len(mom)-1))
        den = sum((x-m)**2 for x in mom)
        ac1 = num/den if den else 0
        sign_hit = sum((mom[i] > 0) == (mom[i+1] > 0) for i in range(len(mom)-1)) / (len(mom)-1)
        print(f"lag-1 autocorrelation of momentum-pair return: {ac1:+.3f}  (near 0 = no persistence)")
        print(f"P(next trade same sign as last): {sign_hit*100:.0f}%  (~50% = coin flip, switch can't time it)")


if __name__ == "__main__":
    run()
