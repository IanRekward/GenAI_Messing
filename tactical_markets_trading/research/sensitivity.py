"""Parameter sensitivity grid for the live sector rotation strategy.

Answers: is the underperformance fixable by tuning, or structural?

288 backtests across position_size × max_positions × hold_days × spread_threshold.
Outputs research/data/sensitivity.csv and research/data/sensitivity_summary.md.
"""

import sys
import time
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from compare_strategies import (
    LIVE_SIGNAL_UNIVERSE,
    OUTPUT_DIR,
    _run_rotation_backtest,
    fetch_prices,
    metrics,
)

POSITION_SIZES = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
MAX_POSITIONS = [1, 3, 5, 10]
HOLD_DAYS = [3, 5, 10, 21]
SPREAD_THRESHOLDS = [0.005, 0.015, 0.030]


def run_grid(prices: pd.DataFrame) -> pd.DataFrame:
    rows = []
    combos = list(product(POSITION_SIZES, MAX_POSITIONS, HOLD_DAYS, SPREAD_THRESHOLDS))
    total = len(combos)
    print(f"Running {total} backtests...")
    start_time = time.time()

    for i, (pos_size, max_pos, hold, spread) in enumerate(combos, 1):
        nav = _run_rotation_backtest(
            prices,
            LIVE_SIGNAL_UNIVERSE,
            momentum_window=5,
            hold_days=hold,
            spread_threshold=spread,
            max_positions=max_pos,
            position_size=pos_size,
        )
        m = metrics(nav)
        rows.append({
            "position_size": pos_size,
            "max_positions": max_pos,
            "hold_days": hold,
            "spread_threshold": spread,
            **m,
        })
        if i % 20 == 0 or i == total:
            elapsed = time.time() - start_time
            est_total = elapsed * total / i
            print(f"  {i}/{total} done — elapsed {elapsed:.0f}s, est total {est_total:.0f}s")

    return pd.DataFrame(rows)


def write_summary(df: pd.DataFrame, output_path: Path) -> None:
    lines = [
        "# Sensitivity analysis — live sector rotation parameters",
        "",
        f"Backtest window: 2014-2026 ({df.iloc[0]['years']:.1f} years)",
        f"Total parameter combinations: {len(df)}",
        "",
        "## Best 10 by Sharpe ratio",
        "",
        df.nlargest(10, "sharpe").to_markdown(index=False),
        "",
        "## Best 10 by CAGR",
        "",
        df.nlargest(10, "cagr_pct").to_markdown(index=False),
        "",
        "## Worst 10 by Sharpe ratio",
        "",
        df.nsmallest(10, "sharpe").to_markdown(index=False),
        "",
        "## Current live parameters performance",
        "",
        "Live: position_size=0.10, max_positions=5, hold_days=5, spread_threshold=0.015",
        "",
    ]
    live_row = df[
        (df.position_size == 0.10)
        & (df.max_positions == 5)
        & (df.hold_days == 5)
        & (df.spread_threshold == 0.015)
    ]
    if not live_row.empty:
        lines.append(live_row.to_markdown(index=False))
        lines.append("")

    # Marginal effect: hold position_size and max_positions at live values, vary hold_days
    lines.append("## Marginal effect of hold_days (at live position_size=0.10, max_positions=5)")
    lines.append("")
    sub = df[(df.position_size == 0.10) & (df.max_positions == 5) & (df.spread_threshold == 0.015)]
    lines.append(sub.sort_values("hold_days").to_markdown(index=False))
    lines.append("")

    lines.append("## Marginal effect of position_size (at live max_positions=5, hold_days=5)")
    lines.append("")
    sub = df[(df.max_positions == 5) & (df.hold_days == 5) & (df.spread_threshold == 0.015)]
    lines.append(sub.sort_values("position_size").to_markdown(index=False))
    lines.append("")

    lines.append("## Decision criterion (per plan)")
    lines.append("")
    best_cagr = df["cagr_pct"].max()
    if best_cagr >= 5:
        lines.append(f"**Tunable.** Best parameter combo achieves {best_cagr:.2f}% CAGR. Phase 2 should explore tuned variants of this signal.")
    elif best_cagr >= 3:
        lines.append(f"**Marginal.** Best combo at {best_cagr:.2f}% CAGR — meaningful improvement over the live 1.69% but still well below buy-and-hold SPY (13.86%). Mixed signal.")
    else:
        lines.append(f"**Structural.** Best combo at only {best_cagr:.2f}% CAGR. Underperformance is not fixable by tuning. Phase 2 should consider a different methodology entirely.")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    universe = sorted(set(LIVE_SIGNAL_UNIVERSE))
    prices = fetch_prices(universe)
    print(f"Loaded {len(prices)} trading days")
    df = run_grid(prices)
    csv_path = OUTPUT_DIR / "sensitivity.csv"
    summary_path = OUTPUT_DIR / "sensitivity_summary.md"
    df.to_csv(csv_path, index=False)
    write_summary(df, summary_path)
    print()
    print("=== Top 5 by Sharpe ===")
    print(df.nlargest(5, "sharpe").to_string(index=False))
    print()
    print("=== Top 5 by CAGR ===")
    print(df.nlargest(5, "cagr_pct").to_string(index=False))
    print()
    print(f"CSV:     {csv_path}")
    print(f"Summary: {summary_path}")
