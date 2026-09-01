# DEV_PLAN — Premarket Briefing implementation plan

**Status: implementation mechanics for [REDESIGN_2026-08-31.md](REDESIGN_2026-08-31.md). Scope and rationale live there and in [fable_plan.md](fable_plan.md); this doc adds only the how — file-by-file changes, verified contract shapes, smoke tests, commit points. If this doc and REDESIGN conflict, REDESIGN wins. Code execution still awaits Ian's explicit go.**

Written 2026-09-01 after re-verifying every sibling contract file against its live contents.

---

## Preconditions before any code

1. **Ian's go on REDESIGN_2026-08-31.md** — not yet recorded anywhere. Hard gate.
2. **Phase −1 (bot repo health session)** ideally happens first — kill switch blocking entries **since 2026-08-03** (see record correction below), bot watchdog LastResult=1, state stale since 8/28. Separate session in `tactical_markets_trading`. Not a hard dependency for MICRO code (briefing v1 will surface the kill switch on its first morning either way), but it's the live risk.
3. **healthchecks.io account + check URL** — manual browser step (free tier). Ian creates one check, schedule "every weekday", grace period so the alert fires ~7:15 ET if no ping. URL goes in `.env` as `HEALTHCHECKS_URL`. Phase 1 code degrades to a no-op if the var is unset, so code can ship before the account exists.

---

## Verified contracts (re-read from live files 2026-09-01)

The redesign doc sketched these from memory; the real shapes differ in two places that matter, so they're pinned here. All reads are defensive: missing file or missing key → "unknown" in the briefing line + a schema-drift warning, never a crash.

### `market_dashboard/data/latest.json` (section 1 — regime)
Top-level fields used: `run_timestamp` (**tz-naive local time**, machine is CT — compare against naive local now, not UTC), `composite`, `composite_band`, `composite_short`, `composite_short_band`, `regime`, `shock_type`, `red_count`, `stale_indicators`, `errors`, `warnings`. Has `schema_version: 1`.
Written daily ~7:30 CT — i.e. **after** the 6:30 ET briefing, so the briefing always reads *yesterday's* MACRO state (~22h old at read time). Staleness threshold 36h accommodates this; >36h → `⚠ MACRO STALE (Xh)`.
Bonus discovered: `buckets.equity_volatility.indicators.vix.raw` and `.vix_term_structure.raw` carry a day-old VIX level and VIX/VIX3M ratio — a zero-new-dependency fallback for the 2b tape section if yfinance misbehaves.

### `tactical_markets_trading/data/last_successful_run.json` (section 2 — bot health)
`completed_at` (tz-aware UTC), `regime`, `equity`, `active_strategies`, `open_position_count`, `had_execution_failures`, `entry_ok`, `entry_gate_reason`.
**Correction to REDESIGN:** equity lives *here*, not in `account_state.json`. Everything section 2 needs except peak is in this one file. Bot completes ~13:35 UTC, so at 6:30 ET the file is normally ~21h old; freshness ⚠ threshold: >30h.

### `tactical_markets_trading/data/account_state.json`
Only `peak_equity`, `peak_timestamp`, `last_updated`. Used solely for drawdown: `(equity − peak_equity) / peak_equity`.

### `tactical_markets_trading/data/strategy_state_*.json` (section 3, phase 2b)
- `..._trend_leveraged_tqqq.json`: `in_position`, `entry_price`, `entry_time`, `position_peak_price`, `stopped_out`.
- `..._trend_following_spy_200d.json`: `in_position`, `entry_price`, `entry_time` — **no peak field** (exit is MA-based, not trailing).
- `..._sector_momentum_top3_monthly.json`: `last_rebalance_month`, `current_holdings` (list of tickers).

### Bot logs (scorer + backlog)
`trades.jsonl`, `drift_log.jsonl`, `shadow_book.jsonl`, `failed_alerts.jsonl`, `reconciler_log.jsonl` — all confirmed present in `tactical_markets_trading/data/`.

### Record correction (2026-09-01, from `trades.jsonl`)
**The kill switch tripped 2026-08-03, not ~June 5.** `entry_gate_reason`'s "last winner 2026-06-05" is the last winner's exit date; the five consecutive losses closed 7/1 (XLE −$689), 7/1 (XLY −$346), 7/16 (TQQQ −$1,251), 7/23 (TQQQ −$577), **8/3 (XLI −$122)**. Entries kept flowing until then (TQQQ 7/22 + 7/27, XLV 8/3). Detection latency was ~28 days (8/3 → 8/31), not the 87 days fable_plan.md Part V headlines — the thesis (oversight gap is real) stands, the number does not. Corrected inline in fable_plan/REDESIGN; consequences for the pending-queue design below.
Also observed: post-May TQQQ trades carry `stop_order_id: null` — the trailing stop is **evaluated at the daily 14:45 run, not a resting order**. An intraday crash blows through the trail until the next run; that's a Phase −1 discussion item, and it changes the wording of the 2b proximity line.

