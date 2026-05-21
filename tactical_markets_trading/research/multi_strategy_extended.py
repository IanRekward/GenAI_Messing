"""Extended-window walk-forward across every strategy in compare_strategies.py,
plus regime-conditional breakdown and a simple multi-strategy ensemble simulation.

Why this exists: backtest data accumulates as fast as Python runs; live data
accumulates 1-2 trades/day. To make a defensible strategy decision faster than
3 months of live trading, we need (a) more historical data, (b) every alternative
strategy walked through the same data, and (c) regime-conditional breakdowns.

Window decisions:
  - Sector rotation universe shrinks to 10 tickers (drop XLC + XLRE — those launched
    2018 and 2015 respectively). With the 9 old SPDRs + IWM/QQQ/SPY/SPY we get
    1999-2026 = 27 years.
  - SPY-only strategies use 1993-2026 = 33 years.
  - 60/40 limited by TLT to 2002+; dual_momentum limited by VEU/BIL to 2007+.

Outputs:
  - research/data/extended_summary.csv — every strategy, every regime split, full + sub-window metrics
  - research/data/extended_report.md — narrative + verdict per strategy + ensemble
  - research/data/extended_decisions.csv — day-by-day decision log (top strategies only, to keep size reasonable)
"""
import sys
import time
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd
import yfinance as yf

# Universe & date defaults
SECTOR_ROTATION_UNIVERSE_EXT = [
    "XLK", "XLF", "XLE", "XLI", "XLV", "XLY", "XLU", "XLB", "XLP",  # 9 old SPDRs
    "IWM", "QQQ", "SPY",
]
DUAL_MOMO_UNIVERSE = ["SPY", "VEU", "BIL"]
SIXTY_FORTY_UNIVERSE = ["SPY", "TLT"]
# Leveraged + inverse ETFs added 2026-05-21 per user request to test strategies
# the no-shorts rule has been blocking. Inverse ETFs (SH/SDS) get used as the
# "short proxy" — max loss = 100% of position, not infinite, so they don't violate
# the spirit of the no-shorts rule. Leveraged longs (TQQQ/UPRO) test the well-known
# "trend-following with leverage" pattern that's been the most-defensible retail
# alpha source historically.
LEVERAGED_TICKERS = ["SH", "SDS", "SSO", "QLD", "TQQQ", "SQQQ", "UPRO", "SPXU",
                     "UVXY", "SVXY", "TMF", "GLD", "UGL"]
ALL_TICKERS = sorted(set(SECTOR_ROTATION_UNIVERSE_EXT + DUAL_MOMO_UNIVERSE
                         + SIXTY_FORTY_UNIVERSE + LEVERAGED_TICKERS + ["BIL", "^VIX"]))

EXTENDED_START = "1999-01-01"
INITIAL_NAV = 100_000.0
TRADING_DAYS_PER_YEAR = 252

OUTPUT_DIR = Path(__file__).resolve().parent / "data"


# ---------- Synthetic leveraged series (pre-ETF-launch history) ----------

def synthesize_leveraged(underlying: pd.Series, multiple: float,
                          expense_ratio_annual: float = 0.0095) -> pd.Series:
    """Build a synthetic leveraged-ETF series by compounding (multiple × daily return)
    minus the daily share of the annual expense ratio. Doesn't model financing costs
    on the swap leg (those are roughly priced into expense ratio for major funds).

    Caveat: real leveraged ETFs have circuit-breaker behavior on extreme single-day
    moves (e.g., a -34% QQQ day would wipe out a 3× ETF entirely; in practice ProShares
    would halt or reset). This synthetic doesn't model that — but no -34% single-day
    move has happened in QQQ history, so it's a moot point for QQQ. For SPY pre-2010,
    the largest single day was -9% (1987 Black Monday; we don't extend that far).
    """
    daily_ret = underlying.pct_change().fillna(0)
    daily_decay = expense_ratio_annual / 252
    lev_daily_ret = multiple * daily_ret - daily_decay
    return INITIAL_NAV * (1 + lev_daily_ret).cumprod()


def add_synthetic_cash(prices: pd.DataFrame, annual_rate: float = 0.025) -> pd.DataFrame:
    """Add BIL_EXTENDED that uses real BIL where available and a synthetic constant-yield
    series (default 2.5% annual ~ historical short-rate average) for pre-2007 dates.
    Without this, every strategy that uses BIL as the out-of-market alternative gets
    truncated to BIL's 2007-05-30 inception, defeating the whole point of synthetic
    leveraged ETF history."""
    prices = prices.copy()
    spy = prices["SPY"].dropna()
    daily_rate = annual_rate / 252
    if "BIL" not in prices.columns:
        # No BIL anywhere — full synthetic
        nav = pd.Series(100.0, index=spy.index)
        for i in range(1, len(nav)):
            nav.iloc[i] = nav.iloc[i-1] * (1 + daily_rate)
        prices["BIL_EXTENDED"] = nav
        return prices
    bil = prices["BIL"].dropna()
    bil_start = bil.index[0]
    pre_dates = spy.index[spy.index < bil_start]
    if len(pre_dates) == 0:
        prices["BIL_EXTENDED"] = bil
        return prices
    # Build pre-BIL synthetic that ends at bil.iloc[0]
    pre_nav = pd.Series(0.0, index=pre_dates)
    pre_nav.iloc[-1] = bil.iloc[0]
    for i in range(len(pre_nav) - 2, -1, -1):
        pre_nav.iloc[i] = pre_nav.iloc[i+1] / (1 + daily_rate)
    extended = pd.concat([pre_nav, bil])
    extended = extended[~extended.index.duplicated(keep="last")]
    prices["BIL_EXTENDED"] = extended
    return prices


