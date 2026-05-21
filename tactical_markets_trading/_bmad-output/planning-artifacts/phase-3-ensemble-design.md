---
title: Phase 3 Ensemble Architecture — Design Document
date: 2026-05-21
status: draft (pending Rekwa review)
supersedes:
  - strategy-gate-decision.md (the Option A/B/C/D framing was about sector-rotation variants; this design replaces it)
informed_by:
  - research/data/strategy_research_consolidated_2026-05-21.md (33-year multi-strategy backtest)
  - research/data/trailing_stop_walk_forward_report.md (98% Sharpe retention on TRAIN -> TEST split)
  - research/data/extended_report.md (every strategy on max-window data)
---

# Phase 3 Design: Multi-Strategy Regime-Routed Ensemble

## Why this design exists

Phase 2 shipped a complete bot infrastructure but live-traded a strategy (`sector_rotation_5d`) whose 33-year backtest now confirms it does not work (CAGR 0.62%, Sharpe 0.19). Phase 3 had been defined as "live capital with same signal." That framing is wrong. The strategy must change; Phase 3 needs to be re-scoped around the actual strategic direction implied by recent research.

## What the research found

Three strategies that beat SPY (10.81% CAGR, Sharpe 0.65, MaxDD -55%) durably over 24-33 years:

| Strategy | Window | CAGR | Sharpe | MaxDD | Notes |
|---|---|---:|---:|---:|---|
| TQQQ trend + 5% trailing stop (50d MA) | 1999-2026 synth | **~42%** | **1.83** | **-21%** | Walk-forward confirmed (TEST=1.83 vs TRAIN=1.87) |
| sector_momentum_top3_monthly | 1999-2026 | 9.17% | 0.57 | -46% | Cross-sectional sector rotation (NOT the 5d variant) |
| sixty_forty (SPY+TLT) | 2002-2026 | 9.05% | 0.84 | -30% | Classic asset allocation |

Three-component regime-routed ensemble across same 24-year window: **21% CAGR / Sharpe 1.12 / MaxDD -28%.**

## Core design principle: ensemble, not pivot

The natural reaction to the walk-forward finding ("42% CAGR, Sharpe 1.83") is to pivot the whole bot to TQQQ trend. **Don't.** Single-strategy concentration carries strategy-specific risk that hits hard during regime changes. The reliable-chug-away ambition (the original project goal) is *only* satisfied with diversified components. The PRD's Phase 4+ vision (multi-strategy ensemble with regime routing) is the right shape; the research validates that it works historically; Phase 3 is the implementation.

Apply 15% haircut to backtest CAGRs for realistic expectations. The 42% becomes ~36%; the 21% ensemble becomes ~18%. Still meaningful, still beats SPY.

---

## Architecture

### Component strategies

Three production strategies, each independent, each with its own entry/exit logic and its own ledger:

**1. trend_leveraged_tqqq (the conviction strategy)**
- Signal: SPY > 50-day moving average (yesterday's close)
- Position: TQQQ at allocated notional, whole-share floor (Alpaca rejects fractional GTC stops)
- Software-managed 5% trailing stop on TQQQ closing price
- Re-entry only after both (a) trend signal still on AND (b) TQQQ above prior in-position peak
- Expected behavior: in TQQQ ~70% of days, in cash ~30%, ~15-30 entries/exits per year

**2. sector_momentum_top3_monthly (the diversifier)**
- Signal: every month-end, rank 9 sector SPDRs by 3-month return; hold top-3 equal-weighted
- Position: 1/3 notional in each of top-3 sectors
- Hold: until next month-end rebalance
- Expected behavior: ~12 rebalance events per year, partial portfolio churn each time

**3. trend_following_spy_200d (the steady contributor)**
- Signal: SPY > 200-day moving average
- Position: SPY at allocated notional
- No stop (the 200d MA is the exit)
- Expected behavior: in SPY ~75% of days, in cash ~25%, ~2-4 entries/exits per year

### Regime router

Daily decision (yesterday's close determines today's allocation):

| Condition | Active components | Allocation |
|---|---|---|
| SPY > 200d MA AND VIX < 25 (bull/calm — ~70% of days) | TQQQ trend + sector monthly + SPY trend | weighted (see below) |
| SPY > 200d MA AND VIX ≥ 25 (bull/elevated — ~6% of days) | sector monthly + 60/40 | 50/50 |
| SPY < 200d MA (bear — ~25% of days) | Cash (BIL_EXTENDED) | 100% |

### Allocation within bull/calm regime

Equal-weight (33/33/33) across the three components — the equal-weight ensemble achieved the highest Sharpe (1.17) in the historical test. Risk-parity weighting under-allocates to the highest-return component (leveraged trend) and gave Sharpe 0.86. Equal-weight wins because each component is itself risk-managed (trend gates, trailing stop, asset diversification within sector_monthly).

### Capital allocation

| Component | % of account |
|---|---:|
| trend_leveraged_tqqq | 33% (max) |
| sector_momentum_top3_monthly | 33% |
| trend_following_spy_200d | 33% |
| Cash buffer | 1% |

Each component manages its own positions within its 33% allocation. The 5% per-trade and 25% per-ticker concentration caps from existing `risk.check_concentration` apply, but with a denominator of "component's allocated notional" not "total account."

---

## Code structure

### Module layout

```
src/
  strategies/                    # NEW directory
    __init__.py
    base.py                      # Strategy ABC with run_daily() interface
    leveraged_trend.py           # trend_leveraged_tqqq
    sector_momentum_monthly.py   # sector_momentum_top3_monthly
    spy_trend.py                 # trend_following_spy_200d
  regime_router.py               # NEW: regime detection + component activation
  ensemble_orchestrator.py       # NEW: the new top-level entry path
  # all existing Phase 2 modules unchanged
```

### Trade record schema additions

Add `strategy` field to every trade in `trades.jsonl`:
```json
{
  "trade_id": "...",
  "strategy": "trend_leveraged_tqqq",  // NEW: required for ensemble accounting
  "regime_at_entry": "bull_calm",       // NEW: which regime triggered the entry
  ...everything else the same
}
```

Backward compat: existing records without `strategy` field default to `"sector_rotation_5d_legacy"` for graduation counts.

### Reconciler changes

Per-strategy reconciliation: drift events now include which strategy "owns" the position. An orphan TQQQ position with no matching `trend_leveraged_tqqq` open record is orphan; a TQQQ position matching a `trend_leveraged_tqqq` record is correctly tracked.

### Preflight changes

Add per-strategy preflight checks:
- For `trend_leveraged_tqqq`: requires SPY 50-day MA computable (≥50 days of SPY history). Always true in production.
- For `sector_momentum_top3_monthly`: requires all 9 sector ETFs have ≥3-month price history. Always true.
- For `trend_following_spy_200d`: requires SPY 200d MA computable. Always true.

The aggregate preflight passes if ALL active components pass; if one component fails, the others continue (degraded operation).

---

## Migration plan from current Phase 2

### Phase 3.0 — design + paper validation (this doc)
- [x] Walk-forward sensitivity validates the trailing-stop strategy is robust
- [x] Retire `sector_rotation_5d` as the live signal (`SECTOR_ROTATION_5D_RETIRED = True` flag in `run_trading.py`)
- [ ] Rekwa reviews this design doc
- [ ] If approved: proceed to Phase 3.1

### Phase 3.1 — first component (trend_leveraged_tqqq) on paper
- Build `src/strategies/leveraged_trend.py` with the 50d MA + 5% trailing stop logic
- Build minimal `ensemble_orchestrator.py` (only handles one component initially)
- Update Windows Scheduled Task to invoke the new orchestrator
- Run on paper for 4 weeks minimum
- Expected: 1-3 entries, 1-3 exits over that window
- Success criterion: every entry has a stop active, every exit closes cleanly, reconciler stays at 0 drift

### Phase 3.2 — add sector_momentum_monthly + trend_following_spy
- Both are simpler than the leveraged trend strategy
- Add the regime router (full 3-component switching)
- Continue on paper

### Phase 3.3 — live capital
- This is the "go live" decision per the PRD locked rule: 50+ paper trades + rules-of-engagement doc + Rekwa explicit sign-off + `paper=True → paper=False` flip
- The 50-trade graduation gate works naturally with the new strategy mix (more frequent rebalances than sector_rotation_5d would have produced)

---

## Risks + caveats

### Strategy-specific risks

**trend_leveraged_tqqq:**
- Tighter 50d MA = more whipsaw than 200d. More entries/exits = more slippage in real trading.
- 5% trailing stop = stops out more often than 10%. Same trade-off.
- Synthetic 3× QQQ data pre-2010 overstated returns by ~16% vs real TQQQ. Apply haircut.
- Software-managed stop means the bot must run daily. Multi-day outage during a crash = unhedged.
- TQQQ has 0.95% expense ratio (already in the synthetic). Real tracking error and fund flows add ~0.2-0.5% drag not modeled.

**sector_momentum_top3_monthly:**
- 3-month lookback can be a lagging indicator at regime changes (got crushed in March 2020).
- Top-3 of 9 means concentrated to one sector type if 3 correlated sectors dominate.
- Monthly rebalance means significant tax events in taxable accounts.

**trend_following_spy_200d:**
- 200d MA is slow — gives back significant gains before exit signal fires.
- Whipsaw losses during choppy markets (e.g., 2011, 2015-16, late 2018).
- This is mostly a "low Sharpe but stable" contributor; useful as ensemble member, weak on its own.

### Architectural risks

**Multi-strategy complexity:**
- Per-component reconciliation is more state to track. Drift detection becomes more nuanced.
- The regime router introduces a new failure mode: regime classification could be wrong/lagging.
- Capital allocation across strategies needs rebalancing logic — when one component drifts significantly above its 33% target, do we rebalance to constraint, or let it run?

**Operational risks:**
- The current Windows Scheduled Task infrastructure has had missed fires (2026-05-14 and 2026-05-20 — see TODO.md). The new strategy is MORE dependent on daily execution. Need to fix the scheduler reliability problem before relying on software-managed stops.
- Phase 3 ramps the bot from "one decision per day" to "potentially multiple per-strategy decisions per day during rebalance events." Code paths get more complex.

### Decision risks

- The 33-year backtest includes 3 major bears (dot-com, GFC, 2022 bear) but doesn't include a prolonged Japan-style 10+ year flat market. All trend strategies would underperform indefinitely in that regime.
- Past performance ≠ future. The ensemble was best historically; that doesn't guarantee future best.
- The 200d MA + VIX 25 thresholds for regime routing are hand-picked. Should be sensitivity-tested.

---

## Open questions for Rekwa — RESOLVED 2026-05-21

### 1. Capital allocation: equal 33/33/33 (DECIDED)

Use equal-weight 33/33/33 in Phase 3.x paper testing. Rationale: it had the best Sharpe in backtest (1.17), it's the simplest default that lets us measure what each component contributes, and "it's all paper for now anyway" so the operator's risk preference between risk-weighted and equal-weighted doesn't yet bind. If paper results show one component dominating the variance budget, revisit at Phase 3.3 (pre-live).

### 2. MICRO retired from automation; MACRO promoted to regime safety layer (DECIDED)

**MICRO:**
- The new ensemble does not read `theses.jsonl`. Sector-rotation signals are dead-end.
- Retire MICRO's role in the trading pipeline.
- KEEP MICRO running as personal-awareness tool — its daily Pushover notifications stay, the operator continues to read them on phone for sector-spread context.
- No code change in MICRO project. Just a clear "we don't trade on this anymore" note.

**MACRO:**
- Promote MACRO from "ignored" to "regime safety layer." The base regime router uses SPY 200d MA + VIX 25 (price-based). MACRO is a richer stress signal that can catch things SPY's 200d MA misses (e.g., credit-spread widening before equity reflects it). Layer it on:

**Updated regime router logic:**

```
IF MACRO red regime (per macro_consumer.validate() + size_multiplier() returning 0.0)
   → bear regime (all in cash, regardless of SPY 200d MA)
ELSE IF SPY < 200d MA
   → bear regime
ELSE IF MACRO orange + high regime (size_multiplier returning 0.5)
   OR VIX >= 25
   → bull/elevated regime (60/40 + sector_monthly only, no leveraged trend)
ELSE
   → bull/calm regime (all 3 components active, 33/33/33)
```

This makes MACRO a "veto" signal that can de-risk even when price-based signals say bull. Doesn't replace SPY 200d MA; supplements it.

**Important**: MACRO must be FRESH for this veto to apply. Use the existing `macro_consumer.validate()` rules — stale MACRO (>4h) degrades to neutral (no veto). Broken MACRO blocks all trading via preflight (existing behavior).

### 3. Phase 3 graduation gate: revisit (DECIDED — replaced)

The "50 trades" gate was sized for sector_rotation_5d cadence (~2-4 trades/week). New ensemble produces ~120-180 trades/year aggregate (40-60 per component). 50 trades = ~3 months which is too fast to validate execution reliability across regimes.

**Replacement graduation criterion (Phase 3.x → 3.3 live capital):**

The gate now has three independent pass conditions, ALL of which must be met:

1. **Time**: minimum 6 months of paper-trading the full 3-component ensemble (covers at least one regime transition in most years)
2. **Per-component minimums**: at least 30 closed trades per ACTIVE component, AND at least 1 stop-fired exit on `trend_leveraged_tqqq`, AND at least 1 MACRO-veto-triggered defensive period
3. **Operational cleanliness**: zero unresolved drift events for the prior 30 days, zero preflight ABORT events for the prior 30 days, zero stranded positions ever

Rationale for the change: the old gate was about COUNT. The new gate is about VALIDATION. We need diverse market behavior (the 6-month time floor), evidence each strategy works (per-component minimums), and evidence the operational layer is reliable (cleanliness).

### 4. Live capital target: defer (DECIDED)

Rekwa: "not even close at this point." Confirmed.

Implication: PDT and concentration cap math don't need to be re-derived for Phase 3.0/3.1/3.2 (all paper at $100k). Phase 3.3 design defers this question until the new gate is hit. Reasonable working assumption when we get there: $25k-$100k live (below PDT-disable threshold means we need PDT-aware code; above means we don't). Phase 3.3 spec will pin this down.

