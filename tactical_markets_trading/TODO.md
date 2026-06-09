# tactical_markets_trading — TODO

## 🔁 AGENT GIT WORKFLOW — DO THIS EVERY SESSION (read first)

This project is the `tactical_markets_trading/` subfolder of the **`IanRekward/GenAI_Messing`** GitHub monorepo. **Git is NOT in this folder** — the clone is at `C:\Users\rekwa\ian_projects\_genai_tmp`. The live bot RUNS from *this* folder (`C:\Users\rekwa\ian_projects\tactical_markets_trading`): its `.venv`, `.env`, Task Scheduler jobs, and `data/` runtime state all live here, so this stays the working + execution copy. Always bracket a session with this loop so the remote never silently goes stale again.

**① START — pull remote, then deploy code DOWN (never touches live `data/` or `.env`):**
```powershell
git -C C:\Users\rekwa\ian_projects\_genai_tmp pull --ff-only origin main
robocopy C:\Users\rekwa\ian_projects\_genai_tmp\tactical_markets_trading C:\Users\rekwa\ian_projects\tactical_markets_trading /E /XD .venv .claude _bmad __pycache__ .pytest_cache .git data /XF .env
```

**② WORK** — make and test changes here in the run folder. `pytest` must stay green before publishing.

**③ END — publish code + tracked artifacts UP to the clone, commit, push:**
```powershell
robocopy C:\Users\rekwa\ian_projects\tactical_markets_trading C:\Users\rekwa\ian_projects\_genai_tmp\tactical_markets_trading /E /XD .venv .claude _bmad __pycache__ .pytest_cache .git /XF .env strategy_state_*.json account_state.json drift_log.jsonl reconciler_log.jsonl graduation_state.json close_orphan_xle_run.log
git -C C:\Users\rekwa\ian_projects\_genai_tmp add -A tactical_markets_trading
git -C C:\Users\rekwa\ian_projects\_genai_tmp commit -m "tactical_markets_trading: <summary>"
git -C C:\Users\rekwa\ian_projects\_genai_tmp push origin main
git -C C:\Users\rekwa\ian_projects\_genai_tmp rev-list --left-right --count origin/main...HEAD   # must print: 0   0
```

**Rules.** Never commit `.env` or runtime state (`strategy_state_*`, `account_state`, `drift_log`, `reconciler_log`, `graduation_state`). `data/trades.jsonl` + `data/macro_weights_allowlist.json` ARE tracked (deliberate audit/config) — let them update. **Step ① excludes the whole `data/` dir on purpose:** the live bot owns its runtime state; overwriting it from the clone would corrupt open positions/stops. If a pull brings code changes, re-run `pytest` after deploying down. See memory `project-git-structure`.

---

Alpaca paper-trading layer. As of 2026-05-21: pivoting from sector-rotation execution to a multi-strategy regime-routed ensemble. Phase 2 infrastructure (preflight, reconciler, kill switches, sizing) is strategy-agnostic and gets reused.

## 2026-06-09 — STATUS: Phase 3.2 running, first stop-fired exit booked

Current verified state (against `data/` ledger + last reconciler run). Phase 3.2 has now been live and trading for ~2 weeks; this is the source of truth, the 2026-05-29 section below is the prior snapshot.

**Live positions (4 open):**

| Strategy | Position | Entry |
|---|---|---|
| `trend_leveraged_tqqq` | **flat / stopped_out**, awaiting re-entry trigger | (last entry $77.13, 05-21) |
| `trend_following_spy_200d` | 44 SPY | $750.82 (05-27) |
| `sector_momentum_top3_monthly` | XLK 60 / XLE 198 / XLY 92 | various (05-27); rebalanced into 2026-06, no churn |

**What changed since 05-29:**
- **First TQQQ trailing-stop fired in the wild 2026-06-05: +$1,756.39 / +5.33%** (entry $77.13 → exit $81.24, `exit_reason: stop_fired`, "TQQQ $81.44 ≤ peak $87.24 × 0.95 = $82.87"). The "watch the first stop-fire" item is **resolved**, and this satisfies the graduation gate's "≥1 stop-fired exit" leg.
- **Realized PnL ≈ +$1,699** across 7 closed trades (TQQQ winner dominates); 4 trades open.
- **peak_equity drawdown kill-switch bug fixed** — it had been frozen at $100,067 since 05-21 because only the retired `run_trading.py` advanced the high-water-mark. `run_ensemble.py` now updates it each cycle; account_state.json now reads $101,008.93 (ratcheting). Intermediate highs before the fix are unrecoverable.
- **Drift log cleaned: 0 unresolved** (10 stale benign events resolved 06-08 — in-flight order false positives + XLE fractional residual). This had been masking the "30d operational cleanliness" graduation leg.
- **Legacy `exit_manager.py` "Tactical Trading Exit" scheduled task disabled 06-08** (was firing daily, emitting reconcile/drift Pushover noise though it never traded). `setup_task.ps1` footgun fixed 06-09 — it no longer re-registers the Exit task on re-run.
- **Pushover title-branding fix completed 06-09** — `src/pushover._format_title` had an em-dash typo failing 4 tests; fixed. Tests now **196 passing** (was 189 at 3.1).

