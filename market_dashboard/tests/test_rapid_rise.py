"""Tests for the rapid-rise alert in src/alerts.py (Brief 3 success criterion)."""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from src.alerts import send_alerts


def _make_history(scores: list[float], start: str = "2026-01-01") -> pd.DataFrame:
    n = len(scores)
    dates = pd.date_range(start, periods=n, freq="D")
    return pd.DataFrame({
        "timestamp": dates,
        "composite": scores,
        "composite_band": ["yellow"] * n,
    })


def _scoring(composite: float, band: str) -> dict:
    return {
        "composite": composite,
        "composite_band": band,
        "composite_short": composite,
        "composite_short_band": band,
        "red_count": 0,
        "orange_count": 0,
        "yellow_count": 1,
        "run_timestamp": "2026-01-01T07:30:00",
        "errors": [],
        "stale_indicators": [],
        "buckets": {},
    }


def _base_state(band: str = "yellow", rapid_rise_alerts: list | None = None) -> dict:
    return {
        "composite_band": band,
        "composite": 40.0,
        "orange_indicators": [],
        "red_indicators": [],
        "rapid_rise_alerts": rapid_rise_alerts or [],
        "stale_indicators": [],
        "weekly_alert_count": 0,
        "corr_regime_streak": 0,
    }


def _run(scoring, history, state):
    """Run send_alerts with Pushover + quiet-hours patched out. Returns sent count."""
    sent_messages: list[str] = []

    def fake_pushover(title, message, env):
        sent_messages.append(f"{title}\n{message}")
        return True

    with patch("src.alerts._load_state", return_value=state), \
         patch("src.alerts._save_state"), \
         patch("src.alerts._in_quiet_hours", return_value=False), \
         patch("src.alerts._send_pushover", side_effect=fake_pushover), \
         patch("src.alerts._send_twilio", return_value=False), \
         patch("src.alerts._log_alert"):
        send_alerts(scoring, {}, history)

    return sent_messages


def test_rapid_rise_fires_on_first_occurrence():
    """
    +15 pts in 7 days, band=yellow, no prior rapid_rise_alerts → alert fires.
    """
    scores = [40.0] * 10 + [55.0]
    history = _make_history(scores)
    scoring = _scoring(55.0, "yellow")

    messages = _run(scoring, history, _base_state("yellow"))

    assert any("RAPID RISE" in m for m in messages), (
        f"Expected RAPID RISE alert. Got: {messages}"
    )


def test_rapid_rise_suppressed_when_already_fired():
    """Same scenario but rapid_rise_yellow already in state → no duplicate."""
    scores = [40.0] * 10 + [55.0]
    history = _make_history(scores)
    scoring = _scoring(55.0, "yellow")

    state = _base_state("yellow", rapid_rise_alerts=["rapid_rise_yellow"])
    messages = _run(scoring, history, state)

    assert not any("RAPID RISE" in m for m in messages), (
        f"Expected no RAPID RISE alert (already fired). Got: {messages}"
    )


def test_rapid_rise_not_fired_below_threshold():
    """+8 pts in 7 days (< 10 threshold) → no rapid-rise alert."""
    scores = [40.0] * 10 + [48.0]
    history = _make_history(scores)
    scoring = _scoring(48.0, "yellow")

    messages = _run(scoring, history, _base_state("yellow"))

    assert not any("RAPID RISE" in m for m in messages), (
        f"Expected no RAPID RISE alert (below threshold). Got: {messages}"
    )


def test_rapid_rise_resets_on_band_change():
    """When band changes, rapid_rise_alerts list is cleared in saved state."""
    scores = [40.0] * 10 + [55.0]
    history = _make_history(scores)
    # Band escalated from yellow → orange
    scoring = _scoring(55.0, "orange")
    state = _base_state("yellow", rapid_rise_alerts=["rapid_rise_yellow"])

    saved: list[dict] = []

    with patch("src.alerts._load_state", return_value=state), \
         patch("src.alerts._save_state", side_effect=lambda s: saved.append(dict(s))), \
         patch("src.alerts._in_quiet_hours", return_value=False), \
         patch("src.alerts._send_pushover", return_value=True), \
         patch("src.alerts._send_twilio", return_value=False), \
         patch("src.alerts._log_alert"):
        send_alerts(scoring, {}, history)

    assert saved, "State should have been saved"
    assert saved[-1].get("rapid_rise_alerts") == [], (
        "rapid_rise_alerts should be reset when band changes"
    )
