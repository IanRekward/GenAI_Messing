"""Tests for src/reconciler.py — drift detection between trades.jsonl and Alpaca.

Mocks the Alpaca client; uses tmp_path for trades.jsonl. No network.
"""
import json
from datetime import datetime, timezone

import pytest

import reconciler
from alpaca.trading.enums import OrderStatus


class FakeOrder:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class FakePosition:
    def __init__(self, symbol, qty):
        self.symbol = symbol
        self.qty = qty


class FakeAlpacaClient:
    def __init__(self, positions=None, orders=None, open_orders=None):
        self._positions = positions or []
        self._orders = orders or []
        self._open_orders = open_orders or []

    def get_all_positions(self):
        return self._positions

    def get_orders(self, request):
        from alpaca.trading.enums import QueryOrderStatus
        if getattr(request, "status", None) == QueryOrderStatus.OPEN:
            return list(self._open_orders)
        out = []
        for o in self._orders:
            if request.symbols and o.symbol not in request.symbols:
                continue
            if request.side and o.side != request.side:
                continue
            if request.status and o.status != OrderStatus.FILLED:
                continue
            out.append(o)
        return out


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    trades = tmp_path / "trades.jsonl"
    log = tmp_path / "reconciler_log.jsonl"
    monkeypatch.setattr(reconciler, "TRADES_PATH", trades)
    monkeypatch.setattr(reconciler, "RECONCILER_LOG", log)
    return trades, log