def add_synthetic_leveraged_to_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """Add SYNTH_3X_QQQ, SYNTH_2X_QQQ, SYNTH_3X_SPY, SYNTH_2X_SPY columns covering
    the FULL underlying history. When the actual ETF data is available, prefer it;
    when not, the synthetic is the only available estimate.
    """
    prices = prices.copy()
    if "QQQ" in prices.columns:
        prices["SYNTH_3X_QQQ"] = synthesize_leveraged(prices["QQQ"].dropna(), 3.0, 0.0095)
        prices["SYNTH_2X_QQQ"] = synthesize_leveraged(prices["QQQ"].dropna(), 2.0, 0.0091)
    if "SPY" in prices.columns:
        prices["SYNTH_3X_SPY"] = synthesize_leveraged(prices["SPY"].dropna(), 3.0, 0.0091)
        prices["SYNTH_2X_SPY"] = synthesize_leveraged(prices["SPY"].dropna(), 2.0, 0.0089)
        prices["SYNTH_INV_SPY"] = synthesize_leveraged(prices["SPY"].dropna(), -1.0, 0.0089)  # SH analog
    return prices


# ---------- Data ----------

def fetch_prices(tickers: list[str], retries: int = 3) -> pd.DataFrame:
    """Fetch max-history for each ticker individually. Returns flat-columns DataFrame."""
    print(f"Fetching {len(tickers)} tickers (max history)...")
    series = {}
    for t in tickers:
        for attempt in range(retries):
            try:
                hist = yf.Ticker(t).history(period="max", auto_adjust=True)
                if not hist.empty and "Close" in hist.columns:
                    s = hist["Close"]
                    s.index = s.index.tz_localize(None) if s.index.tz is not None else s.index
                    series[t] = s
                    break
                if attempt < retries - 1:
                    time.sleep(2)
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(2)
                else:
                    print(f"  WARN: {t} failed: {e}")
    closes = pd.DataFrame(series).dropna(how="all")
    print(f"  Loaded {len(closes)} bars, {closes.index[0].date()} to {closes.index[-1].date()}")
    return closes


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


# ---------- Strategies ----------

def strat_buy_hold(prices: pd.DataFrame, ticker: str = "SPY") -> pd.Series:
    s = prices[ticker].dropna()
    return INITIAL_NAV * (s / s.iloc[0])


def strat_trend_following(prices: pd.DataFrame, ticker: str = "SPY", ma_window: int = 200) -> pd.Series:
    s = prices[ticker].dropna()
    ma = s.rolling(ma_window).mean()
    in_market = (s > ma).shift(1).fillna(False).astype(bool)
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
    blended = 0.6 * spy_ret + 0.4 * tlt_ret
    return INITIAL_NAV * (1 + blended).cumprod()


def strat_dual_momentum(prices: pd.DataFrame, lookback_months: int = 12) -> pd.Series:
    needed = DUAL_MOMO_UNIVERSE
    if not all(t in prices.columns for t in needed):
        return pd.Series(dtype=float)
    df = prices[needed].dropna()
    monthly = df.resample("ME").last()
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


def strat_sector_momentum_monthly(prices: pd.DataFrame, top_n: int = 3, lookback_months: int = 3,
                                   sectors: list[str] | None = None) -> pd.Series:
    if sectors is None:
        sectors = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB"]
    available = [s for s in sectors if s in prices.columns]
    sectors_df = prices[available].dropna()
    monthly = sectors_df.resample("ME").last()
    momentum = monthly.pct_change(lookback_months)
    holdings = {}
    for date in momentum.index:
        row = momentum.loc[date].dropna()
        if len(row) < top_n:
            holdings[date] = []
            continue
        holdings[date] = row.nlargest(top_n).index.tolist()
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


def strat_vix_overlay_spy(prices: pd.DataFrame, threshold: float = 25) -> pd.Series:
    spy = prices["SPY"].dropna()
    if "^VIX" not in prices.columns or "BIL" not in prices.columns:
        return pd.Series(dtype=float)
    vix = prices["^VIX"].dropna()
    bil = prices["BIL"].dropna()
    common = spy.index.intersection(vix.index).intersection(bil.index)
    spy, vix, bil = spy.loc[common], vix.loc[common], bil.loc[common]
    in_spy = (vix < threshold).shift(1).fillna(False).astype(bool)
    spy_ret = spy.pct_change().fillna(0)
    bil_ret = bil.pct_change().fillna(0)
    daily_ret = spy_ret.where(in_spy, bil_ret)
    return INITIAL_NAV * (1 + daily_ret).cumprod()


