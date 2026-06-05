# CLAUDE.md — Market Dashboard

Persistent instructions for any Claude model working on this project.
Read this before touching any file. These rules override defaults.

---

## Note to future models — keep this document alive

If you learn something in your session that would have helped you at the start —
a non-obvious workflow step, a constraint that bit you, a decision that was
debated and settled — **add it here before you finish**. This document is only
useful if it grows with the project. Don't wait to be asked. If you're the first
model to hit a sharp edge, smooth it for the next one.

---

## What this project is

A personal market stress early-warning dashboard for Ian, an active investor.
It fetches ~26 financial indicators, scores them into 11 buckets, computes a
composite stress score (0–100), and sends Pushover mobile alerts when thresholds
are crossed. It runs automatically at 7:30 AM daily and publishes to GitHub Pages.

This is a personal decision-support tool, not a product. Design for signal
quality and Ian's judgment, not for generality. The dashboard should help him
think — never tell him what to do.

---

## Collaboration rules

- Give **one opinionated recommendation**, not a menu. When asked "what's next,"
  pick one thing and defend it.
- When Ian says "use your best judgment" or delegates a scope decision, make
  the call and lock it in. Don't ask follow-up questions.
- Keep updates tight. No narration of your thought process. State results and
  next steps.
- Ian understands markets. Use OAS, SOFR spread, bid-to-cover, etc. without
  defining them.
- Flag data limitations honestly (e.g. CNN Fear & Greed is scraped/unofficial).

---

## Working agreement — Opus and Sonnet

Two Claude models share this project: **Claude Opus** (4.7+) and **Claude
Sonnet** (4.6+). Ian switches between them with `/model`. The models never
communicate directly — CLAUDE.md, git history, TODO.md, and Ian-as-coordinator
are the only channels. This section is the working contract so handoffs are
clean and Ian knows which model fits a given task.

### Honest sketches

**Opus (4.7+) — the designer / diagnostician.**
- Strongest at: design decisions, architectural trade-offs, scope negotiation,
  multi-file debugging, "should we even do this" questions, initial planning
  of large briefs, reviewing design output before Sonnet executes, writing new
  ROADMAP briefs from scratch.
- Blind spots: tends to over-engineer if not checked; slower and more expensive
  per round-trip; will add structure the task didn't need. If a brief is
  well-specified, Opus will still execute — but Sonnet ships it faster for less.
- Temperament: skeptical, weighs trade-offs aloud, will push back on scope.

**Sonnet (4.6+) — the workhorse / shipper.**
- Strongest at: executing well-scoped briefs (ROADMAP entries), writing tests,
  dashboard UI polish, config edits, fetch-layer additions, routine commits.
  Has shipped most of the project to date — `git log` shows the pattern.
- Blind spots: may skip past design nuance to get to shipping; fuzzy scope
  becomes "pick something reasonable and go" — not always what Ian wanted.
- Temperament: decisive, execution-biased, minimal commentary.

### Role division — which model for which task

| Task | Prefer |
|---|---|
| Design a brief / architecture call / "how should we…" | Opus |
| Execute a brief already written in [ROADMAP.md](ROADMAP.md) | Sonnet |
| Weird test failure spanning multiple files | Opus |
| Add a new indicator to a bucket per a clear spec | Sonnet |
| Re-scope a bucket / change a weight / debate inclusion | Opus |
| Fix a typo, add a chart card, write a test | Sonnet |
| Author a new ROADMAP brief from scratch | Opus |
| Mid-execution design question not covered by the brief | Flag → switch to Opus |
| Routine commits / pushes after changes land | Either (Sonnet cheaper) |

### Handoff triggers — say these aloud, then offer the switch

**If Opus is running and about to do routine execution work:**
> "This is well-scoped. Sonnet will be faster and cheaper here — want to
> `/model sonnet` before I start?"

**If Sonnet is running and hits a real design trade-off:**
> "Design decision here: [describe]. My instinct is [A]; [B] trades differently
> on [axis]. Pick one and I'll ship it, or `/model opus` for a design pass
> first?"

**Either model, if a brief is truly ambiguous:** stop executing, write the
ambiguity up, ask Ian to pick — don't guess and commit.

### What neither model does

- **Pretend to consult the other.** No meeting room exists. The record is
  `git log`, TODO.md, and this file. Read it.
- **Rewrite each other's working, tested code for style.** If it's in `main`
  with passing tests, it stays. Only touch it to fix a real bug or when the
  brief requires the change.
- **Re-open locked scope decisions** (see table below) regardless of model.
  Escalate to Ian if a locked decision genuinely needs revisiting.
- **Simulate the other model via the Agent tool.** If Ian wants a second
  opinion he'll `/model` switch. The Agent tool is for parallel searches
  and subtask delegation, not for fake peer review.

