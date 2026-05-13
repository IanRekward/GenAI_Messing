---
stepsCompleted: [1, 2, 3, 4]
status: 'complete'
completedAt: '2026-05-13'
epicCount: 5
storyCount: 24
inputDocuments:
  - "_bmad-output/planning-artifacts/prd.md"
  - "_bmad-output/planning-artifacts/architecture.md"
  - "_bmad-output/planning-artifacts/prd-validation-report.md"
  - "_bmad-output/project-context.md"
  - "docs/architecture.md"
  - "docs/data-models.md"
  - "docs/integration-architecture.md"
scope: 'phase-2-implementation'
baseline: 'Phase 1 BUILT and FROZEN until 5+ trades (lowered from 10 on 2026-05-13); epics herein are Phase 2 forward-looking'
date: '2026-05-13'
---

# tactical_markets_trading — Epic Breakdown

## Overview

This document provides the epic and story breakdown for **Phase 2** of tactical_markets_trading, decomposing requirements from the PRD and Phase 2 architecture into implementable stories.

**Scope:** Phase 2 implementation, layered on top of Phase 1 (BUILT, FROZEN until ≥5 clean trades — lowered from 10 on 2026-05-13). Phase 3 (live capital) and Phase 4+ (end-state vision) are acknowledged as future scope but are NOT decomposed into stories here.

## Requirements Inventory

### Functional Requirements

**Signal Consumption & Routing:**

- **FR1:** Bot consumes market regime signals from MACRO on every pre-market run (6:30 AM ET). Regime values: "bull" (growth), "bear" (defensive), "stress" (cash). Used to scale position allocation.
- **FR2:** Bot consumes tactical sector theses from MICRO on every pre-market run. Each thesis includes: symbol, direction, entry price, stop, target, hold window, confidence score. Theses expire after hold window elapses. *(Reality vs PRD: MICRO emits subset only — `buy`, `sell`, `spread_pct`, `as_of`. Stops/targets computed locally per architecture D2.)*
- **FR3:** If MACRO or MICRO unavailable (>1 hour staleness or API error), bot logs alert and disables new trade execution. Outstanding positions remain open; exits execute on pre-programmed rules.
- **FR4:** Bot auto-routes strategy allocation based on regime. Bull → 60% momentum + 40% breakout; bear → 70% mean-reversion + 30% defensive; stress → 80% cash + 20% carry. *(Phase 4+ — Phase 2 implements coarser two-tier MACRO size-down only.)*

**Trade Execution & Management:**

- **FR5:** Bot generates pre-market trade list (3–5 theses max) showing: symbol, entry price, quantity, stop, target, expected hold window, confidence, reasoning. *(Phase 4+ — dashboard UI deferred.)*
- **FR6:** User reviews dashboard and clicks "Execute" to submit orders. Limit orders within 5 bps with 60-sec TTL. *(REJECTED — automated entries locked per TODO.md; Phase 3 may add pre-flight confirmation gate.)*
- **FR7:** Limit order fill/expiry handling. *(Phase 2.2+ — Phase 2 uses market orders + broker-side stops.)*
- **FR8:** For each open position, bot tracks: entry price, quantity, entry time, target, stop, hold expiry; updates P&L continuously during market hours.
- **FR9:** Position exits automatically on first-trigger-wins: (a) target → "target exit"; (b) stop → "stop exit"; (c) hold window → "timeout exit"; (d) manual kill switch → "manual pause exit".
- **FR10:** On exit, bot logs: exit timestamp, exit price, exit reason, P&L $, P&L %, slippage, tax term, wash-sale flag.

**Position Sizing & Risk Controls:**

