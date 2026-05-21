---
title: Bot Integration Ask — Variant-B signal output for A/B testing (Option C of bot's strategy gate)
audience: tactical_markets (MICRO) project owner
generated: 2026-05-20
status: **CLOSED-CANCELLED 2026-05-21.** The bot project pivoted strategic direction away from sector-rotation entirely. This ask is no longer relevant. See pivot note: [pivot-note-from-bot-2026-05-21.md](pivot-note-from-bot-2026-05-21.md). No MICRO action requested or expected.
source: ../../tactical_markets_trading/_bmad-output/planning-artifacts/strategy-gate-decision.md
superseded_by: ../../tactical_markets_trading/_bmad-output/planning-artifacts/phase-3-ensemble-design.md
---

> **2026-05-21 CLOSED:** The bot has pivoted from sector-rotation execution to a leveraged-trend + multi-strategy ensemble (Phase 3 design). The new strategies do not consume MICRO signal output. This variant-B ask is therefore obsolete and is being closed without action. See [pivot-note-from-bot-2026-05-21.md](pivot-note-from-bot-2026-05-21.md) for context. MICRO project continues independently — its Pushover notifications remain useful to Rekwa as personal-awareness tool.

# Bot Integration Ask: Variant-B Signal Output

This is a single, scoped ask. The bot has chosen **Option C** of its strategy-gate decision (parallel paper A/B variant). To execute Option C, MICRO needs to emit a second variant of its signal alongside the existing `theses.jsonl`.

---

## Context

The bot at `tactical_markets_trading/` has 3 closed trades on the current signal as of 2026-05-20:

| # | Trade | Long-only return | SPY | Sell-leg | Implied pair spread |
|---|---|---:|---:|---:|---:|
| 1 | XLK vs XLE | +1.92% | +0.21% | +6.71% | -4.79% |
| 2 | XLK vs XLU | -2.69% | -0.92% | -0.87% | -1.82% |
| 3 | XLK vs XLRE | -0.75% | +0.28% | +2.78% | -3.53% |
| Σ | | **-1.52%** | **-0.43%** | — | **-10.14%** |

3-for-3 on the pair-trade going the wrong direction. Combined with the bot's 12.3-year backtest showing the current 5-day rotation strategy at **1.7% CAGR vs SPY's 13.9%** (in [strategy-gate-decision.md](../../../tactical_markets_trading/_bmad-output/planning-artifacts/strategy-gate-decision.md) and [comparison_summary.csv](../../../tactical_markets_trading/research/data/comparison_summary.csv)), there's a strong "the parameters may be the problem" hypothesis.

The bot's sensitivity sweep ([sensitivity_summary.md](../../../tactical_markets_trading/research/data/sensitivity_summary.md)) identified higher-Sharpe parameter combinations clustered around:
- **Momentum lookback:** 21 days (vs current 5)
- **Spread threshold:** 3% (vs current 1.5%)
- **Hold window:** 21 days (vs current 5, currently lowered to 2 in Phase 1)
- **Max positions:** 3 (vs current 5)

n=3 live trades is noise. The 12-year backtest is in-sample (same window as sensitivity sweep). The way to disambiguate "the signal is weak" from "the params are wrong" is **a live A/B comparison**, not more theorizing.

---

## The ask

**Emit a second variant of the signal as `data/theses_variant_b.jsonl`** alongside the existing `data/theses.jsonl`.

Same schema, same cadence (daily ~6:30 AM ET), same downstream contract — just computed with the sensitivity-best parameters above:

| Parameter | `theses.jsonl` (current "variant A") | `theses_variant_b.jsonl` (new) |
|---|---|---|
| Momentum lookback | 5 trading days | **21 trading days** |
| Spread threshold | 1.5% | **3.0%** |
| MA filter window | 20 days | 20 days (unchanged) |
| Universe | 12 sector ETFs + IWM/QQQ/SPY | Same |
| Schema | current | identical to current |

The bot will:
- Run a second scheduled task `Tactical Trading Entry Variant B` that reads `theses_variant_b.jsonl`
- Log to a separate ledger `data/trades_variant_b.jsonl`
- Use the same Phase 1 mechanics (long-only, $10k fixed, 2-day NYSE hold) so the only variable being tested is the signal
- Report A/B comparison metrics after ~30 cumulative trades (~6 weeks at current cadence)

Position-sizing differences in the params table (top-3 vs top-5) are bot-side, not MICRO-side — MICRO doesn't need to change anything about max-positions. If MICRO's current emission is "best pair" rather than "top-N pairs," that's preserved for both variants.

---

## Why this isn't M1 (multi-thesis) from the prior ask doc

The prior [bot-integration-asks.md](./bot-integration-asks.md) M1 asked for **top-N pairs** in a single output. That's still desired — it solves the "5 stacked XLK positions" problem.

This ask is **orthogonal**: same single-best-pair output as today, but with different lookback/spread parameters. If MICRO ships M1 first, this ask becomes "emit two N-thesis files with different params"; the bot side handles either shape.

---

## Implementation note for MICRO

The bot is happy to consume whatever shape MICRO finds easiest:
- **Option 1:** Two separate `theses*.jsonl` files (what this ask describes).
- **Option 2:** One `theses.jsonl` file with a `variant` field per record; bot filters client-side.
- **Option 3:** One file with both signals encoded per record (e.g., `signal_a`, `signal_b` parallel fields).

Option 1 is the least invasive on the bot side (no schema change for the bot's existing read path). Option 2 changes the bot's read logic but is cleaner long-term. Option 3 doubles record size and complicates schema versioning. The bot will adapt to whichever MICRO ships.

---

## Non-blocking nature

If MICRO declines or defers this ask, the bot has fallback paths:
- **Fallback 1:** Bot-internal A/B by sub-sampling the existing thesis stream with different filters (degenerate — both variants see the same input). Defeats the purpose.
- **Fallback 2:** Bot reads MICRO's raw momentum data and computes its own variant-B signal client-side. Crosses the "no cross-project imports" line via raw-data file. Technically possible but introduces drift risk.
- **Fallback 3:** Switch to Option B (replace current params with sensitivity-best params, no A/B). Restarts Phase 1 freeze on new params. Slower learning.

The ask above is the cleanest path. If MICRO ships it within ~2 weeks, the bot's A/B comparison can run starting then with full data parity.

---

## Decision request from MICRO

1. **Is this ask in scope** for MICRO's current sprint / planning horizon?
2. **Which output shape** (option 1/2/3 above) is preferred from MICRO's side?
3. **Rough timeline** — if not "this sprint," when?

Reply via the existing `micro-response-to-bot-asks.md` pattern.
