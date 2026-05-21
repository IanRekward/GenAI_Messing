"""Tests for src/order_builder.py — Story 1a.2 submit_stop behavior.

Pure unit tests with monkeypatched trading_client; no Alpaca calls.
"""
import pytest

import order_builder


class FakeOrder:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class HappyClient:
    """Returns a fake order on submit_order."""
    def __init__(self):
        self.last_request = None

    def submit_order(self, request):
        self.last_request = request
        return FakeOrder(id="stop-uuid-1234")


class RaisingClient:
    """Raises on submit_order — simulates Alpaca rejection."""
    def submit_order(self, request):
        raise RuntimeError("alpaca says no: stop_price below current market")


def test_submit_stop_happy_path(monkeypatch):
    client = HappyClient()
    monkeypatch.setattr(order_builder, "trading_client", lambda: client)

    result = order_builder.submit_stop(symbol="XLK", qty=58.1, fill_price=172.0)

    assert result["stop_order_id"] == "stop-uuid-1234"
    assert result["stop_price"] == 167.70  # 172 * 0.975 = 167.70
    assert result["stop_rule_used"] == "fixed_pct_2.5"
    assert result["stop_qty_covered"] == 58  # floored from 58.1
    # Verify the request shape — fractional qty must be floored (Alpaca rejects fractional GTC stops)
    from alpaca.trading.enums import OrderSide, TimeInForce
    assert client.last_request.symbol == "XLK"
    assert client.last_request.qty == 58  # whole shares
    assert client.last_request.side == OrderSide.SELL
    assert client.last_request.stop_price == 167.70
    assert client.last_request.time_in_force == TimeInForce.GTC


def test_submit_stop_fails_cleanly_when_qty_under_one_share(monkeypatch):
    client = HappyClient()
    monkeypatch.setattr(order_builder, "trading_client", lambda: client)
    result = order_builder.submit_stop(symbol="XLK", qty=0.5, fill_price=100.0)
    assert result["stop_order_id"] is None
    assert result["stop_rule_used"] == "stop_submission_failed"
    assert result["stop_qty_covered"] == 0
    assert "floors to 0" in result["stop_submission_error"]
    # Verify no order was submitted to Alpaca
    assert client.last_request is None


def test_submit_stop_returns_failure_metadata_on_alpaca_error(monkeypatch):
    monkeypatch.setattr(order_builder, "trading_client", lambda: RaisingClient())

    result = order_builder.submit_stop(symbol="XLK", qty=58.1, fill_price=172.0)

    assert result["stop_order_id"] is None
    assert result["stop_price"] == 167.70  # computed even when submission fails
    assert result["stop_rule_used"] == "stop_submission_failed"
    assert "alpaca says no" in result["stop_submission_error"]


def test_submit_stop_uses_compute_stop_price_default_pct(monkeypatch):
    """Regression: stop price must match risk.compute_stop_price(fill_price) exactly."""
    monkeypatch.setattr(order_builder, "trading_client", lambda: HappyClient())
    from risk import compute_stop_price

    fills = [100.0, 91.35, 250.0, 17.50]
    for fill in fills:
        result = order_builder.submit_stop("X", 10.0, fill)
        assert result["stop_price"] == compute_stop_price(fill)


# Story 1c.3: submit_order qty vs notional


class BuyClient:
    """Captures the MarketOrderRequest sent."""
    def __init__(self):
        self.last_request = None

    def submit_order(self, request):
        self.last_request = request
        return FakeOrder(id="buy-uuid", symbol=request.symbol, status="ACCEPTED", submitted_at="2026-05-20T13:35:00+00:00")


def test_submit_order_qty_based(monkeypatch):
    client = BuyClient()
    monkeypatch.setattr(order_builder, "trading_client", lambda: client)
    thesis = {"buy": "XLK", "sell": "XLE", "as_of": "2026-05-20T11:30:00+00:00"}
    result = order_builder.submit_order(thesis, qty=58.1)
    assert result["qty"] == 58.1
    assert result["notional"] is None
    assert client.last_request.qty == 58.1
    assert client.last_request.notional is None


def test_submit_order_notional_based(monkeypatch):
    client = BuyClient()
    monkeypatch.setattr(order_builder, "trading_client", lambda: client)
    thesis = {"buy": "XLK", "sell": "XLE", "as_of": "2026-05-20T11:30:00+00:00"}
    result = order_builder.submit_order(thesis, notional=10_000)
    assert result["notional"] == 10_000
    assert result["qty"] is None
    assert client.last_request.notional == 10_000
    assert client.last_request.qty is None


def test_submit_order_requires_exactly_one_of_qty_or_notional():
    thesis = {"buy": "XLK", "sell": "XLE", "as_of": "2026-05-20T11:30:00+00:00"}
    with pytest.raises(ValueError, match="exactly one"):
        order_builder.submit_order(thesis)  # neither
    with pytest.raises(ValueError, match="exactly one"):
        order_builder.submit_order(thesis, qty=10.0, notional=10_000)  # both


# Story 1c.3: get_estimated_entry_price


def test_get_estimated_entry_price_returns_latest_close(monkeypatch):
    import pandas as pd
    fake_history = pd.DataFrame(
        {"Open": [100.0, 101.0], "High": [102.0, 103.0], "Low": [99.0, 100.0], "Close": [101.5, 102.5], "Volume": [0, 0]},
        index=pd.date_range("2026-05-19", periods=2),
    )

    class FakeTicker:
        def history(self, **kw):
            return fake_history

    monkeypatch.setattr(order_builder.yf, "Ticker", lambda _: FakeTicker())
    assert order_builder.get_estimated_entry_price("XLK") == 102.5


def test_get_estimated_entry_price_raises_on_empty(monkeypatch):
    import pandas as pd

    class FakeTicker:
        def history(self, **kw):
            return pd.DataFrame()

    monkeypatch.setattr(order_builder.yf, "Ticker", lambda _: FakeTicker())
    with pytest.raises(RuntimeError, match="no data"):
        order_builder.get_estimated_entry_price("ZZZZ")
