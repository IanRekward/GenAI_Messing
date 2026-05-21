"""Tests for src/preflight.py — Story 1b.4 pre-flight health checks.

Pure unit tests with monkeypatched env, Alpaca client, MICRO file mtime, and MACRO validator.
No real I/O. All 5 entry checks + 2 exit checks covered.
"""
import time
from datetime import datetime, timedelta, timezone

import pytest

import preflight


class FakeAccount:
    def __init__(self, status="ACTIVE", trading_blocked=False, equity=100_000.0):
        self.status = status
        self.trading_blocked = trading_blocked
        self.equity = equity


class FakeClient:
    def __init__(self, account=None, raises=False):
        self._account = account or FakeAccount()
        self._raises = raises

    def get_account(self):
        if self._raises:
            raise RuntimeError("alpaca unreachable")
        return self._account


@pytest.fixture
def fresh_env(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")


@pytest.fixture
def fresh_micro(monkeypatch, tmp_path):
    """Touch a fake theses.jsonl with today's mtime."""
    theses = tmp_path / "theses.jsonl"
    theses.write_text('{"signal": true, "buy": "XLK"}\n')
    monkeypatch.setattr(preflight, "THESES_PATH", theses)
    return theses


@pytest.fixture
def happy_macro(monkeypatch):
    monkeypatch.setattr(preflight.macro_consumer, "validate", lambda: (True, "ok", {"composite_band": "yellow"}))


@pytest.fixture
def happy_alpaca(monkeypatch):
    monkeypatch.setattr(preflight, "trading_client", lambda: FakeClient())


@pytest.fixture
def isolated_account_state(monkeypatch, tmp_path):
    """Story 1c.5 wired check_kill_switch reads/writes account_state.json — isolate to tmp."""
    monkeypatch.setattr(preflight.account_state, "ACCOUNT_STATE_PATH", tmp_path / "account_state.json")
    return tmp_path / "account_state.json"


# check_entry — happy path


def test_check_entry_passes_when_all_checks_ok(fresh_env, fresh_micro, happy_macro, happy_alpaca, isolated_account_state):
    ok, reason = preflight.check_entry()
    assert ok
    assert reason == "ok"


# check_entry — failure paths


def test_check_entry_fails_when_env_key_missing(monkeypatch, fresh_micro, happy_macro, happy_alpaca):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    ok, reason = preflight.check_entry()
    assert not ok
    assert "env_key_missing: ALPACA_API_KEY" in reason


def test_check_entry_fails_when_alpaca_account_not_active(monkeypatch, fresh_env, fresh_micro, happy_macro):
    monkeypatch.setattr(preflight, "trading_client", lambda: FakeClient(account=FakeAccount(status="SUSPENDED")))
    ok, reason = preflight.check_entry()
    assert not ok
    assert "alpaca_account_not_active" in reason


def test_check_entry_fails_when_trading_blocked(monkeypatch, fresh_env, fresh_micro, happy_macro):
    monkeypatch.setattr(preflight, "trading_client", lambda: FakeClient(account=FakeAccount(trading_blocked=True)))
    ok, reason = preflight.check_entry()
    assert not ok
    assert "alpaca_trading_blocked" in reason


def test_check_entry_fails_when_alpaca_call_raises(monkeypatch, fresh_env, fresh_micro, happy_macro):
    monkeypatch.setattr(preflight, "trading_client", lambda: FakeClient(raises=True))
    ok, reason = preflight.check_entry()
    assert not ok
    assert "preflight_check_alpaca_account_raised" in reason


def test_check_entry_fails_when_micro_file_missing(monkeypatch, fresh_env, happy_alpaca, happy_macro, tmp_path):
    monkeypatch.setattr(preflight, "THESES_PATH", tmp_path / "does_not_exist.jsonl")
    ok, reason = preflight.check_entry()
    assert not ok
    assert "micro_theses_file_missing" in reason


def test_check_entry_fails_when_micro_file_stale(monkeypatch, fresh_env, happy_alpaca, happy_macro, tmp_path):
    """MICRO file mtime must be today (UTC)."""
    theses = tmp_path / "theses.jsonl"
    theses.write_text("{}")
    # Backdate mtime by 2 days
    two_days_ago = time.time() - (2 * 86400)
    import os
    os.utime(theses, (two_days_ago, two_days_ago))
    monkeypatch.setattr(preflight, "THESES_PATH", theses)
    ok, reason = preflight.check_entry()
    assert not ok
    assert "micro_theses_stale" in reason


def test_check_entry_passes_on_macro_stale(monkeypatch, fresh_env, fresh_micro, happy_alpaca):
    """Stale MACRO is OK — degrades to neutral, not a block. Per Story 1b.2."""
    monkeypatch.setattr(preflight.macro_consumer, "validate",
                        lambda: (True, "macro_stale_5h_treating_as_neutral", {"neutralized": True}))
    ok, reason = preflight.check_entry()
    assert ok
    assert reason == "ok"


def test_check_entry_fails_on_macro_broken(monkeypatch, fresh_env, fresh_micro, happy_alpaca):
    """Broken / unknown / missing MACRO = block."""
    monkeypatch.setattr(preflight.macro_consumer, "validate",
                        lambda: (False, "macro_weights_hash_unknown: xyz", None))
    ok, reason = preflight.check_entry()
    assert not ok
    assert "macro_broken" in reason
    assert "macro_weights_hash_unknown" in reason


# check_exit — fewer checks


def test_check_exit_passes_with_env_and_alpaca(fresh_env, happy_alpaca):
    ok, reason = preflight.check_exit()
    assert ok
    assert reason == "ok"


def test_check_exit_fails_on_missing_env(monkeypatch, happy_alpaca):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    ok, reason = preflight.check_exit()
    assert not ok
    assert "env_key_missing" in reason


def test_check_exit_does_not_check_micro_or_macro(fresh_env, happy_alpaca, monkeypatch, tmp_path):
    """Exit task must run even when MICRO/MACRO are down — exits don't depend on regime."""
    # Wipe MICRO and MACRO state — exit must still pass
    monkeypatch.setattr(preflight, "THESES_PATH", tmp_path / "does_not_exist.jsonl")
    monkeypatch.setattr(preflight.macro_consumer, "validate", lambda: (False, "macro_file_missing", None))
    ok, reason = preflight.check_exit()
    assert ok


# Story 1c.5: kill switch wired into preflight check 5


def test_check_entry_fails_when_kill_switch_tripped(fresh_env, fresh_micro, happy_macro, monkeypatch, tmp_path):
    """Account in 25% drawdown -> kill switch trips -> check_entry fails."""
    # Set up peak_equity = $100k on disk
    state_path = tmp_path / "account_state.json"
    import json
    state_path.write_text(json.dumps({
        "peak_equity": 100_000.0,
        "peak_timestamp": "2026-05-01T00:00:00+00:00",
        "last_updated": "2026-05-01T00:00:00+00:00",
    }))
    monkeypatch.setattr(preflight.account_state, "ACCOUNT_STATE_PATH", state_path)
    # Current equity = $75k = 25% drawdown
    monkeypatch.setattr(preflight, "trading_client", lambda: FakeClient(account=FakeAccount(equity=75_000.0)))
    ok, reason = preflight.check_entry()
    assert not ok
    assert "kill_switch_drawdown" in reason
    assert "25.00%" in reason


def test_check_entry_passes_with_kill_switch_when_no_drawdown(fresh_env, fresh_micro, happy_macro, monkeypatch, tmp_path):
    """Account at new high-water-mark passes kill switch."""
    import json
    state_path = tmp_path / "account_state.json"
    state_path.write_text(json.dumps({
        "peak_equity": 100_000.0,
        "peak_timestamp": "2026-05-01T00:00:00+00:00",
        "last_updated": "2026-05-01T00:00:00+00:00",
    }))
    monkeypatch.setattr(preflight.account_state, "ACCOUNT_STATE_PATH", state_path)
    monkeypatch.setattr(preflight, "trading_client", lambda: FakeClient(account=FakeAccount(equity=110_000.0)))
    ok, reason = preflight.check_entry()
    assert ok
    assert reason == "ok"


def test_check_entry_initializes_account_state_when_missing(fresh_env, fresh_micro, happy_macro, monkeypatch, tmp_path):
    """First-run case: no account_state.json yet → init with current_equity, kill switch passes."""
    state_path = tmp_path / "account_state.json"
    assert not state_path.exists()
    monkeypatch.setattr(preflight.account_state, "ACCOUNT_STATE_PATH", state_path)
    monkeypatch.setattr(preflight, "trading_client", lambda: FakeClient(account=FakeAccount(equity=100_000.0)))
    ok, reason = preflight.check_entry()
    assert ok
    assert reason == "ok"
    # State file was created
    assert state_path.exists()
