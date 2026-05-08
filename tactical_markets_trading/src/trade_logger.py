import json
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas_market_calendars as mcal

from alpaca_connector import trading_client

TRADES_PATH = Path(__file__).resolve().parent.parent / "data" / "trades.jsonl"
FILL_POLL_INTERVAL = 2
FILL_POLL_TIMEOUT = 60


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
    client = trading_client()
    deadline = time.time() + FILL_POLL_TIMEOUT
    while time.time() < deadline:
        order = client.get_order_by_id(order_id)
        if order.filled_at is not None:
            return {
                "fill_price": float(order.filled_avg_price),
                "fill_qty": float(order.filled_qty),
                "fill_time": str(order.filled_at),
            }
        time.sleep(FILL_POLL_INTERVAL)
    raise RuntimeError(f"Order {order_id} not filled within {FILL_POLL_TIMEOUT}s")


def log_entry(order_result: dict) -> dict:
    TRADES_PATH.parent.mkdir(exist_ok=True)
    fill = wait_for_fill(order_result["order_id"])
    entry_time = datetime.fromisoformat(fill["fill_time"])
    record = {
        "trade_id": str(uuid.uuid4()),
        "order_id": order_result["order_id"],
        "symbol": order_result["symbol"],
        "sell_leg": order_result["sell_leg"],
        "notional": order_result["notional"],
        "thesis_as_of": order_result["thesis_as_of"],
        "entry_time": fill["fill_time"],
        "fill_price": fill["fill_price"],
        "fill_qty": fill["fill_qty"],
        "exit_time_planned": str(add_trading_days(entry_time, 5)),
        "status": "open",
    }
    with open(TRADES_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")
    return record
