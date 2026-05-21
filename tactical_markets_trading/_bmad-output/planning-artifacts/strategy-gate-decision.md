---
date: 2026-05-20
project: tactical_markets_trading
scope: strategy-efficacy gate for Phase 2 wiring
status: **SUPERSEDED 2026-05-21** by [phase-3-ensemble-design.md](phase-3-ensemble-design.md). See note below.
original_recommendation: Option C (parallel paper variant)
---

> **SUPERSEDED 2026-05-21.** The Option A/B/C/D framing in this doc was about variants of `sector_rotation_5d`. Extended walk-forward (1999-2026, 33 years) plus a 30-combo sensitivity sweep on the trailing-stop leveraged-trend strategy showed:
> 1. `sector_rotation_5d` has CAGR 0.62% / Sharpe 0.19 over 33 years — not salvageable by tuning. Retired as live signal.
> 2. TQQQ trend + 50d MA + 5% trailing stop: walk-forward Sharpe 1.83 OOS (TEST=1.83 vs TRAIN=1.87, 98% retention). Robust, not overfit.
> 3. Regime-routed ensemble: 21% CAGR / Sharpe 1.12 / -28% MaxDD over 24 years.
>
> The actual decision is no longer "which sector-rotation variant" but "build the multi-strategy ensemble per PRD Phase 4+ vision, now with backtest validation." See [phase-3-ensemble-design.md](phase-3-ensemble-design.md) for the new architecture.
>
> This doc remains in the planning-artifacts directory as historical record of the decision frame that led to the research that led to the supersession.

# Strategy-gate decision — pre-Phase-2

## Why this exists

The Phase 1 → Phase 2 gate as written in [TODO.md](../../TODO.md) is "**5+ clean executions, no system errors, positions exit on schedule**." This is an **engineering gate**. It verifies the pipes work. It does **not** verify that the signal has edge.

The Phase 2 → Phase 3 gate is "**50+ trades, win rate vs SPY > 50%**." This is the first time strategy edge is checked — and 50 trades is approximately 6 months of paper trading at current cadence. That's a lot of infrastructure to commit *before* we ask the basic question.

The backtest evidence ([research/data/comparison_summary.csv](../../research/data/comparison_summary.csv)) now forces the question early:

| Strategy | CAGR | Sharpe | Max DD | Notes |
|---|---:|---:|---:|---|
| buy_hold_spy | **13.86%** | 0.84 | -33.72% | baseline |
| trend_following_spy | 10.07% | 0.90 | -19.81% | SPY + 200d MA filter |
| sixty_forty | 9.48% | 0.89 | -27.24% | classic 60/40 |
| **sector_rotation_5d_live** (Phase 1 signal) | **1.68%** | **0.60** | -5.10% | what we're trading |
| btc_stress_overlay | 72.53% | 1.24 | -69.11% | outlier; high vol |

**Headline:** the live signal earns ~12% of SPY's cumulative return over 12.3 years at lower Sharpe than 60/40. The smaller drawdown (-5%) is partly a function of being ~50% deployed by design, not skill.

The first three closed Phase 1 trades reinforce this concern. All three pair-trade reconstructions went the wrong direction:

| # | Trade | XLK return | SPY | Sell-leg | Long-short spread |
|---|---|---:|---:|---:|---:|
| 1 | XLK vs XLE (2026-05-08 to 05-15) | +1.92% | +0.21% | +6.71% | **-4.79%** |
| 2 | XLK vs XLU (2026-05-14 to 05-20) | -2.69% | -0.92% | -0.87% | **-1.82%** |
| 3 | XLK vs XLRE (2026-05-15 to 05-20) | -0.75% | +0.28% | +2.78% | **-3.53%** |
| Σ | | **-1.52%** | **-0.43%** | — | **-10.14%** |

Long-only underperformed SPY by 1.1pp absolute in the same window; the cross-sectional bet is 3-for-3 wrong. n=3 is noise — but combined with the 12.3-year backtest evidence, the signal is sitting in "weak edge or none" territory.

This doc separates the **engineering gate** (already in place) from the **strategy gate** (this decision), and forces an explicit choice before Phase 2 wiring commits more code to the same signal.

---

## Options

### Option A — Proceed with Phase 2 wiring as planned

**What it means:** Accept the backtest. Wire Phase 2 (broker-side stops, MACRO size-down, risk-based sizing, kill switch, reconciler) around the existing 5-day sector-rotation signal. Treat Phase 2 infrastructure as strategy-agnostic — re-pointable at a different signal later.

**Pros:**
- Preserves planning artifacts (PRD, epics, architecture all assume this signal)
- Phase 2 infrastructure (risk caps, MACRO consumer, reconciler) is genuinely strategy-agnostic — it would still apply to any sector ETF strategy
- Doesn't block momentum; we keep building

**Cons:**
- Commits engineering hours (~15 stories in Epics 1a/1b/1c per [epics.md](epics.md)) to scaffolding a signal that the backtest says is weak
- "We can re-point it later" is the kind of optionality that often doesn't get exercised — by the time you'd switch, you've calcified around current behavior
- Phase 2 → Phase 3 gate becomes a stricter test the signal probably won't pass; we'd hit the wall later instead of now

