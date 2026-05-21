"""Tests for src/strategies/leveraged_trend.py — Phase 3.1 strategy.

The strategy's decide() is mostly pure (state in, state out, no I/O). Test the
full decision tree: entry, hold, trend exit, stop fire, cooldown, drift defense.
"""
from datetime import datetime, timezone

import pytest

from strategies.leveraged_trend import (
    LEVERAGED_TICKER,
    MA_WINDOW,
    SIGNAL_TICKER,
    TRAILING_STOP_PCT,
    LeveragedTrendStrategy,
)


@pytest.fixture
def strategy():
    return LeveragedTrendStrategy(allocation_pct=0.33)


@pytest.fixture
def trend_on_data():
    """SPY clearly above MA — trend on."""
    return {
        "spy_close_today": 600.0,
        "spy_ma_today": 580.0,
        "tqqq_close_today": 100.0,
    }


@pytest.fixture
def trend_off_data():
    """SPY clearly below MA — trend off."""
    return {
        "spy_close_today": 580.0,
        "spy_ma_today": 600.0,
        "tqqq_close_today": 100.0,
    }


# --- Entry path ---

def test_first_run_with_trend_on_enters(strategy, trend_on_data):
    state = {}
    decision = strategy.decide(state, trend_on_data, account_value=100_000, current_positions={})
    assert decision.action == "buy"
    assert decision.symbol == "TQQQ"
    assert decision.qty == 330  # int(0.33 * 100000 / 100.0) = 330
    assert decision.trigger == "trend_entry"
    # State should now reflect being in position
    assert state["in_position"] is True
    assert state["entry_price"] == 100.0
    assert state["position_peak_price"] == 100.0
    assert state["stopped_out"] is False
    assert "entry_time" in state


def test_first_run_with_trend_off_holds(strategy, trend_off_data):
    state = {}
    decision = strategy.decide(state, trend_off_data, account_value=100_000, current_positions={})
    assert decision.action == "hold"
    assert decision.trigger == "no_signal"
    assert state.get("in_position", False) is False


def test_first_run_insufficient_sizing_holds(strategy, trend_on_data):
    """If allocation fraction × account / price < 1 share, can't enter."""
    decision = strategy.decide(state={}, market_data={**trend_on_data, "tqqq_close_today": 100_000.0},
                                account_value=100, current_positions={})
    assert decision.action == "hold"
    assert decision.trigger == "no_signal"
    assert "insufficient sizing" in decision.reason


# --- Hold path ---

def test_in_position_trend_on_holds(strategy, trend_on_data):
    state = {"in_position": True, "position_peak_price": 100.0, "stopped_out": False}
    decision = strategy.decide(state, trend_on_data, account_value=100_000,
                                current_positions={"TQQQ": 33_000})
    assert decision.action == "hold"
    assert decision.trigger == "already_held"


def test_in_position_new_high_updates_peak(strategy, trend_on_data):
    state = {"in_position": True, "position_peak_price": 100.0, "stopped_out": False}
    md = {**trend_on_data, "tqqq_close_today": 110.0}
    decision = strategy.decide(state, md, account_value=100_000,
                                current_positions={"TQQQ": 33_000})
    assert decision.action == "hold"
    assert state["position_peak_price"] == 110.0  # peak ratcheted up


def test_in_position_below_peak_but_above_stop_holds(strategy, trend_on_data):
    state = {"in_position": True, "position_peak_price": 100.0, "stopped_out": False}
    # 3% below peak — within 5% stop, still holding
    md = {**trend_on_data, "tqqq_close_today": 97.0}
    decision = strategy.decide(state, md, account_value=100_000,
                                current_positions={"TQQQ": 32_010})
    assert decision.action == "hold"
    assert state["position_peak_price"] == 100.0  # peak unchanged


# --- Exit paths ---

def test_trailing_stop_fires_at_threshold(strategy, trend_on_data):
    state = {"in_position": True, "position_peak_price": 100.0, "stopped_out": False}
    # Exactly at the stop (peak * 0.95 = 95.0)
    md = {**trend_on_data, "tqqq_close_today": 95.0}
    decision = strategy.decide(state, md, account_value=100_000,
                                current_positions={"TQQQ": 31_350})
    assert decision.action == "sell"
    assert decision.symbol == "TQQQ"
    assert decision.trigger == "stop_fired"
    assert state["in_position"] is False
    assert state["stopped_out"] is True  # cooldown engaged
    assert state["position_peak_price"] is None


def test_trailing_stop_fires_below_threshold(strategy, trend_on_data):
    state = {"in_position": True, "position_peak_price": 100.0, "stopped_out": False}
    md = {**trend_on_data, "tqqq_close_today": 90.0}  # 10% below peak
    decision = strategy.decide(state, md, account_value=100_000,
                                current_positions={"TQQQ": 29_700})
    assert decision.action == "sell"
    assert decision.trigger == "stop_fired"


