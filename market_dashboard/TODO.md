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

### Phase D — System resilience hardening (high-priority, Sonnet execution)

**Before adding new features, harden the existing system against silent failures and data drift.**

- [x] **Dashboard self-diagnostics** *(shipped)*
  JS `automation-banner` div injected with ISO timestamp on `<body data-run-ts="...">`. If >30 hours since last run, injects red "AUTOMATION OFFLINE — X hours ago" banner. No-op when automation is healthy.

- [ ] **Brief 15 data alignment checks** *(added to Brief 15 implementation)*
  Brief 15's rolling IC card is only valid if backtest and live dashboard are synchronized. Add: (a) timestamp validation — show "backtest: 2026-04-24 07:35, composite: 2026-04-24 07:30" and warn if >2 hours apart; (b) sample count display — show "IC: 0.12 (252 obs)" so small-sample noise is visible; (c) freshness indicator — show "last backtest: 2026-04-24" and warn if >2 days stale. Wired into `_build_signal_quality_card()`.

- [x] **Data quality monitoring / bucket health** *(shipped)*
  `_build_bucket_health_card()` in `dashboard.py`: collapsible "DATA QUALITY (N issues)" section. Detects (a) indicators with `percentile=None` (failed fetches falling back to 50.0) and (b) bucket scores unchanged for ≥3 consecutive runs (possible stale source). Rendered between staleness banner and composite card.

- [x] **Alert channel redundancy** *(shipped)*
  `_send_email_fallback()` in `src/alerts.py` using `smtplib` + Gmail SMTP (port 587). Triggered when both Pushover and Twilio return False. Requires `GMAIL_APP_PASSWORD` in `.env`; `ALERT_EMAIL_FROM`/`ALERT_EMAIL_TO` default to rekward01@gmail.com. Wire `GMAIL_APP_PASSWORD` in `.env` to activate.

- [x] **Mobile / responsive design** *(shipped)*
  Added `@media(max-width:600px)` block: `.hdr` stacks vertically, `.composite` stacks, `.bucket-grid` goes single-column, tooltips right-align to avoid overflow. Action row gets `flex-wrap:wrap;min-width:260px` so cards stack below ~534px.

### Phase E — Design-first items (route through Opus before Sonnet executes) 🅾️

- [x] **Brief 15 — Backtest signal-quality card + link** *(shipped)*
  Opus design pass done (2026-04-24). Scope locked: ONE compact card (rolling composite IC + recent alert hit rate + verdict) on main dashboard, plus a prominent link to the existing full `output/backtest_report.html`.

- [ ] **Brief 16 — VIX term-structure indicator** *(design complete — see [ROADMAP.md §Brief 16](ROADMAP.md))*
  Opus design pass done (2026-04-25). Scope locked: VIX/VIX3M ratio (industry-standard term-structure signal), `equity_volatility` bucket, `computed` handler. Bucket re-weighted (vix 0.50, term_structure 0.25, realized_vol 0.25). Threshold bands 0.95/1.00/1.05 on the raw ratio. Single new test in `tests/test_vix_term_structure.py`. Ready for Sonnet — est. 1–2 hours.

- [ ] **Brief 10A — Regime classification telemetry** *(design complete — see [ROADMAP.md §Brief 10A](ROADMAP.md))*
  Read-only telemetry: classify VIX into low/mid/high terciles (smoothed 5d, hysteretic 1.0 buffer), display badge, log to history. **No scoring change.** Lets Ian observe regime behaviour for weeks before flipping the switch in 10C. Three new tests. Est. half a day.

- [ ] **Brief 10B — Backtest + recalibrate regime extension** *(design complete — see [ROADMAP.md §Brief 10B](ROADMAP.md))*
  Depends on 10A. Add `regime` column to backtest, per-regime per-bucket IC analysis in `evaluation.py`, new `recalibrate --regime` mode that proposes a `regime_weights:` multiplier block to stdout (no auto-apply). Two new tests. Est. half a day.

- [ ] **Brief 10C — Apply regime weights at score time** *(design complete — see [ROADMAP.md §Brief 10C](ROADMAP.md))*
  Depends on 10A + 10B. Wire `regime_weights:` into `compute_composite()`. Always compute both `composite` and `composite_naive` so dashboard shows side-by-side. Default `enabled: false` — Ian flips after a few days of side-by-side observation. Validation backtest + IC comparison required before flipping. Three new tests. Est. half a day.

### Phase F — Blocked on Ian's scope call (do not start until Ian answers)

- [ ] 🅾️ **Paywalled news sources** *(user scope call required)*
  Which of WSJ / FT / Bloomberg does Ian actually want? What's the minimum-viable integration (RSS where allowed, archive links, nothing questionable)? Legal / ToS review required before any scraping. Not an Opus or Sonnet task until Ian picks the feeds.

- [ ] **Portfolio integration** *(user scope call required)*
  Fidelity API or CSV of position holdings for personalized recommendations. Ian needs to decide: (a) Fidelity API vs CSV input, (b) fields needed (symbol, quantity, cost basis?), (c) position-level alerts vs high-level commentary. Not an Opus or Sonnet task until Ian answers these.

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
already-shipped during this session. **Phase D (resilience hardening) is now the
priority before new features.** Phase D items are Sonnet-executable (no design pass needed).
Phase E (VIX term structure, Brief 15, Brief 10, news sources) remains design-first
and requires Opus passes before Sonnet executes.

---

## Execution priorities — 2026-04-25

**Next up for Sonnet:** Phase D resilience hardening (5 items, ~8 hours total).
After Phase D ships, Sonnet can execute Brief 15 with data alignment checks built in.
Then Phase E design-first items await Opus review.
