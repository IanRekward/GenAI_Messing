"""Tests for src/config.py schema validation."""
from __future__ import annotations

import copy

import pytest

from src.config import ConfigError, validate_config
from src.scoring import load_weights, load_thresholds


@pytest.fixture
def valid_weights():
    return load_weights("config/weights.yaml")


@pytest.fixture
def valid_thresholds():
    return load_thresholds("config/thresholds.yaml")


def test_valid_config_passes(valid_weights, valid_thresholds):
    """Current config files must pass validation cleanly."""
    validate_config(valid_weights, valid_thresholds)  # should not raise


def test_bucket_weights_not_summing_raises(valid_weights, valid_thresholds):
    w = copy.deepcopy(valid_weights)
    first_bucket = next(iter(w["buckets"]))
    w["buckets"][first_bucket]["weight"] += 0.10  # sum now > 1.0
    with pytest.raises(ConfigError, match="sum"):
        validate_config(w, valid_thresholds)


def test_indicator_weights_not_summing_raises(valid_weights, valid_thresholds):
    w = copy.deepcopy(valid_weights)
    first_bucket = next(iter(w["buckets"]))
    first_ind = next(iter(w["buckets"][first_bucket]["indicators"]))
    w["buckets"][first_bucket]["indicators"][first_ind]["weight"] += 0.50
    with pytest.raises(ConfigError, match=first_bucket):
        validate_config(w, valid_thresholds)


def test_unknown_indicator_key_raises(valid_weights, valid_thresholds):
    w = copy.deepcopy(valid_weights)
    first_bucket = next(iter(w["buckets"]))
    w["buckets"][first_bucket]["indicators"]["nonexistent_indicator_xyz"] = {
        "label": "X", "weight": 0.0, "invert": False, "unit": ""
    }
    with pytest.raises(ConfigError, match="nonexistent_indicator_xyz"):
        validate_config(w, valid_thresholds)


def test_duplicate_indicator_key_raises(valid_weights, valid_thresholds):
    w = copy.deepcopy(valid_weights)
    buckets = list(w["buckets"].keys())
    if len(buckets) < 2:
        pytest.skip("need at least 2 buckets")
    # Copy vix into a second bucket with weight=0 so sum check doesn't fire first
    first_ind_key = next(iter(w["buckets"][buckets[0]]["indicators"]))
    first_ind_cfg = copy.deepcopy(w["buckets"][buckets[0]]["indicators"][first_ind_key])
    first_ind_cfg["weight"] = 0.0  # keeps bucket sum valid; duplicate check fires
    w["buckets"][buckets[1]]["indicators"][first_ind_key] = first_ind_cfg
    with pytest.raises(ConfigError, match=first_ind_key):
        validate_config(w, valid_thresholds)


def test_threshold_unknown_key_raises(valid_weights, valid_thresholds):
    t = copy.deepcopy(valid_thresholds)
    t.setdefault("indicators", {})["ghost_indicator"] = {
        "direction": "high", "yellow": 1, "orange": 2, "red": 3
    }
    with pytest.raises(ConfigError, match="ghost_indicator"):
        validate_config(valid_weights, t)


def test_no_buckets_raises():
    with pytest.raises(ConfigError):
        validate_config({"buckets": {}}, {})
