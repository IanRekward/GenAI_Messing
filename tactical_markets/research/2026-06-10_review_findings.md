# 2026-06-10 Review — Sector Rotation Signal Findings

**Run:** 2026-06-12 (review was 2 days overdue per TODO.md line 16)
**Author:** Claude Opus 4.8, on Ian's review
**Status:** Findings only. No production code changed. Decision pending Ian sign-off (locked design).

---

## Why this review happened

TODO.md scheduled a 2026-06-10 review: let ~3 weeks of M1 multi-thesis data
accumulate, then decide whether to re-param the signal. (The variant-B 21-day-hold
ask was already CLOSED-CANCELLED on 2026-05-21 when the bot project pivoted away
from sector rotation, so the live question reduced to: **re-param, or leave as-is.**)

## What the signal does

Each morning it ranks 12 ETFs (9 SPDR sectors + IWM/QQQ/SPY) by 5-day return,
then bets **momentum**: buy the 5-day winner, short the 5-day loser, hold 5–7 days,
publish if the top-vs-bottom spread ≥ 1.5% and the buy-leg is above its 20-day MA.
The entire rule rests on one premise: *recent 5-day strength continues over the next 5 days.*

---

## Step 1 — Live data (first ~5 weeks, 2026-05-06 → 2026-06-12)

Deduped to one record per (date, pair); scored each as a market-neutral pair
(long buy-leg, short sell-leg) over the next 5 trading days via yfinance.

| Metric | Value |
|---|---|
| Evaluable trades | 51 |
| Win rate | **27%** |
| Mean pair return (5d) | **−2.97%** |
| Per-trade Sharpe | **−0.66** |
| Worse with bigger spread? | **Yes** — 5%+ spread bucket averaged −3.45% |

The live signal was strongly **anti-predictive**, and *more* confident calls did
*worse*. Worst trade: 2026-05-19 XLE>IWM (spread 9.85%) → −13.4% over 5 days.

**Caveat that drove Step 2:** only 51 trades, mostly the *same pair repeated on
consecutive days* (XLK>XLE ran most of a week), all inside one ~5-week regime.
Effective independent sample ≈ 12–15. Not enough to act on alone.

## Step 2 — 2-year backtest (2024-06-12 → 2026-06-11, 501 trading days)

Replicated the production selection logic exactly (same greedy top-vs-bottom
pairing, 1.5% spread gate, 20d MA filter on the buy-leg) and measured forward
5-day pair returns under both directions. Reversion is the exact mirror of
momentum (same selected pairs, legs swapped).

Script: [`backtest_momentum_vs_reversion.py`](backtest_momentum_vs_reversion.py)

### Top pair per day (what actually gets read on the phone)
| Direction | n | Win | Mean/trade | Sharpe/trade | Cumulative |
|---|---|---|---|---|---|
| **Momentum** (as built) | 462 | 46% | **−0.28%** | −0.07 | **−129%** |
| **Reversion** (flip) | 462 | 54% | +0.28% | +0.07 | +129% |

### Top pair, non-overlapping (step = 5d, ~independent samples)
| Direction | n | Win | Mean/trade | Sharpe/trade | Cumulative |
|---|---|---|---|---|---|
| **Momentum** | 93 | 44% | **−0.50%** | −0.13 | −47% |
| **Reversion** | 93 | 56% | +0.50% | +0.13 | +47% |

### All emitted pairs (multi-thesis days, n inflated/correlated)
| Direction | n | Win | Mean/trade | Sharpe/trade |
|---|---|---|---|---|
| Momentum | 1444 | 48% | −0.03% | −0.01 |
| Reversion | 1444 | 52% | +0.03% | +0.01 |

---

## What this means

1. **The sign is wrong, and it's not a fluke.** Momentum loses across *every* cut
   — overlapping, non-overlapping, and all-pairs. Reversion (buy the 5d loser,
   short the 5d winner) is positive in every cut. The live 5 weeks were directionally
   correct about the problem; they just caught an unusually strong reversion regime
   that exaggerated the magnitude.

