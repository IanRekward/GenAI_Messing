# DEV_PLAN — Premarket Briefing implementation plan

**Status: implementation mechanics for [REDESIGN_2026-08-31.md](REDESIGN_2026-08-31.md). Scope and rationale live there and in [fable_plan.md](fable_plan.md); this doc adds only the how — file-by-file changes, verified contract shapes, smoke tests, commit points. If this doc and REDESIGN conflict, REDESIGN wins. Code execution still awaits Ian's explicit go.**

Written 2026-09-01 after re-verifying every sibling contract file against its live contents. **Revised 2026-09-02 after a review pass found the pins had already drifted** — the 9/1–9/2 sibling sessions changed both MACRO and the bot (see the drift note under Verified contracts). Pins below are snapshots, not promises; re-verifying them is the first action of Phase 2. **Second 9/2 fold-in from a fresh review:** freeze exemption for schema-drift repairs (Phase 3), equity-exposure decision moved into the go conversation (Preconditions), trail-pct read-from-disk check (2b), heartbeat rebase-retry (1b).

---

## Preconditions before any code

*(Revised 2026-09-01: gates 2 and 3 dissolved — heartbeat redesigned onto existing infrastructure, Phase −1 diagnosis done read-only. One gate remains.)*

1. **Ian's go on REDESIGN_2026-08-31.md** — ~~not yet recorded anywhere~~ **GIVEN 2026-09-02** ("begin coding from the dev plan"). The go-conversation decision on `briefings.jsonl` public exposure was settled the same day: **log & track as-is** (paper account, same class as what `theses.jsonl` already publishes).
2. ~~healthchecks.io account~~ **Dissolved.** Heartbeat redesigned to GitHub Actions + existing Pushover (see Phase 1b) — no new accounts. One residual step: `gh secret set PUSHOVER_TOKEN` / `PUSHOVER_USER` on `IanRekward/GenAI_Messing` (gh is authenticated with the needed scopes; the automated attempt was permission-blocked as a credential upload, so it needs one interactive approval at Phase-1 time).
3. ~~Phase −1 bot health session~~ **Diagnosis done 2026-09-01, read-only** (see Phase −1 findings below). Residual items are a decision and a hardware check, not code — they don't block MICRO phases.

## Phase −1 findings (2026-09-01, read-only — supersedes the "separate session" framing)

