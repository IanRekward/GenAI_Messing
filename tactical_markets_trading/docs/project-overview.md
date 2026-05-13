# tactical_markets_trading — Project Overview

**Generated:** 2026-05-13 by `bmad-document-project` (deep scan)
**Status:** Phase 1 live (paper trading); frozen until 5+ trades execute cleanly (lowered from 10 on 2026-05-13).

---

## What this project is

An Alpaca **paper-trading** execution layer that consumes tactical theses from the sibling [`tactical_markets`](../../tactical_markets/) signal generator and submits market orders against a $100k Alpaca paper account. The goal is to **empirically validate** whether sector-rotation theses translate into real fills and P&L before any live capital is committed.

It is the third in a trio of sibling projects:

| Project | Role | Status |
|---|---|---|
| [`market_dashboard`](../../market_dashboard/) | **MACRO** — strategic stress dashboard (11-bucket composite, regime detection) | Production; daily 7:30 AM |
| [`tactical_markets`](../../tactical_markets/) | **MICRO** — premarket tactical signal generator (sector rotation) | Week-1 live; daily 6:30 AM ET |
| `tactical_markets_trading` (this) | **EXECUTION** — Alpaca paper-trading layer | Phase 1 live; daily 8:35/8:40 AM CDT; frozen until 5+ trades |

Integration is **files-on-disk only** — no Python imports across siblings. This project reads `../tactical_markets/data/theses.jsonl` for entry signals. MACRO is **not consumed in Phase 1** (deferred to Phase 2 for regime size-down).

---

## What is built (Phase 1, locked 2026-05-08)

Five Python modules in `src/`, one entrypoint at the root, plus a PowerShell script that registers three Windows Scheduled Tasks. The full daily loop runs unattended:

- **08:20 AM CDT** — Wake task forces the laptop awake.
- **08:35 AM CDT** — Entry task (`run_trading.py`): read today's signal from `theses.jsonl`, check Alpaca for existing exposure, submit a market BUY of the long leg at `notional=$10k`, log to `data/trades.jsonl`, ping Pushover.
- **08:40 AM CDT** — Exit task (`src/exit_manager.py`): for every open trade past its planned exit time, submit market SELL, capture SPY and sell-leg benchmark returns via `yfinance`, log P&L, ping Pushover.

Phase 1 deliberately omits everything the [PRD](../_bmad-output/planning-artifacts/prd.md) describes as the long-term vision (multi-strategy ensemble, regime routing, MACRO consumption, kill switch, dashboard, tax export). Those are Phase 2/3+ scope.

---

## Quick reference

- **Language / runtime:** Python 3.14 (own `.venv/`)
- **Architecture pattern:** Single-entrypoint batch CLI, scheduled via Windows Task Scheduler. Append-only JSONL persistence. No DB. No tests directory.
- **Entry points:** [run_trading.py](../run_trading.py) (entry task), [src/exit_manager.py](../src/exit_manager.py) (exit task)
- **Broker:** Alpaca paper account `PA3SOYDP6IP5` ($100k). The `paper=True` flag in `TradingClient` is the safety pin.
- **Source-of-truth doc:** [TODO.md](../TODO.md). The [ROADMAP_ALPACA_INTEGRATION.md](../ROADMAP_ALPACA_INTEGRATION.md) and [TRADING_INTEGRATION_PLAN.md](../TRADING_INTEGRATION_PLAN.md) are preserved as Phase 2/3 spec context but were **revised** by the 2026-05-08 design pass.
- **PRD:** [_bmad-output/planning-artifacts/prd.md](../_bmad-output/planning-artifacts/prd.md) — describes the end-state vision (classification: `saas_b2b`). The PRD is the north star, not Phase 1 scope.

---

## Generated documentation

- [Architecture](./architecture.md) — daily flow, components, locked decisions, scope boundaries
- [Source Tree Analysis](./source-tree-analysis.md) — file-by-file with key line refs
- [Data Models](./data-models.md) — `data/trades.jsonl` schema (the ledger this bot owns)
- [Integration Architecture](./integration-architecture.md) — sibling-project contracts, Alpaca, Pushover, yfinance
- [Development Guide](./development-guide.md) — venv, env vars, Windows Task Scheduler, two-repo git workflow

## Existing project documentation (canonical)

These pre-date this scan and remain authoritative on intent and policy:

- [TODO.md](../TODO.md) — locked Phase 1 design + current status + Phase 2 lessons input
- [ROADMAP_ALPACA_INTEGRATION.md](../ROADMAP_ALPACA_INTEGRATION.md) — original Phase 1/2/3 implementation brief (revised by 2026-05-08 design pass; preserved as Phase 2/3 spec context)
- [TRADING_INTEGRATION_PLAN.md](../TRADING_INTEGRATION_PLAN.md) — original architecture + platform choice
- [_bmad-output/planning-artifacts/prd.md](../_bmad-output/planning-artifacts/prd.md) — PRD (saas_b2b classification)
- [_bmad-output/planning-artifacts/prd-validation-report.md](../_bmad-output/planning-artifacts/prd-validation-report.md) — PRD validation report (PASS)
- [_bmad-output/project-context.md](../_bmad-output/project-context.md) — rules for AI agents working on this project (generated alongside this doc)

## Getting started

### For an AI agent working on this project

1. Read [_bmad-output/project-context.md](../_bmad-output/project-context.md) first — the unobvious rules.
2. Read [TODO.md](../TODO.md) for the locked Phase 1 design + freeze status.
3. Read [development-guide.md](./development-guide.md) for venv + Windows Task Scheduler setup.
4. If a decision isn't covered by TODO.md, **stop and surface it** rather than guessing.

### For a downstream consumer (none today)

This project does not currently publish a stable contract. `data/trades.jsonl` is the internal P&L ledger; the schema is defined in [data-models.md](./data-models.md) but is not guaranteed stable.

### For Rekwa (the user)

1. Pushover at entry and exit. Watch for two consecutive clean fires.
2. After 10+ end-to-end trades, the Phase 1 freeze unfreezes. Phase 2 design decisions follow (stops, risk-based sizing, MACRO consumption — see [TODO.md](../TODO.md) "Design fork points").

## Brownfield PRD note

When ready to plan post-freeze (Phase 2) features, point a PRD workflow at this `index.md`. The current PRD already exists at [_bmad-output/planning-artifacts/prd.md](../_bmad-output/planning-artifacts/prd.md) but describes the end-state vision; Phase 2 work should narrow that to the next validated increment.
