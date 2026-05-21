---
name: tactical_markets_trading project context
description: Critical rules, patterns, and unobvious constraints for AI agents working on the tactical_markets_trading Alpaca paper-trading bot.
project_name: 'tactical_markets_trading'
user_name: 'Rekwa'
date: '2026-05-13'
sections_completed: ['technology_stack', 'identity_and_scope', 'style', 'secrets', 'cross_project', 'task_scheduler', 'workflow', 'gotchas', 'phase_status']
existing_patterns_found: 7
---

# Project Context for AI Agents — tactical_markets_trading

The canonical sources of policy are [TODO.md](../TODO.md) (current status + locked Phase 1 design + Phase 2 lessons) and the [PRD](./planning-artifacts/prd.md) (north-star vision). This file surfaces the unobvious bits an agent will miss if it only reads code. For full architecture, schema, and integration contracts, see [docs/index.md](../docs/index.md).

---

## Phase status — read this first

**Phase 1 is BUILT. The blanket freeze is RETIRED as of 2026-05-20.** See [TODO.md "2026-05-20 — Freeze retired"](../TODO.md) for the rationale. The freeze was lifted twice in two weeks anyway, "5 clean executions" didn't actually validate strategy edge (only the pipes), and pure-function work demonstrably shipped during the freeze without contaminating anything.

**Replacement policy — production-path vs research-path:**
- **Production-path changes** (`run_trading.py`, `src/order_builder.py`, `src/trade_logger.py`, `src/exit_manager.py`, `src/alpaca_connector.py`, `setup_task.ps1`): require a paper-fire smoke test against the real Alpaca API before they land in the scheduler. Ship → run module's `__main__` block → verify sane output → leave for next scheduled fire.
- **Research-path and protective changes** (`src/risk.py`, `src/macro_consumer.py`, `tests/`, `research/`, `docs/`, `_bmad-output/`, new utility scripts): ship freely. No gate.
- **The safety net is the reconciler, not the freeze.** Build automated drift detection (compare local `trades.jsonl` open count to Alpaca `get_all_positions()`, Pushover-alert on mismatch) as the first Phase 2 story.

**Strategy-gate decision pending.** Before Phase 2 wiring stories unblock, Rekwa needs to pick option A/B/C in [strategy-gate-decision.md](./planning-artifacts/strategy-gate-decision.md). Backtest evidence shows the live signal underperforms SPY by 12× cumulative return at lower Sharpe than 60/40; "engineering gate" (pipes work) and "strategy gate" (signal has edge) were being conflated and need separating.

**The PRD describes the end-state vision** (multi-strategy, regime-aware, MACRO+MICRO fusion, dashboard, kill switch, tax export). **Phase 1 is dramatically simpler:** one signal, long-only momentum, fixed $10k, no stops, no MACRO. Treat the PRD as the north star, not Phase 1 scope.

---

## Technology Stack

- Python 3.14 (own `.venv/` at `tactical_markets_trading/.venv/`)
- `alpaca-py` (TradingClient, MarketOrderRequest, OrderStatus, QueryOrderStatus, GetOrdersRequest)
- `pandas-market-calendars` (NYSE calendar for trading-day arithmetic)
- `yfinance` (benchmark return capture at exit only — not on entry path)
- `python-dotenv` (`.env` loader)
- `requests` (Pushover client only)
- **Windows Task Scheduler** for cadence (three tasks: Wake/Entry/Exit)
- Data store: append-only JSONL at `data/trades.jsonl`; no DB; no tests directory

---

## Critical Implementation Rules

### Identity & Scope (Phase 1)

