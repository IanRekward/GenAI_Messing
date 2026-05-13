import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from alpaca.trading.enums import OrderSide, QueryOrderStatus
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


def already_traded_today(symbol: str) -> bool:
    """Did we already submit a buy for this symbol today (UTC)?
    Prevents intra-day double-fire from scheduler hiccup or manual re-run.
    Authoritative — uses Alpaca, not local trades.jsonl which can lag."""
    client = trading_client()
    today_start = datetime.combine(
        datetime.now(timezone.utc).date(),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )
    request = GetOrdersRequest(
        status=QueryOrderStatus.ALL,
        after=today_start,
        side=OrderSide.BUY,
    )
    for order in client.get_orders(request):
        if order.symbol == symbol:
            return True
    return False


def at_position_limit(max_positions: int = 5) -> bool:
    """Are we at the 5-overlapping-positions design limit per TODO.md?
    Phase 1 design: up to 5 concurrent positions, steady state ~50% deployed."""
    client = trading_client()
    return len(client.get_all_positions()) >= max_positions


def main():
    thesis = today_signal()
    if thesis is None:
        print("No signal for today — no trade.")
        return

    symbol = thesis["buy"]
    if already_traded_today(symbol):
        print(f"Already submitted a buy for {symbol} today — skipping (intra-day dedup).")
        return
    if at_position_limit():
        print(f"At 5-position concurrency limit — skipping {symbol}.")
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
