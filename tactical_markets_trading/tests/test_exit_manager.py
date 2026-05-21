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


def test_cancel_returns_scheduled_for_phase1_record_without_attempting_cancel():
    """Phase 1 entries have no stop_order_id; cancel must be skipped, exit_reason='scheduled'.

    Per Story 1a.5 backward-compatibility AC: closed records all carry exit_reason='scheduled'
    when nothing unusual happened (cancel succeeded OR no stop existed). The "did a stop exist?"
    detail is preserved via the record's existing stop_order_id field.
    """
    client = CancelClient()
    record = {"symbol": "XLK"}  # no stop_order_id
    reason, fill = exit_manager._cancel_stop_and_classify(client, record)
    assert reason == "scheduled"
    assert fill is None
    assert client.cancel_called_with is None  # never attempted


def test_cancel_returns_scheduled_for_null_stop_order_id_without_attempting_cancel():
    """Story 1a.2 fallback (stop_submission_failed) has stop_order_id=None — same path."""
    client = CancelClient()
    record = {"symbol": "XLK", "stop_order_id": None, "stop_rule_used": "stop_submission_failed"}
    reason, fill = exit_manager._cancel_stop_and_classify(client, record)
    assert reason == "scheduled"
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
    monkeypatch.setattr(exit_manager.preflight, "check_exit", lambda: (True, "ok"))
    monkeypatch.setattr(exit_manager, "_market_is_open", lambda: False)
    monkeypatch.setattr(exit_manager.reconciler, "reconcile", lambda dry_run: None)
    result = exit_manager.run_exits()
    assert result == 0


def test_run_exits_proceeds_when_market_open(monkeypatch):
    """When market is open and no trades are past due, run_exits returns 0 without raising."""
    monkeypatch.setattr(exit_manager.preflight, "check_exit", lambda: (True, "ok"))
    monkeypatch.setattr(exit_manager, "_market_is_open", lambda: True)
    monkeypatch.setattr(exit_manager.reconciler, "reconcile", lambda dry_run: None)
    monkeypatch.setattr(exit_manager, "load_trades", lambda: [])
    result = exit_manager.run_exits()
    assert result == 0


# Story 2.5: wash-sale metadata

def test_wash_sale_loss_with_no_prior_lots():
    """Losing close with no other entries for the symbol — potential_wash_sale=False."""
    record = {"trade_id": "t1", "symbol": "XLK", "fill_price": 100.0, "fill_qty": 10.0}
    all_records = [record]
    result = exit_manager._compute_wash_sale(record, all_records, "2026-05-20T13:40:00+00:00", pnl_dollars=-50.0)
    assert result["is_loss"] is True
    assert result["loss_amount"] == -50.0
    assert result["lots_within_30d"] == []
    assert result["potential_wash_sale"] is False


def test_wash_sale_loss_with_prior_lot_within_30d():
    """Losing close + same symbol entered 10 days before — potential_wash_sale=True."""
    record = {"trade_id": "t2", "symbol": "XLK", "fill_price": 100.0, "fill_qty": 10.0,
              "entry_time": "2026-05-20T13:35:00+00:00"}
    prior = {"trade_id": "t1", "symbol": "XLK", "fill_price": 105.0, "fill_qty": 5.0,
             "entry_time": "2026-05-10T13:35:00+00:00", "status": "closed"}
    all_records = [prior, record]
    result = exit_manager._compute_wash_sale(record, all_records, "2026-05-22T13:40:00+00:00", pnl_dollars=-50.0)
    assert result["potential_wash_sale"] is True
    assert len(result["lots_within_30d"]) == 1
    assert result["lots_within_30d"][0]["trade_id"] == "t1"


def test_wash_sale_loss_excludes_self():
    """The exiting trade itself must not appear in its own lots_within_30d."""
    record = {"trade_id": "t1", "symbol": "XLK", "fill_price": 100.0, "fill_qty": 10.0,
              "entry_time": "2026-05-20T13:35:00+00:00"}
    all_records = [record]
    result = exit_manager._compute_wash_sale(record, all_records, "2026-05-22T13:40:00+00:00", pnl_dollars=-50.0)
    assert result["lots_within_30d"] == []


def test_wash_sale_loss_excludes_other_symbols():
    record = {"trade_id": "t2", "symbol": "XLK", "fill_price": 100.0, "fill_qty": 10.0,
              "entry_time": "2026-05-20T13:35:00+00:00"}
    prior = {"trade_id": "t1", "symbol": "XLE", "fill_price": 50.0, "fill_qty": 5.0,
             "entry_time": "2026-05-10T13:35:00+00:00", "status": "closed"}
    all_records = [prior, record]
    result = exit_manager._compute_wash_sale(record, all_records, "2026-05-22T13:40:00+00:00", pnl_dollars=-50.0)
    assert result["potential_wash_sale"] is False  # XLE doesn't count


def test_wash_sale_loss_excludes_lots_outside_30d_window():
    record = {"trade_id": "t2", "symbol": "XLK", "fill_price": 100.0, "fill_qty": 10.0,
              "entry_time": "2026-05-20T13:35:00+00:00"}
    prior = {"trade_id": "t1", "symbol": "XLK", "fill_price": 105.0, "fill_qty": 5.0,
             "entry_time": "2026-03-01T13:35:00+00:00", "status": "closed"}  # 80+ days before
    all_records = [prior, record]
    result = exit_manager._compute_wash_sale(record, all_records, "2026-05-22T13:40:00+00:00", pnl_dollars=-50.0)
    assert result["potential_wash_sale"] is False


def test_wash_sale_winner_records_uniform_shape():
    """Winning closes record wash_sale={is_loss:false, loss_amount:0, lots:[], potential:false}."""
    record = {"trade_id": "t1", "symbol": "XLK", "fill_price": 100.0, "fill_qty": 10.0}
    result = exit_manager._compute_wash_sale(record, [record], "2026-05-22T13:40:00+00:00", pnl_dollars=50.0)
    assert result["is_loss"] is False
    assert result["loss_amount"] == 0
    assert result["lots_within_30d"] == []
    assert result["potential_wash_sale"] is False


def test_run_exits_aborts_on_preflight_failure(monkeypatch):
    """Story 1b.5: preflight failure -> Pushover + sys.exit(1) before reconciler runs."""
    monkeypatch.setattr(exit_manager.preflight, "check_exit", lambda: (False, "env_key_missing: ALPACA_API_KEY"))
    monkeypatch.setattr(exit_manager.pushover, "send", lambda *a, **kw: True)
    # If preflight worked, reconciler would be called. Patching it to raise lets us prove
    # we exited BEFORE reaching reconciler (we'd hit the raise otherwise).
    monkeypatch.setattr(exit_manager.reconciler, "reconcile", lambda dry_run: (_ for _ in ()).throw(AssertionError("should not reach reconciler")))
    with pytest.raises(SystemExit) as exc:
        exit_manager.run_exits()
    assert exc.value.code == 1
