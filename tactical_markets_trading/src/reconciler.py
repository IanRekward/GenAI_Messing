"""Drift detection between local trades.jsonl and Alpaca state.

Detects two drift modes:

Mode 1: local "open" record but no (or smaller) matching Alpaca position.
    Cause: SELL filled on Alpaca but local close-persistence failed (e.g., wait_for_fill
    timed out and raised, or the close happened outside this system).
    Resolution: query Alpaca order history for the matching SELL and backfill the close
    in place. Idempotent — re-running on already-closed records is a no-op.

Mode 2: Alpaca position with no (or smaller) matching local "open" record.
    Cause: manual BUY, entry whose logging failed, or unknown origin.
    Resolution: ALERT ONLY. Reconciler will not synthesize records without provenance.

Designed to be safe to run on every entry and exit cycle. Idempotent. Pushover-alerts
on unresolvable drift only (not on successful backfills — those are normal recovery).

Usage:
    python src/reconciler.py             # reconcile and persist
    python src/reconciler.py --dry-run   # report only, write nothing
"""
import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alpaca.trading.enums import OrderSide, OrderStatus, QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest

import pushover
from alpaca_connector import load_env, trading_client
from trade_logger import TRADES_PATH

RECONCILER_LOG = TRADES_PATH.parent / "reconciler_log.jsonl"
DRIFT_LOG = TRADES_PATH.parent / "drift_log.jsonl"
QTY_EPSILON = 1e-6


