# tactical_markets_trading — TODO

Alpaca paper-trading layer that validates [tactical_markets](../tactical_markets/) signal efficacy. Separate from signal generation; integrates *with* it via files-on-disk (`tactical_markets/data/theses.jsonl`). No imports across projects.

## Status

**Phase 1 Days 1-7 built + hardened (2026-05-08).** Alpaca paper account active (`PA3SOYDP6IP5`, $100k). All code paths in place, all tasks registered with Windows Task Scheduler, hardening pass applied (commit acd618b). First scheduled fires 2026-05-08, entry 8:35 AM CDT, exit 8:40 AM CDT. **Phase 1 freeze began 2026-05-08** — no code changes until 5+ clean trades accumulate.

**2026-05-13 freeze unlock:** Two small changes applied. (1) Lifted the cadence bottleneck: replaced `already_traded(symbol)` with `already_traded_today(symbol)` (intra-day dedup only) + `at_position_limit(5)` (enforce the "up to 5 overlapping positions" design limit). Aligns code with original Phase 1 design intent; does NOT change hypothesis, sizing, hold window, or any other locked rule. (2) Lowered Phase 1 graduation gate from 10 → 5 clean trades — empirical validation substrate is "good enough to proceed with development" sooner, allowing Phase 2 implementation work to begin earlier. Real-capital gate (Phase 3) remains at 50+ paper trades + ROE doc. Expected effect of both changes: Phase 1 graduation reachable in ~1-2 weeks at current cadence.

## Source documents

- [ROADMAP_ALPACA_INTEGRATION.md](ROADMAP_ALPACA_INTEGRATION.md) — original implementation brief, **revised by the 2026-05-08 design pass**. Preserved as Phase 2/3 spec context.
- [TRADING_INTEGRATION_PLAN.md](TRADING_INTEGRATION_PLAN.md) — architecture, platform choice (Alpaca), data flow.

## Locked Phase 1 design (2026-05-08 design pass, Opus 4.7)

Design pass run after `tactical_markets` week-1 ship. The ROADMAP's pair-trade hypothesis cannot be tested under Ian's durable "no shorts, ever" rule (infinite-downside risk preference). Phase 1 tests a *related* long-only momentum hypothesis instead.

**Hypothesis:** Long-only momentum on sector winners outperforms buy-and-hold SPY.

**Mechanic:**
- Account: Alpaca paper, $100k. `paper=True` flag in `TradingClient` is the safety pin.
- Trigger: each trading day, if `tactical_markets/data/theses.jsonl` has a `signal: true` line for that day, buy the `buy` ticker only (ignore the `sell` leg).
- Sizing: fixed **$10k per trade** (10% of account, fractional shares via Alpaca `notional` field). No risk-based sizing in Phase 1.
- Order type: **market order** at entry, **market order** at exit. Slippage optimization deferred.
- Exit: market order, **5 trading days after entry**. No stop, no target.
- Concurrency: up to 5 overlapping positions. Steady state ~50% deployed, ~50% cash.
- Per-trade logging: entry, fills, exit, P&L — plus two benchmarks at exit time:
  - (a) SPY's return over the same window
  - (b) The loser-leg ticker's return over the same window
  - (b) lets us reconstruct the pair-trade Sharpe post-hoc, even though we never short.

**Why no stops in Phase 1:** characterizing the signal, not managing risk. Stops introduce a confound (where did you set it?) that contaminates validation. After ~5 trades we'll see the drawdown distribution and can size stops based on real data instead of guesses.

**Why fixed dollar sizing:** risk-based sizing needs a stop, which we don't have. Fixed dollar makes per-trade P&L directly comparable across trades.

