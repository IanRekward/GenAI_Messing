"""Epic 3: Phase 2 graduation tracking.

Reads `data/trades.jsonl` and `data/drift_log.jsonl`, computes progress toward
the AR20 graduation criterion, and Pushovers once when the criterion is first met.

AR20 graduation criterion:
    total_closed_trades >= 20
  AND stop_fired_exits  >= 2
  AND macro_size_downs  >= 1
  AND drift_false_positives == 0

When met, Phase 3 design opens.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pushover
from trade_logger import TRADES_PATH
from reconciler import DRIFT_LOG

GRADUATION_STATE_PATH = TRADES_PATH.parent / "graduation_state.json"

REQUIRED_CLOSED_TRADES = 20
REQUIRED_STOP_EXITS = 2
REQUIRED_MACRO_SIZE_DOWNS = 1
REQUIRED_DRIFT_CLEAN = 0


def _load_trades() -> list[dict]:
    if not TRADES_PATH.exists():
        return []
    with open(TRADES_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


def _load_drift_events() -> list[dict]:
    if not DRIFT_LOG.exists():
        return []
    with open(DRIFT_LOG) as f:
        return [json.loads(line) for line in f if line.strip()]


def check_status() -> dict:
    """Story 3.1: count progress toward the graduation criterion."""
    trades = _load_trades()
    drift = _load_drift_events()

    closed = [t for t in trades if t.get("status") == "closed"]
    total_closed_trades = len(closed)
    stop_fired_exits = sum(1 for t in closed if t.get("exit_reason") == "stop_fired")

    macro_size_downs = 0
    for t in trades:
        snap = t.get("macro_snapshot")
        if not snap:
            continue
        if snap.get("neutralized"):
            continue  # neutralized doesn't count as a size-down — it's neutral by design
        band = snap.get("composite_band")
        regime = snap.get("regime")
        if band == "red" or (band == "orange" and regime == "high"):
            macro_size_downs += 1

    # Count only UNRESOLVED drift events. Resolved events stay in the audit trail
    # but don't block graduation (human has reviewed and marked benign).
    drift_false_positives = sum(1 for e in drift if not e.get("resolved"))

    criterion_met = (
        total_closed_trades >= REQUIRED_CLOSED_TRADES
        and stop_fired_exits >= REQUIRED_STOP_EXITS
        and macro_size_downs >= REQUIRED_MACRO_SIZE_DOWNS
        and drift_false_positives == REQUIRED_DRIFT_CLEAN
    )
    criterion_summary = (
        f"closed {total_closed_trades}/{REQUIRED_CLOSED_TRADES}, "
        f"stop_fired {stop_fired_exits}/{REQUIRED_STOP_EXITS}, "
        f"macro_size_downs {macro_size_downs}/{REQUIRED_MACRO_SIZE_DOWNS}, "
        f"drift_events {drift_false_positives}/{REQUIRED_DRIFT_CLEAN}"
    )

    return {
        "total_closed_trades": total_closed_trades,
        "stop_fired_exits": stop_fired_exits,
        "macro_size_downs": macro_size_downs,
        "drift_false_positives": drift_false_positives,
        "criterion_met": criterion_met,
        "criterion_summary": criterion_summary,
    }


def notify_if_met() -> bool:
    """Story 3.2: one-shot Pushover when graduation is first met.
    Returns True if a notification was sent this call, False otherwise.
    """
    status = check_status()
    if not status["criterion_met"]:
        return False

    state = {}
    if GRADUATION_STATE_PATH.exists():
        try:
            with open(GRADUATION_STATE_PATH) as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError):
            state = {}
    if state.get("already_notified"):
        return False

    pushover.send(
        "PHASE 2 GRADUATION MET",
        f"Graduation criterion satisfied. {status['criterion_summary']}. "
        f"Open Phase 3 design (rules-of-engagement + live capital sizing).",
    )
    GRADUATION_STATE_PATH.parent.mkdir(exist_ok=True)
    new_state = {
        "already_notified": True,
        "notified_at": datetime.now(timezone.utc).isoformat(),
        "status_when_notified": status,
    }
    with open(GRADUATION_STATE_PATH, "w") as f:
        json.dump(new_state, f, indent=2)
    return True


if __name__ == "__main__":
    from alpaca_connector import load_env
    load_env()
    status = check_status()
    print(f"Phase 2 graduation status:")
    print(f"  closed trades:       {status['total_closed_trades']} / {REQUIRED_CLOSED_TRADES}")
    print(f"  stop-fired exits:    {status['stop_fired_exits']} / {REQUIRED_STOP_EXITS}")
    print(f"  MACRO size-downs:    {status['macro_size_downs']} / {REQUIRED_MACRO_SIZE_DOWNS}")
    print(f"  drift events:        {status['drift_false_positives']} (must be 0)")
    print(f"  criterion met:       {status['criterion_met']}")
    if status["criterion_met"]:
        notified = notify_if_met()
        print(f"  notified this call:  {notified}")
