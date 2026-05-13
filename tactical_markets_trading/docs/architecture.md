# Architecture

**Generated:** 2026-05-13 (deep scan). Reflects Phase 1 as built — frozen until 5+ trades validate (lowered from 10 on 2026-05-13).

This is the **current-state** architecture document. The forward-looking architecture (Phase 2 risk-management features, MACRO consumption, Phase 3 live capital) is **not** captured here — write it in a separate `architecture-phase-2.md` or via the `bmad-create-architecture` workflow, layered on top of this baseline.

---

## Executive summary

Single-entrypoint batch CLI. Three Windows Scheduled Tasks fire in sequence each weekday morning: **Wake (08:20)** → **Entry (08:35)** → **Exit (08:40)** all CDT. The Entry task reads a tactical thesis from `../tactical_markets/data/theses.jsonl`, submits one market BUY order via Alpaca's paper-trading API, and logs the entry record. The Exit task scans the trade ledger for positions whose 5-trading-day hold window has expired, market-sells them, and captures benchmark returns (SPY + the original thesis's sell-leg) post-fill.

The architecture is deliberately minimal. There is no signal generation, no risk engine, no portfolio optimizer, no dashboard. The goal is to **prove the simplest possible execution loop works end-to-end**, accumulate ≥5 clean trades, and only then design Phase 2 enrichments (stops, risk-based sizing, MACRO consumption, multi-strategy routing) against real data.

---

## Daily flow

```
08:20 CDT   Tactical Trading Wake          (WakeToRun, cmd.exe /c exit)
              │ wakes laptop from sleep so 08:35/08:40 tasks can fire
              ▼
08:35 CDT   Tactical Trading Entry         (run_trading.py)
              │
              ├── load .env (ALPACA keys, optional PUSHOVER keys)
              ├── read ../tactical_markets/data/theses.jsonl
              │     → today_signal()   filters to today's signal:true record (UTC)
              ├── already_traded(symbol)?
              │     query Alpaca for positions + open orders in this symbol
              │     if yes → skip (idempotency guard, authoritative against local-file drift)
              ├── submit MarketOrderRequest(symbol=buy_leg, notional=$10k, BUY, DAY)
              ├── wait_for_fill(order_id)  — poll every 2s, terminate on FILLED
              │     fail fast on REJECTED/CANCELED/EXPIRED
              ├── log entry to data/trades.jsonl
              │     {trade_id, order_id, symbol, sell_leg, notional, thesis_as_of,
              │      entry_time, fill_price, fill_qty,
              │      exit_time_planned = +5 NYSE trading days,
              │      status: "open"}
              └── Pushover notify (entry / failure)
              ▼
08:40 CDT   Tactical Trading Exit          (src/exit_manager.py)
              │
              ├── load .env
              ├── read data/trades.jsonl   (full file, in-memory)
              ├── for each record where status=="open" and now >= exit_time_planned:
              │       submit MarketOrderRequest(symbol, qty=fill_qty, SELL, DAY)
              │       wait_for_fill()
              │       compute pnl_dollars, pnl_pct
              │       AFTER SELL fills (close persists no matter what):
              │           try: SPY return over [entry_time, exit_time] via yfinance
              │                sell_leg return over same window via yfinance
              │       update record: status="closed" + exit fields + benchmarks
              │       rewrite data/trades.jsonl (in place, all records)
              │       Pushover notify (exit / failure)
              └── if 0 exits processed, log "no open positions due"
```

**Idempotency model:** the Entry task guards against double-buys by querying Alpaca for open positions + open orders in the candidate symbol. The Exit task is idempotent by construction — only `status=="open"` records past `exit_time_planned` get processed; a successful exit flips the row to `closed` and it's skipped on the next run.

**Non-raising close path:** once the SELL has filled, the close record is always persisted to `trades.jsonl`. Benchmark fetches (`yfinance`) run inside a `try/except` after fill and can leave `spy_return_pct` / `sell_leg_return_pct` as `null` without losing the trade record. This is the design from the 2026-05-08 hardening pass.

---

## Components

| Component | Module | Responsibility |
|---|---|---|
| Auth + client factory | [src/alpaca_connector.py](../src/alpaca_connector.py) | Load `.env`, validate keys, return `TradingClient(paper=True)`. The `paper=True` flag is the safety pin against accidental live trading. |
| Signal reader + order builder | [src/order_builder.py](../src/order_builder.py) | Read MICRO's `theses.jsonl`, build `MarketOrderRequest(notional=$10k)`, submit. |
| Fill polling + ledger writer | [src/trade_logger.py](../src/trade_logger.py) | Wait for `OrderStatus.FILLED` (fail-fast on terminal states), append entry record, compute NYSE-aware planned exit. |
| Exit orchestrator | [src/exit_manager.py](../src/exit_manager.py) | Iterate ledger, exit ripe positions, capture SPY + sell-leg benchmarks, rewrite ledger. |
| Notifications | [src/pushover.py](../src/pushover.py) | Minimal Pushover HTTP client; non-fatal if not configured. |
| Entry orchestration | [run_trading.py](../run_trading.py) | Top-level Entry task — wires the above together + Pushover error reporting. |
| Schedule | [setup_task.ps1](../setup_task.ps1) | Register 3 Windows Scheduled Tasks (Wake/Entry/Exit) with correct battery flags. |

