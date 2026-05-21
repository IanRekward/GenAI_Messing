"""Story 1c.4: persist the all-time peak account equity for the drawdown kill switch.

Single small JSON file at `data/account_state.json`. Operator can delete or edit
to manually reset the high-water-mark after a deposit / withdrawal.

Schema:
    {
      "peak_equity": float,
      "peak_timestamp": ISO-8601 UTC string,
      "last_updated": ISO-8601 UTC string
    }
"""
import json
from datetime import datetime, timezone
from pathlib import Path

ACCOUNT_STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "account_state.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_or_init(current_equity: float) -> tuple[dict, str | None]:
    """Read account state from disk. If missing or corrupt, initialize with current_equity
    and persist immediately.

    Returns (state, init_reason_or_none). init_reason is non-None when we had to
    initialize — caller may Pushover-alert if reason indicates a corrupt-file recovery.
    """
    if not ACCOUNT_STATE_PATH.exists():
        state = {
            "peak_equity": current_equity,
            "peak_timestamp": _now_iso(),
            "last_updated": _now_iso(),
        }
        _persist(state)
        return state, "initialized_from_missing"

    try:
        with open(ACCOUNT_STATE_PATH) as f:
            state = json.load(f)
        if not isinstance(state.get("peak_equity"), (int, float)) or state["peak_equity"] <= 0:
            raise ValueError(f"peak_equity invalid: {state.get('peak_equity')!r}")
        return state, None
    except (json.JSONDecodeError, OSError, ValueError) as e:
        # Corrupt or unreadable — re-init with current equity, surface to caller for alert
        state = {
            "peak_equity": current_equity,
            "peak_timestamp": _now_iso(),
            "last_updated": _now_iso(),
        }
        _persist(state)
        return state, f"reinitialized_from_corrupt: {e}"


def update_peak_if_higher(state: dict, current_equity: float) -> tuple[dict, bool]:
    """If current_equity exceeds the recorded peak, update + persist. Returns (state, was_updated)."""
    if current_equity > state.get("peak_equity", 0):
        state = {
            **state,
            "peak_equity": current_equity,
            "peak_timestamp": _now_iso(),
            "last_updated": _now_iso(),
        }
        _persist(state)
        return state, True
    return state, False


def _persist(state: dict) -> None:
    ACCOUNT_STATE_PATH.parent.mkdir(exist_ok=True)
    with open(ACCOUNT_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)
