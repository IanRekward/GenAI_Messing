# Backtesting & Performance Evaluation — Design Spec

**Status:** Draft · 2026-04-23
**Author:** Claude Opus 4.7 + user
**Purpose:** Define how we evaluate whether the composite stress score actually predicts market stress — historically and in live use going forward.

---

## 1. What We're Actually Measuring

The core question: **does an elevated composite stress score precede actual market stress?**

A score that moves when the market moves is useless — that's a mirror. A score that moves *before* the market moves is a signal. We need to distinguish the two.

Three signal variants to evaluate separately:

| Signal | What it is | Evaluated as |
|---|---|---|
| **Composite score** | Continuous 0–100 | Continuous regression vs. forward outcomes |
| **Composite band** | Discrete green/yellow/orange/red | Classifier vs. binary stress events |
| **Trigger counts** | Count of red/orange indicators | Count regression vs. stress severity |

Plus a breakout analysis for **each bucket** and **each indicator** individually — to answer "which parts of the model are pulling weight?"

---

## 2. Defining "Market Stress" — The Target

There is no single canonical definition. We use three targets and report against all three.

### Primary target: S&P 500 drawdown
**Metric:** Maximum drawdown of ^GSPC over next N days from the signal date
**Why:** Most interpretable to non-specialists. If a user asks "did the model warn me before losses?" this is the answer.

### Secondary target: HY credit spread widening
**Metric:** Change in FRED BAMLH0A0HYM2 over next N days
**Why:** Credit often leads equity in stress regimes. A model that catches credit stress first is more valuable than one that's only coincident with equity.

### Tertiary target: Composite realized stress index
**Metric:** Equal-weighted z-score of forward (VIX, HY OAS, NFCI), averaged over next N days
**Why:** A multi-asset realized stress measure. Captures stress events that don't hit the S&P 500 as hard (e.g. 2015 HY blowup didn't drop SPX much).

**Binary stress events** (for classifier evaluation) derived from targets:
- **MAJOR:** S&P drawdown > 10% in next 90 days
- **MODERATE:** S&P drawdown > 5% in next 30 days
- **CREDIT:** HY OAS widens > 150bps in next 60 days

---

## 3. Prediction Horizons

Different indicators work at different lead times. Evaluate at all four:

| Horizon | Relevance |
|---|---|
| **1 day** | Coincident check. If signal only "predicts" at T+1, it's probably a mirror of current vol. |
| **1 week** | Short-term tactical. VIX spikes and funding stress should register here. |
| **1 month** | Medium-term — where credit spreads and NFCI shine. |
| **3 months** | Equity drawdown horizon — most retail-relevant. |
| **6 months** | Long lead time — tests yield-curve and inflation indicators specifically. |

Report every statistic at every horizon. Expect different indicators to win at different horizons — that's informative, not a problem.

---

## 4. Statistical Approach

### 4a. Continuous signal → continuous target
(e.g. composite score → next-30d max drawdown)

| Statistic | What it tells us |
|---|---|
| **Spearman rank correlation** (primary) | Robust to non-linearity. "Does the rank of the signal predict the rank of the outcome?" |
| **Pearson correlation** | Reported for context; can mislead under fat tails. |
| **Information Coefficient (IC)** | Spearman between signal and forward return — quant industry standard. |
| **Regression R²** | How much variance the signal explains. |

Report 95% bootstrap confidence intervals on all correlations. A correlation of 0.15 ± 0.20 is noise; 0.15 ± 0.03 is real.

### 4b. Discrete signal → binary target
(e.g. band in {green,yellow,orange,red} → "was there a major drawdown?")

| Statistic | What it tells us |
|---|---|
| **Precision** | When we say RED, how often was there actually a drawdown? High = low false alarms. |
| **Recall** | How many drawdowns were actually flagged RED? High = few missed events. |
| **F1 score** | Harmonic mean of P&R — balances the two. |
| **Confusion matrix** | The full picture, per band. |

Always report P&R together. Precision alone is gamed by never signaling; recall alone is gamed by always signaling.

### 4c. Continuous signal → binary target
(e.g. composite score → major drawdown event)

| Statistic | What it tells us |
|---|---|
| **ROC-AUC** | Threshold-agnostic discriminatory power. 0.5 = coin flip, 1.0 = perfect. |
| **Precision-Recall AUC** | Better than ROC for imbalanced classes (crises are rare). Report this. |
| **Lift at top decile** | If we take the top 10% of signals, what's the crisis rate vs. base rate? |

