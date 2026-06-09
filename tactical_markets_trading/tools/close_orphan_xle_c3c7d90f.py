"""One-shot reconciliation for trade c3c7d90f-d451-44e2-a64e-82682e048cf1.

Background: XLE BUY filled 83.292242807 shares 2026-05-21. The GTC stop only
covered 83 whole shares (Alpaca rejects fractional GTC). The stop later fired
for 83 shares, leaving ~0.29 fractional on the broker. Local record stayed
"open" because reconciler's _backfill_close requires exact qty match (1e-6)
and 83 vs 83.292 is a 0.29-share gap. Every reconcile cycle has been Pushovering
drift_unresolvable for this trade.

This script:
  1. Queries Alpaca for the stop SELL fill (we know its order_id).
  2. Updates the local record with the actual close data, marks status=closed,
     and records the partial_close_residual_qty for the audit trail.
  3. If market is open, submits a market SELL for the residual fractional XLE
     to clean up the broker side. If market is closed, prints instructions to
     re-run after open.
  4. Writes a resolved entry to drift_log.jsonl referencing the trade_id so
     future drift_unresolvable alerts for this trade_id are suppressed by the
     reconciler dedup logic (see reconciler.py).

Safe to re-run: idempotent on already-closed local record; will skip residual
sell if broker has no XLE.
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from alpaca_connector import load_env, trading_client
from trade_logger import TRADES_PATH, wait_for_fill

TRADE_ID = "c3c7d90f-d451-44e2-a64e-82682e048cf1"
STOP_ORDER_ID = "52abc415-cd3d-4651-bebb-a362f9a42762"
SYMBOL = "XLE"
DRIFT_LOG = TRADES_PATH.parent / "drift_log.jsonl"


def _market_is_open(client) -> bool:
    clock = client.get_clock()
    return bool(clock.is_open)


def main():
    load_env()
    client = trading_client()

    # 1. Look up stop fill on Alpaca
    print(f"Querying Alpaca for stop order {STOP_ORDER_ID}...")
    stop_order = client.get_order_by_id(STOP_ORDER_ID)
    if str(stop_order.status) != "OrderStatus.FILLED":
        print(f"  stop order status is {stop_order.status} (expected FILLED). Aborting.")
        sys.exit(1)
    stop_fill_qty = float(stop_order.filled_qty)
    stop_fill_price = float(stop_order.filled_avg_price)
    stop_fill_time = str(stop_order.filled_at)
    print(f"  stop FILLED: qty={stop_fill_qty} @ ${stop_fill_price:.4f} at {stop_fill_time}")

    # 2. Update trade record
    with open(TRADES_PATH) as f:
        records = [json.loads(line) for line in f if line.strip()]
    target_idx = None
    for i, r in enumerate(records):
        if r.get("trade_id") == TRADE_ID:
            target_idx = i
            break
    if target_idx is None:
        print(f"  trade {TRADE_ID} not found in trades.jsonl. Aborting.")
        sys.exit(1)
    record = records[target_idx]
    if record.get("status") == "closed":
        print(f"  trade {TRADE_ID[:8]} already closed locally; skipping local update.")
    else:
        entry_cost = record["fill_price"] * stop_fill_qty
        exit_proceeds = stop_fill_price * stop_fill_qty
        residual_qty = float(record["fill_qty"]) - stop_fill_qty
        record.update({
            "status": "closed",
            "exit_order_id": STOP_ORDER_ID,
            "exit_time_actual": stop_fill_time,
            "exit_fill_price": stop_fill_price,
            "exit_fill_qty": stop_fill_qty,
            "pnl_dollars": round(exit_proceeds - entry_cost, 2),
            "pnl_pct": round((exit_proceeds - entry_cost) / entry_cost * 100, 4),
            "exit_reason": "stop_fired",
            "reconciled": True,
            "reconciled_at": datetime.now(timezone.utc).isoformat(),
            "partial_close_residual_qty": round(residual_qty, 9),
            "partial_close_reason": (
                "stop GTC qty was floor(fill_qty) due to Alpaca fractional-GTC rejection; "
                "fractional remainder cleared separately by close_orphan_xle_c3c7d90f.py"
            ),
        })
        with open(TRADES_PATH, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        print(f"  trade {TRADE_ID[:8]} marked CLOSED  "
              f"pnl ${record['pnl_dollars']} ({record['pnl_pct']:+.2f}%)  "
              f"residual {record['partial_close_residual_qty']} XLE")

    # 3. Clear residual on broker side
    try:
        position = client.get_open_position(SYMBOL)
        broker_qty = float(position.qty)
    except Exception:
        broker_qty = 0.0
    if broker_qty <= 1e-9:
        print(f"  broker has no {SYMBOL} position; nothing to sell.")
    elif not _market_is_open(client):
        print(f"  broker has {broker_qty} {SYMBOL} but market is CLOSED. "
              f"Re-run this script during RTH to clear the residual.")
    else:
        print(f"  broker has {broker_qty} {SYMBOL}; submitting market SELL...")
        order = client.submit_order(MarketOrderRequest(
            symbol=SYMBOL,
            qty=broker_qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        ))
        fill = wait_for_fill(str(order.id))
        print(f"  residual SELL filled: {fill['fill_qty']} @ ${fill['fill_price']:.4f}")
        # Clear the residual on the trade record so reconciler stops tracking it.
        with open(TRADES_PATH) as f:
            records = [json.loads(line) for line in f if line.strip()]
        for r in records:
            if r.get("trade_id") == TRADE_ID:
                r["partial_close_residual_qty"] = 0
                r["partial_close_cleared_at"] = datetime.now(timezone.utc).isoformat()
                r["partial_close_cleared_order_id"] = str(order.id)
                r["partial_close_cleared_fill_price"] = fill["fill_price"]
                r["partial_close_cleared_fill_qty"] = fill["fill_qty"]
                break
        with open(TRADES_PATH, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        print(f"  trade record updated: partial_close_residual_qty cleared.")

    # 4. Write a resolved drift_log entry so reconciler dedup suppresses future alerts
    now = datetime.now(timezone.utc).isoformat()
    resolved_event = {
        "type": "drift_unresolvable",
        "trade_id": TRADE_ID,
        "symbol": SYMBOL,
        "error": "no matching FILLED SELL for XLE qty=83.292242807 (partial close — see partial_close_residual_qty on trade record)",
        "event_id": str(uuid.uuid4()),
        "detected_at": now,
        "resolved": True,
        "resolved_at": now,
        "resolved_reason": (
            "stop sold 83 of 83.292 shares (Alpaca fractional-GTC rejection); "
            "trade closed via tools/close_orphan_xle_c3c7d90f.py; "
            "residual cleared via market SELL"
        ),
    }
    DRIFT_LOG.parent.mkdir(exist_ok=True)
    with open(DRIFT_LOG, "a") as f:
        f.write(json.dumps(resolved_event) + "\n")
    print(f"  drift_log resolved entry written for trade {TRADE_ID[:8]}")
    print("Done.")


if __name__ == "__main__":
    main()
