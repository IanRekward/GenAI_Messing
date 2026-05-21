"""Regression tests for src/trade_logger.py — partial-fill bug + terminal-state handling.

The 2026-05-08 partial-fill bug: earlier `wait_for_fill` polled on `filled_at != None`
which Alpaca sets on the FIRST partial fill, not at `status == FILLED`. The fix is
to terminate only on OrderStatus.FILLED. These tests pin that contract.

The terminal-failure-fast contract: REJECTED/CANCELED/EXPIRED should raise immediately
rather than wait out the full 60s poll timeout.
"""
import pytest

import trade_logger
from alpaca.trading.enums import OrderStatus


class FakeOrder:
    def __init__(self, status, filled_at=None, filled_qty=0.0, filled_avg_price=None):
        self.status = status
        self.filled_at = filled_at
        self.filled_qty = filled_qty
        self.filled_avg_price = filled_avg_price


class SequenceClient:
    """Returns a sequence of order states on successive get_order_by_id calls."""
    def __init__(self, sequence):
        self._sequence = list(sequence)
        self._calls = 0

    def get_order_by_id(self, _order_id):
        if self._calls >= len(self._sequence):
            return self._sequence[-1]
        order = self._sequence[self._calls]
        self._calls += 1
        return order


def test_wait_for_fill_returns_on_filled(monkeypatch):
    seq = SequenceClient([
        FakeOrder(OrderStatus.FILLED, filled_at="2026-05-08T13:35:14+00:00", filled_qty=10.0, filled_avg_price=100.5),
    ])
    monkeypatch.setattr(trade_logger, "trading_client", lambda: seq)
    monkeypatch.setattr(trade_logger.time, "sleep", lambda _: None)

    result = trade_logger.wait_for_fill("order-id")

    assert result["fill_price"] == 100.5
    assert result["fill_qty"] == 10.0


def test_wait_for_fill_does_not_return_on_partial(monkeypatch):
    """Regression: must not terminate when filled_at is set but status is still PARTIALLY_FILLED."""
    seq = SequenceClient([
        FakeOrder(OrderStatus.PARTIALLY_FILLED, filled_at="2026-05-08T13:35:14+00:00", filled_qty=5.0, filled_avg_price=100.0),
        FakeOrder(OrderStatus.PARTIALLY_FILLED, filled_at="2026-05-08T13:35:15+00:00", filled_qty=8.0, filled_avg_price=100.2),
        FakeOrder(OrderStatus.FILLED, filled_at="2026-05-08T13:35:16+00:00", filled_qty=10.0, filled_avg_price=100.5),
    ])
    monkeypatch.setattr(trade_logger, "trading_client", lambda: seq)
    monkeypatch.setattr(trade_logger.time, "sleep", lambda _: None)

    result = trade_logger.wait_for_fill("order-id")

    # Must terminate only on the FILLED order (the 3rd), not the partial-fills
    assert result["fill_qty"] == 10.0
    assert result["fill_price"] == 100.5


def test_wait_for_fill_raises_fast_on_rejected(monkeypatch):
    seq = SequenceClient([FakeOrder(OrderStatus.REJECTED, filled_qty=0.0)])
    monkeypatch.setattr(trade_logger, "trading_client", lambda: seq)
    monkeypatch.setattr(trade_logger.time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="REJECTED"):
        trade_logger.wait_for_fill("order-id")


def test_wait_for_fill_raises_fast_on_canceled(monkeypatch):
    seq = SequenceClient([FakeOrder(OrderStatus.CANCELED, filled_qty=0.0)])
    monkeypatch.setattr(trade_logger, "trading_client", lambda: seq)
    monkeypatch.setattr(trade_logger.time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="CANCELED"):
        trade_logger.wait_for_fill("order-id")


def test_wait_for_fill_raises_fast_on_expired(monkeypatch):
    seq = SequenceClient([FakeOrder(OrderStatus.EXPIRED, filled_qty=0.0)])
    monkeypatch.setattr(trade_logger, "trading_client", lambda: seq)
    monkeypatch.setattr(trade_logger.time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="EXPIRED"):
        trade_logger.wait_for_fill("order-id")


# add_trading_days

def test_add_trading_days_skips_weekend():
    """Friday + 1 trading day = Monday (not Saturday)."""
    from datetime import datetime, timezone
    friday = datetime(2026, 5, 15, 13, 35, tzinfo=timezone.utc)
    result = trade_logger.add_trading_days(friday, 1)
    assert result.date().isoformat() == "2026-05-18"


