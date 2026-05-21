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

## Known issues — observed 2026-04-29 (RESOLVED 2026-05-11)

Both issues diagnosed and closed.

~~### Issue 1 — Morning automation fired at 9:30 AM CST instead of 7:30 AM~~
**RESOLVED 2026-05-11:** Git publish timestamps show 7:31 AM runs daily through May. One-off wake event, not a recurring fault.

~~### Issue 2 — Overnight News Brief not updating~~
**RESOLVED 2026-05-11:** Feed probe shows 12/13 feeds live (261 total entries). FSB Press Releases dead (0 entries, non-critical). No `news_feed_failure` entries in alert_log. News triage is healthy.

---

## Known issues — observed 2026-05-20 (OPEN)

### Issue 3 — Missed morning run on 2026-05-20

`data/latest.json` was last written at **17:52 UTC on 2026-05-19**. The daily 7:30 AM ET (11:30 UTC) run on 2026-05-20 did not fire. Machine was likely in deep sleep and did not respond to the RTC wake trigger.

**Impact:** The `tactical_markets_trading` bot's MACRO preflight (`src/macro_consumer.py`) treats sidecar files >24h stale as neutralized — full-size trades, no regime gating. No risk of bad action, but regime protection is defeated until the next successful run.

**To investigate:** Check Windows Event Viewer → Task Scheduler → `Market Dashboard Wake` and `Market Dashboard` task history for 2026-05-20. If the wake task fired but the run task didn't, it's a timing issue (run fires before PC is fully awake). If neither fired, the RTC wake isn't working reliably — may need to pin the machine to never sleep, or add a `StartWhenAvailable` flag to the market_dashboard run task (same fix applied to the trading bot tasks).

---

**Tactical Markets companion projects** are now sibling repos with their own backlogs:
[../tactical_markets/TODO.md](../tactical_markets/TODO.md), [../tactical_markets_trading/TODO.md](../tactical_markets_trading/TODO.md). They remain in hopper until Market Stress Dashboard is complete and all Phase G items ship.

**Downstream consumer coordination:** the `tactical_markets_trading` bot has filed three coordination tasks (W1-W3) at [_bmad-output/planning-artifacts/bot-integration-asks.md](_bmad-output/planning-artifacts/bot-integration-asks.md). **W1 (HIGH) directly affects the 2026-05-30 regime-weights review** — without pre-coordination, that recalibration will silently block bot trading. Read before the 5/30 checkpoint.

---

## Sonnet's next execution queue

Ordered top-down by value × (1/effort), respecting dependencies. Sonnet should
execute in order. Design-first items marked 🅾️ — route through Opus before
Sonnet starts.

### Phase 0 — Highest priority (do these first)