### 4d. Robustness checks (non-negotiable)

- **Out-of-sample split.** Train window (2000–2015), test window (2016–present). Report test-set performance separately.
- **Expanding-window walk-forward.** Retrain the model logic at each point using only prior data. Hardest to game.
- **Regime stratification.** Partition into calm/stress regimes via VIX terciles. Does the model work in both?
- **Per-year IC.** Show IC for each calendar year separately. A model that has 0.3 IC averaged over 20 years but randomly alternates ±0.6 is not stable.
- **Block bootstrap** (not standard bootstrap) — to preserve time-series autocorrelation.

---

## 5. Market Benchmarks — What We Must Beat

No standalone statistic is meaningful. Every metric is compared to baselines.

| Tier | Benchmark | Purpose |
|---|---|---|
| **Trivial** | Always-green / always-red | Floor. If we lose to these we're anti-informative. |
| **Trivial** | Random signal | Coin flip baseline. |
| **Single-indicator** | **VIX alone** | The most important comparison. If composite doesn't beat VIX, the 9 buckets aren't earning their cost. |
| **Single-indicator** | HY OAS alone | Credit-side canonical signal. |
| **Single-indicator** | NFCI (Chicago Fed) | Official Fed financial stress measure — published and peer-reviewed. |
| **Single-indicator** | Yield curve (10Y–2Y) | The Fed's favored recession indicator. |
| **Combination** | Equal-weighted z-score (VIX + HY OAS + 10Y–2Y) | 3-factor naive model. Tests whether our careful 9-bucket weighting adds value over simple combination. |
| **Published** | STLFSI (St. Louis Fed FSI) | Another peer-reviewed multi-indicator composite. |

**The key test:** in out-of-sample data, does the composite beat (a) VIX alone and (b) the 3-factor equal-weighted baseline? If yes, the model earns its complexity. If no, we simplify.

---

## 6. Avoiding Lookahead Bias — Critical

The current code computes percentiles and z-scores using the **full** series including the latest value. That's fine for live use. For backtesting it's a fatal flaw: on 2015-01-01 we'd be saying "VIX is at the 75th percentile" using information from 2016–2025.

**Required change for backtesting:** at each historical date T, compute percentile/z-score using only data from T − HISTORY_YEARS to T.

Three window options:

| Option | Behavior | Recommendation |
|---|---|---|
| **Expanding window** | Use all data up to T | Easy but early dates unreliable; unfair comparison across time. |
| **Fixed 10-year rolling** | Use exactly last 10 years from T | **Recommended** — matches live behavior (HISTORY_YEARS=10). |
| **Fixed 20-year rolling** | Use last 20 years from T | More stable but ignores regime changes. |

Use 10-year rolling. It's the apples-to-apples comparison with what a live user sees.

---

## 7. Evaluation Outputs

Every backtest run produces:

### 7a. Headline metrics table

| Target | Horizon | Composite IC | VIX IC | 3-factor IC | Composite P-value |
|---|---|---|---|---|---|
| SPX drawdown | 1 week | TBD | TBD | TBD | TBD |
| SPX drawdown | 1 month | ... | ... | ... | ... |
| SPX drawdown | 3 months | ... | ... | ... | ... |
| HY widening | 1 month | ... | ... | ... | ... |
| Stress index | 1 month | ... | ... | ... | ... |

### 7b. Per-indicator IC ranking
Full table of all 18 indicators, ranked by IC vs. primary target. Flag indicators with:
- IC < 0.05 — candidates for weight reduction or removal
- IC unstable year-to-year — candidates for re-examination

### 7c. ROC curves
Composite vs. VIX vs. 3-factor, overlaid, for each binary target.

### 7d. Regime table

| Regime | N obs | Composite IC | VIX IC |
|---|---|---|---|
| Calm (VIX bottom tercile) | ... | ... | ... |
| Normal (middle tercile) | ... | ... | ... |
| Stress (top tercile) | ... | ... | ... |

### 7e. Event case studies
For each major historical event (2008 GFC, 2011 EU crisis, 2015 China/HY, 2018 Q4, 2020 COVID, 2022 inflation, 2023 SVB), report:
- Lead time before event (in days) when composite entered orange
- Lead time before event when composite entered red
- Peak composite score during event
- Which buckets drove the score

---

## 8. Live Performance Tracking — Measuring Going Forward

Backtesting tells us how the model would have worked historically. Live tracking tells us if it still works.

