"""trend_leveraged_tqqq — the headline Phase 3 strategy.

Mechanics (validated by walk-forward: TRAIN Sharpe 1.87 -> TEST Sharpe 1.83 OOS,
98% retention; per research/data/trailing_stop_walk_forward_report.md):

  Signal:     SPY > 50-day moving average (yesterday's close)
  Position:   TQQQ, whole-share floor (Alpaca rejects fractional GTC stops)
  Stop:       software-managed 5% trailing stop on TQQQ in-position peak
  Re-entry:   only when (a) trend signal on AND (b) TQQQ above prior in-position peak
              after a stop-out (the "cooldown" prevents immediate re-entry on whipsaw)

Caveats baked into design:
  - Backtest used closing prices. Orchestrator should run after market close OR at
    market open using yesterday's close — either is fine, but stay consistent.
  - Software-managed stop means the bot MUST run daily during market days. Multi-day
    outage during a crash = unhedged.
  - The 5% stop on TQQQ corresponds to roughly a 1.67% drop on QQQ. The trailing
    stop fires more often than the 200d MA flips. Expect 5-15 stop-outs per year.

Persisted state schema (data/strategy_state_trend_leveraged_tqqq.json):
  {
    "in_position": bool,
    "position_peak_price": float | null,
    "entry_price": float | null,
    "entry_time": ISO8601 string | null,
    "stopped_out": bool,           # cooldown flag
    "last_decision_at": ISO8601    # for debugging
  }
"""
from __future__ import annotations

from datetime import datetime, timezone

from .base import Decision, Strategy

# Strategy parameters (frozen post walk-forward)
SIGNAL_TICKER = "SPY"
LEVERAGED_TICKER = "TQQQ"
MA_WINDOW = 50          # walk-forward optimum
TRAILING_STOP_PCT = 0.05  # walk-forward optimum
DEFAULT_ALLOCATION_PCT = 0.33  # Phase 3.1: 33% of account; ensemble may override


class LeveragedTrendStrategy(Strategy):
    name = "trend_leveraged_tqqq"

    def __init__(self, allocation_pct: float = DEFAULT_ALLOCATION_PCT):
        super().__init__()
        self.allocation_pct = allocation_pct

    def decide(self, state: dict, market_data: dict, account_value: float,
               current_positions: dict[str, float]) -> Decision:
        """Decide today's action.

        market_data must contain:
          - "spy_close_today":     latest SPY close (float)
          - "spy_ma_today":        SPY's MA_WINDOW-day moving average (float)
          - "tqqq_close_today":    latest TQQQ close (float)

        State mutations (this method writes into `state`):
          - position_peak_price: updated whenever TQQQ closes higher than prior peak
          - in_position, entry_price, entry_time: updated on entry/exit
          - stopped_out: set True when stop fires; cleared when trend flips off
          - last_decision_at: timestamped each call
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        state["last_decision_at"] = now_iso

        spy_close = float(market_data["spy_close_today"])
        spy_ma = float(market_data["spy_ma_today"])
        tqqq_close = float(market_data["tqqq_close_today"])

        trend_on = spy_close > spy_ma
        in_position = bool(state.get("in_position", False))
        stopped_out = bool(state.get("stopped_out", False))
        actual_tqqq_held = current_positions.get(LEVERAGED_TICKER, 0.0)

        # Drift defense: local state says in_position but Alpaca shows nothing.
        # Trust Alpaca; reconciler should have backfilled but didn't. Clear local
        # state and proceed as out-of-position. Log via Decision.reason.
        if in_position and actual_tqqq_held < 1e-6:
            state["in_position"] = False
            state["position_peak_price"] = None
            in_position = False

        # Path 1: currently in position — check stop and trend
        if in_position:
            peak = float(state.get("position_peak_price") or tqqq_close)
            if tqqq_close > peak:
                state["position_peak_price"] = tqqq_close
                peak = tqqq_close

            stop_price = peak * (1 - TRAILING_STOP_PCT)
            if tqqq_close <= stop_price:
                # Trailing stop hit
                state["in_position"] = False
                state["stopped_out"] = True
                state["position_peak_price"] = None
                return Decision(
                    action="sell", symbol=LEVERAGED_TICKER,
                    reason=f"trailing stop: TQQQ ${tqqq_close:.2f} <= peak ${peak:.2f} * (1 - {TRAILING_STOP_PCT}) = ${stop_price:.2f}",
                    trigger="stop_fired",
                )
            if not trend_on:
                # Trend turned off
                state["in_position"] = False
                state["position_peak_price"] = None
                state["stopped_out"] = False  # trend-off exit also resets cooldown
                return Decision(
                    action="sell", symbol=LEVERAGED_TICKER,
                    reason=f"trend off: SPY ${spy_close:.2f} <= {MA_WINDOW}d MA ${spy_ma:.2f}",
                    trigger="trend_exit",
                )
            return Decision(
                action="hold", symbol=LEVERAGED_TICKER,
                reason=f"holding: peak ${peak:.2f}, stop at ${stop_price:.2f}, TQQQ ${tqqq_close:.2f}",
                trigger="already_held",
            )

        # Path 2: not in position — check entry conditions
        if not trend_on:
            # Cooldown clears whenever trend is off (regardless of in-position).
            # The cooldown's purpose is to prevent immediate re-entry on whipsaw
            # AFTER a stop fires while the trend signal is still on. Once the
            # trend itself turns off, the next trend-on signal is a clean re-entry.
            if stopped_out:
                state["stopped_out"] = False
            return Decision(
                action="hold", reason=f"no trend: SPY ${spy_close:.2f} <= {MA_WINDOW}d MA ${spy_ma:.2f}"
                                       + (" (cooldown cleared)" if stopped_out else ""),
                trigger="no_signal",
            )
        if stopped_out:
            # Cooldown: stopped out and trend still on. Wait for trend to flip off first.
            return Decision(
                action="hold",
                reason="cooldown: stopped out previously, waiting for trend to flip off",
                trigger="cooldown",
            )
        # Trend on, not in position, not in cooldown -> BUY
        target_notional = account_value * self.allocation_pct
        target_qty = target_notional / tqqq_close
        whole_qty = int(target_qty)
        if whole_qty < 1:
            return Decision(
                action="hold",
                reason=f"insufficient sizing: target ${target_notional:.0f} / ${tqqq_close:.2f} = {target_qty:.4f} qty (need >= 1 whole share)",
                trigger="no_signal",
            )
        # Mutate state — we'll be in position after this fills
        state["in_position"] = True
        state["entry_price"] = tqqq_close
        state["entry_time"] = now_iso
        state["position_peak_price"] = tqqq_close
        state["stopped_out"] = False
        return Decision(
            action="buy", symbol=LEVERAGED_TICKER, qty=float(whole_qty),
            reason=f"trend on: SPY ${spy_close:.2f} > {MA_WINDOW}d MA ${spy_ma:.2f}; "
                   f"target ${target_notional:.0f} / ${tqqq_close:.2f} = {whole_qty} whole shares",
            trigger="trend_entry",
        )