---

## Phase 1 — repairs (~1 session, ships independently, old signal keeps running)

### 1a. yfinance retry — `src/sector_rotation.py`
Wrap the `yf.download` call: 3 attempts, 60s sleep between, raise on final failure (existing error path in `run_tactical.py` already logs it). ~10 lines, inline loop, no helper module — the function retires in Phase 2 anyway; 2b builds its own quote fetch.

### 1b. Heartbeat — `run_tactical.py`
```python
def ping_heartbeat(ok: bool = True) -> None:
    url = os.environ.get("HEALTHCHECKS_URL", "")
    if not url:
        return
    try:
        requests.get(url if ok else url + "/fail", timeout=10)
    except Exception:
        pass
```
Call `ping_heartbeat()` on **every completed invocation — weekend and holiday early-returns included** — and `ping_heartbeat(ok=False)` in the error path (labeled alert beats silence-then-alert). Rationale: the heartbeat monitors *machine + scheduler + script alive*, not *signal published*; the scheduled task fires daily (verified via `schtasks` — the code, not the trigger, handles weekends/holidays), so pinging every run lets healthchecks use a simple 1-day period with grace to ~7:15 ET and eliminates false alerts on weekday NYSE holidays (Labor Day 9/7 is the first one the alternative would have tripped on).

**Smoke:** `python -c` invoking `ping_heartbeat` with a test URL; one full `python run_tactical.py` off-schedule (accept the duplicate log line — log-every-run discipline covers it).

**Commit:** `tactical_markets: phase 1 repairs — yfinance retry + healthchecks heartbeat`

---

## Phase 2 — briefing v1 core, sections 0–2 (~1–2 sessions, one commit, no 6:30 gap)

### New: `src/briefing.py` (~150 lines)

Layout, top to bottom:

- **Paths:** sibling roots derived as `BASE.parent / "market_dashboard"` and `BASE.parent / "tactical_markets_trading"` (BASE = repo parent dir). Files-on-disk, read-only, no imports.
- **`read_json(path) -> dict | None`** — one defensive reader (missing/corrupt → None). One function, used four times; this abstraction earns its place.
- **`regime_line(macro) -> tuple[str, dict]`** — returns the display line and the snapshot fields (`regime`, `composite_band`, `composite`). Staleness per contract section above.
- **`bot_lines(run, account) -> tuple[list[str], dict]`** — freshness, `entry_ok`/`entry_gate_reason`, `open_position_count`, equity + drawdown vs peak, `had_execution_failures`. Snapshot fields: `entry_ok`, `entry_gate_reason`, `open_position_count`, `equity`, `drawdown_pct`, `bot_completed_at`.
- **Delta + pending engine**, state in `data/briefing_state.json`:
  ```json
  {"date": "2026-09-01",
   "snapshot": {"regime": "mid", "composite_band": "orange", "entry_ok": false, ...},
   "pending": {"kill_switch_reset": {"first_seen": "2026-06-05", "desc": "kill-switch reset"}}}
  ```
  - **Deltas** = field-by-field compare of today's snapshot vs stored: kill switch tripped/cleared (`entry_ok` flip), regime change, band change, position count change, drawdown crossing −5%/−10%, bot run missed (`bot_completed_at` unchanged across a trading day). First run ever → "first briefing — no deltas".
  - **Pending queue** = states requiring a human decision, currently exactly one derivation: `entry_ok == false` → item `kill_switch_reset`. Age = days since `first_seen`. Seeding on first observation: derive the **trip date from bot `trades.jsonl`** — walk closed trades by `exit_time_actual`, find the last `pnl_dollars > 0`, trip date = exit date of the 5th consecutive loss after it (~10 lines); fallback = observation date. Do **not** seed from the "last winner" date in `entry_gate_reason` — that's the last winner, not the trip, and overstates the pending age 3× on current data (see record correction above). Item auto-clears when `entry_ok` flips true (and emits a "cleared" delta).
  - Unchanged day compresses to one calm line: `No changes. ⚠ pending 88d: kill-switch reset.`
- **`build_briefing(now_et) -> dict`** — assembles message (section 0 first, then regime, then bot; target ≤8 lines), returns `{"message", "snapshot", "deltas", "pending", "warnings"}` where `warnings` carries each ⚠ with its trigger values (rule 4 — scorer food). Writes the new state file **only after** the caller confirms the log append succeeded — order: build → log → push → save state.

