"""Tests for alert debouncing (34), breadth confirmation (35), quiet hours (36)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.alerts import _debounce_passes, _in_quiet_hours, send_alerts


@pytest.fixture(autouse=True)
def _fresh_dashboard():
    # Neutralize the freshness self-check so the health alert doesn't fire on a
    # stale real HTML file and inflate sent counts. Keeps these tests hermetic.
    with patch("src.alerts._check_dashboard_freshness", return_value=(True, "OK: test")):
        yield


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_scoring(composite: float = 52.0, band: str = "orange",
                  n_orange_buckets: int = 1, n_red_buckets: int = 0) -> dict:
    """Build a minimal scoring dict for alert tests."""
    buckets = {}
    for i in range(10):
        if i < n_red_buckets:
            bband = "red"
        elif i < n_red_buckets + n_orange_buckets:
            bband = "orange"
        else:
            bband = "green"
        buckets[f"bucket_{i}"] = {
            "label": f"Bucket {i}",
            "band": bband,
            "score": composite,
            "indicators": {},
        }
    return {
        "composite": composite,
        "composite_band": band,
        "red_count": n_red_buckets,
        "orange_count": n_orange_buckets,
        "yellow_count": 0,
        "buckets": buckets,
        "errors": [],
        "stale_indicators": [],
    }


def _prev_state(band: str = "yellow") -> dict:
    return {
        "composite_band": band,
        "red_indicators": [],
        "orange_indicators": [],
        "rapid_rise_alerts": [],
        "stale_indicators": [],
        "corr_regime_streak": 0,
        "weekly_alert_count": 0,
        "weekly_digest_date": "",
        "suppressed_alerts": [],
    }


# ── Todo 34: Debounce ─────────────────────────────────────────────────────

class TestDebounce:
    def test_escalation_passes_when_above_buffer(self):
        assert _debounce_passes("orange", "yellow", 56.0, 5.0) is True

    def test_escalation_suppressed_when_barely_over_threshold(self):
        assert _debounce_passes("orange", "yellow", 52.0, 5.0) is False

    def test_escalation_passes_exactly_at_threshold_plus_buffer(self):
        assert _debounce_passes("orange", "yellow", 55.0, 5.0) is True

    def test_de_escalation_passes_when_below_buffer(self):
        assert _debounce_passes("yellow", "orange", 44.0, 5.0) is True

    def test_de_escalation_suppressed_when_barely_below_threshold(self):
        assert _debounce_passes("yellow", "orange", 48.0, 5.0) is False

    def test_red_escalation_passes_above_buffer(self):
        assert _debounce_passes("red", "orange", 76.0, 5.0) is True

    def test_red_escalation_suppressed_below_buffer(self):
        assert _debounce_passes("red", "orange", 72.0, 5.0) is False

    def test_zero_buffer_always_passes(self):
        assert _debounce_passes("orange", "yellow", 50.1, 0.0) is True

    def test_send_alerts_suppresses_marginal_escalation(self, tmp_path, monkeypatch):
        """Composite at 52 (barely orange) should not fire escalation with buffer=5."""
        monkeypatch.setattr("src.alerts.STATE_FILE", tmp_path / "state.json")
        monkeypatch.setattr("src.alerts.ALERT_LOG", tmp_path / "log.jsonl")
        monkeypatch.setattr("src.alerts.DATA_DIR", tmp_path)

        import json
        (tmp_path / "state.json").write_text(json.dumps(_prev_state("yellow")))

        scoring = _make_scoring(composite=52.0, band="orange", n_orange_buckets=2)
        env = {"ALERT_DEBOUNCE_BUFFER": "5"}
        sent = send_alerts(scoring, env)
        assert sent == 0  # suppressed by debounce

    def test_send_alerts_fires_confirmed_escalation(self, tmp_path, monkeypatch):
        """Composite at 57 (clearly orange, 2 stressed buckets) should fire."""
        monkeypatch.setattr("src.alerts.STATE_FILE", tmp_path / "state.json")
        monkeypatch.setattr("src.alerts.ALERT_LOG", tmp_path / "log.jsonl")
        monkeypatch.setattr("src.alerts.DATA_DIR", tmp_path)

        import json
        (tmp_path / "state.json").write_text(json.dumps(_prev_state("yellow")))

        scoring = _make_scoring(composite=57.0, band="orange", n_orange_buckets=2)
        env = {"ALERT_DEBOUNCE_BUFFER": "5"}

        printed = []
        with patch("builtins.print", side_effect=lambda *a: printed.append(str(a))):
            sent = send_alerts(scoring, env)
        assert sent == 1
        assert any("COMPOSITE ESCALATED" in p or "SINGLE-BUCKET" in p for p in printed)


# ── Todo 35: Breadth confirmation ────────────────────────────────────────

class TestBreadth:
    def test_single_bucket_stress_label_when_only_one_bucket_elevated(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.alerts.STATE_FILE", tmp_path / "state.json")
        monkeypatch.setattr("src.alerts.ALERT_LOG", tmp_path / "log.jsonl")
        monkeypatch.setattr("src.alerts.DATA_DIR", tmp_path)

        import json
        (tmp_path / "state.json").write_text(json.dumps(_prev_state("yellow")))

        # 1 orange bucket, composite clearly in orange (above debounce buffer)
        scoring = _make_scoring(composite=60.0, band="orange", n_orange_buckets=1)
        env = {"ALERT_DEBOUNCE_BUFFER": "5"}

        printed = []
        with patch("builtins.print", side_effect=lambda *a: printed.append(str(a))):
            sent = send_alerts(scoring, env)

        assert sent == 1
        assert any("SINGLE-BUCKET STRESS" in p for p in printed)

    def test_broad_escalation_label_when_two_buckets_elevated(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.alerts.STATE_FILE", tmp_path / "state.json")
        monkeypatch.setattr("src.alerts.ALERT_LOG", tmp_path / "log.jsonl")
        monkeypatch.setattr("src.alerts.DATA_DIR", tmp_path)

        import json
        (tmp_path / "state.json").write_text(json.dumps(_prev_state("yellow")))

        scoring = _make_scoring(composite=60.0, band="orange", n_orange_buckets=2)
        env = {"ALERT_DEBOUNCE_BUFFER": "5"}

        printed = []
        with patch("builtins.print", side_effect=lambda *a: printed.append(str(a))):
            send_alerts(scoring, env)

        assert any("COMPOSITE ESCALATED" in p for p in printed)

    def test_red_band_always_gets_escalated_label(self, tmp_path, monkeypatch):
        """Red band skips breadth check — always escalated label."""
        monkeypatch.setattr("src.alerts.STATE_FILE", tmp_path / "state.json")
        monkeypatch.setattr("src.alerts.ALERT_LOG", tmp_path / "log.jsonl")
        monkeypatch.setattr("src.alerts.DATA_DIR", tmp_path)

        import json
        (tmp_path / "state.json").write_text(json.dumps(_prev_state("orange")))

        scoring = _make_scoring(composite=76.0, band="red", n_red_buckets=1)
        env = {"ALERT_DEBOUNCE_BUFFER": "5"}

        printed = []
        with patch("builtins.print", side_effect=lambda *a: printed.append(str(a))):
            send_alerts(scoring, env)

        assert any("COMPOSITE ESCALATED" in p for p in printed)


# ── Todo 36: Quiet hours ──────────────────────────────────────────────────

class TestQuietHours:
    def test_in_quiet_hours_wraps_midnight(self):
        env = {"QUIET_HOURS_START": "22", "QUIET_HOURS_END": "7"}
        with patch("src.alerts.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 23
            assert _in_quiet_hours(env) is True
        with patch("src.alerts.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 3
            assert _in_quiet_hours(env) is True
        with patch("src.alerts.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 10
            assert _in_quiet_hours(env) is False

    def test_alert_suppressed_during_quiet_hours(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.alerts.STATE_FILE", tmp_path / "state.json")
        monkeypatch.setattr("src.alerts.ALERT_LOG", tmp_path / "log.jsonl")
        monkeypatch.setattr("src.alerts.DATA_DIR", tmp_path)

        import json
        (tmp_path / "state.json").write_text(json.dumps(_prev_state("yellow")))

        scoring = _make_scoring(composite=60.0, band="orange", n_orange_buckets=2)
        env = {"ALERT_DEBOUNCE_BUFFER": "5", "QUIET_HOURS_START": "0", "QUIET_HOURS_END": "23"}

        with patch("src.alerts.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 2
            mock_dt.now.return_value.isoformat.return_value = "2026-04-23T02:00:00"
            sent = send_alerts(scoring, env)

        assert sent == 0

        # State should have a suppressed_alerts entry
        state = json.loads((tmp_path / "state.json").read_text())
        assert len(state["suppressed_alerts"]) == 1

    def test_red_overrides_quiet_hours(self, tmp_path, monkeypatch):
        """Red-band alerts always fire regardless of quiet hours."""
        monkeypatch.setattr("src.alerts.STATE_FILE", tmp_path / "state.json")
        monkeypatch.setattr("src.alerts.ALERT_LOG", tmp_path / "log.jsonl")
        monkeypatch.setattr("src.alerts.DATA_DIR", tmp_path)

        import json
        (tmp_path / "state.json").write_text(json.dumps(_prev_state("orange")))

        scoring = _make_scoring(composite=76.0, band="red", n_red_buckets=1)
        env = {"ALERT_DEBOUNCE_BUFFER": "5", "QUIET_HOURS_START": "0", "QUIET_HOURS_END": "23"}

        with patch("src.alerts.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 2
            mock_dt.now.return_value.isoformat.return_value = "2026-04-23T02:00:00"
            printed = []
            with patch("builtins.print", side_effect=lambda *a: printed.append(str(a))):
                sent = send_alerts(scoring, env)

        assert sent == 1

    def test_suppressed_digest_delivered_after_quiet_period(self, tmp_path, monkeypatch):
        """When quiet period ends, suppressed alerts are summarized in the next alert."""
        monkeypatch.setattr("src.alerts.STATE_FILE", tmp_path / "state.json")
        monkeypatch.setattr("src.alerts.ALERT_LOG", tmp_path / "log.jsonl")
        monkeypatch.setattr("src.alerts.DATA_DIR", tmp_path)

        import json
        state = _prev_state("yellow")
        state["suppressed_alerts"] = [
            {"timestamp": "2026-04-23T02:00:00", "title": "Market Stress: ORANGE (55/100)", "summary": "COMPOSITE ESCALATED"}
        ]
        (tmp_path / "state.json").write_text(json.dumps(state))

        # Now it's daytime, composite escalated further
        scoring = _make_scoring(composite=60.0, band="orange", n_orange_buckets=2)
        env = {"ALERT_DEBOUNCE_BUFFER": "5", "QUIET_HOURS_START": "22", "QUIET_HOURS_END": "7"}

        with patch("src.alerts.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 10
            mock_dt.now.return_value.isoformat.return_value = "2026-04-23T10:00:00"
            printed = []
            with patch("builtins.print", side_effect=lambda *a: printed.append(str(a))):
                send_alerts(scoring, env)

        # "SUPPRESSED OVERNIGHT" should appear in the alert body
        assert any("SUPPRESSED OVERNIGHT" in p for p in printed)

        # suppressed_alerts should be cleared in state
        state_after = json.loads((tmp_path / "state.json").read_text())
        assert state_after["suppressed_alerts"] == []
