# Market Dashboard — To-Do / Project Plan

## Current status (2026-04-23)

Phases 1–5 complete. Live automation and mobile access complete. Architectural
review for Phase 6+ complete and documented in [ROADMAP.md](ROADMAP.md).

**IMMEDIATE ACTION REQUIRED — see [ROADMAP.md §CRITICAL PRE-WORK](ROADMAP.md).**
`config/weights.yaml` silently reverted to the pre-recalibration 9-bucket
version. Restore from `weights.yaml.bak` before running any further scheduled
work.

## Phase 6+ — pick up from here

For detailed implementation briefs see [ROADMAP.md](ROADMAP.md). Recommended
execution order with priority in parentheses. Check off as Sonnet completes
each.

- [x] **Step 0** — Restore 10-bucket weights.yaml from .bak *(done 2026-04-23)*
- [x] **Brief 2** — Minimum viable test suite *(done 2026-04-23 — 22 tests, 0.24s)*
- [ ] **Brief 1** — Config schema validation + data-driven registry *(high, half day)*
- [ ] **Brief 4A** — Historical events overlay on trend chart *(1 hour UX win)*
- [ ] **Brief 3** — Rate-of-change signal layer *(high, half day)*
- [ ] **Brief 6** — Data staleness alerts *(high, half day)*
- [ ] **Brief 4B** — Indicator drill-down detail pages *(med-high, half day)*
- [ ] **Brief 5** — Correlation-breakdown signal *(high, half day)*
- [ ] Brief 7 — Retry + circuit-breaker in fetch layer
- [ ] Brief 8 — Deescalation alerts + weekly digest
- [ ] Brief 9 — News-to-trigger cross-reference
- [ ] Brief 10 — Regime-aware weighting *(large)*
- [ ] Brief 11 — Audit log for alerts
- [ ] Brief 12 — Provenance stamp on each run
- [ ] Brief 13 — History pruning/archival
- [ ] **Brief 14** — Dashboard tooltips: plain-English explanations of every indicator, bucket, band, and composite score *(last on list)*

## Sonnet onboarding instructions

When starting work on any Brief:

1. **Always** read [ROADMAP.md §CRITICAL PRE-WORK](ROADMAP.md) first. If Step 0
   hasn't been done and you see evidence of the 9-vs-10 bucket drift, do that
   before your brief.
2. Read the full brief in ROADMAP.md — each is self-contained with problem,
   design decision, file list, edge cases, and success criteria.
3. Check the "Dependencies" line of the brief. If it depends on a prior
   brief, verify that brief's success criteria are met before starting.
4. After completing a brief, run the test suite (Brief 2) if it exists, then
   manually verify the success criteria listed in the brief.
5. Update this checklist and commit with a message referencing the brief
   number.

## Completed

### Infrastructure
- [x] Build all 8 source modules (`fetch`, `indicators`, `scoring`, `triggers`, `history`, `alerts`, `news`, `dashboard`)
- [x] Config files (`weights.yaml`, `thresholds.yaml`)
- [x] Push to GitHub (IanRekward/GenAI_Messing → `market_dashboard/`)
- [x] Configure all API keys (FRED, EIA, Anthropic, Pushover)
- [x] Test Pushover alerts

### Automation & access
- [x] Windows taskbar shortcut / launcher (`launch_dashboard.lnk`)
- [x] Mobile access via GitHub Pages (`--publish` flag, auto-push to /docs)
- [x] Windows Task Scheduler daily run at 7:30 AM
- [x] Wake-on-RTC at 7:25 AM (5 min pre-run)
- [x] 31-day heartbeat Pushover confirmations

### Alerts
- [x] Contextual Haiku-generated alert interpretation
- [x] Buy/hold suggestions in alert context (defensive alternatives)

### Backtesting framework (see BACKTEST_DESIGN.md)
- [x] **Phase 1** — Point-in-time backtest engine (`src/backtest.py`)
- [x] **Phase 2** — Evaluation metrics (`src/evaluation.py`)
- [x] **Phase 3** — Backtest report generator (`src/backtest_report.py`)
- [x] **Phase 4** — Live performance tracking (rolling IC + degradation on dashboard)
- [x] **Phase 5** — Recalibration pipeline (`src/recalibrate.py`) *(applied, but weights.yaml reverted — see Step 0)*

### Model additions
- [x] Global Spillover bucket (10th bucket: USD index, Euro HY OAS, EM Corp OAS, EEM vol) *(code complete, config reverted — see Step 0)*

### Design decisions / documentation
- [x] Backtesting design spec — complete, see [BACKTEST_DESIGN.md](BACKTEST_DESIGN.md)
- [x] Architectural review & Phase 6+ roadmap — complete, see [ROADMAP.md](ROADMAP.md)