### 8a. Log extended state each run
Currently `history.csv` logs composite + bucket scores + trigger counts. Extend to also log:
- SPX close (^GSPC)
- VIX close
- HY OAS
- Individual indicator raw values (not just bucket scores)

This gives us a point-in-time record needed to compute forward outcomes later.

### 8b. Rolling performance scorecard
On each run, compute over the last 90/180/365 days of history.csv:
- **Rolling Spearman IC** of composite vs. realized SPX 30-day forward max drawdown
- **Rolling precision** of red-band predictions
- **Rolling hit rate** — fraction of red signals followed by any ≥3% SPX drawdown within 30 days

### 8c. Dashboard integration
Add a "Model Performance" section to [src/dashboard.py](src/dashboard.py):
- Rolling 180-day IC (current value + historical trace)
- Hit rate vs. base rate comparison
- Degradation alert: if rolling IC drops below 0.1 or falls by >50% vs. backtest, flag it

### 8d. Regime-change detection
Use CUSUM or Page-Hinkley statistic on rolling IC. Fire a dashboard notice when the model's apparent skill has statistically significantly degraded — e.g. regime change, data source broken, or genuine alpha decay.

---

## 9. Implementation Plan

### Phase 1 — Core backtest engine
**File:** `src/backtest.py`
- Reuses `fetch.py` to pull all historical series in one go
- New `point_in_time_score()` function that computes the composite for every historical date using only data available at that date
- Generates a "historical composite score" time series as a parallel pandas DataFrame
- Outputs: historical score series + raw indicator history

### Phase 2 — Evaluation module
**File:** `src/evaluation.py`
- Takes: historical signal series + historical target series
- Returns: the full metrics table (Section 7)
- Implements IC, ROC-AUC, precision/recall, bootstrap CIs, regime stratification
- Comparison methods for benchmark signals (VIX alone, 3-factor, etc.)

### Phase 3 — Backtest report generator
**File:** `src/backtest_report.py`
- Produces `output/backtest_report.html`
- Full visual report with all tables, curves, and event case studies
- Self-contained — can be shared or archived after each calibration run

### Phase 4 — Live tracker
**Modifications to `src/history.py`:** extend log schema (Section 8a)
**Modifications to `src/dashboard.py`:** add Model Performance card (Section 8c)

### Phase 5 — Recalibration loop
After first backtest:
- Review per-indicator IC — drop/reduce anything consistently below 0.05
- Adjust bucket weights if one bucket dominates or underperforms
- Re-run backtest on the adjusted model
- Document weight changes in `config/weights.yaml` comments with backtest date and rationale

---

## 10. Decisions Already Made (Driven)

Where the user asked me to drive, these are the choices:

| Decision | Choice | Why |
|---|---|---|
| Primary correlation metric | Spearman IC | Robust to non-linearity and fat tails. |
| Target #1 | SPX max drawdown, forward | Most interpretable. |
| Target #2 | HY OAS widening, forward | Credit leads equity in most regimes. |
| Target #3 | Multi-asset realized stress index | Catches stress that doesn't hit SPX. |
| Binary "major event" threshold | SPX drawdown > 10% in 90d | Matches common definition of "correction". |
| Window for point-in-time stats | 10-year rolling | Matches live HISTORY_YEARS setting. |
| Train/test split | Pre-2016 / post-2016 | Large enough training set; test set covers 2018 Q4, COVID, 2022, 2023 SVB. |
| Benchmark to beat (primary) | VIX alone | If we can't beat VIX, the 9 buckets aren't earning complexity. |
| Bootstrap method | Block bootstrap (not i.i.d.) | Time-series data is autocorrelated. |
| Report format | HTML (`backtest_report.html`) | Matches rest of project; can be archived per run. |

---

## 11. Open Questions — Resolved

All open questions resolved in 2026-04-23 design session. Decisions below.

### Q1 — Non-U.S. markets

**Decision: INCLUDE in v1.** User explicitly cited significant spillover events (2011 EU sovereign crisis, 2015 China/EM, 2022 UK gilt, 2023 China property) that were invisible to U.S.-only indicators.

**New bucket added: "Global Spillover & Cross-Border Risk" (weight 0.08):**

