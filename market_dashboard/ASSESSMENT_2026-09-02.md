# ASSESSMENT_2026-09-02 — deep assessment session record

Full keep/repair/gut/rebuild pass per [DEEP_ASSESSMENT_PROMPT.md](DEEP_ASSESSMENT_PROMPT.md),
run 2026-09-02 by Claude Fable 5. This is the **session record** — the reasoning and the
recomputed evidence. The decisions live in [REDESIGN_2026-09-02.md](REDESIGN_2026-09-02.md)
(canonical execution doc); the implementation mechanics live in [DEV_PLAN.md](DEV_PLAN.md).
Code execution is HOLDING for Ian's explicit go; plan docs commit freely.

Every number below was recomputed from primary evidence this session (logs, history.csv,
alert_log.jsonl, git history, backtest reconstruction, live scheduler state, GitHub API).
Where a doc claim died on contact with evidence, it is corrected inline in the doc that
carried it, with a dated bracketed note.

---

## Phase 1 — Ground truth

### 1.1 What this project actually is (evidence, not docs)

- 316 commits since 2026-04-23: 158 daily-publish commits, 158 feature commits
  (co-authors: Sonnet 103, Opus 44, Haiku 7 — the CLAUDE.md working agreement is real
  in practice).
- ~7,600 lines of production Python, 4,370 lines of tests (281 collected), 1,866 lines
  of YAML config, 6,411 lines of markdown docs. Docs ≈ code, as predicted.
- 29 indicators (27 automated, 2 manual) in 11 buckets → composite 0–100 → bands →
  Pushover alerts → GitHub Pages + `data/latest.json` sidecar.

### 1.2 Reliability audit — recomputed against the calendar

Window 2026-04-23 → 2026-09-01 (132 calendar days), from `data/history.csv`,
`logs/dashboard_run.log`, and publish commits:

- **118/132 days ran (89%). All 14 missed days are weekend/holiday-adjacent**
  (9 Sundays, 3 Mondays, Juneteenth Friday, and 07-05→07-07 — a 3-day holiday-weekend
  outage). **Zero weekday-workday misses since 2026-07-08.** The machine-off miss class
  is real but confined to weekends; the wake/task hardening (Brief 28 + battery flags)
  worked for weekdays.
- **2026-08-31: the run started at 07:30:02, logged history at 07:34:37, sent a RED
  alert at 07:34:46, then died** before writing the dashboard — no traceback in
  `dashboard_run.log`, so a hard process kill (sleep/shutdown/OOM), not an exception.
  No publish that day. The in-pipeline health alert correctly fired the next morning
  ("not updated in 48.0 hours"). One-off; the 09-01 and 09-02 runs completed normally.
  Note the failure asymmetry: the RED market alert fired, then the dashboard behind it
  never materialized.
- **The July push outage (07-27 → 08-10) is push-level only**: publish *commits* exist
  daily right through it (git commits locally even when push is rejected), so git log
  cannot show the outage. Corroboration: the fix commit ("Fix silent publish failure
  that stalled GitHub Pages for 14 days"), the double-publish on 08-10 (07:16 manual
  repair + 07:30 scheduled), and the CLAUDE.md gotcha entry. `tests/test_publish.py`
  now pins the two repair properties.
- **Watchdog is live and armed**: repo secrets `PUSHOVER_APP_TOKEN` / `PUSHOVER_USER_KEY`
  set 2026-06-09 (verified via `gh secret list`); watchdog workflow runs daily with
  success conclusions (verified via `gh run list`). TODO.md's "ACTION REQUIRED — watchdog
  inert" banner was 3 months stale — corrected this session.
- Health-alert override behavior: when the dashboard is stale, `send_alerts()` sends the
  health alert and **returns early — the day's market alerts are swallowed** (observed
  09-01: health alert sent, no market alert despite 5 new reds the previous day).

### 1.3 Scoring the output against reality — the core finding

**Live composite vs. market outcomes (118 live observations, 2026-04-23 → 09-01;
SPX from yfinance; convention: signal on day D → entry at D's close; forward windows
in trading days):**

| Signal | vs fwd 1w return | vs fwd 1m max-drawdown | de-overlapped 1w |
|---|---|---|---|
| composite | IC **+0.42** (p≈0.00) | **+0.51** (shallower DD when stress higher) | +0.40 |
| composite_naive | +0.41 | +0.49 | +0.43 |
| composite_regime_weighted | +0.35 | +0.51 | +0.48 |

