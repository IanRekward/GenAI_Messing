import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest

import pushover
from alpaca_connector import load_env, trading_client
from order_builder import THESES_PATH, submit_order
from trade_logger import log_entry


def today_signal():
    today = datetime.now(timezone.utc).date()
    last = None
    with open(THESES_PATH) as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("signal") and datetime.fromisoformat(entry["as_of"]).date() == today:
                last = entry
    return last


def already_traded(symbol: str) -> bool:
    """Check Alpaca for any open position OR open buy order in this symbol.
    Authoritative source — local file can lag if logging fails."""
    client = trading_client()
    for p in client.get_all_positions():
        if p.symbol == symbol:
            return True
    for o in client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN)):
        if o.symbol == symbol:
            return True
    return False


def main():
    thesis = today_signal()
    if thesis is None:
        print("No signal for today — no trade.")
        return

    symbol = thesis["buy"]
    if already_traded(symbol):
        print(f"Already have an open position or order in {symbol} — skipping.")
        return

    print(f"Signal: BUY {symbol} (spread: {thesis['spread_pct']}%, as_of: {thesis['as_of']})")
    order_result = submit_order(thesis)
    print(f"Order submitted: {order_result['order_id']} status={order_result['status']}")
    record = log_entry(order_result)
    print(f"Trade logged: {record['trade_id']}")
    print(f"  Entry: ${record['fill_price']} x {record['fill_qty']} {record['symbol']}")
    print(f"  Exit planned: {record['exit_time_planned']}")
    pushover.send(
        f"Entered {symbol} ${record['notional']:,}",
        f"Filled {record['fill_qty']:.4f} @ ${record['fill_price']:.2f} | Spread: {thesis['spread_pct']}% | Exit: {record['exit_time_planned'][:10]}",
    )


if __name__ == "__main__":
    load_env()
    try:
        main()
    except Exception as e:
        pushover.send("Tactical Trading ENTRY FAILED", str(e))
        raise
