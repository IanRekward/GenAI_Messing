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
- [x] **Brief 1** — Config schema validation + data-driven registry *(done 2026-04-24 — 177 tests passing)*
- [ ] **VIX term-structure evaluation** — investigate VIX9D (9-day) and VIX1D (1-day) relative to VIX (30-day) as a short-term volatility signal. Assess whether term-structure slope (VIX9D/VIX or VIX1D/VIX) adds signal beyond raw VIX in detecting fast shocks. Decide: add to equity_volatility bucket, rates_curve, or skip? Consider ticker availability on yfinance. *(med, design decision required before adding)*
- [ ] **Brief 4A** — Historical events overlay on trend chart *(1 hour UX win)*
- [x] **Brief 3** — Rate-of-change signal layer *(done 2026-04-24 — 181 tests passing)*
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
- [ ] **Paywalled news sources** — add WSJ, FT, Bloomberg headline feeds; investigate bypass options (RSS where available, archive links, scrapers with ToS review). Goal: richer news context on triggered indicators without manual effort. *(complexity: medium, legal/ToS review required first)*
- [ ] **Backtest history visualization** — plan and build a view that replays the composite stress score through history alongside what the market actually did (e.g. SPX drawdown, forward returns). Should answer: did high stress scores precede market stress? What were the false positives? Leverage existing src/backtest.py + src/evaluation.py + src/backtest_report.py. Needs design pass before implementation — decide on time range, chart format, key metrics to surface (hit rate, lead time, false positive rate), and whether this lives on the main dashboard or a separate page. *(complexity: medium-large, design-first)*
- [ ] **Brief 14** — Dashboard tooltips: plain-English explanations of every indicator, bucket, band, and composite score *(last on list)*

## Dashboard UX & readability improvements

These are polish items that can be worked as a batch or individually — all are self-contained in `src/dashboard.py` / `config/`.

- [ ] **Review Prompts explainer** — Add a short header sentence to the REVIEW PROMPTS card explaining what it is (same pattern as the ESCALATION SCENARIOS card). E.g. "These questions help you stress-test your interpretation of the current reading."
- [ ] **Side-by-side layout: Review Prompts + Escalation Scenarios** — Move the two cards to sit adjacent on the dashboard so thematically related "what to do next" content is grouped together.
- [ ] **Cross-bucket correlation plain-English caption** — Under the correlation card title, add 1–2 sentences explaining what the number means: what "crisis synchronous" looks like vs. normal, and why elevated correlation matters (buckets moving together = fewer diversified buffers against a single shock).
- [ ] **90-Day Composite Trend description** — Add a subtitle or caption sentence under the chart heading that explains what the viewer is looking at: the composite stress score over the past 90 days, what the bands mean, and that today's value is on the right.
- [ ] **Macro calendar: model-linkage badge** — For each event in the Upcoming Macro Events card, show whether that event type drives a model indicator, and if so which one(s). E.g. "CPI release → cpi_yoy (Inflation Pressure bucket)". Events not covered by the model get a "not in model" note.
- [ ] **Indicator and bucket weight display** — In every bucket section, show (a) the bucket's weight as a share of the composite (e.g. "13% of composite"), and (b) each indicator's weight within its bucket (e.g. "VIX — 65% of Equity Volatility"). Pull from weights.yaml so it's always accurate.
- [ ] **Weight bar chart under each bucket** — Add a small horizontal stacked-bar or proportional bar chart visually representing the indicator weights within each bucket, so the relative emphasis is scannable without reading numbers. Keep it compact (thin bar, no axes).
- [ ] **Move "new brief" highlight** — Relocate the highlighted new-entry/orientation card so it sits below the ESCALATION SCENARIOS and REVIEW PROMPTS cards rather than at the top of the page. The top of the page should lead with the composite score.
- [ ] **Indicator tooltips (plain English)** — Add a tooltip to every indicator row in the indicator section. Each tooltip should explain in layman's terms: what the indicator measures, what a high/low reading means in plain English, and why it matters for detecting market stress. Source the copy from a config file (e.g. `config/indicator_descriptions.yaml`) so it can be updated without touching Python. Note: Brief 14 covers band/composite/bucket tooltips — this item covers per-indicator tooltips specifically on the indicator table rows.
- [ ] **Indicator relative weights display** — In the indicator section rows, show each indicator's weight within its bucket alongside the raw value. E.g. "VIX  |  42.3  |  65% of bucket  |  8.5% of composite". The composite share = bucket_weight × indicator_weight. Pull directly from weights.yaml so it's always in sync with the model.

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
