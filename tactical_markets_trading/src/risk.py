"""Phase 2 risk primitives: stop computation, position sizing, concentration checks.

All functions are pure (no I/O, no Alpaca calls) so they can be unit-tested directly.
The orchestrator (run_trading.py) is responsible for fetching account state and
positions from Alpaca and passing them in as arguments.
"""

STOP_PCT_DEFAULT = 0.025  # 2.5% from entry fill. Phase 2.0 fixed; ATR-based deferred to Phase 2.5.
MAX_POSITION_PCT = 0.05   # 5% per trade concentration cap (PRD FR12).
MAX_OPEN_PCT = 0.20       # 20% total open positions cap (PRD FR12).
MAX_TICKER_PCT = 0.25     # 25% single-ticker cap (PRD FR12).
MAX_RISK_PCT = 0.02       # 2% per-trade risk budget (PRD FR11).


def compute_stop_price(fill_price: float, stop_pct: float = STOP_PCT_DEFAULT) -> float:
    """Story 1a.1: Compute the broker-side stop price as a fixed percentage below the entry fill.

    Pure function — no I/O, no Alpaca calls.

    Args:
        fill_price: the average fill price of the entry order.
        stop_pct: the fractional drawdown for the stop (default 0.025 = 2.5%).

    Returns:
        Rounded-to-2dp stop price.
    """
    return round(fill_price * (1 - stop_pct), 2)


def compute_position_size(
    account_value: float,
    entry_price: float,
    stop_price: float,
    max_position_pct: float = MAX_POSITION_PCT,
    max_risk_pct: float = MAX_RISK_PCT,
) -> tuple[float, str]:
    """Story 1c.1: Compute position size as min(risk-based, concentration cap).

    risk_based_qty = (account_value * max_risk_pct) / (entry_price - stop_price)
    cap_qty        = (account_value * max_position_pct) / entry_price
    chosen = min of the two; sizing_rule_used = the rule that bound.

    Pure function. No Alpaca calls. Returns fractional qty (Alpaca supports it).

    Returns:
        (chosen_qty, sizing_rule_used) where sizing_rule_used ∈ {"risk_based", "concentration_cap"}.

    Raises:
        ValueError if stop_price >= entry_price (would be a zero-or-negative-risk trade,
        which is a sign error per Murat's highest-risk Phase 2 failure mode).
    """
    if stop_price >= entry_price:
        raise ValueError(
            f"stop_price ({stop_price}) must be strictly less than entry_price ({entry_price})"
        )
    risk_dollars = account_value * max_risk_pct
    risk_based_qty = risk_dollars / (entry_price - stop_price)
    cap_qty = (account_value * max_position_pct) / entry_price
    if risk_based_qty < cap_qty:
        return risk_based_qty, "risk_based"
    return cap_qty, "concentration_cap"


def check_concentration(
    symbol: str,
    proposed_qty: float,
    proposed_price: float,
    current_positions: dict[str, float],
    account_value: float,
    max_position_pct: float = MAX_POSITION_PCT,
    max_open_pct: float = MAX_OPEN_PCT,
    max_ticker_pct: float = MAX_TICKER_PCT,
) -> tuple[bool, str]:
    """Story 1c.2: Run the three FR12 concentration checks pre-trade.

    Args:
        symbol: the candidate ticker to buy.
        proposed_qty: shares to buy.
        proposed_price: expected fill price (mark or last close).
        current_positions: {symbol: market_value} for all currently-held positions.
            Caller should fetch from Alpaca and pre-compute market values.
        account_value: total account equity.
        max_position_pct: per-trade cap (default 0.05).
        max_open_pct: total open cap (default 0.20).
        max_ticker_pct: per-ticker cap (default 0.25).

    Returns:
        (ok, reason) tuple. reason is human-readable on failure, "ok" on pass.
        Checks fail-fast in order: per-trade → open-total → per-ticker.
    """
    proposed_value = proposed_qty * proposed_price

    per_trade_cap = account_value * max_position_pct
    if proposed_value > per_trade_cap:
        return (
            False,
            f"per_trade_concentration: proposed ${proposed_value:.2f} > cap ${per_trade_cap:.2f} "
            f"({max_position_pct * 100:.0f}% of ${account_value:.2f})",
        )

    open_total = sum(current_positions.values())
    open_cap = account_value * max_open_pct
    if open_total + proposed_value > open_cap:
        return (
            False,
            f"open_total_concentration: existing ${open_total:.2f} + proposed ${proposed_value:.2f} "
            f"= ${open_total + proposed_value:.2f} > cap ${open_cap:.2f} "
            f"({max_open_pct * 100:.0f}% of ${account_value:.2f})",
        )

    existing_for_symbol = current_positions.get(symbol, 0.0)
    ticker_cap = account_value * max_ticker_pct
    if existing_for_symbol + proposed_value > ticker_cap:
        return (
            False,
            f"ticker_concentration: existing {symbol} ${existing_for_symbol:.2f} + proposed "
            f"${proposed_value:.2f} = ${existing_for_symbol + proposed_value:.2f} > cap "
            f"${ticker_cap:.2f} ({max_ticker_pct * 100:.0f}% of ${account_value:.2f})",
        )

    return True, "ok"