### Ian as coordinator

Ian chooses which model runs. The models' job is to be honest about where each
adds value so he can switch intelligently. If the other model would do the next
step better, say so plainly — he'd rather spend 10 seconds switching than spend
10 minutes on a bad fit. No false modesty; no turf.

---

## Two-repo git workflow — CRITICAL

The primary working directory (`c:\Users\rekwa\ian_projects\market_dashboard\`)
is **edit-only**. The git repo lives at `c:\Users\rekwa\ian_projects\_genai_tmp\`.

**Every commit follows this sequence:**
1. Edit files in the primary dir (where Read/Edit/Write tools operate).
2. Copy changed files: `cp market_dashboard/<path> _genai_tmp/market_dashboard/<path>`
3. Prefix every git command: `cd /c/Users/rekwa/ian_projects/_genai_tmp && git ...`
4. Use a HEREDOC for commit messages. Always include the co-author trailer
   matching the running model — e.g.:
   - `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`
   - `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`
   `git log` becomes a cross-model record of who did what.
5. Stage with specific paths (`git add market_dashboard/src/foo.py ...`). Never
   `git add .` or `-A` — the repo contains other projects, and blanket adds
   pull in unrelated work or stray artifacts.
6. `warning: LF will be replaced by CRLF` on every commit is harmless Windows
   line-ending noise. Do not "fix" it or touch `.gitattributes` without asking.

The Bash tool cwd does NOT persist between calls — prefixing the `cd` is the
only reliable approach. A `.git.bak` placeholder in the primary dir will cause
git commands there to fail loudly (good — it's a safety net, don't delete it).

**Remote:** `https://github.com/IanRekward/GenAI_Messing.git`, branch `main`.

---

## Before starting any work

1. `cd /c/Users/rekwa/ian_projects/_genai_tmp && git log --oneline -10` —
   catch up on what the last session (possibly a different model) just landed.
2. Run `python -m pytest tests/ -q` from the primary dir. All tests must pass
   before you write a single line. If they don't, fix it before continuing.
   Tests are fast (~1s, 181+ cases) — there's no excuse to skip.
3. Read [ROADMAP.md](ROADMAP.md) for the full brief before touching any Brief
   task. Each brief is self-contained with problem, design decisions, file list,
   edge cases, and success criteria.
4. Check the brief's "Dependencies" line. Verify prior briefs' criteria are met.
5. Check [TODO.md](TODO.md) for a "mid-task handoff" note at the bottom. If the
   previous session ended mid-brief, it'll be recorded there (see "Mid-task
   handoffs" below).

---

## After completing any work

1. Run the full test suite. All tests must pass before committing.
2. The pre-commit hook in `.git/hooks/pre-commit` runs config validation
   automatically — if it fails, fix the config, don't skip the hook.
3. Mark the item complete in [TODO.md](TODO.md).
4. Commit with a message that references the brief or feature name.
5. Push to `origin main`. **Push is pre-authorized** for this project — the
   whole point of the workflow is same-day publication to GitHub Pages via
   the morning automation. Don't stall to confirm each push. (Force-push
   still requires explicit user sign-off, as does any destructive git op.)

---

## Coding style

- **No comments** unless the WHY is non-obvious (a hidden constraint, a subtle
  invariant, a workaround for a specific bug). Don't explain what code does.
- No extra abstractions beyond what the task requires. Three similar lines beats
  a premature helper.
- No half-finished implementations. Ship complete or don't ship.
- No error handling for scenarios that can't happen. Trust internal guarantees.
  Validate only at system boundaries (user input, external APIs).
- No backwards-compatibility shims. If something is unused, delete it.
- Security: no command injection, no hardcoded secrets. All secrets via `.env`.

---

## Project structure

```
market_dashboard/
  src/
    fetch.py          — all data fetching (FRED, yfinance, TreasuryDirect, CNN F&G)
    indicators.py     — zscore, percentile, vol, yoy transforms
    scoring.py        — composite scoring orchestration; COMPUTED_HANDLERS registry
    triggers.py       — threshold annotation (bands: green/yellow/orange/red)
    history.py        — run logging, momentum, shock classification, regime scoring
    alerts.py         — Pushover dispatch, alert state, rapid-rise logic
    dashboard.py      — HTML generation
    config.py         — config validation (validate_config, ConfigError)
    news.py           — RSS triage
    calendar.py       — upcoming macro events
    narrative.py      — Claude Haiku synthesis
    backtest.py       — point-in-time backtest engine
    evaluation.py     — backtest metrics
    recalibrate.py    — weight recalibration pipeline
  config/
    weights.yaml      — bucket/indicator weights and source definitions (authoritative)
    thresholds.yaml   — per-indicator alert thresholds
    events.yaml       — historical market events for chart overlay
  tests/              — pytest suite; run with `pytest tests/ -q`
  data/               — manual_overrides.json, alert_state.json, alert_log.jsonl
  run_dashboard.py    — entry point
  TODO.md             — task list (source of truth for backlog)
  ROADMAP.md          — full implementation briefs for Phase 6+
```