- **Account is paper — CONFIRMED:** bot `.env` has `ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2`. The "verify" flag is resolved.
- **The bot's watchdog is NOT broken — exit 1 is its alert path working.** `watch_trading.py` is alert-only by design (bot repo's own fable_plan §4.6): on a missed cycle it sends "Trading bot MISSED" to Pushover and exits 1. LastResult=1 on 8/31 = detected + alerted same day. The 8/31 assessment's "bot watchdog is the failing component" framing was wrong (corrected inline in fable_plan/REDESIGN).
- **8/31 missed-cycle root cause: machine slept through the 2:30 PM wake task.** Woke 4:47 PM CT (5:47 ET, post-close); the catch-up entry run correctly logged "Market closed — ensemble cycle skipped" and exited 0 without writing a heartbeat. `-WakeToRun` didn't fire — power-state issue (lid/battery/wake-timers), same shared-fate class MICRO's off-machine heartbeat covers.
- **The 8/4–8/11 aborts were a morning DNS race** (both Alpaca and Pushover unresolvable at the 8:35 wake — the failure alert itself couldn't send). The bot already self-mitigated by moving to 2:45 PM entries with a `dns wait` preflight.
- **Residual, genuinely Ian's:** (a) ~~the kill-switch reset decision~~ *resolved — live files on 9/2 show `entry_ok: true` and entries resumed 9/1 (presumably the bot-repo session); the pending-queue machinery below keeps the general case*; (b) check Windows wake-timer/power settings so the 2:30 PM wake fires from sleep; (c) discussion item: TQQQ trail has no resting stop order (evaluated only at the daily run).
- Division of labor now clean: bot watchdog covers "bot missed while machine healthy later"; MICRO's off-machine heartbeat covers "machine dark all day"; the briefing covers "human decision pending" (the kill-switch episode ran 8/3→9/1 unreviewed — the instance closed, the oversight gap it proves stands).

---

## Verified contracts (re-read from live files 2026-09-01; drift-checked 2026-09-02)

The redesign doc sketched these from memory; the real shapes differ in two places that matter, so they're pinned here. All reads are defensive: missing file or missing key → "unknown" in the briefing line + a schema-drift warning, never a crash.

**Drift observed 2026-09-02 — one day after pinning.** The bot pivoted to a `target_state` architecture and the kill switch was reset (`entry_ok: true`, entries resumed 9/1; a new `cash_sleeve_sgov` strategy appears in `trades.jsonl` with no `strategy_state_*` file of its own). `last_successful_run.json` lost `regime` and `active_strategies`, gained `mode`/`executed_order_count`/`data_source`, and the bot now completes ~19:45 UTC (2:45 PM entries), not ~13:35. MACRO gained an afternoon sidecar run (second `latest.json` write ~18:50 CT) plus new top-level fields; everything section 1 reads still exists. The schema-drift guard designed below proved necessary before a line of it was written. Consequence, folded into Phase 2: **re-run this verification pass as the first action of the Phase-2 session.**

### `market_dashboard/data/latest.json` (section 1 — regime)
Top-level fields used: `run_timestamp` (**tz-naive local time**, machine is CT — compare against naive local now, not UTC), `composite`, `composite_band`, `composite_short`, `composite_short_band`, `regime`, `shock_type`, `red_count`, `stale_indicators`, `errors`, `warnings`. Has `schema_version: 1`.
Written daily ~7:30 CT — i.e. **after** the 6:30 ET briefing — and, since the 9/2 sidecar, again ~18:50 CT, so the 6:30 read sees state ~12h old on sidecar days, ~22h otherwise. Staleness threshold 36h covers both and is safe on Mondays: publish commits confirmed 7 days/week including weekends. >36h → `⚠ MACRO STALE (Xh)`.
Bonus discovered: `buckets.equity_volatility.indicators.vix.raw` and `.vix_term_structure.raw` carry a day-old VIX level and VIX/VIX3M ratio — a zero-new-dependency fallback for the 2b tape section if yfinance misbehaves.

### `tactical_markets_trading/data/last_successful_run.json` (section 2 — bot health)
Live shape as of 9/2: `completed_at` (tz-aware UTC), `mode`, `equity`, `open_position_count`, `executed_order_count`, `had_execution_failures`, `entry_ok`, `entry_gate_reason`, `data_source`. (`regime` and `active_strategies` existed in the 9/1 pin and are gone — see drift note.)
**Correction to REDESIGN:** equity lives *here*, not in `account_state.json`. Everything section 2 needs except peak is in this one file.
**Freshness (revised 9/2 — the fixed >30h threshold was wrong):** the bot writes only on trading-day cycles, so hours-based math false-⚠s every Monday (Fri ~19:45 UTC → Mon 6:30 ET ≈ 63h) and worse after holiday weekends (~87h) — a guaranteed weekly false alarm that would wreck scorer precision and train the reader to ignore ⚠. Rule instead: ⚠ when `completed_at`'s ET date predates the most recent past trading day, reusing the weekend/holiday logic already in `run_tactical.py`. Verify at go time whether a skipped weekend cycle rewrites the file (the filename argues it doesn't).

### `tactical_markets_trading/data/account_state.json`
Only `peak_equity`, `peak_timestamp`, `last_updated`. Used solely for drawdown: `(equity − peak_equity) / peak_equity`.

### `tactical_markets_trading/data/strategy_state_*.json` (section 3, phase 2b)
- `..._trend_leveraged_tqqq.json`: `in_position`, `entry_price`, `entry_time`, `position_peak_price`, `stopped_out`.
- `..._trend_following_spy_200d.json`: `in_position`, `entry_price`, `entry_time` — **no peak field** (exit is MA-based, not trailing).
- `..._sector_momentum_top3_monthly.json`: `last_rebalance_month`, `current_holdings` (list of tickers).
- `cash_sleeve_sgov` (new 9/1) has **no state file** — whether section 3 should show it is a question for the Phase-2 re-verify, not an assumption.