def _write_records(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _open_record(trade_id="t1", symbol="XLK", qty=10.0, price=100.0, entry_time="2026-05-14 13:35:00+00:00"):
    return {
        "trade_id": trade_id,
        "order_id": f"order-{trade_id}",
        "symbol": symbol,
        "sell_leg": "XLE",
        "notional": 10000,
        "thesis_as_of": "2026-05-14T11:30:00+00:00",
        "entry_time": entry_time,
        "fill_price": price,
        "fill_qty": qty,
        "exit_time_planned": "2026-05-18 13:35:00+00:00",
        "status": "open",
    }


def test_no_drift_when_local_and_alpaca_match(isolated_paths, monkeypatch):
    trades, _ = isolated_paths
    _write_records(trades, [_open_record(symbol="XLK", qty=10.0)])
    client = FakeAlpacaClient(positions=[FakePosition("XLK", 10.0)])
    monkeypatch.setattr(reconciler, "trading_client", lambda: client)

    summary = reconciler.reconcile(dry_run=True)

    assert summary["actions"] == []
    assert summary["local_open_count"] == 1
    assert summary["alpaca_position_count"] == 1


def test_backfills_close_when_local_open_but_alpaca_has_no_position(isolated_paths, monkeypatch):
    trades, _ = isolated_paths
    _write_records(trades, [_open_record(trade_id="t1", symbol="XLK", qty=10.0, price=100.0)])
    matching_sell = FakeOrder(
        id="sell-uuid",
        symbol="XLK",
        side=__import__("alpaca.trading.enums", fromlist=["OrderSide"]).OrderSide.SELL,
        status=OrderStatus.FILLED,
        qty=10.0,
        filled_qty=10.0,
        filled_avg_price=105.0,
        filled_at="2026-05-18 13:40:00+00:00",
    )
    client = FakeAlpacaClient(positions=[], orders=[matching_sell])
    monkeypatch.setattr(reconciler, "trading_client", lambda: client)

    summary = reconciler.reconcile(dry_run=False)

    assert len(summary["actions"]) == 1
    a = summary["actions"][0]
    assert a["type"] == "backfilled_close"
    assert a["symbol"] == "XLK"
    assert a["pnl_dollars"] == 50.0  # (105-100)*10
    assert a["pnl_pct"] == 5.0

    # Verify persistence
    with open(trades) as f:
        records = [json.loads(line) for line in f]
    assert records[0]["status"] == "closed"
    assert records[0]["reconciled"] is True
    assert records[0]["exit_fill_price"] == 105.0


def test_unresolvable_drift_when_no_matching_sell_found(isolated_paths, monkeypatch):
    trades, _ = isolated_paths
    _write_records(trades, [_open_record(trade_id="t1", symbol="XLK", qty=10.0)])
    # Alpaca has no XLK position AND no SELL in history
    client = FakeAlpacaClient(positions=[], orders=[])
    monkeypatch.setattr(reconciler, "trading_client", lambda: client)
    # Suppress pushover side-effect in the alert path
    monkeypatch.setattr(reconciler.pushover, "send", lambda *a, **kw: True)

    summary = reconciler.reconcile(dry_run=False)

    assert len(summary["actions"]) == 1
    a = summary["actions"][0]
    assert a["type"] == "drift_unresolvable"
    assert a["symbol"] == "XLK"

    # The record should remain "open" since we couldn't resolve
    with open(trades) as f:
        records = [json.loads(line) for line in f]
    assert records[0]["status"] == "open"


def test_untracked_alpaca_position_alerts_does_not_synthesize_record(isolated_paths, monkeypatch):
    trades, _ = isolated_paths
    _write_records(trades, [])  # no local records
    client = FakeAlpacaClient(positions=[FakePosition("XLE", 169.89)], orders=[])
    monkeypatch.setattr(reconciler, "trading_client", lambda: client)
    monkeypatch.setattr(reconciler.pushover, "send", lambda *a, **kw: True)

    summary = reconciler.reconcile(dry_run=False)

    assert len(summary["actions"]) == 1
    a = summary["actions"][0]
    assert a["type"] == "untracked_alpaca_position"
    assert a["symbol"] == "XLE"
    assert a["alpaca_qty"] == 169.89
    assert a["resolution"] == "manual_investigation_required"

    # Local file must NOT have been modified — no synthetic records
    with open(trades) as f:
        records = [json.loads(line) for line in f]
    assert records == []


# Story 2.1: report() — read-only drift detection with canonical event types


def test_report_returns_empty_when_no_drift(isolated_paths, monkeypatch):
    trades, _ = isolated_paths
    _write_records(trades, [_open_record(symbol="XLK", qty=10.0)])
    client = FakeAlpacaClient(positions=[FakePosition("XLK", 10.0)], open_orders=[])
    monkeypatch.setattr(reconciler, "trading_client", lambda: client)
    events = reconciler.report()
    assert events == []


def test_report_orphan_position(isolated_paths, monkeypatch):
    """Alpaca holds XLE 100 shares, local has nothing for XLE."""
    trades, _ = isolated_paths
    _write_records(trades, [])
    client = FakeAlpacaClient(positions=[FakePosition("XLE", 100.0)], open_orders=[])
    monkeypatch.setattr(reconciler, "trading_client", lambda: client)
    events = reconciler.report()
    assert len(events) == 1
    assert events[0]["type"] == "orphan_position"
    assert events[0]["symbol"] == "XLE"
    assert events[0]["orphan_qty"] == 100.0


def test_report_missing_position(isolated_paths, monkeypatch):
    """Local has XLK open 10 shares, Alpaca holds none."""
    trades, _ = isolated_paths
    _write_records(trades, [_open_record(trade_id="t1", symbol="XLK", qty=10.0)])
    client = FakeAlpacaClient(positions=[], open_orders=[])
    monkeypatch.setattr(reconciler, "trading_client", lambda: client)
    events = reconciler.report()
    assert any(e["type"] == "missing_position" and e["symbol"] == "XLK" for e in events)


def test_report_orphan_open_order(isolated_paths, monkeypatch):
    """Alpaca has an open order whose id matches no local stop_order_id."""
    trades, _ = isolated_paths
    _write_records(trades, [])
    from alpaca.trading.enums import OrderSide as OS
    open_order = FakeOrder(id="stranger-stop", symbol="XLK", side=OS.SELL, qty=10.0, order_type="STOP")
    client = FakeAlpacaClient(positions=[], open_orders=[open_order])
    monkeypatch.setattr(reconciler, "trading_client", lambda: client)
    events = reconciler.report()
    assert any(e["type"] == "orphan_open_order" and e["order_id"] == "stranger-stop" for e in events)


def test_report_missing_stop_order(isolated_paths, monkeypatch):
    """Local has stop_order_id set, but Alpaca doesn't have it in open orders."""
    trades, _ = isolated_paths
    rec = _open_record(trade_id="t1", symbol="XLK", qty=10.0)
    rec["stop_order_id"] = "expected-stop-uuid"
    _write_records(trades, [rec])
    # Alpaca has the position but no open orders
    client = FakeAlpacaClient(positions=[FakePosition("XLK", 10.0)], open_orders=[])
    monkeypatch.setattr(reconciler, "trading_client", lambda: client)
    events = reconciler.report()
    assert any(e["type"] == "missing_stop_order" and e["expected_stop_order_id"] == "expected-stop-uuid" for e in events)


def test_report_recognizes_known_stop_order_as_not_orphan(isolated_paths, monkeypatch):
    """When local stop_order_id matches an Alpaca open order, no drift."""
    trades, _ = isolated_paths
    rec = _open_record(trade_id="t1", symbol="XLK", qty=10.0)
    rec["stop_order_id"] = "tracked-stop"
    _write_records(trades, [rec])
    from alpaca.trading.enums import OrderSide as OS
    tracked = FakeOrder(id="tracked-stop", symbol="XLK", side=OS.SELL, qty=10.0, order_type="STOP")
    client = FakeAlpacaClient(positions=[FakePosition("XLK", 10.0)], open_orders=[tracked])
    monkeypatch.setattr(reconciler, "trading_client", lambda: client)
    events = reconciler.report()
    assert events == []


# Story 2.2: notify_drift — persistence + Pushover


def test_notify_drift_appends_to_drift_log_with_detected_at(isolated_paths, monkeypatch):
    trades, _ = isolated_paths
    drift_log = trades.parent / "drift_log.jsonl"
    monkeypatch.setattr(reconciler, "DRIFT_LOG", drift_log)
    monkeypatch.setattr(reconciler.pushover, "send", lambda *a, **kw: True)
    events = [{"type": "orphan_position", "symbol": "XLE", "alpaca_qty": 100.0, "local_qty": 0.0, "orphan_qty": 100.0}]
    reconciler.notify_drift(events)
    assert drift_log.exists()
    with open(drift_log) as f:
        lines = f.readlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["type"] == "orphan_position"
    assert "detected_at" in event


def test_notify_drift_idempotent_on_empty(isolated_paths, monkeypatch):
    """No drift events -> no Pushover, no file write."""
    trades, _ = isolated_paths
    drift_log = trades.parent / "drift_log.jsonl"
    monkeypatch.setattr(reconciler, "DRIFT_LOG", drift_log)
    pushover_calls = []
    monkeypatch.setattr(reconciler.pushover, "send", lambda *a, **kw: pushover_calls.append(a) or True)
    reconciler.notify_drift([])
    assert not drift_log.exists()
    assert pushover_calls == []


def test_notify_drift_stamps_event_id_and_resolution_fields(isolated_paths, monkeypatch):
    trades, _ = isolated_paths
    drift_log = trades.parent / "drift_log.jsonl"
    monkeypatch.setattr(reconciler, "DRIFT_LOG", drift_log)
    monkeypatch.setattr(reconciler.pushover, "send", lambda *a, **kw: True)
    reconciler.notify_drift([{"type": "orphan_position", "symbol": "XLE", "alpaca_qty": 100, "local_qty": 0, "orphan_qty": 100}])
    with open(drift_log) as f:
        event = json.loads(f.readline())
    assert "event_id" in event
    assert event["resolved"] is False
    assert event["resolved_at"] is None
    assert event["resolved_reason"] is None


def test_resolve_event_marks_one_resolved(isolated_paths, monkeypatch):
    trades, _ = isolated_paths
    drift_log = trades.parent / "drift_log.jsonl"
    monkeypatch.setattr(reconciler, "DRIFT_LOG", drift_log)
    monkeypatch.setattr(reconciler.pushover, "send", lambda *a, **kw: True)
    reconciler.notify_drift([
        {"type": "orphan_position", "symbol": "XLE", "alpaca_qty": 100, "local_qty": 0, "orphan_qty": 100},
        {"type": "missing_stop_order", "trade_id": "t1", "symbol": "XLK", "expected_stop_order_id": "s1"},
    ])
    unresolved = reconciler.list_unresolved()
    assert len(unresolved) == 2
    target_id = unresolved[0]["event_id"]
    found = reconciler.resolve_event(target_id, "benign timing race")
    assert found is True
    remaining = reconciler.list_unresolved()
    assert len(remaining) == 1
    # Resolved event still on disk
    with open(drift_log) as f:
        events = [json.loads(l) for l in f if l.strip()]
    assert any(e["event_id"] == target_id and e["resolved"] and e["resolved_reason"] == "benign timing race" for e in events)


def test_resolve_event_returns_false_when_id_unknown(isolated_paths, monkeypatch):
    trades, _ = isolated_paths
    monkeypatch.setattr(reconciler, "DRIFT_LOG", trades.parent / "drift_log.jsonl")
    assert reconciler.resolve_event("nonexistent-id", "any reason") is False


def test_resolve_all_unresolved_bulk_marks(isolated_paths, monkeypatch):
    trades, _ = isolated_paths
    drift_log = trades.parent / "drift_log.jsonl"
    monkeypatch.setattr(reconciler, "DRIFT_LOG", drift_log)
    monkeypatch.setattr(reconciler.pushover, "send", lambda *a, **kw: True)
    reconciler.notify_drift([
        {"type": "orphan_position", "symbol": "XLE", "alpaca_qty": 100, "local_qty": 0, "orphan_qty": 100},
        {"type": "orphan_position", "symbol": "XLF", "alpaca_qty": 50, "local_qty": 0, "orphan_qty": 50},
    ])
    count = reconciler.resolve_all_unresolved("post-2026-05-21 fix backfill")
    assert count == 2
    assert reconciler.list_unresolved() == []
    # Idempotent — second call resolves 0 more
    assert reconciler.resolve_all_unresolved("another reason") == 0


def test_list_unresolved_migrates_legacy_entries(isolated_paths, monkeypatch):
    """Legacy entries without event_id / resolved get backfilled on first read."""
    trades, _ = isolated_paths
    drift_log = trades.parent / "drift_log.jsonl"
    drift_log.parent.mkdir(parents=True, exist_ok=True)
    # Write a pre-resolution-gate event (no event_id, no resolved fields)
    drift_log.write_text(json.dumps({
        "type": "orphan_position", "symbol": "XLE", "detected_at": "2026-05-20T23:00:00+00:00"
    }) + "\n")
    monkeypatch.setattr(reconciler, "DRIFT_LOG", drift_log)
    unresolved = reconciler.list_unresolved()
    assert len(unresolved) == 1
    assert "event_id" in unresolved[0]
    assert unresolved[0]["resolved"] is False
    # Migration persisted
    with open(drift_log) as f:
        event = json.loads(f.readline())
    assert "event_id" in event


def test_notify_drift_pushover_summary(isolated_paths, monkeypatch):
    trades, _ = isolated_paths
    monkeypatch.setattr(reconciler, "DRIFT_LOG", trades.parent / "drift_log.jsonl")
    captured = []
    monkeypatch.setattr(reconciler.pushover, "send", lambda title, body: captured.append((title, body)) or True)
    events = [
        {"type": "orphan_position", "symbol": "XLE", "alpaca_qty": 100.0, "local_qty": 0.0, "orphan_qty": 100.0},
        {"type": "missing_position", "trade_id": "abcd1234-xxxx", "symbol": "XLK", "local_qty": 10.0, "alpaca_qty": 0.0},
    ]
    reconciler.notify_drift(events)
    assert len(captured) == 1
    title, body = captured[0]
    assert "2 event(s)" in title
    assert "orphan_position" in body
    assert "missing_position" in body


def test_partial_close_residual_counted_against_alpaca(isolated_paths, monkeypatch):
    """A closed trade with partial_close_residual_qty > 0 means we expect that
    much on the broker. Reconciler should NOT flag the residual as untracked."""
    trades, _ = isolated_paths
    closed_with_residual = {
        "trade_id": "t-partial",
        "symbol": "XLE",
        "fill_price": 60.0,
        "fill_qty": 83.292242807,
        "status": "closed",
        "partial_close_residual_qty": 0.292242807,
    }
    _write_records(trades, [closed_with_residual])
    client = FakeAlpacaClient(positions=[FakePosition("XLE", 0.292242807)], orders=[])
    monkeypatch.setattr(reconciler, "trading_client", lambda: client)

    summary = reconciler.reconcile(dry_run=True)

    assert summary["actions"] == [], f"Expected no drift, got {summary['actions']}"


def test_partial_close_residual_cleared_no_drift(isolated_paths, monkeypatch):
    """Once partial_close_residual_qty is cleared to 0 and broker is empty,
    reconciler should report no drift."""
    trades, _ = isolated_paths
    closed_cleared = {
        "trade_id": "t-partial",
        "symbol": "XLE",
        "fill_price": 60.0,
        "fill_qty": 83.292242807,
        "status": "closed",
        "partial_close_residual_qty": 0,
        "partial_close_cleared_at": "2026-05-27T13:32:00+00:00",
    }
    _write_records(trades, [closed_cleared])
    client = FakeAlpacaClient(positions=[], orders=[])
    monkeypatch.setattr(reconciler, "trading_client", lambda: client)

    summary = reconciler.reconcile(dry_run=True)

    assert summary["actions"] == []


def test_drift_unresolvable_dedup_against_resolved_drift_log(isolated_paths, monkeypatch):
    """When a drift_unresolvable event has been marked resolved in drift_log,
    subsequent reconcile cycles must NOT Pushover for the same trade_id."""
    trades, _ = isolated_paths
    drift_log = trades.parent / "drift_log.jsonl"
    monkeypatch.setattr(reconciler, "DRIFT_LOG", drift_log)
    drift_log.parent.mkdir(parents=True, exist_ok=True)
    drift_log.write_text(json.dumps({
        "type": "drift_unresolvable",
        "trade_id": "t1",
        "symbol": "XLK",
        "resolved": True,
        "resolved_at": "2026-05-27T13:00:00+00:00",
        "resolved_reason": "stop sold floor(qty), residual handled manually",
        "event_id": "evt-1",
        "detected_at": "2026-05-27T12:00:00+00:00",
    }) + "\n")

    _write_records(trades, [_open_record(trade_id="t1", symbol="XLK", qty=10.0)])
    client = FakeAlpacaClient(positions=[], orders=[])
    monkeypatch.setattr(reconciler, "trading_client", lambda: client)
    captured = []
    monkeypatch.setattr(reconciler.pushover, "send", lambda *a, **kw: captured.append(a) or True)

    summary = reconciler.reconcile(dry_run=False)

    # Action is still recorded for audit, but Pushover is suppressed
    assert any(a["type"] == "drift_unresolvable" and a["trade_id"] == "t1" for a in summary["actions"])
    assert captured == [], f"Pushover should be suppressed for resolved event, got {captured}"


def test_untracked_position_dedup_against_resolved_drift_log(isolated_paths, monkeypatch):
    """A resolved untracked_alpaca_position with matching (symbol, qty) suppresses
    re-alerts. If qty changes, the new value re-triggers."""
    trades, _ = isolated_paths
    drift_log = trades.parent / "drift_log.jsonl"
    monkeypatch.setattr(reconciler, "DRIFT_LOG", drift_log)
    drift_log.parent.mkdir(parents=True, exist_ok=True)
    drift_log.write_text(json.dumps({
        "type": "untracked_alpaca_position",
        "symbol": "XLE",
        "alpaca_qty": 0.29,
        "resolved": True,
        "resolved_reason": "known residual",
        "event_id": "evt-2",
        "detected_at": "2026-05-27T12:00:00+00:00",
    }) + "\n")

    _write_records(trades, [])
    client = FakeAlpacaClient(positions=[FakePosition("XLE", 0.29)], orders=[])
    monkeypatch.setattr(reconciler, "trading_client", lambda: client)
    captured = []
    monkeypatch.setattr(reconciler.pushover, "send", lambda *a, **kw: captured.append(a) or True)

    summary = reconciler.reconcile(dry_run=False)

    # Action still recorded; Pushover suppressed
    assert any(a["type"] == "untracked_alpaca_position" and a["symbol"] == "XLE" for a in summary["actions"])
    assert captured == []


def test_untracked_position_dedup_does_not_suppress_when_qty_changed(isolated_paths, monkeypatch):
    """A resolved untracked event for qty=0.29 must NOT suppress an alert for
    the same symbol at a meaningfully different qty (e.g., 100)."""
    trades, _ = isolated_paths
    drift_log = trades.parent / "drift_log.jsonl"
    monkeypatch.setattr(reconciler, "DRIFT_LOG", drift_log)
    drift_log.parent.mkdir(parents=True, exist_ok=True)
    drift_log.write_text(json.dumps({
        "type": "untracked_alpaca_position",
        "symbol": "XLE",
        "alpaca_qty": 0.29,
        "resolved": True,
        "resolved_reason": "known residual",
        "event_id": "evt-3",
        "detected_at": "2026-05-27T12:00:00+00:00",
    }) + "\n")

    _write_records(trades, [])
    client = FakeAlpacaClient(positions=[FakePosition("XLE", 100.0)], orders=[])
    monkeypatch.setattr(reconciler, "trading_client", lambda: client)
    captured = []
    monkeypatch.setattr(reconciler.pushover, "send", lambda *a, **kw: captured.append(a) or True)

    reconciler.reconcile(dry_run=False)

    assert len(captured) == 1, f"Expected one Pushover for the new qty, got {captured}"


def test_dry_run_does_not_persist_changes(isolated_paths, monkeypatch):
    trades, _ = isolated_paths
    _write_records(trades, [_open_record(trade_id="t1", symbol="XLK", qty=10.0, price=100.0)])
    matching_sell = FakeOrder(
        id="sell-uuid", symbol="XLK",
        side=__import__("alpaca.trading.enums", fromlist=["OrderSide"]).OrderSide.SELL,
        status=OrderStatus.FILLED, qty=10.0, filled_qty=10.0, filled_avg_price=105.0,
        filled_at="2026-05-18 13:40:00+00:00",
    )
    client = FakeAlpacaClient(positions=[], orders=[matching_sell])
    monkeypatch.setattr(reconciler, "trading_client", lambda: client)

    reconciler.reconcile(dry_run=True)

    with open(trades) as f:
        records = [json.loads(line) for line in f]
    assert records[0]["status"] == "open"  # unchanged


def test_report_ignores_in_flight_market_order(isolated_paths, monkeypatch):
    """An open MARKET order is in-flight execution, not an orphan — it fills or
    rejects within seconds. If it fills into an untracked position, orphan_position
    catches it next cycle. Should not be flagged as orphan_open_order."""
    trades, _ = isolated_paths
    _write_records(trades, [])
    from alpaca.trading.enums import OrderSide as OS
    mkt = FakeOrder(id="inflight-buy", symbol="XLK", side=OS.BUY, qty=60.0, order_type="MARKET")
    client = FakeAlpacaClient(positions=[], open_orders=[mkt])
    monkeypatch.setattr(reconciler, "trading_client", lambda: client)
    events = reconciler.report()
    assert all(e["type"] != "orphan_open_order" for e in events)


def test_notify_drift_dedupes_repeat_event(isolated_paths, monkeypatch):
    """The same drift event seen on a later cycle is not re-logged or re-alerted."""
    trades, _ = isolated_paths
    drift_log = trades.parent / "drift_log.jsonl"
    monkeypatch.setattr(reconciler, "DRIFT_LOG", drift_log)
    sent = []
    monkeypatch.setattr(reconciler.pushover, "send", lambda *a, **kw: sent.append(a) or True)
    event = {"type": "orphan_open_order", "order_id": "o-1", "symbol": "XLK",
             "side": "BUY", "qty": 60.0, "order_type": "STOP"}
    reconciler.notify_drift([event])
    reconciler.notify_drift([event])  # second sighting, same condition
    with open(drift_log) as f:
        lines = [l for l in f if l.strip()]
    assert len(lines) == 1   # logged once
    assert len(sent) == 1    # alerted once