- **Long-only momentum.** Read MICRO's `signal: true` thesis, buy the long leg, ignore the sell leg (preserved only as a benchmark ticker at exit). Pair-trade hypothesis is **non-testable under the no-shorts rule** — do not attempt to revive it.
- **Fixed $10k notional per trade.** Phase 1. No risk-based sizing because there are no stops.
- **Market orders** at entry AND exit. Slippage optimization is Phase 2.
- **Hold 2 NYSE trading days** (lowered from 5 on 2026-05-13 to speed Phase 1 graduation as a pipes-and-signals test; Phase 2 will tune). No stops, no targets.
- **Up to 5 overlapping positions** (steady state ~50% deployed).
- **`paper=True` flag in [src/alpaca_connector.py:22](../src/alpaca_connector.py#L22) is the safety pin.** Do not remove without explicit user sign-off.
- **Authoritative idempotency dedup is Alpaca**, not `data/trades.jsonl`. Two functions in `run_trading.py`: `already_traded_today(symbol)` queries Alpaca for today's BUY orders (intra-day dedup); `at_position_limit(max_positions=5)` enforces the "5 overlapping positions" design limit. Both authoritative against local-file drift. **Updated 2026-05-13:** prior `already_traded(symbol)` (which blocked all-time same-symbol re-entries) was replaced to align with the original "5 overlapping positions" design intent — see TODO.md unlock note.
- **MACRO is NOT consumed in Phase 1.** Phase 2 candidate for size-down logic.

### Locked rules — do not re-open without explicit user sign-off

| Topic | Decision |
|---|---|
| Shorts | **Never.** Long-only or cash only. Durable user preference. |
| Real money | Not until 50+ paper trades validate edge AND rules-of-engagement doc is written. |
| Cross-project imports | Forbidden. Read sibling outputs from disk. |
| Account size | $100k paper. Don't change without re-deriving sizing. |
| Trade size | Fixed $10k per trade in Phase 1. |
| Stops/targets | None in Phase 1. Add in Phase 2 after seeing real drawdown distribution. |
| Manual vs automated | Automated entries and exits. Manual approval contaminates the test. |
| Tests directory | Deferred. Inline `__main__` smoke runs suffice. |

These are also in [TODO.md](../TODO.md) "Locked rules" table — that's the source of truth.

### Python / Code Style

- No comments unless the **why** is non-obvious. Don't narrate the what.
- No premature abstraction. Three similar lines beats a helper.
- No half-finished implementations.
- No error handling for impossible scenarios. Validate only at boundaries: Alpaca, yfinance, Pushover, MICRO's `theses.jsonl`.
- All timestamps as `datetime.now(timezone.utc).isoformat()` where new code is added.
- Append-only `data/trades.jsonl` for entries; in-place rewrite to flip `status: "open" → "closed"` at exit.
- Module-level constants for `NOTIONAL`, `FILL_POLL_INTERVAL`, etc. — Phase 2 may externalize to `config/`.
- **No silent error downgrades on Alpaca.** Catch at the entrypoint (`run_trading.py` / `src/exit_manager.py`), Pushover the failure, and re-raise so Task Scheduler logs a non-zero exit.

### Secrets

- All secrets via `.env` at the project root (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_BASE_URL`, `PUSHOVER_TOKEN`, `PUSHOVER_USER`). **Never hardcode.**
- `.env` is gitignored via the root `.gitignore`.

### Cross-Project Contract — Hard Rule

`tactical_markets_trading`, `tactical_markets` (MICRO), and `market_dashboard` (MACRO) are siblings under `c:\Users\rekwa\ian_projects\` and integrate **only via files-on-disk** (e.g., reading `theses.jsonl`, future reading `latest.json`).

- **Forbidden:** `from market_dashboard.foo import bar` or `from tactical_markets.signal import ...` or any cross-project Python import.
- If you find yourself reaching for one, **stop and surface the design question.**
- Each project owns its own venv — do not reuse another sibling's.
- See [docs/integration-architecture.md](../docs/integration-architecture.md) for the full contract.

### Windows Task Scheduler

- Three tasks registered via [setup_task.ps1](../setup_task.ps1):
  - `Tactical Trading Wake` (08:20 CDT, WakeToRun)
  - `Tactical Trading Entry` (08:35 CDT, runs `run_trading.py`)
  - `Tactical Trading Exit` (08:40 CDT, runs `src/exit_manager.py`)
- Battery flags **must be correct from the start**:
  - `DisallowStartIfOnBatteries = False` (PowerShell: `-AllowStartIfOnBatteries`)
  - `StopIfGoingOnBatteries = False` (PowerShell: `-DontStopIfGoingOnBatteries`)
  - `StartWhenAvailable = True`
  - Wake task additionally needs `-WakeToRun`
- Times are CDT — **5 / 10 min after CDT market open (08:30 CDT)**, NOT 65 min after ET open. A past session shipped 9:35/9:40 by mistake; verify before changing.

## Development Workflow Rules

### Two-Repo Edit/Commit Dance — non-obvious, easy to get wrong

- Primary working dir (`tactical_markets_trading/`) is **edit-only**. Git repo lives at `c:\Users\rekwa\ian_projects\_genai_tmp\` (shared with MICRO + MACRO).
- Every commit sequence:
  1. Edit in primary.
  2. Copy changed files: `cp tactical_markets_trading/<path> _genai_tmp/tactical_markets_trading/<path>` (or PowerShell equivalent).
  3. Prefix every git command: `cd /c/Users/rekwa/ian_projects/_genai_tmp && git ...` — Bash cwd does not persist between calls.
  4. HEREDOC commit messages.
  5. Stage with **specific paths**. Never `git add .` or `git add -A` — the repo contains MICRO + MACRO + this project.
  6. Co-author trailer matching the running model:
     - `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`
     - `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`
- Remote: `https://github.com/IanRekward/GenAI_Messing.git`, branch `main`. Push pre-authorized.
- `LF will be replaced by CRLF` warnings are harmless Windows noise. Do not touch `.gitattributes`.

### Before / After Any Work

- **Before:** `cd /c/Users/rekwa/ian_projects/_genai_tmp && git log --oneline -10` to see the last session, then re-read [TODO.md](../TODO.md) — especially the Phase 1 freeze status.
- **After:** smoke-test relevant module via its `__main__` block (or `python run_trading.py` for an end-to-end run — be aware this will actually trade if there's a signal). Commit with day/phase in the message. Push to `origin main`.

### Model Selection

- Design questions / scope decisions → **Opus 4.7+** (uses [DESIGNER_PROMPT.md-style](../../tactical_markets/DESIGNER_PROMPT.md) deep-think).
- Locked-brief execution → **Sonnet 4.6+**.

---

## Critical Don't-Miss Rules

- **Do not re-open locked scope.** See the table above. Re-opening requires explicit user sign-off.
- **Do not skip the smoke test on production-path changes.** Per the 2026-05-20 policy update, anything touching the entry/exit/fill path requires a paper-fire smoke test before being left for the scheduler. The freeze is gone; the smoke test discipline replaces it.
- **Do not remove `paper=True`** without an explicit user sign-off + the written rules-of-engagement doc.
- **Do not skip writing tests for production-path code.** The "no tests in Phase 1" rule is retired — it cost us the partial-fill bug. Add regression tests as you fix bugs.
- **Do not consume MACRO without the strategy-gate decision being made.** Phase 2 wiring stories are gated on the option A/B/C decision.
- **Do not import across siblings.** Files-on-disk only.
- **Do not delete or rewrite past `data/trades.jsonl` rows.** Append-only; in-place close-update only.
- **Do not let yfinance failures kill the close.** The exit path is non-raising after the SELL fills — leave benchmarks null rather than losing the trade record.
- **Do not eat the `wait_for_fill` timeout on terminal failure states.** REJECTED/CANCELED/EXPIRED should fail fast (already correct in [src/trade_logger.py:50-51](../src/trade_logger.py#L50-L51); don't regress).
- **Do not return on partial fills.** `wait_for_fill` must terminate only on `OrderStatus.FILLED`, not on `filled_at != None`. This was the 2026-05-08 bug (commit `58fa2e1` fixed it).
- **Do not trust local `data/trades.jsonl` for dedup.** Alpaca is authoritative.

---

## Lessons captured from Phase 1 (inputs to Phase 2 design)

From [TODO.md](../TODO.md) "Lessons from Phase 1":

- **Minimize lag between decision and API call.** Polling cycles, sleeps, and multi-step confirmations create windows for state to drift. For Phase 2 risk management (stops, sizing rules), the path from "decide to exit" to "submit order" should have as few steps as possible.
- **Test the scheduled path against the real API before unattended runs.** Smoke runs against real conditions before scheduling.
- **Optimize the polling state machine.** `wait_for_fill` should terminate on unambiguous final states. Terminal failure states fail fast.
- **Add a post-fire reconciliation pass.** Compare local `trades.jsonl` to actual Alpaca positions/orders. Alert on drift. Phase 2 should automate this.

---

## Design fork points (hand back to Opus 4.7 when reached)

- **End of Phase 1 (~5 trades):** review trade distribution. Decide whether to add stops, change sizing, or move to Phase 2 (refined risk management).
- **Surprise in results:** if win rate is dramatically above or below expectation, the hypothesis or the signal might need revisiting.
- **Trading-day calendar edge cases:** long weekends, early closes, halts, ETF rebalances. If 2-trading-day exit math gets weird in practice.
- **Phase 2 → Phase 3:** writing the rules-of-engagement document, picking the live-capital amount, deciding what (if anything) gets sized differently.
