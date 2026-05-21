"""Out-of-sample (walk-forward) validation of sector rotation parameters.

Question this answers: are the in-sample sensitivity-best parameters likely to
keep working out-of-sample, or are they overfit to the 2014-2026 window?

Method:
  1. Hold-out split: TRAIN = 2014-01-01 to 2019-12-31, TEST = 2020-01-01 onwards
     (TEST covers COVID crash, 2022 bear market, post-COVID recovery — diverse regimes)
  2. Full sensitivity sweep on TRAIN only (same 288-combo grid as sensitivity.py).
  3. Pick top-N param combos by Sharpe from TRAIN.
  4. Apply each top-N combo to TEST (out-of-sample).
  5. Also apply CURRENT LIVE params and BUY-HOLD-SPY benchmark to TEST.
  6. Compare in-sample-best vs OOS-realized — if OOS performance collapses, params
     are overfit. If OOS holds up, params have real edge.

Output: research/data/walk_forward_report.md + walk_forward.csv
"""
import sys
import time
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from compare_strategies import (
    LIVE_SIGNAL_UNIVERSE,
    OUTPUT_DIR,
    _run_rotation_backtest,
    fetch_prices,
    metrics,
    strat_buy_hold,
)

TRAIN_START = "2014-01-01"
TRAIN_END = "2019-12-31"
TEST_START = "2020-01-01"
TOP_N_BY_SHARPE = 10
TOP_N_BY_CAGR = 10

POSITION_SIZES = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
MAX_POSITIONS = [1, 3, 5, 10]
HOLD_DAYS = [3, 5, 10, 21]
SPREAD_THRESHOLDS = [0.005, 0.015, 0.030]

LIVE_PARAMS = {
    "position_size": 0.10,
    "max_positions": 5,
    "hold_days": 5,
    "spread_threshold": 0.015,
}


def _slice(prices: pd.DataFrame, start: str, end: str | None = None) -> pd.DataFrame:
    """Return rows whose index falls in [start, end]."""
    if end is None:
        return prices.loc[start:]
    return prices.loc[start:end]


def _run_one(prices: pd.DataFrame, position_size: float, max_positions: int,
             hold_days: int, spread_threshold: float) -> dict:
    # Cast — pandas iterrows can yield numpy.float64 for int columns
    max_positions = int(max_positions)
    hold_days = int(hold_days)
    nav = _run_rotation_backtest(
        prices,
        LIVE_SIGNAL_UNIVERSE,
        momentum_window=5,  # current strategy uses 5-day momentum throughout
        hold_days=hold_days,
        spread_threshold=float(spread_threshold),
        max_positions=max_positions,
        position_size=float(position_size),
    )
    m = metrics(nav)
    return {
        "position_size": position_size,
        "max_positions": max_positions,
        "hold_days": hold_days,
        "spread_threshold": spread_threshold,
        **m,
    }


def run_sweep(prices: pd.DataFrame, label: str) -> pd.DataFrame:
    combos = list(product(POSITION_SIZES, MAX_POSITIONS, HOLD_DAYS, SPREAD_THRESHOLDS))
    print(f"[{label}] running {len(combos)} backtests on {len(prices)} bars "
          f"({prices.index[0].date()} -> {prices.index[-1].date()})...")
    start_t = time.time()
    rows = []
    for i, (pos, mp, hd, sp) in enumerate(combos, 1):
        rows.append(_run_one(prices, pos, mp, hd, sp))
        if i % 50 == 0 or i == len(combos):
            print(f"  [{label}] {i}/{len(combos)} ({time.time() - start_t:.0f}s)")
    return pd.DataFrame(rows)


def _format_param_row(row, prefix: str = "") -> str:
    return (
        f"{prefix}pos={row['position_size']}, max={row['max_positions']}, "
        f"hold={row['hold_days']}, spread={row['spread_threshold']}"
    )


