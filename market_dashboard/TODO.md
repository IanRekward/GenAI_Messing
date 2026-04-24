# Market Dashboard — To-Do / Project Plan

## Current status (2026-04-24)

**Project is in production and substantially feature-complete.** Daily
automation runs at 7:30 AM. 181/181 tests passing. 11 buckets, 26 indicators,
two composite scores (10yr + 3yr), Pushover alerts, GitHub Pages publication.

### Shipped feature set

- **Core scoring:** 11 buckets, percentile + band scoring, `composite` + `composite_short`
- **Signal layers:** rate-of-change momentum (Brief 3), shock-type classification,
  regime-adjusted composite, cross-bucket correlation breakdown (Brief 5)
- **Resilience:** retry/backoff on fetch (Brief 7), staleness detection (Brief 6),
  audit log (Brief 11), provenance stamps (Brief 12), history pruning (Brief 13)
- **Config robustness:** schema validation + data-driven registry (Brief 1),
  pre-commit config hook, test suite (Brief 2)
- **Alerts:** escalation, rapid-rise, correlation-sustained, staleness, weekly
  digest, Haiku-generated interpretation
- **Dashboard:** event overlay on trend chart (Brief 4A), escalation-scenarios
  card, historical analog finder, per-band review prompts, economic calendar,
  cross-bucket correlation card, AI narrative paragraph, tooltip CSS infrastructure,
  news→trigger keyword matching (Brief 9)

See the bottom "Completed" block for the older-history milestone list.

---

## Sonnet's next execution queue

Ordered top-down by value × (1/effort), respecting dependencies. Sonnet should
execute in order. Design-first items marked 🅾️ — route through Opus before
Sonnet starts.

### Phase A — Verify & clean (30–60 min)

- [ ] **Verification sweep** — run `python run_dashboard.py --no-alerts --quiet` end-to-end. Open the generated `dashboard.html`. Confirm the shipped feature list above actually renders / fires correctly (event overlay on trend chart, correlation card, staleness handling, weekly digest, audit log writes to `data/alert_log.jsonl`, provenance columns in `data/history.csv`). If any gap is real, open a dedicated TODO under Phase C.
- [ ] **Delete `config/weights.yaml.bak`** — Brief 1 shipped and pre-commit hook prevents drift. Git is the backup. Per ROADMAP §pre-feature refactor item 3.

### Phase B — Dashboard UX (1–2 days of high-leverage polish)

Grouped into batches so the same HTML / config file is only touched once per batch.

- [ ] **UX Batch A — Layout & explainer captions** *(1–2 hrs, pure HTML)*
  Single pass through `src/dashboard.py`. Consolidates 6 items:
  1. Add explainer sentence to REVIEW PROMPTS card (mirror ESCALATION SCENARIOS format).
  2. Side-by-side layout: REVIEW PROMPTS + ESCALATION SCENARIOS cards adjacent.
  3. Cross-bucket correlation card: 1–2 sentence plain-English caption under the number.
  4. 90-Day Composite Trend: add subtitle explaining what's shown + band meanings + "today is on the right".
  5. Macro calendar: per-event "→ cpi_yoy (Inflation Pressure)" badge when the event drives a model indicator; "not in model" otherwise.
  6. Move the "new brief" / orientation highlight below the two action cards — composite score leads the page.

- [ ] **UX Batch B — Weight display & bar chart** *(3–4 hrs)*
  All touches bucket/indicator rendering; single refactor pass. Pull all numbers from `config/weights.yaml` — never hardcode.
  1. Bucket header shows "X% of composite".
  2. Each indicator row shows "X% of bucket · Y% of composite" (composite share = bucket_weight × indicator_weight).
  3. Small horizontal bar chart under each bucket title visualizing indicator weights (compact, no axes).

- [ ] **Brief 4B — Indicator drill-down pages** *(half day)*
  Per-indicator inline `<details>` block with 10yr chart + stats (min/max/median/percentile/current). See [ROADMAP.md §Brief 4B](ROADMAP.md). Pre-req for UX Batch C.

