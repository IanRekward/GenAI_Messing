"""Tests for alert post-mortem tracking (todo 33)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from src.alerts import score_past_alerts, get_postmortem_stats, ALERT_LOG, DATA_DIR


def _write_log(tmp_path: Path, entries: list[dict]) -> Path:
    log = tmp_path / "alert_log.jsonl"
    with open(log, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return log


def _make_history(composites: list[float], start_days_ago: int = 40) -> pd.DataFrame:
    base = datetime.now() - timedelta(days=start_days_ago)
    rows = []
    for i, c in enumerate(composites):
        ts = (base + timedelta(days=i)).strftime("%Y-%m-%d")
        rows.append({"timestamp": ts, "composite": c})
    return pd.DataFrame(rows)


@pytest.fixture(autouse=True)
def patch_log_path(tmp_path, monkeypatch):
    """Redirect ALERT_LOG to a temp file for all tests in this module."""
    monkeypatch.setattr("src.alerts.ALERT_LOG", tmp_path / "alert_log.jsonl")
    monkeypatch.setattr("src.alerts.DATA_DIR", tmp_path)


def test_score_fills_t7_when_window_elapsed(tmp_path, monkeypatch):
    monkeypatch.setattr("src.alerts.ALERT_LOG", tmp_path / "alert_log.jsonl")
    alert_ts = (datetime.now() - timedelta(days=10)).isoformat()
    entry = {
        "timestamp": alert_ts,
        "composite_score": 55.0,
        "composite_band": "orange",
        "alert_types": ["composite_escalation"],
        "t7_composite": None,
        "t14_composite": None,
        "t30_composite": None,
    }
    log_path = tmp_path / "alert_log.jsonl"
    log_path.write_text(json.dumps(entry) + "\n")

    # History covers 40 days ending today, all at 60.0
    hist = _make_history([60.0] * 40)
    score_past_alerts(hist)

    updated = [json.loads(l) for l in log_path.read_text().splitlines() if l]
    assert updated[0]["t7_composite"] == 60.0
    assert updated[0]["t14_composite"] is None  # 14d window not yet elapsed (10 < 14)


def test_score_skips_future_windows(tmp_path, monkeypatch):
    monkeypatch.setattr("src.alerts.ALERT_LOG", tmp_path / "alert_log.jsonl")
    alert_ts = (datetime.now() - timedelta(days=3)).isoformat()
    entry = {
        "timestamp": alert_ts,
        "composite_score": 55.0,
        "t7_composite": None,
        "t14_composite": None,
        "t30_composite": None,
    }
    log_path = tmp_path / "alert_log.jsonl"
    log_path.write_text(json.dumps(entry) + "\n")

    hist = _make_history([60.0] * 10)
    score_past_alerts(hist)

    updated = [json.loads(l) for l in log_path.read_text().splitlines() if l]
    assert updated[0]["t7_composite"] is None  # only 3d elapsed, 7d window not yet closed


def test_score_does_not_overwrite_existing(tmp_path, monkeypatch):
    monkeypatch.setattr("src.alerts.ALERT_LOG", tmp_path / "alert_log.jsonl")
    alert_ts = (datetime.now() - timedelta(days=10)).isoformat()
    entry = {
        "timestamp": alert_ts,
        "composite_score": 55.0,
        "t7_composite": 42.0,  # already filled
        "t14_composite": None,
        "t30_composite": None,
    }
    log_path = tmp_path / "alert_log.jsonl"
    log_path.write_text(json.dumps(entry) + "\n")

    hist = _make_history([99.0] * 40)
    score_past_alerts(hist)

    updated = [json.loads(l) for l in log_path.read_text().splitlines() if l]
    assert updated[0]["t7_composite"] == 42.0  # not overwritten


def test_postmortem_stats_hit_rate(tmp_path, monkeypatch):
    monkeypatch.setattr("src.alerts.ALERT_LOG", tmp_path / "alert_log.jsonl")
    now = datetime.now()
    entries = [
        {
            "timestamp": (now - timedelta(days=20)).isoformat(),
            "composite_score": 55.0,
            "t7_composite": 62.0,  # stayed elevated → hit
        },
        {
            "timestamp": (now - timedelta(days=15)).isoformat(),
            "composite_score": 55.0,
            "t7_composite": 38.0,  # dropped below 50 → miss
        },
    ]
    log_path = tmp_path / "alert_log.jsonl"
    log_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    stats = get_postmortem_stats(days=60)
    assert stats["scored_count"] == 2
    assert stats["hit_rate_7d_pct"] == 50.0
    assert stats["avg_t7_change"] == pytest.approx(((62 - 55) + (38 - 55)) / 2)


def test_postmortem_stats_empty_log(tmp_path, monkeypatch):
    monkeypatch.setattr("src.alerts.ALERT_LOG", tmp_path / "alert_log.jsonl")
    stats = get_postmortem_stats()
    assert stats == {}


def test_postmortem_excludes_entries_outside_window(tmp_path, monkeypatch):
    monkeypatch.setattr("src.alerts.ALERT_LOG", tmp_path / "alert_log.jsonl")
    now = datetime.now()
    entries = [
        {
            "timestamp": (now - timedelta(days=90)).isoformat(),  # outside 60d window
            "composite_score": 55.0,
            "t7_composite": 62.0,
        },
    ]
    log_path = tmp_path / "alert_log.jsonl"
    log_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    stats = get_postmortem_stats(days=60)
    assert stats.get("scored_count", 0) == 0


def test_score_no_crash_on_missing_log():
    """score_past_alerts should not raise if log file does not exist."""
    hist = _make_history([50.0] * 10)
    score_past_alerts(hist)  # ALERT_LOG is in tmp_path (doesn't exist yet) → no-op


def test_score_handles_legacy_entries_without_crash(tmp_path, monkeypatch):
    monkeypatch.setattr("src.alerts.ALERT_LOG", tmp_path / "alert_log.jsonl")
    log_path = tmp_path / "alert_log.jsonl"
    legacy = {"timestamp": (datetime.now() - timedelta(days=10)).isoformat(),
               "title": "old", "body": "old body"}  # no t7/t14/t30 keys
    log_path.write_text(json.dumps(legacy) + "\n")

    hist = _make_history([50.0] * 40)
    score_past_alerts(hist)  # should not crash