Higher stress readings predicted *better* forward outcomes all window. **Do not read
this as "the model is inverted"** — the live window is a single monotone regime: SPX
+16.1% over the window, worst 1-month forward drawdown −4.5%, composite drifting 54→36
as the rally proceeded. Two opposite trends produce exactly this correlation. Effective
n at 1 month is ~4 non-overlapping observations. **The honest statement: 132 days of
one calm rally cannot validate or refute the composite. No stress episode has occurred
on its watch. The 9-year backtest (n=2,263) remains the only instrument with power:
IC vs SPX drawdown +0.151 @ 1w, +0.117 @ 1m, +0.012 @ 3m, −0.064 @ 6m** (recomputed
this session) — modest, real, short-horizon-only skill.

**The stress_index target is contaminated.** `build_stress_index` is constructed from
VIX + HY OAS + NFCI — all three are composite *inputs*. The headline "0.73–0.81 IC vs
realized stress" (Brief 29's proven-skill line, quoted in TODO.md and the calibration
card) is substantially the composite predicting its own components' persistence. The
honest external benchmark is the SPX-drawdown column only.

**Band distribution is the true headline: 107 of 118 live days ORANGE, 11 RED,
zero green or yellow — through a +16% rally.** An early-warning system pinned at
orange has no discrimination and trains its user to ignore it.

### 1.4 Why it's pinned orange — mechanism, recomputed

`annotate_results` (src/triggers.py): headline band is trigger-count-driven —
`red>=1 → orange`, `red>=3 → red`. Reconstructing per-indicator bands from
point-in-time backtest raws (current thresholds, 2018→2026, excluding the
cnn_fear_greed backtest placeholder — see §4.2):

- **≥1 indicator red on 51% of ALL days 2018–2026** → headline orange-or-worse 55%
  of the last nine years. By year: 2019 = 4%, **2021 = 63%**, 2024 = 13%. A threshold
  set that paints calm bull year 2021 orange 63% of the time is not calibrated.
- **Live window: ≥1 red on 100% of days.** The pinned reds are
  `crack_spread_321` (red 66% of live days; raw 62.6 today, 98.6th pctile) and
  `copper_gold_ratio` (red 80% of live days; inverted, 14.2th pctile) — both Brief 19
  additions (2026-04-29) whose brief *explicitly scheduled a 2-week threshold re-check
  that never happened*. `eem_vol` orange 63% of live days compounds it.
- Historical red-firing rates of current thresholds (share of all 2,263 days):
  copper_gold_ratio 21%, jobless_claims 15%, cpi_yoy 11.5% — "red" states that fire
  1-in-5 to 1-in-9 days carry ~no information.
- Meanwhile `composite_short` (3-year percentiles) reads **33 = yellow** today — the
  structurally-adjusted line already disagrees with the headline — and it is **not
  logged to history.csv** (unscoreable) and ignored by band logic.

### 1.5 Alert stream scored

52 alert-log entries in 132 days. Composition: 24 staleness, 15 new-reds, 7 health,
7 new-oranges, 5 improvements — **operational plumbing (31) outnumbers market signal
(22).** Scoring the 22 escalation-class alerts against SPX: 9% were followed by a
≥3% drawdown within a month vs a 14% base rate across all days (n=22 — no power, but
the direction is not flattering); zero ≥5% drawdowns occurred at all. The postmortem
scorer (t7/t14/t30 written back into alert_log) measures the alert against **the
composite itself**, not against the market — self-referential.

Documented alert-fatigue evidence already exists: during the July outage the watchdog
fired priority-1 Pushover daily for 13 days with no action taken (CLAUDE.md gotcha).

### 1.6 External contracts verified against live files