### 5. Close variant-B ask to MICRO (DECIDED — actioned today)

The variant-B ask doc (filed 2026-05-20 to request 21-day-hold MICRO signal output) is now moot. The bot pivot away from sector rotation entirely makes the ask irrelevant.

Closing action:
- Update `../tactical_markets/_bmad-output/planning-artifacts/bot-integration-asks-variant-b-2026-05-20.md` to CLOSED-CANCELLED with the pivot explanation
- Update MICRO's `TODO.md` line to reflect the closure
- Write a brief note to MICRO project owner explaining the pivot

---

## What this design does NOT include

- **Live execution code yet.** This doc is design only. Implementation = Phase 3.1.
- **Tier 2 single stocks** (PRD Phase 4+). The ensemble starts with sector ETFs + SPY/TQQQ only.
- **Tier 3 crypto** (PRD Phase 4+). Backtest showed BTC strategies have high CAGR but unacceptable volatility/correlation profile. Defer.
- **Machine-learning strategy selection.** Regime router is deterministic rules. ML routing is Phase 5+.
- **Real-time intraday signals.** All decisions are end-of-day or open-only. Intraday is Phase 4+.

---

## Acceptance criteria for this design doc

The design is approved (and Phase 3.1 can begin) when Rekwa has:
1. Reviewed the three strategies' mechanics
2. Confirmed equal-weight allocation (or specified alternative)
3. Decided what to do with MICRO/MACRO project status
4. Set a target live-capital amount
5. Signed off on the migration plan from Phase 2 → 3.0 → 3.1 → 3.2 → 3.3
