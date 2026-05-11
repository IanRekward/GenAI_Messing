# tactical_markets — Documentation Index

Generated 2026-05-11 by `bmad-document-project` (exhaustive scan).
Primary entry point for AI-assisted development on this project.

## Project Overview

- **Type:** monolith
- **Primary Language:** Python 3.14
- **Architecture:** single-entrypoint batch CLI; one signal generator, one delivery client
- **Status:** week-1 live; scheduler firing daily at 6:30 AM ET

## Quick Reference

- **Tech Stack:** Python + yfinance + pandas + pyyaml + requests + python-dotenv; Pushover for delivery; Windows Task Scheduler for cadence
- **Entry Point:** [run_tactical.py](../run_tactical.py)
- **Architecture Pattern:** Single-entrypoint batch CLI with config-driven thresholds and append-only JSONL persistence
- **Cross-project integration:** files-on-disk only — `data/theses.jsonl` is the consumption contract for `tactical_markets_trading`

## Generated Documentation

- [Project Overview](./project-overview.md) — what, why, status, doc map
- [Architecture](./architecture.md) — daily flow, components, scope boundaries, decisions
- [Source Tree Analysis](./source-tree-analysis.md) — file-by-file with key line refs
- [Development Guide](./development-guide.md) — run, edit, commit (two-repo workflow), style rules, common tasks
- [Data Models](./data-models.md) — `theses.jsonl` schema (the trading-bot contract)
- [Integration Architecture](./integration-architecture.md) — sibling-project contracts, gaps vs. README/ROADMAP

## Existing Project Documentation (canonical)

These pre-date this scan and remain authoritative on intent and policy:

- [CLAUDE.md](../CLAUDE.md) — persistent agent instructions; locked-scope table; two-repo workflow
- [TODO.md](../TODO.md) — locked week-1 design; current status; three failure-mode branches
- [ROADMAP_SIGNAL_GENERATION.md](../ROADMAP_SIGNAL_GENERATION.md) — preserved v2 spec context (revised by 2026-05-05 design pass; do not treat as current)
- [RESEARCH_SUMMARY.md](../RESEARCH_SUMMARY.md) — empirical findings (2000–2026) grounding the signal design
- [DESIGNER_PROMPT.md](../DESIGNER_PROMPT.md) — designer-mode prompt for Opus 4.7+ design passes
- [README.md](../README.md) — **stale**; says "early-stage ideation"; all four design TBDs are now locked

## Getting Started

### For an AI agent working on this project

1. Read [CLAUDE.md](../CLAUDE.md) first.
2. Read [TODO.md](../TODO.md) for the locked week-1 design and current status.
3. Read [development-guide.md](./development-guide.md) for the two-repo workflow.
4. If a decision isn't covered by TODO.md, **stop and surface it** rather than guessing.

### For the trading-bot author (downstream consumer)

1. Read [data-models.md](./data-models.md) — the `theses.jsonl` schema.
2. Read [integration-architecture.md](./integration-architecture.md) — what this project surfaces, what it deliberately omits, what's on you.
3. Plan against the schema as-is; do not pre-implement v2 ROADMAP fields.

### For Ian (the user)

1. Pushover at 6:30 AM ET. Read the thesis. Two weeks of this is the calibration substrate.
2. After 14 days, the design unfreezes per one of three failure modes in [TODO.md](../TODO.md).

## Brownfield PRD note

When ready to plan post-freeze features (VIX slope, dashboard, confidence scoring, etc.), point a PRD workflow at this `index.md`.