- **`data/latest.json` → tactical_markets_trading bot: live production surface.**
  Bot validated and consumed it yesterday (2026-09-01 log: "MACRO advisory:
  macro_stale_7.2h_treating_as_neutral; increases at x0.5"). Contract verified
  field-by-field clean: schema_version==1, errors empty, composite in range, band,
  regime, weights_hash in allowlist ("2532e380"), run_timestamp naive-local-Chicago.
- **BUT the band gate is dead code since 2026-08-31**: the bot's entry run moved to
  2:45 PM CT; the sidecar publishes 7:30 AM; 7.25h > the bot's 4h staleness window,
  so **every scheduled bot run neutralizes MACRO to a flat 0.5x-on-increases. The
  red→0.0 and orange+high→0.5 rules can never fire.** Nobody documented this
  interaction. (Bot is paper-account; it resumed trading 2026-09-01 after its 08-31
  rebuild; its kill-switch freeze ran 08-03→08-31.)
- **A second consumer is imminent**: the tactical_markets 08-31 redesign builds a
  6:30 AM ET premarket briefing whose Section 1 reads latest.json directly
  (composite, band, regime, shock_type, composite_short*, red_count,
  stale_indicators, warnings, buckets fallbacks) with its own 36h staleness rule,
  and **encodes the naive-local-Central run_timestamp assumption**. The sidecar
  schema is a real two-consumer contract now; fields the bot ignores are about to
  become load-bearing. Cosmetic defect: label/unit strings carry UTF-8-as-cp1252
  mojibake ("10Yâ€“2Y Spread"); no consumer reads labels.
- Nothing else on the machine consumes any output. GitHub Pages + Pushover are
  human-facing only.
- **Manual indicators are dead inputs**: `data/manual_overrides.json` has held
  `repo_stress: 0, iran_trigger: 0` since 2026-04-23 17:30 — never updated once,
  including through the Iran/Hormuz episodes the alert narratives kept citing.
  They contribute constant neutral-50 scores at a combined ~5.4% of composite weight
  and imply a manual-update workflow that does not exist.

### 1.7 Test suite ground truth

- 281 tests; **the suite is time-of-day dependent**: 3 tests in
  `test_alert_controls.py` (TestDebounce escalation + both TestBreadth labels) call
  the real `_in_quiet_hours` and fail whenever pytest runs 22:00–07:00 (quiet window
  suppresses the orange escalation they assert on). Verified failing at 06:41 and
  06:56, and passing 17/17 at 07:00:52 the same morning.
- **`tests/test_ondemand.py` writes to production `output/`**: its `_patched_main`
  patches every side effect of `run_dashboard.main()` *except* `_maybe_refresh_backtest`,
  so the real backtest regenerates `output/backtest_full.csv`, `backtest_subset.csv`,
  `backtest_ic_summary.json` (+ report) with mocked-empty weights — a degenerate
  all-NaN frame over the real artifacts. **This session's own 06:40 pytest run did
  exactly that**, and because `_maybe_refresh_backtest` age-gates on the CSV's mtime,
  the 07:30 production run would have skipped the refresh and rendered NaN garbage
  on the calibration card. Restored before 07:30 by force-regenerating via the
  project's own code path (verified: n_obs 2,263, real ICs). `data/alert_log.jsonl`
  also gets its mtime bumped by the suite (content verified intact).

### 1.8 Code-level audit — state machine bugs and silent-failure inventory

A full read of run_dashboard.py + all of src/ (this session, subagent-assisted;
file:line evidence retained in the audit transcript) found, beyond the above:

**Live state-machine bugs (all verified against current data files):**
- **The health-alert early return saves the *previous* state, not the new one**
  (`alerts.py` health branch calls `_save_state(prev)` then `return 1`). Live
  consequence right now: `data/alert_state.json` holds `composite_band: "red"` +
  six red indicators frozen from 2026-08-31; the 09-01 run's health alert both
  suppressed that day's market alerts *and* froze the dedupe state. Prediction
  registered before the fact: the 09-02 07:30 run will fire a stale
  "COMPOSITE IMPROVED: RED → ORANGE" alert two days after the fact. *(Outcome
  recorded in §4.6.)*
- **`new_state` is rebuilt from a fixed key list that drops `heartbeat_start` and
  `last_health_alert_time`.** So (a) the "31-day" heartbeat re-seeds its start date
  every run and never expires — Ian gets a daily heartbeat ping forever (state file
  confirms `heartbeat_start: "2026-09-01"`), and (b) the health alert's 6-hour
  debounce resets daily.
- **`_load_state()` does raw `json.load` with no error handling** — a truncated
  `alert_state.json` crashes the entire run at step 14.
- **`score_past_alerts` rewrites `data/alert_log.jsonl` whole-file, non-atomically**
  — a crash mid-write destroys the project's only postmortem dataset.
- **Cache-key defect**: `_cache_path` keys on ticker only, not window length. The
  dashboard's calibration card fetches `^GSPC` at `years=2`; under `--no-cache`
  (the documented dry-run) that overwrites the 10-year `yf_XGSPC.json` cache, and
  every run in the next 12h computes `sp500_1m_vol` and `spx_200dma_distance`
  percentiles against a 2-year window. The dry-run corrupts production percentiles.
- **`_publish_to_github` never checks `git add`'s return code**; if either pathspec
  is missing the add fails atomically and the day publishes nothing, reported as
  "dashboard unchanged."
- **`_log_feed_failure` (news.py) calls `_log_alert` with the wrong signature —
  every call raises TypeError, swallowed by `except: pass`.** RSS feed health has
  never been recorded. Related: `--no-news` doesn't gate the alert-path news
  context, which still pulls all 13 feeds + an Anthropic call; and the documented
  "no paid APIs" dry-run makes a fresh Haiku narrative call every time
  (`--no-cache` defeats the narrative cache).
- Brief 17's remediation logging has produced **zero** records in production
  despite 24 staleness alerts (all remediation-eligible `move_index`) — the audit
  trail for the feature is empty.

**Structural divergences that undermine the published numbers:**
- The backtest treats `cnn_fear_greed` as manual-neutral and applies no regime
  weighting — **the "proven skill" ICs come from a materially different model than
  the live one** (whole sentiment bucket constant-50 in backtest).
- Live scoring lets failed indicators keep their full weight (diluting buckets
  toward 50); the backtest *excludes* unavailable indicators and renormalizes —
  the two composites handle missing data oppositely.
- `composite_short_band` comes from score cutoffs while the headline
  `composite_band` comes from trigger counts — two different band rules on the
  same dashboard.
- `alerts.py:404` hardcodes "N/10 buckets" (there are 11); the dashboard footer
  hardcodes "26 individual market indicators" (there are 29) and always says
  "10-year history" (`history_years` is never set).

**Silent-failure classes** (~35 swallowed-exception sites inventoried): whole
dashboard cards vanish without trace on any exception (AI narrative, calendar,
Model Calibration, weight annotations); `load_yaml_safe` turns a malformed YAML
into `{}` (feature silently disappears); TreasuryDirect failures return `[]`;
`triggers` renders `raw=None` as a **green** dot while the indicator contributes
neutral-50 to the score — a broken feed literally shows as "all clear."

**Dead code/data**: `data/latest_serial.json` orphan (no reader/writer);
`t14_composite`/`t30_composite` written, never read; per-indicator `zscore`/
`percentile_short`/`score_short` shipped in the sidecar, rendered nowhere;
`_best_match_url` uncalled; `EIA_API_KEY` unread; 22 vestigial history.csv columns.

---

## Phase 2 — Provenance and methodology autopsy

### 2.1 Threshold provenance: 0 of 29 are data-derived

Full audit of `config/thresholds.yaml` against ROADMAP briefs, BACKTEST_DESIGN, and
all of git history: **five introducing commits, zero tuning commits, ever.** The file
header's "calibrated to roughly 2000–2025 history" has no calibration artifact
anywhere in the repo. Classification: 24 of 29 are round-number judgment calls with
post-hoc tooltip anecdotes ("2008 peaked at 9.0"); 5 have no traceable provenance at
all (sp500_1m_vol, ig_oas, sector_breadth, em_corp_oas, eem_vol); 2 are manual
ordinal scales. Brief 19's own locked design said "after ~2 weeks of live data,
re-check actual percentile placement and tune" — the re-check never ran, and its
indicators are today's pinned reds.

### 2.2 The founding-inversion class of error — found, twice

1. **The one empirical recalibration was silently reverted within hours.** Commit
   `3385de6` (2026-04-23) applied Phase-5 backtest-IC-derived indicator weights
   (vix 0.88, NFCI→0.0, wti→0.0…). Commit `cbb4516` hours later ("Step 0 — restore
   10-bucket config") restored a `.bak` that reverted every one of them to the
   original judgment numbers — while its commit message calls the restored file
   "the 10-bucket **recalibrated** version." No later commit re-applied them; the
   `.bak` was deleted. **Every weight live today is a judgment number, and the record
   claimed otherwise for four months.**
2. **The backtest's cnn_fear_greed placeholder**: the backtest stores raw=0.0
   (pct=50 neutral) for CNN F&G on all 2,263 days; applying the inverted threshold
   to that raw yields "red 100% of history" for anyone who reconstructs bands from
   the CSV — a booby trap for exactly the kind of analysis this session ran (§4.2).

### 2.3 Did the project re-derive what its docs already contained?

Inverse case: the project *built* the machinery (recalibrate.py, per-regime IC,
firing-rate-capable backtest raws) and then never pointed it at its own thresholds.
The instrument existed; the measurement was never taken.

### 2.4 Instrument match

- The feedback loop trusted with "is the model calibrated?" (live rolling IC card)
  has n≈118 in one regime — noise floor far above the plausible effect. Brief 29's
  adequacy gate (≥90 obs) technically passed at n≈110+ but the gate counts
  observations, not regimes; it will happily render a verdict from a single monotone
  rally. Lived exposure calibrates UX; only the 9-year backtest calibrates the edge.
- Composite-level calibration artifacts exist and are honest (backtest IC by horizon,
  band precision/recall) **except** the contaminated stress_index target (§1.3).
- Per-indicator level: no firing rates, no calibration, nowhere.
- The staleness cadences (`series_cadence.yaml`) are the **best-calibrated numbers in
  the repo** — each tuned against observed false-positive rates with evidence inline.
  Proof the team knows how; it was just never applied to the thresholds that drive
  the headline.

### 2.5 Config/doc inconsistencies found (all corrected or queued this session)

1. README.md contained unresolved merge-conflict markers and described a 9-bucket
   model with an EIA key requirement — long obsolete.
2. CLAUDE.md gotcha lists 3 inverted indicators; weights.yaml has 4
   (omits copper_gold_ratio). CLAUDE.md references `data/fetch_cache/`; the real
   path is `data/cache/`.
3. TODO.md carried the stale "watchdog inert — add secrets" banner (§1.2).
4. `series_cadence.yaml` contains orphan `oil_vol` (deleted indicator) and is
   missing entries for vix_term_structure, crack_spread_321, natgas,
   copper_gold_ratio → **those four have no staleness detection at all** (two of
   them are the pinned reds; a silent upstream break would freeze them red forever).
5. tooltips.yaml says "10 buckets" twice (there are 11) and "Brief 10C will use
   this" (shipped 2026-04-25).
6. iran_trigger red threshold is 3 on a 0–2 scale — unreachable by construction.
7. `history.csv` raw_* columns: populated for one day in April, frozen at the old
   indicator universe, never written since — 20+ vestigial columns.
8. `data/latest_serial.json` last written 2026-05-27 (Brief 27 comparison artifact).
9. Brief 26 (regime-weights review): re-review was due 2026-06-20; open and unrun
   2.5 months later. weights.yaml comment still says "target review date
   2026-05-30." The documented disease — a review with no default action.

### 2.6 Transferable methodology rules (numbered, for the rebuild to cite)

1. **A threshold ships with its historical firing rate or it doesn't ship.** Red
   should be rare by construction (target base rates, e.g. red ≤5% of history,
   orange ≤15%); print the rate as a comment next to the number in config.
2. **Never score a signal against a target built from its own inputs.** External
   outcomes only (SPX drawdown, realized forward vol on assets the composite
   doesn't ingest).
3. **Every published number needs one command from log to outcome** — and the
   outcome must be market truth, not the signal's own future value.
4. **Count regimes, not observations, for adequacy.** n=118 in one monotone rally
   is n=1 for validation purposes.
5. **Level-percentile scoring measures regime, not change.** An "early-warning"
   headline must be change-aware (momentum/breadth/hysteresis) or it becomes a
   structural-level meter that pins in shifted regimes (10Y at 4.7% = permanent
   orange).
6. **Any-single-trigger aggregation amplifies the worst-calibrated input.**
   The headline inherits the noise of the noisiest of 29 thresholds; require
   breadth or composite confirmation.
7. **Manual inputs need an owner and a heartbeat** (alert when untouched >N days)
   or they are constants wearing indicator costumes.
8. **A promised follow-up ("re-check in 2 weeks") that isn't scheduled is a wish.**
   Put the date in the doc with a default action, or don't write it.
9. **Scheduled-time couplings between systems must be stated in both systems' docs**
   (the 2:45 PM bot vs 7:30 AM sidecar interaction was documented in neither).
10. **Tests that can touch production paths will eventually corrupt them at the
    worst moment** (06:40, fifty minutes before the daily run). Isolation is a
    tripwire fixture, not a convention.

---

## Phase 4 — Second-thoughts self-audit

(Recorded here; performed before the execution doc was frozen. Phase 3 lives in
[REDESIGN_2026-09-02.md](REDESIGN_2026-09-02.md).)

1. **My first quiet-hours confirmation was wrong and I nearly shipped it.** I
   "re-verified after 07:00" at what was actually 06:55 (mis-tracked elapsed time),
   saw the tests still failing, and briefly retracted the theory. Re-deriving the
   clock from `date` — not from my sense of elapsed time — restored it, and the
   post-07:00 rerun is the recorded proof. Lesson applied from the prompt: re-derive
   any date/duration from the primary source, including your own.
2. **My initial firing-rate table showed cnn_fear_greed red 100% of history — an
   artifact of my own method** (applying live thresholds to the backtest's raw=0.0
   placeholder), not a finding. Excluded and recomputed; the 51%/55% headline
   numbers above are the corrected ones. The same artifact briefly inflated the
   "n=1 raw columns" reading of history.csv — that one survived verification
   (the columns really are vestigial).
3. **The +0.42 live IC is reported as a trend artifact, not as model skill**, with
   effective n and the de-overlap check shown, per rule 4 (§2.6). It must not be
   quoted as "the composite works" — nor, symmetrically, may the +0.51
   drawdown-sign be quoted as "the composite is inverted." Detrending confirms:
   composite 5-day *change* vs forward 1-week return is IC +0.13 (p=0.18, n=105;
   de-overlapped +0.25 on n=21) — statistically nothing survives in either
   direction once the trend is removed.
4. Re-checked priority ordering against live risk: nothing is on fire today
   (scheduler healthy, run 09-02 completed, watchdog armed, bot is paper). The
   binding constraint is signal quality, not reliability — the plan leads with
   calibration, not with the GH-Actions migration.
5. Doc hygiene executed: stale claims corrected inline (TODO watchdog banner,
   CLAUDE.md invert list + cache path, README rebuilt); REDESIGN_2026-09-02.md is
   the ONE canonical execution doc; this file is the frozen session record; no
   dual maintenance (execution doc wins conflicts).

### 4.6 Registered prediction — outcome (added 07:35, same morning)

Predicted at ~07:10 from the frozen-state bug (§1.8), before the fact: the 09-02
07:30 run would fire a stale "COMPOSITE IMPROVED: RED → ORANGE" alert. **Verified
at 07:31:22** — Ian's phone received exactly that ("stress is easing"), reporting
a band transition that actually happened on 09-01 but was masked by the health
alert, bundled with "NEW RED TRIGGERS (1): Copper / Gold Ratio" — an indicator
that has been red ~80% of the live window and is only "new" because the state
freeze dropped it. One Pushover message containing both diagnosed failure modes
(state-freeze staleness + uncalibrated-threshold cry-wolf), delivered while this
assessment was being written. The run itself completed healthy (`run ok` 07:31:35,
composite 39.3, orange) and skipped the backtest refresh because of this
session's 06:45 restore — both as expected (§1.7).

---

## Appendix — commands to reproduce the key numbers

- Reliability calendar + live IC + alert scoring: `scratchpad assess.py` (session
  scratchpad; logic: history.csv daily-first dedup, ^GSPC close-to-close forward
  windows, Spearman, weekly de-overlap).
- Firing rates: apply `src.triggers._evaluate_band` to `output/backtest_full.csv`
  `__raw` columns with `config/thresholds.yaml`, excluding cnn_fear_greed.
- Backtest IC: `output/backtest_ic_summary.json` after
  `run_standard_backtests(load_weights('config/weights.yaml'), env)` +
  `backtest_report.run()`.
- Contract verification: `tactical_markets_trading/src/macro_consumer.py` validate()
  vs live `data/latest.json`; bot log `data/logs/ensemble_20260901.log`.
