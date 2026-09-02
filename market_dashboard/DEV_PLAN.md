# DEV_PLAN — implementation mechanics for REDESIGN_2026-09-02

Scope lives in [REDESIGN_2026-09-02.md](REDESIGN_2026-09-02.md) (it wins conflicts).
This doc adds only the *how*. **Holding for Ian's explicit go.**

---

## Verified contracts (pinned this session — exact, from live files)

**`data/latest.json` → tactical_markets_trading `macro_consumer.validate()`:**
- `schema_version` must equal `1` (int).
- `errors` must be an empty list (any entry → feed invalid; soft conditions belong
  in `warnings`, which the bot ignores).
- `composite` numeric 0–100; `composite_band`, `regime` keys must exist.
- `weights_hash` must be in the bot's allowlist
  (`tactical_markets_trading/data/macro_weights_allowlist.json`, currently exactly
  `["2532e380"]`). **`weights_hash` = MD5 of the raw BYTES of config/weights.yaml,
  first 8 hex chars** (`src/history.py:_weights_hash`). Any byte change — comments
  and whitespace included — invalidates the feed (post-08-31 consequence: permanent
  0.5x advisory, not a hard block).
- `run_timestamp`: ISO, tz-naive, **interpreted as America/Chicago** by the bot;
  the planned premarket briefing (tactical_markets DEV_PLAN) additionally encodes
  the naive-local assumption. Do not switch the publisher to UTC-aware.
- Bot staleness window: 4h from run_timestamp; briefing: 36h.
- Fields about to become load-bearing for the briefing: `composite_short`,
  `composite_short_band`, `shock_type`, `red_count`, `stale_indicators`,
  `warnings`, `buckets.*.indicators.{vix,vix_term_structure}.raw`. Do not prune.
- Known cosmetic defect to fix (R11): label/unit strings are UTF-8-as-cp1252
  mojibake ("10Yâ€“2Y Spread"); no consumer reads labels today.

**Headline band (current, `src/triggers.py:annotate_results`):**
red: `red_count>=3 or composite>=70`; orange: `red_count>=1 or orange_count>=3
or composite>=50`; yellow: `orange_count>=1 or yellow_count>=3 or composite>=30`.
`composite_short_band` uses plain score cutoffs — different rule, same page.

**Watchdog:** keys off the **commit time of `docs/index.html`** in the GitHub repo
(>28h → Pushover). Nothing in this plan changes that path; the publish step and
file name must not move.

**Scheduler:** "Market Stress Dashboard" 07:30 daily (`--publish --heartbeat
--quiet`), PT20M limit; wake task 07:20. Not touched by any phase.

---

## Phase 1 — mechanical repairs (3 commits, on go)

### Commit 1A — test isolation (R1)
- `tests/test_ondemand.py` (~+3): add `patch("run_dashboard._maybe_refresh_backtest")`
  to `_patched_main`'s patch list.
- `tests/test_alert_controls.py` (~+6): `monkeypatch.setattr("src.alerts._in_quiet_hours",
  lambda env: False)` in the 3 time-dependent tests (escalation + 2 breadth).
- `tests/conftest.py` (~+25): autouse tripwire fixture — snapshot mtimes of
  `output/*` and `data/*.{json,jsonl,csv}` at session start, assert unchanged at
  session end; fail loudly naming the offender file.
- **Smoke:** run the full suite; then `ls -l output/ data/` and verify no mtime
  moved. Run once with system clock reality-checked before 07:00 (or with
  `QUIET_HOURS_END` faked) to prove time-independence.

### Commit 1B — alert state machine (R2, R3, R4)
- `src/alerts.py` health branch (~±15): build `new_state` from current scoring
  BEFORE the health check; on health-alert return, save the merged new_state with
  `last_health_alert_time` set. Add `heartbeat_start` and `last_health_alert_time`
  to the `new_state` key list (~+2).
- `src/alerts.py:_load_state` (~+5): try/except JSONDecodeError/OSError → default
  state + `logging.warning`.