2. **But the edge is small.** Reversion's per-trade Sharpe is ~+0.13 (non-overlapping),
   ~+0.5% mean per 5-day trade — and that is **gross of costs**. Long-short on sector
   ETFs with bid/ask + slippage twice a week would eat a meaningful slice. This is
   nowhere near the published 0.92-Sharpe hypothesis the project treats as a starting point.

3. **The "fix" is literally a sign flip.** Because reversion is the same selected pairs
   with legs swapped, switching the signal from momentum to mean-reversion is a
   small, contained change to which leg is labelled buy vs sell (plus rethinking the
   20d MA "trend-confirmed" filter, which is a momentum-confirmation device that
   doesn't map onto a reversion thesis).

## Recommendation

This lands on **TODO.md failure mode (b): "feels like noise" → fix sector rotation
before adding anything.** Concretely:

- **Do not add VIX slope / new signals (mode a).** The core signal hasn't earned expansion.
- **Do not reinstate variant-B.** Already cancelled; momentum-at-5d is the problem, not hold length.
- **Momentum as-built is mildly value-destructive** — that alone justifies not trading it live.
- **Reversion is the better hypothesis but is a weak standalone edge.** Before flipping
  the production rule, worth deciding whether a ~0.13 Sharpe gross signal clears the bar
  to keep publishing at all, or whether reversion needs a stronger filter (e.g. only
  fade *extreme* short-term moves, add an overbought/oversold gate) to be worth a phone alert.

## Follow-up — can a regime-adaptive switch beat a static flip?

Ian's question: momentum is wrong *now* but maybe not *always* — instead of a static
sign flip, detect which regime we're in and trade that direction. Tested the simplest
honest version: at each entry, trade whichever direction the trailing-K *realized*
trades favored (causal — only uses outcomes already known at entry).

Script: [`backtest_adaptive_switch.py`](backtest_adaptive_switch.py)

| Strategy (top pair, daily) | n | Win | Mean/trade | Sharpe/trade | Cumulative |
|---|---|---|---|---|---|
| Momentum (static) | 463 | 46% | −0.28% | −0.07 | −129% |
| Reversion (static flip) | 463 | 54% | +0.28% | +0.07 | +129% |
| Adaptive K=5 | 454 | 51% | −0.02% | −0.01 | −10% |
| Adaptive K=10 | 449 | 55% | +0.18% | +0.05 | +80% |
| Adaptive K=20 | 439 | 55% | **+0.33%** | **+0.09** | +143% |
| Adaptive K=40 | 419 | 49% | −0.17% | −0.04 | −70% |
| Oracle (always right) | 463 | 100% | +2.93% | +1.17 | — |

**Verdict: not convincingly.** K=20 edges out static reversion (+0.33% vs +0.28%
per trade), but K=5 and K=40 both *lose* money — the result is exquisitely sensitive
to the lookback, which is the signature of parameter luck, not a robust regime detector.

The diagnostic looks encouraging on its face (lag-1 autocorrelation +0.60, 70%
sign-persistence) but is **mostly a mechanical artifact**: consecutive daily entries
with 5-day holds share 4 of 5 days of price action, so adjacent trade returns are
correlated by construction. The non-overlapping evidence (Step 2: reversion wins
56% of independent 5-day windows) remains the cleanest read, and it favors a static
flip over a switch.

If adaptive were pursued anyway, it would also double the parameter surface
(direction + lookback K) on a signal whose base edge is already marginal — the
opposite of the project's rule-based-heuristic constraint.

## Open decision for Ian (locked design — requires sign-off)

- **(A)** Flip the production rule momentum → reversion (sign change + revisit MA filter), keep collecting under the new direction.
- **(B)** Flip *and* add a stronger gate (only fade extreme moves) before re-publishing.
- **(C)** Treat the edge as too weak to publish as a trade; keep running for awareness only, no directional claim.
- **(D)** Keep collecting unchanged for more out-of-sample data before any change.

## Reproduction

```powershell
python research/backtest_momentum_vs_reversion.py
python research/backtest_adaptive_switch.py
```
Data via yfinance (`2y`, auto_adjust). Numbers will drift slightly as the window rolls forward.
