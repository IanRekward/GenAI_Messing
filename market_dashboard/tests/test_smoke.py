"""End-to-end smoke test: load real config, mock network, verify output shape."""
from __future__ import annotations

import pandas as pd
import pytest

from src.scoring import compute_composite, load_weights, load_thresholds
from src.triggers import annotate_results


def _mock_fetch(key, cfg, env, manual):
    """Return neutral (50th percentile) values for every indicator."""
    if cfg.get("manual"):
        return float(manual.get(key, 0)), None
    # 100-element series, current = median → 50th percentile
    s = pd.Series(range(1, 101), dtype=float)
    return 50.0, s


def test_smoke_full_config(monkeypatch):
    """Real weights.yaml + thresholds.yaml, all indicators mocked to neutral."""
    monkeypatch.setattr("src.scoring._fetch_indicator", _mock_fetch)

    weights = load_weights("config/weights.yaml")
    thresholds = load_thresholds("config/thresholds.yaml")
    manual = {k: 0 for k in ["repo_stress", "aaii_bull_bear", "iran_trigger"]}
    env = {"HISTORY_YEARS": "10"}

    scoring = compute_composite(weights, env, manual)
    scoring = annotate_results(scoring, thresholds)

    # Shape checks
    assert "composite" in scoring
    assert "composite_band" in scoring
    assert "buckets" in scoring
    assert "errors" in scoring

    # All expected buckets present
    expected_buckets = set(weights["buckets"].keys())
    assert set(scoring["buckets"].keys()) == expected_buckets

    # Every bucket in weights.yaml has its indicators
    for bkey, bcfg in weights["buckets"].items():
        bucket = scoring["buckets"][bkey]
        for ikey in bcfg["indicators"]:
            assert ikey in bucket["indicators"], f"Missing indicator {bkey}.{ikey}"

    # Score is in valid range
    assert 0.0 <= scoring["composite"] <= 100.0

    # No fetch errors (all mocked to succeed)
    assert scoring["errors"] == [], f"Unexpected errors: {scoring['errors']}"

    # Composite band is one of the four valid bands
    assert scoring["composite_band"] in ("green", "yellow", "orange", "red")
