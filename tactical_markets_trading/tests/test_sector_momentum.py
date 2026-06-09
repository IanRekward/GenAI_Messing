"""Tests for src/strategies/sector_momentum_monthly.py — Phase 3.2 strategy."""
import pytest

from strategies.sector_momentum_monthly import (
    LOOKBACK_DAYS,
    SECTOR_TICKERS,
    TOP_N,
    SectorMomentumMonthlyStrategy,
)


@pytest.fixture
def strategy():
    return SectorMomentumMonthlyStrategy(allocation_pct=0.33)


def _make_history(returns: dict[str, float]) -> dict[str, list[float]]:
    """Build a per-sector close history with LOOKBACK_DAYS+1 entries such that
    end/start - 1 == returns[sym]. Filler points are linearly interpolated."""
    hist = {}
    for sym in SECTOR_TICKERS:
        r = returns.get(sym, 0.0)
        start = 100.0
        end = start * (1.0 + r)
        # Linear interp over LOOKBACK_DAYS+1 points
        step = (end - start) / LOOKBACK_DAYS
        hist[sym] = [start + step * i for i in range(LOOKBACK_DAYS + 1)]
    return hist


def _market_data(today: str, returns: dict[str, float], prices: dict[str, float] | None = None) -> dict:
    history = _make_history(returns)
    prices = prices or {sym: history[sym][-1] for sym in SECTOR_TICKERS}
    return {
        "today": today,
        "sector_close_history": history,
        "sector_close_today": prices,
    }


def test_first_run_buys_top_three(strategy):
    """First call (no last_rebalance_month) — should rank and buy top-3."""
    returns = {"XLK": 0.20, "XLF": 0.15, "XLE": 0.10,
               "XLY": 0.05, "XLP": 0.04, "XLV": 0.03, "XLI": 0.02, "XLU": 0.01, "XLB": 0.0}
    md = _market_data("2026-06-01", returns)
    state = {}
    actions = strategy.decide_actions(state, md, account_value=100_000, current_positions={})
    assert len(actions) == TOP_N
    bought = {a.symbol for a in actions}
    assert bought == {"XLK", "XLF", "XLE"}
    for a in actions:
        assert a.action == "buy"
        assert a.qty >= 1
    assert state["last_rebalance_month"] == "2026-06"
    assert set(state["current_holdings"]) == {"XLK", "XLF", "XLE"}


def test_same_month_no_action(strategy):
    """Second call in the same month is a no-op."""
    state = {"last_rebalance_month": "2026-06", "current_holdings": ["XLK", "XLF", "XLE"]}
    returns = {sym: 0.0 for sym in SECTOR_TICKERS}
    actions = strategy.decide_actions(state, _market_data("2026-06-15", returns),
                                       account_value=100_000, current_positions={})
    assert actions == []


def test_rebalance_swaps_holdings(strategy):
    """New month, new top-3 — sells dropouts, buys new entrants."""
    # Previous month held XLK, XLF, XLE. This month XLV, XLU surge past XLF and XLE.
    state = {"last_rebalance_month": "2026-06", "current_holdings": ["XLK", "XLF", "XLE"]}
    returns = {"XLK": 0.30, "XLV": 0.25, "XLU": 0.20,
               "XLF": 0.05, "XLE": 0.04, "XLY": 0.03, "XLP": 0.02, "XLI": 0.01, "XLB": 0.0}
    actions = strategy.decide_actions(state, _market_data("2026-07-01", returns),
                                       account_value=100_000, current_positions={})
    sells = [a for a in actions if a.action == "sell"]
    buys = [a for a in actions if a.action == "buy"]
    assert {s.symbol for s in sells} == {"XLF", "XLE"}
    assert {b.symbol for b in buys} == {"XLV", "XLU"}
    # Sells come first so cash is freed before buys
    sell_idxs = [i for i, a in enumerate(actions) if a.action == "sell"]
    buy_idxs = [i for i, a in enumerate(actions) if a.action == "buy"]
    assert max(sell_idxs) < min(buy_idxs)
    # State updated
    assert state["last_rebalance_month"] == "2026-07"
    assert set(state["current_holdings"]) == {"XLK", "XLV", "XLU"}


def test_no_change_in_top_three(strategy):
    """Same top-3 across months — no buys, no sells, but state still advances."""
    state = {"last_rebalance_month": "2026-06", "current_holdings": ["XLK", "XLF", "XLE"]}
    returns = {"XLK": 0.30, "XLF": 0.25, "XLE": 0.20,
               "XLV": 0.10, "XLU": 0.05, "XLY": 0.03, "XLP": 0.02, "XLI": 0.01, "XLB": 0.0}
    actions = strategy.decide_actions(state, _market_data("2026-07-01", returns),
                                       account_value=100_000, current_positions={})
    assert actions == []
    assert state["last_rebalance_month"] == "2026-07"
    assert set(state["current_holdings"]) == {"XLK", "XLF", "XLE"}


def test_insufficient_history_skips_rebalance(strategy):
    """If a sector has <LOOKBACK_DAYS+1 closes, it's excluded from ranking.
    If too few sectors qualify, the whole rebalance skips."""
    history = {sym: [100.0] * 10 for sym in SECTOR_TICKERS}  # only 10 days
    md = {
        "today": "2026-06-01",
        "sector_close_history": history,
        "sector_close_today": {sym: 100.0 for sym in SECTOR_TICKERS},
    }
    state = {}
    actions = strategy.decide_actions(state, md, account_value=100_000, current_positions={})
    assert actions == []
    # State NOT advanced — we'll try again next call
    assert state.get("last_rebalance_month") is None


def test_per_leg_notional_split_three_ways(strategy):
    """Each buy should target ~ allocation_pct * account / TOP_N."""
    returns = {"XLK": 0.20, "XLF": 0.15, "XLE": 0.10,
               "XLY": 0.05, "XLP": 0.04, "XLV": 0.03, "XLI": 0.02, "XLU": 0.01, "XLB": 0.0}
    # Account 99,000 -> 33% = 32,670; / 3 = 10,890 per leg
    # Sector prices ~ 100, 100, 100 (no growth in history start) — at end_close prices
    md = _market_data("2026-06-01", returns)
    state = {}
    actions = strategy.decide_actions(state, md, account_value=99_000, current_positions={})
    for a in actions:
        # Each leg: int(10_890 / end_price) — prices vary by return %, so qty varies
        assert a.qty >= 80  # ballpark, gives margin
    # Total notional ~ allocation_pct * account
    total = sum(a.qty * md["sector_close_today"][a.symbol] for a in actions)
    assert 0.30 * 99_000 <= total <= 0.33 * 99_000


def test_decide_falls_back_to_hold_on_non_rebalance(strategy):
    """The single-Decision decide() wrapper returns hold when no rebalance is due."""
    state = {"last_rebalance_month": "2026-06", "current_holdings": ["XLK", "XLF", "XLE"]}
    returns = {sym: 0.0 for sym in SECTOR_TICKERS}
    d = strategy.decide(state, _market_data("2026-06-15", returns),
                        account_value=100_000, current_positions={})
    assert d.action == "hold"
    assert d.trigger == "no_signal"