def _run_rotation_backtest(prices: pd.DataFrame, universe: list[str], momentum_window: int,
                            hold_days: int, spread_threshold: float = 0.015, ma_window: int = 20,
                            max_positions: int = 5, position_size: float = 0.10) -> pd.Series:
    """Generic sector rotation backtest. Casts numeric args to int as needed."""
    momentum_window = int(momentum_window)
    hold_days = int(hold_days)
    max_positions = int(max_positions)
    available = [t for t in universe if t in prices.columns]
    df = prices[available].dropna(how="all")
    momentum = df.pct_change(momentum_window)
    ma = df.rolling(ma_window).mean()
    nav = pd.Series(INITIAL_NAV, index=df.index)
    cash = INITIAL_NAV
    positions = []
    warmup = max(ma_window, momentum_window)
    for i, date in enumerate(df.index):
        if i < warmup:
            nav.iloc[i] = cash
            continue
        # Exit
        still_open = []
        for p in positions:
            if i >= df.index.get_loc(p["exit_date"]):
                cash += p["qty"] * df.loc[date, p["ticker"]]
            else:
                still_open.append(p)
        positions = still_open
        # Entry
        if len(positions) < max_positions:
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
                                    "qty": qty,
                                    "exit_date": df.index[exit_idx],
                                })
        position_value = sum(p["qty"] * df.loc[date, p["ticker"]] for p in positions)
        nav.loc[date] = cash + position_value
    return nav


def strat_sector_rotation_5d_live(prices: pd.DataFrame, universe: list[str] | None = None) -> pd.Series:
    """The live strategy (5d momentum, 1.5% spread, 5d hold, top-5, 10% size)."""
    if universe is None:
        universe = SECTOR_ROTATION_UNIVERSE_EXT
    return _run_rotation_backtest(prices, universe, momentum_window=5, hold_days=5,
                                   spread_threshold=0.015, max_positions=5, position_size=0.10)


# ---------- Leveraged / inverse ETF strategies (added 2026-05-21) ----------

def _hold_when_in_market(prices: pd.DataFrame, in_market: pd.Series,
                        in_ticker: str, out_ticker: str = "BIL") -> pd.Series:
    """Generic regime-routed strategy: hold in_ticker when in_market, out_ticker otherwise.
    Both tickers must be in prices. Returns daily-NAV time series."""
    if in_ticker not in prices.columns:
        return pd.Series(dtype=float)
    in_p = prices[in_ticker].dropna()
    if out_ticker in prices.columns:
        out_p = prices[out_ticker].dropna()
    else:
        out_p = pd.Series(1.0, index=in_p.index)  # static "cash" if BIL missing
    common = in_p.index.intersection(out_p.index).intersection(in_market.index)
    in_p, out_p, in_market_c = in_p.loc[common], out_p.loc[common], in_market.loc[common]
    in_ret = in_p.pct_change().fillna(0)
    out_ret = out_p.pct_change().fillna(0)
    daily_ret = in_ret.where(in_market_c, out_ret)
    return INITIAL_NAV * (1 + daily_ret).cumprod()


def strat_trend_leveraged_tqqq(prices: pd.DataFrame) -> pd.Series:
    """Trend-following with 3× leverage: TQQQ when SPY > 200d MA, BIL otherwise.
    Available from 2010-02 (TQQQ launch). Captures the COVID + 2022 bear + post-COVID
    bull. Beta-decay is real but historically high CAGR."""
    spy = prices["SPY"].dropna()
    ma = spy.rolling(200).mean()
    in_market = (spy > ma).shift(1).fillna(False).astype(bool)
    return _hold_when_in_market(prices, in_market, "TQQQ", "BIL")


def strat_trend_leveraged_upro(prices: pd.DataFrame) -> pd.Series:
    """Trend-following with 3× leverage on SPY: UPRO when SPY > 200d MA, BIL otherwise.
    Available from 2009-06 (UPRO launch). Captures the post-GFC recovery."""
    spy = prices["SPY"].dropna()
    ma = spy.rolling(200).mean()
    in_market = (spy > ma).shift(1).fillna(False).astype(bool)
    return _hold_when_in_market(prices, in_market, "UPRO", "BIL")


def strat_trend_with_inverse(prices: pd.DataFrame) -> pd.Series:
    """Trend-following with inverse-ETF downside: SPY when SPY > 200d MA, SH when SPY < 200d MA.
    Available from 2006-06 (SH launch). Lets us 'bet on downside' without literal shorting —
    max loss = 100% of position, not infinite."""
    spy = prices["SPY"].dropna()
    ma = spy.rolling(200).mean()
    in_market = (spy > ma).shift(1).fillna(False).astype(bool)
    return _hold_when_in_market(prices, in_market, "SPY", "SH")


def strat_hedgefundie(prices: pd.DataFrame, upro_pct: float = 0.55, tmf_pct: float = 0.45) -> pd.Series:
    """Hedgefundie's Excellent Adventure: 55% UPRO (3× SPY) + 45% TMF (3× treasuries),
    rebalanced monthly. The classic leveraged 60/40. Available from 2009-06 (UPRO + TMF launch).
    High vol, high CAGR historically, brutal in 2022 when stocks AND bonds fell together."""
    if "UPRO" not in prices.columns or "TMF" not in prices.columns:
        return pd.Series(dtype=float)
    upro = prices["UPRO"].dropna()
    tmf = prices["TMF"].dropna()
    common = upro.index.intersection(tmf.index)
    upro, tmf = upro.loc[common], tmf.loc[common]
    upro_ret = upro.pct_change().fillna(0)
    tmf_ret = tmf.pct_change().fillna(0)
    blended = upro_pct * upro_ret + tmf_pct * tmf_ret
    return INITIAL_NAV * (1 + blended).cumprod()


