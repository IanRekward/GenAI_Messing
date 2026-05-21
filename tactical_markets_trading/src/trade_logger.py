import json
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas_market_calendars as mcal

from alpaca.trading.enums import OrderStatus

from alpaca_connector import trading_client

TERMINAL_FAILED = {OrderStatus.REJECTED, OrderStatus.CANCELED, OrderStatus.EXPIRED}

TRADES_PATH = Path(__file__).resolve().parent.parent / "data" / "trades.jsonl"
FILL_POLL_INTERVAL = 2
# 60s was too short — XLE 2026-05-18 entry took 3min 21s to fill, wait_for_fill
# raised, log_entry never persisted, and we silently held an untracked position
# for two days. 300s is generous enough for slow market fills and still fails
# fast on truly stuck orders. The reconciler is the secondary safety net.
FILL_POLL_TIMEOUT = 300
HOLD_DAYS = 2  # NYSE trading days. Lowered from 5 on 2026-05-13 to speed Phase 1 graduation (pipes-and-signals test).


def add_trading_days(dt: datetime, n: int) -> datetime:
    nyse = mcal.get_calendar("NYSE")
    schedule = nyse.valid_days(
        start_date=dt.date().isoformat(),
        end_date=(dt.date() + timedelta(days=n + 14)).isoformat(),
    )
    future = [d for d in schedule if d.date() > dt.date()]
    if len(future) < n:
        raise RuntimeError(f"insufficient NYSE trading days: needed {n}, got {len(future)}")
    return datetime.combine(future[n - 1].date(), dt.time(), tzinfo=dt.tzinfo)


def wait_for_fill(order_id: str) -> dict:
    """Wait for an order to reach OrderStatus.FILLED. Polling on filled_at != None
    can return on a partial fill — Alpaca updates filled_at and filled_qty incrementally."""
    client = trading_client()
    deadline = time.time() + FILL_POLL_TIMEOUT
    last_status = None
    while time.time() < deadline:
        order = client.get_order_by_id(order_id)
        last_status = order.status
        if order.status == OrderStatus.FILLED:
            return {
                "fill_price": float(order.filled_avg_price),
                "fill_qty": float(order.filled_qty),
                "fill_time": str(order.filled_at),
            }
        if order.status in TERMINAL_FAILED:
            raise RuntimeError(f"Order {order_id} ended in {order.status} (filled_qty={order.filled_qty})")
        time.sleep(FILL_POLL_INTERVAL)
    raise RuntimeError(f"Order {order_id} not filled within {FILL_POLL_TIMEOUT}s (last status: {last_status})")


def log_entry(order_result: dict, macro_snapshot: dict | None = None, sizing_rule_used: str = "phase1_fixed") -> dict:
    """Log an entry record. Optional Phase 2 fields:
        macro_snapshot: dict with run_timestamp, composite_band, regime, weights_hash,
                        neutralized — extracted from regime_data per Story 1b.6.
        sizing_rule_used: 'phase1_fixed', 'phase1_fixed_x_macro_mult' (transitional),
                          'risk_based', or 'concentration_cap' (Story 1c.3+).
    """
    TRADES_PATH.parent.mkdir(exist_ok=True)
    fill = wait_for_fill(order_result["order_id"])
    entry_time = datetime.fromisoformat(fill["fill_time"])

    # Story 1a.2 + 1a.3: submit broker-side stop AFTER entry fills, persist the result.
    # Late import — order_builder also imports from this module, avoid a cycle at load time.
    from order_builder import submit_stop
    stop_result = submit_stop(
        symbol=order_result["symbol"],
        qty=fill["fill_qty"],
        fill_price=fill["fill_price"],
    )
    if stop_result["stop_order_id"] is None:
        # Surface to human per Story 1a.2 AC; do NOT auto-close the entry position.
        import pushover
        pushover.send(
            f"Stop order submission FAILED for {order_result['symbol']}",
            f"Entry filled {fill['fill_qty']} @ ${fill['fill_price']}. "
            f"Stop computed at ${stop_result['stop_price']}. "
            f"Error: {stop_result.get('stop_submission_error', 'unknown')}. "
            f"Position is open and UNPROTECTED — broker stop not in place.",
        )

    record = {
        "trade_id": str(uuid.uuid4()),
        "order_id": order_result["order_id"],
        "symbol": order_result["symbol"],
        "sell_leg": order_result["sell_leg"],
        # notional is None when Story 1c.3 qty-based sizing was used; preserved as a
        # Phase 1 / 1b.6 transitional value otherwise.
        "notional": order_result.get("notional"),
        "submitted_qty": order_result.get("qty"),  # the qty we asked Alpaca to fill (None if notional-based)
        "thesis_as_of": order_result["thesis_as_of"],
        "entry_time": fill["fill_time"],
        "fill_price": fill["fill_price"],
        "fill_qty": fill["fill_qty"],
        "exit_time_planned": str(add_trading_days(entry_time, HOLD_DAYS)),
        "status": "open",
        "stop_order_id": stop_result["stop_order_id"],
        "stop_price": stop_result["stop_price"],
        "stop_rule_used": stop_result["stop_rule_used"],
        "stop_qty_covered": stop_result.get("stop_qty_covered"),
        "sizing_rule_used": sizing_rule_used,
        "macro_snapshot": macro_snapshot,
    }
    with open(TRADES_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")
    return record
