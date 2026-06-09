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

import account_state
import macro_consumer
import preflight
import pushover
import reconciler
import regime_router
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
from strategies.sector_momentum_monthly import (
    LOOKBACK_DAYS as SECTOR_LOOKBACK_DAYS,
    SECTOR_TICKERS,
    SectorMomentumMonthlyStrategy,
)
from strategies.spy_trend import (
    MA_WINDOW as SPY_TREND_MA_WINDOW,
    SpyTrendStrategy,
)
from trade_logger import TRADES_PATH, wait_for_fill

ENSEMBLE_LOG = TRADES_PATH.parent / "ensemble_log.jsonl"
# Phase 3.2: three components registered. regime_router decides which fire each
# cycle based on SPY 200d MA + VIX + MACRO regime.
ACTIVE_STRATEGIES = [
    LeveragedTrendStrategy(),
    SpyTrendStrategy(),
    SectorMomentumMonthlyStrategy(),
]
VIX_TICKER = "^VIX"


def _fetch_market_data() -> dict:
    """Pull the price data the active strategies need. Yesterday's close is the
    signal day — yfinance returns it in `Close.iloc[-1]` outside RTH and during
    early RTH (intraday updates appear later in the session).

    Returns dict with all data the three active strategies (leveraged_trend,
    spy_trend, sector_momentum) need. Single yfinance batch keeps the call
    graph simple and shares the SPY history across strategies.
    """
    spy_period = f"{max(MA_WINDOW, SPY_TREND_MA_WINDOW) + 30}d"
    spy_hist = yf.Ticker(SIGNAL_TICKER).history(period=spy_period, auto_adjust=True)
    tqqq_hist = yf.Ticker(LEVERAGED_TICKER).history(period="5d", auto_adjust=True)
    vix_hist = yf.Ticker(VIX_TICKER).history(period="5d", auto_adjust=True)
    if spy_hist.empty:
        raise RuntimeError(f"yfinance returned no data for {SIGNAL_TICKER}")
    if tqqq_hist.empty:
        raise RuntimeError(f"yfinance returned no data for {LEVERAGED_TICKER}")
    if vix_hist.empty:
        raise RuntimeError(f"yfinance returned no data for {VIX_TICKER}")
    spy_close = float(spy_hist["Close"].iloc[-1])
    spy_ma_50 = float(spy_hist["Close"].rolling(MA_WINDOW).mean().iloc[-1])
    spy_ma_200 = float(spy_hist["Close"].rolling(SPY_TREND_MA_WINDOW).mean().iloc[-1])
    tqqq_close = float(tqqq_hist["Close"].iloc[-1])
    vix_close = float(vix_hist["Close"].iloc[-1])

    # Sector data for sector_momentum_top3_monthly. Period = lookback + buffer.
    sector_period = f"{SECTOR_LOOKBACK_DAYS + 30}d"
    sector_close_history: dict[str, list[float]] = {}
    sector_close_today: dict[str, float] = {}
    for sym in SECTOR_TICKERS:
        h = yf.Ticker(sym).history(period=sector_period, auto_adjust=True)
        if h.empty:
            print(f"  WARNING: yfinance returned no data for sector {sym}")
            continue
        sector_close_history[sym] = h["Close"].tolist()
        sector_close_today[sym] = float(h["Close"].iloc[-1])

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return {
        "today": today_str,
        "spy_close_today": spy_close,
        "spy_ma_today": spy_ma_50,           # legacy alias for leveraged_trend
        "spy_ma_200_today": spy_ma_200,
        "tqqq_close_today": tqqq_close,
        "vix_close_today": vix_close,
        "spy_close_history": spy_hist["Close"].tolist()[-MA_WINDOW - 1:],
        "sector_close_history": sector_close_history,
        "sector_close_today": sector_close_today,
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
        "regime_at_entry": market_data.get("regime", "unknown"),
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

    # Step 2: market-hours guard — only act during RTH.
    # Must run BEFORE reconcile so catch-up runs (StartWhenAvailable firing hours
    # after the scheduled slot) don't churn the broker and Pushover for nothing.
    if not _market_is_open():
        now_iso = datetime.now(timezone.utc).isoformat()
        print(f"Market closed at {now_iso} — ensemble cycle skipped.")
        return

    # Step 3: reconcile (catch drift before deciding)
    try:
        reconciler.reconcile(dry_run=False)
    except Exception as e:
        print(f"reconciler failed (non-fatal): {e}")
        pushover.send("Ensemble reconciler failed", str(e))

    # Step 4: market data
    try:
        market_data = _fetch_market_data()
    except Exception as e:
        print(f"market data fetch failed: {e}")
        pushover.send("Ensemble ABORT", f"market data fetch failed: {e}")
        sys.exit(1)
    print(f"Market: SPY ${market_data['spy_close_today']:.2f} vs 50d MA ${market_data['spy_ma_today']:.2f} / "
          f"200d MA ${market_data['spy_ma_200_today']:.2f}, "
          f"TQQQ ${market_data['tqqq_close_today']:.2f}, VIX {market_data['vix_close_today']:.2f}")

    # Step 5: regime classification. preflight already validated MACRO; we re-fetch
    # the data here because preflight only returns ok/reason (not the data dict).
    _, _, macro_data = macro_consumer.validate()
    regime, regime_reason = regime_router.classify(
        spy_close=market_data["spy_close_today"],
        spy_ma_200=market_data["spy_ma_200_today"],
        vix=market_data["vix_close_today"],
        macro_data=macro_data,
    )
    market_data["regime"] = regime
    active_names = set(regime_router.active_strategies(regime))
    print(f"Regime: {regime} — {regime_reason}")
    print(f"Active components this cycle: {sorted(active_names) or 'none (cash)'}")

    # Step 6: ask each active strategy to decide
    client = trading_client()
    account = client.get_account()
    account_value = float(account.equity)
    positions_mkt_value = _current_positions_market_value(client)
    print(f"Equity: ${account_value:,.2f}  Positions: {positions_mkt_value or 'none'}")

    # Advance the drawdown kill-switch high-water-mark. preflight only reads/inits
    # peak_equity via load_or_init; nothing in the live ensemble path advanced it on
    # new equity highs (the retired run_trading.py was the only updater), so the peak
    # had been frozen at the last run_trading.py execution — understating drawdown and
    # under-arming the kill switch. Update it here every cycle.
    acct_state, _ = account_state.load_or_init(account_value)
    acct_state, hwm_updated = account_state.update_peak_if_higher(acct_state, account_value)
    if hwm_updated:
        print(f"  peak_equity advanced to ${account_value:,.2f}")

    for strategy in ACTIVE_STRATEGIES:
        if strategy.name not in active_names:
            print(f"\n--- {strategy.name} ---")
            print(f"  skipped: not active in regime {regime}")
            continue
        state = strategy_state.load_state(strategy.name)
        print(f"\n--- {strategy.name} ---")
        print(f"  state in: {state}")
        actions = strategy.decide_actions(state, market_data, account_value, positions_mkt_value)
        if not actions:
            print(f"  no actions this fire")
            strategy_state.save_state(strategy.name, state)
            continue

        any_failed = False
        for decision in actions:
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
                any_failed = True
                # Continue trying remaining legs — a single failed leg shouldn't
                # block the rest of a multi-leg rebalance.

        if any_failed:
            # Don't persist state on any execution failure — next fire will
            # re-evaluate from prior state. Safer than half-committing the rebalance.
            print(f"  state NOT persisted (partial execution failure)")
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
            print("GRADUATION GATE MET — Pushover sent.")
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
