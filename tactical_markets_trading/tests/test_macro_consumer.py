"""Tests for src/macro_consumer.py — MACRO sidecar validation + size multiplier.

Uses monkeypatch + tmp_path to isolate from the real MACRO sidecar and allow-list.
No network, no filesystem-outside-tmp.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

import macro_consumer


# Helpers


def _write_sidecar(path, **overrides):
    """Write a valid MACRO sidecar JSON to path, with optional field overrides."""
    base = {
        "schema_version": 1,
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "composite": 50.0,
        "composite_band": "yellow",
        "regime": "mid",
        "weights_hash": "abc1234",
        "errors": [],
    }
    base.update(overrides)
    path.write_text(json.dumps(base))


def _write_allowlist(path, hashes):
    path.write_text(json.dumps({"allowed_hashes": hashes}))


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    """Redirect macro_consumer to use tmp paths for sidecar and allow-list."""
    sidecar = tmp_path / "latest.json"
    allowlist = tmp_path / "allowlist.json"
    monkeypatch.setattr(macro_consumer, "MACRO_SIDECAR_PATH", sidecar)
    monkeypatch.setattr(macro_consumer, "ALLOWLIST_PATH", allowlist)
    return sidecar, allowlist


# Story 1b.1: schema and content validation


def test_validate_ok_when_everything_clean(isolated_paths):
    sidecar, allowlist = isolated_paths
    _write_sidecar(sidecar, weights_hash="known_hash")
    _write_allowlist(allowlist, ["known_hash"])
    ok, reason, data = macro_consumer.validate()
    assert ok is True
    assert reason == "ok"
    assert data["composite_band"] == "yellow"
    assert data["regime"] == "mid"
    assert data["neutralized"] is False


def test_validate_blocks_when_file_missing(isolated_paths):
    sidecar, allowlist = isolated_paths
    _write_allowlist(allowlist, ["known_hash"])
    # don't write sidecar
    ok, reason, data = macro_consumer.validate()
    assert ok is False
    assert "macro_file_missing" in reason
    assert data is None


def test_validate_blocks_on_malformed_json(isolated_paths):
    sidecar, allowlist = isolated_paths
    sidecar.write_text("{not valid json")
    _write_allowlist(allowlist, ["known_hash"])
    ok, reason, data = macro_consumer.validate()
    assert ok is False
    assert "macro_file_malformed" in reason


def test_validate_blocks_on_schema_version_mismatch(isolated_paths):
    sidecar, allowlist = isolated_paths
    _write_sidecar(sidecar, schema_version=2, weights_hash="known_hash")
    _write_allowlist(allowlist, ["known_hash"])
    ok, reason, _ = macro_consumer.validate()
    assert ok is False
    assert "macro_schema_version_unexpected" in reason


def test_validate_blocks_on_non_empty_errors(isolated_paths):
    sidecar, allowlist = isolated_paths
    _write_sidecar(sidecar, weights_hash="known_hash", errors=["STALE: cpi_yoy"])
    _write_allowlist(allowlist, ["known_hash"])
    ok, reason, _ = macro_consumer.validate()
    assert ok is False
    assert "macro_errors" in reason


def test_validate_blocks_on_composite_out_of_range(isolated_paths):
    sidecar, allowlist = isolated_paths
    _write_sidecar(sidecar, composite=150.0, weights_hash="known_hash")
    _write_allowlist(allowlist, ["known_hash"])
    ok, reason, _ = macro_consumer.validate()
    assert ok is False
    assert "macro_composite_out_of_range" in reason


# Story 1b.2: staleness + provenance allow-list


def test_validate_stale_returns_neutral_after_4h(isolated_paths):
    sidecar, allowlist = isolated_paths
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    _write_sidecar(sidecar, run_timestamp=stale_ts, weights_hash="known_hash",
                   composite_band="red", regime="high")  # would be aggressive if not stale
    _write_allowlist(allowlist, ["known_hash"])
    ok, reason, data = macro_consumer.validate()
    assert ok is True  # stale is degrade, not block
    assert "macro_stale" in reason
    assert "treating_as_neutral" in reason
    assert data["neutralized"] is True


def test_validate_not_stale_at_3h(isolated_paths):
    sidecar, allowlist = isolated_paths
    fresh_ts = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    _write_sidecar(sidecar, run_timestamp=fresh_ts, weights_hash="known_hash")
    _write_allowlist(allowlist, ["known_hash"])
    ok, reason, data = macro_consumer.validate()
    assert ok is True
    assert reason == "ok"
    assert data["neutralized"] is False


def test_validate_blocks_on_unknown_weights_hash(isolated_paths):
    sidecar, allowlist = isolated_paths
    _write_sidecar(sidecar, weights_hash="surprise_new_hash")
    _write_allowlist(allowlist, ["known_hash_1", "known_hash_2"])
    ok, reason, _ = macro_consumer.validate()
    assert ok is False
    assert "macro_weights_hash_unknown" in reason
    assert "surprise_new_hash" in reason


def test_validate_blocks_when_allowlist_missing(isolated_paths):
    sidecar, allowlist = isolated_paths
    _write_sidecar(sidecar, weights_hash="known_hash")
    # don't write allowlist
    ok, reason, _ = macro_consumer.validate()
    assert ok is False
    assert "macro_weights_allowlist_missing" in reason


def test_validate_blocks_when_allowlist_malformed(isolated_paths):
    sidecar, allowlist = isolated_paths
    _write_sidecar(sidecar, weights_hash="known_hash")
    allowlist.write_text("{not json")
    ok, reason, _ = macro_consumer.validate()
    assert ok is False
    assert "macro_weights_allowlist_malformed" in reason


# Story 1b.3: size_multiplier


def test_size_multiplier_red_band_returns_zero():
    assert macro_consumer.size_multiplier({"composite_band": "red", "regime": "mid"}) == 0.0


def test_size_multiplier_orange_plus_high_regime_returns_half():
    assert macro_consumer.size_multiplier({"composite_band": "orange", "regime": "high"}) == 0.5


def test_size_multiplier_orange_plus_mid_regime_returns_full():
    assert macro_consumer.size_multiplier({"composite_band": "orange", "regime": "mid"}) == 1.0


def test_size_multiplier_green_returns_full():
    assert macro_consumer.size_multiplier({"composite_band": "green", "regime": "low"}) == 1.0


def test_size_multiplier_yellow_returns_full():
    assert macro_consumer.size_multiplier({"composite_band": "yellow", "regime": "mid"}) == 1.0


def test_size_multiplier_neutralized_overrides_red():
    # Stale data → neutralized=True → multiplier always 1.0, ignoring band/regime
    assert macro_consumer.size_multiplier({
        "composite_band": "red", "regime": "high", "neutralized": True,
    }) == 1.0
