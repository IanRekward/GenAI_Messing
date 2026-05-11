import json
import re
from pathlib import Path

import pytest

from src.history import write_latest_sidecar, SIDECAR_SCHEMA_VERSION

REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version", "run_timestamp", "composite", "composite_naive",
    "composite_regime_weighted", "regime_weights_applied", "composite_band",
    "composite_short", "composite_short_band", "composite_regime_adj",
    "composite_regime_adj_label", "regime", "shock_type",
    "red_count", "orange_count", "yellow_count",
    "stale_indicators", "errors", "buckets",
    "weights_hash", "code_sha",
}

_MINIMAL_SCORING = {
    "run_timestamp": "2026-05-11T07:30:00",
    "composite": 49.8,
    "composite_naive": 49.8,
    "composite_regime_weighted": 49.8,
    "regime_weights_applied": False,
    "composite_band": "orange",
    "composite_short": 51.2,
    "composite_short_band": "orange",
    "composite_regime_adj": 52.1,
    "composite_regime_adj_label": "+2.3 velocity premium",
    "regime": "mid",
    "red_count": 1,
    "orange_count": 0,
    "yellow_count": 4,
    "stale_indicators": ["cpi_yoy"],
    "errors": [],
    "buckets": {
        "equity_volatility": {
            "label": "Equity Volatility",
            "weight": 0.13,
            "score": 67.1,
            "score_short": 62.4,
            "band": "orange",
            "indicators": {
                "vix": {
                    "label": "VIX",
                    "raw": 18.42,
                    "zscore": 0.31,
                    "percentile": 64.5,
                    "percentile_short": 58.9,
                    "score": 64.5,
                    "score_short": 58.9,
                    "band": "orange",
                    "unit": "",
                    "manual": False,
                    "invert": False,
                    "_series": {"dates": ["2026-05-01", "2026-05-02"], "values": [17.0, 18.42]},
                }
            },
        }
    },
}


def test_sidecar_written(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    write_latest_sidecar(_MINIMAL_SCORING.copy(), shock_type="slow_burn")

    sidecar = tmp_path / "data" / "latest.json"
    assert sidecar.exists()
    payload = json.loads(sidecar.read_text())
    assert payload["schema_version"] == SIDECAR_SCHEMA_VERSION
    assert payload["schema_version"] == 1


def test_sidecar_required_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    write_latest_sidecar(_MINIMAL_SCORING.copy(), shock_type="calm")

    payload = json.loads((tmp_path / "data" / "latest.json").read_text())
    missing = REQUIRED_TOP_LEVEL_KEYS - set(payload.keys())
    assert not missing, f"Missing top-level keys: {missing}"


def test_sidecar_strips_series(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    write_latest_sidecar(_MINIMAL_SCORING.copy(), shock_type=None)

    payload = json.loads((tmp_path / "data" / "latest.json").read_text())
    for bkey, bucket in payload["buckets"].items():
        for ikey, ind in bucket["indicators"].items():
            assert "_series" not in ind, f"_series found in {bkey}.{ikey}"


def test_sidecar_shock_type_passed_through(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    write_latest_sidecar(_MINIMAL_SCORING.copy(), shock_type="fast_shock")

    payload = json.loads((tmp_path / "data" / "latest.json").read_text())
    assert payload["shock_type"] == "fast_shock"


def test_sidecar_weights_hash_format(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    write_latest_sidecar(_MINIMAL_SCORING.copy(), shock_type=None)

    payload = json.loads((tmp_path / "data" / "latest.json").read_text())
    wh = payload["weights_hash"]
    assert wh == "" or re.fullmatch(r"[0-9a-f]{8}", wh), f"Unexpected weights_hash: {wh!r}"


def test_sidecar_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    write_latest_sidecar(_MINIMAL_SCORING.copy(), shock_type="calm")
    write_latest_sidecar(_MINIMAL_SCORING.copy(), shock_type="slow_burn")

    sidecar = tmp_path / "data" / "latest.json"
    payload = json.loads(sidecar.read_text())
    assert payload["shock_type"] == "slow_burn"
    assert payload["schema_version"] == 1
