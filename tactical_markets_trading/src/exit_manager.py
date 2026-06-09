import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

import pandas_market_calendars as mcal
import yfinance as yf

import preflight
import pushover
import reconciler
from alpaca_connector import load_env, trading_client
from trade_logger import TRADES_PATH, wait_for_fill


def _compute_wash_sale(record: dict, all_records: list[dict], exit_time_actual: str, pnl_dollars: float) -> dict:
    """Story 2.5: scan local trades for same-symbol entries within 30 days before exit.

    Phase 2 implementation is informational only — Phase 3 may auto-block re-entries
    that would trigger a wash sale. Returns the wash_sale object for embedding in the
    close record.
    """
    is_loss = pnl_dollars < 0
    if not is_loss:
        return {"is_loss": False, "loss_amount": 0, "lots_within_30d": [], "potential_wash_sale": False}

    exit_dt = datetime.fromisoformat(exit_time_actual)
    window_start = exit_dt - timedelta(days=30)
    lots = []
    for r in all_records:
        if r.get("symbol") != record.get("symbol"):
            continue
        if r.get("trade_id") == record.get("trade_id"):
            continue
        et = r.get("entry_time")
        if not et:
            continue
        try:
            entry_dt = datetime.fromisoformat(et)
        except ValueError:
            continue
        if window_start <= entry_dt < exit_dt:
            lots.append({
                "trade_id": r["trade_id"],
                "entry_time": et,
                "fill_price": r.get("fill_price"),
                "fill_qty": r.get("fill_qty"),
            })

    return {
        "is_loss": True,
        "loss_amount": pnl_dollars,
        "lots_within_30d": lots,
        "potential_wash_sale": len(lots) > 0,
    }


def get_return_pct(ticker: str, start: datetime, end: datetime) -> float | None:
    # yf.Ticker().history() returns flat columns; yf.download() returns MultiIndex
    # columns even for single tickers, which silently broke float(data["Close"].iloc[0])
    # and caused every prior benchmark capture to land as null.
    start_str = start.date().isoformat()
    end_str = (end.date() + timedelta(days=1)).isoformat()
    data = yf.Ticker(ticker).history(start=start_str, end=end_str, auto_adjust=True)
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


def _cancel_stop_and_classify(client, record: dict) -> tuple[str, dict | None]:
    """Story 1a.4 + 1a.5: cancel the broker stop, classify what we found.

    Returns (exit_reason, stop_fill_data_or_none).

    - "scheduled"          — cancel succeeded OR no stop existed (Phase 1 / stop_submission_failed);
                             proceed with market SELL. The "did a stop exist?" detail is preserved
                             in the record's stop_order_id field for forensics.
    - "stop_fired"         — cancel raised AND position size is 0 → broker's stop already filled;
                             returns the stop's fill data so the caller skips the SELL
    - "stop_cancel_failed" — cancel raised but position still held; proceed with market SELL
    """
    stop_order_id = record.get("stop_order_id")
    if not stop_order_id:
        return "scheduled", None

    try:
        client.cancel_order_by_id(stop_order_id)
        return "scheduled", None
    except Exception as cancel_err:
        # Cancel raised. Two cases: stop fired (position is 0) or genuinely failed (position held).
        try:
            position = client.get_open_position(record["symbol"])
            qty_held = float(position.qty)
        except Exception:
            qty_held = 0.0

        if qty_held < 1e-6:
            # Stop fired — look up the filled stop order to capture fill data
            try:
                stop_order = client.get_order_by_id(stop_order_id)
                stop_fill = {
                    "exit_order_id": stop_order_id,
                    "exit_time_actual": str(stop_order.filled_at),
                    "exit_fill_price": float(stop_order.filled_avg_price),
                    "exit_fill_qty": float(stop_order.filled_qty),
                }
                return "stop_fired", stop_fill
            except Exception as lookup_err:
                # Cancel said the stop is gone, position is 0, but we can't read the stop's fill.
                # Surface as stop_fired with null fill data; reconciler will resolve.
                return "stop_fired", None
        else:
            print(f"  stop cancel raised ({cancel_err}) but position still held qty={qty_held}; proceeding with market SELL")
            return "stop_cancel_failed", None


