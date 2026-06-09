"""trend_following_spy_200d — the steady-contributor Phase 3 strategy.

Mechanics (per phase-3-ensemble-design.md):

  Signal:    SPY > 200-day moving average (yesterday's close)
  Position:  SPY at allocated notional, whole-share floor
  Exit:      SPY < 200d MA (the MA is the exit; no stop)
  Re-entry:  no cooldown — flips back in as soon as signal re-asserts

This is the "low Sharpe but stable" ensemble contributor. On its own it's weak
(slow exit gives back significant gains during fast drawdowns), but it
diversifies the leveraged_trend and sector_momentum components.

Persisted state schema (data/strategy_state_trend_following_spy_200d.json):
  {
    "in_position": bool,
    "entry_price": float | null,
    "entry_time": ISO8601 string | null,
    "last_decision_at": ISO8601
  }
"""
from __future__ import annotations

from datetime import datetime, timezone

from .base import Decision, Strategy

TICKER = "SPY"
MA_WINDOW = 200
DEFAULT_ALLOCATION_PCT = 0.33


class SpyTrendStrategy(Strategy):
    name = "trend_following_spy_200d"

    def __init__(self, allocation_pct: float = DEFAULT_ALLOCATION_PCT):
        super().__init__()
        self.allocation_pct = allocation_pct

    def decide(self, state: dict, market_data: dict, account_value: float,
               current_positions: dict[str, float]) -> Decision:
        """Decide today's action.

        market_data must contain:
          - "spy_close_today":      latest SPY close (float)
          - "spy_ma_200_today":     SPY's 200-day moving average (float)
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        state["last_decision_at"] = now_iso

        spy_close = float(market_data["spy_close_today"])
        spy_ma = float(market_data["spy_ma_200_today"])
        trend_on = spy_close > spy_ma
        in_position = bool(state.get("in_position", False))
        actual_held = current_positions.get(TICKER, 0.0)

        # Drift defense: local state says in_position but Alpaca shows nothing.
        # Trust Alpaca and proceed as out-of-position.
        if in_position and actual_held < 1e-6:
            state["in_position"] = False
            in_position = False

        if in_position:
            if not trend_on:
                state["in_position"] = False
                return Decision(
                    action="sell", symbol=TICKER,
                    reason=f"trend off: SPY ${spy_close:.2f} <= {MA_WINDOW}d MA ${spy_ma:.2f}",
                    trigger="trend_exit",
                )
            return Decision(
                action="hold", symbol=TICKER,
                reason=f"holding SPY: ${spy_close:.2f} > {MA_WINDOW}d MA ${spy_ma:.2f}",
                trigger="already_held",
            )

        if not trend_on:
            return Decision(
                action="hold",
                reason=f"no trend: SPY ${spy_close:.2f} <= {MA_WINDOW}d MA ${spy_ma:.2f}",
                trigger="no_signal",
            )

        # Trend on, not in position -> BUY
        target_notional = account_value * self.allocation_pct
        target_qty = target_notional / spy_close
        whole_qty = int(target_qty)
        if whole_qty < 1:
            return Decision(
                action="hold",
                reason=(f"insufficient sizing: target ${target_notional:.0f} / "
                        f"${spy_close:.2f} = {target_qty:.4f} qty (need >= 1 whole share)"),
                trigger="no_signal",
            )
        state["in_position"] = True
        state["entry_price"] = spy_close
        state["entry_time"] = now_iso
        return Decision(
            action="buy", symbol=TICKER, qty=float(whole_qty),
            reason=(f"trend on: SPY ${spy_close:.2f} > {MA_WINDOW}d MA ${spy_ma:.2f}; "
                    f"target ${target_notional:.0f} / ${spy_close:.2f} = {whole_qty} whole shares"),
            trigger="trend_entry",
        )
