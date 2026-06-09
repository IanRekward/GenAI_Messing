"""Tests for src/strategies/spy_trend.py — Phase 3.2 strategy."""
import pytest

from strategies.spy_trend import MA_WINDOW, TICKER, SpyTrendStrategy


@pytest.fixture
def strategy():
    return SpyTrendStrategy(allocation_pct=0.33)


@pytest.fixture
def trend_on_data():
    return {"spy_close_today": 600.0, "spy_ma_200_today": 580.0}


@pytest.fixture
def trend_off_data():
    return {"spy_close_today": 580.0, "spy_ma_200_today": 600.0}


def test_first_run_with_trend_on_enters(strategy, trend_on_data):
    state = {}
    d = strategy.decide(state, trend_on_data, account_value=100_000, current_positions={})
    assert d.action == "buy"
    assert d.symbol == "SPY"
    assert d.qty == 55  # int(0.33 * 100000 / 600) = 55
    assert d.trigger == "trend_entry"
    assert state["in_position"] is True
    assert state["entry_price"] == 600.0


def test_first_run_with_trend_off_holds(strategy, trend_off_data):
    state = {}
    d = strategy.decide(state, trend_off_data, account_value=100_000, current_positions={})
    assert d.action == "hold"
    assert d.trigger == "no_signal"
    assert state.get("in_position", False) is False


def test_in_position_trend_on_holds(strategy, trend_on_data):
    state = {"in_position": True, "entry_price": 590.0}
    d = strategy.decide(state, trend_on_data, account_value=100_000,
                        current_positions={TICKER: 30000.0})
    assert d.action == "hold"
    assert d.trigger == "already_held"


def test_in_position_trend_off_sells(strategy, trend_off_data):
    state = {"in_position": True, "entry_price": 590.0}
    d = strategy.decide(state, trend_off_data, account_value=100_000,
                        current_positions={TICKER: 25000.0})
    assert d.action == "sell"
    assert d.symbol == "SPY"
    assert d.trigger == "trend_exit"
    assert state["in_position"] is False


def test_drift_defense_clears_state_when_alpaca_empty(strategy, trend_on_data):
    """Local says in_position but Alpaca has nothing — clear state, re-enter."""
    state = {"in_position": True, "entry_price": 590.0}
    d = strategy.decide(state, trend_on_data, account_value=100_000,
                        current_positions={})  # no SPY on Alpaca
    # State was cleared, then re-entered fresh
    assert d.action == "buy"
    assert state["in_position"] is True
    assert state["entry_price"] == 600.0  # the new entry, not the stale 590


def test_no_re_entry_cooldown(strategy, trend_on_data):
    """Unlike leveraged_trend, spy_trend has no cooldown. After a trend-off exit
    and trend back on, it re-enters cleanly on the next fire."""
    state = {"in_position": True, "entry_price": 590.0}
    # Exit on trend-off
    d1 = strategy.decide(state, {"spy_close_today": 580, "spy_ma_200_today": 600},
                          account_value=100_000, current_positions={TICKER: 25000})
    assert d1.action == "sell"
    # Trend back on next fire -> immediate buy (no cooldown flag check)
    d2 = strategy.decide(state, trend_on_data, account_value=100_000, current_positions={})
    assert d2.action == "buy"


def test_insufficient_sizing_holds(strategy, trend_on_data):
    d = strategy.decide(state={}, market_data={"spy_close_today": 100_000.0, "spy_ma_200_today": 1.0},
                        account_value=100, current_positions={})
    assert d.action == "hold"
    assert "insufficient sizing" in d.reason


def test_decide_actions_default_wraps_decide(strategy, trend_on_data):
    """Base class default decide_actions should wrap decide() in a single-element list."""
    actions = strategy.decide_actions({}, trend_on_data, account_value=100_000, current_positions={})
    assert len(actions) == 1
    assert actions[0].action == "buy"