def strat_buy_dip_tqqq(prices: pd.DataFrame, dip_pct: float = 0.05, lookback: int = 20) -> pd.Series:
    """Buy TQQQ on N-day drawdown of `dip_pct`; exit on new N-day high. Hold cash (BIL)
    when not in a buy-dip event. Available from 2010-02 (TQQQ launch)."""
    if "TQQQ" not in prices.columns or "SPY" not in prices.columns:
        return pd.Series(dtype=float)
    spy = prices["SPY"].dropna()
    tqqq = prices["TQQQ"].dropna()
    common = spy.index.intersection(tqqq.index)
    spy, tqqq = spy.loc[common], tqqq.loc[common]
    spy_high = spy.rolling(lookback).max()
    in_dip = ((spy / spy_high - 1) <= -dip_pct).astype(bool)
    # State: once we enter on dip, hold until SPY hits a new 20d high
    new_high = (spy >= spy_high).astype(bool)
    holding = pd.Series(False, index=spy.index)
    state = False
    for i, date in enumerate(spy.index):
        if not state and in_dip.iloc[i]:
            state = True
        elif state and new_high.iloc[i]:
            state = False
        holding.iloc[i] = state
    holding_yest = holding.shift(1).fillna(False).astype(bool)
    if "BIL" in prices.columns:
        bil = prices["BIL"].reindex(common).ffill().bfill()
        bil_ret = bil.pct_change().fillna(0)
    else:
        bil_ret = pd.Series(0.0, index=common)
    tqqq_ret = tqqq.pct_change().fillna(0)
    daily_ret = tqqq_ret.where(holding_yest, bil_ret)
    return INITIAL_NAV * (1 + daily_ret).cumprod()


# Short-hold + hedged variants of leveraged trend (added 2026-05-21 per user request)


def _max_hold_overlay(holding_signal: pd.Series, max_hold_days: int) -> pd.Series:
    """Force exit after max_hold_days of continuous holding, even if signal still on.
    Re-entry requires signal to fire again the next day. Tests whether forced shorter
    holds reduce decay/risk vs let-it-ride."""
    out = pd.Series(False, index=holding_signal.index)
    days_held = 0
    cooldown = False
    for i in range(len(holding_signal)):
        if holding_signal.iloc[i] and not cooldown:
            out.iloc[i] = True
            days_held += 1
            if days_held >= max_hold_days:
                cooldown = True
                days_held = 0
        else:
            out.iloc[i] = False
            days_held = 0
            if cooldown and not holding_signal.iloc[i]:
                cooldown = False  # cooldown ends when signal also drops
    return out


def _leveraged_trend_with_max_hold(prices: pd.DataFrame, lev_ticker: str,
                                    max_hold_days: int = 5, ma_window: int = 200) -> pd.Series:
    """Leveraged trend with forced exit after max_hold_days. Otherwise BIL."""
    if "SPY" not in prices.columns or lev_ticker not in prices.columns:
        return pd.Series(dtype=float)
    spy = prices["SPY"].dropna()
    ma = spy.rolling(ma_window).mean()
    raw_signal = (spy > ma).shift(1).fillna(False).astype(bool)
    capped = _max_hold_overlay(raw_signal, max_hold_days)
    return _hold_when_in_market(prices, capped, lev_ticker, "BIL")


def strat_tqqq_trend_1d_hold(prices: pd.DataFrame) -> pd.Series:
    """TQQQ trend with forced 1-day-then-cooldown holds. Tests minimum decay exposure."""
    return _leveraged_trend_with_max_hold(prices, "TQQQ", max_hold_days=1)


def strat_tqqq_trend_5d_hold(prices: pd.DataFrame) -> pd.Series:
    """TQQQ trend with forced 5-day max holds. Balance between decay and momentum capture."""
    return _leveraged_trend_with_max_hold(prices, "TQQQ", max_hold_days=5)


def strat_tqqq_trend_21d_hold(prices: pd.DataFrame) -> pd.Series:
    """TQQQ trend with forced 21-day (1-month) max holds."""
    return _leveraged_trend_with_max_hold(prices, "TQQQ", max_hold_days=21)


def strat_tqqq_trend_vix_gated(prices: pd.DataFrame, vix_max: float = 25) -> pd.Series:
    """TQQQ when SPY > 200d MA AND VIX < vix_max, else BIL. Adds vol-spike hedge —
    exit on high vol even if trend technically still on, since high vol often precedes
    crashes."""
    if "SPY" not in prices.columns or "TQQQ" not in prices.columns or "^VIX" not in prices.columns:
        return pd.Series(dtype=float)
    spy = prices["SPY"].dropna()
    vix = prices["^VIX"].dropna()
    ma = spy.rolling(200).mean()
    trend_ok = (spy > ma).shift(1).fillna(False).astype(bool)
    vix_ok = (vix < vix_max).shift(1).fillna(False).astype(bool)
    common = trend_ok.index.intersection(vix_ok.index)
    combined = (trend_ok.loc[common] & vix_ok.loc[common]).astype(bool)
    return _hold_when_in_market(prices, combined, "TQQQ", "BIL")


