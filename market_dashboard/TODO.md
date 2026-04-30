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

## Known issues — observed 2026-04-29 (diagnose first)

These two items are **observed bugs**, not design tasks. Diagnose before
shipping more features. If Sonnet picks them up, run the diagnostic steps
in order rather than guessing at fixes.

### Issue 1 — Morning automation fired at 9:30 AM CST instead of 7:30 AM

**Symptom:** Today's dashboard run completed at ~9:30 AM CST. Expected
7:30 AM (per Windows Task Scheduler "Market Stress Dashboard" task). Two-
hour delay is consistent with: laptop failed to wake, or the scheduled
task fired but stalled on something (network, fetch, dependency).

**Diagnostic order** (per CLAUDE.md "Morning automation" section):

1. `powercfg /lastwake` (admin shell) — what woke the machine and when?
   - If wake timestamp is 9:30 AM, the wake task at 7:20 AM didn't fire
     → check `powercfg /waketimers` (admin) for the "Market Dashboard
     Wake" entry; verify `RTCWAKE=1` is still set in the task XML; verify
     the laptop wasn't unplugged (RTC wake is power-state-dependent on
     some configs).
   - If wake timestamp is 7:20 AM but dashboard ran at 9:30 AM, the wake
     succeeded but the 7:30 task either fired-and-stalled or didn't fire.
2. `schtasks /query /tn "Market Stress Dashboard" /v /fo LIST` — check
   "Last Run Time" and "Last Result" code. Result `0x0` = success;
   anything else (especially `0x1` or `0x2`) is a fault to investigate.
3. Check `data/alert_log.jsonl` for entries between 7:30 AM and 9:30 AM
   today — if there are entries, the dashboard *did* run at 7:30 but
   maybe failed silently and retried.
4. Check `output/dashboard.html` mtime — if it's 9:30, only one run
   happened. If 7:30 mtime exists but stale content, the run completed
   but didn't write properly (rare but possible if a fetch hung).
5. Windows Event Viewer → Applications and Services Logs → Microsoft →
   Windows → TaskScheduler → Operational. Filter for the dashboard task
   GUID; look for "Task Engine launched" / "Task completed" pairs and any
   error events in the 7:30–9:30 window.

**Note on DST:** US DST began 2026-03-08, so we're 7 weeks in. Unlikely to
be a DST-edge-case bug at this point in the cycle, but worth checking
that the task XML still has the local-time trigger and not a UTC trigger
that drifted at the DST boundary.

### Issue 2 — Overnight News Brief not updating in the Pushover-delivered report

**Symptom:** Pushover alerts / heartbeats coming through but the news
brief content appears stale (or the news section appears empty).

**Clarification needed before fixing:** the dashboard's "Overnight News
Brief" section and the news content in Pushover messages come from
*different code paths*. Likely interpretations:

- **(a) The dashboard HTML's news section is stale** — `get_news_brief()`
  in `src/news.py` returned `[]` so `news_html` is empty; the previous
  render's news doesn't carry forward (each run rewrites the file). When
  Ian clicks the GitHub Pages link in his Pushover message, the dashboard
  has no news section.
- **(b) The Pushover message body lacks news context** — by design,
  `send_alerts()` only appends `get_trigger_news_context()` output when
  triggers actually fire. Daily heartbeats (`send_heartbeat()`) and
  weekly digests (`send_weekly_digest()`) do *not* include news. If Ian
  expects news in the daily heartbeat, that's a feature gap, not a bug.

**Most likely root cause for (a):** one of the 4 hardcoded RSS feeds in
`src/news.py:RSS_FEEDS` (Reuters businessNews, MarketWatch, Yahoo
Finance, WSJ markets) has gone dead, and the silent `try/except: continue`
on lines 47–48 hides the failure. If 2+ feeds die, the headline list is
short or empty → `_filter_relevant` returns nothing → Haiku gets nothing
to summarize → `get_news_brief` returns `[]`.

**Diagnostic steps (run in order):**

1. From the primary dir, run a manual dry pass and inspect the news
   section: `python run_dashboard.py --no-cache --no-alerts --quiet`
   then open `output/dashboard.html` in a browser. Is the "Overnight
   News Brief" section present and populated, or empty?
2. If empty, instrument the four RSS feeds — quick Python REPL:
   ```python
   import feedparser
   for url in [
       "https://feeds.reuters.com/reuters/businessNews",
       "https://feeds.marketwatch.com/marketwatch/realtimeheadlines/",
       "https://finance.yahoo.com/rss/topstories",
       "https://www.wsj.com/xml/rss/3_7085.xml",
   ]:
       f = feedparser.parse(url)
       print(url, "→", len(f.entries), "entries")
   ```
   Any feed returning 0 entries is the (or a) culprit.