**Still open / deferred:**
- **Phase 3.3 (live capital)** — gated on 6mo paper + per-component minimums (30 closed trades each, ≥1 stop-fired exit ✓, ≥1 MACRO-veto period) + 30d operational cleanliness. Not close — several more months of paper testing expected (confirmed 2026-06-09).
- **Remaining Pushover noise (deferred):** `notify_drift` re-alerts on benign in-flight orders (no dedupe); raw `json.dumps` body at `reconciler.py:252`; stale "PHASE 2 GRADUATION" label.
- Update `run_ensemble.py` module docstring (still says "Phase 3.1 single-strategy variant").

---

## 2026-05-29 — PHASE 3.2 LIVE: full 3-component regime-routed ensemble

**Status correction:** the sections below this one stop at Phase 3.1 (single TQQQ component). The running system is now well past that — Phase 3.2 is built and trading daily. This section is the current source of truth; older sections are history.

**Three components live**, all registered in `run_ensemble.py` `ACTIVE_STRATEGIES`, routed by `src/regime_router.py` (classifies on SPY 200d MA + VIX + MACRO):

| Strategy | Module | State file | Live position (2026-05-29) |
|---|---|---|---|
| `trend_leveraged_tqqq` | `src/strategies/leveraged_trend.py` | `data/strategy_state_trend_leveraged_tqqq.json` | 427 TQQQ, in_position, peak $84.375, not stopped out (entry $77.12 / 05-21) |
| `trend_following_spy_200d` | `src/strategies/spy_trend.py` | `data/strategy_state_trend_following_spy_200d.json` | 44 SPY, in_position (entry $750.82 / 05-27) |
| `sector_momentum_top3_monthly` | `src/strategies/sector_momentum_monthly.py` | `data/strategy_state_sector_momentum_top3_monthly.json` | XLK 60 / XLE 198 / XLY 92, rebalance month 2026-05 (entries 05-27) |

- Regime at recent entries: `bull_calm`. Daily decision cycle confirmed firing (state files timestamped 2026-05-29 13:35 UTC).
- **TQQQ software trailing stop** sits ~$80.16 (5% below peak $84.375). Not yet fired in the wild — watch for the first stop-fire.
- **Legacy positions closed:** XLF closed 2026-05-28 (scheduled, flat $0). XLE legacy slot superseded by the sector-momentum component. Old `run_trading.py`/`exit_manager.py` path stays gated off by `SECTOR_ROTATION_5D_RETIRED=True`.
- **Known stale comment:** `run_ensemble.py` module docstring still says "Phase 3.1 single-strategy variant" — the code below it is the full 3.2 ensemble.

### Open items
- **Phase 3.3 (live capital)** — gated on 6mo paper + per-component minimums (30 closed trades each, ≥1 stop-fired exit, ≥1 MACRO-veto period) + 30d operational cleanliness. Not close.
- Update `run_ensemble.py` docstring to drop the "Phase 3.1 single-strategy" framing.
- Re-confirm test count after the 3.2 modules (was 156 at end of 3.1).

---

## 2026-05-21 — PHASE 3.1 BUILT + FIRST PAPER TRADE EXECUTED

**Phase 3.1 component shipped.** `src/strategies/leveraged_trend.py` (TQQQ + 50d MA + 5% trailing stop) + `src/strategy_state.py` (per-strategy persistence) + `run_ensemble.py` (new orchestrator) + 19 tests. **156/156 tests passing.**

**First live paper trade taken via the new orchestrator (2026-05-21 18:12 UTC):**
- BUY 427 shares TQQQ @ $77.13 (target ~$33k = 33% of $100k equity, whole-share floor)
- Trigger: trend on (SPY $743.12 > 50d MA $694.87)
- Trade ID: `dc67b513...` in `data/trades.jsonl` with new schema fields (`strategy`, `trigger`, etc.)
- Strategy state: `in_position=True, position_peak_price=$77.12, stopped_out=False` in `data/strategy_state_trend_leveraged_tqqq.json` (gitignored, like other runtime state)

**Cooldown reset bug found and fixed while writing tests:** original code only reset the post-stop cooldown when in-position, meaning once stopped out, cooldown stayed sticky forever (no re-entry possible). Fixed: cooldown now clears whenever trend signal goes off (regardless of in-position status). Test: `test_cooldown_full_cycle_stop_fire_then_trend_off_then_trend_on_enters_clean`.

### Scheduled task migration (when ready)

Currently the Windows Scheduled Task "Tactical Trading Entry" still points at `run_trading.py` (which short-circuits via `SECTOR_ROTATION_5D_RETIRED` flag — no trades). To activate the new orchestrator on the daily schedule:

```powershell
# In setup_task.ps1 or via Task Scheduler GUI:
# Change the Action for "Tactical Trading Entry" task from:
#   Execute: ...python.exe
#   Arguments: run_trading.py
# To:
#   Execute: ...python.exe
#   Arguments: run_ensemble.py
```

