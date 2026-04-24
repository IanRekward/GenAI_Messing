# CLAUDE.md — Market Dashboard

Persistent instructions for any Claude model working on this project.
Read this before touching any file. These rules override defaults.

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

## Two-repo git workflow — CRITICAL

The primary working directory (`c:\Users\rekwa\ian_projects\market_dashboard\`)
is **edit-only**. The git repo lives at `c:\Users\rekwa\ian_projects\_genai_tmp\`.

**Every commit follows this sequence:**
1. Edit files in the primary dir (where Read/Edit/Write tools operate).
2. Copy changed files: `cp market_dashboard/<path> _genai_tmp/market_dashboard/<path>`
3. Prefix every git command: `cd /c/Users/rekwa/ian_projects/_genai_tmp && git ...`
4. Use a HEREDOC for commit messages. Always include the co-author trailer:
   `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`

The Bash tool cwd does NOT persist between calls — prefixing the `cd` is the
only reliable approach. A `.git.bak` placeholder in the primary dir will cause
git commands there to fail loudly (good — it's a safety net, don't delete it).

**Remote:** `https://github.com/IanRekward/GenAI_Messing.git`, branch `main`.

---

## Before starting any work

1. Run `python -m pytest tests/ -q` from the primary dir. All tests must pass
   before you write a single line. If they don't, fix it before continuing.
2. Read [ROADMAP.md](ROADMAP.md) for the full brief before touching any Brief
   task. Each brief is self-contained with problem, design decisions, file list,
   edge cases, and success criteria.
3. Check the brief's "Dependencies" line. Verify prior briefs' criteria are met.

---

## After completing any work

1. Run the full test suite. All tests must pass before committing.
2. The pre-commit hook in `.git/hooks/pre-commit` runs config validation
   automatically — if it fails, fix the config, don't skip the hook.
3. Mark the item complete in [TODO.md](TODO.md).
4. Commit with a message that references the brief or feature name.
5. Push to `origin main`.

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
- If automation breaks, diagnose in order: `powercfg /waketimers` (admin),
  `schtasks /query /tn "Market Dashboard Wake"`, `powercfg /lastwake`.
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