def test_add_trading_days_2_days_from_thursday_lands_monday():
    """Thursday + 2 trading days = Monday (Thurs -> Fri -> Mon)."""
    from datetime import datetime, timezone
    thursday = datetime(2026, 5, 14, 13, 35, tzinfo=timezone.utc)
    result = trade_logger.add_trading_days(thursday, 2)
    assert result.date().isoformat() == "2026-05-18"


def test_add_trading_days_skips_memorial_day_2026():
    """Memorial Day 2026 = May 25 (Monday). Friday May 22 + 1 trading day = Tuesday May 26."""
    from datetime import datetime, timezone
    friday_before_memorial = datetime(2026, 5, 22, 13, 35, tzinfo=timezone.utc)
    result = trade_logger.add_trading_days(friday_before_memorial, 1)
    assert result.date().isoformat() == "2026-05-26"


# Story 1a.3: log_entry persists stop fields


def test_log_entry_persists_stop_fields_on_happy_path(monkeypatch, tmp_path):
    """log_entry must include stop_order_id, stop_price, stop_rule_used in the record."""
    import json
    from datetime import datetime, timezone
    monkeypatch.setattr(trade_logger, "TRADES_PATH", tmp_path / "trades.jsonl")
    import types
    monkeypatch.setattr(trade_logger, "time", types.SimpleNamespace(time=lambda: 0, sleep=lambda _: None))

    # Mock the BUY-fill polling
    fill_order = FakeOrder(OrderStatus.FILLED, filled_at="2026-05-20T13:35:14+00:00", filled_qty=58.1, filled_avg_price=172.0)
    monkeypatch.setattr(trade_logger, "trading_client", lambda: SequenceClient([fill_order]))

    # Mock submit_stop to return a happy result
    import order_builder
    monkeypatch.setattr(order_builder, "submit_stop", lambda symbol, qty, fill_price: {
        "stop_order_id": "stop-uuid-9876",
        "stop_price": 167.70,
        "stop_rule_used": "fixed_pct_2.5",
    })

    record = trade_logger.log_entry({
        "order_id": "buy-uuid",
        "symbol": "XLK",
        "sell_leg": "XLE",
        "notional": None,
        "qty": 58.1,
        "thesis_as_of": "2026-05-20T11:30:00+00:00",
    })

    assert record["stop_order_id"] == "stop-uuid-9876"
    assert record["stop_price"] == 167.70
    assert record["stop_rule_used"] == "fixed_pct_2.5"
    # Verify Phase 1 fields preserved
    assert record["symbol"] == "XLK"
    assert record["fill_price"] == 172.0
    assert record["fill_qty"] == 58.1

    # Verify persisted to disk
    with open(tmp_path / "trades.jsonl") as f:
        persisted = json.loads(f.readline())
    assert persisted["stop_order_id"] == "stop-uuid-9876"


def test_log_entry_persists_null_stop_on_submission_failure(monkeypatch, tmp_path):
    """When submit_stop returns stop_order_id=None, log_entry persists null and continues."""
    import json
    monkeypatch.setattr(trade_logger, "TRADES_PATH", tmp_path / "trades.jsonl")
    import types
    monkeypatch.setattr(trade_logger, "time", types.SimpleNamespace(time=lambda: 0, sleep=lambda _: None))

    fill_order = FakeOrder(OrderStatus.FILLED, filled_at="2026-05-20T13:35:14+00:00", filled_qty=58.1, filled_avg_price=172.0)
    monkeypatch.setattr(trade_logger, "trading_client", lambda: SequenceClient([fill_order]))

    import order_builder
    monkeypatch.setattr(order_builder, "submit_stop", lambda **kw: {
        "stop_order_id": None,
        "stop_price": 167.70,
        "stop_rule_used": "stop_submission_failed",
        "stop_submission_error": "alpaca rejected",
    })
    # Suppress pushover side-effect
    import pushover
    monkeypatch.setattr(pushover, "send", lambda *a, **kw: True)

    record = trade_logger.log_entry({
        "order_id": "buy-uuid",
        "symbol": "XLK",
        "sell_leg": "XLE",
        "notional": None,
        "qty": 58.1,
        "thesis_as_of": "2026-05-20T11:30:00+00:00",
    })

    assert record["stop_order_id"] is None
    assert record["stop_price"] == 167.70  # still recorded — useful for forensics
    assert record["stop_rule_used"] == "stop_submission_failed"
    # Position stays "open" — never auto-close on stop submission failure
    assert record["status"] == "open"
