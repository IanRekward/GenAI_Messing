# Market Dashboard — To-Do / Project Plan

## Pending

- [x] **Backtesting design spec** — complete, see [BACKTEST_DESIGN.md](BACKTEST_DESIGN.md). All decisions locked in by Opus 4.7 session on 2026-04-23.

- [ ] **Backtesting Phase 1 — Point-in-time engine** (implement with Sonnet)
  Build `src/backtest.py` per [BACKTEST_DESIGN.md §9](BACKTEST_DESIGN.md#9-implementation-plan).
  - Reuse `fetch.py` to pull all historical series (including new non-U.S. indicators)
  - Implement `point_in_time_percentile()` and `point_in_time_zscore()` using 10-year rolling window — NOT full series. This is the critical fix.
  - Generate historical composite score time series for every backtest date
  - Output: DataFrame with date, composite, bucket scores, all indicator raw values
  - Two runs produced: 2018+ (full model) and 2000–2017 (subset model per Q5 decision)

- [ ] **Backtesting Phase 2 — Evaluation module** (implement with Sonnet)
  Build `src/evaluation.py` per [BACKTEST_DESIGN.md §4, §7](BACKTEST_DESIGN.md#4-statistical-approach).
  - Metrics: Spearman IC (primary), Pearson, ROC-AUC, PR-AUC, precision, recall, F1, F0.5
  - EW-IC with 5yr half-life + equal-weighted variant (report both per Q2 decision)
  - Block bootstrap 95% CIs (not i.i.d. bootstrap)
  - Benchmark comparisons: VIX alone, HY OAS alone, NFCI, STLFSI, yield curve, 3-factor equal-weighted
  - Regime stratification by VIX terciles
  - Per-year IC stability check

- [ ] **Backtesting Phase 3 — Report generator** (implement with Sonnet)
  Build `src/backtest_report.py` → `output/backtest_report.html`.
  - Headline metrics table, per-indicator IC ranking, ROC curves, regime tables, event case studies
  - See [BACKTEST_DESIGN.md §7](BACKTEST_DESIGN.md#7-evaluation-outputs) for full output spec

- [ ] **Backtesting Phase 4 — Live performance tracking** (implement with Sonnet)
  - Extend `history.csv` schema per [BACKTEST_DESIGN.md §8a](BACKTEST_DESIGN.md#8-live-performance-tracking--measuring-going-forward)
  - Add "Model Performance" section to `src/dashboard.py`
  - Rolling IC + degradation alerts per Q3 decision (two-tier threshold)

- [ ] **Backtesting Phase 5 — Recalibration** (implement with Sonnet)
  - Apply 2×2 matrix from Q4 decision to all indicators
  - Update weights.yaml with empirically-justified weights
  - Document each weight change in config comments with backtest date + IC rationale

- [ ] **Add Global Spillover bucket to model** (implement with Sonnet, precedes Phase 1)
  Add new 10th bucket to `config/weights.yaml` per [BACKTEST_DESIGN.md §11 Q1](BACKTEST_DESIGN.md#q1--non-us-markets).
  - New FRED fetches: `DTWEXBGS`, `BAMLHE00EHYIOAS`, `BAMLEMCBPIOAS`
  - New yfinance fetch: `EEM` + realized vol series
  - Rebalance existing bucket weights per table in design doc
  - Add corresponding thresholds to `config/thresholds.yaml`
  - Update `src/scoring.py` indicator router with 4 new entries

- [ ] **Project optimization, documentation & feature roadmap**
  Use Opus 4.7 to: review current architecture for improvements, write thorough
  documentation, and generate a prioritized feature enhancement roadmap.

- [ ] **Contextual interpretation in Pushover notifications**
  Current alerts are terse and cryptic (e.g. "NEW RED TRIGGERS (1): Oil 1M Realized Vol"),
  which requires opening the dashboard to understand. Enrich alerts with a one-or-two
  sentence interpretation so the notification itself is actionable.
  Example of desired output:
    > "Oil 1M Realized Vol hit red (62.3%, above 60% threshold). Indicates sudden
    >  volatility in energy markets — historically correlated with geopolitical events
    >  or supply shocks. Check news bucket for context."
  Two possible implementations:
    1. Static lookup table — one short "meaning" string per indicator, defined in config
    2. Dynamic — use Claude Haiku to generate a contextual sentence from the current
       indicator state + recent headlines (costs ~$0.001/alert)
  Option 2 is richer but adds latency and dependency on Anthropic API being up during alerts.
  Decide during design phase.

- [ ] **Windows taskbar shortcut / launcher**
  One-click launcher that can be pinned to the Windows taskbar. Clicking it should:
    1. Run `python run_dashboard.py` to refresh with latest data
    2. Open the generated `output/dashboard.html` in the default browser
  Needs a custom icon (ideally something stress-gauge themed) so it's visually
  distinct on the taskbar. Likely implementation: a `.bat` or PowerShell script
  with an `.ico` file, wrapped as a shortcut (`.lnk`). Consider whether refresh
  should be silent (no console window flash) vs showing progress.

- [ ] **Mobile access for dashboard**
  Enable viewing the full HTML dashboard from phone, not just Pushover alerts.
  Leading option: auto-publish `output/dashboard.html` to GitHub Pages after each run.
  See conversation notes — Options 2 (local server) and 3 (hosting) discussed.

## Completed

- [x] Build all 8 source modules (`fetch`, `indicators`, `scoring`, `triggers`, `history`, `alerts`, `news`, `dashboard`)
- [x] Config files (`weights.yaml`, `thresholds.yaml`)
- [x] Push to GitHub (IanRekward/GenAI_Messing → `market_dashboard/`)
- [x] Configure all API keys (FRED, EIA, Anthropic, Pushover)
- [x] Test Pushover alerts