**No cross-component coupling beyond explicit imports.** `exit_manager.py` reuses `wait_for_fill` from `trade_logger.py` and the client factory from `alpaca_connector.py`. The dependency graph is a shallow DAG.

---

## Locked design decisions (Phase 1)

These were debated and settled in the 2026-05-08 design pass. **Do not re-open without explicit user sign-off.**

| Topic | Decision | Rationale |
|---|---|---|
| Shorts | **Never.** Long-only or cash only. | Durable user preference — infinite-downside risk avoided. Recorded in user memory. |
| Hypothesis | Long-only momentum on sector winners outperforms buy-and-hold SPY | Original ROADMAP's pair-trade hypothesis is non-testable under the no-shorts rule. Phase 1 tests a related long-only hypothesis instead. |
| Account | Alpaca paper, $100k, `PA3SOYDP6IP5`. `paper=True` flag in `TradingClient`. | Free, no real capital risk during validation. |
| Sizing | **Fixed $10k per trade** (10% of account, fractional shares via Alpaca `notional`) | No stops in Phase 1 → can't compute risk-based sizing. Fixed dollar makes per-trade P&L directly comparable. |
| Order type | **Market orders** at entry AND exit | Slippage optimization deferred. Execution simplicity > marginal bps savings during validation. |
| Hold | **5 trading days** (NYSE-aware) | Matches the documented sector-rotation mean-reversion window (3-7 days). |
| Stops / targets | **None** | Phase 1 characterizes the signal. Stops introduce a confound (where do you set them?) that contaminates validation. After ~5 trades the drawdown distribution will be visible and stops can be sized empirically. |
| Concurrency | Up to **5 overlapping positions** | Steady state ≈ 50% deployed, 50% cash. Caps over-concentration. |
| Benchmarks | At exit, capture (a) SPY return and (b) sell-leg ticker return over the same window | (b) lets us reconstruct the pair-trade Sharpe post-hoc, even though we never short. |
| Approval | **Fully automated** (no manual click-to-execute) | Tests the signal, not Rekwa's discretionary judgment. Manual approval reintroduces contamination. |
| MACRO consumption | **Not in Phase 1.** May read MACRO's `data/latest.json` in Phase 2 for size-down logic when band is red. | Stand-alone first; integrate after validation. |
| Tests directory | **Deferred.** Inline `__main__` smoke runs suffice. | Phase 1 surface area is small; tests are a Phase 2+ concern. |
| Real money | **Not until 50+ paper trades validate edge AND rules-of-engagement doc is written.** | Hard floor. |

These are also captured in [TODO.md](../TODO.md) "Locked rules" + [_bmad-output/project-context.md](../_bmad-output/project-context.md) for AI-agent enforcement.

---

## Scope boundaries

### In scope (Phase 1)

- Reading one signal/day from MICRO via files-on-disk
- One market BUY per signal day (long leg only)
- 5-trading-day hold
- Market SELL at exit
- Post-fill SPY + sell-leg benchmark capture
- Append-only trade ledger
- Pushover notifications on entry, exit, and every failure path
- Windows Task Scheduler-driven automation
- Alpaca paper account only

### Explicitly out of scope (Phase 1 — deferred to Phase 2+)