---

## Config is authoritative

`config/weights.yaml` defines every indicator: its bucket, weight, source type,
and fetch parameters. `src/scoring.py:COMPUTED_HANDLERS` and
`src/config.py:KNOWN_INDICATOR_KEYS` must stay in sync with it.
`validate_config()` is called at startup and in the pre-commit hook — any drift
fails loudly. When adding an indicator:
1. Add it to `config/weights.yaml` with a `source:` block.
2. Add its key to `KNOWN_INDICATOR_KEYS` in `src/config.py`.
3. If `type: computed`, register a handler in `COMPUTED_HANDLERS` in `src/scoring.py`.

---

## Technical gotchas — things that bit a past session

Each of these cost a previous model at least one wasted iteration. Read once,
save yourself the same mistake. Add to this list when something bites you too.

- **Pre-commit hook validates the `_genai_tmp/` copy, not primary.** The hook
  runs `cd "$(git rev-parse --show-toplevel)/market_dashboard"` before calling
  `validate_config()`. If you edit `config/weights.yaml` in primary but forget
  to `cp` it to `_genai_tmp/` before committing, the hook rejects using the
  stale file. When committing config changes: **sync config files first**.
- **Two composite scores exist.** `composite` uses 10-year percentiles,
  `composite_short` uses 3-year (`HISTORY_YEARS_SHORT` env var, default 3).
  Any composite-aware feature — alerts, dashboard cards, Pushover body,
  narrative — must handle both. Search for `composite_short` before adding.
- **`invert: true` flag flips score direction.** Indicators where LOWER raw =
  MORE stress must set `invert: true` in `weights.yaml`. Current inverted
  indicators: `yield_curve` (inverted curve = stress), `cnn_fear_greed` (fear
  = low score = stress), `spx_200dma_distance` (below MA = stress). Easy to
  forget when adding a new indicator.
- **Alert dedupe state lives in `data/alert_state.json`.** Keys include
  `composite_band`, `orange_indicators`, `red_indicators`, `rapid_rise_alerts`,
  `corr_regime_streak`, `stale_indicators`, `weekly_alert_count`. When adding a
  new alert type: (a) handle the first-run empty-state case, (b) decide when
  the dedupe key resets. The `rapid_rise_alerts` pattern (reset on band change)
  is the canonical template — copy it.
- **Dry-run invocation for manual verification:**
  `python run_dashboard.py --no-cache --no-news --no-alerts --quiet`
  runs the full pipeline without burning paid APIs or sending Pushover. Use
  this after any edit that changes scoring, thresholds, or HTML output.
- **CNN Fear & Greed is scraped, not official.** `fetch_cnn_fear_greed()` can
  fail silently on site changes. `_handler_cnn_fear_greed` falls back to FRED
  UMCSENT. Don't assume freshness — check `data/fetch_cache/` staleness if
  sentiment numbers look stale.
- **Parallel indicator fetch via `MAX_FETCH_WORKERS`.** `compute_composite`
  parallelizes the ~26 top-level indicator fetches across 8 workers by
  default. Set `MAX_FETCH_WORKERS=1` in `.env` or shell to force serial
  execution (escape hatch for concurrency-related issues). Computed handlers'
  nested `fetch.fetch_yfinance_series` calls stay serial — no nested pool
  submissions.

---

## Testing patterns

- **Alert-test mock targets (`src/alerts.py`):** patch `_send_pushover`,
  `_send_twilio`, `_in_quiet_hours`, `_log_alert`, `_load_state`, `_save_state`.
  There is no `_dispatch` or `_should_send` — don't try to patch them.
  See `tests/test_rapid_rise.py` for the canonical shape.
- **History tests:** build synthetic DataFrames with `pd.date_range(...)` and
  a scores list. See `tests/test_history.py` and `tests/test_shock_type.py`
  for templates. No need to touch real `data/history.csv`.
- **Fetch tests:** all HTTP is mocked. Tests pass offline. If a new test needs
  network, that's a code smell — factor the logic so the network layer can be
  mocked out.
- **Config tests** (`tests/test_config.py`) are the canary for schema drift.
  If you break `validate_config()`, these fail first.