**What this revises from ROADMAP_ALPACA_INTEGRATION.md:**
- Pair trade → long-only winner + counterfactual loser-leg tracking.
- Limit orders w/ ask + 5bps → market orders.
- 2% risk / 5% position / 20% open caps → deferred to Phase 2 (after drawdown distribution is known).
- Confidence-based sizing → fixed sizing.
- "Manual approval, user clicks Execute" → fully automated; we want to test the signal, not Ian's discretionary judgment.
- Phase 1 success criteria → simplified (see below).

**Trade-offs accepted:**
- Long-only ≠ pair-trade hypothesis, so we're testing a related but not identical edge.
- Market orders sacrifice slippage optimization for execution simplicity.
- Full automation contaminates "would Ian have actually placed this trade?" but cleanly tests the signal.

## Phase 1 day-by-day (all complete 2026-05-08)

- **Day 1 ✅** [src/alpaca_connector.py](src/alpaca_connector.py) — `load_env()`, `trading_client()`, account fetch.
- **Day 2 ✅** [src/order_builder.py](src/order_builder.py) — read latest `signal: true` from `../tactical_markets/data/theses.jsonl`, submit market buy with `notional=10000`.
- **Day 3 ✅** [src/trade_logger.py](src/trade_logger.py) — `wait_for_fill` polls Alpaca; appends entry record to `data/trades.jsonl` with NYSE-aware `add_trading_days` for `exit_time_planned`.
- **Day 4 ✅** [src/exit_manager.py](src/exit_manager.py) — finds open trades past `exit_time_planned`, submits market sell, atomic save (fill-then-benchmark, never raises after fill).
- **Day 5 ✅** Benchmark capture inside `exit_position` — `spy_return_pct` and `sell_leg_return_pct` via yfinance over the same window. Failures default to `null`, never block close.
- **Day 6 ✅** [run_trading.py](run_trading.py) (entry orchestration) + [setup_task.ps1](setup_task.ps1) — three Windows Tasks registered: Wake (8:20 AM CDT, WakeToRun), Entry (8:35 AM CDT, runs `run_trading.py`), Exit (8:40 AM CDT, runs `src/exit_manager.py`). Times are 5-10 min after CDT market open (8:30 AM CDT). Battery flags: `DisallowStartIfOnBatteries=False`, `StopIfGoingOnBatteries=False`, `StartWhenAvailable=True`.
- **Day 7 (in progress):** watch for two consecutive clean fires. First scheduled entry/exit fires today at 8:35/8:40 AM CDT.

### Hardening pass (2026-05-08, Opus 4.7 design review, commit acd618b)

Six structural fixes applied before freeze:
1. `already_traded` queries Alpaca (positions + open orders), not local file. Local file lags if logging fails; Alpaca is the actual source of truth for whether we have exposure.
2. `exit_position` is non-raising after the SELL fills. yfinance/network errors leave `spy_return_pct`/`sell_leg_return_pct` as `null` but the close is always persisted.
3. `add_trading_days` uses NYSE calendar via `pandas_market_calendars` — handles US holidays (Memorial Day verified for entries May 18-22).
4. [src/pushover.py](src/pushover.py) added — minimal client, mirrors `tactical_markets/src/pushover.py`. Notifications on entry, exit, every failure path. Silently no-ops if env not configured (prints `[pushover not configured]`).
5. Stale hardcoded `__main__` removed from `trade_logger.py` (was a smoke-test artifact pointing at a now-cancelled order id).
6. Scheduler timing corrected from 9:35/9:40/9:20 to 8:35/8:40/8:20 (5 min after CDT market open, not 65 min after ET open).

After Phase 1 freeze, **no new code** until 5+ trades accumulate (revised down from 10 on 2026-05-13). Success gate: 5+ trades executed end-to-end without rejections or stranded positions.

## Validation gates

- **Phase 1 → Phase 2:** 5+ clean executions, no system errors, positions exit on schedule. ~1-2 weeks at the post-dedup-fix cadence.
- **Phase 2 → Phase 3 (live capital):** 50+ trades, win rate vs SPY > 50%, alpha statistically positive. ~10+ weeks.
- **Hard floor:** no live capital until Ian writes a one-page rules-of-engagement document and the validation gate is passed.