- `src/alerts.py:score_past_alerts` (~+4): write to `ALERT_LOG.with_suffix(".tmp")`,
  then `os.replace`.
- Tests (~+60 across `tests/test_alert_controls.py` / new `tests/test_health_state.py`):
  (a) health-alert day → state carries TODAY's band and red list; (b) corrupt
  state file → no crash, default state; (c) heartbeat_start survives a normal run
  and expires after 31 days; (d) atomic rewrite leaves valid JSONL on simulated
  crash (write to tmp asserted).
- **Smoke:** with a stale dashboard copy in a sandbox dir, run send_alerts twice
  within 6h → exactly one health alert (debounce now real).

### Commit 1C — data integrity (R5–R9, R14)
- `src/fetch.py:_cache_path` (~+2): include `years` in the cache filename;
  one-time: existing `yf_*.json` caches invalidate naturally (TTL 12h).
- `run_dashboard.py:_publish_to_github` (~+4): check `git add` returncode, treat
  failure like push failure (log ERROR + Pushover).
- `src/news.py:_log_feed_failure` (~±6): call `_log_alert(title, body, ...)`
  correctly; add 1 test asserting a failed feed produces a log entry.
- `run_dashboard.py` / `src/news.py` (~+6): `get_trigger_news_context` returns ""
  when `ENABLE_NEWS_TRIAGE=false`; `--no-news` also skips `generate_narrative`
  (keeps CLAUDE.md's "no paid APIs" dry-run claim honest — update CLAUDE.md
  gotcha in same commit).
- `config/series_cadence.yaml` (~+8/−1): add `vix_term_structure: daily`,
  `crack_spread_321: daily`, `natgas: daily`, `copper_gold_ratio: daily`
  (all yfinance-daily underlyings; use `daily_lagged` if flaps appear); delete
  orphan `oil_vol`.
- R14 (~investigation + ≤10): instrument `_remediation` block; root-cause zero
  records; fix or remove the dead logging.
- R16 (~+12): `logger.info("step: %s", name)` between main() stages; pass
  `timeout=60` to the Anthropic client in narrative.py/news.py (httpx default
  can hang far past the useful window — the 08-31 hang lived in this segment).
- R17 (~+6): gate `log_run`/`prune_history`/`score_past_alerts` behind the same
  condition as alerts for non-`--ondemand` dry-runs, or add `--dry-run` alias
  for `--ondemand --no-news`; update the CLAUDE.md dry-run gotcha to match.
- **Smoke:** `python run_dashboard.py --no-cache --no-news --no-alerts --quiet`
  → zero Anthropic calls (assert via missing narrative-cache update), and
  afterwards `yf_XGSPC*.json` for years=10 still present alongside years=2 key.

## Phase 2 — measurement honesty (2 commits)

### Commit 2A — R12/R13/R10/R11 + GUT deletions
- `src/history.py:log_run` (~±20): add `composite_short` column; stop carrying
  the 22 vestigial columns (write a one-off migration that archives current
  history.csv to `data/history_pre_migration_2026-09.csv` then rewrites without
  dead columns). Delete `data/latest_serial.json`. Stop writing `t14_composite`/
  `t30_composite` (keep t7); drop the two writer lines + postmortem loop entries.
- `src/dashboard.py` + `src/evaluation.py:ic_summary_dict` (~±30): calibration
  card headline uses `composite_vs_spx_drawdown` only; stress_index shown (if at
  all) with the label "in-family target — inflated by construction". Add the
  backtest-model caveat line ("backtest excludes CNN F&G + regime weights").
  Adequacy: require ≥90 obs AND ≥2 distinct VIX regimes in-window before any
  live verdict; else "Building history".
- Truth-in-labels (R10, ~±10 across `src/alerts.py` L404, `src/dashboard.py`
  footer, `config/tooltips.yaml` ×3, `config/thresholds.yaml` iran red 3→2).
- R11 (~+4): read/write sidecar labels with explicit `encoding="utf-8"` at the
  writer; one-off re-emit fixes stored mojibake next run.
