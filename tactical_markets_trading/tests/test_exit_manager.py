"""Regression tests for src/exit_manager.py — primarily the yfinance MultiIndex bug.

The bug: `yf.download(single_ticker)` returns MultiIndex columns even for a single
ticker, so `float(data["Close"].iloc[0])` raises (iloc[0] is a Series, not a scalar).
The broad `except Exception` in `exit_position` silently swallowed it, causing every
prior benchmark capture to land as null. Fix: use `yf.Ticker().history()` which
returns flat columns.

This test pins the contract: get_return_pct must return a float (or None on empty),
not raise on the data-structure shape.
"""
import pandas as pd
import pytest

import exit_manager


class FakeTicker:
    def __init__(self, df):
        self._df = df

    def history(self, **kw):
        return self._df


def _make_history(closes):
    """Build a flat-columns DataFrame like yf.Ticker().history() returns."""
    return pd.DataFrame(
        {"Open": closes, "High": closes, "Low": closes, "Close": closes, "Volume": [0] * len(closes)},
        index=pd.date_range("2026-05-08", periods=len(closes)),
    )


def test_get_return_pct_returns_float_not_series(monkeypatch):
    """Regression for the MultiIndex bug — must yield a float without raising."""
    fake = FakeTicker(_make_history([100.0, 105.0]))
    monkeypatch.setattr(exit_manager.yf, "Ticker", lambda _t: fake)
    from datetime import datetime, timezone
    result = exit_manager.get_return_pct(
        "SPY",
        datetime(2026, 5, 8, tzinfo=timezone.utc),
        datetime(2026, 5, 9, tzinfo=timezone.utc),
    )
    assert isinstance(result, float)
    assert result == 5.0


def test_get_return_pct_returns_none_on_empty(monkeypatch):
    fake = FakeTicker(pd.DataFrame())
    monkeypatch.setattr(exit_manager.yf, "Ticker", lambda _t: fake)
    from datetime import datetime, timezone
    result = exit_manager.get_return_pct(
        "ZZZZ",
        datetime(2026, 5, 8, tzinfo=timezone.utc),
        datetime(2026, 5, 9, tzinfo=timezone.utc),
    )
    assert result is None


def test_get_return_pct_returns_none_on_single_row(monkeypatch):
    """Need at least 2 rows to compute a return."""
    fake = FakeTicker(_make_history([100.0]))
    monkeypatch.setattr(exit_manager.yf, "Ticker", lambda _t: fake)
    from datetime import datetime, timezone
    result = exit_manager.get_return_pct(
        "SPY",
        datetime(2026, 5, 8, tzinfo=timezone.utc),
        datetime(2026, 5, 9, tzinfo=timezone.utc),
    )
    assert result is None


def test_get_return_pct_rounds_to_4_decimals(monkeypatch):
    # (100.1234567 - 100.0) / 100.0 = 0.001234567 -> 0.1235% (4dp)
    fake = FakeTicker(_make_history([100.0, 100.1234567]))
    monkeypatch.setattr(exit_manager.yf, "Ticker", lambda _t: fake)
    from datetime import datetime, timezone
    result = exit_manager.get_return_pct(
        "SPY",
        datetime(2026, 5, 8, tzinfo=timezone.utc),
        datetime(2026, 5, 9, tzinfo=timezone.utc),
    )
    assert result == 0.1235


# Story 1a.4 + 1a.5: _cancel_stop_and_classify behavior


class FakeOrder:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class FakePosition:
    def __init__(self, qty):
        self.qty = qty


class CancelClient:
    """Configurable fake. Records whether cancel was called."""
    def __init__(self, cancel_raises=False, position_qty=None, stop_filled_order=None):
        self.cancel_raises = cancel_raises
        self.position_qty = position_qty
        self.stop_filled_order = stop_filled_order
        self.cancel_called_with = None

    def cancel_order_by_id(self, order_id):
        self.cancel_called_with = order_id
        if self.cancel_raises:
            raise RuntimeError("order already filled")
        return None

    def get_open_position(self, symbol):
        if self.position_qty is None:
            raise RuntimeError("404 position not found")
        return FakePosition(self.position_qty)

    def get_order_by_id(self, order_id):
        return self.stop_filled_order