- **FR11:** Position size = (account_value × 2%) / (entry_price − stop_price); capped at 5% of account; adjusted for spread if >0.1%.
- **FR12:** Pre-order checks: (a) sufficient buying power; (b) position ≤ 5% of account; (c) total open ≤ 20%; (d) no ticker > 25% of account.
- **FR13:** Kill switch pauses trading if: single-trade loss >5%, win rate <48% (rolling 10), max drawdown >25%, account equity <$5k. Manual intervention to resume.
- **FR14:** Pattern Day Trading (PDT): for accounts <$25k, max 3 round-trips per 5-day window. *(Phase 3 only — paper account doesn't enforce PDT.)*

**Reporting & Logging:**

- **FR15:** Dashboard displays real-time: account equity, cash, open positions with P&L %, running win rate, Sharpe (30-day), max drawdown. *(Phase 4+.)*
- **FR16:** Daily 5 PM ET report: trades executed, fills, exits, daily P&L, cumulative P&L, signal execution rate. *(Phase 3+.)*
- **FR17:** Trade log CSV: symbol, entry/exit datetime+price, qty, P&L $/%, slippage bps, tax term, wash-sale flag, strategy family, signal stack reasoning. *(Phase 2 records schema fields; CSV export Phase 3+.)*
- **FR18:** Weekly summary: rolling win rate (10/30/90 windows), Sharpe (30-day), max drawdown, largest winner/loser, strategy family breakdown. *(Phase 3+.)*

**Backtesting & Validation:**

- **FR19:** Backtesting module with historical scenarios (2015–2026), taxes, fees, slippage, wash-sale adjustments, walk-forward (80/20). *(Phase 4+ — research/ scripts stay off-production-path.)*
- **FR20:** Backtest output: Sharpe, win rate, max drawdown, monthly returns, strategy family performance, sensitivity analysis. *(Phase 4+.)*

### Non-Functional Requirements

**Performance:**

- **NFR1:** Dashboard <500ms P&L latency during market hours; daily reporting complete by 4:05 PM ET. *(Phase 4+.)*
- **NFR2:** MACRO/MICRO API calls complete <2s (95th percentile); >5s falls back to cached signal. *(Phase 2 — MACRO via file is on-disk; MICRO read is fast.)*
- **NFR3:** Backtests complete <5 min for 10-year dataset; walk-forward <10 min. *(Phase 4+.)*

**Reliability & Uptime:**

- **NFR4:** 99% uptime during market hours; outages >5 min trigger alert.
- **NFR5:** If VPS connection drops mid-market, positions auto-exit on target/stop/hold-window regardless (failsafe mode). **(Phase 2 critical — broker-side stops.)**
- **NFR6:** Signal freshness: MACRO/MICRO <1 hour; >2 hours staleness → alert + disable new entries.

**Security & Data Protection:**

- **NFR7:** API keys in encrypted environment, not in code. Credentials never logged in plaintext. *(Phase 1 baseline — `.env`.)*
- **NFR8:** Trade logs / P&L on bot's VPS, not cloud, unless explicitly exported. No third-party telemetry without consent. *(Phase 1 baseline.)*
- **NFR9:** Dashboard accessible only locally (localhost or VPS-bound private network). No public endpoints. VPS access via cryptographic key auth. *(Phase 4+ — no dashboard yet.)*

**Fault Tolerance:**

- **NFR10:** If MACRO unavailable, continue with last-known regime (cache 2 hours). If MICRO unavailable, manage open positions; no new theses.
- **NFR11:** Partial order fills handled: open position with actual fill qty; exit rules scale proportionally. *(Phase 1 baseline — `wait_for_fill` terminates only on FILLED.)*
- **NFR12:** Network retry: transient errors (timeout, 5xx) retry 3x with exponential backoff (1s/2s/4s). Permanent errors (401/403/404) escalate.

### Additional Requirements (from Architecture)

**Hard locked constraints (apply forever):**

- **AR1:** No shorts, ever. Long-only or cash only. Removes pair-trade hypothesis from solution space.
- **AR2:** No Python imports across siblings. All sibling integration via files-on-disk.
- **AR3:** `paper=True` safety pin in `TradingClient` remains until 50+ paper trades validated + rules-of-engagement doc written.
- **AR4:** Audit trail per trade — every decision (sizing, stop, regime size-down) reconstructable from `data/trades.jsonl`.

**Phase 2 architecture-specific requirements:**

- **AR5:** Broker-side stop-sell orders at entry fill (NFR5 failsafe; survives multi-day VPS outage).
- **AR6:** Stop level rule: fixed-percentage drawdown from entry fill, default 2.5%.
- **AR7:** Sizing rule: `min(risk-based, 5% concentration cap)`; log `sizing_rule_used` per trade.
- **AR8:** Concentration limits enforced pre-trade: ≤5% per trade, ≤20% open total, ≤25% per ticker.
- **AR9:** MACRO size-down: `composite_band == red` → block; `composite_band == orange AND regime == high` → 0.5x; otherwise full.
- **AR10:** MACRO staleness 4-hour hard reject threshold (Phase 2 architectural decision; tighter than PRD's NFR6).
- **AR11:** Two-tier MACRO failure recovery: stale → neutral (full size); broken/missing → block.
- **AR12:** MACRO provenance allow-list (`data/macro_weights_allowlist.json`); unknown `weights_hash` blocks.
- **AR13:** Kill switch (Phase 2 primitive): drawdown 20% auto-pause + 5 consecutive-loss counter.
- **AR14:** Pre-flight health check at top of Entry and Exit tasks (5 conditions: .env, Alpaca account, MICRO file freshness, MACRO validation, kill switch state).
- **AR15:** Reconciler ships dry-run-only Phase 2; no autonomous correction.
- **AR16:** Wash-sale schema recorded in `trades.jsonl` for all losing closes; enforcement Phase 3.
- **AR17:** Module boundaries: `src/risk.py`, `src/macro_consumer.py`, `src/preflight.py`, `src/reconciler.py` (Phase 2.1). `run_trading.py` stays ≤120 lines post-Phase-2.
- **AR18:** Trade ledger schema v2 additive: new fields `stop_order_id`, `stop_price`, `stop_rule_used`, `sizing_rule_used`, `macro_snapshot`, `exit_reason`, `wash_sale`. No `schema_version` field yet.
- **AR19:** Testing framework: `pytest` in `tests/` directory. First tests: `test_risk.py`, `test_macro_consumer.py`, `test_preflight.py`.

**Phase 2 graduation criterion (must validate before Phase 3):**

- **AR20:** ≥20 paper trades with ≥2 stop-triggered exits verified against broker fills, ≥1 MACRO size-down observed, zero reconciliation false-positives.

### UX Design Requirements

*(Not applicable — no UX spec exists. Dashboard/UI is Phase 4+. Phase 2 stays headless with stdout + Pushover only.)*

### FR Coverage Map

**Phase 2 epic coverage:**

| Requirement | Epic | Notes |
|---|---|---|
| FR1 (MACRO regime consumption) | Epic 1b | |
| FR3 (signal unavailability) | Epic 1b | |
| FR4 (regime-based routing) | Epic 1b | Partial — coarse two-tier size-down only; full ensemble routing Phase 4+ |
| FR9 (auto-exit on stop/timeout) | Epic 1a | Broker-side stops + scheduled timeouts |
| FR10 (exit logging) | Epic 1a | `exit_reason` field on close records |
| FR11 (risk-based sizing) | Epic 1c | |
| FR12 (pre-trade concentration checks) | Epic 1c | |
| FR13 (kill switch) | Epic 1c + Epic 2 | Drawdown in 1c; consecutive-loss in 2; full Sharpe/win-rate in Phase 3+ |
| FR17 (trade log fields) | Epic 1a + Epic 2 | Phase 2 records the fields; CSV export Phase 3+ |
| NFR2, NFR6, NFR10 (signal freshness, caching, fault tolerance) | Epic 1b | |
| NFR5 (failsafe / multi-day outage) | Epic 1a | **Critical** — broker-side stops |
| AR5, AR6, AR18 (entry-side) | Epic 1a | Broker stops, fixed-pct rule, schema entry fields |
| AR9, AR10, AR11, AR12, AR14 | Epic 1b | MACRO size-down, staleness, failure recovery, allow-list, preflight |
| AR7, AR8, AR13 (drawdown) | Epic 1c | Sizing rule, concentration limits, drawdown kill switch |
| AR4 (audit), AR13 (consecutive-loss), AR15, AR16, AR18 (close-side) | Epic 2 | Reconciler, consecutive-loss kill, wash-sale, schema close fields |
| AR20 (graduation criterion) | Epic 3 | |
| AR1, AR2, AR3 (hard constraints) | All epics | Applied per-story; no shorts, no cross-sibling imports, paper=True |
| AR17, AR19 (modules + tests) | All epics | Distributed across module-creation stories |

**Phase 2 scope confirmation:**

| Status | Items |
|---|---|
| **In scope (this document):** | All FRs, NFRs, ARs mapped above. |
| **Out of scope — Phase 3+:** | FR14 (PDT), FR16 (daily report), FR17 CSV export, FR18 (weekly summary), full FR13 (Sharpe/win-rate kill switch), NFR9 (dashboard local-only — no dashboard yet). |
| **Out of scope — Phase 4+:** | FR4 full (11+ strategy ensemble), FR5 (pre-market trade list display), FR15 (real-time dashboard), FR19/20 (backtest module integration), NFR1 (dashboard latency), NFR3 (backtest perf). |
| **Phase 1 baseline (continues, no new epic):** | FR2 (MICRO subset consumption), FR8 (position tracking), NFR7 (encrypted creds), NFR8 (local storage), NFR11 (partial fills). |
| **Rejected:** | FR6 (manual Execute UI — automated locked per TODO.md; Phase 3 may add pre-flight confirmation gate). |
| **Deferred — Phase 2.2:** | FR7 (limit orders), NFR12 (network retry with exponential backoff). |

## Epic List

### Epic 1a: Broker-Enforced Stop Orders

**Goal:** Every Phase 2 position carries a broker-held stop order at 2.5% below entry. NFR5 failsafe satisfied — positions never bleed unbounded during VPS outage. Closed records carry an `exit_reason`.

**FRs covered:** FR9 (partial — stop/timeout exits), FR10
**NFRs covered:** NFR5 (critical)
**ARs covered:** AR5, AR6, AR18 (entry-side fields)
**Files touched:** `src/risk.py` (compute_stop_price only), `src/order_builder.py` (stop submission after entry fill), `src/exit_manager.py` (stop cancel + exit_reason), `src/trade_logger.py` (entry schema v2 fields), `tests/test_risk.py` (stop math)

### Epic 1b: Regime-Aware Pre-flight (MACRO + Health Checks)

**Goal:** Every Entry fire validates Alpaca + MICRO file freshness + MACRO state before any trade decision. Bot blocks new entries on red regime, degrades to neutral on stale MACRO, refuses to act on broken/unknown MACRO state.

**FRs covered:** FR1, FR3, FR4 (partial — coarse tier)
**NFRs covered:** NFR2, NFR6, NFR10
**ARs covered:** AR9, AR10, AR11, AR12, AR14
**Files touched:** `src/macro_consumer.py` (new), `src/preflight.py` (new), `src/risk.py` (size_multiplier), edits to `run_trading.py` + `src/exit_manager.py`, `data/macro_weights_allowlist.json` (new), `tests/test_macro_consumer.py` + `tests/test_preflight.py`

### Epic 1c: Portfolio Risk Engine (Sizing + Concentration + Drawdown Kill Switch)

**Goal:** Position sizes are risk-aware and capped by concentration limits. Pre-trade checks block oversized or over-concentrated trades. Bot auto-pauses new entries on 20% drawdown from account high-water-mark.

**FRs covered:** FR11, FR12, FR13 (drawdown)
**ARs covered:** AR7, AR8, AR13 (drawdown trigger)
**Files touched:** `src/risk.py` (compute_position_size, check_concentration, check_kill_switch), edits to `run_trading.py`, `data/account_state.json` (new), `tests/test_risk.py` (extended)

### Epic 2: Drift Detection + Loss Discipline (Phase 2.1)

**Goal:** After every Entry/Exit fire, the bot compares Alpaca state to local ledger and alerts on drift (dry-run only). Consecutive-loss kill switch catches slow-bleed regime before drawdown threshold. Every losing close records wash-sale metadata.

**FRs covered:** FR13 (consecutive-loss), FR17 (wash_sale fields)
**ARs covered:** AR4 strengthened, AR13 (consecutive-loss), AR15, AR16, AR18 (close-side fields)
**Files touched:** `src/reconciler.py` (new), `src/risk.py` (consecutive-loss check), `src/exit_manager.py` (wash_sale at close), `data/drift_log.jsonl` (new), `tests/test_reconciler.py`

### Epic 3: Phase 2 Graduation Tracking

**Goal:** Reporting tool tracks progress toward Phase 2 graduation criterion (20+ trades, ≥2 stop exits, ≥1 MACRO size-down, zero reconciliation false-positives). Pushover when met, opening Phase 3 design.

**ARs covered:** AR20
**Files touched:** `src/graduation.py` (new), light hook into Exit task to invoke check post-fire, optional `tests/test_graduation.py`

### Epic dependency flow

```
Epic 1a (stops)              ←  standalone; depends on Phase 1 baseline only; ships first
Epic 1b (MACRO + preflight)  ←  standalone; can ship before or after 1a
Epic 1c (sizing/conc/kill)   ←  builds on 1a (uses stop_price for risk math) and 1b (uses size_multiplier)
Epic 2 (drift + loss)        ←  builds on 1a (reconciler checks stop orders)
Epic 3 (graduation)          ←  needs 1a/1b/1c/2 all live to count anything
```

---

## Epic 1a: Broker-Enforced Stop Orders

**Goal:** Every Phase 2 position carries a broker-held stop-sell order at 2.5% below the entry fill price. NFR5 failsafe satisfied — positions exit at the stop even during a multi-day VPS outage. Closed records carry an `exit_reason`.

### Story 1a.1: Compute stop price from entry fill (pure function)

As the operator (Rekwa),
I want a pure function that computes a stop price from an entry fill and a configurable percentage,
So that the stop-level rule is deterministic, testable, and isolated from broker logic.

**Acceptance Criteria:**

**Given** an entry fill price and a `stop_pct` parameter
**When** `risk.compute_stop_price(fill_price, stop_pct)` is called
**Then** it returns `round(fill_price * (1 - stop_pct), 2)`
**And** the function has no I/O or Alpaca dependencies (pure)

**Given** `stop_pct` is not provided
**When** `risk.compute_stop_price(fill_price)` is called
**Then** it defaults to 0.025 (2.5%)
**And** the default matches architecture Decision 2

**Given** `fill_price` is 91.35
**When** `compute_stop_price(91.35)` is called
**Then** it returns 89.07 (= round(91.35 × 0.975, 2))

**Given** `tests/test_risk.py` is run
**When** the test suite executes
**Then** at least 3 assertions cover this function (default, custom percentage, rounding edge cases)

### Story 1a.2: Submit broker-side stop-sell order after entry fill

As the operator (Rekwa),
I want a stop-sell order placed at the broker immediately after the entry order fills,
So that the position is protected by Alpaca's stop logic even if my VPS or Task Scheduler goes down.

**Acceptance Criteria:**

**Given** an entry market BUY has filled (returned `fill_price`, `fill_qty`)
**When** `order_builder.submit_order(thesis)` completes the entry submission
**Then** the function computes `stop_price = risk.compute_stop_price(fill_price)`
**And** submits an `alpaca.trading.requests.StopOrderRequest(symbol, qty=fill_qty, side=SELL, stop_price=stop_price, time_in_force=GTC)`
**And** returns the `stop_order_id` alongside the existing entry result fields

**Given** the stop-sell submission fails (Alpaca returns error)
**When** the failure is detected
**Then** the entry is logged with a `stop_order_id` of `null` and `stop_rule_used: "stop_submission_failed"`
**And** a Pushover alert is sent: "Stop order submission FAILED for {symbol}"
**And** the entry position remains open (do NOT auto-close — surface to human)

**Given** `paper=True` is set in `alpaca_connector.trading_client()`
**When** the stop order is submitted
**Then** the order is routed to Alpaca paper-trading (no real money at risk)

### Story 1a.3: Persist stop fields in entry record

As the operator (Rekwa),
I want stop metadata recorded in `data/trades.jsonl` at entry time,
So that I can audit which stop rule was used per trade and the Exit task can find the stop order to cancel.

**Acceptance Criteria:**

**Given** an entry order has filled and a stop-sell order has been submitted
**When** `trade_logger.log_entry(order_result)` writes the entry record
**Then** the JSON record includes the additive fields: `stop_order_id`, `stop_price`, `stop_rule_used: "fixed_pct_2.5"`
**And** all Phase 1 fields are preserved unchanged

**Given** the stop submission failed (per Story 1a.2)
**When** the entry is logged
**Then** `stop_order_id` is `null`, `stop_price` is the computed value, `stop_rule_used` is `"stop_submission_failed"`

**Given** a Phase 1 record exists in `trades.jsonl` (no stop_* fields)
**When** Phase 2 code reads it
**Then** the code uses `record.get("stop_order_id", None)` and tolerates the missing field without error

### Story 1a.4: Cancel stop order at scheduled exit time

As the operator (Rekwa),
I want the Exit task to cancel the broker-held stop order before submitting the scheduled market SELL,
So that we don't double-sell when the position is closed at the planned exit time.

**Acceptance Criteria:**

**Given** an open trade record has `stop_order_id` set and `now >= exit_time_planned`
**When** `exit_manager.exit_position(record)` is called
**Then** it first calls `trading_client.cancel_order_by_id(record["stop_order_id"])`
**And** waits briefly (≤2s) for cancellation confirmation
**And** then submits the market SELL for `fill_qty` shares

**Given** the cancel call raises (e.g., order already filled by stop firing)
**When** the cancel exception is caught
**Then** the Exit task queries Alpaca for current position size for the symbol
**And** if position size is 0 → position is already gone; log `exit_reason: "stop_fired"` and skip the SELL
**And** if position size > 0 → log `exit_reason: "stop_cancel_failed"` and proceed with market SELL

**Given** `stop_order_id` is `null` on a record (Phase 1 entry, or Story 1a.2 fallback)
**When** the Exit task processes that record
**Then** it skips the cancel step entirely and proceeds with market SELL as Phase 1 did

### Story 1a.5: Record exit_reason on close

As the operator (Rekwa),
I want every closed record in `trades.jsonl` to carry an `exit_reason` field,
So that I can distinguish broker-triggered stops from scheduled exits and from failed cancels when reviewing trade history.

**Acceptance Criteria:**

**Given** an exit completes successfully through the scheduled path
**When** the close record is written
**Then** it includes `exit_reason: "scheduled"`

**Given** the cancel raises and Alpaca reports position size is 0
**When** the close record is written
**Then** it includes `exit_reason: "stop_fired"`, `exit_time_actual` reflects Alpaca's recorded stop fill time, and `exit_fill_price` is Alpaca's stop fill price

**Given** the cancel raises but the position is still open and the market SELL fills
**When** the close record is written
**Then** it includes `exit_reason: "stop_cancel_failed"`

**Given** a closed record from Phase 1 (no `exit_reason` field)
**When** Phase 2 code reads it
**Then** the code uses `.get("exit_reason", "scheduled")` for backward compatibility

---

## Epic 1b: Regime-Aware Pre-flight (MACRO + Health Checks)

**Goal:** Every Entry fire validates Alpaca + MICRO file freshness + MACRO regime state before any trade decision. Bot blocks new entries on red regime; degrades to neutral on stale MACRO; refuses to act on broken/unknown MACRO state.

### Story 1b.1: Read and validate MACRO sidecar — schema and content checks

As the operator (Rekwa),
I want a MACRO consumer module that reads `../market_dashboard/data/latest.json` and validates its schema and content,
So that I never trade on malformed or schema-broken regime data.

**Acceptance Criteria:**

**Given** the file `../market_dashboard/data/latest.json` exists and is well-formed
**When** `macro_consumer.validate()` is called
**Then** it returns `(True, "ok", regime_data_dict)` if `schema_version == 1`, `errors[]` is empty, `composite` is in [0, 100], and required fields are present
**And** `regime_data_dict` includes at minimum `composite_band`, `regime`, `run_timestamp`, `weights_hash`

**Given** the file is missing
**When** `validate()` is called
**Then** it returns `(False, "macro_file_missing: <path>", None)`

**Given** the file is present but `json.loads` raises
**When** `validate()` is called
**Then** it returns `(False, "macro_file_malformed: <error>", None)`

**Given** the file is present and parses, but `schema_version != 1`
**When** `validate()` is called
**Then** it returns `(False, "macro_schema_version_unexpected: <version>", None)`

**Given** the file is present but `errors[]` is non-empty
**When** `validate()` is called
**Then** it returns `(False, "macro_errors: <error list>", None)`

**Given** `composite` is outside [0, 100]
**When** `validate()` is called
**Then** it returns `(False, "macro_composite_out_of_range: <value>", None)`

### Story 1b.2: Add staleness threshold and provenance allow-list to MACRO validation

As the operator (Rekwa),
I want the MACRO consumer to enforce a 4-hour staleness window and a known-weights-hash allow-list,
So that the bot degrades gracefully on stale data and refuses to use regime data when MACRO has been recalibrated without my review.

**Acceptance Criteria:**

**Given** the MACRO file is present and content-valid (per Story 1b.1) but `run_timestamp` is more than 4 hours old
**When** `macro_consumer.validate()` is called
**Then** it returns `(True, "macro_stale_<N>h_treating_as_neutral", regime_data)` where regime_data carries a `neutralized: true` flag
**And** callers reading `regime_data` treat the band/regime as if neutral (no size-down)

**Given** `data/macro_weights_allowlist.json` exists with a JSON array of known-good hash strings
**When** `validate()` checks `weights_hash`
**Then** if the hash is in the allow-list, validation continues normally
**And** if the hash is NOT in the allow-list, validation returns `(False, "macro_weights_hash_unknown: <hash>", None)`

**Given** `data/macro_weights_allowlist.json` does not exist
**When** `validate()` is called
**Then** it returns `(False, "macro_weights_allowlist_missing", None)` (forces explicit bootstrap)

**Given** the operator wants to bootstrap the allow-list with the current MACRO weights_hash
**When** they manually create `data/macro_weights_allowlist.json` with the current hash
**Then** subsequent runs validate successfully

### Story 1b.3: Compute MACRO size multiplier from regime data

As the operator (Rekwa),
I want a `size_multiplier()` function that maps the regime data to a sizing multiplier per the policy table,
So that the Entry orchestrator can scale (or skip) the position based on MACRO regime.

**Acceptance Criteria:**

**Given** validated `regime_data` from `validate()`
**When** `macro_consumer.size_multiplier(regime_data)` is called
**Then** it returns 0.0 if `composite_band == "red"` (block: no entry today)
**And** returns 0.5 if `composite_band == "orange" AND regime == "high"`
**And** returns 1.0 otherwise (including `neutralized=True` from staleness)

**Given** `regime_data` has `neutralized: true` (per Story 1b.2)
**When** `size_multiplier()` is called
**Then** it returns 1.0 regardless of `composite_band` or `regime` values

**Given** `tests/test_macro_consumer.py` is run
**When** the test suite executes
**Then** at least 5 assertions cover this function (red, orange+high, orange+mid, green, neutralized)

### Story 1b.4: Create pre-flight health check module

As the operator (Rekwa),
I want a `preflight` module with `check_entry()` and `check_exit()` functions that validate system state before any trade logic runs,
So that broken state surfaces as a clean ABORT rather than a bad trade.

**Acceptance Criteria:**

**Given** `preflight.check_entry()` is invoked
**When** it executes
**Then** it runs 5 checks in order: (1) `.env` keys ALPACA_API_KEY and ALPACA_SECRET_KEY present; (2) Alpaca account reachable with `status == "ACTIVE"`, `trading_blocked == False`, `paper == True`; (3) MICRO `theses.jsonl` exists and was written today (file mtime check); (4) MACRO validates per `macro_consumer.validate()` — "stale" is OK, only "broken/missing" fails; (5) kill switch placeholder returns OK (real implementation in Story 1c.5)
**And** returns `(True, "ok")` if all pass
**And** returns `(False, "<first failed check reason>")` on the first failure (short-circuits)

**Given** `preflight.check_exit()` is invoked
**When** it executes
**Then** it runs 2 checks: (1) `.env` keys present; (2) Alpaca account reachable + ACTIVE + paper=True
**And** returns `(True, "ok")` or `(False, "<reason>")` analogously

**Given** any check raises an exception
**When** the exception is caught
**Then** `check_entry()` / `check_exit()` returns `(False, "preflight_check_X_raised: <message>")`

**Given** `tests/test_preflight.py` is run
**When** the test suite executes
**Then** at least 6 assertions cover the failure paths (missing .env keys, Alpaca unreachable, MICRO file stale, MACRO broken, exception in check)

### Story 1b.5: Wire pre-flight into Entry and Exit tasks

As the operator (Rekwa),
I want both `run_trading.py` and `src/exit_manager.py` to invoke `preflight` before any trade logic,
So that scheduled fires never proceed on broken state.

**Acceptance Criteria:**

**Given** `run_trading.py` is invoked by the scheduled Entry task
**When** the script starts
**Then** it calls `preflight.check_entry()` as the first action after `load_env()`
**And** if `ok=False`, sends Pushover `"Tactical Trading ABORT: <reason>"` and `sys.exit(1)`
**And** if `ok=True`, proceeds with existing entry logic (today_signal → already_traded → submit_order → log_entry)

**Given** `src/exit_manager.py` is invoked by the scheduled Exit task
**When** the script starts
**Then** it calls `preflight.check_exit()` as the first action after `load_env()`
**And** if `ok=False`, sends Pushover and `sys.exit(1)`
**And** if `ok=True`, proceeds with existing exit logic

**Given** preflight ABORTs the Entry task
**When** the Exit task fires at 08:40 CDT
**Then** the Exit task still runs (its own preflight is more permissive — only Alpaca check)

### Story 1b.6: Wire MACRO size multiplier into Entry flow

As the operator (Rekwa),
I want the Entry task to consult the MACRO size multiplier and skip entries when the multiplier is 0,
So that the bot blocks new positions during red regime.

**Acceptance Criteria:**

**Given** preflight passed and a today's signal is present
**When** `run_trading.py` continues after preflight
**Then** it calls `ok, reason, regime_data = macro_consumer.validate()` and `multiplier = macro_consumer.size_multiplier(regime_data)`
**And** if `multiplier == 0.0`, logs "MACRO size-down to 0 (red regime) — no entry today" + sends Pushover info, then returns (no trade)
**And** if `multiplier > 0.0`, proceeds to entry submission

**Given** the entry record is being written
**When** `trade_logger.log_entry()` is called
**Then** the record includes a new field `macro_snapshot: {run_timestamp, composite_band, regime, weights_hash}` extracted from `regime_data`
**And** if `regime_data` had `neutralized: true`, the snapshot records the stale state explicitly

**Given** Phase 2 Story 1c.3 is not yet shipped (sizing logic not in place)
**When** Story 1b.6 lands first
**Then** the MACRO multiplier is applied directly to the Phase 1 fixed `notional=$10,000` (e.g., $5,000 if multiplier=0.5)
**And** the entry record records `sizing_rule_used: "phase1_fixed_x_macro_mult"` as a transitional value
**And** when Story 1c.3 lands, this is replaced by full risk-based sizing × multiplier

---

## Epic 1c: Portfolio Risk Engine (Sizing + Concentration + Drawdown Kill Switch)

**Goal:** Position sizes are risk-aware and capped by concentration limits. Pre-trade checks block oversized or over-concentrated trades. Bot auto-pauses new entries on 20% drawdown from account high-water-mark.

### Story 1c.1: Compute risk-based position size (pure function)

As the operator (Rekwa),
I want a pure function that computes position size as `min(risk-based, concentration cap)` and reports which rule bound,
So that I have a deterministic, testable sizing primitive and an audit trail of which rule was active.

**Acceptance Criteria:**

**Given** parameters `account_value`, `entry_price`, `stop_price`, `max_position_pct=0.05`, `max_risk_pct=0.02`
**When** `risk.compute_position_size(...)` is called
**Then** it computes `risk_based_qty = (account_value × max_risk_pct) / (entry_price − stop_price)`
**And** computes `cap_qty = (account_value × max_position_pct) / entry_price`
**And** returns `(chosen_qty, sizing_rule_used)` where `chosen_qty = min(risk_based_qty, cap_qty)` and `sizing_rule_used` is `"risk_based"` or `"concentration_cap"`

**Given** `account_value=100_000`, `entry_price=90`, `stop_price=87.75` (2.5% stop)
**When** `compute_position_size()` is called with defaults
**Then** `risk_based_qty ≈ 888.9` ($2,000 risk / $2.25 per share)
**And** `cap_qty ≈ 55.6` ($5,000 cap / $90 per share)
**And** result is `(55.6, "concentration_cap")` — cap binds at $100k paper account

**Given** `account_value=10_000` (Phase 3 live minimum)
**When** `compute_position_size(10_000, 90, 87.75)` is called
**Then** `risk_based_qty ≈ 88.9` ($200 risk / $2.25)
**And** `cap_qty ≈ 5.6` ($500 / $90)
**And** result is `(5.6, "concentration_cap")` — cap still binds at $10k

**Given** `account_value=10_000`, `entry_price=90`, `stop_price=80` (12% stop — wider than 5% cap allows)
**When** `compute_position_size()` is called
**Then** `risk_based_qty = 20` ($200 / $10)
**And** `cap_qty ≈ 5.6` ($500 / $90)
**And** result is `(5.6, "concentration_cap")`

**Given** `tests/test_risk.py` is run
**When** the suite executes
**Then** at least 4 assertions cover this function (cap binds, risk_based binds, edge case stop_price ≥ entry_price raises, sign-error guards)

### Story 1c.2: Pre-trade concentration checks

As the operator (Rekwa),
I want a function that runs the three FR12 concentration checks against the candidate trade and the current Alpaca portfolio,
So that no trade is submitted that would breach 5% / 20% / 25% limits.

**Acceptance Criteria:**

**Given** parameters `symbol`, `proposed_qty`, `proposed_price`, `current_positions` (from Alpaca), `account_value`
**When** `risk.check_concentration(...)` is called
**Then** it computes `proposed_value = proposed_qty × proposed_price`
**And** checks (a) `proposed_value ≤ account_value × 0.05`; (b) `sum(current_position_values) + proposed_value ≤ account_value × 0.20`; (c) `existing_value_for_symbol + proposed_value ≤ account_value × 0.25`
**And** returns `(True, "ok")` if all pass
**And** returns `(False, "<which check failed>: <values>")` on first failure

**Given** an existing XLE position worth $4,500 and a proposed XLE buy worth $1,000 on a $100k account
**When** `check_concentration("XLE", proposed_qty, proposed_price, positions, 100_000)` is called
**Then** check (a) passes ($1,000 < $5,000)
**And** check (b) depends on other positions
**And** check (c) fails ($4,500 + $1,000 = $5,500 < $25,000 OK — wait, that passes); revise example

**Given** an existing XLE position worth $24,500 and a proposed XLE buy worth $1,000 on a $100k account
**When** `check_concentration(...)` is called
**Then** check (c) fails (`$24,500 + $1,000 = $25,500 > $25,000`)
**And** the returned reason includes "ticker_concentration"

**Given** `tests/test_risk.py` is extended
**When** the suite executes
**Then** at least 3 assertions cover this function (per-trade cap, open-total cap, per-ticker cap)

### Story 1c.3: Wire sizing + concentration into Entry orchestration

As the operator (Rekwa),
I want `run_trading.py` to use `compute_position_size` + `check_concentration` instead of Phase 1's fixed $10k notional,
So that every entry is risk-aware and respects portfolio limits.

**Acceptance Criteria:**

**Given** preflight and MACRO checks have passed
**When** `run_trading.py` is about to call `submit_order`
**Then** it fetches `account_value` from Alpaca via `trading_client().get_account().equity`
**And** computes `stop_price` for the candidate symbol using the entry price estimate (mark or last close)
**And** calls `compute_position_size(account_value, entry_price, stop_price)` to get `(chosen_qty, sizing_rule_used)`
**And** applies the MACRO size multiplier: `final_qty = chosen_qty × multiplier`
**And** calls `check_concentration(symbol, final_qty, entry_price, current_positions, account_value)`
**And** if concentration check fails, sends Pushover info "Pre-trade BLOCK: <reason>" and returns (no trade)
**And** if concentration passes, submits a qty-based MarketOrderRequest (not notional)

**Given** `order_builder.submit_order` is updated to accept a qty (not notional)
**When** the entry order submits
**Then** the order request is `MarketOrderRequest(symbol, qty=final_qty, side=BUY, time_in_force=DAY)` (fractional qty OK)

**Given** the entry record is being written
**When** `trade_logger.log_entry()` is called
**Then** it records `sizing_rule_used` (from compute_position_size, modified to include "_with_macro_x_<multiplier>" suffix if multiplier != 1.0)
**And** the Phase 1 `notional` field is preserved but set to `null` (since qty-based now)

### Story 1c.4: Track account high-water-mark

As the operator (Rekwa),
I want the bot to record the all-time peak account equity in `data/account_state.json`,
So that the drawdown kill switch has a stable reference point.

**Acceptance Criteria:**

**Given** the Entry task is running and preflight has passed
**When** account equity is fetched from Alpaca
**Then** the bot reads `data/account_state.json` (creating with default `{"peak_equity": <current_equity>, "peak_timestamp": "<now>"}` if missing)
**And** if `current_equity > peak_equity`, updates the file with new peak + timestamp
**And** if `current_equity <= peak_equity`, leaves the file unchanged

**Given** the file is corrupt or unreadable
**When** the read raises
**Then** the bot treats it as missing (re-initialize with current equity) and sends Pushover "account_state.json reinitialized due to read error"

**Given** the operator wants to manually reset the high-water-mark (e.g., after a manual deposit)
**When** they delete the file or edit it
**Then** the next Entry run regenerates it without complaint

### Story 1c.5: Drawdown auto-pause kill switch

As the operator (Rekwa),
I want the kill switch to block new entries when drawdown exceeds 20% from peak account equity,
So that the bot stops adding risk during a steep losing streak.

**Acceptance Criteria:**

**Given** `account_state.json` contains a peak_equity and current_equity is fetched from Alpaca
**When** `risk.check_kill_switch(current_equity, account_state)` is called
**Then** it computes `drawdown = (peak_equity − current_equity) / peak_equity`
**And** returns `(False, "kill_switch_drawdown: <pct>% (peak $<peak> → current $<current>)")` if `drawdown >= 0.20`
**And** returns `(True, "ok")` otherwise

**Given** `preflight.check_entry()` placeholder check 5 from Story 1b.4
**When** Story 1c.5 lands
**Then** check 5 calls `risk.check_kill_switch(current_equity, account_state)` and uses its return as the check 5 result
**And** the check 5 fetches `current_equity` only if checks 1-4 passed (avoid unnecessary Alpaca call)

**Given** the kill switch is tripped
**When** Pushover ABORT is sent
**Then** the title is "Tactical Trading ABORT: KILL SWITCH" and the body is the drawdown reason
**And** the Exit task continues normally — it processes ripe positions and respects stop fills, but no new entries land

**Given** the operator wants to reset the kill switch (after manual review)
**When** they delete `data/account_state.json` or manually edit `peak_equity` downward
**Then** the next Entry run computes a smaller (or zero) drawdown and resumes trading

---

## Epic 2: Drift Detection + Loss Discipline (Phase 2.1)

**Goal:** After every Entry/Exit fire, the bot compares Alpaca state to local ledger and alerts on drift (dry-run only — no autonomous correction). Consecutive-loss kill switch catches slow-bleed regime. Every losing close records wash-sale metadata.

### Story 2.1: Reconciler — detect orphan positions, stop orders, and ledger drift

As the operator (Rekwa),
I want a reconciler module that compares Alpaca state to `data/trades.jsonl` and reports any drift,
So that I see ledger-vs-broker divergence within the same trading day instead of discovering it weeks later.

**Acceptance Criteria:**

**Given** the reconciler is invoked
**When** `reconciler.report()` is called
**Then** it queries Alpaca for `get_all_positions()` and `get_orders(status=OPEN)`
**And** loads all records from `data/trades.jsonl`
**And** returns a list of drift events with at least these types:
  - `"orphan_position"`: an Alpaca position with no matching `status=="open"` record
  - `"orphan_open_order"`: an Alpaca open order with no matching record (stop order or otherwise)
  - `"missing_position"`: a `status=="open"` record with no matching Alpaca position
  - `"missing_stop_order"`: a `status=="open"` record with `stop_order_id` set but no matching open order at Alpaca
**And** returns an empty list if no drift detected

**Given** `tests/test_reconciler.py` is run
**When** the suite executes
**Then** at least 4 assertions cover each drift type (one per type, with synthetic Alpaca + ledger fixtures)

### Story 2.2: Persist drift events and notify

As the operator (Rekwa),
I want drift events appended to `data/drift_log.jsonl` and a Pushover summary sent when drift is detected,
So that I have an audit trail of every state-divergence event.

**Acceptance Criteria:**

**Given** `reconciler.report()` returns a non-empty list
**When** `reconciler.notify_drift(drift_events)` is called
**Then** each event is appended as a JSON line to `data/drift_log.jsonl` with a `detected_at` UTC timestamp
**And** a single Pushover is sent with title `"Tactical Trading DRIFT (<count> event(s))"` and body summarizing each event (truncated to fit Pushover's 1024-char limit)

**Given** `reconciler.report()` returns an empty list
**When** `notify_drift([])` is called
**Then** no Pushover is sent and no write to `drift_log.jsonl` happens (idempotent on no-drift)

**Given** `data/drift_log.jsonl` does not yet exist
**When** the first drift event is recorded
**Then** the file is created and the event is appended

### Story 2.3: Append reconciler to Entry and Exit task completion

As the operator (Rekwa),
I want the reconciler to run automatically after every Entry and Exit task,
So that drift is surfaced same-day without needing a separate Scheduled Task.

**Acceptance Criteria:**

**Given** `run_trading.py` has finished its main logic (whether or not a trade was placed)
**When** the script reaches its post-main block
**Then** it calls `drift = reconciler.report()` and `reconciler.notify_drift(drift)`
**And** any exception from the reconciler is caught and Pushover'd as `"Reconciler crashed: <error>"` but does NOT raise (the Entry task already succeeded)

**Given** `src/exit_manager.py` has finished `run_exits()`
**When** the function returns
**Then** it calls `drift = reconciler.report()` and `reconciler.notify_drift(drift)`
**And** any exception is handled per the Entry pattern (Pushover, do not raise)

### Story 2.4: Consecutive-loss kill switch

As the operator (Rekwa),
I want the kill switch to block new entries when the last 5 consecutive closed trades all show negative P&L,
So that the bot pauses during a slow-bleed regime even before drawdown threshold trips.

**Acceptance Criteria:**

**Given** `data/trades.jsonl` contains a sequence of closed records
**When** `risk.check_consecutive_losses(trades, threshold=5)` is called
**Then** it loads the last `threshold` closed records (status=="closed", ordered by exit_time_actual)
**And** returns `(False, "kill_switch_consecutive_losses: <N> losses in a row, last winner <date>")` if all last 5 have `pnl_dollars < 0`
**And** returns `(True, "ok")` if any of the last 5 has `pnl_dollars >= 0` OR if fewer than 5 closed records exist

**Given** `preflight.check_entry()` check 5 (kill switch) currently runs only the drawdown check
**When** Story 2.4 lands
**Then** check 5 runs BOTH `check_kill_switch` (drawdown) AND `check_consecutive_losses`
**And** if either fails, returns the failing reason
**And** if both pass, returns ok

**Given** the consecutive-loss kill is tripped
**When** Pushover ABORT is sent
**Then** the title is "Tactical Trading ABORT: CONSECUTIVE LOSSES" and the body includes the count and last winner date

### Story 2.5: Record wash-sale metadata at exit time

As the operator (Rekwa),
I want every closing trade with negative P&L to record wash-sale metadata in its close record,
So that Phase 3 (live capital) starts with clean wash-sale bookkeeping from day one.

**Acceptance Criteria:**

**Given** a position is exiting and `pnl_dollars < 0`
**When** `exit_manager.exit_position(record)` writes the close record
**Then** it adds a `wash_sale` object with fields: `is_loss: true`, `loss_amount: pnl_dollars`, `lots_within_30d: [...]`, `potential_wash_sale: true|false`
**And** `lots_within_30d` is the list of entries in `trades.jsonl` for the same symbol whose `entry_time` is within 30 days before `exit_time_actual`
**And** `potential_wash_sale` is `true` if `lots_within_30d` is non-empty, else `false`

**Given** `pnl_dollars >= 0` (winning close)
**When** the close record is written
**Then** the `wash_sale` object is still recorded but with `is_loss: false` and `loss_amount: 0` (Phase 3 may extend; Phase 2 keeps it uniform)

**Given** a Phase 1 close record (no `wash_sale` field)
**When** Phase 2 code reads it
**Then** the code uses `.get("wash_sale", None)` and tolerates the absence

---

## Epic 3: Phase 2 Graduation Tracking

**Goal:** Track progress toward AR20 graduation criterion and notify when met, opening Phase 3 design.

### Story 3.1: Compute Phase 2 graduation status from trade history

As the operator (Rekwa),
I want a function that reads `trades.jsonl` and `drift_log.jsonl` and reports current graduation progress,
So that I can see at-a-glance how close Phase 2 is to graduation.

**Acceptance Criteria:**

**Given** `graduation.check_status()` is called
**When** the function executes
**Then** it returns a dict with: `total_closed_trades`, `stop_fired_exits`, `macro_size_downs`, `drift_false_positives`, `criterion_met` (bool), `criterion_summary` (human-readable string)
**And** `total_closed_trades` counts records with `status=="closed"` in `trades.jsonl`
**And** `stop_fired_exits` counts closed records with `exit_reason=="stop_fired"`
**And** `macro_size_downs` counts entry records whose `macro_snapshot.composite_band` triggered a size_multiplier < 1.0 (i.e., red or orange+high)
**And** `drift_false_positives` counts events in `drift_log.jsonl` (until human-confirmation gate exists, every drift event counts as a false positive; Phase 3 design refines this)
**And** `criterion_met = (total_closed_trades >= 20) AND (stop_fired_exits >= 2) AND (macro_size_downs >= 1) AND (drift_false_positives == 0)`

**Given** `trades.jsonl` is empty or missing
**When** `check_status()` is called
**Then** all counts return 0 and `criterion_met=False`

### Story 3.2: Pushover notification when graduation criterion is met

As the operator (Rekwa),
I want a single Pushover when Phase 2 graduation is first met,
So that I'm prompted to open Phase 3 design without having to manually check.

**Acceptance Criteria:**

**Given** `graduation.check_status()` returns `criterion_met=True`
**When** `graduation.notify_if_met()` is called
**Then** it checks `data/graduation_state.json` for an `already_notified: true` flag
**And** if not already notified, sends Pushover: title `"PHASE 2 GRADUATION MET"`, body summarizing the four counts
**And** writes `data/graduation_state.json` with `already_notified: true` and the timestamp

**Given** `criterion_met=False`
**When** `notify_if_met()` is called
**Then** no Pushover is sent and the state file is unchanged (idempotent)

**Given** the operator wants to re-trigger the notification (e.g., after a Phase 2 reset)
**When** they delete `data/graduation_state.json`
**Then** the next graduation check that finds `criterion_met=True` will Pushover again

### Story 3.3: Run graduation check after Exit task completion

As the operator (Rekwa),
I want `graduation.notify_if_met()` invoked after every Exit task,
So that the criterion is checked exactly when new closed trades appear (the only event that can move the counts).

**Acceptance Criteria:**

**Given** `src/exit_manager.py` has completed its work (including reconciler from Story 2.3)
**When** the script reaches its final post-block
**Then** it calls `graduation.notify_if_met()`
**And** any exception is caught and Pushover'd as `"Graduation check crashed: <error>"` but does NOT raise (the Exit task already succeeded)

**Given** no exits ran (no ripe positions)
**When** the Exit task still calls graduation check
**Then** the check still runs and reports current progress (counts may be 0)
**And** no Pushover is sent if criterion not met (idempotent)