def strat_tqqq_trend_trailing_stop(prices: pd.DataFrame, stop_pct: float = 0.10) -> pd.Series:
    """TQQQ trend with a trailing-stop layer: exit on `stop_pct` drawdown from in-position
    peak, even if 200d MA signal still on. Re-enter only after both signal AND a new local
    high after the stop. Adds a hard floor on drawdown.
    """
    if "SPY" not in prices.columns or "TQQQ" not in prices.columns or "BIL" not in prices.columns:
        return pd.Series(dtype=float)
    spy = prices["SPY"].dropna()
    tqqq = prices["TQQQ"].dropna()
    bil = prices["BIL"].dropna()
    common = spy.index.intersection(tqqq.index).intersection(bil.index)
    spy, tqqq, bil = spy.loc[common], tqqq.loc[common], bil.loc[common]

    ma = spy.rolling(200).mean()
    trend_on = (spy > ma).shift(1).fillna(False).astype(bool)
    tqqq_ret = tqqq.pct_change().fillna(0)
    bil_ret = bil.pct_change().fillna(0)

    holding = pd.Series(False, index=common)
    in_pos = False
    pos_peak = 0.0
    stopped_out = False
    for i, date in enumerate(common):
        price = tqqq.iloc[i]
        if in_pos:
            if price > pos_peak:
                pos_peak = price
            if price <= pos_peak * (1 - stop_pct):
                # Trailing-stop hit
                in_pos = False
                stopped_out = True
            elif not trend_on.iloc[i]:
                # Trend turned off, exit normally
                in_pos = False
        else:
            if trend_on.iloc[i] and not stopped_out:
                in_pos = True
                pos_peak = price
            elif stopped_out and not trend_on.iloc[i]:
                # Cooldown ends when trend goes off
                stopped_out = False
        holding.iloc[i] = in_pos
    daily_ret = tqqq_ret.where(holding, bil_ret)
    return INITIAL_NAV * (1 + daily_ret).cumprod()


def strat_synth_3x_qqq_trend(prices: pd.DataFrame) -> pd.Series:
    """The TQQQ trend strategy applied to synthetic 3× QQQ, extending the backtest
    to QQQ's 1999 inception. Uses BIL_EXTENDED for cash so we get the full window
    (not truncated to BIL's 2007 inception). Lets us see how the strategy would have
    performed in dot-com (2000-02) and GFC (2007-09)."""
    if "SYNTH_3X_QQQ" not in prices.columns or "SPY" not in prices.columns:
        return pd.Series(dtype=float)
    spy = prices["SPY"].dropna()
    ma = spy.rolling(200).mean()
    in_market = (spy > ma).shift(1).fillna(False).astype(bool)
    return _hold_when_in_market(prices, in_market, "SYNTH_3X_QQQ", "BIL_EXTENDED")


def strat_synth_3x_spy_trend(prices: pd.DataFrame) -> pd.Series:
    """UPRO trend strategy applied to synthetic 3× SPY, extending to SPY's 1993 inception.
    Includes dot-com AND GFC (both pre-real-UPRO)."""
    if "SYNTH_3X_SPY" not in prices.columns or "SPY" not in prices.columns:
        return pd.Series(dtype=float)
    spy = prices["SPY"].dropna()
    ma = spy.rolling(200).mean()
    in_market = (spy > ma).shift(1).fillna(False).astype(bool)
    return _hold_when_in_market(prices, in_market, "SYNTH_3X_SPY", "BIL_EXTENDED")


def strat_synth_3x_qqq_trend_vix_gated(prices: pd.DataFrame, vix_max: float = 25) -> pd.Series:
    """Synthetic 3× QQQ with both trend filter AND VIX gate, full-window (uses BIL_EXTENDED)."""
    if "SYNTH_3X_QQQ" not in prices.columns:
        return pd.Series(dtype=float)
    spy = prices["SPY"].dropna()
    vix = prices["^VIX"].dropna()
    ma = spy.rolling(200).mean()
    trend_ok = (spy > ma).shift(1).fillna(False).astype(bool)
    vix_ok = (vix < vix_max).shift(1).fillna(False).astype(bool)
    common = trend_ok.index.intersection(vix_ok.index)
    combined = (trend_ok.loc[common] & vix_ok.loc[common]).astype(bool)
    return _hold_when_in_market(prices, combined, "SYNTH_3X_QQQ", "BIL_EXTENDED")


def strat_synth_3x_qqq_trend_trailing_stop(prices: pd.DataFrame, stop_pct: float = 0.10) -> pd.Series:
    """Synthetic 3× QQQ trend with 10% trailing stop — full-window test of the hedged
    version through dot-com and GFC. This is the most promising candidate."""
    if "SYNTH_3X_QQQ" not in prices.columns or "BIL_EXTENDED" not in prices.columns:
        return pd.Series(dtype=float)
    spy = prices["SPY"].dropna()
    synth = prices["SYNTH_3X_QQQ"].dropna()
    bil = prices["BIL_EXTENDED"].dropna()
    common = spy.index.intersection(synth.index).intersection(bil.index)
    spy, synth, bil = spy.loc[common], synth.loc[common], bil.loc[common]

    ma = spy.rolling(200).mean()
    trend_on = (spy > ma).shift(1).fillna(False).astype(bool)
    synth_ret = synth.pct_change().fillna(0)
    bil_ret = bil.pct_change().fillna(0)

    holding = pd.Series(False, index=common)
    in_pos = False
    pos_peak = 0.0
    stopped_out = False
    for i in range(len(common)):
        price = synth.iloc[i]
        if in_pos:
            if price > pos_peak:
                pos_peak = price
            if price <= pos_peak * (1 - stop_pct):
                in_pos = False
                stopped_out = True
            elif not trend_on.iloc[i]:
                in_pos = False
        else:
            if trend_on.iloc[i] and not stopped_out:
                in_pos = True
                pos_peak = price
            elif stopped_out and not trend_on.iloc[i]:
                stopped_out = False
        holding.iloc[i] = in_pos
    daily_ret = synth_ret.where(holding, bil_ret)
    return INITIAL_NAV * (1 + daily_ret).cumprod()