def exit_position(record: dict) -> dict:
    client = trading_client()
    # Pre-flight: confirm we actually hold this symbol on Alpaca. If not, raise so
    # the reconciler can backfill the close from order history rather than triggering
    # the "fractional cannot be sold short" rejection. Also capture the actual position
    # qty — if a stop partial-fill or fractional-remainder leak occurred, we sell what's
    # actually there, not what the local record thinks.
    try:
        position = client.get_open_position(record["symbol"])
        actual_position_qty = float(position.qty)
    except Exception as e:
        raise RuntimeError(
            f"no Alpaca position for {record['symbol']} (local trade {record['trade_id'][:8]}); "
            f"likely already closed externally — run reconciler to backfill ({type(e).__name__}: {e})"
        )

    # Story 1a.4: cancel the broker stop before submitting market SELL (avoid double-sell).
    exit_reason, stop_fill = _cancel_stop_and_classify(client, record)

    if exit_reason == "stop_fired" and stop_fill is not None:
        # Broker's stop already filled. Skip the SELL; use the stop's fill data.
        entry_cost = record["fill_price"] * record["fill_qty"]
        exit_proceeds = stop_fill["exit_fill_price"] * stop_fill["exit_fill_qty"]
        pnl_dollars = round(exit_proceeds - entry_cost, 2)
        pnl_pct = round((exit_proceeds - entry_cost) / entry_cost * 100, 4)
        closed = {
            **record,
            **stop_fill,
            "pnl_dollars": pnl_dollars,
            "pnl_pct": pnl_pct,
            "spy_return_pct": None,
            "sell_leg_return_pct": None,
            "status": "closed",
            "exit_reason": exit_reason,
            "wash_sale": _compute_wash_sale(record, load_trades(), stop_fill["exit_time_actual"], pnl_dollars),
        }
        try:
            entry_time = datetime.fromisoformat(record["entry_time"])
            exit_time = datetime.fromisoformat(stop_fill["exit_time_actual"])
            closed["spy_return_pct"] = get_return_pct("SPY", entry_time, exit_time)
            closed["sell_leg_return_pct"] = get_return_pct(record["sell_leg"], entry_time, exit_time)
        except Exception as e:
            print(f"  benchmark fetch failed: {e} - record saved without benchmarks")
        return closed

    # Normal path (scheduled, no_stop_to_cancel, or stop_cancel_failed): submit market SELL
    # for what we ACTUALLY hold on Alpaca. Using actual_position_qty (rather than the local
    # record's fill_qty) lets us cleanly close fractional-remainder leakage from a prior
    # whole-share stop partial-fire.
    if abs(actual_position_qty - record["fill_qty"]) > 1e-6:
        print(f"  position qty drift: local={record['fill_qty']} alpaca={actual_position_qty} — selling actual")
    order = client.submit_order(MarketOrderRequest(
        symbol=record["symbol"],
        qty=actual_position_qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    ))
    fill = wait_for_fill(str(order.id))
    entry_cost = record["fill_price"] * record["fill_qty"]
    exit_proceeds = fill["fill_price"] * fill["fill_qty"]
    pnl_dollars = round(exit_proceeds - entry_cost, 2)
    pnl_pct = round((exit_proceeds - entry_cost) / entry_cost * 100, 4)
    closed = {
        **record,
        "exit_order_id": str(order.id),
        "exit_time_actual": fill["fill_time"],
        "exit_fill_price": fill["fill_price"],
        "exit_fill_qty": fill["fill_qty"],
        "pnl_dollars": pnl_dollars,
        "pnl_pct": pnl_pct,
        "spy_return_pct": None,
        "sell_leg_return_pct": None,
        "status": "closed",
        "exit_reason": exit_reason,
        "wash_sale": _compute_wash_sale(record, load_trades(), fill["fill_time"], pnl_dollars),
    }
    try:
        entry_time = datetime.fromisoformat(record["entry_time"])
        exit_time = datetime.fromisoformat(fill["fill_time"])
        closed["spy_return_pct"] = get_return_pct("SPY", entry_time, exit_time)
        closed["sell_leg_return_pct"] = get_return_pct(record["sell_leg"], entry_time, exit_time)
    except Exception as e:
        print(f"  benchmark fetch failed: {e} - record saved without benchmarks")
    return closed


