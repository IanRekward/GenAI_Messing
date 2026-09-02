"""Tests for Commit 1B — alert state-machine repairs (R2, R3, R4)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pandas as pd
import pytest

from src.alerts import _load_state, score_past_alerts, send_alerts


def _scoring(band="orange", composite=45.0):
    return {
        "composite": composite,
        "composite_band": band,
        "regime": "mid",
        "stale_indicators": [],
        "buckets": {
            "credit_spreads": {
                "band": "green",
                "indicators": {
                    "hy_oas": {"label": "HY OAS", "band": "green", "raw": 3.0},
                },
            },
        },
    }


def _redirect(monkeypatch, tmp_path):
    monkeypatch.setattr("src.alerts.STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr("src.alerts.ALERT_LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr("src.alerts.DATA_DIR", tmp_path)
    monkeypatch.setattr("src.alerts._in_quiet_hours", lambda env: False)


def test_corrupt_state_file_does_not_crash(tmp_path, monkeypatch):
    _redirect(monkeypatch, tmp_path)
    (tmp_path / "state.json").write_text('{"composite_band": "or')
    state = _load_state()
    assert state["composite_band"] == "green"
    assert state["red_indicators"] == []


def test_timekeeping_keys_survive_normal_run(tmp_path, monkeypatch):
    _redirect(monkeypatch, tmp_path)
    (tmp_path / "state.json").write_text(json.dumps({
        "composite_band": "orange",
        "red_indicators": [],
        "orange_indicators": [],
        "heartbeat_start": "2026-04-23",
        "last_health_alert_time": 1234567890.0,
    }))
    with patch("src.alerts._check_dashboard_freshness", return_value=(True, "")):
        sent = send_alerts(_scoring(band="orange"), {})
    assert sent == 0
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved["heartbeat_start"] == "2026-04-23"
    assert saved["last_health_alert_time"] == 1234567890.0


def test_health_alert_debounce_holds_across_runs(tmp_path, monkeypatch):
    _redirect(monkeypatch, tmp_path)
    (tmp_path / "state.json").write_text(json.dumps({
        "composite_band": "orange",
        "red_indicators": [],
        "orange_indicators": [],
    }))
    stale = ("", "CRITICAL: Dashboard not updated in 48.0 hours")
    with patch("src.alerts._check_dashboard_freshness", return_value=(False, stale[1])), \
         patch("src.alerts._send_pushover", return_value=True) as push:
        first = send_alerts(_scoring(band="orange"), {})
        assert first == 1
        assert push.call_count == 1
        # Second run, still stale, minutes later: debounce must hold.
        second = send_alerts(_scoring(band="orange"), {})
        assert push.call_count == 1, "health alert re-fired within 6h window"
        assert second == 0
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved["last_health_alert_time"] > 0


def test_score_past_alerts_rewrite_is_atomic(tmp_path, monkeypatch):
    _redirect(monkeypatch, tmp_path)
    log = tmp_path / "log.jsonl"
    log.write_text(json.dumps({
        "timestamp": "2026-08-01T07:30:00",
        "title": "x",
        "t7_composite": None,
        "t14_composite": None,
        "t30_composite": None,
    }) + "\n")
    idx = pd.date_range("2026-08-01", periods=40, freq="D")
    hist = pd.DataFrame({"timestamp": idx, "composite": [40.0] * 40})
    score_past_alerts(hist)
    assert not (tmp_path / "log.jsonl.tmp").exists()
    entries = [json.loads(l) for l in log.read_text().splitlines()]
    assert entries[0]["t7_composite"] == 40.0
