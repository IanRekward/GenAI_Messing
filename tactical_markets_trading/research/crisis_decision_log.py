"""Day-by-day decision log for the top strategies during historical crisis windows.

Lets you see exactly what each strategy would have held through dot-com, GFC, COVID,
and the 2022 bear — and where the hedges (trailing stop, VIX gate) kick in vs miss.

Outputs research/data/crisis_decisions_<crisis>.csv for each crisis window.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from multi_strategy_extended import (
    ALL_TICKERS,
    INITIAL_NAV,
    add_synthetic_cash,
    add_synthetic_leveraged_to_prices,
    fetch_prices,
)

OUTPUT_DIR = Path(__file__).resolve().parent / "data"

CRISIS_WINDOWS = [
    ("dotcom", "2000-01-01", "2002-12-31"),
    ("gfc", "2007-10-01", "2009-06-30"),
    ("covid", "2020-02-15", "2020-05-15"),
    ("bear_2022", "2022-01-01", "2022-12-31"),
]


def _compute_decisions(prices: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """For each day in [start, end], record what the key strategies would have held."""
    spy = prices["SPY"].dropna()
    ma200 = spy.rolling(200).mean()
    vix = prices["^VIX"].dropna() if "^VIX" in prices.columns else None
    synth_3x_qqq = prices.get("SYNTH_3X_QQQ")
    bil_ext = prices.get("BIL_EXTENDED")

    common = spy.index.intersection(ma200.dropna().index)
    if synth_3x_qqq is not None:
        common = common.intersection(synth_3x_qqq.index)
    if bil_ext is not None:
        common = common.intersection(bil_ext.index)
    if vix is not None:
        common = common.intersection(vix.index)
    window = common[(common >= pd.Timestamp(start)) & (common <= pd.Timestamp(end))]
    if len(window) == 0:
        return pd.DataFrame()

    # Trend signal: SPY > 200d MA (using yesterday's value to avoid lookahead)
    trend_on = (spy > ma200).shift(1).fillna(False).astype(bool)
    vix_low = (vix < 25).shift(1).fillna(False).astype(bool) if vix is not None else None

    # Run trailing-stop logic specifically for the full window so we have the state going in
    pos = False
    pos_peak = 0.0
    stopped_out = False
    decisions_ts = []
    decisions_ts_vix = []
    decisions_tts = []
    spy_pct_from_high = []

    spy_rolling_high = spy.rolling(252, min_periods=1).max()

    for i, date in enumerate(common):
        if date < pd.Timestamp(start):
            # Update trailing-stop state but don't record yet
            price = synth_3x_qqq.loc[date] if synth_3x_qqq is not None else 0
            if pos:
                if price > pos_peak:
                    pos_peak = price
                if price <= pos_peak * 0.90:
                    pos = False
                    stopped_out = True
                elif not trend_on.loc[date]:
                    pos = False
            else:
                if trend_on.loc[date] and not stopped_out:
                    pos = True
                    pos_peak = price
                elif stopped_out and not trend_on.loc[date]:
                    stopped_out = False
            continue
        if date > pd.Timestamp(end):
            break
        # In window — record
        price = synth_3x_qqq.loc[date] if synth_3x_qqq is not None else 0
        if pos:
            if price > pos_peak:
                pos_peak = price
            if price <= pos_peak * 0.90:
                pos = False
                stopped_out = True
            elif not trend_on.loc[date]:
                pos = False
        else:
            if trend_on.loc[date] and not stopped_out:
                pos = True
                pos_peak = price
            elif stopped_out and not trend_on.loc[date]:
                stopped_out = False

        decisions_ts.append("SYNTH_3X_QQQ" if trend_on.loc[date] else "BIL_EXTENDED")
        if vix_low is not None:
            decisions_ts_vix.append("SYNTH_3X_QQQ" if (trend_on.loc[date] and vix_low.loc[date]) else "BIL_EXTENDED")
        decisions_tts.append("SYNTH_3X_QQQ" if pos else ("BIL_EXTENDED (stopped)" if stopped_out else "BIL_EXTENDED"))
        spy_pct_from_high.append(round((spy.loc[date] / spy_rolling_high.loc[date] - 1) * 100, 2))

    df = pd.DataFrame({
        "date": window.date,
        "spy_close": spy.loc[window].round(2).values,
        "spy_200d_ma": ma200.loc[window].round(2).values,
        "spy_pct_from_252d_high": spy_pct_from_high,
        "vix": vix.loc[window].round(2).values if vix is not None else None,
        "synth_3x_qqq_nav_proxy": synth_3x_qqq.loc[window].round(2).values if synth_3x_qqq is not None else None,
        "trend_only_position": decisions_ts,
        "trend_plus_vix_gate_position": decisions_ts_vix if vix is not None else None,
        "trend_plus_trailing_stop_position": decisions_tts,
    })
    return df


def _summarize(df: pd.DataFrame, name: str) -> dict:
    """Headline numbers for a crisis window: starting/ending SPY, % of days each strategy was in market."""
    if df.empty:
        return {"name": name, "rows": 0}
    return {
        "name": name,
        "rows": len(df),
        "spy_start": df.iloc[0]["spy_close"],
        "spy_end": df.iloc[-1]["spy_close"],
        "spy_return_pct": round((df.iloc[-1]["spy_close"] / df.iloc[0]["spy_close"] - 1) * 100, 2),
        "worst_spy_drawdown_pct": df["spy_pct_from_252d_high"].min(),
        "synth3x_start": df.iloc[0]["synth_3x_qqq_nav_proxy"],
        "synth3x_end": df.iloc[-1]["synth_3x_qqq_nav_proxy"],
        "synth3x_return_pct": round((df.iloc[-1]["synth_3x_qqq_nav_proxy"] / df.iloc[0]["synth_3x_qqq_nav_proxy"] - 1) * 100, 2),
        "trend_only_pct_in_3x_qqq": round((df["trend_only_position"] == "SYNTH_3X_QQQ").mean() * 100, 1),
        "trend_plus_trailing_stop_pct_in_3x_qqq": round((df["trend_plus_trailing_stop_position"] == "SYNTH_3X_QQQ").mean() * 100, 1),
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = fetch_prices(ALL_TICKERS)
    prices = add_synthetic_leveraged_to_prices(prices)
    prices = add_synthetic_cash(prices)

    print("\n=== CRISIS WINDOW DECISION LOG ===\n")
    summaries = []
    for name, start, end in CRISIS_WINDOWS:
        df = _compute_decisions(prices, start, end)
        if df.empty:
            print(f"{name}: no data in window")
            continue
        path = OUTPUT_DIR / f"crisis_decisions_{name}.csv"
        df.to_csv(path, index=False)
        s = _summarize(df, name)
        summaries.append(s)
        print(f"\n--- {name} ({start} to {end}, {s['rows']} days) ---")
        print(f"  SPY: ${s['spy_start']} -> ${s['spy_end']} ({s['spy_return_pct']:+.2f}%); worst pullback from 252d high: {s['worst_spy_drawdown_pct']}%")
        if s.get("synth3x_start"):
            print(f"  3xQQQ (synthetic): ${s['synth3x_start']} -> ${s['synth3x_end']} ({s['synth3x_return_pct']:+.2f}%)")
        print(f"  trend_only:           in 3xQQQ {s['trend_only_pct_in_3x_qqq']}% of days")
        print(f"  trend+trailing_stop:  in 3xQQQ {s['trend_plus_trailing_stop_pct_in_3x_qqq']}% of days")
        print(f"  Saved: {path}")

    print("\n\n=== SUMMARY ===\n")
    print(pd.DataFrame(summaries).to_string(index=False))


if __name__ == "__main__":
    main()
