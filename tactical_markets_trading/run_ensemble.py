"""Phase 3.1 ensemble orchestrator — single-strategy variant.

Initially handles only `trend_leveraged_tqqq`. Phase 3.2 will add the other two
components and the regime router. Until then this is essentially a refactored,
strategy-agnostic version of the trading loop.

Daily flow:
  1. load_env + preflight (env, Alpaca, MICRO freshness, MACRO, kill switch)
  2. reconcile (catch any state drift before deciding)
  3. market-hours guard (skip if before/after RTH)
  4. fetch market data (yesterday's SPY/TQQQ closes, SPY MA)
  5. for each active strategy:
       state = load_state(strategy.name)
       decision = strategy.decide(state, market_data, equity, positions)
       execute(decision)
       save_state(strategy.name, state)
  6. post-cycle drift report (catch anything the cycle itself introduced)
  7. graduation check

The existing run_trading.py + exit_manager.py paths continue to exist but
are gated by the SECTOR_ROTATION_5D_RETIRED flag — they will not trade.
This orchestrator is the new entry path. The Windows Scheduled Task can be
re-pointed to invoke this script directly.
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import yfinance as yf

from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

import preflight
import pushover
import reconciler
import strategy_state
from alpaca_connector import load_env, trading_client
from exit_manager import _market_is_open
from strategies.base import Decision
from strategies.leveraged_trend import (
    LEVERAGED_TICKER,
    MA_WINDOW,
    SIGNAL_TICKER,
    LeveragedTrendStrategy,
)
from trade_logger import TRADES_PATH, wait_for_fill

ENSEMBLE_LOG = TRADES_PATH.parent / "ensemble_log.jsonl"
ACTIVE_STRATEGIES = [LeveragedTrendStrategy()]  # Phase 3.1: single component


def _fetch_market_data() -> dict:
    """Pull the price data the active strategies need. Yesterday's close is the
    signal day — yfinance returns it in `Close.iloc[-1]` outside RTH and during
    early RTH (intraday updates appear later in the session).

    Returns dict with:
      spy_close_today, spy_ma_today, tqqq_close_today, spy_close_history (last MA_WINDOW+1)
    """
    spy_hist = yf.Ticker(SIGNAL_TICKER).history(period=f"{MA_WINDOW + 30}d", auto_adjust=True)
    tqqq_hist = yf.Ticker(LEVERAGED_TICKER).history(period="5d", auto_adjust=True)
    if spy_hist.empty:
        raise RuntimeError(f"yfinance returned no data for {SIGNAL_TICKER}")
    if tqqq_hist.empty:
        raise RuntimeError(f"yfinance returned no data for {LEVERAGED_TICKER}")
    spy_close = float(spy_hist["Close"].iloc[-1])
    spy_ma = float(spy_hist["Close"].rolling(MA_WINDOW).mean().iloc[-1])
    tqqq_close = float(tqqq_hist["Close"].iloc[-1])
    return {
        "spy_close_today": spy_close,
        "spy_ma_today": spy_ma,
        "tqqq_close_today": tqqq_close,
        "spy_close_history": spy_hist["Close"].tolist()[-MA_WINDOW - 1:],
    }


def _current_positions_market_value(client) -> dict[str, float]:
    return {p.symbol: float(p.market_value) for p in client.get_all_positions()}


def _current_positions_qty(client) -> dict[str, float]:
    return {p.symbol: float(p.qty) for p in client.get_all_positions()}


def _execute_buy(client, decision: Decision, strategy_name: str, market_data: dict) -> None:
    """Submit a market BUY for whole-share qty per the strategy's decision."""
    if decision.qty is None or decision.symbol is None:
        raise ValueError(f"buy decision missing qty or symbol: {decision}")
    order = client.submit_order(MarketOrderRequest(
        symbol=decision.symbol,
        qty=decision.qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
    ))
    fill = wait_for_fill(str(order.id))
    record = {
        "trade_id": str(uuid.uuid4()),
        "order_id": str(order.id),
        "strategy": strategy_name,
        "symbol": decision.symbol,
        "side": "buy",
        "trigger": decision.trigger,
        "reason": decision.reason,
        "submitted_qty": decision.qty,
        "fill_price": fill["fill_price"],
        "fill_qty": fill["fill_qty"],
        "fill_time": fill["fill_time"],
        "spy_close_at_decision": market_data["spy_close_today"],
        "spy_ma_at_decision": market_data["spy_ma_today"],
        "status": "open",
    }
    with open(TRADES_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")
    pushover.send(
        f"ENSEMBLE: BUY {decision.symbol} {fill['fill_qty']:.2f} @ ${fill['fill_price']:.2f}",
        f"{strategy_name}: {decision.reason}",
    )
    print(f"  BUY filled: {decision.symbol} qty={fill['fill_qty']} @ ${fill['fill_price']:.2f} trade_id={record['trade_id'][:8]}")


def _execute_sell(client, decision: Decision, strategy_name: str, market_data: dict) -> None:
    """Submit a market SELL for whatever's actually held on Alpaca (handles any
    fractional drift between local state and broker)."""
    if decision.symbol is None:
        raise ValueError(f"sell decision missing symbol: {decision}")
    try:
        position = client.get_open_position(decision.symbol)
        sell_qty = float(position.qty)
    except Exception as e:
        print(f"  SELL skipped: no Alpaca position for {decision.symbol} ({e})")
        # Mark the latest open record for this symbol as closed-via-drift so reconciler
        # can resolve. For now just log; reconciler picks it up next cycle.
        return
    order = client.submit_order(MarketOrderRequest(
        symbol=decision.symbol,
        qty=sell_qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    ))
    fill = wait_for_fill(str(order.id))
    # Find the matching open record and close it
    with open(TRADES_PATH) as f:
        records = [json.loads(line) for line in f if line.strip()]
    for r in reversed(records):  # most recent matching open
        if r.get("strategy") == strategy_name and r.get("symbol") == decision.symbol and r.get("status") == "open":
            entry_cost = r["fill_price"] * r["fill_qty"]
            exit_proceeds = fill["fill_price"] * fill["fill_qty"]
            r.update({
                "status": "closed",
                "exit_order_id": str(order.id),
                "exit_time_actual": fill["fill_time"],
                "exit_fill_price": fill["fill_price"],
                "exit_fill_qty": fill["fill_qty"],
                "pnl_dollars": round(exit_proceeds - entry_cost, 2),
                "pnl_pct": round((exit_proceeds - entry_cost) / entry_cost * 100, 4),
                "exit_reason": decision.trigger,  # "stop_fired" / "trend_exit"
                "exit_explanation": decision.reason,
            })
            break
    with open(TRADES_PATH, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    pushover.send(
        f"ENSEMBLE: SELL {decision.symbol} {fill['fill_qty']:.2f} @ ${fill['fill_price']:.2f} ({decision.trigger})",
        f"{strategy_name}: {decision.reason}",
    )
    print(f"  SELL filled: {decision.symbol} qty={fill['fill_qty']} @ ${fill['fill_price']:.2f} reason={decision.trigger}")


def main():
    # Step 1: preflight
    ok, reason = preflight.check_entry()
    if not ok:
        print(f"Preflight FAILED: {reason}")
        title = "Ensemble ABORT: KILL SWITCH" if "kill_switch" in reason else "Ensemble ABORT"
        pushover.send(title, reason)
        sys.exit(1)

    # Step 2: reconcile (catch drift before deciding)
    try:
        reconciler.reconcile(dry_run=False)
    except Exception as e:
        print(f"reconciler failed (non-fatal): {e}")
        pushover.send("Ensemble reconciler failed", str(e))

    # Step 3: market-hours guard — only act during RTH
    if not _market_is_open():
        now_iso = datetime.now(timezone.utc).isoformat()
        print(f"Market closed at {now_iso} — ensemble cycle skipped.")
        return

    # Step 4: market data
    try:
        market_data = _fetch_market_data()
    except Exception as e:
        print(f"market data fetch failed: {e}")
        pushover.send("Ensemble ABORT", f"market data fetch failed: {e}")
        sys.exit(1)
    print(f"Market: SPY ${market_data['spy_close_today']:.2f} vs {MA_WINDOW}d MA ${market_data['spy_ma_today']:.2f}, "
          f"TQQQ ${market_data['tqqq_close_today']:.2f}")

    # Step 5: ask each active strategy to decide
    client = trading_client()
    account = client.get_account()
    account_value = float(account.equity)
    positions_mkt_value = _current_positions_market_value(client)
    print(f"Equity: ${account_value:,.2f}  Positions: {positions_mkt_value or 'none'}")

    for strategy in ACTIVE_STRATEGIES:
        state = strategy_state.load_state(strategy.name)
        print(f"\n--- {strategy.name} ---")
        print(f"  state in: {state}")
        decision = strategy.decide(state, market_data, account_value, positions_mkt_value)
        print(f"  decision: {decision.action} ({decision.trigger}) — {decision.reason}")

        try:
            if decision.action == "buy":
                _execute_buy(client, decision, strategy.name, market_data)
            elif decision.action == "sell":
                _execute_sell(client, decision, strategy.name, market_data)
            # hold = no-op
        except Exception as e:
            print(f"  EXECUTION FAILED: {e}")
            pushover.send(f"Ensemble execution FAILED: {strategy.name}", str(e))
            # Don't persist state on execution failure — next fire will re-attempt
            continue

        strategy_state.save_state(strategy.name, state)
        print(f"  state out: {state}")

    # Step 6: post-cycle drift report
    try:
        events = reconciler.report_and_notify()
        if events:
            print(f"Post-cycle drift: {len(events)} event(s) recorded")
    except Exception as e:
        print(f"post-cycle drift check failed: {e}")

    # Step 7: graduation check (will fail criterion at this point — fine, just records)
    try:
        import graduation
        if graduation.notify_if_met():
            print("PHASE 2 GRADUATION MET — Pushover sent.")
    except Exception as e:
        print(f"graduation check failed (non-fatal): {e}")


if __name__ == "__main__":
    load_env()
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        pushover.send("Ensemble CRASHED", str(e))
        raise
