# CLAUDE.md — tactical_markets

Persistent instructions for any Claude model working on this project.
Read this before touching any file. These rules override defaults.

---

## What this project is

Companion to the strategic [market_dashboard](../market_dashboard/) early-warning system. Generates short-horizon (24–48h) tactical theses for Ian's discretionary review. Runs at 6:30 AM ET premarket, delivers via Pushover.

**Design constraint, locked:** This is a **rule-based heuristic, not a model.** Parameters come from published research and are treated as a starting hypothesis. The "calibration step" is Ian reading theses on his phone for two weeks; the code stays frozen during that window. ML / learned-confidence layers are deferred until the trading layer exists and produces labels (≥30 trades).

---

## Working agreement

Read [TODO.md](TODO.md) for the locked week-1 design before any code change. The original [ROADMAP_SIGNAL_GENERATION.md](ROADMAP_SIGNAL_GENERATION.md) is preserved as v2-spec context — its 4-week parallel rollout was **revised by the 2026-05-05 design pass**. TODO.md is the source of truth for what's actually being built.

For design questions, use [DESIGNER_PROMPT.md](DESIGNER_PROMPT.md) and switch to Opus 4.7+. For locked-brief execution, Sonnet 4.6+ is the right model.

If a decision isn't covered by TODO.md, **stop and surface it** rather than guessing. The whole point of two-week freezes is that scope drift is visible.

---

## Two-repo workflow — same as market_dashboard

The primary working directory (`c:\Users\rekwa\ian_projects\tactical_markets\`) is **edit-only**. The git repo lives at `c:\Users\rekwa\ian_projects\_genai_tmp\`.

Every commit follows this sequence:
1. Edit files in primary.
2. Copy changed files: `cp tactical_markets/<path> _genai_tmp/tactical_markets/<path>`
3. Prefix every git command: `cd /c/Users/rekwa/ian_projects/_genai_tmp && git ...`
4. HEREDOC commit messages with the running model's co-author trailer:
   - `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`
   - `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`
5. Stage with specific paths. Never `git add .` or `-A` — the repo contains other projects.
6. `LF will be replaced by CRLF` warnings are harmless Windows noise. Don't touch `.gitattributes`.

Bash tool cwd does not persist between calls. Prefix the `cd` every time.

**Remote:** `https://github.com/IanRekward/GenAI_Messing.git`, branch `main`. Push is pre-authorized.

---

## Coding style

Same as market_dashboard:
- No comments unless WHY is non-obvious.
- No extra abstractions. Three similar lines beats a premature helper.
- No half-finished implementations.
- No error handling for impossible scenarios. Validate only at boundaries (yfinance, FRED, Pushover).
- All secrets via `.env`. Never hardcoded.

Project-specific:
- **No shared imports across the three sibling projects.** `tactical_markets`, `market_dashboard`, and `tactical_markets_trading` integrate via files-on-disk, not Python imports. If you find yourself wanting `from market_dashboard.foo import bar`, stop and surface the design question.
- **Own venv, not market_dashboard's.** When a venv is needed, create `tactical_markets/.venv/`. Day 1–2 can use system Python (yfinance is already installed system-wide).

---

## Before starting any work

1. `cd /c/Users/rekwa/ian_projects/_genai_tmp && git log --oneline -5` — what was the last session.
2. Read [TODO.md](TODO.md) for the locked design.
3. If executing a brief, verify dependencies in the brief are met before writing code.

## After completing any work

1. Smoke-test the change. (No `tests/` directory in week 1; an inline `__main__` smoke run is sufficient.)
2. Commit with a message that names the day/phase (e.g., `tactical_markets: day 1 sector rotation thesis generator`).
3. Push to `origin main`.

---

## Locked scope decisions — do not re-open without explicit user sign-off

| Topic | Decision |
|---|---|
| Week 1 signal | Sector rotation only. VIX slope, gaps, credit-spread context all deferred. |
| Week 1 output | Pushover only. No HTML, no dashboard tiles. |
| Confidence scoring | Binary publish / don't publish on a hard threshold. No formula. |
| Backtest framework | Deferred. Treat published Sharpe 0.92 as starting hypothesis, not a thing we re-derive. |
| Tests directory | Deferred until surface area justifies it. Inline smoke runs suffice in week 1. |
| Two-week freeze rule | After week 1 ships, code is frozen for 14 days while Ian reads theses. No additions during freeze. |
| Cross-project imports | Forbidden. Files-on-disk contracts only. |
