"""Tests for config/indicator_explainers.yaml coverage (Brief 18)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.config import KNOWN_INDICATOR_KEYS


def _load_explainers() -> dict:
    p = Path("config/indicator_explainers.yaml")
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("indicators", {})


def test_all_known_indicators_have_explainer_entry():
    explainers = _load_explainers()
    missing = [k for k in KNOWN_INDICATOR_KEYS if k not in explainers]
    assert not missing, f"Missing explainer entries for: {sorted(missing)}"


def test_all_explainer_entries_have_required_fields():
    explainers = _load_explainers()
    bad = []
    for key in KNOWN_INDICATOR_KEYS:
        entry = explainers.get(key, {})
        for field in ("advanced", "layman", "model_role"):
            if not entry.get(field, "").strip():
                bad.append(f"{key}.{field}")
    assert not bad, f"Empty or missing explainer fields: {bad}"


def test_no_oil_vol_explainer():
    """oil_vol was removed in Brief 19 — its explainer block should not exist."""
    explainers = _load_explainers()
    assert "oil_vol" not in explainers


def test_brief19_indicators_have_explainers():
    """crack_spread_321, natgas, copper_gold_ratio were pre-staged in the YAML."""
    explainers = _load_explainers()
    for key in ("crack_spread_321", "natgas", "copper_gold_ratio"):
        assert key in explainers, f"Missing pre-staged explainer for {key}"
        for field in ("advanced", "layman", "model_role"):
            assert explainers[key].get(field, "").strip(), f"Empty {field} for {key}"
