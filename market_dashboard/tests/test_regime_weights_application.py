"""Tests for Brief 10C — _apply_regime_weights in src/scoring.py."""
from __future__ import annotations

import pytest

from src.scoring import _apply_regime_weights


def _bucket_results(a_score: float = 80.0, b_score: float = 20.0) -> dict:
    return {
        "bucket_a": {"score": a_score, "weight": 0.6},
        "bucket_b": {"score": b_score, "weight": 0.4},
    }


def _rw_cfg(enabled: bool, high_mults: dict) -> dict:
    neutral = {"bucket_a": 1.0, "bucket_b": 1.0}
    return {
        "enabled": enabled,
        "classifier": {"type": "vix_tercile", "smoothing_days": 5, "hysteresis_vix": 1.0},
        "multipliers": {"low": neutral, "mid": neutral, "high": high_mults},
    }


def test_regime_disabled_returns_naive():
    """With enabled=false, composite_regime_weighted is computed but applied=False."""
    cfg = _rw_cfg(enabled=False, high_mults={"bucket_a": 2.0, "bucket_b": 0.5})
    result = _apply_regime_weights(_bucket_results(), cfg, "high")

    assert result["applied"] is False
    assert result["error"] is None
    # composite_regime_weighted is still calculated (for side-by-side display)
    # With bucket_a=80 at 2x weight and bucket_b=20 at 0.5x:
    # adj_weights: a=1.2, b=0.2 → total=1.4
    # weighted = (80 * 1.2 + 20 * 0.2) / 1.4 = (96 + 4) / 1.4 ≈ 71.4
    assert result["composite_regime_weighted"] != pytest.approx(
        0.6 * 80.0 + 0.4 * 20.0  # naive = 56.0
    )


def test_regime_enabled_applies_multipliers():
    """With enabled=true and 2x on high-stress bucket, composite shifts upward."""
    cfg = _rw_cfg(enabled=True, high_mults={"bucket_a": 2.0, "bucket_b": 1.0})
    buckets = _bucket_results(a_score=80.0, b_score=20.0)
    result = _apply_regime_weights(buckets, cfg, "high")

    assert result["applied"] is True
    naive = 0.6 * 80.0 + 0.4 * 20.0  # 56.0
    # Doubling bucket_a (high score) should push composite above naive
    assert result["composite_regime_weighted"] > naive


def test_regime_renormalisation_preserves_range():
    """All multipliers = 2.0 — composite must still be in [0, 100]."""
    cfg = _rw_cfg(enabled=True, high_mults={"bucket_a": 2.0, "bucket_b": 2.0})
    buckets = _bucket_results(a_score=100.0, b_score=100.0)
    result = _apply_regime_weights(buckets, cfg, "high")

    assert 0.0 <= result["composite_regime_weighted"] <= 100.0
    assert result["error"] is None
