"""Tests for src/risk.py — Phase 2 risk primitives.

Pure-function tests with no Alpaca/network dependencies. Per Murat's party-mode
review: sizing sign-error is the highest P(occurrence) × Impact failure mode in
Phase 2; these tests are the first regression guard.
"""
import pytest

from risk import (
    KILL_SWITCH_DRAWDOWN_PCT,
    STOP_PCT_DEFAULT,
    check_concentration,
    check_kill_switch,
    compute_position_size,
    compute_stop_price,
)


# Story 1a.1: compute_stop_price


def test_compute_stop_price_default_is_2_5_percent_below_entry():
    assert compute_stop_price(100.0) == 97.50


def test_compute_stop_price_uses_supplied_pct():
    assert compute_stop_price(100.0, 0.05) == 95.00


def test_compute_stop_price_rounds_to_2_decimals():
    # 91.35 * 0.975 = 89.0662 → rounds to 89.07
    assert compute_stop_price(91.35) == 89.07


def test_compute_stop_price_default_constant_is_0_025():
    assert STOP_PCT_DEFAULT == 0.025


# Story 1c.1: compute_position_size


def test_position_size_concentration_cap_binds_at_100k_paper():
    # account=100k, entry=$90, stop=$87.75 (2.5%)
    # risk_based: 200/2.25 = 88.9 shares
    # cap:        5000/90  = 55.5 shares  ← binds
    qty, rule = compute_position_size(100_000, 90.0, 87.75)
    assert rule == "concentration_cap"
    assert qty == pytest.approx(55.56, abs=0.01)


def test_position_size_risk_based_binds_with_wide_stop():
    # account=100k, entry=$90, stop=$50 (wide 44% stop — wider than 5% cap allows in $)
    # risk_based: 2000/40 = 50 shares = $4500 < 5000 cap ✓ risk_based binds
    qty, rule = compute_position_size(100_000, 90.0, 50.0)
    assert rule == "risk_based"
    assert qty == 50.0


def test_position_size_raises_on_stop_above_entry():
    # Sign-error guard: if stop >= entry, the math would give negative or zero risk
    with pytest.raises(ValueError, match="must be strictly less than"):
        compute_position_size(100_000, 90.0, 90.0)


def test_position_size_raises_on_stop_above_entry_reversed():
    with pytest.raises(ValueError, match="must be strictly less than"):
        compute_position_size(100_000, 90.0, 95.0)


def test_position_size_cap_still_binds_at_10k_phase3_minimum():
    # account=10k, entry=$90, stop=$87.75 (2.5%)
    # risk_based: 200/2.25 = 88.9 — too many shares for $10k? Actually 88*90 = $7920 < $10k
    # cap: 500/90 = 5.55  ← binds (5% of $10k = $500)
    qty, rule = compute_position_size(10_000, 90.0, 87.75)
    assert rule == "concentration_cap"
    assert qty == pytest.approx(5.56, abs=0.01)


# Story 1c.2: check_concentration


def test_concentration_ok_when_proposed_under_all_caps():
    ok, reason = check_concentration(
        symbol="XLE",
        proposed_qty=10,
        proposed_price=90.0,   # $900 proposed
        current_positions={},  # nothing held
        account_value=100_000,
    )
    assert ok
    assert reason == "ok"


def test_concentration_blocks_per_trade_cap():
    # 60 shares × $90 = $5400 > 5% × $100k = $5000 → fail per-trade
    ok, reason = check_concentration(
        symbol="XLE",
        proposed_qty=60,
        proposed_price=90.0,
        current_positions={},
        account_value=100_000,
    )
    assert not ok
    assert "per_trade_concentration" in reason


def test_concentration_blocks_open_total_cap():
    # Proposed $4000 is under per-trade cap, but existing positions sum to $18000.
    # Open total cap = 20% × $100k = $20000. 18000 + 4000 = 22000 > 20000 → fail open-total.
    ok, reason = check_concentration(
        symbol="XLE",
        proposed_qty=44,
        proposed_price=90.0,  # ~$3960
        current_positions={"SPY": 6000.0, "QQQ": 6000.0, "IWM": 6000.0},
        account_value=100_000,
    )
    assert not ok
    assert "open_total_concentration" in reason


