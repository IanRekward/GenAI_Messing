---
name: tactical_markets project context
description: Critical rules, patterns, and unobvious constraints for AI agents working on the tactical_markets premarket signal generator.
project_name: 'tactical_markets'
user_name: 'Rekwa'
date: '2026-05-11'
sections_completed: ['technology_stack', 'identity_and_scope', 'style', 'secrets', 'cross_project', 'task_scheduler', 'workflow', 'gotchas']
existing_patterns_found: 5
---

# Project Context for AI Agents — tactical_markets

[CLAUDE.md](../CLAUDE.md) is the canonical source of policy. This file surfaces
the unobvious bits an agent will miss if it only reads code. For full
architecture, signal schema, and integration contracts, see [docs/index.md](../docs/index.md).

---

## Technology Stack

- Python 3.14 (system interpreter; **no venv yet** — do not create `.venv/` unless work requires it)
- yfinance, pandas, pyyaml, requests, python-dotenv
- Pushover HTTP API for delivery
- Windows Task Scheduler for the 6:30 AM ET premarket trigger
- Data store: append-only JSONL at `data/theses.jsonl`; no DB
- No tests directory in week 1 — inline `__main__` smoke runs only

## Critical Implementation Rules

### Identity & Scope

- **Rule-based heuristic, not a model.** No ML, no learned confidence, no fit-to-history until the trading layer produces ≥30 labeled trades.
- Week 1 ships **sector rotation only**, delivered via **Pushover only**. VIX slope, gaps, credit spreads, HTML tiles, confidence formula, backtest framework, and tests dir are **deferred** — do not add.
- After week 1 ships, **14-day code freeze** while Ian reads theses. No additions during freeze.
- [TODO.md](../TODO.md) is the source of truth. [ROADMAP_SIGNAL_GENERATION.md](../ROADMAP_SIGNAL_GENERATION.md) is preserved as v2-spec context but was **revised** on 2026-05-05. If a decision isn't covered by TODO.md, **stop and surface it** rather than guessing.

### Python / Code Style

- No comments unless the **why** is non-obvious. Don't narrate the what.
- No premature abstraction. Three similar lines beats a helper.
- No half-finished implementations.
- No error handling for impossible scenarios. Validate only at boundaries: yfinance, FRED, Pushover.
- Pure-function signal generators returning `dict | None` — `None` means no-signal (already the convention in [src/sector_rotation.py:18](../src/sector_rotation.py#L18)).
- All timestamps as `datetime.now(timezone.utc).isoformat()`.
- Append-only JSONL logs — one record per run including no-signal days with `{"signal": false, ...}` and error days with `{"signal": false, "error": "...", ...}`.
- Thresholds live in `config/*.yaml` — never hardcode publish gates, momentum windows, or hold days inside `src/`.

### Secrets

- All secrets via `.env` (`PUSHOVER_TOKEN`, `PUSHOVER_USER`, future FRED keys). **Never hardcode.**
- `.env` lives next to `run_tactical.py`, loaded with `python-dotenv`.

### Cross-Project Contract — Hard Rule

`tactical_markets`, `market_dashboard`, and `tactical_markets_trading` are
siblings under `c:\Users\rekwa\ian_projects\` and integrate **only via
files-on-disk** (e.g., reading `theses.jsonl`).

- **Forbidden:** `from market_dashboard.foo import bar` or any cross-project Python import.
- If you find yourself reaching for one, stop and surface the design question.
- Each project owns its own venv (when it has one) — do not reuse market_dashboard's.
- See [docs/integration-architecture.md](../docs/integration-architecture.md) for the full contract.

### Windows Task Scheduler

- Premarket job at 6:30 AM ET; wake task at 6:20 AM ET.
- Battery flags **must be correct from the start**:
  - `DisallowStartIfOnBatteries=false` (PowerShell flag: `-AllowStartIfOnBatteries`)
  - `StopIfGoingOnBatteries=false` (PowerShell flag: `-DontStopIfGoingOnBatteries`)
  - `StartWhenAvailable=true`
  - Wake task additionally needs `-WakeToRun`
- Already correct in [setup_task.ps1](../setup_task.ps1) — preserve when re-registering.

## Development Workflow Rules

### Two-Repo Edit/Commit Dance — non-obvious, easy to get wrong

- Primary working dir (`tactical_markets/`) is **edit-only**. Git repo lives at `c:\Users\rekwa\ian_projects\_genai_tmp\`.
- Every commit sequence:
  1. Edit in primary.
  2. Copy changed files: `cp tactical_markets/<path> _genai_tmp/tactical_markets/<path>`
  3. Prefix every git command: `cd /c/Users/rekwa/ian_projects/_genai_tmp && git ...` — Bash cwd does not persist between calls.
  4. HEREDOC commit messages.
  5. Stage with **specific paths**. Never `git add .` or `git add -A` — the repo contains other projects.
  6. Co-author trailer matching the running model:
     - `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`
     - `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`
- Remote: `https://github.com/IanRekward/GenAI_Messing.git`, branch `main`. Push pre-authorized.
- `LF will be replaced by CRLF` warnings are harmless Windows noise. Do not touch `.gitattributes`.

### Before / After Any Work

- Before: `cd /c/Users/rekwa/ian_projects/_genai_tmp && git log --oneline -5` to see the last session, then re-read [TODO.md](../TODO.md).
- After: smoke-test (inline `__main__` is fine in week 1), commit with day/phase in the message (e.g., `tactical_markets: day 1 sector rotation thesis generator`), push to `origin main`.

### Model Selection

- Design questions / DESIGNER_PROMPT.md work → Opus 4.7+.
- Locked-brief execution → Sonnet 4.6+.

## Critical Don't-Miss Rules

- **Do not re-open locked scope.** The table at the bottom of CLAUDE.md ("Locked scope decisions") is binding. Re-opening requires explicit user sign-off.
- **Do not add features the brief doesn't require.** A bug fix doesn't need surrounding cleanup; the daily script doesn't need a helper module.
- **Do not introduce a tests directory in week 1.** Inline `__main__` smoke run is sufficient.
- **Do not pull market_dashboard's composite score in week 1.** Standalone by design. Week 3+ may consume it as macro context.
- **Do not silently downgrade `yfinance` errors.** They're a boundary — catch at the entrypoint ([run_tactical.py](../run_tactical.py)), log to `theses.jsonl` with `"signal": false, "error": ...`, and surface in stdout.
- **Do not delete or rewrite `theses.jsonl` rows.** Append-only — historical no-signal days are part of the calibration record Ian is reading.
- **Do not parse the `thesis` text string to recover structured fields.** Use the structured columns. The `thesis` is display-only.