Or run `setup_task.ps1` after updating its Action argument. **NOT YET DONE** — the new orchestrator was smoke-tested via manual invocation today; first scheduled fire will not run it until the task is re-pointed.

Until you re-point the scheduled task: the new strategy runs only when you manually execute `python run_ensemble.py`. The TQQQ position now held is real (paper) and will be managed by future scheduled fires of `run_ensemble.py`. **You should re-point the task before the next NYSE open** so the trailing stop is checked daily — otherwise the position sits unmanaged.

### Open items

- **Re-point scheduled task** to invoke `run_ensemble.py` (above)
- **Verify state persistence across machine restarts** — `data/strategy_state_trend_leveraged_tqqq.json` survives reboots
- **Monitor first real stop-fire event** when it happens — the software-managed stop is new; we want to see it work in the wild
- **Phase 3.2 next**: add `sector_momentum_monthly` + `spy_trend` + regime router. Recommended timing: after `trend_leveraged_tqqq` has 3-4 weeks of paper-trading and at least one full entry/exit cycle.

---

## 2026-05-21 — STRATEGY PIVOT: ensemble per PRD Phase 4+ vision

**TL;DR:** 33-year multi-strategy research showed `sector_rotation_5d` (the live signal) is broken (CAGR 0.62%, Sharpe 0.19). Walk-forward validated a new candidate: TQQQ trend + 50d MA + 5% trailing stop earns ~42% CAGR / Sharpe 1.83 OOS (TEST=1.83 vs TRAIN=1.87, 98% retention). A 3-component regime-routed ensemble earns ~21% CAGR / Sharpe 1.12 / -28% MaxDD over 24 years. **Pivoting to ensemble architecture.**

Full research evidence:
- [research/data/strategy_research_consolidated_2026-05-21.md](research/data/strategy_research_consolidated_2026-05-21.md) — every strategy tested
- [research/data/trailing_stop_walk_forward_report.md](research/data/trailing_stop_walk_forward_report.md) — robustness validation
- [research/data/extended_report.md](research/data/extended_report.md) — extended-window backtest
- [research/data/crisis_decisions_*.csv](research/data/) — day-by-day decisions through dot-com / GFC / COVID / 2022

New design doc: [_bmad-output/planning-artifacts/phase-3-ensemble-design.md](_bmad-output/planning-artifacts/phase-3-ensemble-design.md). Awaiting Rekwa review.

**Actions taken today:**
- `sector_rotation_5d` retired as live signal via `SECTOR_ROTATION_5D_RETIRED = True` flag in [run_trading.py](run_trading.py). Scheduled task still fires but short-circuits cleanly. No new entries until ensemble is built.
- Existing open positions (XLE, XLF) continue to be managed by Exit task until scheduled close.
- 137 tests still passing.

**Open questions for Rekwa — RESOLVED 2026-05-21:**
1. **Capital allocation:** equal 33/33/33 in Phase 3.x paper testing (best Sharpe in backtest; simplest default for measuring per-component contribution). Revisit at Phase 3.3 (pre-live).
2. **MICRO retired from automation; MACRO promoted to regime safety layer.** The new ensemble does NOT consume `theses.jsonl` for trading. MICRO continues to ship Pushovers as personal-awareness tool. MACRO becomes a "veto" layer in the regime router — if MACRO sees red even when SPY > 200d MA, force defensive allocation. See full updated regime router logic in the design doc.
3. **Phase 3 graduation gate replaced.** Old: "50 trades." New: 6-month time floor AND per-component minimums (30 closed trades, ≥1 stop-fired exit, ≥1 MACRO-veto period) AND 30-day operational cleanliness (zero drift, zero ABORT, zero stranded). About VALIDATION not COUNT.
4. **Live capital amount deferred.** Not close to deployment; doesn't bind for Phase 3.0/3.1/3.2 (all paper at $100k). Phase 3.3 design will pin down.
5. **Variant-B ask CLOSED.** Updated MICRO project artifact + filed pivot note to MICRO owner: `../tactical_markets/_bmad-output/planning-artifacts/pivot-note-from-bot-2026-05-21.md`.

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

- Wait for MICRO to ship `theses_variant_b.jsonl` (per the ask doc). **HELD pending 2026-06-10 M1 review.**
- Once shipped (if needed per the 2026-06-10 review), parameterize the bot's entry path to read either ledger via a `--variant` flag, create the second scheduled task, set up `data/trades_variant_b.jsonl` ledger, A/B compare at 30 cumulative trades.
- Apply the Phase 2 → Phase 3 gate tightening (Sharpe- / relative-return-based, replacing the coin-flip-clearable "win rate vs SPY > 50%"). **Done — captured in the 2026-05-20 strategy gate section above.**
- Begin Phase 2 wiring stories (broker-side stops, MACRO size-down, risk-based sizing, kill switch) in the order specified in [epics.md](_bmad-output/planning-artifacts/epics.md). The reconciler is now in place as the safety net.

---

## 2026-05-20 — Epic 1a shipped: Broker-Enforced Stop Orders