def _market_is_open() -> bool:
    """True only during NYSE regular hours (9:30–16:00 ET). Handles weekends and holidays."""
    now_utc = datetime.now(timezone.utc)
    date_str = now_utc.date().isoformat()
    schedule = mcal.get_calendar("NYSE").schedule(start_date=date_str, end_date=date_str)
    if schedule.empty:
        return False
    market_open = schedule.iloc[0]["market_open"].to_pydatetime()
    market_close = schedule.iloc[0]["market_close"].to_pydatetime()
    return market_open <= now_utc <= market_close


def run_exits():
    # Story 1b.5: preflight ABORT on broken state (env keys, Alpaca reachability).
    ok, reason = preflight.check_exit()
    if not ok:
        print(f"Exit preflight FAILED: {reason}")
        pushover.send("Tactical Trading EXIT ABORT", reason)
        sys.exit(1)

    # Guard: only submit SELLs during NYSE hours. StartWhenAvailable can fire this task
    # in the middle of the night; without this check pre-market orders are queued,
    # wait_for_fill times out, and local state diverges from Alpaca until reconciler runs.
    # Runs BEFORE reconcile() so catch-up runs don't Pushover drift alerts at weird hours.
    if not _market_is_open():
        now_et = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
        print(f"Market closed ({now_et.strftime('%H:%M ET')}) — exit cycle skipped.")
        return 0

    # Reconcile so local state matches Alpaca before we decide what to exit.
    # Backfills closures we missed; alerts on untracked positions. Non-fatal on failure
    # (reconciler will Pushover its own crash); we still proceed with the exit cycle.
    try:
        reconciler.reconcile(dry_run=False)
    except Exception as e:
        print(f"reconciler pre-flight failed (non-fatal): {e}")
        pushover.send("Reconciler pre-flight failed", str(e))

    now = datetime.now(timezone.utc)
    records = load_trades()
    exited = 0
    for i, record in enumerate(records):
        if record["status"] != "open":
            continue
        # Phase 3.1 records (from run_ensemble.py) don't use timed exits — their
        # owning strategy manages exit via trailing stop + trend signal. Skip them
        # here; they're managed by the ensemble orchestrator.
        if "exit_time_planned" not in record:
            continue
        exit_due = datetime.fromisoformat(record["exit_time_planned"])
        if now < exit_due:
            continue
        print(f"Exiting {record['symbol']} (trade {record['trade_id'][:8]}...)")
        try:
            records[i] = exit_position(record)
            save_trades(records)
            exited += 1
            closed = records[i]
            spy = closed.get("spy_return_pct")
            sl = closed.get("sell_leg_return_pct")
            spy_str = f"{spy:+.2f}%" if spy is not None else "n/a"
            sl_str = f"{sl:+.2f}%" if sl is not None else "n/a"
            pushover.send(
                f"Exited {closed['symbol']} {closed['pnl_pct']:+.2f}%",
                f"P&L: ${closed['pnl_dollars']} | SPY {spy_str} | {closed['sell_leg']} {sl_str}",
            )
        except Exception as e:
            print(f"  EXIT FAILED for {record['trade_id'][:8]}: {e}")
            pushover.send(
                "Tactical Trading EXIT FAILED",
                f"{record['symbol']} (trade {record['trade_id'][:8]}): {e}",
            )
    if not exited:
        print(f"No open positions due for exit ({len(records)} record(s) checked).")

    # Story 2.3: post-cycle drift report (passive monitoring). Catches drift the cycle
    # itself may have introduced (e.g., a stop fired mid-run). Non-fatal on failure.
    try:
        events = reconciler.report_and_notify()
        if events:
            print(f"Post-cycle drift: {len(events)} event(s) recorded to drift_log.jsonl")
    except Exception as e:
        print(f"reconciler post-report failed (non-fatal): {e}")
        pushover.send("Reconciler post-report failed", str(e))

    # Epic 3: check graduation status, Pushover once when criterion is first met.
    try:
        import graduation
        if graduation.notify_if_met():
            print("PHASE 2 GRADUATION MET — Pushover sent.")
    except Exception as e:
        print(f"graduation check failed (non-fatal): {e}")

    return exited


if __name__ == "__main__":
    load_env()
    try:
        run_exits()
    except Exception as e:
        pushover.send("Tactical Trading EXIT CRASHED", str(e))
        raise