### Changed: `run_tactical.py`
- `from src.briefing import build_briefing` replaces the `sector_rotation` import; drop `UNIVERSE`/`THRESHOLDS`.
- Log target becomes `data/briefings.jsonl`, one line per run: `{"signal_type": "premarket_briefing", "as_of", "message", "snapshot", "deltas", "pending", "warnings", "pushover_sent"}`. Error days still log (`"error": ...`). `theses.jsonl` freezes as history, stays git-tracked.
- Briefing always pushes (there is no "no signal" day anymore — an all-calm briefing is one line). Holiday/weekend gates and heartbeat unchanged.

### Changed: `watch_tactical.py` — **gap in REDESIGN, caught here**
It checks `theses.jsonl` for a today-entry. Left alone, it would fire "Tactical Markets MISSED" every day after the swap. Point it at `briefings.jsonl` in the same commit.

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

**Smoke:** (1) `python -c "from src.briefing import build_briefing; print(build_briefing(...)['message'])"` against the live sibling files — on current data it must show the kill-switch ⚠ with age counted from **2026-08-03** (the derived trip date), not from the "last winner" date; (2) hand-corrupt a copied `last_successful_run.json` in scratch and confirm "unknown" lines, not a crash; (3) one full run with a real push, verify on phone + one well-formed `briefings.jsonl` line; (4) `python score_briefings.py` runs clean on one day of data.

**Commit:** `tactical_markets: phase 2 briefing v1 — health console ships, momentum signal retires`

---

## Phase 2b — sections 3–4, best-effort quotes (~1 session, separate commit)

Additions to `src/briefing.py` only. Governing rule: **a failed quote drops the line, never the briefing** — every function here returns `list[str]` that may be empty.

- **`quotes(tickers) -> dict[str, float] | None`** — yfinance with the Phase-1 retry pattern (shorter backoff, 2×15s — the 6:30 slot can't absorb 3×60s twice); premarket via `Ticker.fast_info` where available, else prior close and say so.
- **Section 3 — flip proximity:**
  - TQQQ: trailing stop = `position_peak_price × (1 − TRAIL_PCT)`; `TRAIL_PCT = 0.05` hardcoded **mirroring the bot's config — provenance comment required (rule 1), and a schema-drift risk if the bot ever changes it**; ⚠ when price within 2% of stop; `stopped_out: true` → plain status line. Word the line as *"trail level $X (evaluated at bot's 14:45 run)"* — the stop is decision-time, not a resting order (see record correction), and the briefing must not imply otherwise.
  - SPY: distance to 200d and 50d MA (daily history download, 1 call); ⚠ within 2% of a cross.
  - Sector sleeve: `current_holdings` listed once, no proximity math (monthly cadence).
- **Section 4 — overnight tape:** SPY/QQQ gap vs prior close, flag |gap| ≥ 1%; VIX last close + 5d change (no premarket exists). Fallback if quotes fail: day-old `vix.raw` / `vix_term_structure.raw` from MACRO's `latest.json`, labeled `(yday)`.
- Scorer: add proximity precision/recall (⚠ stop/MA line followed within 3d by actual stop-out / cross, from bot `trades.jsonl` + prices).

**Smoke:** run with network cable pulled (or a monkeypatched failing `quotes`) → sections 0–2 still deliver.

**Commit:** `tactical_markets: phase 2b briefing sections 3–4 — flip proximity + overnight tape, best-effort`

---

## Phase 3 — the two-week read (no code)

Clock starts the first live 6:30 briefing morning. Ends +14 calendar days. Then the sunset defaults from REDESIGN apply mechanically:
- default = **alert-only mode** unless Ian affirmatively opts into the daily push;
- 8 weeks with zero acted-on ⚠ lines → default = park the project;
- backlog picks (weekly digest is the promoted candidate) only after the read.

---

## Deliberately not in this plan

Everything in REDESIGN's rejected list, plus these implementation-level ones: no `src/market_data.py` abstraction (two call sites, different needs), no schema versioning on the state file (one reader, one writer, same repo), no pytest scaffolding (inline smoke runs per CLAUDE.md — revisit only if 2b's quote logic grows branches), no backfill of `briefings.jsonl` from `theses.jsonl` (different products; history stays where it is).

## Sequencing summary

| Order | What | Size | Gate |
|---|---|---|---|
| 0 | Ian's go + healthchecks account (+ Phase −1 bot session, separate) | manual | **open** |
| 1 | Phase 1 repairs | ~15 lines | go |
| 2 | Phase 2 briefing core + retire + scorer + docs | ~250 lines | go |
| 3 | Phase 2b quotes sections | ~80 lines | phase 2 live |
| 4 | Two-week read → sunset defaults | none | phase 2 live |
