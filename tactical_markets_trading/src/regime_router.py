"""Regime router for the Phase 3.2 ensemble.

Classifies the current market regime from price-based signals (SPY 200d MA, VIX)
and MACRO state (composite_band + size_multiplier via macro_consumer). Returns
the regime label plus the list of strategy names that should be active.

Decision rules (per phase-3-ensemble-design.md, Open Question 2, resolved 2026-05-21):

    IF MACRO red (size_multiplier == 0.0)            → bear
    ELIF SPY <= 200d MA                              → bear
    ELIF MACRO orange-high (size_multiplier == 0.5)
         OR VIX >= 25                                → bull_elevated
    ELSE                                             → bull_calm

Regime → active components:

    bull_calm:     all three strategies (TQQQ trend + sector momentum + SPY trend)
    bull_elevated: drop the leveraged TQQQ component (highest beta); keep the
                   diversifiers (sector momentum + SPY trend). The design doc
                   names "60/40" here; spy_trend is the closest analogue we have.
    bear:          no strategies active. Existing positions are NOT auto-flattened
                   by the router — strategies' own exit logic (200d MA cross,
                   trailing stop, monthly rebalance) handles that on subsequent
                   fires. Forced-exit-on-regime-change is a separate concern.

Pure module: takes pre-fetched signal values + macro_data dict. Does no I/O.
"""
from __future__ import annotations

REGIME_BULL_CALM = "bull_calm"
REGIME_BULL_ELEVATED = "bull_elevated"
REGIME_BEAR = "bear"

# Threshold from design doc. Not tuned — hand-picked. Sensitivity-test in Phase 3.3+.
VIX_ELEVATED_THRESHOLD = 25.0

_ACTIVE_STRATEGIES_BY_REGIME = {
    REGIME_BULL_CALM: [
        "trend_leveraged_tqqq",
        "trend_following_spy_200d",
        "sector_momentum_top3_monthly",
    ],
    REGIME_BULL_ELEVATED: [
        "trend_following_spy_200d",
        "sector_momentum_top3_monthly",
    ],
    REGIME_BEAR: [],
}


def classify(spy_close: float, spy_ma_200: float, vix: float,
             macro_data: dict | None) -> tuple[str, str]:
    """Classify the current regime. Pure function over the inputs.

    Args:
        spy_close: yesterday's SPY close.
        spy_ma_200: yesterday's 200-day SPY moving average.
        vix: yesterday's VIX close.
        macro_data: regime data dict from macro_consumer.validate (the third
            return value). May be None if MACRO is broken — that case is
            treated conservatively as bear so the bot doesn't make new
            entries on degraded signal.

    Returns:
        (regime_label, reason) — label is one of the REGIME_* constants,
        reason is a human-readable explanation suitable for logging.
    """
    # Lazy import to keep this module pure-Python for tests that don't want to
    # touch the file-system side of macro_consumer.
    import macro_consumer

    if macro_data is None:
        return REGIME_BEAR, "macro_data_unavailable_defensive_bear"

    macro_mult = macro_consumer.size_multiplier(macro_data)
    if macro_mult == 0.0:
        return REGIME_BEAR, f"macro_red (band={macro_data.get('composite_band')})"

    if spy_close <= spy_ma_200:
        return REGIME_BEAR, f"SPY ${spy_close:.2f} <= 200d MA ${spy_ma_200:.2f}"

    if macro_mult == 0.5:
        return REGIME_BULL_ELEVATED, (
            f"macro_orange_high (band={macro_data.get('composite_band')}, "
            f"regime={macro_data.get('regime')})"
        )

    if vix >= VIX_ELEVATED_THRESHOLD:
        return REGIME_BULL_ELEVATED, f"VIX {vix:.2f} >= {VIX_ELEVATED_THRESHOLD}"

    return REGIME_BULL_CALM, (
        f"SPY ${spy_close:.2f} > 200d MA ${spy_ma_200:.2f}, "
        f"VIX {vix:.2f} < {VIX_ELEVATED_THRESHOLD}, macro_mult=1.0"
    )


def active_strategies(regime_label: str) -> list[str]:
    """Strategy names active in the given regime. Unknown regime → empty list
    (defensive: skip everything rather than guess)."""
    return list(_ACTIVE_STRATEGIES_BY_REGIME.get(regime_label, []))
