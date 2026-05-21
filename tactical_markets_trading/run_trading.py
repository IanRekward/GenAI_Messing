import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from alpaca.trading.enums import OrderSide, QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest

import pushover
import account_state
import macro_consumer
import preflight
import reconciler
import risk
from alpaca_connector import load_env, trading_client
from order_builder import THESES_PATH, get_estimated_entry_price, submit_order
from trade_logger import log_entry

# RETIRED 2026-05-21: 33-year backtest (CAGR 0.62%, Sharpe 0.19) + walk-forward
# evidence show this signal does not work. Replacement strategy (TQQQ trend +
# trailing stop) is in Phase 3 design but not yet wired. Until then, this flag
# makes the scheduled Entry task short-circuit cleanly without trading the dead
# signal. Existing open positions (if any) are still managed by the Exit task.
# To re-enable for any reason: set to False. To remove the bot entirely from
# entries: delete the Windows "Tactical Trading Entry" scheduled task.
SECTOR_ROTATION_5D_RETIRED = True


def today_signals() -> list[dict]:
    today = datetime.now(timezone.utc).date()
    results = []
    with open(THESES_PATH) as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("signal") and datetime.fromisoformat(entry["as_of"]).date() == today:
                results.append(entry)
    return results


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


def _extract_macro_snapshot(regime_data: dict) -> dict:
    """Story 1b.6: persist the regime decision the trade was made under."""
    return {
        "run_timestamp": regime_data.get("run_timestamp"),
        "composite_band": regime_data.get("composite_band"),
        "regime": regime_data.get("regime"),
        "weights_hash": regime_data.get("weights_hash"),
        "neutralized": regime_data.get("neutralized", False),
    }


def _current_positions_market_value() -> dict[str, float]:
    """Story 1c.3: {symbol: market_value} for all current Alpaca positions, for check_concentration."""
    client = trading_client()
    return {p.symbol: float(p.market_value) for p in client.get_all_positions()}