- Stops, profit targets
- Risk-based sizing (Kelly, % risk, drawdown-conditional)
- Confidence-weighted sizing
- Limit orders (entry or exit)
- Slippage modeling / calibration
- Multiple strategies (the PRD's "11+ strategy ensemble" is Phase 2/3+)
- Regime-aware routing (MACRO consumption)
- Multi-thesis days (signal envelope >1)
- HTML dashboard / live P&L view (PRD's FR15-16 — Phase 2+)
- Kill switch with auto-disable thresholds
- Tax CSV export
- Live (real-capital) trading
- Shorts, options, leverage, margin — **shorts are forbidden forever, not deferred**
- Crypto (PRD Tier 3) — Phase 2/3+
- Single-stock universe (PRD Tier 2) — Phase 2/3+

### PRD vs. reality

The [PRD](../_bmad-output/planning-artifacts/prd.md) describes the **end-state vision** (FR1–FR20, 11+ strategies, regime routing, dashboard, kill switch, tax export). The validation report rates it 4/5 GOOD and "implementable" — but that's PRD-internal consistency, not PRD-to-Phase-1 fit. Architectural work should treat the PRD as the **north star** and Phase 1 as the **starting point**. Phase 2 design will be a delta against this document, narrowing the PRD's vision into the next validated increment.

---

## Failure modes and how they're handled

| Failure | Detection | Handling |
|---|---|---|
| No signal in `theses.jsonl` today | `today_signal()` returns `None` | Exit clean, no order, no Pushover (silent no-op is fine — MICRO already pinged user) |
| Already have exposure in `buy_leg` | `already_traded(symbol)` returns `True` | Skip, log "Already have an open position…", exit clean |
| Order REJECTED / CANCELED / EXPIRED | `wait_for_fill` checks `TERMINAL_FAILED` set | Raise `RuntimeError`, caught at top-level, Pushover "ENTRY FAILED" |
| Order doesn't fill within 60s | `wait_for_fill` timeout | Raise with last status, Pushover "ENTRY FAILED" |
| Partial fill mid-poll | `wait_for_fill` does NOT return on first partial — only on `OrderStatus.FILLED` | Continues polling; this is the fix from commit `58fa2e1` |
| `yfinance` fails during exit benchmark capture | `try/except` in `exit_position` after SELL fills | Record persists with `spy_return_pct=null, sell_leg_return_pct=null` |
| Top-level crash in Entry or Exit | `try/except` at entrypoint | Pushover with the exception message, then re-raise |
| Pushover not configured | `pushover.send` returns `False` after printing `[pushover not configured]` | Non-fatal; trade still executes |
| Alpaca connection drops mid-poll | `get_order_by_id` exception | Propagates up; Pushover "ENTRY FAILED" / "EXIT CRASHED" |
| Local `trades.jsonl` out of sync with Alpaca | `already_traded` queries Alpaca, not the file | Self-correcting at next Entry run |
| Holiday / early close | NYSE calendar via `pandas_market_calendars` | `add_trading_days` skips non-trading days correctly (Memorial Day verified) |

---

## Persistence

| Path | Format | Purpose |
|---|---|---|
| [`data/trades.jsonl`](../data/trades.jsonl) | Append-only JSONL + in-place updates on exit | The only stateful artifact this project owns. Full schema in [data-models.md](./data-models.md). |
| `.env` | Key=value | Alpaca + Pushover credentials. **Never commit.** |

No database. No cache layer. No tests directory. The Windows Task Scheduler state is a stateful artifact but lives in the OS, not the project.

---

## Cross-project contracts

This project sits **downstream** of MICRO and (eventually) MACRO. See [integration-architecture.md](./integration-architecture.md) for the full contract details. Summary:

- **Inbound from MICRO:** read `../tactical_markets/data/theses.jsonl` for entry signals. Files-on-disk only. No Python imports. Schema documented in MICRO's [docs/data-models.md](../../tactical_markets/docs/data-models.md).
- **Inbound from MACRO:** not consumed in Phase 1. Phase 2 may read `../market_dashboard/data/latest.json` (sidecar shipped via MACRO's Brief 24, commit `2046161`). Stable contract documented in MACRO's [integration brief](../../market_dashboard/_bmad-output/planning-artifacts/integration-brief-for-tactical-bot.md).
- **Outbound to Alpaca:** REST API via `alpaca-py` SDK. Paper-trading endpoint. Order submission + fill polling + position checks.
- **Outbound to Pushover:** HTTP POST for entry / exit / failure notifications. Non-fatal if not configured.
- **Outbound to yfinance:** SPY + sell-leg historical close prices for benchmark capture at exit. Failure is logged and tolerated.

---

## Tech stack

| Category | Choice | Notes |
|---|---|---|
| Runtime | Python 3.14 (system; own `.venv/`) | Created Day 1 of Phase 1. |
| Broker SDK | `alpaca-py` | `TradingClient`, `MarketOrderRequest`, `OrderSide`, `TimeInForce`, `OrderStatus`, `QueryOrderStatus`, `GetOrdersRequest`. |
| Config / secrets | `python-dotenv` | `.env` at project root. |
| Calendar | `pandas-market-calendars` | NYSE valid_days for the +5-trading-days exit math. |
| Data | `yfinance` | Benchmark return capture at exit time only. Not on the entry path. |
| HTTP | `requests` | Pushover only. |
| Scheduling | Windows Task Scheduler (3 tasks) | `setup_task.ps1` registers them. |
| Persistence | Append-only JSONL files | `data/trades.jsonl`. |

No dependencies on the sibling projects (verified by absence of cross-project Python imports). The cross-project boundary is filesystem-only.

---

## Open questions feeding Phase 2 design

From [TODO.md](../TODO.md) "Design fork points":

- After ~5 clean trades: review trade distribution, decide whether to add stops, change sizing, or move to Phase 2 (refined risk management).
- Trading-day calendar edge cases: long weekends, early closes, halts, ETF rebalances. If 5-trading-day exit math gets weird in practice.
- Surprise in results: if win rate is dramatically above or below expectation, the hypothesis or the signal might need revisiting.
- Phase 2 → Phase 3: writing the rules-of-engagement document, picking the live-capital amount, deciding what (if anything) gets sized differently.

From the [Phase 1 lessons in TODO.md](../TODO.md):

- Minimize lag between decision and API call.
- Test the scheduled path against the real API before unattended runs.
- Optimize the polling state machine for unambiguous final states.
- Add a post-fire reconciliation pass comparing local `trades.jsonl` to actual Alpaca state.

These are inputs for the **next** architecture document (Phase 2), not this one.
