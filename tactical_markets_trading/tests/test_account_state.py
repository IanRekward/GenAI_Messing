"""Tests for src/account_state.py — Story 1c.4 high-water-mark persistence."""
import json

import pytest

import account_state


@pytest.fixture
def isolated_path(tmp_path, monkeypatch):
    path = tmp_path / "account_state.json"
    monkeypatch.setattr(account_state, "ACCOUNT_STATE_PATH", path)
    return path


def test_load_or_init_creates_file_with_current_equity_when_missing(isolated_path):
    state, init_reason = account_state.load_or_init(100_000.0)
    assert init_reason == "initialized_from_missing"
    assert state["peak_equity"] == 100_000.0
    assert "peak_timestamp" in state
    assert isolated_path.exists()
    with open(isolated_path) as f:
        on_disk = json.load(f)
    assert on_disk["peak_equity"] == 100_000.0


def test_load_or_init_reads_existing_file(isolated_path):
    isolated_path.write_text(json.dumps({
        "peak_equity": 105_000.0,
        "peak_timestamp": "2026-05-15T13:30:00+00:00",
        "last_updated": "2026-05-15T13:30:00+00:00",
    }))
    state, init_reason = account_state.load_or_init(100_000.0)
    assert init_reason is None
    assert state["peak_equity"] == 105_000.0


def test_load_or_init_reinits_on_corrupt_file(isolated_path):
    isolated_path.write_text("{not valid json")
    state, init_reason = account_state.load_or_init(100_000.0)
    assert init_reason.startswith("reinitialized_from_corrupt")
    assert state["peak_equity"] == 100_000.0


def test_load_or_init_reinits_when_peak_equity_invalid(isolated_path):
    isolated_path.write_text(json.dumps({"peak_equity": "not_a_number"}))
    state, init_reason = account_state.load_or_init(100_000.0)
    assert init_reason.startswith("reinitialized_from_corrupt")
    assert state["peak_equity"] == 100_000.0


def test_load_or_init_reinits_when_peak_equity_zero_or_negative(isolated_path):
    isolated_path.write_text(json.dumps({"peak_equity": 0}))
    state, init_reason = account_state.load_or_init(100_000.0)
    assert init_reason.startswith("reinitialized_from_corrupt")


def test_update_peak_if_higher_persists_new_peak(isolated_path):
    state, _ = account_state.load_or_init(100_000.0)
    new_state, updated = account_state.update_peak_if_higher(state, 110_000.0)
    assert updated is True
    assert new_state["peak_equity"] == 110_000.0
    with open(isolated_path) as f:
        on_disk = json.load(f)
    assert on_disk["peak_equity"] == 110_000.0


def test_update_peak_if_higher_no_change_when_current_below_peak(isolated_path):
    state, _ = account_state.load_or_init(100_000.0)
    new_state, updated = account_state.update_peak_if_higher(state, 95_000.0)
    assert updated is False
    assert new_state["peak_equity"] == 100_000.0


def test_update_peak_if_higher_no_change_when_current_equals_peak(isolated_path):
    state, _ = account_state.load_or_init(100_000.0)
    new_state, updated = account_state.update_peak_if_higher(state, 100_000.0)
    assert updated is False
    assert new_state["peak_equity"] == 100_000.0
