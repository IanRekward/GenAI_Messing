# tactical_markets — Project Overview

Generated 2026-05-11 by `bmad-document-project` (exhaustive scan).

## What it is

A premarket tactical-signal companion to the strategic `market_dashboard` early-warning system. Runs once daily at 6:30 AM ET, computes a sector-rotation thesis if one exists, and delivers it to Ian's phone via Pushover. Persists every run (signal or no-signal) as one line in `data/theses.jsonl`.

Companion project: `tactical_markets_trading/` (Alpaca bot, not yet built) will consume `theses.jsonl` once it exists.

## Status

**Week-1 implementation, live.** The locked week-1 design (per [TODO.md](../TODO.md) and the 2026-05-05 design pass) is implemented and running daily. After week-1 ships, code is **frozen for 14 days** while Ian reads theses on his phone. No additions during freeze.

`theses.jsonl` shows ~5 days of live runs at 11:30 UTC (= 6:30 AM EST), so the scheduler is firing on cadence.

## Tech stack

| Category | Choice |
|---|---|
| Language | Python 3.14 (system interpreter; no venv yet) |
| Market data | `yfinance` (OHLC, free, ~2 s latency) |
| Analytics | `pandas` for momentum + MA computation |
| Config | `pyyaml` (universe + thresholds in YAML) |
| Delivery | Pushover HTTP API via `requests` |
| Secrets | `.env` loaded by `python-dotenv` |
| Scheduler | Windows Task Scheduler (`setup_task.ps1`) |
| Persistence | Append-only JSONL at `data/theses.jsonl` |

No database. No web framework. No tests directory. No HTML rendering. No backtest framework. Each of those was on the v2 roadmap and was deliberately cut to ship something Ian could actually evaluate.

## Architecture type

Monolith, single-entrypoint CLI. `run_tactical.py` is ~50 lines; it calls one pure function (`src/sector_rotation.generate`) and one side-effecting client (`src/pushover.send`).

## Repository structure

```
tactical_markets/
  run_tactical.py            entrypoint
  src/
    sector_rotation.py       pure-function signal generator
    pushover.py              minimal Pushover client
  config/
    universe.yaml            9 sector ETFs + 3 broad indices
    thresholds.yaml          spread / momentum / MA / hold parameters
  data/
    theses.jsonl             append-only log; one record per run
  setup_task.ps1             Windows Task Scheduler registration
  .env                       PUSHOVER_TOKEN, PUSHOVER_USER
```

## Documentation index

- [Architecture](./architecture.md) — single-entrypoint flow, scope boundaries, dependencies
- [Source Tree Analysis](./source-tree-analysis.md) — file-by-file walkthrough with key line refs
- [Development Guide](./development-guide.md) — how to run, edit, commit (two-repo workflow)
- [Data Models](./data-models.md) — the `theses.jsonl` record schema (the trading-bot contract)
- [Integration Architecture](./integration-architecture.md) — sibling-project contracts and the gap between design and reality
- [Index](./index.md) — master entry point

## Existing project documentation (canonical)

These pre-date this scan and remain the source of truth on intent and policy:

- [CLAUDE.md](../CLAUDE.md) — persistent agent instructions, locked-scope table, two-repo workflow
- [TODO.md](../TODO.md) — locked week-1 design, status, three failure-mode branches
- [ROADMAP_SIGNAL_GENERATION.md](../ROADMAP_SIGNAL_GENERATION.md) — preserved v2 spec context (revised by the 2026-05-05 design pass)
- [RESEARCH_SUMMARY.md](../RESEARCH_SUMMARY.md) — empirical findings (2000–2026) that ground the signal design
- [DESIGNER_PROMPT.md](../DESIGNER_PROMPT.md) — designer-mode prompt for Opus 4.7+ design passes
- [README.md](../README.md) — **stale**; says "early-stage ideation, TBD: architecture, data sources, cadence, format" — all four are locked now.