def write_report(train_df: pd.DataFrame, test_df: pd.DataFrame,
                 live_test: dict, spy_test: dict, output_path: Path) -> None:
    top_sharpe_train = train_df.nlargest(TOP_N_BY_SHARPE, "sharpe")
    top_cagr_train = train_df.nlargest(TOP_N_BY_CAGR, "cagr_pct")

    lines = [
        "# Walk-Forward (Out-of-Sample) Validation",
        "",
        f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"**TRAIN window:** {TRAIN_START} to {TRAIN_END} (in-sample, ~6 years)",
        f"**TEST window:** {TEST_START} to today (out-of-sample, ~6+ years, includes COVID crash + 2022 bear)",
        "",
        "## Question",
        "",
        "Are the in-sample sensitivity-best sector-rotation parameters likely to keep working out-of-sample, or are they overfit to the 2014-2026 window the sweep was originally run on?",
        "",
        "## Method",
        "",
        "1. Run the same 288-combo sensitivity sweep, but only on the TRAIN window.",
        "2. Identify the top-10 combos by Sharpe AND the top-10 by CAGR from TRAIN.",
        "3. Apply each of those param sets to the TEST window without re-tuning.",
        "4. Compare to the current LIVE params (pos=0.10, max=5, hold=5, spread=0.015) and BUY-HOLD-SPY benchmark, both applied to the same TEST window.",
        "",
        "## TRAIN summary (in-sample, for reference)",
        "",
        "### Top 10 by Sharpe — TRAIN",
        "",
        top_sharpe_train.to_markdown(index=False),
        "",
        "### Top 10 by CAGR — TRAIN",
        "",
        top_cagr_train.to_markdown(index=False),
        "",
        "## TEST results (out-of-sample)",
        "",
        "These are the same TRAIN-best params **applied to the TEST window without re-tuning**. If params hold up here, they have real out-of-sample edge.",
        "",
        "### Top-10-by-Sharpe-on-TRAIN, evaluated on TEST",
        "",
    ]

    # Apply each TRAIN-top to TEST
    test_rows = []
    for _, r in top_sharpe_train.iterrows():
        test_metrics = _run_one(
            test_df, r["position_size"], r["max_positions"],
            r["hold_days"], r["spread_threshold"]
        )
        test_rows.append({
            "rank_in_train_by_sharpe": int(top_sharpe_train.index.get_loc(r.name)) + 1,
            **test_metrics,
        })
    test_top_sharpe_df = pd.DataFrame(test_rows)
    lines.append(test_top_sharpe_df.to_markdown(index=False))
    lines.append("")

    lines.append("### Top-10-by-CAGR-on-TRAIN, evaluated on TEST")
    lines.append("")
    test_rows = []
    for _, r in top_cagr_train.iterrows():
        test_metrics = _run_one(
            test_df, r["position_size"], r["max_positions"],
            r["hold_days"], r["spread_threshold"]
        )
        test_rows.append({
            "rank_in_train_by_cagr": int(top_cagr_train.index.get_loc(r.name)) + 1,
            **test_metrics,
        })
    test_top_cagr_df = pd.DataFrame(test_rows)
    lines.append(test_top_cagr_df.to_markdown(index=False))
    lines.append("")

    lines.append("### Benchmark comparisons on TEST")
    lines.append("")
    lines.append(f"- **CURRENT LIVE params** (pos=0.10, max=5, hold=5, spread=0.015): "
                 f"CAGR {live_test['cagr_pct']}%, Sharpe {live_test['sharpe']}, MaxDD {live_test['max_drawdown_pct']}%, Calmar {live_test['calmar']}")
    lines.append(f"- **BUY-HOLD-SPY**: CAGR {spy_test['cagr_pct']}%, Sharpe {spy_test['sharpe']}, MaxDD {spy_test['max_drawdown_pct']}%, Calmar {spy_test['calmar']}")
    lines.append("")

    # Verdict
    lines.append("## Verdict")
    lines.append("")
    best_test_sharpe_oos = test_top_sharpe_df["sharpe"].max()
    best_test_cagr_oos = test_top_cagr_df["cagr_pct"].max()
    median_test_cagr_oos = test_top_sharpe_df["cagr_pct"].median()

    if best_test_cagr_oos >= spy_test["cagr_pct"]:
        verdict = (
            f"**Out-of-sample edge confirmed.** Best TRAIN-top param set achieves "
            f"{best_test_cagr_oos:.2f}% CAGR on TEST, beating buy-hold-SPY ({spy_test['cagr_pct']:.2f}%). "
            f"Median across top-Sharpe-TRAIN params: {median_test_cagr_oos:.2f}% CAGR on TEST. "
            f"Sensitivity-best params have defensible out-of-sample evidence — proceed with re-param "
            f"or A/B test (Option B or C) carries lower overfit risk."
        )
    elif best_test_cagr_oos >= spy_test["cagr_pct"] * 0.8:
        verdict = (
            f"**Marginal.** Best TRAIN-top achieves {best_test_cagr_oos:.2f}% CAGR on TEST vs "
            f"buy-hold-SPY {spy_test['cagr_pct']:.2f}%. Within 80% but below benchmark. "
            f"Sensitivity-best params are not catastrophically overfit but don't have a clean edge either. "
            f"Re-paramming may move the needle modestly; switching signal entirely may be needed for real edge."
        )
    else:
        verdict = (
            f"**Sensitivity-best params do NOT survive out-of-sample.** Best TRAIN-top achieves only "
            f"{best_test_cagr_oos:.2f}% CAGR on TEST vs buy-hold-SPY {spy_test['cagr_pct']:.2f}%. "
            f"In-sample sweep was overfit to the 2014-2019 regime. Re-paramming will NOT fix the strategy. "
            f"The 5-day sector rotation signal itself is the bottleneck; switching to a different signal "
            f"(monthly momentum, dual momentum, 60/40, trend-following SPY) is the only defensible path forward."
        )
    lines.append(verdict)
    lines.append("")

    # Decision matrix
    lines.append("## What this means for Option B vs C vs new-signal")
    lines.append("")
    lines.append(f"- **Option B (re-param to TRAIN-best 21d-style params):** OOS evidence says this is "
                 f"{'reasonable' if best_test_cagr_oos >= spy_test['cagr_pct'] * 0.8 else 'unlikely to help'}.")
    lines.append(f"- **Option C (parallel A/B paper):** OOS evidence says "
                 f"{'gather live data to confirm' if best_test_cagr_oos >= spy_test['cagr_pct'] * 0.8 else 'low expected value — both variants will likely underperform'}.")
    lines.append(f"- **Switch signal entirely:** look at compare_strategies.py — "
                 f"trend_following_spy (10.07% CAGR, Sharpe 0.90), sixty_forty (9.48%, 0.89), and "
                 f"sector_momentum_top3_monthly (11.74%, 0.74) all dominated sector_rotation_5d_live "
                 f"in-sample. The btc_stress_overlay (72.53% CAGR, Sharpe 1.24) is the outlier but carries "
                 f"high vol and crypto correlation; consider only if risk preferences allow.")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    universe = sorted(set(LIVE_SIGNAL_UNIVERSE + ["SPY"]))
    prices = fetch_prices(universe)
    print(f"Loaded {len(prices)} trading days from {prices.index[0].date()} to {prices.index[-1].date()}")

    train = _slice(prices, TRAIN_START, TRAIN_END)
    test = _slice(prices, TEST_START)
    print(f"TRAIN: {train.index[0].date()} to {train.index[-1].date()} ({len(train)} bars)")
    print(f"TEST:  {test.index[0].date()} to {test.index[-1].date()} ({len(test)} bars)")
    print()

    # In-sample sensitivity sweep on TRAIN
    train_df = run_sweep(train, "TRAIN")
    train_df.to_csv(OUTPUT_DIR / "walk_forward_train.csv", index=False)

    # Benchmark applications on TEST
    live_test = _run_one(test, **LIVE_PARAMS)
    spy_nav = strat_buy_hold(test, "SPY")
    spy_test = metrics(spy_nav)
    spy_test = {"position_size": None, "max_positions": None, "hold_days": None,
                "spread_threshold": None, **spy_test}

    # Test top-of-train on OOS
    write_report(train_df, test, live_test, spy_test,
                 OUTPUT_DIR / "walk_forward_report.md")

    print()
    print("=== Live params on TEST (out-of-sample) ===")
    print(f"  CAGR {live_test['cagr_pct']}%, Sharpe {live_test['sharpe']}, MaxDD {live_test['max_drawdown_pct']}%")
    print("=== Buy-hold-SPY on TEST ===")
    print(f"  CAGR {spy_test['cagr_pct']}%, Sharpe {spy_test['sharpe']}, MaxDD {spy_test['max_drawdown_pct']}%")
    print()
    print(f"Train CSV: {OUTPUT_DIR / 'walk_forward_train.csv'}")
    print(f"Report:    {OUTPUT_DIR / 'walk_forward_report.md'}")


if __name__ == "__main__":
    main()
