"""Tests for the --ondemand flag: state-mutating steps are skipped, dashboard write runs."""
from __future__ import annotations

import sys
from contextlib import contextmanager, ExitStack
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd


def _minimal_scoring() -> dict:
    return {
        "composite": 45.0, "composite_naive": 45.0,
        "composite_band": "yellow", "composite_short": 47.0,
        "composite_short_band": "yellow", "composite_regime_adj": 45.0,
        "composite_regime_adj_label": "", "regime": "mid",
        "run_timestamp": "2026-05-11T07:30:00",
        "red_count": 0, "orange_count": 0, "yellow_count": 1,
        "stale_indicators": [], "errors": [], "history_years": 10,
        "buckets": {},
    }


@contextmanager
def _patched_main(argv: list[str]):
    """Patch all external I/O in run_dashboard.main() and yield spy dict."""
    log_run_m     = MagicMock()
    prune_hist_m  = MagicMock()
    score_past_m  = MagicMock()
    send_alerts_m = MagicMock(return_value=0)
    send_digest_m = MagicMock()
    send_hb_m     = MagicMock()
    write_dash_m  = MagicMock(return_value=Path("output/dashboard.html"))
    write_side_m  = MagicMock()

    patches = [
        patch.object(sys, "argv", argv),
        patch("run_dashboard.load_dotenv"),
        patch("run_dashboard.load_weights", return_value={"buckets": {}}),
        patch("run_dashboard.load_thresholds", return_value={}),
        patch("run_dashboard.validate_config"),
        patch("run_dashboard.load_manual_overrides", return_value={}),
        patch("run_dashboard.compute_composite", return_value=_minimal_scoring()),
        patch("run_dashboard.annotate_results", side_effect=lambda s, t: s),
        patch("run_dashboard.log_run", log_run_m),
        patch("run_dashboard.prune_history", prune_hist_m),
        patch("run_dashboard.load_history", return_value=pd.DataFrame()),
        patch("run_dashboard.score_past_alerts", score_past_m),
        patch("run_dashboard.send_alerts", send_alerts_m),
        patch("run_dashboard.send_weekly_digest", send_digest_m),
        patch("run_dashboard.send_heartbeat", send_hb_m),
        patch("run_dashboard.write_dashboard", write_dash_m),
        patch("run_dashboard._verify_dashboard_written"),
        patch("run_dashboard.write_latest_sidecar", write_side_m),
        patch("run_dashboard.get_news_brief", return_value=[]),
        patch("run_dashboard.generate_narrative", return_value=("", "")),
        patch("run_dashboard.fetch_upcoming_events", return_value=[]),
        patch("run_dashboard.compute_composite_momentum",
              return_value={"velocity_7d": 0.0, "regime": "insufficient"}),
        patch("run_dashboard.compute_bucket_momentum", return_value={}),
        patch("run_dashboard.classify_shock_type", return_value="slow_burn"),
        patch("run_dashboard.compute_regime_adjusted_composite", return_value=(45.0, "")),
        patch("src.alerts.get_postmortem_stats", return_value={}),
    ]

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        yield {
            "log_run": log_run_m,
            "prune_history": prune_hist_m,
            "score_past_alerts": score_past_m,
            "send_alerts": send_alerts_m,
            "send_weekly_digest": send_digest_m,
            "send_heartbeat": send_hb_m,
            "write_dashboard": write_dash_m,
            "write_latest_sidecar": write_side_m,
        }


def _run(_argv):
    import run_dashboard
    run_dashboard.main()


def test_ondemand_skips_log_run():
    argv = ["run_dashboard.py", "--ondemand", "--quiet"]
    with _patched_main(argv) as m:
        _run(argv)
    m["log_run"].assert_not_called()
    m["prune_history"].assert_not_called()


def test_ondemand_skips_send_alerts():
    argv = ["run_dashboard.py", "--ondemand", "--quiet"]
    with _patched_main(argv) as m:
        _run(argv)
    m["send_alerts"].assert_not_called()
    m["send_weekly_digest"].assert_not_called()
    m["score_past_alerts"].assert_not_called()


def test_ondemand_calls_write_dashboard():
    argv = ["run_dashboard.py", "--ondemand", "--quiet"]
    with _patched_main(argv) as m:
        _run(argv)
    m["write_dashboard"].assert_called_once()


def test_ondemand_calls_write_latest_sidecar():
    argv = ["run_dashboard.py", "--ondemand", "--quiet"]
    with _patched_main(argv) as m:
        _run(argv)
    m["write_latest_sidecar"].assert_called_once()


def test_normal_run_calls_log_run():
    """Without --ondemand, log_run fires (regression guard)."""
    argv = ["run_dashboard.py", "--no-alerts", "--quiet"]
    with _patched_main(argv) as m:
        _run(argv)
    m["log_run"].assert_called_once()
