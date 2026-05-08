import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from alpaca_connector import trading_client

THESES_PATH = Path(__file__).resolve().parent.parent.parent / "tactical_markets" / "data" / "theses.jsonl"
NOTIONAL = 10_000


def latest_signal():
    last = None
    with open(THESES_PATH) as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("signal"):
                last = entry
    return last


def submit_order(thesis: dict) -> dict:
    symbol = thesis["buy"]
    request = MarketOrderRequest(
        symbol=symbol,
        notional=NOTIONAL,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
    )
    order = trading_client().submit_order(request)
    return {
        "order_id": str(order.id),
        "symbol": order.symbol,
        "notional": NOTIONAL,
        "status": str(order.status),
        "submitted_at": str(order.submitted_at),
        "thesis_as_of": thesis["as_of"],
        "sell_leg": thesis["sell"],
    }


if __name__ == "__main__":
    thesis = latest_signal()
    if thesis is None:
        print("No signal found in theses.jsonl — no order submitted.")
        sys.exit(0)

    print(f"Signal: BUY {thesis['buy']} (sell leg: {thesis['sell']}, spread: {thesis['spread_pct']}%)")
    print(f"  as_of: {thesis['as_of']}")
    result = submit_order(thesis)
    print("Order submitted:")
    for k, v in result.items():
        print(f"  {k}: {v}")