- Tests: sidecar schema test extended (composite_short in history header, t14/t30
  absent from new entries, utf-8 labels round-trip).
- **Smoke:** dry-run; open dashboard; calibration card shows SPX-drawdown ICs
  (1w +0.151 territory) and no 0.7–0.8 stress_index headline. history.csv gains
  the column; sidecar consumers unaffected (no schema_version change — additive
  only). Corrupt a COPY of latest.json (`run_timestamp: "garbage"`) and run the
  bot's `macro_consumer.validate` against it → expect
  `macro_run_timestamp_malformed` (proves the degradation path end-to-end).

### Commit 2B — `src/threshold_report.py` (B1 artifact, ~250 new lines + tests)
- Inputs: `output/backtest_full.csv` `__raw` columns + `config/thresholds.yaml`;
  for **cnn_fear_greed use `data/cache/cnn_fear_greed.json`** (16 months of
  real daily values — the backtest's raw=0.0 placeholder is the booby trap from
  ASSESSMENT §2.2, but the accumulating cache is genuine); exclude only the two
  manual indicators. Report both tails: always-hot (copper_gold 21%, jobless
  15%, cpi 11.5%, cnn 13%) **and never-fired** (ten_year/nfci/
  treasury_auction_stress red = 0% of 2,263 days). Include proposed composite
  score-cutoff recalibration (30/50/70 → base-rate targets) for B2.
- Output: per indicator — current thresholds, historical band firing rates
  (full sample + per-year + live window), and proposed thresholds hitting target
  base rates (red ≤5%, orange ≤15% of days; percentile-derived from the raw
  distribution, judgment overrides marked).
- Writes `output/threshold_report.md` for Ian + prints a proposed
  thresholds.yaml diff. **Applies nothing.**
- **Smoke:** report reproduces this session's numbers (copper_gold red 21% full /
  80% live; crack_spread 4.1%/66%; jobless_claims 15%; ≥1-red days 51% excl-CNN).
- Ian reviews → D2 default applies the diff on 2026-09-16 (Phase 3).

## Phase 3 — semantics changes (design-gated: D1, D2)

### Commit 3A — apply recalibrated thresholds (after D2)
- `config/thresholds.yaml` full regeneration **with firing-rate comments per
  band**. No weights.yaml change → weights_hash stable → bot unaffected.
- **Smoke:** replay bands year-by-year (2018–2026) with new thresholds; print the
  orange-or-worse share per year; expect calm years single-digit %, 2020/2022
  elevated. Live day expectation: with composite 38 and recalibrated commodity
  thresholds, headline should read yellow-or-green — state the actual before
  merging.

### Commit 3B — band redesign (after D1; default option A)
- `src/triggers.py:annotate_results` (~±25): headline = score band of composite,
  +1 level max if red indicators present in ≥2 distinct buckets; one-day
  hysteresis (needs prev band — read from alert_state, already loaded nearby).
  `composite_short_band` unchanged.
- `src/alerts.py` unchanged in logic — inherits saner bands.
- Tests (~+80): table-driven band matrix incl. the 08-31 case and the
  pinned-two-commodity case (→ yellow, not orange). *[Corrected 2026-09-02
  during execution: 08-31 (composite 39.2, reds in 4 buckets) reads ORANGE
  under option A — yellow score band +1 breadth level — not red as this line
  first claimed; escalation is capped at one level by design. Red requires
  composite ≥50 with breadth, the COVID/2022 shape.]*
- **Sidecar semantics note:** `composite_band` distribution changes for both
  consumers. Bot: red→0.0 rule becomes *reachable* again only if D4 chooses
  republish/widen; regardless, red days become rarer and more meaningful.
  Notify tactical_markets docs (one-line PR) same day.
- **Smoke:** replay 2018–2026 headline-band shares before/after; verify
  2026-09-02's headline against the live data and print it in the commit message.

### Commit 3C — alert routing (B3)
- `src/alerts.py` (~±60): route staleness/feed-health/recovery to digest+card
  lanes; push lane keeps band changes, new reds, dashboard-stale, publish-failure.
  Heartbeat expires (already fixed in 1B) and is not re-armed.