### Bot logs (scorer + backlog)
`trades.jsonl`, `drift_log.jsonl`, `shadow_book.jsonl`, `failed_alerts.jsonl`, `reconciler_log.jsonl` — all confirmed present in `tactical_markets_trading/data/`.

### Record correction (2026-09-01, from `trades.jsonl`)
**The kill switch tripped 2026-08-03, not ~June 5.** `entry_gate_reason`'s "last winner 2026-06-05" is the last winner's exit date; the five consecutive losses closed 7/1 (XLE −$689), 7/1 (XLY −$346), 7/16 (TQQQ −$1,251), 7/23 (TQQQ −$577), **8/3 (XLI −$122)**. Entries kept flowing until then (TQQQ 7/22 + 7/27, XLV 8/3). Detection latency was ~28 days (8/3 → 8/31), not the 87 days fable_plan.md Part V headlines — the thesis (oversight gap is real) stands, the number does not. Corrected inline in fable_plan/REDESIGN; consequences for the pending-queue design below.
Also observed: post-May TQQQ trades carry `stop_order_id: null` — the trailing stop is **evaluated at the daily 14:45 run, not a resting order**. An intraday crash blows through the trail until the next run; that's a Phase −1 discussion item, and it changes the wording of the 2b proximity line.

---

## Phase 1 — repairs (~1 session, ships independently, old signal keeps running)

### 1a. yfinance retry — `src/sector_rotation.py`
Wrap the `yf.download` call: 3 attempts, 60s sleep between, raise on final failure (existing error path in `run_tactical.py` already logs it). ~10 lines, inline loop, no helper module — the function retires in Phase 2 anyway; 2b builds its own quote fetch.

### 1b. Heartbeat — GitHub Actions dead-man's switch *(redesigned 2026-09-01: healthchecks.io needed a new account = Ian's intervention; this version rides infrastructure that already exists and is proven)*

Building blocks, all verified: `gh` authenticated as IanRekward with `repo`+`workflow` scopes; push from scheduled tasks proven by market_dashboard's daily 7:33 publish commits (months of history); Pushover working; the tactical task fires daily with the code handling weekends/holidays.

**Machine side (~12 lines in `run_tactical.py`):** on every completed invocation — weekend/holiday early-returns included — write an ISO timestamp to `_genai_tmp/tactical_markets/data/heartbeat.txt`, then `git add/commit/push` it (message `tactical heartbeat YYYY-MM-DD`, specific path staged, never `-A`). On push rejection, one retry: `git pull --rebase --autostash`, push again *(added 9/2 — a session that leaves `_genai_tmp` diverged from origin would otherwise turn every subsequent 5:30 CT push into a false alarm until someone notices; `--autostash` covers the dirty-worktree case too)*. A push that still fails after the retry = missing heartbeat = alert, which is then correct behavior. Timestamp only, no briefing content — the repo is **public**, so the daily commit exposes nothing new (`briefings.jsonl` keeps syncing manually at session commits; flag to Ian someday: it will contain paper-account equity, same class as what `theses.jsonl` already publishes).

**GitHub side — `.github/workflows/tactical-heartbeat.yml` (~30 lines):** `schedule:` crons at 11:30, 12:30, and 13:30 UTC daily (in EST the 11:30 firing lands 6:30 ET and exits quietly, and GH drops scheduled runs entirely under load — the third cron keeps two effective checks year-round); the job computes current ET, exits quietly unless it's past ~7:15 ET, then checks the heartbeat by **reading `heartbeat.txt`'s content at HEAD** — alert if its ISO timestamp isn't today (ET). File content, not commit-date parsing: committer timezones can't lie. Alert = one `curl` to Pushover using `secrets.PUSHOVER_TOKEN`/`PUSHOVER_USER`. Because the machine pings 7 days/week, the Action needs **zero** weekend/holiday logic. Known trade-offs, accepted: GH Actions cron jitter (10–40 min typical) means the alert may land 7:30–8:15 ET rather than 7:15 sharp — hours ahead of the bot's afternoon entry window; a missing heartbeat may alert twice as later crons re-check — a dead machine deserves two pings.