**When to choose this:** if the conviction is that *the pipes are the bottleneck and the signal can be swapped later cheaply*.

### Option B — Switch parameters before Phase 2

**What it means:** Pause Phase 2 wiring. Re-parameterize the MICRO signal in `tactical_markets/` based on the sensitivity sweep ([research/data/sensitivity_summary.md](../../research/data/sensitivity_summary.md)) — best Sharpe combinations cluster around 21-day hold, 3% spread, top-3 max positions. Restart Phase 1 paper-validation on the new params, then resume Phase 2 wiring.

**Pros:**
- Phase 2 wraps better infrastructure around a better-validated signal
- Forces upstream conversation with MICRO project (cross-project asks doc — same pattern as 2026-05-13 distribution)
- Sharpe-optimal sensitivity-sweep params are concrete and defensible

**Cons:**
- Restarts the Phase 1 freeze conceptually — new params, new validation substrate, ~2 weeks of paper trading before Phase 2 can resume
- Requires changes in the MICRO project; coupled timeline
- Sensitivity sweep is *in-sample* (same 12.3-year window as the comparison). The top params might be overfit. Walk-forward validation is the next step we haven't done.

**When to choose this:** if conviction is *the signal is salvageable with the right params, and we should fix that before building more around it*.

### Option C — Parallel paper variant (recommended)

**What it means:** Keep Phase 1 running as-is. Add a **second** scheduled task that runs a sensitivity-best variant on the same MICRO signal feed (e.g., reads `theses.jsonl` differently, holds longer, uses tighter spread filter — or runs against a different MICRO output if MICRO is updated to emit multiple variants). Both variants log to separate `trades.jsonl` files. After ~30 trades (~6 weeks), compare live A/B results and use the data to drive the Phase 2 wiring decision.

Concretely:
- New scheduled task `Tactical Trading Entry Variant B` at 8:36 AM CDT (1 min after primary so they don't race on the same Alpaca API)
- New `run_trading_variant_b.py` (or single `run_trading.py --variant b`) — same pipes, different filter/hold params
- New ledger `data/trades_variant_b.jsonl`
- New backfill / reconciler aware of both ledgers

**Pros:**
- Empirical — generates live A/B data under same market conditions (matches the [[feedback-evaluate-strategies-empirically]] preference)
- Doesn't force the strategy choice before you have evidence
- Doesn't block Phase 2 wiring conceptually — wiring can proceed in parallel because the infrastructure is strategy-agnostic
- Cheap: ~1 day of work to set up; paper money, no real cost

**Cons:**
- Doubles operational surface: two tasks, two ledgers, two sets of benchmarks to backfill
- Twice the failure modes to monitor (Pushover noise doubles)
- 30-trade comparison is still small-n; doesn't replace longer validation, just gives a faster signal than 6 months

**When to choose this:** if conviction is *I want data before I commit, but I don't want to stop development*.

---

## Recommendation

**Option C** + this doc as a permanent strategy-gate artifact. Rationale:

1. **It matches the empirical-not-pedigree principle** Rekwa already established. Backtests are pedigree (in-sample, 12-year-old data); live A/B is evidence.
2. **It doesn't force a freeze.** Phase 2 wiring can proceed in parallel; the wiring is strategy-agnostic by design.
3. **It surfaces the strategy question to a regular review cadence** — every ~30 trades, look at the A/B numbers and decide whether to keep, switch variant, or revisit.
4. **The cost is small.** A second scheduled task and a second ledger file is not a big lift.

The thing that would change my mind: if running two variants simultaneously creates Alpaca rate-limit / position-conflict issues, or if MICRO can't easily emit a second variant of the signal. Both are unknowns until we try.

## Phase 2 → Phase 3 gate change (independent of A/B/C)

Regardless of which option is chosen, the Phase 2 → Phase 3 gate as written ("win rate vs SPY > 50%") should be tightened. A coin-flip hits this 50% of the time. Proposed replacement:

> **Phase 2 → Phase 3:** 50+ paper trades AND (Sharpe ≥ 0.6 on the live ledger OR realized return ≥ 80% of SPY's same-window return). Plus the rules-of-engagement doc.

This is still loose, but at least it can't be cleared by random chance. Better metrics (information ratio, hit rate × avg-win/avg-loss) can come later.

---

## Next actions (post-decision)

If **Option C** is chosen:
1. Write a "bot-integration-asks" doc to `tactical_markets/` requesting a second-variant signal output (e.g., longer-lookback, tighter-spread) emitted alongside the existing `theses.jsonl`
2. Add `run_trading_variant_b.py` and parallel scheduled task in `setup_task.ps1`
3. Set the first A/B review at 30 cumulative trades (live ledger sum across both variants)

If **Option B**:
1. Write bot-integration-asks to MICRO with the sensitivity-sweep params
2. Pause Phase 2 wiring stories until new-params Phase 1 has 5+ clean trades
3. Walk-forward validate the chosen params before live-fire (Phase 1 freeze on signal-switch is justified here)

If **Option A**:
1. Add this doc as the explicit "we know, we're proceeding" record
2. Tighten the Phase 2 → Phase 3 gate (above)
3. Schedule a review at 30 trades to revisit whether the signal evidence has shifted

This doc lives forever in planning-artifacts as the strategy-gate record, independent of which option is chosen.
