import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from order_builder import THESES_PATH, submit_order
from trade_logger import TRADES_PATH, log_entry


def today_signal():
    today = datetime.now(timezone.utc).date()
    last = None
    with open(THESES_PATH) as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("signal") and datetime.fromisoformat(entry["as_of"]).date() == today:
                last = entry
    return last


def already_traded_today():
    if not TRADES_PATH.exists():
        return False
    today = datetime.now(timezone.utc).date()
    with open(TRADES_PATH) as f:
        for line in f:
            record = json.loads(line)
            if record.get("status") == "open":
                if datetime.fromisoformat(record["entry_time"]).date() == today:
                    return True
    return False


if __name__ == "__main__":
    if already_traded_today():
        print("Already have an open trade entered today — skipping.")
        sys.exit(0)

    thesis = today_signal()
    if thesis is None:
        print("No signal for today — no trade.")
        sys.exit(0)

    print(f"Signal: BUY {thesis['buy']} (spread: {thesis['spread_pct']}%, as_of: {thesis['as_of']})")
    order_result = submit_order(thesis)
    print(f"Order submitted: {order_result['order_id']} status={order_result['status']}")
    record = log_entry(order_result)
    print(f"Trade logged: {record['trade_id']}")
    print(f"  Entry: ${record['fill_price']} x {record['fill_qty']} {record['symbol']}")
    print(f"  Exit planned: {record['exit_time_planned']}")