**All 5 stories of Epic 1a complete.** Every Phase 2 entry now carries a broker-held stop at 2.5% below fill; exits cancel the stop before market SELL; closed records carry an `exit_reason` distinguishing scheduled / stop_fired / stop_cancel_failed close paths. NFR5 (multi-day VPS outage failsafe) is satisfied.

### Changes

- **Story 1a.1 (compute_stop_price):** already shipped 2026-05-13 in `src/risk.py`. No changes.
- **Story 1a.2 (submit broker-side stop after entry fill):** added `submit_stop(symbol, qty, fill_price)` in `src/order_builder.py`. Computes stop via `risk.compute_stop_price`, submits `StopOrderRequest(side=SELL, time_in_force=GTC)`. On failure: returns `stop_order_id=None`, `stop_rule_used="stop_submission_failed"`, leaves position open (never auto-close), Pushover alerts caller.
- **Story 1a.3 (persist stop fields in entry record):** `log_entry` in `src/trade_logger.py` now calls `submit_stop` after `wait_for_fill` succeeds, persists `stop_order_id`, `stop_price`, `stop_rule_used` in the new entry record.
- **Story 1a.4 (cancel stop at scheduled exit):** new helper `_cancel_stop_and_classify(client, record)` in `src/exit_manager.py`. Handles four paths: (a) cancel succeeds → `exit_reason="scheduled"`, (b) record has no `stop_order_id` (Phase 1 / stop_submission_failed) → skip cancel, `exit_reason="scheduled"`, (c) cancel raises AND position is 0 → `exit_reason="stop_fired"`, looks up the filled stop order for fill data, skips the market SELL, (d) cancel raises AND position still held → `exit_reason="stop_cancel_failed"`, proceeds with market SELL.
- **Story 1a.5 (exit_reason on close):** every closed record now carries `exit_reason`. Phase 1 records read by Phase 2 code use `.get("exit_reason", "scheduled")` for backward compat.

### Tests added (48 → 61 passing)

- `tests/test_order_builder.py` (3 tests) — `submit_stop` happy path, failure metadata, stop-price math matches `compute_stop_price`.
- `tests/test_trade_logger.py` (+2 tests) — `log_entry` persists stop fields on success and on failure.
- `tests/test_exit_manager.py` (+6 tests) — covers all four `_cancel_stop_and_classify` branches plus market-hours guard (Rekwa-added).

### Files touched

- `src/order_builder.py` — added `submit_stop`, imports
- `src/trade_logger.py` — wired `submit_stop` into `log_entry`, added 3 new entry-record fields, `FILL_POLL_TIMEOUT` already bumped earlier this session
- `src/exit_manager.py` — added `_cancel_stop_and_classify`, branched `exit_position` (stop_fired path skips SELL; normal path tags exit_reason)
- `tests/test_order_builder.py` (new), `tests/test_trade_logger.py` (extended), `tests/test_exit_manager.py` (extended)

### What still needs a live smoke test

The Story 1a changes are production-path. Per the new policy, they need a paper-fire smoke test against the real Alpaca API before they ride a scheduled fire. Two scenarios to cover:

1. **Entry-path smoke:** next signal-positive trading day, the scheduled 13:35 UTC fire will exercise `submit_order → log_entry → submit_stop` end-to-end. Verify in `data/trades.jsonl` that the new record has non-null `stop_order_id`, `stop_price`, `stop_rule_used="fixed_pct_2.5"`.
2. **Exit-path smoke (stop cancel):** the next scheduled 13:40 UTC exit fire that closes a Phase 2 record. Verify the stop gets cancelled and `exit_reason="scheduled"` is on the close. (XLE's queued SELL from earlier today is a Phase 1 record — no stop, no cancel attempt; closes via the "no_stop_to_cancel → scheduled" branch.)

If MICRO's M1 multi-thesis emits today/tomorrow, the first Phase 2 entry will land naturally without any manual smoke step needed.

### Open question / known gap

- **Alpaca fractional-qty stop-order support is unverified.** Stop orders may not accept fractional `qty` (only whole shares). If Alpaca rejects, `submit_stop` returns `stop_rule_used="stop_submission_failed"` and the position stays open without a broker stop. The Pushover alert will surface this immediately. If it turns out fractional stops aren't supported, the fix is either (a) floor the qty to whole shares (sacrifices some hedge), or (b) submit two stops (whole + fractional notional sell). Defer until we see the first live attempt.

---

## Next concrete code work

1. **Watch tomorrow's scheduled cycle (2026-05-21 13:30/13:40 UTC).** Verify:
   - XLE SELL fills at open
   - Reconciler at exit-task fire detects local-open-but-Alpaca-no-position, backfills the close
   - If MICRO emits a signal, the entry path exercises Story 1a + 1b end-to-end (first Phase 2 entry with broker-side stop + MACRO snapshot field)
2. **Investigate the 2026-05-14 16:40 UTC Task Scheduler miss** — the BUY for trade `68527bf4` submitted 3 hours late. Check Event Viewer history. If `StartWhenAvailable` is firing tasks when machines wake at random times, the new `_market_is_open()` guard on the exit task handles it, but entries are still at risk.
3. **After tomorrow's live fire validates Stories 1a+1b: ship Epic 1c (risk-based sizing + concentration limits + drawdown kill switch).** This is the biggest semantic change in Phase 2 because risk-based sizing replaces the fixed $10k notional with a qty tied to stop distance. The pure functions are already shipped in `src/risk.py`; the wiring is in `run_trading.py`. Touches the same code paths as Epic 1b so worth letting 1b bake for a few cycles first.

---

## 2026-05-20 — Epic 1b shipped: Regime-Aware Pre-flight (MACRO + Health Checks)

**Stories 1b.1, 1b.2, 1b.3 were already shipped** in `src/macro_consumer.py` on 2026-05-13 (validate, staleness + allow-list, size_multiplier). The wiring work — Stories 1b.4, 1b.5, 1b.6 — landed today.

### Changes

- **Story 1b.4 (preflight module):** new [src/preflight.py](src/preflight.py) with `check_entry()` (5 checks: env keys, Alpaca account, MICRO file freshness, MACRO validate, kill-switch stub) and `check_exit()` (2 checks: env keys, Alpaca account). Short-circuits on first failure. Any check that raises wraps the exception into `preflight_check_X_raised: ...`. Kill-switch check is a placeholder returning OK; real implementation comes with Story 1c.5.
- **Story 1b.5 (wire preflight):** `run_trading.py` calls `preflight.check_entry()` as the first action after `load_env()`; on failure sends Pushover ABORT and `sys.exit(1)`. `src/exit_manager.run_exits()` calls `preflight.check_exit()` analogously.
- **Story 1b.6 (wire MACRO multiplier):** `run_trading.main()` now calls `macro_consumer.validate()` + `size_multiplier()` once per batch, after preflight. If multiplier == 0 (red regime) → skip entries with Pushover info. Otherwise applies multiplier to the fixed $10k notional and passes the adjusted value to `submit_order(thesis, notional=...)`. Entry record gains two new fields:
  - `macro_snapshot`: `{run_timestamp, composite_band, regime, weights_hash, neutralized}` — the regime decision the trade was made under
  - `sizing_rule_used`: `"phase1_fixed"` when multiplier is 1.0, `"phase1_fixed_x_macro_mult"` when scaled. Story 1c.3 will replace this with `"risk_based"` / `"concentration_cap"`.
- **Pushover message expanded** to include MACRO band/regime/multiplier so notifications carry the regime context.

### Tests added (61 → 74 passing)

- `tests/test_preflight.py` (13 tests) — happy-path entry/exit + every failure mode: missing env keys, Alpaca down, account not active, trading_blocked, MICRO file missing/stale, MACRO broken, exception in check, and the explicit "MACRO stale is OK" assertion. Also pins `check_exit` deliberately not depending on MICRO/MACRO (exit task must run when regime data is broken).
- `tests/test_exit_manager.py` (+1 test) — `test_run_exits_aborts_on_preflight_failure` confirms preflight failure short-circuits before reconciler runs.

### Smoke-tested against real environment

`preflight.check_entry()` and `check_exit()` both return `(True, "ok")` against the actual `.env`, Alpaca paper account, MICRO `theses.jsonl` (written today), and MACRO sidecar (currently 30h stale → neutralized, treated as OK). Confirmed MACRO's current regime (`orange / mid`) maps to `size_multiplier = 1.0` via the stale-neutralized path — so tomorrow's entry (if MICRO emits) will trade full size.

### Files touched

- `src/preflight.py` (new)
- `src/order_builder.py` — `submit_order(thesis, notional=NOTIONAL)` now takes optional notional
- `src/trade_logger.py` — `log_entry(order_result, macro_snapshot=None, sizing_rule_used="phase1_fixed")` adds two optional kwargs + persists them
- `src/exit_manager.py` — preflight + ABORT wired at top of `run_exits()`
- `run_trading.py` — preflight + MACRO validate + multiplier + size-scaled notional + macro_snapshot
- `tests/test_preflight.py` (new), `tests/test_exit_manager.py` (extended)

### Open question / known gap

- **MACRO sidecar is currently 30h stale.** It's degrading to neutral as designed (Story 1b.2), but you'll want to ask the MACRO project owner if the daily 07:30 ET refresh is still firing. If not, Phase 2 trades will always run "full size with stale neutralized MACRO" — defeats the point of MACRO size-down. Flag for MACRO project investigation. **(Cross-project — see MACRO investigation note below.)**

---

## 2026-05-20 — MACRO refresh missed today; investigation flagged

While shipping Epic 1b, I checked the MACRO sidecar state:
- `market_dashboard/data/latest.json` `run_timestamp`: **2026-05-19 17:52 UTC** (~30 hours ago at time of check)
- Expected: daily ~07:30 ET (`market_dashboard/TODO.md` says "Daily automation runs at 7:30 AM")
- Today's (2026-05-20) refresh did not fire — analogous to the bot's 2026-05-14 Task Scheduler miss

**No bot-side action — this is a cross-project (MACRO) concern.** Surface to MACRO project owner. The bot itself degrades cleanly: `validate()` returns `(True, "macro_stale_30h_treating_as_neutral", regime_data_with_neutralized=True)`, `size_multiplier` returns 1.0, entries trade full size. But the *point* of MACRO size-down is to scale down during stress regimes, and stale MACRO can never trigger that.

**Action:** Rekwa check MACRO's Task Scheduler history (or whatever automation runs `market_dashboard/`'s daily refresh) and reschedule / debug. Related: the bot's own `_market_is_open` guard could be the right pattern for MACRO if it has a similar "StartWhenAvailable fires off-hours" problem.

