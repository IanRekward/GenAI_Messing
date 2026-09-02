# Market Stress Dashboard

*[Rewritten 2026-09-02: the previous README carried unresolved merge-conflict
markers since the repo's first push and described the long-gone 9-bucket model
and a defunct EIA dependency. See git history for the original.]*

A personal market stress early-warning dashboard for Ian. Every morning at 7:30
it fetches 29 free public indicators (FRED, Yahoo Finance, TreasuryDirect, CNN
Fear & Greed), scores them into 11 weighted buckets against 10-year percentile
history, computes composite stress scores (0–100, long and short window),
evaluates per-indicator alert thresholds, sends Pushover alerts on real changes,
and publishes a single HTML page to GitHub Pages plus a `data/latest.json`
sidecar consumed by the tactical_markets trading bot and premarket briefing.

This is a personal decision-support tool, not a product. It helps Ian think;
it never tells him what to do.

## Daily operation

Fully automated: Windows Task Scheduler wakes the machine 07:20, runs
`python run_dashboard.py --publish --heartbeat --quiet` at 07:30. A GitHub
Actions dead-man's switch (`dashboard-watchdog.yml`) alerts if no publish lands
for 28h. Manual dry-run without paid APIs or alerts:

```bash
python run_dashboard.py --no-cache --no-news --no-alerts --quiet
```

## Where things live

- **[CLAUDE.md](CLAUDE.md)** — working agreement, two-repo git workflow,
  technical gotchas. Read first.
- **[REDESIGN_2026-09-02.md](REDESIGN_2026-09-02.md)** — canonical execution
  plan (keep/repair/gut/rebuild) · **[DEV_PLAN.md](DEV_PLAN.md)** — mechanics ·
  **[ASSESSMENT_2026-09-02.md](ASSESSMENT_2026-09-02.md)** — evidence record.
- **[TODO.md](TODO.md)** — backlog · **[ROADMAP.md](ROADMAP.md)** — historical
  briefs · **[BACKTEST_DESIGN.md](BACKTEST_DESIGN.md)** — backtest spec.
- `config/weights.yaml` — authoritative indicator/bucket definition (⚠️ its
  byte-level MD5 is a consumer contract — see DEV_PLAN "Verified contracts").
- `src/` — pipeline modules · `tests/` — `pytest tests/ -q` (fast, offline;
  note quiet-hours: 3 alert tests require the 07:00–22:00 window until R1 ships).

## Keys

`.env` requires `FRED_API_KEY`, `ANTHROPIC_API_KEY` (Haiku narrative/news),
`PUSHOVER_APP_TOKEN`/`PUSHOVER_USER_KEY`; optional Twilio fallback vars.