**Secrets staging:** `gh secret set PUSHOVER_TOKEN` / `PUSHOVER_USER` -R `IanRekward/GenAI_Messing`, values piped from `tactical_markets/.env`. Attempted 2026-09-01; blocked by the permission classifier as a credential upload — retry in the interactive Phase-1 session (one approval) or Ian runs the two commands.

**Fallback if Ian prefers fewer moving parts:** the original healthchecks.io design (5-line ping, 3-minute account, no repo commits, no cron jitter) remains valid — his call at go time; the plan defaults to the zero-intervention version per his 2026-09-01 request.

**Smoke:** one full `python run_tactical.py` off-schedule (accept the duplicate log line — log-every-run discipline covers it) → confirm the heartbeat commit landed on GitHub; repeat once with `_genai_tmp` deliberately one commit behind origin plus an unstaged scratch edit → confirm the rebase-retry path pushes clean; give the workflow a `workflow_dispatch` trigger with a `force_alert` input and dispatch it once via `gh workflow run` → test Pushover arrives on phone.

**Commit:** `tactical_markets: phase 1 repairs — yfinance retry + GH Actions heartbeat`

---

## Phase 2 — briefing v1 core, sections 0–2 (~1–2 sessions, one commit, no 6:30 gap)

### New: `src/briefing.py` (~150 lines)

Layout, top to bottom:

- **Paths:** sibling roots derived as `BASE.parent / "market_dashboard"` and `BASE.parent / "tactical_markets_trading"` (BASE = repo parent dir). Files-on-disk, read-only, no imports.
- **`read_json(path) -> dict | None`** — one defensive reader (missing/corrupt → None). One function, used four times; this abstraction earns its place.
- **`regime_line(macro) -> tuple[str, dict]`** — returns the display line and the snapshot fields (`regime`, `composite_band`, `composite`). Staleness per contract section above.
- **`bot_lines(run, account) -> tuple[list[str], dict]`** — freshness, `entry_ok`/`entry_gate_reason`, `open_position_count`, equity + drawdown vs peak, `had_execution_failures`. Snapshot fields: `entry_ok`, `entry_gate_reason`, `open_position_count`, `equity`, `drawdown_pct`, `bot_completed_at`, `mode` — `mode` added 9/2 because the bot just demonstrated it can pivot architectures mid-hold, and that's exactly the kind of delta this console exists to surface.
- **Delta + pending engine**, state in `data/briefing_state.json`:
  ```json
  {"date": "2026-09-01",
   "snapshot": {"regime": "mid", "composite_band": "orange", "entry_ok": false, ...},
   "pending": {"kill_switch_reset": {"first_seen": "2026-08-03", "desc": "kill-switch reset"}}}
  ```
  - **Deltas** = field-by-field compare of today's snapshot vs stored: kill switch tripped/cleared (`entry_ok` flip), regime change, band change, position count change, drawdown crossing −5%/−10%, bot run missed (`bot_completed_at` unchanged across a trading day). First run ever → "first briefing — no deltas".
  - **Pending queue** = states requiring a human decision, currently exactly one derivation: `entry_ok == false` → item `kill_switch_reset`. Age = days since `first_seen`. Seeding on first observation: derive the **trip date from bot `trades.jsonl`** — walk closed trades by `exit_time_actual`, find the last `pnl_dollars > 0`, trip date = exit date of the 5th consecutive loss after it (~10 lines); fallback = observation date. Do **not** seed from the "last winner" date in `entry_gate_reason` — that's the last winner, not the trip, and overstates the pending age 3× on the 8/3 episode (see record correction above). **Fragility, noted 9/2:** exits keep closing after entries stop, and a post-trip *winner* (e.g. the XLV +$546 that closed 9/1) moves "last winner" past the trip — the walk then finds no 5-loss streak. So: sanity-bound the derivation (result must be ≤ observation date with a full 5-loss streak found), take the fallback without ceremony otherwise, and put to Ian the clean fix — **the bot publishing its own trip timestamp** — as a bot-side files-on-disk contract addition (his call, never assumed here). Item auto-clears when `entry_ok` flips true (and emits a "cleared" delta).
  - Unchanged day compresses to one calm line: `No changes. ⚠ pending 29d: kill-switch reset.`