- [x] 🅾️ **Codebase optimization pass** — Opus design pass complete 2026-04-29.
  Produced **Brief 21** (in [ROADMAP.md](ROADMAP.md#brief-21--codebase-optimization-pass)) — 9 prioritized items split across P0/P1/P2 tiers with effort estimates totaling ~3.5–4 hours. Recommended commit order: 21A (backtest indicator gap) → 21B (band-from-score consolidation) → 21C (color palette unification) → 21D (fetch dedup) → 21F (VIX series capture) → 21G (deferred imports) → 21E (yaml loader helper) → 21H/21I (small wins). Sonnet to execute as separate commits per item.

- [x] **Brief 22 — Model explainer section in backtest report** *(shipped 2026-04-29)*
  `_section_explainer()` wired into `src/backtest_report.py:generate_report`. Both expert and plain-English registers in collapsible `<details>` blocks.

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

- [x] **Brief 15 data alignment checks** *(shipped — commit e6ac3fa)*
  Signal quality card now shows backtest and composite timestamps side-by-side. Warns (yellow) if >2h apart or backtest CSV >2 days stale.

- [x] **Data quality monitoring / bucket health** *(shipped)*
  `_build_bucket_health_card()` in `dashboard.py`: collapsible "DATA QUALITY (N issues)" section. Detects (a) indicators with `percentile=None` (failed fetches falling back to 50.0) and (b) bucket scores unchanged for ≥3 consecutive runs (possible stale source). Rendered between staleness banner and composite card.

- [x] **Alert channel redundancy** *(shipped)*
  `_send_email_fallback()` in `src/alerts.py` using `smtplib` + Gmail SMTP (port 587). Triggered when both Pushover and Twilio return False. Requires `GMAIL_APP_PASSWORD` in `.env`; `ALERT_EMAIL_FROM`/`ALERT_EMAIL_TO` default to rekward01@gmail.com. Wire `GMAIL_APP_PASSWORD` in `.env` to activate.

- [x] **Mobile / responsive design** *(shipped)*
  Added `@media(max-width:600px)` block: `.hdr` stacks vertically, `.composite` stacks, `.bucket-grid` goes single-column, tooltips right-align to avoid overflow. Action row gets `flex-wrap:wrap;min-width:260px` so cards stack below ~534px.

### Phase E — Design-first items (route through Opus before Sonnet executes) 🅾️

- [x] **Brief 15 — Backtest signal-quality card + link** *(shipped)*
  Opus design pass done (2026-04-24). Scope locked: ONE compact card (rolling composite IC + recent alert hit rate + verdict) on main dashboard, plus a prominent link to the existing full `output/backtest_report.html`.

- [x] **Brief 16 — VIX term-structure indicator** *(shipped — commit e032f70)*
  VIX/VIX3M ratio in equity_volatility bucket. Reweighted: vix→0.50, vix_term_structure→0.25, sp500_1m_vol→0.25. Thresholds: yellow=0.95, orange=1.00, red=1.05. 4 new tests, 187/187 passing.

- [x] **Brief 10A — Regime classification telemetry** *(shipped — commit 9541963)*
  classify_vix_regime() in history.py; badge in composite card (low=green, mid=yellow, high=orange); regime column in history.csv; regime_previous persisted via alert_state.json. Composite unchanged. 3 new tests, 190/190 passing.

- [x] **Brief 10B — Backtest + recalibrate regime extension** *(shipped — commit 7a9108e)*
  Backtest writes `regime` column per date (point-in-time VIX tercile). evaluation.py gains per_regime_bucket_ic(). recalibrate --regime prints proposed regime_weights: YAML block to stdout (no file writes). 2 new tests, 192/192 passing.

- [x] **Brief 10C — Apply regime weights at score time** *(shipped — commit pending)*
  regime_weights: block in weights.yaml (Option A conservative multipliers, enabled=false). _apply_regime_weights() in scoring.py: computes both composite_naive and composite_regime_weighted every run. Dashboard shows "Regime preview: XX (disabled)" side-by-side with composite. Flip enabled: true after review. 3 new tests, 195/195 passing.

- [x] **Brief 20 — Expand free wire-service news coverage** *(shipped 2026-04-29 — commit f9b1001)*
  Feed list in `config/news_feeds.yaml` (not hardcoded). 13 feeds live as of 2026-05-01:
  6 official (Fed, Fed Speeches, ECB, Treasury, BIS Speeches, FSB) + 7 publisher
  (MarketWatch, Yahoo, Bloomberg, CNBC, FT Alphaville, WSJ Economy, FT Global Economy).
  Reuters and AP have no free individual-tier path. Jaccard dedup, source attribution
  in dashboard and Haiku prompt, feed-health logging, `_validate_news_feeds()` in
  startup chain. 219/219 tests.

- [x] **Brief 19 — Commodities & Energy bucket diversification** *(shipped 2026-04-29 — commit 86be640)*
  Full brief in [ROADMAP.md](ROADMAP.md#brief-19--commodities--energy-bucket-diversification).
  Drops `oil_vol` (redundant with VIX/MOVE in real stress); adds `crack_spread_321`
  (3-2-1 crack — paper-vs-physical refining-margin signal, Ian's specific ask),
  `natgas` (NG=F YoY — independent supply-shock vector), and `copper_gold_ratio`
  (HG=F/GC=F — growth/risk-off proxy). New weights: wti_crude 0.30,
  crack_spread_321 0.25, natgas 0.25, copper_gold_ratio 0.20. Bucket weight in
  composite stays 0.07. Two new computed handlers, one yfinance ticker with
  yoy_series transform, three new threshold blocks, three new tooltips, three
  new tests. Bucket label stays "Commodities & Energy".

- [ ] 🅾️ **Regime-weights review checkpoint + W1 protocol** *(re-review due 2026-06-20 — Brief 26 in ROADMAP.md)*
  **Gate run 2026-05-20 — DEFERRED.** Criterion (a) failed: every production day since
  2026-04-25 has been `mid` regime; zero high-regime episodes → cannot verify sensible
  divergence. Criteria (b) passed (rates_curve +0.180, inflation +0.150 in high) and
  (c) passed (stable regime column, 7 NaN startup rows not genuine flaps).
  `enabled` stays false. `weights_hash` unchanged → no bot W1 coordination needed.
  **Two bugs found to fix before next review (Sonnet-executable, ~1 hour):**
  1. `composite_regime_weighted` not logged to `history.csv` (Brief 10C gap) — add column
     to `log_run()` in `src/history.py` so next review has divergence data.
  2. Recalibrate multiplier logic amplifies anti-signal: negative-IC buckets get 2x
     multipliers (e.g. `economic_momentum` IC=-0.195 → mult=2.0 in high). Fix: in
     `propose_regime_weights()`, use `max(ic_val, 0.0)` when computing the IC ratio,
     so negative-IC buckets always get multiplier=1.0 (neutral).
  Also found: `_bt_yf` dead import bug in `recalibrate.py` (committed 2026-05-20).
  Re-review on 2026-06-20 with Brief 26 Part A procedure unchanged.

### Phase F — Blocked on Ian's scope call (do not start until Ian answers)

- [x] ~~**Paywalled news sources**~~ *(closed 2026-05-20 — Ian's call)*
  Brief 20 (free wire-service expansion) shipped and covers the use case. Paywall
  bypass tooling (12ft.io dead; Bypass Paywalls Clean is browser-only; archive.ph
  unreliable for recent content; cookie-auth violates ToS and requires manual renewal).
  Marginal-signal argument: the system does keyword matching on headlines; existing 13
  feeds already include wire-service content via MarketWatch, Yahoo, Bloomberg, CNBC,
  FT Global Economy, WSJ Economy. No demonstrated coverage gap. Not pursuing further
  unless a real market episode shows the free feeds missed something material.

- [x] **Research — find free/reliable Reuters, WSJ, and FT feed alternatives** *(complete 2026-05-01)*
  Findings shipped as 4 new feeds in `config/news_feeds.yaml` (now 13 total: 6 official + 7 publisher).
  - **WSJ:** Old `wsj.com/xml/rss/` URLs are dead. `feeds.content.dowjones.io/public/rss/socialeconomyfeed` is live, no auth. Added as publisher.
  - **FT:** Free RSS at `ft.com/global-economy?format=rss` — official, no auth. Added as publisher.
  - **BIS Speeches:** `bis.org/doclist/cbspeeches.rss` aggregates global CB speeches (Fed/ECB/BOE) before wire services. Added as official.
  - **FSB:** `fsb.org/wordpress/content_type/press-releases/feed/` — G20 macroprudential releases. Added as official.
  - **Reuters/AP/Bloomberg beyond existing:** No viable individual-tier path. Reuters LSEG API $500–$10K+/month institutional; AP requires sales contact (likely $10K+/year); Bloomberg nothing between free Markets RSS and $28K/year Terminal. Dead ends confirmed.

- [ ] **Portfolio integration** *(user scope call required)*
  Fidelity API or CSV of position holdings for personalized recommendations. Ian needs to decide: (a) Fidelity API vs CSV input, (b) fields needed (symbol, quantity, cost basis?), (c) position-level alerts vs high-level commentary. Not an Opus or Sonnet task until Ian answers these.

### Phase G — User-requested UX additions (2026-04-25)

Ian's batch from 2026-04-25 review. Item 1 is its own brief (real behavior change);
items 2/3/7 cluster naturally as a "naming + plain-English layer" batch; items 4/5
are small ordering/link fixes; item 6 is a content-authoring brief. Sonnet should
preserve Ian's numbering when committing so the trail back to this list is clear.

- [x] **G1 — Stale data + data quality auto-remediation** *(Brief 17 v2 in ROADMAP.md — design locked, ready for Sonnet)* *(commit 13a9beb)*
  Full brief in ROADMAP.md. **Read v2 only — v1 had three load-bearing errors
  (wrong function name, unsafe pipeline placement, dispatch in wrong layer)
  that Opus corrected in v2.** Summary: after `annotate_results()` and
  *before* `log_run()`/`send_alerts()`, collect indicators with `percentile:
  None` or in `stale_indicators` (excluding `computed` types); pass
  `_remediation_keys` through `env`; the bypass dispatch lives in
  `_fetch_indicator()`, not the leaf fetch functions. Run
  `compute_composite` + `annotate_results` a second time (once max). Log
  each attempt to `data/alert_log.jsonl`. 3 new tests + 2 regression checks
  (single history row, single alert call).

- [x] **G2 — Name "Weighted Average" section + plain-English explainer** *(commit 46dc1b5)*
  Identify the section Ian is referring to (likely the composite card showing
  the 0–100 score, or the per-bucket weighted contribution row).
  - Give it an explicit heading (e.g. "COMPOSITE — WEIGHTED AVERAGE OF 11 BUCKETS").
  - Add a "What does this mean?" `<details>` block: what 0–100 represents,
    how to read the current band, what to do (or not do) with the number.
    Calibrate to Ian's stated use — "help me think, never tell me what to do."

- [x] 🅾️ **G3 — Layman narrative suggests household action** *(shipped — commit 2099f57)*
  Surprise: most of G3 is already shipped (both registers generated, JSON-parsed,
  cached, toggle button + JS in place). The real gap was the layman prompt
  forbidding action — Ian's call (2026-05-01) is to flip that. Brief 23 covers:
  (1) new `_SYSTEM` prompt (verbatim in brief) with band-calibrated household-level
  action language; (2) localStorage persistence of toggle choice; (3) cache
  versioning so old observational layman text doesn't survive the prompt change;
  (4) disclaimer wording update; (5) one regression test.
  **Locked:** action level is household financial behavior only (cash buffer,
  emergency fund, timing of large purchases) — never specific securities,
  sectors, or asset allocations. Expert register stays observational per
  CLAUDE.md. Asymmetry is intentional and documented in brief.

- [x] **G4 — Reorder: swap Overnight News Brief ↔ Historical Analogies** *(shipped 2026-04-29)*
  News section now renders after bucket grid; analogies card renders directly after AI narrative.

- [x] **G5 — Restore clickable links in Overnight News Brief** *(already shipped — confirmed 2026-04-29)*
  Headlines were already wrapped in `<a href>` via `best_match_url` in `news.py`. No change needed.

- [x] **G6 — Indicator Detail enrichment: advanced + layman interpretations** *(Brief 18 — shipped 2026-04-29)*
  Content delivered: `config/indicator_explainers.yaml` is authored with
  advanced + layman + model_role entries for all 27 active indicators plus
  3 staged for Brief 19 (crack_spread_321 / natgas / copper_gold_ratio).
  Sonnet's remaining work is purely the wiring:
  (a) Extend `src/indicator_detail.py:build_indicator_detail` to load the
      YAML and render the three prose blocks below the existing chart +
      stats table. Render `model_role` as a footer line, not a separate
      block.
  (b) Add `_validate_indicator_explainers()` to `src/config.py` that warns
      (does not raise) when an indicator in weights.yaml has no explainer
      entry — placeholder text "(explainer coming soon — Brief 18)" should
      render in the dashboard for that case so the absence is visible.
  (c) Add a small test that loads the YAML and asserts every key in
      `KNOWN_INDICATOR_KEYS` (excluding the 3 Brief 19 entries which are
      pre-staged) has all three fields populated.

  > ⚠️ **Coordination with Brief 19:** when Brief 19 ships, it must
  > delete the `oil_vol:` block from `config/indicator_explainers.yaml`
  > in the same commit. The 3 Brief 19 entries (`crack_spread_321`,
  > `natgas`, `copper_gold_ratio`) are *already* present in the YAML —
  > Brief 19 does NOT need to add them. See Brief 19's file step 6 in
  > ROADMAP.md.

- [x] **G7 — Name the buckets section** *(shipped 2026-04-29)*
  Section heading added at `.9rem` to match REVIEW PROMPTS typographic weight.

- [x] **As-of dates on Overnight News Brief** *(shipped 2026-04-29)*
  `news.py` captures `published_parsed`/`updated_parsed` from feedparser; renders as "Source · Apr 30:" label on each bullet.

- [x] **G8 — Dashboard section reorder (Ian, 2026-05-15)** *(commit 74abba1)*
  Move four sections — **Historical Analogues**, **Cross-bucket correlation**, **Model Calibration**, and **90-day Composite trend** — to where the **Overnight News Brief** currently renders, preserving the listed order. Move **Overnight News Brief** to immediately below the **AI Narrative Summary**. Single-file edit in `src/dashboard.py`; confirm current render sequence first (the existing G4 reorder moved News after the bucket grid and Analogies after the narrative — this supersedes that placement for both). No config / data / test changes expected unless a layout test asserts ordering.

- [x] **G9 — "Next anticipated refresh" for stale indicators (Ian, 2026-05-15)** *(commit 8bdf626)*
  When an indicator appears in the staleness banner or bucket health card as stale, show an estimated next-data-release date rather than just "stale — X days ago." This prevents the dashboard from implying the data *could* be fresher when it simply hasn't been published yet. Design decisions needed before Sonnet executes:
  - Where does the release schedule live? Options: (a) a `next_release:` field per indicator in `config/weights.yaml` (authoritative, co-located with source config, but static); (b) a new `config/release_schedule.yaml` keyed by indicator with a release cadence rule (e.g., `weekly: thursday`, `monthly: second_tuesday`, `quarterly: last_business_day_of_quarter`); (c) hardcoded per fetch type in `src/fetch.py` (no config overhead but harder to maintain). Recommend (b) — separates scheduling concern cleanly, easy to extend.
  - What does the UI show? Suggested: `"next release est. Fri May 16"` inline in the staleness banner / bucket health card wherever the stale indicator label appears. If the next release date has already passed (data is late), show `"expected by [date] — overdue"` in orange.
  - Which indicators need schedule entries on day 1? At minimum the ones that have actually appeared as stale in production: `stlfsi` (weekly, Fridays), `jobless_claims` (weekly, Thursdays). Add others from `config/weights.yaml` as a best-effort batch — FRED series release schedules are documented in their API metadata.
  - Opus design pass required to settle (a)/(b)/(c) and the overdue-display logic before Sonnet implements.

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

## Design questions pending Opus input

**Energy/Commodities bucket — paper vs. real prices** *(flagged 2026-04-27, resolved 2026-04-27)*
~~Original ask: should bucket include spot gasoline/diesel/jet fuel?~~
**Resolved as Brief 19** in ROADMAP.md. Crack spread (3-2-1) captures Ian's
paper-vs-physical intuition more cleanly than retail spot prices, and the
bucket is simultaneously diversified beyond pure WTI exposure (added natgas,
copper/gold). Real-economy "consumer energy burden" deferred to a future
non-scored display panel. See Phase E for the executable brief.

---

## Execution priorities — 2026-04-25

**Next up for Sonnet:** Phase G items G3–G7 (dashboard UX additions).
When a design question blocks progress, flag to Opus (e.g., Energy/Commodities bucket above).

---

### Phase I — Downstream integration (Sonnet-ready, 2026-05-11)

- [x] **Brief 24 — JSON sidecar for downstream consumers** *(shipped — commit 2046161)*
  `data/latest.json` written after each run. `write_latest_sidecar()` in
  `src/history.py`; wired into `run_dashboard.py` after `write_dashboard()`.
  Strips `_series` blobs; stamps `schema_version`/`weights_hash`/`code_sha`.
  6 new tests in `tests/test_sidecar.py`; 236/236 passing.

### Phase H — Phone-triggered refresh (Sonnet-ready, 2026-05-11)

- [x] 🅾️ **Brief 25 — Phase H: Phone-triggered dashboard refresh via GitHub Actions** *(shipped — commit 957736b)*
  `.github/workflows/on-demand-dashboard.yml` live with retry-on-conflict logic.
  `--ondemand` flag in `run_dashboard.py` skips log_run/prune/alerts/digest/heartbeat.
  `tests/test_ondemand.py` covers all 5 assertions. Secrets to add in GitHub:
  `FRED_API_KEY`, `ANTHROPIC_API_KEY`. iOS Shortcut setup in ROADMAP.md Brief 25.