def test_concentration_blocks_ticker_cap():
    # Existing XLE $24,500; proposed $1,000 → ticker total $25,500 > 25% × $100k = $25,000 → fail.
    # Note: proposed $1000 is under per-trade ($5k) AND under open-total ($20k - $24.5k = -$4.5k... wait)
    # Actually open total would also be 24500+1000 = 25500 > 20000 → open-total fails FIRST.
    # To isolate ticker check, we need open total under cap.
    # Use account_value=200k: open cap = $40k. XLE existing $24.5k.
    # ticker cap = 25% × $200k = $50k. Existing $24.5k + proposed $26k = $50.5k > $50k → ticker fails.
    # But per_trade cap = 5% × $200k = $10k. Proposed $26k > $10k → per-trade fails FIRST.
    # Pure ticker-cap test needs proposed under per-trade AND open-total but pushing ticker over.
    # account=$1000k. per_trade cap=$50k. ticker cap=$250k. existing XLE=$249k. proposed $50k → ticker total $299k > $250k.
    # open cap = $200k. existing total = $249k > open cap ALREADY. Hmm.
    # Realistic test: account=$200k, existing XLE=$49k (just under per-ticker cap), proposed $2k (under per-trade $10k).
    # existing+proposed = $51k > ticker cap $50k → ticker fail.
    # But open total = $49k + $2k = $51k. open cap = $40k. open-total fails first. Damn.
    # Try: open is fine, ticker fails:
    # account=$400k. per_trade cap=$20k. open cap=$80k. ticker cap=$100k.
    # existing XLE=$99k. existing total=$99k (XLE only). + proposed $2k = open $101k > $80k → open fails first.
    # Conclusion: ticker cap (25%) always > open cap (20%), so per-ticker check only matters when
    # there are MULTIPLE tickers. Let me construct: open is fine across distinct tickers, but adding to existing
    # ticker pushes that one over its individual 25% cap.
    # account=$100k. per_trade=$5k. open=$20k. ticker=$25k. Existing: just XLE=$23k. Open total = $23k > $20k already.
    # Hmm, can't have a single ticker exceed open total cap without open failing.
    # The ticker cap matters only relative to a single SYMBOL within the open total.
    # If existing XLE=$10k and existing SPY=$8k, open=$18k. Then proposed XLE $4k:
    # per_trade $4k OK (<$5k). open $22k > $20k → open fails. Still ticker isn't isolated.
    # Realistically the ticker check is a tighter constraint than open-total only when proposed adds
    # to one existing ticker more than 25%. In normal flow open will block first.
    # So this test verifies the check WORKS (returns ticker failure when relevant), even if rare.
    # Construct: existing XLE=$24k (under 25% cap), open=$24k (over 20%... no).
    # OK realistic: account=$100k. open cap=$20k. ticker cap=$25k. existing XLE=$15k. proposed XLE $3k.
    # per_trade $3k < $5k OK. open $18k < $20k OK. ticker $18k < $25k OK. → ok!
    # To force ticker fail isolated: existing XLE=$24.5k. open total = $24.5k > $20k cap → open fails.
    # So ticker check is genuinely the LAST line — it triggers only when existing+proposed for ONE symbol
    # exceeds 25% while open total is somehow within 20%. Mathematically impossible unless caps are tweaked.
    # The check is defensive (e.g., for a future config where ticker cap < open cap), not currently
    # reachable with defaults. Test with non-default caps:
    ok, reason = check_concentration(
        symbol="XLE",
        proposed_qty=10,
        proposed_price=100.0,
        current_positions={"XLE": 4000.0},  # existing XLE $4k; proposed $1k → $5k for XLE
        account_value=100_000,
        max_position_pct=0.10,  # $10k per trade allows proposed $1k
        max_open_pct=0.10,      # $10k open cap; existing $4k + proposed $1k = $5k OK
        max_ticker_pct=0.045,    # $4.5k ticker cap; existing $4k + proposed $1k = $5k > $4.5k → ticker fail
    )
    assert not ok
    assert "ticker_concentration" in reason


def test_concentration_per_trade_check_uses_proposed_value_not_qty():
    # Verify the math uses qty × price, not just qty
    ok, reason = check_concentration(
        symbol="A",
        proposed_qty=100,
        proposed_price=0.10,  # $10 total — well under any cap
        current_positions={},
        account_value=100_000,
    )
    assert ok, reason


# Story 1c.5: check_kill_switch


def test_kill_switch_ok_when_no_drawdown():
    ok, reason = check_kill_switch(current_equity=100_000, account_state={"peak_equity": 100_000})
    assert ok
    assert reason == "ok"


def test_kill_switch_ok_when_drawdown_below_threshold():
    # 10% drawdown — below 20% threshold
    ok, reason = check_kill_switch(current_equity=90_000, account_state={"peak_equity": 100_000})
    assert ok
    assert reason == "ok"


def test_kill_switch_trips_at_exactly_threshold():
    # Exactly 20% drawdown — trips (>= comparison)
    ok, reason = check_kill_switch(current_equity=80_000, account_state={"peak_equity": 100_000})
    assert not ok
    assert "kill_switch_drawdown" in reason
    assert "20.00%" in reason


