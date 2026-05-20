# tactical_markets_trading — TODO

Alpaca paper-trading layer that validates [tactical_markets](../tactical_markets/) signal efficacy. Separate from signal generation; integrates *with* it via files-on-disk (`tactical_markets/data/theses.jsonl`). No imports across projects.

## Status

**Phase 1 Days 1-7 built + hardened (2026-05-08).** Alpaca paper account active (`PA3SOYDP6IP5`, $100k). All code paths in place, all tasks registered with Windows Task Scheduler, hardening pass applied (commit acd618b). First scheduled fires 2026-05-08, entry 8:35 AM CDT, exit 8:40 AM CDT.

**2026-05-13 freeze unlock:** Two small changes applied. (1) Lifted the cadence bottleneck: replaced `already_traded(symbol)` with `already_traded_today(symbol)` (intra-day dedup only) + `at_position_limit(5)` (enforce the "up to 5 overlapping positions" design limit). Aligns code with original Phase 1 design intent; does NOT change hypothesis, sizing, hold window, or any other locked rule. (2) Lowered Phase 1 graduation gate from 10 → 5 clean trades.

## 2026-05-20 — Strategy gate decision: D → C

**Chose Option D first, then C.** Full decision record: [strategy-gate-decision.md](_bmad-output/planning-artifacts/strategy-gate-decision.md).

All 3 closed Phase 1 trades were concentrated XLK — the pre-M1 single-thesis shape, not the diversified multi-thesis signal that shipped 2026-05-20. That data can't validate the strategy as designed. Let M1 run for 2–3 weeks to get representative evidence, then decide whether to add a parallel variant (Option C / 21-day hold) or re-param (Option B).

**Review date: ~2026-06-10.** At that point: look at the live ledger. If diversification is improving results → build Option C (parallel 21-day-hold variant). If not → Option B/E (re-param, restart Phase 1 on new params).

**Phase 1 engineering gate retired.** 3 clean round-trip trades, pipes validated.

**Phase 2 → Phase 3 gate tightened:** 50+ trades AND (Sharpe ≥ 0.6 OR realized return ≥ 80% of SPY same-window). "Win rate > 50%" alone is a coin-flip.

**Pre-market exit bug fixed (2026-05-20).** `exit_manager._market_is_open()` now guards `run_exits()`. Reconciler still runs before the guard so drift detection is always active. Root cause: `StartWhenAvailable` fired the exit task at 08:00 UTC (03:00 CDT) when the machine woke; SELLs queued pre-market, `wait_for_fill` timed out, local state diverged until reconciler ran. The 08:00 UTC XLK SELLs on 2026-05-20 were ours (the exit task via StartWhenAvailable), not a security incident.

---

## 2026-05-20 — Freeze retired + strategy gate added

The Phase 1 freeze is **retired** as a blanket policy. Replaced with a **production-path vs research-path** distinction (below). Rationale captured in [_bmad-output/planning-artifacts/strategy-gate-decision.md](_bmad-output/planning-artifacts/strategy-gate-decision.md); short version: the freeze cost more than it produced, and the validation cadence (3 trades in 12 days vs the 5 needed) is too slow for "freeze until N trades" to be a sane gating mechanism.

### Why the freeze is retired

- **Was lifted twice in two weeks anyway** (10→5 graduation gate; dedup fix on 2026-05-13). A freeze you lift twice isn't a freeze, it's friction.
- **The "5 clean executions" gate doesn't validate strategy edge** — only that the pipes work. The strategy question needs its own gate (the new strategy-gate decision doc).
- **Pure-function work shipped during the freeze without contaminating anything** (Phase 2 `src/risk.py`, `src/macro_consumer.py`, tests) — demonstrating the "freeze prevents contamination" argument was overweighted.
- **"No tests in Phase 1" was actively harmful.** The partial-fill bug on 2026-05-08 surfaced in live fire when a recorded-response test would have caught it in seconds. Tests are protection, not contamination.

### Replacement policy — production-path vs research-path

- **Production-path changes** (anything in `run_trading.py`, `src/order_builder.py`, `src/trade_logger.py`, `src/exit_manager.py`, `src/alpaca_connector.py`, `setup_task.ps1`): require a paper-fire smoke test against the real Alpaca API before they land in the scheduler. Ship the change, run the relevant module's `__main__` block (or `python run_trading.py` outside the scheduler window), verify the call returns sane output, then leave it for the next scheduled fire.
- **Research-path and protective changes** (anything in `src/risk.py`, `src/macro_consumer.py`, `tests/`, `research/`, `docs/`, `_bmad-output/`, new files like `src/backfill_benchmarks.py`): ship freely. No gate.
- **Reconciler-as-circuit-breaker, not freeze-as-circuit-breaker.** The right safety net for production-path drift is automated drift detection (compare local `trades.jsonl` open count to Alpaca `get_all_positions()`, alert via Pushover on mismatch). Build the reconciler as the *first* Phase 2 story so the safety net exists before the wiring lands.
- **Phase 3 (live capital) gate is unchanged.** 50+ paper trades + rules-of-engagement doc. That's not a freeze, it's a different kind of gate (capital deployment).

