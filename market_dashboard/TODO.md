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

- [x] **Verification sweep** — all shipped briefs confirmed rendering: event overlay, correlation card, staleness, audit log, provenance (weights_hash populated; code_sha empty as expected — primary dir has no git). Pruning archive absent but OK (25 rows, < 2yr). No gaps found.
- [x] **Delete `config/weights.yaml.bak`** — done (was never in git; only existed in primary dir).

### Phase B — Dashboard UX (1–2 days of high-leverage polish)

Grouped into batches so the same HTML / config file is only touched once per batch.

- [x] **UX Batch A — Layout & explainer captions** *(commit cfe6101)*
  All 6 items shipped: explainer on REVIEW PROMPTS, side-by-side action cards, correlation caption, trend subtitle + band key, calendar indicator badges, composite leads page with narrative moved below action cards.

- [x] **UX Batch B — Weight display & bar chart** *(commit da9ba03)*
  All 3 items shipped: bucket header shows "X% of composite", each indicator row shows "X% of bucket · Y% of composite", compact 5px flex bar chart under each bucket title. All weights pulled live from weights.yaml.

- [x] **Brief 4B — Indicator drill-down pages** *(already shipped — src/indicator_detail.py)*
  Per-indicator `<details>` block with 10yr SVG chart + stats (min/max/median/percentile/current/last-obs). Wired into dashboard.py, links from indicator labels in bucket table.

- [x] **UX Batch C — Full tooltip coverage** *(effectively shipped + regime_adjusted added)*
  All 26 indicators, 11 buckets, composite, bands, correlation, shock_type, regime_window all have tooltips in config/tooltips.yaml and are rendered. Added regime_adjusted key (was referenced in code but missing from YAML).

### Phase C — Remaining brief work

- [x] **Brief 8 (second half) — Deescalation alerts** — already shipped
  Section 1b in `send_alerts()` fires `composite_improvement` alert with same debounce buffer when band order drops. Tested in `tests/test_alert_controls.py` (de-escalation tests at lines 68–72).

### Phase D — Design-first (route through Opus before Sonnet executes) 🅾️

- [ ] 🅾️ **VIX term-structure evaluation** — design decision needed. Is VIX9D/VIX1D slope a valuable short-term vol signal beyond raw VIX? Where does it live — equity_volatility or rates_curve? yfinance ticker availability (^VIX9D appears to exist; ^VIX1D may not). Opus recommendation → Sonnet implements.

- [ ] **Brief 15 — Backtest signal-quality card + link** *(design complete — see [ROADMAP.md §Brief 15](ROADMAP.md))*
  Opus design pass done (2026-04-24). Scope locked: ONE compact card (rolling composite IC + recent alert hit rate + verdict) on main dashboard, plus a prominent link to the existing full `output/backtest_report.html`. Dropped SPX overlay and lead-time / FP-rate metrics on purpose — those belong in the full report. Live rolling IC is the actual unshipped piece (claimed Phase 4 never landed on the dashboard). Ready for Sonnet — est. half a day.

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

## Status as of 2026-04-24 (post-Sonnet 4.6 execution pass)

Phases A, B, and C are fully complete. All items either shipped or confirmed
already-shipped during this session. Only Phase D remains, and each item there
requires an Opus design pass before Sonnet can execute.

---

## Mid-task handoff — 2026-04-24, Opus → Sonnet (Brief 15)

**Context:** Opus completed the design pass for the backtest signal-quality
card. Full brief is in [ROADMAP.md §Brief 15](ROADMAP.md).

**Key scope decisions Opus locked in (do not re-open without surfacing):**

- Main-dashboard card + link to existing `output/backtest_report.html`.
  **Not** a full page port — the comprehensive report already exists.
- Only TWO numeric metrics on the card: rolling composite IC (252d, 21d
  forward SPX drawdown) and recent alert hit rate (60d from
  `get_postmortem_stats`). Lead time, FP rate, and SPX overlay are out.
- Reuse `build_forward_drawdown` and `spearman_ic` from `src/evaluation.py`
  verbatim. No parallel IC implementations.
- Verdict thresholds: IC ≥ 0.15 = Tracking, 0.05 ≤ IC < 0.15 = Weak,
  IC < 0.05 = Miscalibrated, <60 history rows = Insufficient history.
- Discovered in passing: TODO.md's "Phase 4 — Live performance tracking"
  claim is wrong — no backtest content exists on the live dashboard today.
  Brief 15 closes that gap.

**Start here (Sonnet):**

1. Read [ROADMAP.md §Brief 15](ROADMAP.md) in full — it lists every file
   touch, the IC helper signature, test names, and edge cases.
2. Run `python -m pytest tests/ -q` — must be 181+ green before starting.
3. Implement in the order listed in the brief: (a) `rolling_composite_ic`
   in `evaluation.py`, (b) test it, (c) `_build_signal_quality_card` in
   `dashboard.py`, (d) wire through `run_dashboard.py`, (e) the
   `--publish` docs copy.
4. Verify the card's IC is within ±0.1 of the 21-day cell in
   `output/backtest_report.html` (ballpark sanity check — they won't match
   exactly since the card uses last 252 rows only).
5. Commit with a message referencing Brief 15. Mark this TODO item done.

**Flag and switch back to Opus if:**

- The rolling IC comes out wildly different (>0.2 away) from the full
  backtest — that's an alignment bug and needs design attention, not a
  shipping fix.
- `get_postmortem_stats` turns out to have zero scored alerts in 60 days
  (alert log too sparse). Decide: hide the hit-rate line or show "0/0" as
  a non-signal. Default to hiding if ambiguous.

**Delete this section** once Brief 15 ships and the card renders with real
numbers in the generated dashboard.