def strat_vix_timing_with_inverse(prices: pd.DataFrame, low_vix: float = 20, high_vix: float = 30) -> pd.Series:
    """Long SPY when VIX < low_vix, long SH when VIX > high_vix, BIL otherwise.
    Available from 2006-06 (SH launch). VIX low = complacency = ride SPY; VIX high = panic
    = ride downside via SH; in between = sit in cash."""
    if "^VIX" not in prices.columns or "SH" not in prices.columns:
        return pd.Series(dtype=float)
    spy = prices["SPY"].dropna()
    sh = prices["SH"].dropna()
    vix = prices["^VIX"].dropna()
    bil = prices["BIL"].dropna() if "BIL" in prices.columns else None
    common = spy.index.intersection(sh.index).intersection(vix.index)
    if bil is not None:
        common = common.intersection(bil.index)
    spy, sh, vix = spy.loc[common], sh.loc[common], vix.loc[common]
    bil_c = bil.loc[common] if bil is not None else pd.Series(1.0, index=common)
    long_spy = (vix < low_vix).shift(1).fillna(False).astype(bool)
    long_sh = (vix > high_vix).shift(1).fillna(False).astype(bool)
    spy_ret = spy.pct_change().fillna(0)
    sh_ret = sh.pct_change().fillna(0)
    bil_ret = bil_c.pct_change().fillna(0)
    daily_ret = bil_ret.copy()  # default: in cash
    daily_ret = daily_ret.where(~long_spy, spy_ret)
    daily_ret = daily_ret.where(~long_sh, sh_ret)
    return INITIAL_NAV * (1 + daily_ret).cumprod()


def strat_sector_rotation_sensitivity_best(prices: pd.DataFrame, universe: list[str] | None = None) -> pd.Series:
    """The sensitivity-best variant per the prior walk-forward: 5d momentum, 21d hold, 3% spread, top-3, 5% size.
    This matched SPY on Sharpe in the 2020-2026 OOS window."""
    if universe is None:
        universe = SECTOR_ROTATION_UNIVERSE_EXT
    return _run_rotation_backtest(prices, universe, momentum_window=5, hold_days=21,
                                   spread_threshold=0.03, max_positions=3, position_size=0.05)


# ---------- Walk-forward / regime conditional ----------

def regime_split_metrics(nav: pd.Series, prices: pd.DataFrame, ma_window: int = 200) -> dict:
    """Split nav into SPY-bull-regime days and SPY-bear-regime days. Compute annualized
    metrics conditional on each regime.
    Regime proxy: SPY > 200-day MA on the prior day = bull, else bear.
    """
    spy = prices["SPY"].dropna()
    spy_ma = spy.rolling(ma_window).mean()
    in_bull = (spy > spy_ma).shift(1).fillna(False).astype(bool)
    common = nav.dropna().index.intersection(in_bull.index)
    nav_c = nav.loc[common]
    in_bull_c = in_bull.loc[common]
    daily_ret = nav_c.pct_change().fillna(0)

    def annualized(ret_series_in_regime):
        if len(ret_series_in_regime) < 30:
            return {"cagr_pct": None, "sharpe": None, "days": int(len(ret_series_in_regime))}
        mean_d = ret_series_in_regime.mean()
        std_d = ret_series_in_regime.std()
        cagr = ((1 + mean_d) ** TRADING_DAYS_PER_YEAR - 1) * 100
        sharpe = (mean_d * TRADING_DAYS_PER_YEAR) / (std_d * np.sqrt(TRADING_DAYS_PER_YEAR)) if std_d > 0 else 0
        return {
            "cagr_pct": round(cagr, 2),
            "sharpe": round(sharpe, 2),
            "days": int(len(ret_series_in_regime)),
        }

    bull_ret = daily_ret.loc[in_bull_c]
    bear_ret = daily_ret.loc[~in_bull_c]
    return {"bull": annualized(bull_ret), "bear": annualized(bear_ret)}


def sub_window_metrics(nav: pd.Series, prices: pd.DataFrame, window_years: int = 5) -> list[dict]:
    """Compute metrics on rolling (non-overlapping) sub-windows of N years each."""
    nav = nav.dropna()
    if len(nav) < 2:
        return []
    windows = []
    start = nav.index[0]
    end_data = nav.index[-1]
    while start < end_data:
        end = start + pd.DateOffset(years=window_years)
        sub = nav.loc[start:end]
        if len(sub) >= 100:
            m = metrics(sub)
            windows.append({
                "start": str(sub.index[0].date()),
                "end": str(sub.index[-1].date()),
                **m,
            })
        start = end
    return windows


# ---------- Ensemble ----------

def strat_ensemble_regime_routed(prices: pd.DataFrame) -> pd.Series:
    """Multi-strategy ensemble that switches based on SPY's 200d MA position.
    Bull regime (SPY > 200d MA): run sensitivity-best sector rotation.
    Bear regime (SPY < 200d MA): hold BIL (cash equivalent) — capital preservation.

    This is a primitive Phase 4+ vision test — what would happen if MACRO-style
    regime detection routed between strategies historically?
    """
    spy = prices["SPY"].dropna()
    spy_ma = spy.rolling(200).mean()
    in_bull = (spy > spy_ma).shift(1).fillna(False).astype(bool)

    # Run sensitivity-best on the full history (always)
    rot_nav = strat_sector_rotation_sensitivity_best(prices)
    # BIL as bear-regime parking
    if "BIL" in prices.columns:
        bil = prices["BIL"].dropna()
        bil_ret = bil.pct_change().fillna(0)
    else:
        bil_ret = pd.Series(0.0, index=rot_nav.index)  # 0% in cash if no BIL data

    # Compose: each day, take rotation's daily return if bull, else BIL's
    rot_daily_ret = rot_nav.pct_change().fillna(0)
    common = rot_daily_ret.index.intersection(in_bull.index).intersection(bil_ret.index if len(bil_ret) > 0 else rot_daily_ret.index)
    rot_c = rot_daily_ret.loc[common]
    bull_c = in_bull.loc[common]
    bil_c = bil_ret.reindex(common).fillna(0) if len(bil_ret) > 0 else pd.Series(0.0, index=common)

    ensemble_ret = rot_c.where(bull_c, bil_c)
    return INITIAL_NAV * (1 + ensemble_ret).cumprod()