def test_cancel_returns_scheduled_when_stop_cancels_cleanly():
    client = CancelClient(cancel_raises=False)
    record = {"stop_order_id": "stop-abc", "symbol": "XLK"}
    reason, fill = exit_manager._cancel_stop_and_classify(client, record)
    assert reason == "scheduled"
    assert fill is None
    assert client.cancel_called_with == "stop-abc"


def test_cancel_returns_no_stop_to_cancel_for_phase1_record():
    """Phase 1 entries have no stop_order_id; cancel must be skipped."""
    client = CancelClient()
    record = {"symbol": "XLK"}  # no stop_order_id
    reason, fill = exit_manager._cancel_stop_and_classify(client, record)
    assert reason == "no_stop_to_cancel"
    assert fill is None
    assert client.cancel_called_with is None  # never attempted


def test_cancel_returns_no_stop_to_cancel_for_null_stop_order_id():
    """Story 1a.2 fallback (stop_submission_failed) has stop_order_id=None."""
    client = CancelClient()
    record = {"symbol": "XLK", "stop_order_id": None, "stop_rule_used": "stop_submission_failed"}
    reason, fill = exit_manager._cancel_stop_and_classify(client, record)
    assert reason == "no_stop_to_cancel"
    assert fill is None
    assert client.cancel_called_with is None


def test_cancel_returns_stop_fired_when_cancel_raises_and_position_is_zero():
    """Stop already filled scenario: cancel raises, position is gone."""
    stop_filled = FakeOrder(
        filled_at="2026-05-19T15:00:00+00:00",
        filled_avg_price=167.50,
        filled_qty=58.1,
    )
    client = CancelClient(cancel_raises=True, position_qty=0.0, stop_filled_order=stop_filled)
    record = {"stop_order_id": "stop-abc", "symbol": "XLK"}
    reason, fill = exit_manager._cancel_stop_and_classify(client, record)
    assert reason == "stop_fired"
    assert fill["exit_order_id"] == "stop-abc"
    assert fill["exit_fill_price"] == 167.50
    assert fill["exit_fill_qty"] == 58.1


def test_cancel_returns_stop_fired_when_position_lookup_404s():
    """If cancel raises and position lookup also 404s, the position is gone — treat as stop_fired."""
    stop_filled = FakeOrder(
        filled_at="2026-05-19T15:00:00+00:00",
        filled_avg_price=167.50,
        filled_qty=58.1,
    )
    client = CancelClient(cancel_raises=True, position_qty=None, stop_filled_order=stop_filled)
    record = {"stop_order_id": "stop-abc", "symbol": "XLK"}
    reason, fill = exit_manager._cancel_stop_and_classify(client, record)
    assert reason == "stop_fired"
    assert fill["exit_order_id"] == "stop-abc"


def test_cancel_returns_stop_cancel_failed_when_position_still_held():
    """Cancel raised but position still held — proceed with market SELL, tag exit_reason."""
    client = CancelClient(cancel_raises=True, position_qty=58.1)
    record = {"stop_order_id": "stop-abc", "symbol": "XLK"}
    reason, fill = exit_manager._cancel_stop_and_classify(client, record)
    assert reason == "stop_cancel_failed"
    assert fill is None


# Market-hours guard

def test_run_exits_skips_when_market_closed(monkeypatch):
    """StartWhenAvailable wakeups must not submit pre-market SELLs."""
    monkeypatch.setattr(exit_manager, "_market_is_open", lambda: False)
    monkeypatch.setattr(exit_manager.reconciler, "reconcile", lambda dry_run: None)
    result = exit_manager.run_exits()
    assert result == 0


def test_run_exits_proceeds_when_market_open(monkeypatch):
    """When market is open and no trades are past due, run_exits returns 0 without raising."""
    monkeypatch.setattr(exit_manager, "_market_is_open", lambda: True)
    monkeypatch.setattr(exit_manager.reconciler, "reconcile", lambda dry_run: None)
    monkeypatch.setattr(exit_manager, "load_trades", lambda: [])
    result = exit_manager.run_exits()
    assert result == 0
