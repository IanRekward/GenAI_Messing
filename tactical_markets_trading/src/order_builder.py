import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest, StopOrderRequest

import yfinance as yf

from alpaca_connector import trading_client
from risk import compute_stop_price

THESES_PATH = Path(__file__).resolve().parent.parent.parent / "tactical_markets" / "data" / "theses.jsonl"
NOTIONAL = 10_000  # Phase 1 fixed notional. Story 1c.3 replaces this with risk-based qty.
STOP_RULE = "fixed_pct_2.5"  # Phase 2 default; Phase 2.5 may switch to ATR-based


def get_estimated_entry_price(symbol: str) -> float:
    """Story 1c.3 helper: best-effort entry-price estimate for pre-trade sizing.

    Uses yfinance's most recent close (`history(period='2d').iloc[-1]['Close']`).
    During market hours yfinance returns today's intraday "close" (= latest price);
    pre-market it returns yesterday's close. Either is fine — the actual fill will
    differ by slippage, and the broker stop uses the actual fill_price (not the
    estimate). The estimate just sizes the qty.
    """
    data = yf.Ticker(symbol).history(period="2d", auto_adjust=True)
    if data.empty:
        raise RuntimeError(f"yfinance returned no data for {symbol} — cannot estimate entry price")
    return float(data["Close"].iloc[-1])


def latest_signal():
    last = None
    with open(THESES_PATH) as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("signal"):
                last = entry
    return last


def submit_order(thesis: dict, qty: float | None = None, notional: float | None = None) -> dict:
    """Submit a market BUY for the thesis's long leg.

    Pass either `qty` (Story 1c.3 risk-based path) OR `notional` (Phase 1 / 1b.6
    transitional path). Exactly one must be set. The result dict carries whichever
    was used; the other is null. `notional: None` in the persisted record signals
    qty-based sizing.
    """
    if (qty is None) == (notional is None):
        raise ValueError("submit_order requires exactly one of qty or notional, not both/neither")
    symbol = thesis["buy"]
    request = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        notional=notional,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
    )
    order = trading_client().submit_order(request)
    return {
        "order_id": str(order.id),
        "symbol": order.symbol,
        "notional": notional,
        "qty": qty,
        "status": str(order.status),
        "submitted_at": str(order.submitted_at),
        "thesis_as_of": thesis["as_of"],
        "sell_leg": thesis["sell"],
    }


def submit_stop(symbol: str, qty: float, fill_price: float) -> dict:
    """Story 1a.2: Submit a broker-side stop-sell at compute_stop_price(fill_price).

    GTC so it survives multi-day VPS outage (NFR5). Alpaca rejects fractional qty
    on non-DAY orders ("fractional orders must be DAY orders"), so we floor to whole
    shares. The fractional remainder (typically < 1 share) is left unprotected by the
    broker stop — exit_position cleans it up using actual Alpaca position qty at exit.

    Returns: {"stop_order_id": str|None, "stop_price": float, "stop_rule_used": str,
              "stop_qty_covered": int|None}

    On submission failure, returns stop_order_id=None and stop_rule_used="stop_submission_failed".
    """
    stop_price = compute_stop_price(fill_price)
    whole_qty = int(qty)  # floor: e.g., 83.292 -> 83
    if whole_qty <= 0:
        # Position smaller than 1 share — can't submit any stop. Tiny positions
        # ($60 of SPY, etc.) would hit this. Surface as failure; caller alerts.
        return {
            "stop_order_id": None,
            "stop_price": stop_price,
            "stop_rule_used": "stop_submission_failed",
            "stop_qty_covered": 0,
            "stop_submission_error": f"qty {qty} floors to 0 — too small for whole-share stop",
        }
    try:
        order = trading_client().submit_order(StopOrderRequest(
            symbol=symbol,
            qty=whole_qty,
            side=OrderSide.SELL,
            stop_price=stop_price,
            time_in_force=TimeInForce.GTC,
        ))
        return {
            "stop_order_id": str(order.id),
            "stop_price": stop_price,
            "stop_rule_used": STOP_RULE,
            "stop_qty_covered": whole_qty,
        }
    except Exception as e:
        return {
            "stop_order_id": None,
            "stop_price": stop_price,
            "stop_rule_used": "stop_submission_failed",
            "stop_qty_covered": 0,
            "stop_submission_error": str(e),
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