## Design fork points (hand back to Opus 4.7)

- **End of Phase 1 (~5 trades):** review trade distribution, decide whether to add stops, change sizing, or move to Phase 2 (refined risk management).
- **Surprise in results:** if win rate is dramatically above or below expectation, the hypothesis or the signal might need revisiting.
- **Trading-day calendar edge cases:** long weekends, early closes, halts, ETF rebalances. If 5-trading-day exit math gets weird in practice.
- **Phase 2 → Phase 3:** writing the rules-of-engagement document, picking the live-capital amount, deciding what (if anything) gets sized differently.

## Locked rules — do not re-open without explicit user sign-off

| Topic | Decision |
|---|---|
| Shorts | Never. Durable preference (memory: feedback_no_shorts.md). Long-only or cash only. |
| Real money | Not until 50+ paper trades validate edge AND rules-of-engagement doc is written. |
| Cross-project imports | Forbidden. Read `theses.jsonl` from disk. |
| Account size | $100k paper. Don't change without re-deriving sizing. |
| Trade size | Fixed $10k per trade. Phase 1 only; Phase 2 may reintroduce risk-based sizing. |
| Stops/targets | None in Phase 1. Add in Phase 2 after seeing real drawdown distribution. |
| Manual vs automated | Automated entries and exits. Manual approval reintroduces discretionary contamination. |

## Lessons from Phase 1 — inputs to Phase 2 design

Captured here so the next design pass (end of Phase 1 or end-of-freeze review) doesn't lose them. See also memory: `feedback_scheduler_api_testing.md`.

- **Minimize lag between decision and API call.** Polling cycles, sleeps, and multi-step confirmations all create windows for state to drift. For Phase 2 risk management (stops, sizing rules), the path from "decide to exit" to "submit order" should have as few steps as possible. Don't pre-compute decisions and act later — act on what's true at decision time.
- **Test the scheduled path against the real API before unattended runs.** Day 7's first fire surfaced a partial-fill bug (`wait_for_fill` returned on `filled_at != None`, which Alpaca sets on the first partial fill, not at `status == FILLED`). Logic looked right; behavior was wrong; only the live fire exposed it. Phase 2 changes must include a smoke run against real conditions before being scheduled.
- **Optimize the polling state machine.** `wait_for_fill` should terminate on the unambiguous *final* state. Terminal failure states (REJECTED, CANCELED, EXPIRED) should fail fast, not eat the full timeout. This is fixed in the Phase 1 hardening pass (commit 58fa2e1) — pattern carries forward to any future Alpaca interaction.
- **Add a post-fire reconciliation pass.** Compare local trades.jsonl to actual Alpaca positions/orders. Alert on drift. Today we caught it manually; Phase 2 should automate this check after every entry and exit.

## Cross-project integration

- **`tactical_markets/`** — read-only consumer of `data/theses.jsonl`. No imports.
- **`market_dashboard/`** — not consumed in Phase 1. May read composite stress score in Phase 2 for size-down logic when band is red.

## Environment

- Own venv at `tactical_markets_trading/.venv/`. Created Day 1 with Python 3.14 (system).
- Dependencies installed: `alpaca-py`, `python-dotenv`, `yfinance`, `pandas-market-calendars`, `requests` (transitive).
- `.env` keys: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_BASE_URL`, `PUSHOVER_TOKEN`, `PUSHOVER_USER`. Gitignored via root `.gitignore`. The `paper=True` flag in `TradingClient` is the actual safety pin against accidentally hitting live markets.
- Three Windows Scheduled Tasks: `Tactical Trading Wake`, `Tactical Trading Entry`, `Tactical Trading Exit`. Re-register via `PowerShell -ExecutionPolicy Bypass -File .\setup_task.ps1` (uses `-Force` so safe to re-run).