def main():
    # 2026-05-21: sector_rotation_5d retired as the live signal (33-year backtest
    # CAGR 0.62%, Sharpe 0.19). The scheduled task still fires this script but we
    # short-circuit at the top — no new entries, no MICRO consumption. Exit task
    # continues to manage any existing open positions until they close out.
    if SECTOR_ROTATION_5D_RETIRED:
        print("Entry path RETIRED — sector_rotation_5d signal is dead (see TODO.md 2026-05-21).")
        print("No new positions will be opened. Existing positions still managed by Exit task.")
        print("Run `python -c \"import run_trading; run_trading.SECTOR_ROTATION_5D_RETIRED = False\"` and re-run if testing.")
        return

    # Reconcile FIRST so local state matches Alpaca before preflight (kill-switch check
    # reads trades.jsonl for consecutive-loss math). Also prevents transient drift events
    # in the post-cycle report when a queued exit filled overnight but wasn't yet backfilled.
    try:
        reconciler.reconcile(dry_run=False)
    except Exception as e:
        print(f"reconciler pre-entry failed (non-fatal): {e}")
        pushover.send("Reconciler pre-entry failed", str(e))

    # Story 1b.5 + 1c.5: preflight ABORT on broken state (env, Alpaca, MICRO, MACRO, kill switch).
    ok, reason = preflight.check_entry()
    if not ok:
        print(f"Preflight FAILED: {reason}")
        title = "Tactical Trading ABORT: KILL SWITCH" if reason.startswith("kill_switch_drawdown") else "Tactical Trading ABORT"
        pushover.send(title, reason)
        sys.exit(1)

    theses = today_signals()
    if not theses:
        print("No signal for today — no trade.")
        return

    # Story 1b.6: one regime decision for the batch of today's theses.
    macro_ok, macro_reason, regime_data = macro_consumer.validate()
    if not macro_ok:
        print(f"MACRO validate failed post-preflight: {macro_reason}")
        pushover.send("Tactical Trading ABORT", f"macro_broken_post_preflight: {macro_reason}")
        sys.exit(1)
    multiplier = macro_consumer.size_multiplier(regime_data)
    macro_snapshot = _extract_macro_snapshot(regime_data)

    if multiplier == 0.0:
        msg = f"MACRO size-down to 0 ({regime_data.get('composite_band')} regime) — no entry today (reason: {macro_reason})"
        print(msg)
        pushover.send("Tactical Trading: MACRO blocks entry", msg)
        return

    # Story 1c.3 + 1c.4: fetch account state for risk-based sizing.
    client = trading_client()
    account = client.get_account()
    account_value = float(account.equity)
    # Update high-water-mark if today's equity exceeds peak.
    state, _ = account_state.load_or_init(account_value)
    state, hwm_updated = account_state.update_peak_if_higher(state, account_value)
    if hwm_updated:
        print(f"New account high-water-mark: ${account_value:,.2f}")

    if multiplier != 1.0:
        print(f"MACRO size multiplier {multiplier}x will be applied to risk-based qty")

    for thesis in theses:
        symbol = thesis["buy"]

        if already_traded_today(symbol):
            print(f"Already submitted a buy for {symbol} today — skipping (intra-day dedup).")
            continue

        if at_position_limit():
            print(f"At 5-position concurrency limit — skipping {symbol} and remaining theses.")
            break

        # Story 1c.3: risk-based sizing. Estimate entry, compute stop, compute qty.
        try:
            entry_price_est = get_estimated_entry_price(symbol)
        except Exception as e:
            print(f"Could not estimate entry price for {symbol}: {e} — skipping")
            pushover.send(f"Skipped {symbol}: entry-price estimate failed", str(e))
            continue
        stop_price_est = risk.compute_stop_price(entry_price_est)
        risk_qty, sizing_rule_used = risk.compute_position_size(account_value, entry_price_est, stop_price_est)
        final_qty = risk_qty * multiplier
        if multiplier != 1.0:
            sizing_rule_used = f"{sizing_rule_used}_with_macro_x_{multiplier}"

        # Story 1c.4: pre-trade concentration checks against current Alpaca portfolio.
        current_positions = _current_positions_market_value()
        conc_ok, conc_reason = risk.check_concentration(
            symbol=symbol,
            proposed_qty=final_qty,
            proposed_price=entry_price_est,
            current_positions=current_positions,
            account_value=account_value,
        )
        if not conc_ok:
            print(f"Pre-trade concentration BLOCK for {symbol}: {conc_reason}")
            pushover.send(f"Pre-trade BLOCK: {symbol}", conc_reason)
            continue

        print(f"Signal: BUY {symbol} qty={final_qty:.4f} (est entry ${entry_price_est:.2f}, "
              f"stop ${stop_price_est:.2f}, rule={sizing_rule_used}, spread {thesis['spread_pct']}%)")
        order_result = submit_order(thesis, qty=final_qty)
        print(f"Order submitted: {order_result['order_id']} status={order_result['status']}")
        record = log_entry(order_result, macro_snapshot=macro_snapshot, sizing_rule_used=sizing_rule_used)
        print(f"Trade logged: {record['trade_id']}")
        print(f"  Entry: ${record['fill_price']} x {record['fill_qty']} {record['symbol']}")
        print(f"  Exit planned: {record['exit_time_planned']}")
        actual_value = record["fill_price"] * record["fill_qty"]
        pushover.send(
            f"Entered {symbol} ${actual_value:,.0f}",
            f"Filled {record['fill_qty']:.4f} @ ${record['fill_price']:.2f} | Spread: {thesis['spread_pct']}% | "
            f"Sizing: {sizing_rule_used} | MACRO {regime_data.get('composite_band')}/{regime_data.get('regime')} x{multiplier} | "
            f"Exit: {record['exit_time_planned'][:10]}",
        )


if __name__ == "__main__":
    load_env()
    try:
        main()
    except Exception as e:
        pushover.send("Tactical Trading ENTRY FAILED", str(e))
        raise
    finally:
        # Story 2.3: post-cycle drift report (passive monitoring). Runs whether or not
        # main() raised. Non-fatal — the Entry task has already done its work.
        try:
            events = reconciler.report_and_notify()
            if events:
                print(f"Post-cycle drift: {len(events)} event(s) recorded to drift_log.jsonl")
        except Exception as e:
            print(f"reconciler post-report failed (non-fatal): {e}")
            try:
                pushover.send("Reconciler post-report failed", str(e))
            except Exception:
                pass