- **`build_briefing(now_et) -> dict`** — assembles message (section 0 first, then regime, then bot; target ≤8 lines), returns `{"message", "snapshot", "deltas", "pending", "warnings"}` where `warnings` carries each ⚠ with its trigger values (rule 4 — scorer food). Order pinned (9/2 — the earlier wording was ambiguous): build → log → push → **save state only after a successful push**. A failed push leaves state unsaved, so today's deltas re-surface tomorrow instead of being marked reported-but-unseen; the log line still records them with `pushover_sent: false`.

### Changed: `run_tactical.py`
- `from src.briefing import build_briefing` replaces the `sector_rotation` import; drop `UNIVERSE`/`THRESHOLDS`.
- Log target becomes `data/briefings.jsonl`, one line per run: `{"signal_type": "premarket_briefing", "as_of", "message", "snapshot", "deltas", "pending", "warnings", "pushover_sent"}`. Error days still log (`"error": ...`). `theses.jsonl` freezes as history, stays git-tracked.
- Briefing always pushes (there is no "no signal" day anymore — an all-calm briefing is one line). Holiday/weekend gates and heartbeat unchanged.

### Changed: `watch_tactical.py` — **gap in REDESIGN, caught here**
It checks `theses.jsonl` for a today-entry. Left alone, it would fire "Tactical Markets MISSED" every day after the swap. Point it at `briefings.jsonl` in the same commit — and close a second blindness while in there (9/2): today it counts **any** today-entry as success, `pushover_sent` unread, error entries included. Under always-push, a Pushover outage would mean briefing logged, heartbeat green, watchdog happy, phone dark — a silent miss. New rule: alert unless a today-entry exists with `pushover_sent: true`.

### Retired: `src/sector_rotation.py` → `research/sector_rotation.py`
`git mv` so the production `src/` contains only what runs. `config/universe.yaml` + `thresholds.yaml` stay put (research still references them; zero risk in place).

### New: `score_briefings.py` (repo root, ~60–80 lines)
Rule 4: ships in the same commit as v1, not after. Reads `briefings.jsonl` + bot `trades.jsonl` + state files; one command, prints:
- per-⚠-type counts and current ages (kill-switch pending age, stale counts, missed-run count);
- **precision**: ⚠ lines followed within 3 days by their flagged event (v1-core events: kill-switch state change, bot-run resumed/stopped);
- **recall**: events with no prior-day ⚠.
Proximity-warning scoring (stop hits, MA crosses) lands with 2b when those lines exist. Skeleton prints "n/a" for empty categories rather than crashing on day 1.

### Docs, same commit
- CLAUDE.md locked-scope table: replace "Week 1 signal: sector rotation only" row with the briefing scope; note the gut per REDESIGN.
- TODO.md status paragraph: momentum retired, briefing v1 live, two-week read starts.

**Smoke:** (1) `python -c "from src.briefing import build_briefing; print(build_briefing(...)['message'])"` against the live sibling files — all sections render; an empty pending queue is the legitimate result while `entry_ok` is true *(rewritten 9/2 — the original expected the kill-switch ⚠ "on current data", which the 9/1 reset made unsatisfiable)*; (2) the kill-switch path via fixture: scratch copies of `last_successful_run.json` with `entry_ok: false` + the live `trades.jsonl` → pending line appears with age from the **derived trip date**, not the "last winner" date, and the fallback engages cleanly when the streak walk finds nothing; (3) hand-corrupt a copied `last_successful_run.json` in scratch and confirm "unknown" lines, not a crash; (4) one full run with a real push, verify on phone + one well-formed `briefings.jsonl` line; (5) `python score_briefings.py` runs clean on one day of data.

**Commit:** `tactical_markets: phase 2 briefing v1 — health console ships, momentum signal retires`

---

## Phase 2b — sections 3–4, best-effort quotes (~1 session, separate commit)

