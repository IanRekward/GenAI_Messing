"""Tests for src/strategy_state.py — atomic per-strategy persistence."""
import json

import pytest

import strategy_state


@pytest.fixture
def isolated_state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(strategy_state, "STATE_DIR", tmp_path)
    return tmp_path


def test_load_missing_returns_empty(isolated_state_dir):
    assert strategy_state.load_state("noexist") == {}


def test_save_then_load_roundtrip(isolated_state_dir):
    state = {"in_position": True, "peak": 123.45, "list_field": [1, 2, 3]}
    strategy_state.save_state("test_strategy", state)
    loaded = strategy_state.load_state("test_strategy")
    assert loaded == state


def test_load_corrupt_returns_empty(isolated_state_dir):
    (isolated_state_dir / "strategy_state_corrupt.json").write_text("{not json")
    assert strategy_state.load_state("corrupt") == {}


def test_save_is_atomic_via_tmp_file(isolated_state_dir):
    strategy_state.save_state("atomic_test", {"x": 1})
    # The .tmp file shouldn't linger after a successful save
    assert not (isolated_state_dir / "strategy_state_atomic_test.json.tmp").exists()
    assert (isolated_state_dir / "strategy_state_atomic_test.json").exists()


def test_save_overwrites_existing(isolated_state_dir):
    strategy_state.save_state("over", {"v": 1})
    strategy_state.save_state("over", {"v": 2})
    assert strategy_state.load_state("over") == {"v": 2}