- **`live` marker for network-required tests.** The default `pytest tests/ -q`
  excludes `@pytest.mark.live` tests via `pytest.ini` and runs in seconds.
  Live tests (currently 4 in `test_remediation.py`) hit real FRED + yfinance,
  load `.env` for `FRED_API_KEY`, and skip cleanly when the key is absent.
  Run them with `pytest -m live` before publishing or after fetch-layer
  changes. The `block_network` autouse fixture in `conftest.py` exempts
  `live`-marked tests; everything else gets `RuntimeError` on any
  `requests.get`/`yf.download` call.

---

## Mid-task handoffs

Sessions can end mid-brief (context limit, interruption). When that happens,
before your last message add a **`## Mid-task handoff`** section at the
bottom of [TODO.md](TODO.md) with:

1. Which brief / item you were on.
2. What's done (file list + behavior shipped).
3. What's next — the literal next step in concrete terms, not a vague
   "finish the brief."
4. Any gotchas you hit but didn't write up yet.

Delete the section when the next session picks up and completes the work.
This turns a truncated session from "lost state" into "warm handoff."

---

## Locked scope decisions — do not re-open without explicit user sign-off

These were debated and decided. Treat them as constraints, not starting points.

| Topic | Decision |
|---|---|
| Sentiment source | CNN Fear & Greed (primary), FRED UMCSENT (fallback if CNN fails) |
| Bond auction metrics | Bid-to-cover, indirect %, dealer % only. Auction tail **excluded**. |
| Auction structure | Z-score composite of 10Y Note + 30Y Bond; lives in `rates_curve` at 0.15 weight |
| rates_curve weights | yield_curve 0.45, ten_year 0.20, move_index 0.20, treasury_auction_stress 0.15 |
| Economic calendar scope | CPI/PPI/PCE, FOMC+minutes, NFP+initial claims, GDP, ISM, retail sales, Treasury auctions |
| Economic calendar exclusions | Regional Fed speakers, housing starts, durable goods, data revisions |
| Bucket count | 11 buckets. If a count check fails, investigate before reducing `_MIN_BUCKETS`. |

---

## Morning automation

- **Wake task:** "Market Dashboard Wake" in Windows Task Scheduler — 7:20 AM daily,
  `WakeToRun: true`. Requires RTCWAKE=1 (Enable) in powercfg.
- **Dashboard task:** "Market Stress Dashboard" — 7:30 AM daily,
  `python run_dashboard.py --publish --heartbeat --quiet`
- If automation breaks, diagnose in order: **`logs/dashboard_run.log` first**
  (Brief 28 — every run logs start/finish + full crash traceback there, even
  under `--quiet`), then `powercfg /waketimers` (admin),
  `schtasks /query /tn "Market Dashboard Wake"`, `powercfg /lastwake`.
- **External watchdog (Brief 28):** `.github/workflows/dashboard-watchdog.yml`
  runs on GitHub (cron 20:00 UTC), keys off the commit time of `docs/index.html`,
  and Pushover-alerts if no publish in >28h — the dead-man's switch for the
  machine being off. It is **inert until repo secrets `PUSHOVER_APP_TOKEN` and
  `PUSHOVER_USER_KEY` are added** (it logs a warning and exits 0 without them).
- **`ExecutionTimeLimit` is PT20M (Brief 28)**, not the PT72H default — a hung
  run self-terminates so the next day starts clean. The main task was set live;
  the wake task needs an elevated shell (Access denied otherwise) but its limit
  is moot (it runs `cmd /c exit`). `setup_task.ps1` bakes PT20M into both.
- **Battery flags must stay false on a laptop.** Both tasks need
  `DisallowStartIfOnBatteries=false` and `StopIfGoingOnBatteries=false`. With
  the defaults true, the wake task is silently skipped on battery and only
  `NumberOfMissedRuns` reveals it (not `LastTaskResult`). Verify with
  `(Get-ScheduledTask -TaskName 'Market Dashboard Wake').Settings`. Modifying
  these requires admin (the task's `RunLevel` is `HighestAvailable`); use
  `Set-ScheduledTask` from an elevated shell. Also set `StartWhenAvailable=true`
  so a missed run catches up rather than waiting until the next day.
- Lock screen on wake is expected — tasks run in locked session, Pushover fires
  without any user input.

---

## Task queue

See [TODO.md](TODO.md) for the current backlog. The recommended next items as of
2026-04-24 (after Briefs 1, 2, 3 complete):

- **Brief 4A** — Historical events overlay on trend chart (1 hour, high UX value)
- **Brief 6** — Data staleness alerts (high priority)
- **Brief 4B** — Indicator drill-down detail pages
- **Brief 5** — Correlation-breakdown signal
- **Dashboard UX batch A** — Items 6+7+10 together (bucket/indicator weight display)
- **Dashboard UX batch B** — Items 9+Brief 14 together (indicator tooltips + band tooltips)