def _load_records() -> list[dict]:
    if not TRADES_PATH.exists():
        return []
    with open(TRADES_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


def _save_records(records: list[dict]) -> None:
    TRADES_PATH.parent.mkdir(exist_ok=True)
    with open(TRADES_PATH, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _log_event(event: dict) -> None:
    RECONCILER_LOG.parent.mkdir(exist_ok=True)
    with open(RECONCILER_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")


def _resolved_trade_ids_for(event_type: str) -> set[str]:
    """Return trade_ids that have a resolved drift_log entry of the given type.
    Used to suppress repeat alerts on drift events the operator has already
    acknowledged + cleared."""
    if not DRIFT_LOG.exists():
        return set()
    out: set[str] = set()
    with open(DRIFT_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            if event.get("type") == event_type and event.get("resolved") and event.get("trade_id"):
                out.add(event["trade_id"])
    return out


def _resolved_untracked_positions() -> list[tuple[str, float]]:
    """Return (symbol, alpaca_qty) pairs from resolved untracked_alpaca_position
    drift_log entries. A new untracked detection matching one of these (qty within
    QTY_EPSILON) is suppressed — the operator already acknowledged it. If the
    untracked qty changes, the new value won't match and re-alerts."""
    if not DRIFT_LOG.exists():
        return []
    out: list[tuple[str, float]] = []
    with open(DRIFT_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            if (
                event.get("type") == "untracked_alpaca_position"
                and event.get("resolved")
                and event.get("symbol")
                and event.get("alpaca_qty") is not None
            ):
                out.append((event["symbol"], float(event["alpaca_qty"])))
    return out


def _backfill_close(client, record: dict) -> tuple[dict | None, str | None]:
    """Find the SELL in Alpaca order history matching this local open record and
    build a closed-record dict. Returns (closed_dict, error_str)."""
    entry_time = datetime.fromisoformat(record["entry_time"])
    request = GetOrdersRequest(
        status=QueryOrderStatus.CLOSED,
        after=entry_time,
        side=OrderSide.SELL,
        symbols=[record["symbol"]],
    )
    sell_orders = list(client.get_orders(request))
    match = None
    for o in sell_orders:
        if o.status != OrderStatus.FILLED:
            continue
        if abs(float(o.filled_qty) - record["fill_qty"]) < QTY_EPSILON:
            match = o
            break
    if match is None:
        return None, f"no matching FILLED SELL for {record['symbol']} qty={record['fill_qty']} after {entry_time.isoformat()}"

    entry_cost = record["fill_price"] * record["fill_qty"]
    exit_proceeds = float(match.filled_avg_price) * float(match.filled_qty)
    closed = {
        **record,
        "exit_order_id": str(match.id),
        "exit_time_actual": str(match.filled_at),
        "exit_fill_price": float(match.filled_avg_price),
        "exit_fill_qty": float(match.filled_qty),
        "pnl_dollars": round(exit_proceeds - entry_cost, 2),
        "pnl_pct": round((exit_proceeds - entry_cost) / entry_cost * 100, 4),
        "spy_return_pct": None,  # backfill_benchmarks.py handles separately
        "sell_leg_return_pct": None,
        "status": "closed",
        # Story 1a.5 backward-compat: reconciler-recovered closes are tagged "scheduled"
        # (we don't know retroactively whether the SELL was the scheduled exit, a stop fire,
        # or a manual close; "scheduled" is the safe default per the story's read-fallback).
        "exit_reason": "scheduled",
        "reconciled": True,
        "reconciled_at": datetime.now(timezone.utc).isoformat(),
    }
    return closed, None


def reconcile(dry_run: bool = False) -> dict:
    client = trading_client()
    records = _load_records()
    local_open_idx = [i for i, r in enumerate(records) if r.get("status") == "open"]
    local_qty_by_symbol: dict[str, float] = {}
    local_records_by_symbol: dict[str, list[int]] = {}
    for i in local_open_idx:
        r = records[i]
        local_qty_by_symbol[r["symbol"]] = local_qty_by_symbol.get(r["symbol"], 0.0) + r["fill_qty"]
        local_records_by_symbol.setdefault(r["symbol"], []).append(i)

    # Account for known residuals left over on the broker after a partial close
    # (e.g., fractional share remainder after a whole-share GTC stop fires). These
    # are tracked on the closed trade record via partial_close_residual_qty so the
    # broker side isn't reported as drift. Cleared (set to 0) once the residual
    # is sold — see tools/close_orphan_xle_c3c7d90f.py for the pattern.
    for r in records:
        if r.get("status") == "closed":
            residual = r.get("partial_close_residual_qty") or 0
            if residual > 0:
                local_qty_by_symbol[r["symbol"]] = local_qty_by_symbol.get(r["symbol"], 0.0) + residual

    positions = client.get_all_positions()
    alpaca_qty_by_symbol = {p.symbol: float(p.qty) for p in positions}

    actions: list[dict] = []
    changed = False

    # Mode 1: local has open positions Alpaca doesn't (or has less of)
    for symbol, local_qty in local_qty_by_symbol.items():
        alpaca_qty = alpaca_qty_by_symbol.get(symbol, 0.0)
        if local_qty <= alpaca_qty + QTY_EPSILON:
            continue
        for i in local_records_by_symbol[symbol]:
            record = records[i]
            closed, error = _backfill_close(client, record)
            if error:
                actions.append({
                    "type": "drift_unresolvable",
                    "trade_id": record["trade_id"],
                    "symbol": symbol,
                    "error": error,
                })
                continue
            if not dry_run:
                records[i] = closed
                changed = True
            actions.append({
                "type": "backfilled_close",
                "trade_id": record["trade_id"],
                "symbol": symbol,
                "exit_order_id": closed["exit_order_id"],
                "pnl_dollars": closed["pnl_dollars"],
                "pnl_pct": closed["pnl_pct"],
            })

    # Mode 2: Alpaca has positions local doesn't (or has more of)
    for symbol, alpaca_qty in alpaca_qty_by_symbol.items():
        local_qty = local_qty_by_symbol.get(symbol, 0.0)
        if alpaca_qty <= local_qty + QTY_EPSILON:
            continue
        actions.append({
            "type": "untracked_alpaca_position",
            "symbol": symbol,
            "alpaca_qty": alpaca_qty,
            "local_qty": local_qty,
            "untracked_qty": alpaca_qty - local_qty,
            "resolution": "manual_investigation_required",
        })

    if changed and not dry_run:
        _save_records(records)

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "local_open_count": len(local_open_idx),
        "alpaca_position_count": len(positions),
        "actions": actions,
    }
    if not dry_run:
        _log_event(summary)

    # Suppress alerts for drift events already marked resolved in drift_log.jsonl.
    # Without this, a stuck event (e.g., partial close where stop covered floor(qty))
    # Pushovers on every reconcile run forever.
    resolved_trade_ids = _resolved_trade_ids_for("drift_unresolvable")
    resolved_untracked = _resolved_untracked_positions()

    def _is_resolved(a: dict) -> bool:
        if a["type"] == "drift_unresolvable" and a.get("trade_id") in resolved_trade_ids:
            return True
        if a["type"] == "untracked_alpaca_position":
            for sym, qty in resolved_untracked:
                if a.get("symbol") == sym and abs(float(a.get("alpaca_qty", 0)) - qty) < QTY_EPSILON:
                    return True
        return False

    alert_actions = [
        a for a in actions
        if a["type"] in ("drift_unresolvable", "untracked_alpaca_position") and not _is_resolved(a)
    ]
    if alert_actions and not dry_run:
        lines = []
        for a in alert_actions:
            if a["type"] == "drift_unresolvable":
                lines.append(f"unresolvable {a['symbol']} trade {a['trade_id'][:8]}: {a['error']}")
            elif a["type"] == "untracked_alpaca_position":
                lines.append(
                    f"untracked {a['symbol']} qty={a['untracked_qty']:.4f} "
                    f"(alpaca={a['alpaca_qty']} local={a['local_qty']})"
                )
            else:
                lines.append(json.dumps(a))
        pushover.send(
            f"Reconciler: {len(alert_actions)} drift event(s)",
            "\n".join(lines)[:1024],
        )

    return summary


def _print_summary(summary: dict) -> None:
    print(f"Reconciler @ {summary['timestamp']} (dry_run={summary['dry_run']})")
    print(f"  Local open: {summary['local_open_count']}, Alpaca positions: {summary['alpaca_position_count']}")
    if not summary["actions"]:
        print("  No drift detected.")
        return
    for a in summary["actions"]:
        t = a["type"]
        if t == "backfilled_close":
            print(f"  BACKFILLED close: {a['symbol']} trade {a['trade_id'][:8]} -> exit_order {a['exit_order_id'][:8]} pnl ${a['pnl_dollars']} ({a['pnl_pct']:+.2f}%)")
        elif t == "untracked_alpaca_position":
            print(f"  UNTRACKED Alpaca position: {a['symbol']} qty={a['untracked_qty']} (alpaca={a['alpaca_qty']} local={a['local_qty']}) - manual investigation required")
        elif t == "drift_unresolvable":
            print(f"  UNRESOLVABLE drift: {a['symbol']} trade {a['trade_id'][:8]} - {a['error']}")


# Story 2.1: read-only drift detection — returns canonical drift event types per spec.
# Distinct from reconcile() which performs active backfill + state mutation.


def report() -> list[dict]:
    """Story 2.1: read-only inventory of drift events.

    Queries Alpaca positions + open orders, loads local trades.jsonl, returns a list
    of drift events with canonical types:
      - "orphan_position":   Alpaca position with no matching local status=="open" record
      - "orphan_open_order": Alpaca open order with no matching record's stop_order_id
      - "missing_position":  local status=="open" record with no matching Alpaca position
      - "missing_stop_order": local status=="open" with stop_order_id set but not in Alpaca open orders

    Returns [] if no drift detected. No side effects.
    """
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    client = trading_client()
    positions = client.get_all_positions()
    open_orders = list(client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN)))
    records = _load_records()
    local_open = [r for r in records if r.get("status") == "open"]

    events: list[dict] = []

    # Build lookup: symbol -> total local open qty
    local_qty_by_symbol: dict[str, float] = {}
    for r in local_open:
        local_qty_by_symbol[r["symbol"]] = local_qty_by_symbol.get(r["symbol"], 0.0) + r["fill_qty"]

    # orphan_position: Alpaca holds something local doesn't track
    for p in positions:
        alpaca_qty = float(p.qty)
        local_qty = local_qty_by_symbol.get(p.symbol, 0.0)
        if alpaca_qty > local_qty + QTY_EPSILON:
            events.append({
                "type": "orphan_position",
                "symbol": p.symbol,
                "alpaca_qty": alpaca_qty,
                "local_qty": local_qty,
                "orphan_qty": alpaca_qty - local_qty,
            })

    # missing_position: local thinks open but Alpaca disagrees
    alpaca_qty_by_symbol = {p.symbol: float(p.qty) for p in positions}
    for r in local_open:
        alpaca_qty = alpaca_qty_by_symbol.get(r["symbol"], 0.0)
        if r["fill_qty"] > alpaca_qty + QTY_EPSILON:
            events.append({
                "type": "missing_position",
                "trade_id": r["trade_id"],
                "symbol": r["symbol"],
                "local_qty": r["fill_qty"],
                "alpaca_qty": alpaca_qty,
            })

    # orphan_open_order: Alpaca open order not tracked by any local record's stop_order_id
    # AND not an in-flight exit (market SELL for a symbol with a local open position).
    # The in-flight-exit case happens normally when exit_position submits a SELL that
    # queues for next market open — the order is alive on Alpaca but no record persists
    # its id until wait_for_fill returns.
    tracked_stop_ids = {r.get("stop_order_id") for r in records if r.get("stop_order_id")}
    local_open_symbols = {r["symbol"] for r in local_open}
    for o in open_orders:
        if str(o.id) in tracked_stop_ids:
            continue
        side = str(getattr(o, "side", ""))
        if "SELL" in side and o.symbol in local_open_symbols:
            continue  # in-flight exit, not orphan
        # In-flight MARKET orders are transient execution, not drift: a market order
        # seen "open" mid-reconcile fills (or rejects) within seconds. If it fills
        # into an untracked position, orphan_position catches it next cycle. Only
        # non-market open orders (stop/limit) we don't track are genuine orphans.
        # This kills the false-alarm pings for entry BUYs / stop SELLs still in flight.
        order_type = str(getattr(o, "order_type", ""))
        if "MARKET" in order_type.upper():
            continue
        events.append({
            "type": "orphan_open_order",
            "order_id": str(o.id),
            "symbol": o.symbol,
            "side": side,
            "qty": float(o.qty) if o.qty is not None else None,
            "order_type": str(getattr(o, "order_type", "")),
        })

    # missing_stop_order: local has stop_order_id but it's not in Alpaca's open orders
    open_order_ids = {str(o.id) for o in open_orders}
    for r in local_open:
        sid = r.get("stop_order_id")
        if sid and sid not in open_order_ids:
            events.append({
                "type": "missing_stop_order",
                "trade_id": r["trade_id"],
                "symbol": r["symbol"],
                "expected_stop_order_id": sid,
            })

    return events


def _event_signature(event: dict) -> tuple:
    """Stable identity for a drift event, used to dedupe repeat alerts. Two
    detections of the same underlying condition (same order, same orphan qty,
    same trade's missing stop) share a signature."""
    t = event.get("type")
    if t == "orphan_position":
        return (t, event.get("symbol"), round(float(event.get("orphan_qty", 0)), 6))
    if t == "missing_position":
        return (t, event.get("trade_id"), event.get("symbol"))
    if t == "orphan_open_order":
        return (t, event.get("order_id"))
    if t == "missing_stop_order":
        return (t, event.get("trade_id"), event.get("expected_stop_order_id"))
    return (t, json.dumps(event, sort_keys=True))


def notify_drift(drift_events: list[dict]) -> None:
    """Story 2.2: persist drift events to data/drift_log.jsonl and send one
    Pushover summary. Idempotent on empty input.

    Dedupes against events already in the drift log (resolved or not): a drift
    condition caught on consecutive cycles — or a transient in-flight order seen
    more than once — is logged + alerted only on first sighting, never re-pinged.
    Without this, persistent/recurring drift Pushovers every run.

    Each NEW event gets a unique event_id (UUID) + resolved=false + resolved_at=null
    + resolved_reason=null fields for the human-confirmation gate (resolve_event /
    resolve_all_unresolved). Graduation counts only unresolved events.
    """
    if not drift_events:
        return

    existing_signatures: set[tuple] = set()
    if DRIFT_LOG.exists():
        with open(DRIFT_LOG) as f:
            for line in f:
                line = line.strip()
                if line:
                    existing_signatures.add(_event_signature(json.loads(line)))

    drift_events = [e for e in drift_events if _event_signature(e) not in existing_signatures]
    if not drift_events:
        return

    detected_at = datetime.now(timezone.utc).isoformat()
    DRIFT_LOG.parent.mkdir(exist_ok=True)
    with open(DRIFT_LOG, "a") as f:
        for event in drift_events:
            f.write(json.dumps({
                **event,
                "event_id": str(uuid.uuid4()),
                "detected_at": detected_at,
                "resolved": False,
                "resolved_at": None,
                "resolved_reason": None,
            }) + "\n")
    # Pushover body — truncate to 1024 chars
    summary_lines = []
    for e in drift_events:
        t = e["type"]
        if t == "orphan_position":
            summary_lines.append(f"orphan_position {e['symbol']} aq={e['alpaca_qty']:.2f} lq={e['local_qty']:.2f}")
        elif t == "missing_position":
            summary_lines.append(f"missing_position {e['symbol']} trade {e['trade_id'][:8]} lq={e['local_qty']:.2f}")
        elif t == "orphan_open_order":
            summary_lines.append(f"orphan_open_order {e['symbol']} order {e['order_id'][:8]} {e['side']}")
        elif t == "missing_stop_order":
            summary_lines.append(f"missing_stop_order {e['symbol']} trade {e['trade_id'][:8]} stop {e['expected_stop_order_id'][:8]}")
        else:
            summary_lines.append(json.dumps(e))
    body = "\n".join(summary_lines)
    if len(body) > 1024:
        body = body[:1020] + "..."
    pushover.send(f"Tactical Trading DRIFT ({len(drift_events)} event(s))", body)


def report_and_notify() -> list[dict]:
    """Story 2.3 helper: convenience wrapper for the post-task pattern.
    Returns the drift events (empty list = clean).
    """
    events = report()
    notify_drift(events)
    return events


# Human-confirmation gate for drift events: each event has resolved/resolved_at/
# resolved_reason fields. Graduation counts only unresolved events. Resolution is
# write-once — once resolved, the event stays in the audit trail with its reason.


def _load_drift_log_with_migration() -> tuple[list[dict], bool]:
    """Read drift_log.jsonl. Backfill missing event_id / resolved fields on legacy
    entries (events written before the human-confirmation gate landed). Returns
    (events, migrated_any)."""
    if not DRIFT_LOG.exists():
        return [], False
    events = []
    migrated = False
    with open(DRIFT_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            if "event_id" not in event:
                event["event_id"] = str(uuid.uuid4())
                migrated = True
            if "resolved" not in event:
                event["resolved"] = False
                event["resolved_at"] = None
                event["resolved_reason"] = None
                migrated = True
            events.append(event)
    return events, migrated


def _save_drift_log(events: list[dict]) -> None:
    with open(DRIFT_LOG, "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def list_unresolved() -> list[dict]:
    events, migrated = _load_drift_log_with_migration()
    if migrated:
        _save_drift_log(events)
    return [e for e in events if not e.get("resolved")]


def resolve_event(event_id: str, reason: str) -> bool:
    """Mark a single drift event resolved. Returns True if found+resolved, False if not found."""
    events, _ = _load_drift_log_with_migration()
    resolved_at = datetime.now(timezone.utc).isoformat()
    found = False
    for e in events:
        if e.get("event_id") == event_id:
            e["resolved"] = True
            e["resolved_at"] = resolved_at
            e["resolved_reason"] = reason
            found = True
            break
    if found:
        _save_drift_log(events)
    return found


def resolve_all_unresolved(reason: str) -> int:
    """Bulk-resolve every currently-unresolved event with one reason. Returns count."""
    events, _ = _load_drift_log_with_migration()
    resolved_at = datetime.now(timezone.utc).isoformat()
    count = 0
    for e in events:
        if not e.get("resolved"):
            e["resolved"] = True
            e["resolved_at"] = resolved_at
            e["resolved_reason"] = reason
            count += 1
    if count:
        _save_drift_log(events)
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", action="store_true", help="Read-only drift report (Story 2.1)")
    parser.add_argument("--list-drift", action="store_true", help="List unresolved drift events from drift_log.jsonl")
    parser.add_argument("--resolve", metavar="EVENT_ID", help="Mark one drift event resolved")
    parser.add_argument("--resolve-all", metavar="REASON", help="Mark all unresolved drift events resolved with one reason")
    parser.add_argument("--reason", help="Reason text used with --resolve EVENT_ID")
    args = parser.parse_args()

    if args.list_drift:
        events = list_unresolved()
        print(f"Unresolved drift events: {len(events)}")
        for e in events:
            print(f"  id={e['event_id']} type={e['type']} symbol={e.get('symbol','?')} detected={e['detected_at']}")
        sys.exit(0)
    if args.resolve_all:
        count = resolve_all_unresolved(args.resolve_all)
        print(f"Resolved {count} drift event(s) with reason: {args.resolve_all}")
        sys.exit(0)
    if args.resolve:
        if not args.reason:
            print("--resolve requires --reason 'text'")
            sys.exit(2)
        found = resolve_event(args.resolve, args.reason)
        print(f"{'Resolved' if found else 'No event found with id'} {args.resolve}")
        sys.exit(0 if found else 1)

    load_env()
    try:
        if args.report:
            events = report()
            print(f"Drift report: {len(events)} event(s)")
            for e in events:
                print(f"  {e}")
        else:
            summary = reconcile(dry_run=args.dry_run)
            _print_summary(summary)
    except Exception as e:
        pushover.send("Reconciler CRASHED", str(e))
        raise