Additions to `src/briefing.py` only. Governing rule: **a failed quote drops the line, never the briefing** — every function here returns `list[str]` that may be empty.

- **`quotes(tickers) -> dict[str, float] | None`** — yfinance with the Phase-1 retry pattern (shorter backoff, 2×15s — the 6:30 slot can't absorb 3×60s twice); premarket via `Ticker.fast_info` where available, else prior close and say so.
- **Section 3 — flip proximity:**
  - TQQQ: trailing stop = `position_peak_price × (1 − TRAIL_PCT)`. **First action of this phase (9/2): check whether the bot exposes its trail pct anywhere on disk** — config file, state file, `last_successful_run.json` — and read it if so; files-on-disk reads are the sanctioned integration path and a read eliminates the drift risk entirely. Only if it's genuinely not on disk: `TRAIL_PCT = 0.05` hardcoded mirroring the bot's config — provenance comment required (rule 1), and a schema-drift risk if the bot ever changes it. ⚠ when price within 2% of stop; `stopped_out: true` → plain status line. Word the line as *"trail level $X (evaluated at bot's 14:45 run)"* — the stop is decision-time, not a resting order (see record correction), and the briefing must not imply otherwise.
  - SPY: distance to 200d and 50d MA (daily history download, 1 call); ⚠ within 2% of a cross.
  - Sector sleeve: `current_holdings` listed once, no proximity math (monthly cadence).
- **Section 4 — overnight tape:** SPY/QQQ gap vs prior close, flag |gap| ≥ 1%; VIX last close + 5d change (no premarket exists). Fallback if quotes fail: day-old `vix.raw` / `vix_term_structure.raw` from MACRO's `latest.json`, labeled `(yday)`.
- Scorer: add proximity precision/recall (⚠ stop/MA line followed within 3d by actual stop-out / cross, from bot `trades.jsonl` + prices).

**Smoke:** run with network cable pulled (or a monkeypatched failing `quotes`) → sections 0–2 still deliver.

**Commit:** `tactical_markets: phase 2b briefing sections 3–4 — flip proximity + overnight tape, best-effort`

---

## Phase 3 — the two-week read (no code)

Clock starts the first live 6:30 briefing morning. Ends +14 calendar days.

**Freeze exemption, defined up front (9/2):** the freeze binds features, not observability repairs. The contract pins drifted within one day of being written — assume the bot drifts again mid-read. If sibling schema drift breaks a section, restoring an existing line to accuracy is a **repair**: it ships immediately, gets its own commit, and is noted in that day's `briefings.jsonl` entry. New lines, sections, or thresholds stay frozen. Without this rule, a mid-read drift leaves the briefing printing "unknown" for two weeks and the read's verdict measures the drift, not the concept.

Then the sunset defaults from REDESIGN apply mechanically:
- default = **alert-only mode** unless Ian affirmatively opts into the daily push;
- 8 weeks with zero acted-on ⚠ lines → default = park the project;
- backlog picks (weekly digest is the promoted candidate) only after the read.

---

## Deliberately not in this plan

Everything in REDESIGN's rejected list, plus these implementation-level ones: no `src/market_data.py` abstraction (two call sites, different needs), no schema versioning on the state file (one reader, one writer, same repo), no pytest scaffolding (inline smoke runs per CLAUDE.md — revisit only if 2b's quote logic grows branches), no backfill of `briefings.jsonl` from `theses.jsonl` (different products; history stays where it is).

## Sequencing summary

| Order | What | Size | Gate |
|---|---|---|---|
| 0 | Ian's go (the only remaining gate; kill switch reset 9/1 per live files — that decision is off the table) | one word | **given 9/2** |
| 1 | Phase 1 repairs: retry + GH-Actions heartbeat (incl. secrets, one approval) | ~60 lines | go |
| 2 | Phase 2: **re-verify contracts first**, then briefing core + retire + scorer + docs | ~250 lines | go |
| 3 | Phase 2b quotes sections | ~80 lines | phase 2 live |
| 4 | Two-week read → sunset defaults | none | phase 2 live |