---

## 2026-05-20 — Epic 1c shipped: Portfolio Risk Engine

**All 5 stories of Epic 1c complete.** Position sizing is risk-aware (qty derived from account_value, entry_price estimate, and stop_price), concentration limits are enforced pre-trade, and the drawdown auto-pause kill switch is wired into preflight check 5.

### Changes

- **Stories 1c.1, 1c.2 (compute_position_size, check_concentration):** already shipped 2026-05-13 in `src/risk.py`. No changes.
- **Story 1c.3 (wire sizing + concentration):** `run_trading.main()` now:
  1. Fetches `account.equity` from Alpaca
  2. For each thesis, estimates entry via `get_estimated_entry_price(symbol)` (yfinance `history(period="2d").Close.iloc[-1]`)
  3. Computes `stop_price` via `risk.compute_stop_price`
  4. Computes `(qty, sizing_rule_used)` via `risk.compute_position_size`
  5. Applies MACRO multiplier: `final_qty = qty * multiplier`, `sizing_rule_used += "_with_macro_x_{multiplier}"` if scaled
  6. Fetches current positions and runs `risk.check_concentration` — on fail, Pushover info + skip
  7. Submits qty-based `MarketOrderRequest(qty=final_qty)` via refactored `submit_order(thesis, qty=…)`
- **Story 1c.4 (account high-water-mark):** new [src/account_state.py](src/account_state.py) module with `load_or_init(current_equity)` and `update_peak_if_higher(state, current_equity)`. Persists to `data/account_state.json`. Handles corrupt-file recovery by reinitializing with current equity + surfaces reason to caller for optional alerting. `run_trading.main()` updates HWM after each Entry preflight passes.
- **Story 1c.5 (drawdown kill switch):** new `risk.check_kill_switch(current_equity, account_state, threshold=0.20)` — pure function, returns `(ok, reason)`. Wired into `preflight._check_kill_switch` replacing the stub. Trips when drawdown >= 20%; Pushover title becomes "Tactical Trading ABORT: KILL SWITCH"; Exit task continues normally.
- **`order_builder.submit_order` refactored** to accept either `qty` (Story 1c.3) OR `notional` (transitional). Raises if both/neither. Result dict carries `qty` and `notional` (one is None).
- **`trade_logger.log_entry` updated** — new entry-record field `submitted_qty` (the qty we asked Alpaca to fill, None for notional-based); `notional` becomes None on qty-based entries.

### Tests added (74 → 97 passing)

- `tests/test_risk.py` (+7 tests) — `check_kill_switch` happy path, threshold-edge, custom threshold, missing peak, default constant
- `tests/test_account_state.py` (new, 8 tests) — load/init/persist + corrupt-file recovery
- `tests/test_preflight.py` (+3 tests) — kill switch wired into check 5: tripped on drawdown, ok on no-drawdown, initializes state when missing
- `tests/test_order_builder.py` (+5 tests) — `submit_order` qty vs notional dispatch, requires exactly one, `get_estimated_entry_price` returns latest close + raises on empty
- `tests/test_trade_logger.py` (updated) — log_entry now handles qty-based + notional-based shapes

### Smoke-tested against real environment

- `preflight.check_entry()` now returns `(False, "micro_theses_stale: last_mtime=2026-05-20, today=2026-05-21")` because the date rolled over mid-session — correct behavior; MICRO refreshes at ~11:30 UTC today
- `account.equity = $100,221.05` (small positive PnL since session start)
- `account_state.json` initialized at $100,000 peak earlier in session; update_peak_if_higher will bump to $100,221 on the first signal-positive day
- `get_estimated_entry_price("SPY") = $741.25` — works

### Files touched

- `src/risk.py` — added `check_kill_switch` + `KILL_SWITCH_DRAWDOWN_PCT` constant
- `src/account_state.py` (new)
- `src/preflight.py` — replaced kill-switch stub with real implementation
- `src/order_builder.py` — `submit_order(qty | notional)` refactor, added `get_estimated_entry_price` helper
- `src/trade_logger.py` — `submitted_qty` field, handles None `notional`
- `run_trading.py` — full risk-based entry orchestration with concentration check + HWM update
- `tests/test_risk.py`, `tests/test_account_state.py` (new), `tests/test_preflight.py`, `tests/test_order_builder.py`, `tests/test_trade_logger.py`

---

## 2026-05-21 — Epic 2 + Epic 3 shipped; investigations + diagnostics

### Diagnostics from PowerShell / Task Scheduler

