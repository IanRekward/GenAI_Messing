"""Pre-flight health checks for Entry and Exit scheduled tasks.

Story 1b.4 + 1b.5: validate system state before any trade logic runs. Broken state
surfaces as a clean ABORT (return False + reason) rather than a partial bad trade.

`check_entry()` runs 5 checks short-circuit-on-first-failure:
    1. .env keys (ALPACA_API_KEY, ALPACA_SECRET_KEY) are set
    2. Alpaca account reachable + ACTIVE + trading_blocked=False
    3. MICRO theses.jsonl exists and was written today (UTC date)
    4. MACRO validates — "stale" is OK (degrades to neutral), only broken/missing fails
    5. Kill switch placeholder (real implementation in Story 1c.5)

`check_exit()` runs 2 checks: .env keys + Alpaca reachable + ACTIVE.

Any check that raises gets wrapped into a `preflight_check_X_raised:` failure reason.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import account_state
import macro_consumer
import risk
from alpaca_connector import trading_client
from order_builder import THESES_PATH


def _check_env_keys() -> tuple[bool, str]:
    for key in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"):
        if not os.environ.get(key):
            return False, f"env_key_missing: {key}"
    return True, "ok"


def _check_alpaca_account() -> tuple[bool, str]:
    client = trading_client()
    account = client.get_account()
    status = str(account.status)
    if "ACTIVE" not in status:
        return False, f"alpaca_account_not_active: status={status}"
    if account.trading_blocked:
        return False, "alpaca_trading_blocked"
    return True, "ok"


def _check_micro_freshness() -> tuple[bool, str]:
    if not THESES_PATH.exists():
        return False, f"micro_theses_file_missing: {THESES_PATH}"
    # Written today (UTC). MICRO publishes ~06:30 ET (11:30 UTC) so file mtime
    # should be today by the time Entry fires at 13:35 UTC.
    mtime = datetime.fromtimestamp(THESES_PATH.stat().st_mtime, tz=timezone.utc)
    today = datetime.now(timezone.utc).date()
    if mtime.date() != today:
        return False, f"micro_theses_stale: last_mtime={mtime.date().isoformat()}, today={today.isoformat()}"
    return True, "ok"


def _check_macro() -> tuple[bool, str]:
    ok, reason, _data = macro_consumer.validate()
    if not ok:
        return False, f"macro_broken: {reason}"
    # ok==True covers both "ok" and "macro_stale_Nh_treating_as_neutral" — both are acceptable
    # because stale degrades to neutral rather than blocking trading.
    return True, "ok"


def _check_kill_switch() -> tuple[bool, str]:
    """Story 1c.5 + Story 2.4: block new entries on drawdown OR consecutive losses.

    Fetches current_equity from Alpaca (second call this run — checks 1-4 have already
    passed so the account is known reachable). Loads peak_equity from account_state.json
    and trades from trades.jsonl. Both checks must pass.
    """
    account = trading_client().get_account()
    current_equity = float(account.equity)
    state, init_reason = account_state.load_or_init(current_equity)

    # Story 1c.5: drawdown check
    ok, reason = risk.check_kill_switch(current_equity, state)
    if not ok:
        return ok, reason

    # Story 2.4: consecutive-loss check
    import json
    from trade_logger import TRADES_PATH
    trades = []
    if TRADES_PATH.exists():
        with open(TRADES_PATH) as f:
            trades = [json.loads(line) for line in f if line.strip()]
    ok, reason = risk.check_consecutive_losses(trades)
    if not ok:
        return ok, reason

    if init_reason and init_reason.startswith("reinitialized_from_corrupt"):
        return True, f"ok_kill_switch_state_{init_reason}"
    return True, "ok"


_ENTRY_CHECKS = (
    ("env_keys", _check_env_keys),
    ("alpaca_account", _check_alpaca_account),
    ("micro_freshness", _check_micro_freshness),
    ("macro", _check_macro),
    ("kill_switch", _check_kill_switch),
)

_EXIT_CHECKS = (
    ("env_keys", _check_env_keys),
    ("alpaca_account", _check_alpaca_account),
)


def _run_checks(checks: tuple) -> tuple[bool, str]:
    for name, fn in checks:
        try:
            ok, reason = fn()
        except Exception as e:
            return False, f"preflight_check_{name}_raised: {type(e).__name__}: {e}"
        if not ok:
            return False, reason
    return True, "ok"


def check_entry() -> tuple[bool, str]:
    return _run_checks(_ENTRY_CHECKS)


def check_exit() -> tuple[bool, str]:
    return _run_checks(_EXIT_CHECKS)