### Today's work

- **Wrote [strategy-gate decision doc](_bmad-output/planning-artifacts/strategy-gate-decision.md)** — three options (A: proceed as-is, B: switch params upstream, C: parallel A/B variant). Recommendation: Option C. Awaiting Rekwa's pick.
- **Fixed a real bug in `src/exit_manager.py` `get_return_pct`** — `yf.download()` returns MultiIndex columns even for single tickers, which made `float(data["Close"].iloc[0])` raise inside the silent `except`. Every prior benchmark capture has landed as null because of this. Switched to `yf.Ticker().history()` (the pattern already used in `research/compare_strategies.py`).
- **Added [src/backfill_benchmarks.py](src/backfill_benchmarks.py)** to backfill null SPY / sell-leg benchmarks in closed trades.
- **Built [src/reconciler.py](src/reconciler.py)** — first Phase 2 protective story. Detects drift between local `trades.jsonl` and Alpaca state. Auto-backfills "local-open-but-Alpaca-closed" by looking up the SELL in Alpaca order history. Pushover-alerts on "Alpaca-position-with-no-local-record" (never synthesizes records without provenance). Idempotent. Logs to `data/reconciler_log.jsonl`. Dry-run mode for safety.
- **Ran reconciler** to flush today's drift state. Result:
  - Backfilled close for trade `68527bf4` (XLK, -$269.47, -2.69%)
  - Backfilled close for trade `6cf21482` (XLK, -$75.01, -0.75%)
  - Flagged untracked XLE position (169.89 shares @ ~$58.86 avg) for manual investigation
- **Added regression tests:**
  - `tests/test_reconciler.py` (5 tests) — no-drift, backfill-on-match, unresolvable-on-no-match, untracked-alert, dry-run-no-persist
  - `tests/test_exit_manager.py` (4 tests) — pins the yfinance MultiIndex bug regression
  - `tests/test_trade_logger.py` (8 tests) — pins the partial-fill bug regression + terminal-failure-fast + NYSE calendar edge cases (Memorial Day 2026)
  - Full suite: **48/48 passing**.
- **Updated `_bmad-output/project-context.md`** to remove the blanket freeze and add the production-path policy.

### Strategy data so far (n=3 closed trades)

| # | Trade | XLK return | SPY | Sell-leg | Long-short spread |
|---|---|---:|---:|---:|---:|
| 1 | XLK vs XLE (2026-05-08 to 05-15) | +1.92% | +0.21% | +6.71% | **-4.79%** |
| 2 | XLK vs XLU (2026-05-14 to 05-20) | -2.69% | -0.92% | -0.87% | **-1.82%** |
| 3 | XLK vs XLRE (2026-05-15 to 05-20) | -0.75% | +0.28% | +2.78% | **-3.53%** |
| Σ | | **-1.52%** | **-0.43%** | — | **-10.14%** |

3-for-3 on the pair-trade going the wrong direction. The "no shorts" rule has been protecting capital. n=3 is noise, but as early signal it reinforces the strategy-gate concern. Long-only is also underperforming SPY by 1.1pp absolute (-1.52% vs -0.43%) in the same window.

### Open items flagged (need Rekwa attention)

- **Untracked XLE position on Alpaca** (169.89 shares @ ~$58.86 avg = $10,149 market value). Origin unknown. Possibilities:
  - Manual buy via Alpaca UI — if so, suppress the alert by adding a manual record or accepting the recurring alert
  - Lost entry log (BUY succeeded, `trade_logger.log_entry` failed before persisting) — would need to find the BUY in Alpaca order history and reconstruct the record
  - Unknown other source
  - **Action:** investigate origin via Alpaca order history. Either create a manual record in `trades.jsonl` with best-known provenance, or close the position manually and let the reconciler clean up.
- **The two XLK SELLs at 08:00:16 UTC today (2026-05-20)** were submitted from outside this system (our exit task runs at 13:40 UTC). Probably you closing them in the Alpaca UI overnight, but worth confirming. If you didn't submit those, something else has API credentials.
- **Trade 68527's 16:40 UTC entry on 2026-05-14** — the BUY's Alpaca `submitted_at` confirms 16:40 UTC, not the scheduled 13:35 UTC. Probably a Task Scheduler miss (machine asleep, lock conflict). Check Task Scheduler history.
- **Strategy-gate decision** — pick A/B/C in [strategy-gate-decision.md](_bmad-output/planning-artifacts/strategy-gate-decision.md). Phase 2 wiring stories shouldn't unblock until that's chosen.
- **Phase 1 → Phase 2 engineering gate** can now be retired. Reconciler shipped + 48 tests passing + 3 round-trip-validated trades demonstrate the pipes work. The "5 clean executions" gate has served its purpose.
- **Phase 2 → Phase 3 gate change** proposed in the strategy-gate doc: tighten "win rate vs SPY > 50%" (coin-flip clears that) to something Sharpe- or relative-return-based.

