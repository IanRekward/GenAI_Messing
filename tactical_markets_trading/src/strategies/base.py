"""Strategy ABC + Decision dataclass for Phase 3 ensemble.

Each strategy implements `decide()` as a pure-as-possible function over current
state. The orchestrator handles the I/O (order submission, persistence, etc.).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


@dataclass
class Decision:
    """A single trading decision from a strategy on a given day.

    action: what the strategy wants to do this fire
        - "buy":   open a new position (qty, symbol required)
        - "sell":  close an existing position (symbol required; qty defaults to
                   actual Alpaca position qty)
        - "hold":  do nothing (no-op; included so we always have an explicit answer)

    reason: human-readable explanation. Persisted with the trade for audit.
            Goes into the Pushover message body.

    trigger: machine-readable categorization for ledger filtering:
        - "trend_entry":   trend turned on, entering
        - "trend_exit":    trend turned off, exiting
        - "stop_fired":    trailing stop hit, exiting (and cooldown begins)
        - "cooldown":      not entering because of post-stop cooldown
        - "no_signal":     trend off, no action
        - "already_held":  trend on but we're already in position
    """
    action: Literal["buy", "sell", "hold"]
    symbol: str | None = None
    qty: float | None = None
    notional: float | None = None
    reason: str = ""
    trigger: str = ""


class Strategy(ABC):
    """Base class for all ensemble components.

    Each subclass declares its `name` (used in trade records' `strategy` field
    and in state-file paths) and implements `decide()`.

    Strategies are stateful between fires — they persist state across runs via
    `strategy_state.py`. The orchestrator gives each strategy its own state dict.
    """

    name: str  # set by subclass

    def __init__(self):
        if not hasattr(self, "name") or not self.name:
            raise NotImplementedError(f"{type(self).__name__} must set class-level `name`")

    @abstractmethod
    def decide(self, state: dict, market_data: dict, account_value: float,
               current_positions: dict[str, float]) -> Decision:
        """Decide today's single action.

        Args:
            state: this strategy's persistent state (mutable; orchestrator persists after).
                Strategy is free to read and write keys here.
            market_data: price data the strategy needs. Concrete keys depend on strategy;
                orchestrator should pre-fetch and pass in. Typically: {"SPY_close": [...],
                "SPY_ma_50": ..., "TQQQ_close": ..., etc.}
            account_value: total account equity from Alpaca.
            current_positions: {symbol: market_value} of all current Alpaca positions.

        Returns:
            A Decision describing what to do. The orchestrator executes it.

        Idempotency contract: calling decide() multiple times on the same state +
        market_data MUST return the same decision. State mutation only happens when
        decide() observes a new market input (price change, signal flip, etc.).
        """
        ...

    def decide_actions(self, state: dict, market_data: dict, account_value: float,
                       current_positions: dict[str, float]) -> list[Decision]:
        """Multi-action variant. Default wraps decide() so single-action strategies
        need only implement decide(). Multi-leg strategies (e.g., monthly rebalance
        across multiple sectors in one fire) override this to return a list.

        Empty list means "no action this fire" — equivalent to a single hold Decision
        but avoids generating a Decision record per no-op.
        """
        d = self.decide(state, market_data, account_value, current_positions)
        return [d]
