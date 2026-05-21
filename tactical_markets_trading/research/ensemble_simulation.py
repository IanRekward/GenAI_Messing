"""Multi-strategy ensemble simulation.

Tests three ways of combining strategies vs running any single one:
1. Equal-weight blend (33/33/33) of trend_leveraged + 60/40 + trend_following_spy
2. Risk-parity (inverse-vol weighting recalculated monthly)
3. Regime-routed: pick the right strategy for the current regime

The Phase 4+ PRD vision is regime-routing. This script tests whether the vision
would have worked historically.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from multi_strategy_extended import (
    ALL_TICKERS,
    INITIAL_NAV,
    TRADING_DAYS_PER_YEAR,
    add_synthetic_cash,
    add_synthetic_leveraged_to_prices,
    fetch_prices,
    metrics,
    strat_buy_hold,
    strat_sixty_forty,
    strat_synth_3x_qqq_trend_trailing_stop,
    strat_trend_following,
)

OUTPUT_DIR = Path(__file__).resolve().parent / "data"


def _daily_returns(nav: pd.Series) -> pd.Series:
    return nav.pct_change().fillna(0)


def equal_weight_ensemble(component_navs: dict[str, pd.Series]) -> pd.Series:
    """Equal-weight daily-rebalanced ensemble. Each day, allocate 1/N of NAV to each component's daily return."""
    rets = {name: _daily_returns(nav) for name, nav in component_navs.items()}
    common = None
    for s in rets.values():
        common = s.index if common is None else common.intersection(s.index)
    rets = {name: s.loc[common] for name, s in rets.items()}
    weight = 1.0 / len(rets)
    blended = sum(weight * s for s in rets.values())
    return INITIAL_NAV * (1 + blended).cumprod()


def risk_parity_ensemble(component_navs: dict[str, pd.Series], lookback_days: int = 63) -> pd.Series:
    """Inverse-volatility weighted, recalculated daily over a 63-day lookback (~3 months)."""
    rets = {name: _daily_returns(nav) for name, nav in component_navs.items()}
    common = None
    for s in rets.values():
        common = s.index if common is None else common.intersection(s.index)
    rets_df = pd.DataFrame({name: s.loc[common] for name, s in rets.items()})
    vol = rets_df.rolling(lookback_days).std()
    inv_vol = 1.0 / vol.replace(0, np.nan)
    weights = inv_vol.div(inv_vol.sum(axis=1), axis=0).fillna(1.0 / len(rets_df.columns))
    # Use yesterday's weights to avoid lookahead
    weights = weights.shift(1).fillna(1.0 / len(rets_df.columns))
    blended = (weights * rets_df).sum(axis=1)
    return INITIAL_NAV * (1 + blended).cumprod()


def regime_routed_ensemble(prices: pd.DataFrame) -> pd.Series:
    """Phase 4+ vision: route between strategies based on regime.
    - SPY > 200d MA AND VIX < 25 (bull/calm):    tqqq_trend_trailing_stop_10pct (leveraged growth)
    - SPY > 200d MA AND VIX >= 25 (bull/elevated): 60/40 (balanced)
    - SPY < 200d MA (bear):                        BIL_EXTENDED (cash/capital preservation)
    """
    spy = prices["SPY"].dropna()
    vix = prices["^VIX"].dropna()
    bil = prices["BIL_EXTENDED"].dropna()
    ma = spy.rolling(200).mean()

    trend_on = (spy > ma).shift(1).fillna(False).astype(bool)
    vix_calm = (vix < 25).shift(1).fillna(False).astype(bool)

    tqqq_strat = strat_synth_3x_qqq_trend_trailing_stop(prices)
    sixty_forty_strat = strat_sixty_forty(prices)
    common = (tqqq_strat.index
              .intersection(sixty_forty_strat.index)
              .intersection(trend_on.index)
              .intersection(vix_calm.index)
              .intersection(bil.index))

    tqqq_ret = _daily_returns(tqqq_strat.loc[common])
    sf_ret = _daily_returns(sixty_forty_strat.loc[common])
    bil_ret = _daily_returns(bil.loc[common])
    trend_on_c = trend_on.loc[common]
    vix_calm_c = vix_calm.loc[common]

    # Start with bil_ret as default (bear regime)
    daily_ret = bil_ret.copy()
    # Bull + elevated VIX -> 60/40
    bull_elevated = trend_on_c & ~vix_calm_c
    daily_ret = daily_ret.where(~bull_elevated, sf_ret)
    # Bull + calm -> leveraged
    bull_calm = trend_on_c & vix_calm_c
    daily_ret = daily_ret.where(~bull_calm, tqqq_ret)

    return INITIAL_NAV * (1 + daily_ret).cumprod()


