# tactical_markets

Premarket tactical-signal companion to the strategic [`market_dashboard`](../market_dashboard/) early-warning system. Runs once daily at 6:30 AM ET, computes a short-horizon (24–48 h) sector-rotation thesis if one exists, and delivers it to phone via Pushover.

## Status

**Week-1 implementation, live.** Daily scheduled run firing at 6:30 AM ET; see `data/theses.jsonl` for the live record.

After week-1 ships, code is **frozen for 14 days** while Ian reads theses on his phone. The locked design is in [TODO.md](TODO.md). The frozen state is the calibration substrate — modifying it mid-window invalidates the read.

## What's actually shipped

- **Sector rotation signal** — 5-day momentum rank across 9 SPDR sector ETFs + 3 broad indices (12 tickers); publish if top-vs-bottom spread ≥ 1.5% **and** buy-side is above its 20-day MA.
- **Pushover delivery** — plain-text thesis to phone.
- **Append-only JSONL log** — `data/theses.jsonl`, one record per run including no-signal and error days. This is the consumption contract for the future trading bot.
- **Windows Task Scheduler** — daily 6:30 AM ET via `setup_task.ps1` (wake task at 6:20 ET).

Three projects sit side by side and integrate via files-on-disk only (no shared Python imports):

| Project | Role | Status |
|---|---|---|
| `market_dashboard` | Strategic; "Is the system in stress?" (10y+ context, 11 buckets, composite) | Shipping |
| `tactical_markets` *(this)* | Tactical; "What's the 24–48h trade?" (premarket, sector rotation) | Week-1 live |
| `tactical_markets_trading` | Alpaca-based execution against signals from this project | Not built |

## What's deferred (per 2026-05-05 design pass)

The v2 [ROADMAP_SIGNAL_GENERATION.md](ROADMAP_SIGNAL_GENERATION.md) envisioned a broader system (VIX slope, gap detection, credit-spread macro context, HTML dashboard tiles, confidence scoring, multi-thesis envelope, backtest framework). All of that is **deliberately cut** until two weeks of lived exposure surface what's actually wrong. See [TODO.md](TODO.md) for the freeze rule and the three failure modes that unfreeze it.

## Design principles

- Shorter data window (24–48 h) vs the strategic dashboard's percentiles (10y+).
- Rule-based heuristic, not a model — no ML, no learned confidence, until the trading layer produces ≥30 labeled trades.
- Never predicts; surfaces "market is pricing X, you decide".
- Feeds tactical decisions, not strategic positioning.
- Files-on-disk contracts between sibling projects, not Python imports.

## Documentation

- [docs/index.md](docs/index.md) — full documentation entry point
- [docs/data-models.md](docs/data-models.md) — `theses.jsonl` schema (the trading-bot contract)
- [docs/integration-architecture.md](docs/integration-architecture.md) — cross-project boundaries; gap table vs the v2 ROADMAP; advice for the downstream trading-bot author
- [docs/architecture.md](docs/architecture.md) — daily flow, components, scope boundaries
- [docs/development-guide.md](docs/development-guide.md) — run, edit, two-repo commit workflow

Persistent context for AI agents working on this project: [CLAUDE.md](CLAUDE.md), [TODO.md](TODO.md), [_bmad-output/project-context.md](_bmad-output/project-context.md).

## Quick start

```powershell
# Manual run (writes to theses.jsonl, sends Pushover if configured)
python run_tactical.py

# Smoke run (prints thesis or "no signal", no side effects)
python -m src.sector_rotation

# Register the daily scheduler (one-time, no admin)
.\setup_task.ps1
```

Requires `.env` at the project root with `PUSHOVER_TOKEN` and `PUSHOVER_USER`.
