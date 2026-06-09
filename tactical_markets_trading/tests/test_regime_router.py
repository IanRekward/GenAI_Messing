"""Tests for src/regime_router.py — Phase 3.2c regime classification."""
import pytest

import regime_router


# Fixtures: macro_data dicts at each tier (mimicking macro_consumer.validate's third return)

@pytest.fixture
def macro_green():
    return {"composite_band": "green", "regime": "low", "neutralized": False}


@pytest.fixture
def macro_orange_high():
    return {"composite_band": "orange", "regime": "high", "neutralized": False}


@pytest.fixture
def macro_red():
    return {"composite_band": "red", "regime": "high", "neutralized": False}


@pytest.fixture
def macro_stale_neutralized():
    # Stale MACRO degrades to neutral — size_multiplier returns 1.0 regardless of band
    return {"composite_band": "orange", "regime": "high", "neutralized": True}


# Decision tree from top to bottom

def test_macro_red_forces_bear_regardless_of_price(macro_red):
    regime, reason = regime_router.classify(
        spy_close=600, spy_ma_200=500, vix=10, macro_data=macro_red
    )
    assert regime == regime_router.REGIME_BEAR
    assert "macro_red" in reason


def test_spy_below_200d_is_bear(macro_green):
    regime, reason = regime_router.classify(
        spy_close=500, spy_ma_200=600, vix=10, macro_data=macro_green
    )
    assert regime == regime_router.REGIME_BEAR
    assert "200d MA" in reason


def test_spy_equal_200d_is_bear(macro_green):
    """Strict inequality — equal counts as bear (conservative)."""
    regime, _ = regime_router.classify(
        spy_close=600, spy_ma_200=600, vix=10, macro_data=macro_green
    )
    assert regime == regime_router.REGIME_BEAR


def test_macro_orange_high_is_bull_elevated_even_with_low_vix(macro_orange_high):
    regime, reason = regime_router.classify(
        spy_close=600, spy_ma_200=500, vix=10, macro_data=macro_orange_high
    )
    assert regime == regime_router.REGIME_BULL_ELEVATED
    assert "macro_orange_high" in reason


def test_high_vix_is_bull_elevated_even_with_green_macro(macro_green):
    regime, reason = regime_router.classify(
        spy_close=600, spy_ma_200=500, vix=30, macro_data=macro_green
    )
    assert regime == regime_router.REGIME_BULL_ELEVATED
    assert "VIX" in reason


def test_vix_at_threshold_is_bull_elevated(macro_green):
    """VIX >= 25 (boundary inclusive)."""
    regime, _ = regime_router.classify(
        spy_close=600, spy_ma_200=500, vix=25.0, macro_data=macro_green
    )
    assert regime == regime_router.REGIME_BULL_ELEVATED


def test_clean_bull_calm(macro_green):
    regime, reason = regime_router.classify(
        spy_close=600, spy_ma_200=500, vix=15, macro_data=macro_green
    )
    assert regime == regime_router.REGIME_BULL_CALM
    assert "macro_mult=1.0" in reason


def test_stale_macro_neutralized_is_bull_calm_if_other_signals_clean(macro_stale_neutralized):
    """Stale MACRO degrades to neutral (size_multiplier=1.0). When SPY trend on
    and VIX low, we're in bull_calm. The orange-high label is ignored."""
    regime, _ = regime_router.classify(
        spy_close=600, spy_ma_200=500, vix=15, macro_data=macro_stale_neutralized
    )
    assert regime == regime_router.REGIME_BULL_CALM


def test_macro_data_none_is_defensive_bear():
    regime, reason = regime_router.classify(
        spy_close=600, spy_ma_200=500, vix=15, macro_data=None
    )
    assert regime == regime_router.REGIME_BEAR
    assert "macro_data_unavailable" in reason


# active_strategies mapping

def test_bull_calm_activates_all_three():
    names = regime_router.active_strategies(regime_router.REGIME_BULL_CALM)
    assert set(names) == {
        "trend_leveraged_tqqq",
        "trend_following_spy_200d",
        "sector_momentum_top3_monthly",
    }


def test_bull_elevated_drops_leveraged_trend():
    names = regime_router.active_strategies(regime_router.REGIME_BULL_ELEVATED)
    assert "trend_leveraged_tqqq" not in names
    assert "trend_following_spy_200d" in names
    assert "sector_momentum_top3_monthly" in names


def test_bear_returns_empty():
    assert regime_router.active_strategies(regime_router.REGIME_BEAR) == []


def test_unknown_regime_returns_empty():
    """Defensive: an unknown label results in no active strategies."""
    assert regime_router.active_strategies("nonsense") == []