- Tests: routing matrix (~+40).
- **Smoke:** simulate a staleness-only day → no push, digest queued; simulate a
  new-red day → push.

## Phase 4 — coordinated decisions (D3, D4, D5, B4)

- **D3 retire manual indicators** (~±40 + config): remove iran_trigger +
  repo_stress from weights.yaml; reweight sentiment (cnn 1.0) and
  funding_liquidity (sofr_spread 1.0); delete their explainers/tooltips/threshold
  blocks; drop `load_manual_overrides` plumbing if nothing remains manual.
  **SWAP-GAP: this changes weights.yaml bytes → new weights_hash → same-day
  append of the new hash to `tactical_markets_trading/data/macro_weights_allowlist.json`
  in the same working session, and only then the first publish.** Also delete the
  stale "2026-05-30" review comment in the same edit (one hash change, not two).
- **B4 regime-review event trigger** (~+15): dashboard-card notice + one push on
  first 5 consecutive high-regime days; remove the calendar-date language.
  (Rides the same weights.yaml edit.)
- **D4/D5**: per Ian's picks; D4 "accept" = documentation-only (one paragraph in
  both projects' CLAUDE/TODO); D5 "delete" = remove `_send_email_fallback` (~−30).

## Swap-time gap hunt (things that break the moment something ships)

1. **weights.yaml byte-sensitivity** (above) — the one genuinely dangerous edit;
   verified: hash covers comments/whitespace. Protocol: hash-change commits are
   paired with the bot allowlist commit, executed before the next 07:30 run.
2. **Watchdog** keys off `docs/index.html` commit time — publish path unchanged
   in every phase; nothing to do.
3. **conftest tripwire (1A) vs legitimate artifact tests** — tests that *should*
   write use tmp_path already; tripwire only guards real paths.
4. **history.csv migration (2A)** — `load_history(days=90)` and momentum/shock
   readers tolerate the slimmer schema (they select columns by name); the
   archived pre-migration file preserves the audit trail.
5. **Band redesign (3B) vs alert dedupe state** — first run after deploy sees a
   band drop (orange→yellow likely); the improvement alert will fire once,
   correctly annotated by 1B's fixed state. Acceptable; note in commit.
6. **Removing t14/t30 (2A)** — `tests/test_postmortem.py` asserts them; update
   the same commit. `get_postmortem_stats` reads only t7 — unaffected.

## Gate audit — human steps that remain

Verified credentials/infrastructure this session: gh CLI authenticated (secret
list + run list worked); Pushover repo secrets present; Twilio env vars present
(untested channel — exercised only if Pushover fails); FRED/Anthropic keys in
.env and working daily. **No credential gaps block any phase.**

Remaining genuinely-human gates, all one word each: **the go** (Phase 1),
**D1–D5** (defaults fire 2026-09-16 per REDESIGN). Everything else here is
executable without Ian.

## Deliberately not doing (implementation altitude)

- No fetcher abstraction layer / no async rewrite — ThreadPoolExecutor stays.
- No schema_version bump — all sidecar changes are additive or cosmetic.
- No new YAML files except none (threshold_report writes to output/, not config/).
- No backtest-engine changes (divergence labeled, not fixed — REDESIGN Rejected #6).
- No CI for the test suite beyond the existing tests.yml.
- No refactor of dashboard.py's 1,300 lines — edits stay surgical.
- No versioning of thresholds.yaml beyond git + the firing-rate comments.

## Commit-point summary

| Phase | Commits | Risk | Rollback |
|---|---|---|---|
| 1 | 1A test-iso · 1B alert-state · 1C data-integrity | none→low | revert commit |
| 2 | 2A honesty+guts · 2B threshold_report | low (display + additive) | revert |
| 3 | 3A thresholds · 3B bands · 3C routing | medium (semantics) | config/logic revert, one commit each |
| 4 | D3+B4 paired w/ allowlist · D4 · D5 | medium (cross-repo) | paired revert both repos |