- **Task Scheduler Operational log is DISABLED** (`enabled: false` per `wevtutil gl Microsoft-Windows-TaskScheduler/Operational`). That's why fire history is invisible — every "did the task run?" question is currently unanswerable from event logs. **Fix (needs admin):** `wevtutil sl Microsoft-Windows-TaskScheduler/Operational /e:true`. Worth doing — without it, the 2026-05-14 miss and the MACRO refresh miss can't be definitively diagnosed.
- **All tasks' `LastRunTime = 2026-05-19 5:51:18 PM`** across all three projects (Market Dashboard, Tactical Markets, Tactical Trading). That's a bulk re-registration timestamp (`setup_task.ps1 -Force` style), not a real fire signal. After re-enabling the operational log, future LastRunTime values will be meaningful.
- **Power events show evening-only wake/sleep activity** for 5/18–5/19 (6 PM–8 PM range). No morning power events visible in the last 20 events — the machine is probably in deep sleep at 8:20/8:35/8:40 AM CDT. The Wake task with `WakeToRun=True` is supposed to handle this; the operational log would tell us whether it's working.
- **MACRO last refreshed 2026-05-19 17:52 UTC** (scheduled "Market Stress Dashboard" task is configured correctly with NextRunTime 5/21 7:30 AM). Today's 5/20 refresh didn't fire — same pattern as the bot's 5/14 miss.
- **Cross-project follow-ups for Rekwa:**
  - Enable Task Scheduler Operational log (one-time admin action)
  - Check power settings — ensure hibernate/sleep doesn't block scheduled fires (`powercfg /devicequery wake_armed` shows what can wake the machine)
  - The MICRO project's `Tactical Markets Watchdog` task has `LastRunTime = 11/30/1999` (never run) and result `267011` (never ran yet); next fire today 7:00 AM CT. Worth watching.

### Smoke test of wired-up entry path

- `python run_trading.py` cleanly exits on `Preflight FAILED: micro_theses_stale: last_mtime=2026-05-20, today=2026-05-21` — correct (date rolled mid-session; MICRO refreshes ~11:30 UTC).

### Epic 2 (Drift Detection + Loss Discipline) — shipped

- **Story 2.1 (canonical drift events):** new `reconciler.report()` is read-only and returns events with the spec's canonical types: `orphan_position`, `orphan_open_order`, `missing_position`, `missing_stop_order`. Distinct from existing `reconcile()` which is active backfill. Smarter `orphan_open_order` detection: skips in-flight market SELLs whose symbol matches a local open record (those are normal pending exits, not drift).
- **Story 2.2 (drift_log + notify):** `reconciler.notify_drift(events)` appends each event to `data/drift_log.jsonl` with `detected_at` UTC timestamp and sends a single Pushover summary (truncated to 1024 chars). Idempotent on empty input.
- **Story 2.3 (post-task reconciler):** `reconciler.report_and_notify()` convenience wrapper. Wired into the `finally` block of `run_trading.py` `__main__` AND the end of `exit_manager.run_exits()`. Catches drift the cycle itself introduces; non-fatal on failure.
- **Story 2.4 (consecutive-loss kill switch):** new `risk.check_consecutive_losses(trades, threshold=5)`. Sorts closed trades by `exit_time_actual` and trips if the last 5 are all losses. Wired into `preflight._check_kill_switch` alongside the drawdown check. Pushover title becomes "Tactical Trading ABORT: CONSECUTIVE LOSSES" when this trips.
- **Story 2.5 (wash-sale at exit):** `exit_manager._compute_wash_sale(record, all_records, exit_time, pnl)` scans local trades for same-symbol entries in the 30 days before exit. Embeds a `wash_sale` object in every closed record (uniform shape regardless of win/loss). Excludes self and other symbols. Phase 2 is informational; Phase 3 may auto-block re-entries.

### Epic 3 (Graduation Tracking) — shipped

- **Story 3.1 (graduation status):** new [src/graduation.py](src/graduation.py) with `check_status()` returning `{total_closed_trades, stop_fired_exits, macro_size_downs, drift_false_positives, criterion_met, criterion_summary}`. Reads `trades.jsonl` + `drift_log.jsonl`. Counts MACRO size-downs from `macro_snapshot.composite_band` (red=any, orange+high), skipping neutralized records. Current status (smoke-tested): 3/20 closed, 0/2 stop-fired, 0/1 MACRO size-down, 0 drift events (after the tightening fix). Long road to graduation.
- **Story 3.2 (graduation notify):** `notify_if_met()` sends a one-shot Pushover when criterion is first met; idempotent via `data/graduation_state.json` `already_notified: true` flag. Wired into the end of `exit_manager.run_exits()`.

### Tests added (97 → 129 passing)

- `tests/test_reconciler.py` (+8 tests) — all 4 canonical drift types, notify_drift persistence + idempotence + Pushover format, recognizes tracked stop, in-flight exit not flagged
- `tests/test_risk.py` (+7 tests) — `check_consecutive_losses`: under-threshold, breaks-on-winner, trips-on-streak, ignores-open, orders-by-time, custom threshold, default constant
- `tests/test_exit_manager.py` (+6 tests) — `_compute_wash_sale`: no-prior, prior-within-30d, excludes-self, excludes-other-symbols, excludes-outside-window, winner-uniform-shape
- `tests/test_graduation.py` (new, 11 tests) — count each criterion field, files-missing case, criterion logic, notify idempotence