def regime_routed_diagnostics(prices: pd.DataFrame) -> dict:
    """Report what % of days each regime was active."""
    spy = prices["SPY"].dropna()
    vix = prices["^VIX"].dropna()
    ma = spy.rolling(200).mean()
    trend_on = (spy > ma).shift(1).fillna(False).astype(bool)
    vix_calm = (vix < 25).shift(1).fillna(False).astype(bool)
    common = trend_on.index.intersection(vix_calm.index)
    trend_on_c = trend_on.loc[common]
    vix_calm_c = vix_calm.loc[common]
    bull_calm = (trend_on_c & vix_calm_c).sum()
    bull_elevated = (trend_on_c & ~vix_calm_c).sum()
    bear = (~trend_on_c).sum()
    total = len(common)
    return {
        "total_days": total,
        "bull_calm_pct (leveraged)": round(bull_calm / total * 100, 1),
        "bull_elevated_pct (60/40)": round(bull_elevated / total * 100, 1),
        "bear_pct (cash)": round(bear / total * 100, 1),
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = fetch_prices(ALL_TICKERS)
    prices = add_synthetic_leveraged_to_prices(prices)
    prices = add_synthetic_cash(prices)

    print("\n=== Building component strategies ===")
    components = {
        "tqqq_trend_trailing_stop_10pct (synth, 1999+)": strat_synth_3x_qqq_trend_trailing_stop(prices),
        "sixty_forty (2002+)": strat_sixty_forty(prices),
        "trend_following_spy_200d (1993+)": strat_trend_following(prices),
    }
    for name, nav in components.items():
        m = metrics(nav)
        print(f"  {name}: CAGR {m['cagr_pct']}% Sharpe {m['sharpe']} MaxDD {m['max_drawdown_pct']}% years {m['years']}")

    print("\n=== Equal-weight ensemble ===")
    ew = equal_weight_ensemble(components)
    m = metrics(ew)
    print(f"  CAGR {m['cagr_pct']}% Sharpe {m['sharpe']} MaxDD {m['max_drawdown_pct']}% years {m['years']}")

    print("\n=== Risk-parity ensemble (inverse-vol, 63d lookback) ===")
    rp = risk_parity_ensemble(components)
    m = metrics(rp)
    print(f"  CAGR {m['cagr_pct']}% Sharpe {m['sharpe']} MaxDD {m['max_drawdown_pct']}% years {m['years']}")

    print("\n=== Regime-routed ensemble (Phase 4+ vision) ===")
    diag = regime_routed_diagnostics(prices)
    print(f"  Regime breakdown across history: {diag}")
    rr = regime_routed_ensemble(prices)
    m = metrics(rr)
    print(f"  CAGR {m['cagr_pct']}% Sharpe {m['sharpe']} MaxDD {m['max_drawdown_pct']}% years {m['years']}")

    print("\n=== Benchmarks for comparison ===")
    bm_spy = strat_buy_hold(prices, "SPY")
    print(f"  buy_hold_spy: CAGR {metrics(bm_spy)['cagr_pct']}% Sharpe {metrics(bm_spy)['sharpe']} MaxDD {metrics(bm_spy)['max_drawdown_pct']}%")

    # Persist
    out = pd.DataFrame({
        "equal_weight": ew,
        "risk_parity": rp,
        "regime_routed": rr,
        **{name: nav for name, nav in components.items()},
        "buy_hold_spy": bm_spy,
    }).dropna(how="all")
    out.to_csv(OUTPUT_DIR / "ensemble_nav.csv")
    print(f"\nNAVs: {OUTPUT_DIR / 'ensemble_nav.csv'}")


if __name__ == "__main__":
    main()
