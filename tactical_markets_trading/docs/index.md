# tactical_markets_trading — Documentation Index

Generated 2026-05-13 by `bmad-document-project` (deep scan).
Primary entry point for AI-assisted development on this project.

## Project Overview

- **Type:** monolith
- **Primary Language:** Python 3.14
- **Architecture:** single-entrypoint batch CLI, scheduled via Windows Task Scheduler; append-only JSONL persistence
- **Status:** Phase 1 live; daily 8:35/8:40 AM CDT firings; **FROZEN until 5+ trades validate** (lowered from 10 on 2026-05-13)

## Quick Reference

- **Tech Stack:** Python + alpaca-py + yfinance + pandas-market-calendars + python-dotenv + requests
- **Entry Points:**
  - [run_trading.py](../run_trading.py) — Entry task (08:35 CDT)
  - [src/exit_manager.py](../src/exit_manager.py) — Exit task (08:40 CDT)
  - [setup_task.ps1](../setup_task.ps1) — one-time Windows Task Scheduler registration
- **Architecture Pattern:** Single-entrypoint batch CLI; long-only momentum executor consuming MICRO theses via files-on-disk
- **Cross-project integration:** Reads `../tactical_markets/data/theses.jsonl` (MICRO). MACRO `data/latest.json` NOT consumed in Phase 1.
- **Broker:** Alpaca paper account `PA3SOYDP6IP5` ($100k). `paper=True` flag is the safety pin.

## Generated Documentation

- [Project Overview](./project-overview.md) — what, why, status, doc map
- [Architecture](./architecture.md) — daily flow, components, locked Phase 1 decisions, scope boundaries
- [Source Tree Analysis](./source-tree-analysis.md) — file-by-file with key line refs
- [Data Models](./data-models.md) — `trades.jsonl` schema, Alpaca request shapes, Pushover messages
- [Integration Architecture](./integration-architecture.md) — sibling-project contracts, Alpaca, Pushover, yfinance
- [Development Guide](./development-guide.md) — venv, env vars, Windows Task Scheduler, two-repo git workflow

## Existing Project Documentation (canonical)

These pre-date this scan and remain authoritative on intent and policy:

- [TODO.md](../TODO.md) — **source of truth** for locked Phase 1 design, current freeze status, Phase 2 lessons
- [ROADMAP_ALPACA_INTEGRATION.md](../ROADMAP_ALPACA_INTEGRATION.md) — original Phase 1/2/3 brief (revised 2026-05-08; preserved as Phase 2/3 spec context)
- [TRADING_INTEGRATION_PLAN.md](../TRADING_INTEGRATION_PLAN.md) — original architecture + platform-choice rationale
- [_bmad-output/planning-artifacts/prd.md](../_bmad-output/planning-artifacts/prd.md) — PRD (saas_b2b classification; describes end-state vision)
- [_bmad-output/planning-artifacts/prd-validation-report.md](../_bmad-output/planning-artifacts/prd-validation-report.md) — PRD validation report (PASS, 4/5 GOOD)
- [_bmad-output/project-context.md](../_bmad-output/project-context.md) — **persistent rules for AI agents** (generated alongside this scan)
- [_bmad-output/planning-artifacts/FINTECH_TRADING_BOT_REFERENCE_MATERIALS.md](../_bmad-output/planning-artifacts/FINTECH_TRADING_BOT_REFERENCE_MATERIALS.md) — regulatory/technical reference materials

## Sibling project documentation

These are the two upstream projects this bot integrates with. Their docs define the contracts this bot depends on:

- [`tactical_markets/docs/index.md`](../../tactical_markets/docs/index.md) (MICRO) — premarket signal generator. Critical: [data-models.md](../../tactical_markets/docs/data-models.md), [integration-architecture.md](../../tactical_markets/docs/integration-architecture.md)
- [`market_dashboard/_bmad-output/planning-artifacts/integration-brief-for-tactical-bot.md`](../../market_dashboard/_bmad-output/planning-artifacts/integration-brief-for-tactical-bot.md) (MACRO) — integration brief explicitly written for this project; defines the stable `data/latest.json` contract for Phase 2+ consumption.

## Getting Started

### For an AI agent working on this project

1. Read [_bmad-output/project-context.md](../_bmad-output/project-context.md) first — the unobvious rules + Phase 1 freeze status.
2. Read [TODO.md](../TODO.md) for the locked Phase 1 design and current status.
3. Read [development-guide.md](./development-guide.md) for the two-repo workflow + Task Scheduler setup.
4. If a decision isn't covered by TODO.md, **stop and surface it** rather than guessing.

### For Rekwa (the user)

1. Watch Pushover at 08:35 / 08:40 CDT on weekdays — entry and exit notifications.
2. After 5+ clean trades, Phase 1 freeze lifts and Phase 2 design opens.
3. After 50+ paper trades validated + rules-of-engagement doc written, Phase 3 (live capital) becomes possible.

## Brownfield PRD note

When ready to plan post-freeze Phase 2 features (stops, risk sizing, MACRO consumption, multi-strategy), point a PRD workflow at this `index.md`. The current PRD already exists at [_bmad-output/planning-artifacts/prd.md](../_bmad-output/planning-artifacts/prd.md) but describes the end-state vision — Phase 2 work should narrow it into the next validated increment.

For architecture, layer a `architecture-phase-2.md` on top of the current [architecture.md](./architecture.md). The current doc captures Phase 1 only.
