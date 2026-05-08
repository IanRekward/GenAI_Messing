import json
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alpaca_connector import trading_client

TRADES_PATH = Path(__file__).resolve().parent.parent / "data" / "trades.jsonl"
FILL_POLL_INTERVAL = 2
FILL_POLL_TIMEOUT = 60


def add_trading_days(dt: datetime, n: int) -> datetime:
    result = dt
    added = 0
    while added < n:
        result += timedelta(days=1)
        if result.weekday() < 5:
            added += 1
    return result


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
    raise RuntimeError(f"Order {order_id} not filled within {FILL_POLL_TIMEOUT}s — market may be closed")


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


if __name__ == "__main__":
    order_result = {
        "order_id": "55f625e5-d89f-495e-b6c7-e53315feab0a",
        "symbol": "XLK",
        "sell_leg": "XLE",
        "notional": 10_000,
        "thesis_as_of": "2026-05-08T11:30:05.590776+00:00",
    }
    print(f"Polling for fill on {order_result['order_id']}...")
    try:
        record = log_entry(order_result)
        print("Trade logged:")
        for k, v in record.items():
            print(f"  {k}: {v}")
    except RuntimeError as e:
        print(f"Not logged: {e}")