### Smoke tests against real environment

- `graduation.check_status()`: 3 closed / 0 stop-fired / 0 macro-sizedown / 0 drift → criterion_met=False (as expected)
- `reconciler.report()`: 0 drift events after the in-flight-exit fix (was incorrectly flagging XLE's queued SELL as orphan_open_order before the fix)

### Files touched

- `src/reconciler.py` — added `report()`, `notify_drift()`, `report_and_notify()`, new `DRIFT_LOG` constant; CLI gained `--report` flag
- `src/risk.py` — added `check_consecutive_losses` + `CONSECUTIVE_LOSS_THRESHOLD` constant
- `src/preflight.py` — `_check_kill_switch` now runs BOTH drawdown and consecutive-loss checks
- `src/exit_manager.py` — `_compute_wash_sale` helper, wash_sale field on both stop_fired and normal closes, `report_and_notify` hook at end of `run_exits`, graduation hook at end of `run_exits`
- `run_trading.py` — `finally` block calls `report_and_notify`
- `src/graduation.py` (new)
- `tests/test_reconciler.py`, `tests/test_risk.py`, `tests/test_exit_manager.py`, `tests/test_graduation.py` (new)

---

## Phase 2 status as of 2026-05-21

**All Phase 2 epics complete** (1a, 1b, 1c, 2, 3). All wired together. 129/129 tests passing. Live smoke-validated everywhere I could without actually trading.

Next live milestone: today's 13:30/13:35/13:40 UTC scheduled cycle. If MICRO emits, the Entry path will exercise the full stack — preflight (env, Alpaca, MICRO, MACRO, kill-switch+consecutive-loss) → MACRO validate → risk-based sizing → concentration check → submit BUY → wait_for_fill → submit_stop → log_entry → post-cycle drift report. The Exit task will run reconcile → market-hours guard → cancel stops + market SELL → wash-sale compute → drift report → graduation check.

### Known limitations / Phase 2.5 candidates

- **`get_estimated_entry_price` uses yfinance daily bars.** During market hours yfinance returns today's intraday close (= latest tick), which is fine for sizing. Edge case: a fast-moving stock with a 5% intraday move between the price estimate and the actual fill produces a position size that's slightly miscalibrated relative to the actual fill. For Phase 2 / sector ETFs (low intraday vol) this is negligible. Phase 2.5 may switch to Alpaca's `StockHistoricalDataClient.get_stock_latest_trade()` for sub-second freshness.
- **High-water-mark only updates on Entry fires.** During no-signal stretches, peak can lag actual equity. The kill switch then under-reports drawdown (peak too low → drawdown smaller than reality). Acceptable for Phase 2; Phase 3 may want to update HWM on every Exit too.
- **Concentration check fetches positions inside the per-thesis loop.** If MICRO emits 3 theses and the bot enters all 3, each check uses Alpaca state from when the loop started (positions submitted earlier in the loop aren't reflected yet because orders are still ACCEPTED, not filled). Phase 2.5: incrementally update `current_positions` after each successful submission. For now: per-trade caps are unaffected; only open-total cap could be undercounted within a single fire.
- **Drift resolution is manual-only.** v1 of the human-confirmation gate (shipped 2026-05-21) requires running `python src/reconciler.py --resolve-all "reason"` to clear benign drift. Phase 2.5 candidates:
  - **Auto-resolve heuristics:** `orphan_open_order` whose `order_id` is now FILLED/CANCELED in Alpaca history → safe to auto-resolve (the order completed, was real, just transient). `missing_position` for a trade_id that now has matching exit_order_id → similarly safe.
  - **Drift summary command:** `python src/reconciler.py --drift-summary` showing counts by week / by type, both resolved and unresolved. Useful for "is the bot producing more drift over time" trend monitoring.
  - **Pushover-link to the resolve workflow:** the drift Pushover currently just lists event types; could include the `event_id`s so a one-tap-from-phone resolve becomes possible.
- **Fractional-share remainder is uncovered by broker stops.** `submit_stop` floors to whole shares (Alpaca rejects fractional GTC stops); typical remainder is <1 share = ~$20-30 of unprotected position. `exit_position` mitigates by selling Alpaca's actual qty at scheduled exit (cleans up any post-stop-fire residue). True fix needs either (a) Alpaca to allow fractional GTC stops, or (b) a second DAY stop for the fractional remainder resubmitted each day. Both are real Phase 2.5 considerations if the dollar amounts ever grow meaningfully (e.g., live capital sizing produces larger fractional remainders).
- **Reconciler-recovered closes default `exit_reason="scheduled"`.** If a stop ever fires through a reconciler-recovery path (rather than the exit-task path), it gets tagged "scheduled" not "stop_fired" — undercounting in graduation's `stop_fired_exits`. The probability is low (stop fire is detected at exit-task time normally) but non-zero. Phase 2.5: have reconciler distinguish stop-vs-scheduled SELL by querying the order's `order_type` field.

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