| Indicator | Source | Weight in bucket | Rationale |
|---|---|---|---|
| Broad Dollar Index | FRED `DTWEXBGS` | 0.30 | Purest transmission signal — strong dollar = EM debt stress |
| Euro HY OAS | FRED `BAMLHE00EHYIOAS` | 0.25 | EU credit regime |
| EM Corporate OAS | FRED `BAMLEMCBPIOAS` | 0.25 | EM debt regime |
| EM Equity 1M Realized Vol | yfinance `EEM` | 0.20 | EM equity panic (sometimes leads credit) |

**Flagged risk:** Euro HY may be >0.7 correlated with U.S. HY. Backtest will verify each non-U.S. indicator adds information; any correlation > 0.7 with its U.S. counterpart flagged as redundant and re-weighted.

**Weight rebalance (bucket totals sum to 1.0):**

| Bucket | Old | New |
|---|---|---|
| equity_volatility | 0.18 | 0.15 |
| credit_spreads | 0.20 | 0.17 |
| rates_curve | 0.13 | 0.12 |
| financial_conditions | 0.14 | 0.13 |
| inflation | 0.09 | 0.09 |
| funding_liquidity | 0.08 | 0.08 |
| commodities | 0.07 | 0.07 |
| economic_momentum | 0.07 | 0.07 |
| sentiment | 0.04 | 0.04 |
| global_spillover (new) | — | 0.08 |

### Q2 — EW-IC vs equal-weighted

**Decision: EW-IC with 5-year half-life as primary; equal-weighted as robustness check.** Report both; investigate any divergence > 20%.

### Q3 — Degradation threshold

**Decision: Two-tier with persistence requirement.**
- **Warning (yellow):** Rolling 90-day IC drops >40% from backtest baseline OR falls below 0.15.
- **Alert (red):** Rolling 90-day IC drops >60% from baseline AND stays below 0.05 for 60+ consecutive days.

**v2 upgrade note:** upgrade to confidence-interval-based thresholds (Warning if rolling 95% CI no longer overlaps backtest CI; Alert if rolling upper bound drops below zero). Requires more tracked data before we have enough points for meaningful CIs.

### Q4 — Weak-indicator handling

**Decision: 2×2 matrix based on historical and recent IC:**

| Historical IC (pre-2016) | Recent IC (post-2016) | Action |
|---|---|---|
| Strong (≥ 0.10) | Strong | Keep at current weight |
| Strong | Weak | Reduce to 0.25× (regime change, may recover) |
| Weak | Strong | Keep at current weight (new signal emerging) |
| Weak | Weak | Drop entirely |

**v2 upgrade note:** make thresholds (0.10 for "strong," 0.25× for weight reduction) configurable via backtest output rather than hardcoded, so we can tune sensitivity as more data accumulates.

### Q5 — Minimum data availability

**Decision: Option C — split backtest.**
- **Full-model backtest:** 2018–present (all indicators including SOFR, plus new global_spillover bucket indicators where available)
- **Subset-model backtest:** 2000–2017 (reliable long-history indicators only)
- Report both separately, clearly labeled.

Rationale: gives us 25+ years of history for the reliable subset *and* full-model evaluation for 7+ years with all indicators.

### Q6 — Trading vs. alerting framework

**Decision: Alerting/awareness tool.** User is an investor (not a trader) making portfolio allocation decisions rather than intraday trades.

**Implications for evaluation:**
- **No transaction costs, slippage, or latency modeling.**
- **Precision and recall both matter** — false alarms waste cognitive load; missed events mean unpreparedness.
- Report F1 (balanced) as the primary classifier metric. Also report F0.5 (precision-weighted) since an investor might reasonably prefer fewer false alarms. User chooses emphasis based on preference.
- ROC-AUC reported for threshold-agnostic comparison.

### Q7 — Raw vs. smoothed score

**Decision: Evaluate both.**
- **Raw daily score** for reactivity metrics (IC, ROC-AUC)
- **5-day smoothed score** for band-classification metrics (precision/recall)

Rationale: smoothed is truer to how a user actually consumes the dashboard (no one checks 5 times a day). Raw is truer to how predictive power accumulates day by day.

---

## 12. Success Criteria

This project is a success if, at the end of Phase 5, we can confidently state:

> "The 9-bucket composite score has a statistically-significant out-of-sample Spearman IC of X against forward SPX drawdowns, which is [higher/lower/similar] to the VIX-alone baseline of Y. It meaningfully led the [specific events] with a lead time of [N days]. Live performance over the past [K months] shows IC of [Z] — consistent with / degraded from backtest expectations."

If we can't defensibly produce that statement, the model isn't ready for daily use as a decision aid.
