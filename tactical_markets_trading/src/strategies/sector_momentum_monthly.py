"""sector_momentum_top3_monthly — the cross-sectional diversifier.

Mechanics (per phase-3-ensemble-design.md):

  Signal:    at each month's first market day, rank the 9 SPDR sector ETFs by
             trailing 3-month total return; hold the top-3 equal-weighted within
             this strategy's allocated notional (1/3 each)
  Position:  one third of allocated notional in each of the top-3 sectors,
             whole-share floor
  Hold:      until next month's rebalance

This strategy is naturally multi-leg: a rebalance day produces up to 6 actions
(sell up-to-3 dropouts, buy up-to-3 new entrants). On non-rebalance days, the
strategy returns no actions (the orchestrator no-ops cleanly).

Persisted state schema (data/strategy_state_sector_momentum_top3_monthly.json):
  {
    "last_rebalance_month": "YYYY-MM" | null,
    "current_holdings": [symbol, ...],
    "last_decision_at": ISO8601
  }
"""
from __future__ import annotations

from datetime import datetime, timezone

from .base import Decision, Strategy

SECTOR_TICKERS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
LOOKBACK_DAYS = 63  # ~3 months of trading days
TOP_N = 3
DEFAULT_ALLOCATION_PCT = 0.33


class SectorMomentumMonthlyStrategy(Strategy):
    name = "sector_momentum_top3_monthly"

    def __init__(self, allocation_pct: float = DEFAULT_ALLOCATION_PCT):
        super().__init__()
        self.allocation_pct = allocation_pct

    def decide(self, state: dict, market_data: dict, account_value: float,
               current_positions: dict[str, float]) -> Decision:
        # Single-Decision contract still needed for the base ABC. Returns a
        # representative summary Decision; real execution goes through
        # decide_actions(). Orchestrator calls decide_actions() so this path is
        # only exercised by direct callers (tests / debugging).
        actions = self.decide_actions(state, market_data, account_value, current_positions)
        if not actions:
            return Decision(action="hold", reason="not a rebalance day", trigger="no_signal")
        return actions[0]

    def decide_actions(self, state: dict, market_data: dict, account_value: float,
                       current_positions: dict[str, float]) -> list[Decision]:
        """Multi-leg decision for monthly rebalance.

        market_data must contain:
          - "today":                  ISO date string (YYYY-MM-DD); orchestrator
                                       passes the decision day (yesterday's close
                                       is the signal, but the trade fires today)
          - "sector_close_history":   {symbol: [closes, ...]} with at least
                                       LOOKBACK_DAYS + 1 closes per sector
          - "sector_close_today":     {symbol: latest close}
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        state["last_decision_at"] = now_iso

        today_str = market_data["today"]  # YYYY-MM-DD
        today_month = today_str[:7]  # YYYY-MM
        last_month = state.get("last_rebalance_month")

        # Rebalance trigger: first market-day this strategy sees in a new month.
        # On the FIRST EVER run with no last_rebalance_month, we rebalance immediately.
        if last_month == today_month:
            return []  # already rebalanced this month

        # Compute 3-month returns per sector
        history = market_data["sector_close_history"]
        ranked: list[tuple[str, float]] = []
        for sym in SECTOR_TICKERS:
            closes = history.get(sym, [])
            if len(closes) < LOOKBACK_DAYS + 1:
                continue
            start = float(closes[-LOOKBACK_DAYS - 1])
            end = float(closes[-1])
            if start <= 0:
                continue
            ranked.append((sym, end / start - 1.0))
        if len(ranked) < TOP_N:
            return []  # not enough data to rank — skip this rebalance
        ranked.sort(key=lambda x: x[1], reverse=True)
        new_top = [sym for sym, _ in ranked[:TOP_N]]

        current = list(state.get("current_holdings") or [])
        to_sell = [s for s in current if s not in new_top]
        to_buy = [s for s in new_top if s not in current]

        per_leg_notional = (account_value * self.allocation_pct) / TOP_N
        actions: list[Decision] = []

        # Sells first so the cash from sells is available for the buys
        for sym in to_sell:
            actions.append(Decision(
                action="sell", symbol=sym,
                reason=f"monthly rebalance {today_month}: {sym} dropped from top-{TOP_N}",
                trigger="trend_exit",
            ))

        prices = market_data["sector_close_today"]
        for sym in to_buy:
            price = float(prices.get(sym, 0))
            if price <= 0:
                continue
            qty = int(per_leg_notional / price)
            if qty < 1:
                continue
            actions.append(Decision(
                action="buy", symbol=sym, qty=float(qty),
                reason=(f"monthly rebalance {today_month}: {sym} entered top-{TOP_N}; "
                        f"target ${per_leg_notional:.0f} / ${price:.2f} = {qty} whole shares"),
                trigger="trend_entry",
            ))

        # Update state to reflect new month's holdings (orchestrator will persist)
        state["last_rebalance_month"] = today_month
        state["current_holdings"] = new_top
        return actions