# ---------- Report ----------

def write_report(results: list[dict], path: Path) -> None:
    lines = [
        "# Multi-Strategy Extended Walk-Forward Report",
        "",
        f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Context",
        "",
        "Every strategy in `compare_strategies.py` (plus a regime-routed ensemble) run on the **maximum-available historical window**:",
        "",
        f"- Sector rotation universe: 10 ETFs (dropped XLC + XLRE; window starts {EXTENDED_START})",
        "- SPY-only / SPY-anchored strategies: 1993+ (33+ years)",
        "- 60/40 limited by TLT to 2002+",
        "- Dual momentum limited by VEU/BIL to 2007+",
        "",
        "## Headline summary",
        "",
        "| Strategy | Years | CAGR | Sharpe | MaxDD | Calmar |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        m = r["metrics"]
        if not m:
            continue
        lines.append(f"| {r['name']} | {m.get('years','?')} | {m.get('cagr_pct','?')}% | "
                     f"{m.get('sharpe','?')} | {m.get('max_drawdown_pct','?')}% | {m.get('calmar','?')} |")
    lines.append("")
    lines.append("## Regime-conditional breakdown (SPY 200d MA proxy)")
    lines.append("")
    lines.append("| Strategy | Bull CAGR | Bull Sharpe | Bear CAGR | Bear Sharpe |")
    lines.append("|---|---:|---:|---:|---:|")
    for r in results:
        reg = r.get("regime", {})
        bull = reg.get("bull", {})
        bear = reg.get("bear", {})
        lines.append(f"| {r['name']} | {bull.get('cagr_pct','?')}% | {bull.get('sharpe','?')} | "
                     f"{bear.get('cagr_pct','?')}% | {bear.get('sharpe','?')} |")
    lines.append("")
    lines.append("## Per-strategy 5-year sub-window metrics")
    lines.append("")
    lines.append("Tests whether each strategy works across diverse historical regimes "
                 "(2000-04 dot-com unwind, 2005-09 GFC build+crash, 2010-14 recovery, "
                 "2015-19 late-cycle bull, 2020-24 COVID+bear).")
    lines.append("")
    for r in results:
        if not r.get("sub_windows"):
            continue
        lines.append(f"### {r['name']}")
        lines.append("")
        df = pd.DataFrame(r["sub_windows"])
        lines.append(df.to_markdown(index=False))
        lines.append("")
    lines.append("## Verdict per strategy")
    lines.append("")
    spy_full = next((r for r in results if r["name"] == "buy_hold_spy"), None)
    spy_cagr = spy_full["metrics"]["cagr_pct"] if spy_full else None
    for r in results:
        m = r["metrics"]
        if not m or not spy_cagr:
            continue
        if r["name"] == "buy_hold_spy":
            lines.append(f"- **{r['name']}**: Baseline (CAGR {m['cagr_pct']}%, Sharpe {m['sharpe']}).")
            continue
        verdict_parts = []
        if m["cagr_pct"] >= spy_cagr:
            verdict_parts.append("BEATS SPY on CAGR")
        elif m["cagr_pct"] >= spy_cagr * 0.8:
            verdict_parts.append(f"underperforms SPY by {spy_cagr - m['cagr_pct']:.1f}pp CAGR")
        else:
            verdict_parts.append(f"SIGNIFICANTLY underperforms SPY (CAGR {m['cagr_pct']}% vs SPY's {spy_cagr}%)")
        if m["sharpe"] >= 1.0:
            verdict_parts.append(f"Sharpe {m['sharpe']} > 1.0 (good)")
        elif m["sharpe"] >= (spy_full["metrics"]["sharpe"] if spy_full else 0.8):
            verdict_parts.append(f"Sharpe {m['sharpe']} matches SPY")
        else:
            verdict_parts.append(f"Sharpe {m['sharpe']} below SPY")
        if abs(m["max_drawdown_pct"]) <= 15:
            verdict_parts.append(f"low max DD ({m['max_drawdown_pct']}%)")
        elif abs(m["max_drawdown_pct"]) <= 25:
            verdict_parts.append(f"moderate DD ({m['max_drawdown_pct']}%)")
        else:
            verdict_parts.append(f"high DD ({m['max_drawdown_pct']}%)")
        lines.append(f"- **{r['name']}**: {'; '.join(verdict_parts)}.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------- Main ----------

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = fetch_prices(ALL_TICKERS)
    prices = add_synthetic_leveraged_to_prices(prices)
    prices = add_synthetic_cash(prices)
    print(f"  Added synthetic leveraged columns: {[c for c in prices.columns if c.startswith('SYNTH_')]}")
    print(f"  BIL_EXTENDED covers: {prices['BIL_EXTENDED'].dropna().index[0].date()} to {prices['BIL_EXTENDED'].dropna().index[-1].date()}")

    strategies = [
        # Classical strategies
        ("buy_hold_spy", lambda p: strat_buy_hold(p, "SPY"), "1993+"),
        ("buy_hold_qqq", lambda p: strat_buy_hold(p, "QQQ"), "1999+"),
        ("trend_following_spy_200d", lambda p: strat_trend_following(p, "SPY", 200), "1993+"),
        ("sixty_forty", strat_sixty_forty, "2002+ (TLT)"),
        ("dual_momentum", strat_dual_momentum, "2007+ (BIL/VEU)"),
        ("sector_momentum_top3_monthly", strat_sector_momentum_monthly, "1999+ (sectors)"),
        ("vix_overlay_spy_25", lambda p: strat_vix_overlay_spy(p, 25), "2007+ (BIL)"),
        ("vix_overlay_spy_30", lambda p: strat_vix_overlay_spy(p, 30), "2007+ (BIL)"),
        # Sector rotation (the current live design)
        ("sector_rotation_5d_live", strat_sector_rotation_5d_live, "1999+ (sectors)"),
        ("sector_rotation_sensitivity_best", strat_sector_rotation_sensitivity_best, "1999+ (sectors)"),
        ("ensemble_regime_routed", strat_ensemble_regime_routed, "1999+"),
        # Leveraged / inverse ETF strategies (added 2026-05-21)
        ("trend_leveraged_tqqq", strat_trend_leveraged_tqqq, "2010+ (TQQQ)"),
        ("trend_leveraged_upro", strat_trend_leveraged_upro, "2009+ (UPRO)"),
        ("trend_with_inverse_sh", strat_trend_with_inverse, "2006+ (SH)"),
        ("hedgefundie_55_45_upro_tmf", strat_hedgefundie, "2009+ (UPRO+TMF)"),
        ("buy_dip_tqqq", strat_buy_dip_tqqq, "2010+ (TQQQ)"),
        ("vix_timing_with_inverse", strat_vix_timing_with_inverse, "2006+ (SH+VIX)"),
        # Short-hold variants of TQQQ trend
        ("tqqq_trend_1d_hold", strat_tqqq_trend_1d_hold, "2010+ (TQQQ)"),
        ("tqqq_trend_5d_hold", strat_tqqq_trend_5d_hold, "2010+ (TQQQ)"),
        ("tqqq_trend_21d_hold", strat_tqqq_trend_21d_hold, "2010+ (TQQQ)"),
        # Hedged variants
        ("tqqq_trend_vix_gated", strat_tqqq_trend_vix_gated, "2010+ (TQQQ+VIX)"),
        ("tqqq_trend_trailing_stop_10pct", strat_tqqq_trend_trailing_stop, "2010+ (TQQQ)"),
        # SYNTHETIC leveraged (extends test through dot-com + GFC)
        ("synth_3x_qqq_trend", strat_synth_3x_qqq_trend, "1999+ SYNTHETIC"),
        ("synth_3x_spy_trend", strat_synth_3x_spy_trend, "1993+ SYNTHETIC"),
        ("synth_3x_qqq_trend_vix_gated", strat_synth_3x_qqq_trend_vix_gated, "1999+ SYNTHETIC"),
        ("synth_3x_qqq_trend_trailing_stop_10pct", strat_synth_3x_qqq_trend_trailing_stop, "1999+ SYNTHETIC"),
    ]

    results = []
    for name, fn, window_note in strategies:
        print(f"\n=== {name} ({window_note}) ===")
        t0 = time.time()
        try:
            nav = fn(prices)
            if nav.empty:
                print(f"  empty — skipping")
                continue
            m = metrics(nav)
            reg = regime_split_metrics(nav, prices)
            sub = sub_window_metrics(nav, prices, window_years=5)
            results.append({
                "name": name,
                "metrics": m,
                "regime": reg,
                "sub_windows": sub,
                "nav": nav,  # keep for ensemble / save later
            })
            print(f"  CAGR {m['cagr_pct']}%, Sharpe {m['sharpe']}, MaxDD {m['max_drawdown_pct']}%, "
                  f"years {m['years']} ({time.time() - t0:.0f}s)")
        except Exception as e:
            print(f"  FAILED: {e}")

    # Persist headline CSV
    summary_rows = []
    for r in results:
        row = {"strategy": r["name"], **r["metrics"]}
        # flatten regime
        bull = r["regime"].get("bull", {})
        bear = r["regime"].get("bear", {})
        row["bull_cagr_pct"] = bull.get("cagr_pct")
        row["bull_sharpe"] = bull.get("sharpe")
        row["bear_cagr_pct"] = bear.get("cagr_pct")
        row["bear_sharpe"] = bear.get("sharpe")
        summary_rows.append(row)
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(OUTPUT_DIR / "extended_summary.csv", index=False)

    # Persist daily NAVs for downstream analysis
    nav_df = pd.DataFrame({r["name"]: r["nav"] for r in results}).dropna(how="all")
    nav_df.to_csv(OUTPUT_DIR / "extended_nav.csv")

    write_report(results, OUTPUT_DIR / "extended_report.md")
    print(f"\nReport:  {OUTPUT_DIR / 'extended_report.md'}")
    print(f"Summary: {OUTPUT_DIR / 'extended_summary.csv'}")
    print(f"NAVs:    {OUTPUT_DIR / 'extended_nav.csv'}")


if __name__ == "__main__":
    main()
