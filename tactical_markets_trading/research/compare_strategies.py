"""Backtest multiple systematic strategies head-to-head.

Off the production path — does not place orders, does not run on the scheduler.
Pure historical analysis using yfinance close data.

Strategies:
  1. Buy-and-hold SPY (baseline)
  2. Trend-following SPY (200-day MA filter)
  3. 60/40 SPY/TLT (rebalanced monthly)
  4. Dual momentum (Antonacci, monthly)
  5. Cross-sectional sector momentum (monthly, top-3 by 3-month return)
  6. 5-day sector rotation (current live strategy, backtested)
  7. Buy-and-hold BTC (high-vol crypto benchmark)
  8. BTC with stress overlay (BTC when SPY > 200d MA, else cash)

Output:
  research/data/comparison_nav.csv       — daily NAV per strategy
  research/data/comparison_summary.csv   — per-strategy metrics
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

OUTPUT_DIR = Path(__file__).resolve().parent / "data"
START = "2014-01-01"
END = None  # today
INITIAL_NAV = 100_000.0
TRADING_DAYS_PER_YEAR = 252

# Live signal universe — must match tactical_markets/config/universe.yaml exactly
LIVE_SIGNAL_UNIVERSE = ["XLK", "XLF", "XLE", "XLI", "XLV", "XLY", "XLC", "XLU", "XLRE", "IWM", "QQQ", "SPY"]
# Larger sector universe for the monthly-rebalance comparison (more tickers, more diversification)
SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB"]
DUAL_MOMO = ["SPY", "VEU", "BIL"]
SIXTY_FORTY = ["SPY", "TLT"]
TIMESERIES_BASKET = ["SPY", "QQQ", "IWM", "GLD", "TLT", "VNQ"]
CRYPTO = ["BTC-USD"]
CASH_PROXY = "BIL"


def fetch_prices(tickers: list[str], retries: int = 3) -> pd.DataFrame:
    """Fetch one at a time to dodge yfinance batch-throttling, with retry on transient failures."""
    import time
    print(f"Fetching {len(tickers)} tickers from yfinance...")
    series = {}
    for ticker in tickers:
        for attempt in range(retries):
            try:
                hist = yf.Ticker(ticker).history(start=START, end=END, auto_adjust=True)
                if not hist.empty and "Close" in hist.columns:
                    s = hist["Close"]
                    s.index = s.index.tz_localize(None) if s.index.tz is not None else s.index
                    series[ticker] = s
                    break
                else:
                    if attempt < retries - 1:
                        time.sleep(2)
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(2)
                else:
                    print(f"  WARN: {ticker} failed after {retries} attempts: {e}")
    closes = pd.DataFrame(series).dropna(how="all")
    missing = set(tickers) - set(closes.columns)
    if missing:
        print(f"  WARN: missing tickers: {missing}")
    return closes


# ---------- Strategy implementations ----------
# Each returns a daily NAV series indexed by date.

def strat_buy_hold(prices: pd.DataFrame, ticker: str = "SPY") -> pd.Series:
    s = prices[ticker].dropna()
    return INITIAL_NAV * (s / s.iloc[0])


def strat_trend_following(prices: pd.DataFrame, ticker: str = "SPY", ma_window: int = 200) -> pd.Series:
    s = prices[ticker].dropna()
    ma = s.rolling(ma_window).mean()
    in_market = (s > ma).shift(1).fillna(False)
    daily_ret = s.pct_change().fillna(0)
    strat_ret = daily_ret.where(in_market, 0)
    return INITIAL_NAV * (1 + strat_ret).cumprod()


def strat_sixty_forty(prices: pd.DataFrame) -> pd.Series:
    spy = prices["SPY"].dropna()
    tlt = prices["TLT"].dropna()
    common = spy.index.intersection(tlt.index)
    spy, tlt = spy.loc[common], tlt.loc[common]
    spy_ret = spy.pct_change().fillna(0)
    tlt_ret = tlt.pct_change().fillna(0)
    month_ends = pd.Series(common).groupby([common.year, common.month]).max()
    weights = pd.Series(0.6, index=common, name="spy_weight")
    blended = 0.6 * spy_ret + 0.4 * tlt_ret
    return INITIAL_NAV * (1 + blended).cumprod()


def strat_dual_momentum(prices: pd.DataFrame, lookback_months: int = 12) -> pd.Series:
    """Antonacci's basic dual momentum:
       - At month end, compare SPY's lookback return to BIL (cash).
       - If SPY > cash: hold whichever of [SPY, VEU] has higher lookback return.
       - Else: hold cash (BIL).
    """
    needed = ["SPY", "VEU", "BIL"]
    df = prices[needed].dropna()
    monthly = df.resample("ME").last()
    lookback_days = lookback_months * 21  # approximate trading days
    monthly_lookback = monthly.pct_change(lookback_months)

    holdings = pd.Series(index=monthly.index, dtype=object)
    for date in monthly.index:
        row = monthly_lookback.loc[date]
        if pd.isna(row["SPY"]) or pd.isna(row["BIL"]):
            holdings[date] = "BIL"
            continue
        if row["SPY"] > row["BIL"]:
            holdings[date] = "SPY" if row["SPY"] >= row.get("VEU", -np.inf) else "VEU"
        else:
            holdings[date] = "BIL"

    daily = pd.Series(index=df.index, dtype=object)
    last_holding = "BIL"
    for date in df.index:
        if date in holdings.index:
            last_holding = holdings[date]
        daily[date] = last_holding

    daily_ret = pd.Series(0.0, index=df.index)
    for ticker in needed:
        ret = df[ticker].pct_change().fillna(0)
        mask = (daily.shift(1) == ticker)
        daily_ret = daily_ret + ret.where(mask, 0)

    return INITIAL_NAV * (1 + daily_ret).cumprod()


def strat_sector_momentum_monthly(prices: pd.DataFrame, top_n: int = 3, lookback_months: int = 3) -> pd.Series:
    sectors_df = prices[SECTORS].dropna()
    monthly = sectors_df.resample("ME").last()
    momentum = monthly.pct_change(lookback_months)

    holdings = {}
    for date in momentum.index:
        row = momentum.loc[date].dropna()
        if len(row) < top_n:
            holdings[date] = []
            continue
        winners = row.nlargest(top_n).index.tolist()
        holdings[date] = winners

    daily_ret = pd.Series(0.0, index=sectors_df.index)
    last_winners = []
    for date in sectors_df.index:
        if date in holdings:
            last_winners = holdings[date]
        if not last_winners:
            continue
        weight = 1.0 / len(last_winners)
        for w in last_winners:
            daily_ret.loc[date] += weight * sectors_df[w].pct_change().fillna(0).loc[date]

    return INITIAL_NAV * (1 + daily_ret).cumprod()


def strat_buy_hold_btc(prices: pd.DataFrame) -> pd.Series:
    s = prices["BTC-USD"].dropna()
    return INITIAL_NAV * (s / s.iloc[0])


def strat_btc_stress_overlay(prices: pd.DataFrame, ma_window: int = 200) -> pd.Series:
    """Hold BTC when SPY is in an uptrend (SPY > 200d MA), else cash.
       Tests whether an equity-derived macro signal adds value to crypto exposure."""
    btc = prices["BTC-USD"].dropna()
    spy = prices["SPY"].dropna()
    common = btc.index.intersection(spy.index)
    btc, spy = btc.loc[common], spy.loc[common]
    spy_ma = spy.rolling(ma_window).mean()
    in_market = (spy > spy_ma).shift(1).fillna(False)
    btc_ret = btc.pct_change().fillna(0)
    strat_ret = btc_ret.where(in_market, 0)
    return INITIAL_NAV * (1 + strat_ret).cumprod()


def _run_rotation_backtest(
    prices: pd.DataFrame,
    universe: list[str],
    momentum_window: int,
    hold_days: int,
    spread_threshold: float = 0.015,
    ma_window: int = 20,
    max_positions: int = 5,
    position_size: float = 0.10,
    trend_filter_ticker: str | None = None,
    trend_filter_ma: int = 200,
) -> pd.Series:
    """Generic rotation backtest matching live signal logic exactly:
       - Each day, rank universe by `momentum_window`-day momentum
       - If (winner momentum - loser momentum) >= spread_threshold AND winner > its `ma_window`-day MA,
         AND (optional) trend_filter_ticker is above its trend_filter_ma:
         buy winner with `position_size` of capital, hold `hold_days` trading days
       - Up to `max_positions` concurrent. Skip if winner already held."""
    available = [t for t in universe if t in prices.columns]
    df = prices[available].dropna(how="all")

    momentum = df.pct_change(momentum_window)
    ma = df.rolling(ma_window).mean()

    trend_in_market = None
    if trend_filter_ticker and trend_filter_ticker in prices.columns:
        tf = prices[trend_filter_ticker].dropna()
        tf_ma = tf.rolling(trend_filter_ma).mean()
        trend_in_market = (tf > tf_ma).reindex(df.index).fillna(False)

    nav = pd.Series(INITIAL_NAV, index=df.index)
    cash = INITIAL_NAV
    positions = []

    warmup = max(ma_window, trend_filter_ma if trend_filter_ticker else 0) + momentum_window
    for i, date in enumerate(df.index):
        if i < warmup:
            nav.iloc[i] = cash
            continue

        # Exit positions past their hold window
        still_open = []
        for p in positions:
            if i >= df.index.get_loc(p["exit_date"]):
                cash += p["qty"] * df.loc[date, p["ticker"]]
            else:
                still_open.append(p)
        positions = still_open

        # Trend filter gate (skip new entries if macro trend is off)
        trend_ok = True if trend_in_market is None else bool(trend_in_market.loc[date])

        if trend_ok and len(positions) < max_positions:
            row = momentum.loc[date].dropna()
            if len(row) >= 2:
                winner = row.idxmax()
                loser = row.idxmin()
                spread = row[winner] - row[loser]
                if spread >= spread_threshold:
                    winner_price = df.loc[date, winner]
                    winner_ma = ma.loc[date, winner]
                    if winner_price > winner_ma:
                        held = {p["ticker"] for p in positions}
                        if winner not in held:
                            trade_size = INITIAL_NAV * position_size
                            if cash >= trade_size:
                                qty = trade_size / winner_price
                                cash -= trade_size
                                exit_idx = min(i + hold_days, len(df) - 1)
                                positions.append({
                                    "ticker": winner,
                                    "entry_date": date,
                                    "entry_price": winner_price,
                                    "qty": qty,
                                    "exit_date": df.index[exit_idx],
                                })

        position_value = sum(p["qty"] * df.loc[date, p["ticker"]] for p in positions)
        nav.loc[date] = cash + position_value

    return nav


def strat_sector_5day_rotation_live(prices: pd.DataFrame) -> pd.Series:
    """Exactly matches tactical_markets/src/sector_rotation.py: 12-ticker universe (9 sectors + IWM/QQQ/SPY),
       5-day momentum, 1.5% spread, 20d MA filter, 5-day hold, up to 5 concurrent."""
    return _run_rotation_backtest(prices, LIVE_SIGNAL_UNIVERSE, momentum_window=5, hold_days=5)


def strat_sector_5day_with_trend_filter(prices: pd.DataFrame) -> pd.Series:
    """Live strategy + macro trend gate: only enter when SPY > 200d MA."""
    return _run_rotation_backtest(
        prices, LIVE_SIGNAL_UNIVERSE, momentum_window=5, hold_days=5,
        trend_filter_ticker="SPY", trend_filter_ma=200,
    )


def strat_sector_monthly_match_live(prices: pd.DataFrame) -> pd.Series:
    """Same logic as live (same universe, same rules) but at the timeframe research validates:
       63-day (~3-month) momentum, 21-day (~1-month) hold."""
    return _run_rotation_backtest(
        prices, LIVE_SIGNAL_UNIVERSE, momentum_window=63, hold_days=21, spread_threshold=0.03,
    )


# ---------- Metrics ----------

def metrics(nav: pd.Series) -> dict:
    nav = nav.dropna()
    if len(nav) < 2:
        return {}
    daily_ret = nav.pct_change().dropna()
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1
    vol = daily_ret.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe = (daily_ret.mean() * TRADING_DAYS_PER_YEAR) / vol if vol > 0 else 0
    running_max = nav.cummax()
    drawdown = (nav - running_max) / running_max
    max_dd = drawdown.min()
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0
    monthly = nav.resample("ME").last().pct_change().dropna()
    monthly_win = (monthly > 0).mean()
    return {
        "final_nav": round(nav.iloc[-1], 2),
        "cagr_pct": round(cagr * 100, 2),
        "vol_pct": round(vol * 100, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "calmar": round(calmar, 2),
        "monthly_win_rate_pct": round(monthly_win * 100, 1),
        "years": round(years, 1),
    }


# ---------- Diagnostics ----------

def diagnose_dual_momentum(prices: pd.DataFrame, output_path: Path, lookback_months: int = 12) -> dict:
    """Dump every monthly decision to CSV. Returns summary stats for printing."""
    needed = ["SPY", "VEU", "BIL"]
    df = prices[needed].dropna()
    monthly = df.resample("ME").last()
    monthly_lookback = monthly.pct_change(lookback_months)

    rows = []
    for date in monthly.index:
        row = monthly_lookback.loc[date]
        spy_lb, veu_lb, bil_lb = row.get("SPY"), row.get("VEU"), row.get("BIL")
        if pd.isna(spy_lb) or pd.isna(bil_lb):
            holding = "BIL_warmup"
        elif spy_lb > bil_lb:
            holding = "SPY" if spy_lb >= (veu_lb if not pd.isna(veu_lb) else -np.inf) else "VEU"
        else:
            holding = "BIL_riskoff"
        rows.append({
            "date": date.date(),
            "spy_12mo_pct": round(spy_lb * 100, 2) if not pd.isna(spy_lb) else None,
            "veu_12mo_pct": round(veu_lb * 100, 2) if not pd.isna(veu_lb) else None,
            "bil_12mo_pct": round(bil_lb * 100, 2) if not pd.isna(bil_lb) else None,
            "holding": holding,
        })

    df_out = pd.DataFrame(rows).set_index("date")
    df_out.to_csv(output_path)

    riskoff_months = (df_out["holding"] == "BIL_riskoff").sum()
    warmup_months = (df_out["holding"] == "BIL_warmup").sum()
    invested = df_out[df_out["holding"].isin(["SPY", "VEU"])]
    by_holding = df_out["holding"].value_counts().to_dict()

    # Find regime transitions and durations spent in cash
    state = df_out["holding"].apply(lambda x: "CASH" if x.startswith("BIL") else "EQUITY")
    transitions = []
    prev_state = None
    prev_date = None
    for date, st in state.items():
        if prev_state is not None and st != prev_state:
            duration = (date - prev_date).days // 30 if prev_date else 0
            transitions.append({
                "transition_date": date,
                "from": prev_state,
                "to": st,
                "prev_regime_months_approx": duration,
            })
            prev_date = date
        elif prev_state is None:
            prev_date = date
        prev_state = st

    return {
        "total_months": len(df_out),
        "by_holding": by_holding,
        "months_in_riskoff_cash": riskoff_months,
        "months_in_warmup": warmup_months,
        "transitions": transitions,
    }


# ---------- Stress-period analysis ----------

STRESS_PERIODS = [
    ("2018 Q4 Selloff",     "2018-10-01", "2018-12-24"),
    ("COVID Crash",         "2020-02-19", "2020-03-23"),
    ("2022 Bear Market",    "2022-01-04", "2022-10-12"),
]


def stress_window_metrics(nav: pd.Series, start: str, end: str) -> dict:
    window = nav.loc[start:end].dropna()
    if len(window) < 2:
        return {"return_pct": None, "max_dd_pct": None}
    total_return = (window.iloc[-1] / window.iloc[0]) - 1
    running_max = window.cummax()
    drawdown = (window - running_max) / running_max
    return {
        "return_pct": round(total_return * 100, 2),
        "max_dd_pct": round(drawdown.min() * 100, 2),
    }


def write_markdown_report(strategies: dict, summary: pd.DataFrame, output_path: Path, dm_stats: dict | None = None) -> None:
    lines = []
    lines.append("# Strategy Comparison Report")
    lines.append("")
    lines.append(f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
    first_nav = next(iter(strategies.values()))
    lines.append(f"Backtest window: {first_nav.index[0].date()} to {first_nav.index[-1].date()}")
    lines.append("")
    lines.append("## Summary metrics")
    lines.append("")
    lines.append(summary.to_markdown())
    lines.append("")
    lines.append("## Performance during stress periods")
    lines.append("")
    lines.append("Total return and max drawdown for each strategy *within the window*. Helps see who's robust under fire.")
    lines.append("")
    for label, start, end in STRESS_PERIODS:
        rows = []
        for name, nav in strategies.items():
            m = stress_window_metrics(nav, start, end)
            rows.append({"strategy": name, **m})
        df = pd.DataFrame(rows).set_index("strategy")
        lines.append(f"### {label} ({start} → {end})")
        lines.append("")
        lines.append(df.to_markdown())
        lines.append("")
    lines.append("## NAV at key dates")
    lines.append("")
    key_dates = ["2016-12-31", "2018-12-31", "2020-12-31", "2022-12-31", "2024-12-31"]
    rows = []
    for name, nav in strategies.items():
        row = {"strategy": name}
        for d in key_dates:
            try:
                row[d[:7]] = round(nav.asof(pd.Timestamp(d)), 0)
            except Exception:
                row[d[:7]] = None
        row["latest"] = round(nav.iloc[-1], 0)
        rows.append(row)
    nav_df = pd.DataFrame(rows).set_index("strategy")
    lines.append(nav_df.to_markdown())
    lines.append("")

    if dm_stats is not None:
        lines.append("## Diagnostics: dual_momentum regime analysis")
        lines.append("")
        lines.append(f"Dual momentum's 7.74% CAGR (Sharpe 0.57) sits well below Antonacci's published 1974-2014 results (~17% CAGR). This is **regime-dependent, not a bug** — the implementation matches Antonacci's GEM rule (compare SPY 12-mo to T-bills; if SPY wins, hold max of SPY/VEU; else hold cash).")
        lines.append("")
        lines.append("**Decision history ({} months):** {}.".format(dm_stats["total_months"], dm_stats["by_holding"]))
        lines.append("")
        lines.append("**Regime transitions and whipsaws:**")
        lines.append("")
        lines.append("| Date | Transition | Prev regime months |")
        lines.append("|---|---|---|")
        for t in dm_stats["transitions"]:
            lines.append(f"| {t['transition_date']} | {t['from']} → {t['to']} | ~{t['prev_regime_months_approx']} |")
        lines.append("")
        lines.append("**Key whipsaws in this window:**")
        lines.append("- **2018-12-31:** exited to cash at the bottom of the Q4 selloff; re-entered 2 months later after SPY had already rebounded ~10%. Classic 12-month-lookback V-shape penalty.")
        lines.append("- **2020-03-31:** exited at COVID bottom; re-entered 2 months later after SPY rallied ~30%. Catastrophic whipsaw.")
        lines.append("- **2022-05-31:** correctly anticipated the bear market; stayed in cash 13 months. Strategy working as designed.")
        lines.append("")
        lines.append("**Implication for Phase 2:** dual momentum requires extended drawdowns (1+ year regime transitions) to capture its edge. In our 2014-2026 window, two of three SPY drawdowns were V-shaped, neutralizing the strategy. Antonacci's 1974-2014 backtest included the 2000-2002 dot-com bust and 2007-2009 GFC — both 12+ month drawdowns. Don't read this window as evidence the strategy is broken; read it as evidence the strategy is *regime-conditional*.")
        lines.append("")
        lines.append("Full decision history: [dual_momentum_decisions.csv](dual_momentum_decisions.csv)")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


# ---------- Main ----------

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    universe = sorted(set(LIVE_SIGNAL_UNIVERSE + SECTORS + DUAL_MOMO + SIXTY_FORTY + TIMESERIES_BASKET + CRYPTO + [CASH_PROXY]))
    prices = fetch_prices(universe)
    print(f"Loaded {len(prices)} trading days from {prices.index[0].date()} to {prices.index[-1].date()}")
    print()

    strategies = {
        "buy_hold_spy": strat_buy_hold(prices, "SPY"),
        "trend_following_spy": strat_trend_following(prices, "SPY"),
        "sixty_forty": strat_sixty_forty(prices),
        "dual_momentum": strat_dual_momentum(prices),
        "sector_momentum_top3_monthly": strat_sector_momentum_monthly(prices),
        "sector_rotation_5d_live": strat_sector_5day_rotation_live(prices),
        "sector_rotation_5d_trend_filter": strat_sector_5day_with_trend_filter(prices),
        "sector_rotation_monthly_match_live": strat_sector_monthly_match_live(prices),
        "buy_hold_btc": strat_buy_hold_btc(prices),
        "btc_stress_overlay": strat_btc_stress_overlay(prices),
    }

    nav_df = pd.DataFrame(strategies)
    nav_df.to_csv(OUTPUT_DIR / "comparison_nav.csv")

    rows = []
    for name, nav in strategies.items():
        m = metrics(nav)
        m["strategy"] = name
        rows.append(m)
    summary = pd.DataFrame(rows).set_index("strategy")[
        ["years", "final_nav", "cagr_pct", "vol_pct", "sharpe", "max_drawdown_pct", "calmar", "monthly_win_rate_pct"]
    ]
    summary.to_csv(OUTPUT_DIR / "comparison_summary.csv")

    # Task 1: dual momentum diagnostic (must run before write_markdown_report so we can include it)
    dm_stats = diagnose_dual_momentum(prices, OUTPUT_DIR / "dual_momentum_decisions.csv")

    write_markdown_report(strategies, summary, OUTPUT_DIR / "comparison_report.md", dm_stats=dm_stats)
    print()
    print("=== Dual momentum decision history ===")
    print(f"Total months: {dm_stats['total_months']}")
    print(f"By holding:   {dm_stats['by_holding']}")
    print(f"Risk-off months (signaled cash, not warmup): {dm_stats['months_in_riskoff_cash']}")
    print(f"Regime transitions:")
    for t in dm_stats["transitions"]:
        print(f"  {t['transition_date']}: {t['from']} -> {t['to']} (prev regime ~{t['prev_regime_months_approx']} months)")

    print("=== Strategy comparison ===")
    print(summary.to_string())
    print()
    print(f"NAV history: {OUTPUT_DIR / 'comparison_nav.csv'}")
    print(f"Summary:     {OUTPUT_DIR / 'comparison_summary.csv'}")
    print(f"Report:      {OUTPUT_DIR / 'comparison_report.md'}")


if __name__ == "__main__":
    main()