3. Check `.env` for `ENABLE_NEWS_TRIAGE` — if it's `false` or missing,
   the brief is intentionally skipped. Default should be `true` (or
   unset, which `news.py` treats as `true`).
4. Check `ANTHROPIC_API_KEY` is still valid — if Haiku auth fails,
   `get_news_brief` returns `[]` silently.
5. Inspect `data/cache/` for any news-related cache file — if one is
   minutes old but empty, the cache is masking a fetch failure.

**Likely fix:** **Brief 20** in [ROADMAP.md](ROADMAP.md#brief-20--expand-free-wire-service-news-coverage)
already addresses this directly:
- expands feeds from 4 to ≥8 (so a single feed death isn't fatal),
- moves feed list to `config/news_feeds.yaml` (no code change to swap a
  dead feed),
- adds `_log_feed_failure()` writing to `alert_log.jsonl` so silent
  failures become observable,
- adds source attribution end-to-end (Ian can see *which* feed each
  headline came from in the dashboard).

**Recommendation:** diagnose with the steps above to confirm root cause
*today*, then prioritise shipping Brief 20 as the durable fix. If it's
specifically interpretation (b) — Ian wants news in the daily heartbeat
itself — open a separate small brief for that (heartbeat enrichment
is a 30-min change in `src/alerts.py:send_heartbeat`).

---

## Tactical Markets (In Planning, Hopper Until Market Stress Dashboard Ships)

**Two companion tool briefs drafted and committed (2026-04-27):**
- `tactical_markets/ROADMAP_SIGNAL_GENERATION.md` — overnight repricing + sector rotation dashboard (6:30 AM premarket signals)
- `tactical_markets_trading/ROADMAP_ALPACA_INTEGRATION.md` — Alpaca paper trading integration + validation loop (Phase 1–3)
- `tactical_markets/RESEARCH_SUMMARY.md` — research grounding (2000–2026 empirical findings)

**Status:** Specs locked in, research-backed, not yet coded. Remain in hopper until Market Stress Dashboard is complete and all Phase G items shipped. Target start: after 2026-05-30 regime-weights review checkpoint.

---

## Sonnet's next execution queue

Ordered top-down by value × (1/effort), respecting dependencies. Sonnet should
execute in order. Design-first items marked 🅾️ — route through Opus before
Sonnet starts.

### Phase 0 — Highest priority (do these first)

- [x] 🅾️ **Codebase optimization pass** — Opus design pass complete 2026-04-29.
  Produced **Brief 21** (in [ROADMAP.md](ROADMAP.md#brief-21--codebase-optimization-pass)) — 9 prioritized items split across P0/P1/P2 tiers with effort estimates totaling ~3.5–4 hours. Recommended commit order: 21A (backtest indicator gap) → 21B (band-from-score consolidation) → 21C (color palette unification) → 21D (fetch dedup) → 21F (VIX series capture) → 21G (deferred imports) → 21E (yaml loader helper) → 21H/21I (small wins). Sonnet to execute as separate commits per item.

- [x] **Model explainer section in backtest report** — Opus content drafted 2026-04-29 as **Brief 22** in [ROADMAP.md](ROADMAP.md#brief-22--backtest-model-explainer-expert--plain-english). Both registers (~400 words each) provided as ready-to-paste HTML in a `_section_explainer()` function. Sonnet wires into `src/backtest_report.py:generate_report` above the first `_run_and_render` call.

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
  9 feeds live: 4 official (Fed, Fed Speeches, ECB, Treasury) + 5 publisher
  (MarketWatch, Yahoo, Bloomberg, CNBC, FT Alphaville). Reuters and AP have fully
  abandoned free public RSS. Jaccard dedup, source attribution in dashboard and
  Haiku prompt, feed-health logging, `_validate_news_feeds()` in startup chain.
  205/205 tests. Fixed pre-existing `test_remediation_skipped_on_clean_run` failure
  (weekly FRED series legitimately stale — test was asserting wrong condition).

- [ ] **Brief 19 — Commodities & Energy bucket diversification** *(design locked 2026-04-27, ready for Sonnet)*
  Full brief in [ROADMAP.md](ROADMAP.md#brief-19--commodities--energy-bucket-diversification).
  Drops `oil_vol` (redundant with VIX/MOVE in real stress); adds `crack_spread_321`
  (3-2-1 crack — paper-vs-physical refining-margin signal, Ian's specific ask),
  `natgas` (NG=F YoY — independent supply-shock vector), and `copper_gold_ratio`
  (HG=F/GC=F — growth/risk-off proxy). New weights: wti_crude 0.30,
  crack_spread_321 0.25, natgas 0.25, copper_gold_ratio 0.20. Bucket weight in
  composite stays 0.07. Two new computed handlers, one yfinance ticker with
  yoy_series transform, three new threshold blocks, three new tooltips, three
  new tests. Bucket label stays "Commodities & Energy".

- [ ] **Regime-weights review checkpoint** *(due 2026-05-30)*
  Run `python -m src.recalibrate --regime` and check history.csv for regime distribution and composite vs composite_naive divergence. Decision criteria: (a) at least one high-regime episode where composite_regime > composite_naive and divergence made sense, (b) IC table still shows rates_curve and inflation positive in high regime, (c) no frequent regime flapping. If criteria met, flip `regime_weights.enabled: true` in config/weights.yaml and tell Sonnet to commit.

### Phase F — Blocked on Ian's scope call (do not start until Ian answers)

- [ ] 🅾️ **Paywalled news sources** *(user scope call required — partially superseded 2026-04-27)*
  **Update:** Opus design pass 2026-04-27 produced **Brief 20 (free
  wire-service expansion)** as the first move — explicitly rejecting paywall
  bypass tooling (12ft.io / Bypass Paywalls Clean) on legal + operational +
  marginal-signal grounds. Ship Brief 20 first; revisit paywalled-source
  integration only if a real market episode shows the breadth expansion
  isn't enough. The original "Brief B" alternative (manual override channel
  via `data/manual_news.json` for Ian's existing WSJ/FT subscriptions)
  remains available as a follow-on if needed.

- [ ] **Research — find free/reliable Reuters, WSJ, and FT feed alternatives**
  *(Ian's ask 2026-04-29 — research task, not execution)*
  Reuters and AP have pulled their free RSS feeds entirely. WSJ free RSS returns
  empty (paywall redirect). None of these were recoverable in Brief 20 testing.
  Before designing Brief 20B, investigate what legitimately-accessible options
  exist:
  - **Reuters:** Does the Reuters news agency publish a free API or RSS at any
    tier? Does Reuters Connect have a developer/trial tier? Does Refinitiv/LSEG
    publish anything accessible to individual subscribers?
  - **WSJ:** Ian has a WSJ subscription. Does WSJ offer RSS feeds behind login
    (email-based RSS, subscriber RSS)? Is there a "My Account → RSS" feature?
  - **Financial Times:** Does FT offer subscriber RSS (FT already has FT Alphaville
    free RSS which is in Brief 20's feed list; does a paid FT subscription unlock
    broader feeds)? FT has had a developer API in the past.
  - **Bloomberg:** Bloomberg Terminal subscribers get a feed; Bloomberg Markets RSS
    (already in Brief 20) is the free surface. Anything else at the non-Terminal tier?
  - **AP Newsroom:** AP offers paid API access (AP Content API). What's the pricing
    and whether it's viable for a personal project?
  Decision criteria: free or very low-cost (< $50/month), reliable (official API
  or subscriber RSS rather than scraping), and providing genuinely early/primary
  content rather than just aggregating what we already have. Do not start
  implementation until research is complete and Ian approves an approach.

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

- [ ] **G3 — Plain-English toggle on the AI narrative / summary**
  Identify the section (likely the Haiku-generated narrative paragraph).
  - Give it an explicit heading.
  - Add a toggle that flips between current text and a simpler layman version
    ("what is happening, why it matters, what a non-pro should do with it").
  - Source of layman text: ask Haiku for **both registers in one call** so
    they stay paired and we pay one round-trip. Cache to disk like other
    Haiku output.

- [ ] **G4 — Reorder: swap Overnight News Brief ↔ Historical Analogies**
  In `dashboard.py`, swap render order of these two sections. Verify with
  `python run_dashboard.py --no-cache --no-alerts --quiet` that section order
  is correct and layout doesn't break.

- [ ] **G5 — Restore clickable links in Overnight News Brief**
  Ian recalls headlines were clickable previously. Verify in `dashboard.py`
  / `news.py` whether headlines are wrapped in `<a href>`. If not clickable:
  (a) confirm the RSS feed exposes URLs, (b) thread URL through to rendered
  HTML. If clickable but not visibly so: add styling (underline + hover).

- [ ] **G6 — Indicator Detail enrichment: advanced + layman interpretations** *(Brief 18 — content drafted 2026-04-29, ready for Sonnet wiring)*
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

- [ ] **G7 — Name the buckets section**
  The container section housing Equity Volatility, Credit Spreads, Rates &
  Yield Curve, etc. has no top-level heading (or only a generic one). Add an
  explicit heading — e.g. "BUCKETS — 11 SIGNAL CATEGORIES" — matched to the
  typographic weight of other section headers (REVIEW PROMPTS, etc.).

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