### Round 2 of today (after first review): XLE root-cause, wiring, MICRO ask

**XLE untracked position root-caused:**
- The Alpaca order metadata shows submission at 2026-05-18 13:35:08 UTC (exactly the scheduled 8:35 CDT entry time), $10k notional, MARKET, DAY — bot signature.
- The order took **3 minutes 21 seconds to fill** (filled at 13:38:29).
- `FILL_POLL_TIMEOUT` was 60s. `wait_for_fill` timed out, raised, and the BUY-already-submitted order continued on Alpaca's side. `log_entry` never persisted the record.
- MICRO thesis for 2026-05-18 confirmed: buy=XLE, sell=XLY, spread 9.77%.
- **Action taken:** reconstructed the XLE record in `trades.jsonl` with `reconstructed: true`, `reconstructed_at`, and `reconstruction_reason` audit fields. Reconciler dry-run now reports 0 drift.

**The two XLK SELLs at 08:00:16 UTC today (2026-05-20) confirmed as manual:**
- `created_at` 2026-05-19 22:51 and 22:52 UTC (5:51/5:52 PM CDT), one minute apart — manual click-through cadence
- `submitted_at` 9 hours later at 08:00 UTC = Alpaca app's market-on-open queue
- Almost certainly you closing them via the Alpaca app last night.

**Wired the reconciler into the scheduled cycle:**
- `reconciler.reconcile(dry_run=False)` now runs at the top of `run_exits()` in `src/exit_manager.py`. Every scheduled exit cycle reconciles first, then exits.
- Added pre-flight `client.get_open_position(symbol)` check in `exit_position` — raises cleanly if we don't actually hold the symbol, instead of letting the SELL hit the "fractional cannot be sold short" rejection.
- **Bumped `FILL_POLL_TIMEOUT` from 60s to 300s** in `src/trade_logger.py` — root-cause fix for the XLE log loss. 300s is generous for slow market fills, still fails fast on stuck orders. Reconciler is the secondary safety net.
- **Smoke-tested by running `python src/exit_manager.py`** per the new production-path policy. Outcome demonstrated the safety net working as designed:
  - `reconcile()` ran first — 0 drift detected (state was clean)
  - Pre-flight `get_open_position("XLE")` succeeded (we hold it)
  - SELL submitted (order `d6750ced`)
  - `wait_for_fill` timed out at 300s because the smoke test ran after market close (23:13 UTC = 6:13 PM ET); Alpaca queued the market DAY order for next-day open
  - Exception caught, Pushover'd, no autonomous bad action — order is in flight, status ACCEPTED, will fill at 13:30 UTC tomorrow
  - Tomorrow's 13:40 UTC scheduled exit task will reconcile, find local-open-but-Alpaca-no-position, auto-backfill the close from `d6750ced` in order history
- **After-hours edge case surfaced (low priority, deferrable):** `exit_position` doesn't detect market-closed state. Submits a market DAY order anyway, which queues for next open. Safe but noisy (one 300s timeout per misfire). In normal scheduled operation this never triggers (exit task runs at 13:40 UTC = 9:40 ET, post-open). Only affects manual runs of `exit_manager.py` after hours. Future polish: detect with `client.get_clock()` and skip cleanly.

**Filed the Option C ask to MICRO:**
- New asks doc at `../tactical_markets/_bmad-output/planning-artifacts/bot-integration-asks-variant-b-2026-05-20.md`
- Requests a second variant signal output `theses_variant_b.jsonl` using sensitivity-best params (21d lookback, 3% spread)
- Linked from MICRO's TODO.md for discoverability (same pattern as the 2026-05-13 distribution)

### Next concrete code work (post-smoke-test)

- Wait for MICRO to ship `theses_variant_b.jsonl` (per the ask doc).
- Once shipped, parameterize the bot's entry path to read either ledger via a `--variant` flag, create the second scheduled task, set up `data/trades_variant_b.jsonl` ledger, A/B compare at 30 cumulative trades.
- Apply the Phase 2 → Phase 3 gate tightening (Sharpe- / relative-return-based, replacing the coin-flip-clearable "win rate vs SPY > 50%").
- Begin Phase 2 wiring stories (broker-side stops, MACRO size-down, risk-based sizing, kill switch) in the order specified in [epics.md](_bmad-output/planning-artifacts/epics.md). The reconciler is now in place as the safety net.

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
- Exit: market order, **2 trading days after entry** (lowered from 5 on 2026-05-13 to speed Phase 1 graduation as a pipes-and-signals test; Phase 2 will tune). No stop, no target.
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
- **Trading-day calendar edge cases:** long weekends, early closes, halts, ETF rebalances. If 2-trading-day exit math gets weird in practice.
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