def test_trend_off_exits_in_position(strategy, trend_off_data):
    state = {"in_position": True, "position_peak_price": 100.0, "stopped_out": False}
    decision = strategy.decide(state, trend_off_data, account_value=100_000,
                                current_positions={"TQQQ": 33_000})
    assert decision.action == "sell"
    assert decision.trigger == "trend_exit"
    assert state["in_position"] is False
    assert state["stopped_out"] is False  # trend-off exit resets cooldown


# --- Cooldown ---

def test_cooldown_blocks_re_entry_when_trend_still_on(strategy, trend_on_data):
    """After stop-out, even if trend signal is still on, no re-entry until trend cycles."""
    state = {"in_position": False, "stopped_out": True}
    decision = strategy.decide(state, trend_on_data, account_value=100_000,
                                current_positions={})
    assert decision.action == "hold"
    assert decision.trigger == "cooldown"
    assert state["stopped_out"] is True  # still in cooldown


def test_cooldown_clears_when_trend_turns_off_while_out_of_position(strategy, trend_off_data):
    """After a stop-out, cooldown clears when trend signal goes off — re-entry path is
    then clean once trend comes back on. This is the fixed behavior (was a bug)."""
    state = {"in_position": False, "stopped_out": True}
    # Trend off while in cooldown: state should reset
    decision = strategy.decide(state, trend_off_data, account_value=100_000,
                                current_positions={})
    assert decision.action == "hold"
    assert decision.trigger == "no_signal"
    assert state["stopped_out"] is False  # cleared
    assert "cooldown cleared" in decision.reason


def test_cooldown_full_cycle_stop_fire_then_trend_off_then_trend_on_enters_clean(strategy):
    """Stop fires -> cooldown -> trend goes off (clears cooldown) -> trend comes back on -> clean re-entry."""
    state = {"in_position": True, "position_peak_price": 100.0, "stopped_out": False}
    # Day 1: stop fires
    d1 = strategy.decide(state, {"spy_close_today": 600, "spy_ma_today": 580, "tqqq_close_today": 90},
                          account_value=100_000, current_positions={"TQQQ": 33_000})
    assert d1.trigger == "stop_fired"
    assert state["stopped_out"] is True

    # Day 2: still in cooldown, trend on but blocked
    d2 = strategy.decide(state, {"spy_close_today": 600, "spy_ma_today": 580, "tqqq_close_today": 100},
                          account_value=100_000, current_positions={})
    assert d2.trigger == "cooldown"

    # Day 3: trend turns off, cooldown should clear
    d3 = strategy.decide(state, {"spy_close_today": 580, "spy_ma_today": 600, "tqqq_close_today": 95},
                          account_value=100_000, current_positions={})
    assert d3.trigger == "no_signal"
    assert state["stopped_out"] is False

    # Day 4: trend back on — clean re-entry
    d4 = strategy.decide(state, {"spy_close_today": 600, "spy_ma_today": 580, "tqqq_close_today": 100},
                          account_value=100_000, current_positions={})
    assert d4.action == "buy"
    assert d4.trigger == "trend_entry"


# --- Drift defense ---

def test_drift_defense_when_local_says_in_position_but_alpaca_empty(strategy, trend_off_data):
    """Local state says in_position but Alpaca shows no TQQQ — trust Alpaca, clear local."""
    state = {"in_position": True, "position_peak_price": 100.0, "stopped_out": False,
             "entry_price": 100.0, "entry_time": "2026-05-21T13:35:00+00:00"}
    decision = strategy.decide(state, trend_off_data, account_value=100_000,
                                current_positions={})  # no TQQQ on Alpaca
    # State should be cleared
    assert state["in_position"] is False
    assert state["position_peak_price"] is None
    # Decision should reflect the cleared-state path (trend off → no_signal)
    assert decision.action == "hold"
    assert decision.trigger == "no_signal"


# --- Idempotency ---

def test_hold_decision_idempotent(strategy, trend_on_data):
    """Calling decide twice on same inputs produces same hold decision + same trading-relevant state."""
    state1 = {"in_position": True, "position_peak_price": 110.0, "stopped_out": False}
    state2 = {"in_position": True, "position_peak_price": 110.0, "stopped_out": False}
    # tqqq_close=106 is between stop ($104.5 = 110 * 0.95) and peak; should hold
    md = {**trend_on_data, "tqqq_close_today": 106.0}
    d1 = strategy.decide(state1, md, 100_000, {"TQQQ": 35_000})
    d2 = strategy.decide(state2, md, 100_000, {"TQQQ": 35_000})
    assert d1.action == d2.action == "hold"
    # Compare trading-relevant fields (last_decision_at is a timestamp that always advances)
    for k in ("in_position", "position_peak_price", "stopped_out"):
        assert state1.get(k) == state2.get(k), f"divergence on {k}"
    # peak unchanged because tqqq_close 106 < peak 110
    assert state1["position_peak_price"] == 110.0
