"""Tests for Brief 17 — stale data + data quality auto-remediation."""
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from dotenv import load_dotenv

from src.scoring import compute_composite, load_weights, load_thresholds
from src.triggers import annotate_results
from src.fetch import load_manual_overrides
from src.history import log_run, load_history
from run_dashboard import (
    _indicator_source_type,
    _log_remediation,
)


def _live_env() -> dict:
    """Build an env dict with .env credentials for live-network tests."""
    load_dotenv()
    if not os.environ.get("FRED_API_KEY"):
        pytest.skip("FRED_API_KEY not set — live network test")
    return {**os.environ, "CACHE_HOURS": "12"}


@pytest.mark.live
def test_remediation_triggers_on_percentile_none():
    """Remediation triggers when percentile: None indicators are present."""
    weights = load_weights("config/weights.yaml")
    thresholds = load_thresholds("config/thresholds.yaml")
    manual = load_manual_overrides()
    env = _live_env()

    # Score normally
    scoring = compute_composite(weights, env, manual)
    scoring = annotate_results(scoring, thresholds)

    # Inject a failed fetch (None percentile) by editing the scoring
    found_one = False
    for bdata in scoring["buckets"].values():
        for ind in bdata["indicators"].values():
            if ind.get("percentile") is not None:
                ind["percentile"] = None
                found_one = True
                break
        if found_one:
            break

    assert found_one, "Test setup: should have injected at least one failed indicator"

    # Check that remediation would trigger
    failed_keys = {
        ikey
        for bdata in scoring["buckets"].values()
        for ikey, ind in bdata["indicators"].items()
        if ind.get("percentile") is None
    }
    assert len(failed_keys) > 0, "Should detect failed indicators"

    # Verify these are non-computed (can be remediated)
    remediation_keys = {
        k for k in failed_keys
        if _indicator_source_type(weights, k) != "computed"
    }
    assert len(remediation_keys) > 0, "Should have non-computed remediation candidates"


@pytest.mark.live
def test_remediation_triggers_on_stale_indicators():
    """Remediation triggers when stale_indicators is non-empty."""
    weights = load_weights("config/weights.yaml")
    thresholds = load_thresholds("config/thresholds.yaml")
    manual = load_manual_overrides()
    env = _live_env()

    # Score normally
    scoring = compute_composite(weights, env, manual)
    scoring = annotate_results(scoring, thresholds)

    # Inject stale indicators list
    scoring["stale_indicators"] = ["vix"]  # Assume vix exists and is not computed
    stale_keys = set(scoring.get("stale_indicators", []))

    assert len(stale_keys) > 0, "Test setup: should have stale indicators"

    # Check that remediation would trigger
    remediation_keys = {
        k for k in stale_keys
        if _indicator_source_type(weights, k) != "computed"
    }
    assert len(remediation_keys) > 0, "Should have non-computed stale candidates"


@pytest.mark.live
def test_remediation_skipped_on_clean_run():
    """No indicators have a failed fetch (percentile=None) on a clean cached run.

    Note: stale_indicators may be non-empty for weekly FRED series (STLFSI,
    jobless_claims) — that's expected and not a failure. This test checks only
    that no indicator has a fetch error (percentile=None), which is what would
    cause spurious remediation on a healthy run.
    """
    weights = load_weights("config/weights.yaml")
    thresholds = load_thresholds("config/thresholds.yaml")
    manual = load_manual_overrides()
    env = _live_env()

    scoring = compute_composite(weights, env, manual)
    scoring = annotate_results(scoring, thresholds)

    failed_keys = {
        ikey
        for bdata in scoring["buckets"].values()
        for ikey, ind in bdata["indicators"].items()
        if ind.get("percentile") is None
    }
    fetch_failure_remediation_keys = {
        k for k in failed_keys
        if _indicator_source_type(weights, k) != "computed"
    }

    assert len(fetch_failure_remediation_keys) == 0, (
        f"Clean run should have no fetch-failure remediation candidates; "
        f"got: {fetch_failure_remediation_keys}"
    )


def test_computed_indicators_excluded_from_remediation():
    """Computed-type indicators are excluded from remediation_keys."""
    weights = load_weights("config/weights.yaml")

    # Find a computed indicator
    computed_keys = []
    for bdata in weights.get("buckets", {}).values():
        for ikey, ind in bdata.get("indicators", {}).items():
            if ind.get("source", {}).get("type") == "computed":
                computed_keys.append(ikey)

    assert len(computed_keys) > 0, "Test setup: should have at least one computed indicator"

    # Verify _indicator_source_type returns "computed"
    for key in computed_keys:
        assert _indicator_source_type(weights, key) == "computed"


def test_log_remediation_writes_jsonl(tmp_path, monkeypatch):
    """_log_remediation() writes properly formatted JSONL entries."""
    monkeypatch.chdir(tmp_path)
    _log_remediation("vix", "success", "stale")
    _log_remediation("hy_oas", "failed", "percentile_none")

    alert_log = Path("data/alert_log.jsonl")
    assert alert_log.exists()

    lines = alert_log.read_text().strip().split("\n")
    rem_lines = [json.loads(l) for l in lines if l and "remediation_attempt" in l]

    assert len(rem_lines) >= 2, "Should have at least 2 remediation lines"
    assert rem_lines[-2]["indicator"] == "vix"
    assert rem_lines[-2]["outcome"] == "success"
    assert rem_lines[-2]["reason"] == "stale"
    assert rem_lines[-1]["indicator"] == "hy_oas"
    assert rem_lines[-1]["outcome"] == "failed"
    assert rem_lines[-1]["reason"] == "percentile_none"


@pytest.mark.live
def test_history_csv_single_row_per_run(tmp_path, monkeypatch):
    """Regression check: exactly one row appended per log_run cycle.

    Live fetches, but logs to a tmp COPY of history.csv — this test wrote a
    real production row on 2026-09-02 before the tripwire caught it.
    """
    import shutil
    real = Path("data/history.csv")
    tmp_csv = tmp_path / "history.csv"
    if real.exists():
        shutil.copy2(real, tmp_csv)
        initial_lines = len(tmp_csv.read_text().strip().split("\n"))
    else:
        initial_lines = 0
    monkeypatch.setattr("src.history.HISTORY_FILE", tmp_csv)
    monkeypatch.setattr("src.history.DATA_DIR", tmp_path)

    weights = load_weights("config/weights.yaml")
    thresholds = load_thresholds("config/thresholds.yaml")
    manual = load_manual_overrides()
    env = _live_env()

    # Single compute + annotate + log_run cycle
    scoring = compute_composite(weights, env, manual)
    scoring = annotate_results(scoring, thresholds)
    log_run(scoring)

    final_lines = len(tmp_csv.read_text().strip().split("\n"))
    assert final_lines == max(initial_lines, 1) + 1, "Should append exactly one row"


def test_indicator_source_type_helper():
    """_indicator_source_type() walks weights correctly."""
    weights = load_weights("config/weights.yaml")

    # Test finding a real indicator
    result = _indicator_source_type(weights, "vix")
    assert result in ["yfinance", "fred", "computed", "manual"], f"Got {result}"

    # Test missing indicator
    result = _indicator_source_type(weights, "nonexistent_key_xyz")
    assert result == "", "Should return empty string for missing indicator"
