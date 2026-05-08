import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

import yfinance as yf

from alpaca_connector import trading_client
from trade_logger import TRADES_PATH, wait_for_fill


def get_return_pct(ticker: str, start: datetime, end: datetime) -> float | None:
    start_str = start.date().isoformat()
    end_str = (end.date() + timedelta(days=1)).isoformat()
    data = yf.download(ticker, start=start_str, end=end_str, progress=False, auto_adjust=True)
    if data.empty or len(data) < 2:
        return None
    first = float(data["Close"].iloc[0])
    last = float(data["Close"].iloc[-1])
    return round((last - first) / first * 100, 4)


def load_trades():
    if not TRADES_PATH.exists():
        return []
    with open(TRADES_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


def save_trades(records):
    TRADES_PATH.parent.mkdir(exist_ok=True)
    with open(TRADES_PATH, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


def exit_position(record: dict) -> dict:
    client = trading_client()
    order = client.submit_order(MarketOrderRequest(
        symbol=record["symbol"],
        qty=record["fill_qty"],
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    ))
    fill = wait_for_fill(str(order.id))
    entry_cost = record["fill_price"] * record["fill_qty"]
    exit_proceeds = fill["fill_price"] * fill["fill_qty"]
    pnl_dollars = round(exit_proceeds - entry_cost, 2)
    pnl_pct = round((exit_proceeds - entry_cost) / entry_cost * 100, 4)
    entry_time = datetime.fromisoformat(record["entry_time"])
    exit_time = datetime.fromisoformat(fill["fill_time"])
    spy_return = get_return_pct("SPY", entry_time, exit_time)
    sell_leg_return = get_return_pct(record["sell_leg"], entry_time, exit_time)
    return {
        **record,
        "exit_order_id": str(order.id),
        "exit_time_actual": fill["fill_time"],
        "exit_fill_price": fill["fill_price"],
        "exit_fill_qty": fill["fill_qty"],
        "pnl_dollars": pnl_dollars,
        "pnl_pct": pnl_pct,
        "spy_return_pct": spy_return,
        "sell_leg_return_pct": sell_leg_return,
        "status": "closed",
    }


def run_exits():
    now = datetime.now(timezone.utc)
    records = load_trades()
    exited = 0
    for i, record in enumerate(records):
        if record["status"] != "open":
            continue
        exit_due = datetime.fromisoformat(record["exit_time_planned"])
        if now >= exit_due:
            print(f"Exiting {record['symbol']} (trade {record['trade_id'][:8]}...)")
            records[i] = exit_position(record)
            exited += 1
    if exited:
        save_trades(records)
        print(f"Exited {exited} position(s). trades.jsonl updated.")
    else:
        print(f"No open positions due for exit ({len(records)} record(s) checked).")
    return exited


if __name__ == "__main__":
    run_exits()
