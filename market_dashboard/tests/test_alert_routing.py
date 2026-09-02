"""Tests for Commit 3C (B3) — two-lane alert routing: market pushes, plumbing digests."""
from __future__ import annotations

import json
from unittest.mock import patch

import pandas as pd

from src.alerts import send_alerts, send_heartbeat, send_weekly_digest


def _redirect(monkeypatch, tmp_path):
    monkeypatch.setattr("src.alerts.STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr("src.alerts.ALERT_LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr("src.alerts.DATA_DIR", tmp_path)
    monkeypatch.setattr("src.alerts._in_quiet_hours", lambda env: False)
    monkeypatch.setattr(
        "src.alerts._check_dashboard_freshness", lambda env: (True, "")
    )


def _scoring(stale=(), band="yellow", composite=40.0):
    return {
        "composite": composite,
        "composite_band": band,
        "regime": "mid",
        "stale_indicators": list(stale),
        "buckets": {
            "credit_spreads": {
                "band": "green",
                "indicators": {
                    "hy_oas": {"label": "HY OAS", "band": "green", "raw": 3.0},
                },
            },
        },
    }


def _seed_state(tmp_path, **extra):
    state = {"composite_band": "yellow", "red_indicators": [],
             "orange_indicators": [], **extra}
    (tmp_path / "state.json").write_text(json.dumps(state))


def test_staleness_never_pushes_but_logs_and_queues(tmp_path, monkeypatch):
    _redirect(monkeypatch, tmp_path)
    _seed_state(tmp_path)
    with patch("src.alerts._send_pushover", return_value=True) as push:
        sent = send_alerts(_scoring(stale=["hy_oas"]), {})
    assert sent == 0
    push.assert_not_called()
    log = [json.loads(l) for l in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert log[0]["alert_types"] == ["staleness"]
    state = json.loads((tmp_path / "state.json").read_text())
    assert len(state["pending_digest_notes"]) == 1
    assert "STALE DATA (1)" in state["pending_digest_notes"][0]


def test_digest_delivers_and_clears_plumbing_notes(tmp_path, monkeypatch):
    _redirect(monkeypatch, tmp_path)
    _seed_state(
        tmp_path,
        pending_digest_notes=["2026-09-01: STALE DATA (1): MOVE Index"],
        weekly_alert_count=2,
    )
    monkeypatch.setattr("src.alerts.date", _FakeMonday)
    hist = pd.DataFrame({
        "timestamp": pd.date_range("2026-08-27", periods=7, freq="D"),
        "composite": [40.0] * 7,
    })
    with patch("src.alerts._send_pushover", return_value=True) as push:
        assert send_weekly_digest(_scoring(), {}, hist) is True
    body = push.call_args[0][1]
    assert "Data plumbing since last digest" in body
    assert "MOVE Index" in body
    assert "morning runs completed" in body
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["pending_digest_notes"] == []


class _FakeMonday:
    @staticmethod
    def today():
        import datetime
        return datetime.date(2026, 9, 7)  # a Monday

    @staticmethod
    def fromisoformat(s):
        import datetime
        return datetime.date.fromisoformat(s)


def test_heartbeat_does_not_self_seed(tmp_path, monkeypatch):
    _redirect(monkeypatch, tmp_path)
    _seed_state(tmp_path)  # no heartbeat_start key
    scoring = {**_scoring(), "red_count": 0, "orange_count": 0, "yellow_count": 0}
    with patch("src.alerts._send_pushover", return_value=True) as push:
        assert send_heartbeat(scoring, {}) is False
    push.assert_not_called()
    state = json.loads((tmp_path / "state.json").read_text())
    assert "heartbeat_start" not in state


def test_heartbeat_expired_start_stays_silent(tmp_path, monkeypatch):
    _redirect(monkeypatch, tmp_path)
    _seed_state(tmp_path, heartbeat_start="2026-04-23")
    scoring = {**_scoring(), "red_count": 0, "orange_count": 0, "yellow_count": 0}
    with patch("src.alerts._send_pushover", return_value=True) as push:
        assert send_heartbeat(scoring, {}) is False
    push.assert_not_called()


def test_regime_review_fires_once_at_five_high_days(tmp_path, monkeypatch):
    _redirect(monkeypatch, tmp_path)
    _seed_state(tmp_path, high_regime_streak=4)
    scoring = {**_scoring(), "regime": "high"}
    with patch("src.alerts._send_pushover", return_value=True) as push:
        sent = send_alerts(scoring, {})
    assert sent == 1
    assert "REGIME-WEIGHTS REVIEW TRIGGERED" in push.call_args[0][1]
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["regime_review_fired"] is True
    assert state["high_regime_streak"] == 5
    # day 6: latched, no re-fire
    with patch("src.alerts._send_pushover", return_value=True) as push2:
        sent2 = send_alerts(scoring, {})
    assert sent2 == 0
    push2.assert_not_called()
