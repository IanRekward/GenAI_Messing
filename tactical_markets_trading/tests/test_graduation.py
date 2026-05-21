"""Tests for src/graduation.py — Epic 3 graduation status + notify."""
import json

import pytest

import graduation


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    trades = tmp_path / "trades.jsonl"
    drift = tmp_path / "drift_log.jsonl"
    state = tmp_path / "graduation_state.json"
    monkeypatch.setattr(graduation, "TRADES_PATH", trades)
    monkeypatch.setattr(graduation, "DRIFT_LOG", drift)
    monkeypatch.setattr(graduation, "GRADUATION_STATE_PATH", state)
    return trades, drift, state


def _write_records(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _closed(pnl=10.0, exit_reason="scheduled", macro_snapshot=None):
    return {
        "status": "closed",
        "pnl_dollars": pnl,
        "exit_reason": exit_reason,
        "macro_snapshot": macro_snapshot,
    }


# Story 3.1: check_status


def test_status_zero_when_files_missing(isolated_paths):
    status = graduation.check_status()
    assert status["total_closed_trades"] == 0
    assert status["stop_fired_exits"] == 0
    assert status["macro_size_downs"] == 0
    assert status["drift_false_positives"] == 0
    assert status["criterion_met"] is False


def test_status_counts_closed_trades(isolated_paths):
    trades, _, _ = isolated_paths
    _write_records(trades, [_closed() for _ in range(5)] + [{"status": "open"}])
    status = graduation.check_status()
    assert status["total_closed_trades"] == 5


def test_status_counts_stop_fired_exits(isolated_paths):
    trades, _, _ = isolated_paths
    _write_records(trades, [
        _closed(exit_reason="scheduled"),
        _closed(exit_reason="stop_fired"),
        _closed(exit_reason="stop_fired"),
        _closed(exit_reason="stop_cancel_failed"),
    ])
    status = graduation.check_status()
    assert status["stop_fired_exits"] == 2


def test_status_counts_macro_size_downs(isolated_paths):
    trades, _, _ = isolated_paths
    _write_records(trades, [
        _closed(macro_snapshot={"composite_band": "green", "regime": "low", "neutralized": False}),
        _closed(macro_snapshot={"composite_band": "red", "regime": "low", "neutralized": False}),
        _closed(macro_snapshot={"composite_band": "orange", "regime": "high", "neutralized": False}),
        _closed(macro_snapshot={"composite_band": "orange", "regime": "mid", "neutralized": False}),
        _closed(macro_snapshot={"composite_band": "red", "regime": "high", "neutralized": True}),  # neutralized -> not counted
    ])
    status = graduation.check_status()
    assert status["macro_size_downs"] == 2  # red+anything, orange+high


def test_status_counts_drift_events(isolated_paths):
    _, drift, _ = isolated_paths
    drift.parent.mkdir(parents=True, exist_ok=True)
    with open(drift, "w") as f:
        f.write(json.dumps({"type": "orphan_position", "symbol": "XLK", "resolved": False}) + "\n")
        f.write(json.dumps({"type": "missing_stop_order", "trade_id": "t1", "resolved": False}) + "\n")
    status = graduation.check_status()
    assert status["drift_false_positives"] == 2


def test_status_excludes_resolved_drift_events(isolated_paths):
    """Resolved events stay in the audit trail but don't block graduation."""
    _, drift, _ = isolated_paths
    drift.parent.mkdir(parents=True, exist_ok=True)
    with open(drift, "w") as f:
        f.write(json.dumps({"type": "orphan_position", "symbol": "XLK", "resolved": True, "resolved_reason": "benign timing"}) + "\n")
        f.write(json.dumps({"type": "missing_stop_order", "trade_id": "t1", "resolved": False}) + "\n")
    status = graduation.check_status()
    assert status["drift_false_positives"] == 1  # only the unresolved one counts


def test_status_treats_missing_resolved_field_as_unresolved(isolated_paths):
    """Legacy events with no `resolved` field count as unresolved (safe default)."""
    _, drift, _ = isolated_paths
    drift.parent.mkdir(parents=True, exist_ok=True)
    drift.write_text(json.dumps({"type": "orphan_position", "symbol": "XLK"}) + "\n")
    status = graduation.check_status()
    assert status["drift_false_positives"] == 1


def test_criterion_met_requires_all_four(isolated_paths):
    """20 trades + 2 stop_fired + 1 macro_size_down + 0 drift = met."""
    trades, _, _ = isolated_paths
    records = [_closed(exit_reason="scheduled") for _ in range(17)]
    records += [_closed(exit_reason="stop_fired"), _closed(exit_reason="stop_fired")]
    records += [_closed(macro_snapshot={"composite_band": "red", "regime": "high", "neutralized": False})]
    _write_records(trades, records)
    status = graduation.check_status()
    assert status["criterion_met"] is True


def test_criterion_not_met_when_drift_present(isolated_paths):
    trades, drift, _ = isolated_paths
    records = [_closed(exit_reason="stop_fired") for _ in range(2)]
    records += [_closed(macro_snapshot={"composite_band": "red", "regime": "high", "neutralized": False})]
    records += [_closed() for _ in range(17)]
    _write_records(trades, records)
    drift.parent.mkdir(parents=True, exist_ok=True)
    drift.write_text(json.dumps({"type": "orphan_position"}) + "\n")
    status = graduation.check_status()
    assert status["criterion_met"] is False
    assert status["drift_false_positives"] == 1


# Story 3.2: notify_if_met


def test_notify_returns_false_when_criterion_not_met(isolated_paths, monkeypatch):
    monkeypatch.setattr(graduation.pushover, "send", lambda *a, **kw: True)
    assert graduation.notify_if_met() is False


def test_notify_sends_pushover_and_writes_state_when_met(isolated_paths, monkeypatch):
    trades, _, state_path = isolated_paths
    records = [_closed(exit_reason="stop_fired") for _ in range(2)]
    records += [_closed(macro_snapshot={"composite_band": "red", "regime": "high", "neutralized": False})]
    records += [_closed() for _ in range(17)]
    _write_records(trades, records)
    sent = []
    monkeypatch.setattr(graduation.pushover, "send", lambda title, body: sent.append((title, body)) or True)
    assert graduation.notify_if_met() is True
    assert len(sent) == 1
    assert "PHASE 2 GRADUATION MET" in sent[0][0]
    assert state_path.exists()


def test_notify_idempotent_after_first_call(isolated_paths, monkeypatch):
    trades, _, state_path = isolated_paths
    records = [_closed(exit_reason="stop_fired") for _ in range(2)]
    records += [_closed(macro_snapshot={"composite_band": "red", "regime": "high", "neutralized": False})]
    records += [_closed() for _ in range(17)]
    _write_records(trades, records)
    sent = []
    monkeypatch.setattr(graduation.pushover, "send", lambda title, body: sent.append((title, body)) or True)
    assert graduation.notify_if_met() is True
    assert graduation.notify_if_met() is False  # second call: idempotent
    assert len(sent) == 1