- [ ] **UX Batch C — Full tooltip coverage** *(half day)*
  Consolidates UX item 9 + Brief 14. Builds on Brief 4B + existing `config/tooltips.yaml`.
  1. Plain-English tooltip on every indicator row: what it measures, what high/low means, why it matters.
  2. Tooltips on composite, bucket labels, band labels, regime terms.
  3. All copy lives in `config/tooltips.yaml`. Extend schema if needed.

### Phase C — Remaining brief work

- [ ] **Brief 8 (second half) — Deescalation alerts** *(1–2 hrs)*
  Mirror of escalation alert: fire Pushover when composite band improves (red→orange, orange→yellow, yellow→green). Debounce using same buffer pattern as escalation. Update `data/alert_state.json` schema if needed. See [ROADMAP.md §Brief 8 sketch](ROADMAP.md).

### Phase D — Design-first (route through Opus before Sonnet executes) 🅾️

- [ ] 🅾️ **VIX term-structure evaluation** — design decision needed. Is VIX9D/VIX1D slope a valuable short-term vol signal beyond raw VIX? Where does it live — equity_volatility or rates_curve? yfinance ticker availability (^VIX9D appears to exist; ^VIX1D may not). Opus recommendation → Sonnet implements.

- [ ] 🅾️ **Backtest history visualization** — design decision needed. Main-dashboard card or separate page? Metrics (hit rate, lead time, false-positive rate, SPX drawdown overlay)? Time range? Uses existing `src/backtest.py` + `src/evaluation.py` + `src/backtest_report.py`. Design pass → Sonnet implements.

- [ ] 🅾️ **Brief 10 — Regime-aware weighting (LARGE)** *(multi-day)*
  Two weight sets by VIX tercile (low/mid/high), precomputed during backtest, applied at score time. Touches scoring, backtest, recalibrate. Opus should design the API + migration (how do we handle the weight-set switch in the composite calculation, how does it interact with Brief 3 momentum, how does history.csv represent which regime was active) before Sonnet executes.

- [ ] 🅾️ **Paywalled news sources** *(user scope call + ToS review)*
  Which of WSJ / FT / Bloomberg does Ian actually want? What's the minimum-viable integration (RSS where allowed, archive links, nothing questionable)? Legal / ToS review required before any scraping. Not a Sonnet task until Ian picks the feeds.

---

## Sonnet onboarding instructions

When starting work on any Brief:

1. Read [CLAUDE.md](CLAUDE.md) first — two-repo workflow, technical gotchas,
   working agreement, locked scope decisions.
2. `cd /c/Users/rekwa/ian_projects/_genai_tmp && git log --oneline -10` to catch up.
3. Read the full brief in [ROADMAP.md](ROADMAP.md) if it references one.
4. Run `python -m pytest tests/ -q` before making any edits. Must be 181+ green.
5. Mark the item done here after the brief's success criteria verify. Commit
   with a message referencing the brief or batch name.

---

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
- [x] Wake-on-RTC at 7:20 AM (5 min pre-run)
- [x] 31-day heartbeat Pushover confirmations

### Alerts
- [x] Contextual Haiku-generated alert interpretation
- [x] Buy/hold suggestions in alert context (defensive alternatives)
- [x] Rapid-rise alert (Brief 3)
- [x] Correlation-sustained alert (Brief 5)
- [x] Staleness alert (Brief 6)
- [x] Weekly digest (Brief 8 — first half)
- [x] Audit log to `data/alert_log.jsonl` (Brief 11)

### Model additions
- [x] Global Spillover bucket (10th bucket)
- [x] Breadth_flow bucket (11th bucket — sector breadth + SPX 200d MA)
- [x] Treasury auction stress indicator
- [x] Shock-type classification (temporal + source)
- [x] Regime-adjusted composite (partial implementation of Brief 10)
- [x] Historical analog finder
- [x] Escalation scenarios / pre-mortem card
- [x] Per-band review prompts
- [x] Economic calendar display
- [x] AI daily narrative paragraph