def test_kill_switch_trips_above_threshold():
    # 25% drawdown
    ok, reason = check_kill_switch(current_equity=75_000, account_state={"peak_equity": 100_000})
    assert not ok
    assert "25.00%" in reason
    assert "peak $100,000.00" in reason
    assert "current $75,000.00" in reason


def test_kill_switch_ok_when_peak_missing():
    """Defensive: missing peak_equity (freshly initialized state) returns OK."""
    ok, reason = check_kill_switch(current_equity=100_000, account_state={})
    assert ok
    assert reason == "ok"


def test_kill_switch_custom_threshold():
    # 15% drawdown trips at 10% threshold
    ok, reason = check_kill_switch(
        current_equity=85_000, account_state={"peak_equity": 100_000}, threshold=0.10
    )
    assert not ok
    assert "15.00%" in reason


def test_kill_switch_default_threshold_constant():
    assert KILL_SWITCH_DRAWDOWN_PCT == 0.20


# Story 2.4: check_consecutive_losses


from risk import CONSECUTIVE_LOSS_THRESHOLD, check_consecutive_losses


def _closed(pnl, exit_at="2026-05-15T13:40:00+00:00"):
    return {"status": "closed", "pnl_dollars": pnl, "exit_time_actual": exit_at}


def test_consecutive_losses_ok_when_fewer_than_threshold_records():
    trades = [_closed(-100), _closed(-100), _closed(-100)]  # only 3 closes
    ok, reason = check_consecutive_losses(trades)
    assert ok
    assert reason == "ok"


def test_consecutive_losses_ok_when_recent_winner_in_last_5():
    trades = [
        _closed(-100, "2026-05-01T13:40:00+00:00"),
        _closed(-100, "2026-05-02T13:40:00+00:00"),
        _closed(+200, "2026-05-03T13:40:00+00:00"),  # winner breaks the streak
        _closed(-100, "2026-05-04T13:40:00+00:00"),
        _closed(-100, "2026-05-05T13:40:00+00:00"),
    ]
    ok, reason = check_consecutive_losses(trades)
    assert ok


def test_consecutive_losses_trips_when_last_5_are_all_losses():
    trades = [
        _closed(+50, "2026-05-01T13:40:00+00:00"),
        _closed(-100, "2026-05-02T13:40:00+00:00"),
        _closed(-100, "2026-05-03T13:40:00+00:00"),
        _closed(-100, "2026-05-04T13:40:00+00:00"),
        _closed(-100, "2026-05-05T13:40:00+00:00"),
        _closed(-100, "2026-05-06T13:40:00+00:00"),
    ]
    ok, reason = check_consecutive_losses(trades)
    assert not ok
    assert "kill_switch_consecutive_losses" in reason
    assert "5 losses" in reason
    assert "2026-05-01" in reason  # last winner date


def test_consecutive_losses_ignores_open_records():
    trades = [
        _closed(-100, "2026-05-01T13:40:00+00:00"),
        _closed(-100, "2026-05-02T13:40:00+00:00"),
        _closed(-100, "2026-05-03T13:40:00+00:00"),
        _closed(-100, "2026-05-04T13:40:00+00:00"),
        _closed(-100, "2026-05-05T13:40:00+00:00"),
        {"status": "open", "pnl_dollars": None},  # open record ignored
    ]
    ok, reason = check_consecutive_losses(trades)
    assert not ok


def test_consecutive_losses_orders_by_exit_time():
    """Out-of-order input must still pick the correct last 5 by exit_time_actual."""
    trades = [
        _closed(-100, "2026-05-05T13:40:00+00:00"),
        _closed(+200, "2026-05-01T13:40:00+00:00"),  # earliest, ignored in last-5
        _closed(-100, "2026-05-04T13:40:00+00:00"),
        _closed(-100, "2026-05-02T13:40:00+00:00"),  # 2nd earliest — IS in last 5 if N=5
        _closed(-100, "2026-05-03T13:40:00+00:00"),
        _closed(-100, "2026-05-06T13:40:00+00:00"),
    ]
    # Last 5 sorted by exit_time: 05-02, 05-03, 05-04, 05-05, 05-06 — all -100 → trip
    ok, reason = check_consecutive_losses(trades)
    assert not ok


def test_consecutive_losses_custom_threshold():
    trades = [_closed(-100) for _ in range(3)]
    ok, reason = check_consecutive_losses(trades, threshold=3)
    assert not ok
    ok, reason = check_consecutive_losses(trades, threshold=5)
    assert ok  # only 3 records, threshold 5


def test_consecutive_losses_default_threshold_is_5():
    assert CONSECUTIVE_LOSS_THRESHOLD == 5