### Resilience & config
- [x] **Step 0** — Restore 10-bucket weights.yaml *(2026-04-23)*
- [x] **Brief 1** — Config schema validation + data-driven registry *(2026-04-24)*
- [x] **Brief 2** — Minimum viable test suite *(2026-04-23)*
- [x] **Brief 3** — Rate-of-change signal layer *(2026-04-24)*
- [x] **Brief 4A** — Historical events overlay on trend chart
- [x] **Brief 5** — Correlation-breakdown signal
- [x] **Brief 6** — Data staleness alerts
- [x] **Brief 7** — Retry + circuit-breaker in fetch layer
- [x] **Brief 8 (first half)** — Weekly digest
- [x] **Brief 9** — News-to-trigger cross-reference
- [x] **Brief 11** — Audit log for alerts
- [x] **Brief 12** — Provenance stamp on each run
- [x] **Brief 13** — History pruning / archival to parquet
- [x] Pre-commit hook for config validation

### Backtesting framework (see BACKTEST_DESIGN.md)
- [x] **Phase 1** — Point-in-time backtest engine (`src/backtest.py`)
- [x] **Phase 2** — Evaluation metrics (`src/evaluation.py`)
- [x] **Phase 3** — Backtest report generator (`src/backtest_report.py`)
- [x] **Phase 4** — Live performance tracking (rolling IC + degradation on dashboard)
- [x] **Phase 5** — Recalibration pipeline (`src/recalibrate.py`)

### Design decisions / documentation
- [x] Backtesting design spec — [BACKTEST_DESIGN.md](BACKTEST_DESIGN.md)
- [x] Architectural review & Phase 6+ roadmap — [ROADMAP.md](ROADMAP.md)
- [x] Cross-model working agreement — [CLAUDE.md](CLAUDE.md)

---

## Mid-task handoff — 2026-04-24, Opus → Sonnet

**Context:** Opus did a full-repo audit and rewrote this file into an execution
queue. Many briefs turned out to be already shipped; they've been moved into the
Completed block above. Ian has now switched to `/model sonnet` to execute Phase A
and Phase B.

**Start here:**

1. Phase A → **Verification sweep** (first unchecked item).
   - Run `python run_dashboard.py --no-alerts --quiet` from the primary dir.
   - Open the generated `dashboard.html` and confirm each Phase A target actually
     renders/fires: event overlay on the 90-day trend chart (Brief 4A), correlation
     card (Brief 5), staleness rendering when a series is old (Brief 6), audit-log
     writes to `data/alert_log.jsonl` (Brief 11), `weights_hash`/`code_sha` columns
     in `data/history.csv` (Brief 12), pruning behavior (Brief 13, rows beyond 2yr
     archived to `history_archive.parquet`).
   - If any item is silently NOT wired up, open a dedicated TODO under Phase C
     ("Brief X — fix gap found during verification") and tell Ian which ones
     slipped through. Don't re-order the queue without surfacing it.
2. Phase A → **Delete `config/weights.yaml.bak`**. Brief 1 + pre-commit hook make
   it obsolete. Commit separately with a message noting Step 0 is fully closed.
3. Phase B → **UX Batch A** (layout + captions, 1–2 hrs). Single pass through
   `src/dashboard.py`. Six self-contained edits listed in the batch.
4. Continue down Phase B (Batch B → Brief 4B → Batch C) as time allows.

**Gotchas Opus hit during the audit (save yourself the same trip):**
- The co-author trailer in commits should match the running model — use
  `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` while Sonnet is
  driving.
- Pre-commit hook validates the `_genai_tmp/` copy of `weights.yaml`, not the
  primary dir copy. If UX Batch A touches any config, sync to `_genai_tmp` first.
- `tooltips.yaml` already exists and is consumed by the dashboard — UX Batch C
  should extend it, not create a parallel file.

**Flag and switch back to Opus if:**
- A "shipped" brief turns out to have a real gap beyond a trivial fix.
- A UX item has a real design ambiguity (not a style preference — an actual
  "should this be one card or two" question).
- You hit Phase D and Ian hasn't explicitly picked one of the design-first items
  to open.

**Delete this section** when Phase A + Phase B are done. Leave a fresh handoff
note if you end mid-phase.
