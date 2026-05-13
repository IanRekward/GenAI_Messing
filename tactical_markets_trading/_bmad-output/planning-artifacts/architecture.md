---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'complete'
completedAt: '2026-05-13'
inputDocuments:
  prd:
    - "_bmad-output/planning-artifacts/prd.md"
    - "_bmad-output/planning-artifacts/prd-validation-report.md"
  research:
    - "_bmad-output/planning-artifacts/research/domain-active-trading-bot-regime-strategies-research-2026-05-11.md"
    - "_bmad-output/planning-artifacts/FINTECH_TRADING_BOT_REFERENCE_MATERIALS.md"
  project_local:
    - "TRADING_INTEGRATION_PLAN.md"
    - "ROADMAP_ALPACA_INTEGRATION.md"
    - "TODO.md"
    - "research/data/comparison_report.md"
    - "research/data/sensitivity_summary.md"
  project_docs:
    - "docs/index.md"
    - "docs/project-overview.md"
    - "docs/architecture.md"
    - "docs/source-tree-analysis.md"
    - "docs/data-models.md"
    - "docs/integration-architecture.md"
    - "docs/development-guide.md"
    - "_bmad-output/project-context.md"
  macro_upstream:
    - "../market_dashboard/CLAUDE.md"
    - "../market_dashboard/README.md"
    - "../market_dashboard/BACKTEST_DESIGN.md"
    - "../market_dashboard/TODO.md"
    - "../market_dashboard/_bmad-output/planning-artifacts/integration-brief-for-tactical-bot.md"
  micro_upstream:
    - "../tactical_markets/CLAUDE.md"
    - "../tactical_markets/ROADMAP_SIGNAL_GENERATION.md"
    - "../tactical_markets/RESEARCH_SUMMARY.md"
    - "../tactical_markets/TODO.md"
    - "../tactical_markets/_bmad-output/project-context.md"
    - "../tactical_markets/docs/index.md"
    - "../tactical_markets/docs/architecture.md"
    - "../tactical_markets/docs/integration-architecture.md"
    - "../tactical_markets/docs/data-models.md"
workflowType: 'architecture'
scope: 'phase-2-forward'
baseline: 'docs/architecture.md (current Phase 1, frozen)'
project_name: 'tactical_markets_trading'
user_name: 'Rekwa'
date: '2026-05-13'
---

# Architecture Decision Document — tactical_markets_trading

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

**Scope of this document:** Forward-looking architecture covering **Phase 2 design** (post-Phase-1-freeze) and the path to the PRD's end-state vision. The current Phase 1 baseline is captured in [docs/architecture.md](../../docs/architecture.md) — this document is a delta on top of that.

**Phase boundaries (for grounding):**

| Phase | Status | Scope |
|---|---|---|
| Phase 1 | **BUILT, FROZEN** until ≥5 clean trades (lowered from 10 on 2026-05-13) | Long-only momentum, fixed $10k, no stops, market orders, MICRO-only, 2-day hold (lowered from 5 on 2026-05-13) |
| Phase 2 | **Target of this document** | Stops + risk-based sizing, MACRO consumption (size-down on red regime), drawdown-distribution-informed sizing, reconciliation, possibly limit orders |
| Phase 3 | Architectural awareness only — gated on Phase 2 validation + ROE doc | Live capital |
| Phase 4+ | PRD end-state vision — informs design tradeoffs but not committed scope | Multi-strategy ensemble (11+), regime routing, Tier 2 single stocks, dashboard, full Sharpe-based kill switch, tax CSV export, manual-execute UI question |

---

## Project Context Analysis

### Requirements Overview

The PRD enumerates **20 FRs** across 5 categories (signal consumption, trade execution, sizing/risk, reporting, backtesting) and **12 NFRs** across 4 (performance, reliability, security, fault tolerance). The PRD validation report rated this 4/5 GOOD — but that validated PRD-internal consistency, not PRD-to-codebase fit. This architecture's first job is to bridge that gap.

**FR allocation by phase** (revised after party-mode review):

| Tier | FRs | Architectural treatment in this doc |
|---|---|---|
| **Phase 2 graduation requirements** | FR1 (MACRO consumption — size-down on red regime), FR11 (risk-based sizing), **FR12 (portfolio concentration limits)**, FR13 partial (drawdown auto-pause + consecutive-loss kill), FR10/FR17 (enriched logging incl. **wash-sale schema**), reconciliation, broker-side stop orders | Design in detail |
| **Phase 3 live-capital requirements** | FR14 (PDT rules — only matters live), FR13 full (Sharpe-/win-rate-based pause), FR17 wash-sale **logic enforcement** (schema already exists from Phase 2), FR16 daily report | Architectural skeleton; full design at Phase 3 |
| **Phase 4+ end-state** | FR4 (11+ strategies + regime routing), FR15 (live dashboard), FR2 with MICRO-emits-stops, FR6 manual Execute UI (or pre-flight confirmation gate — see workflow-gate decision below) | Acknowledge as north star; do not commit |

**Phase boundary corrections absorbed from party-mode review:**

- **FR12 (portfolio concentration) → Phase 2.** Sizing without concentration guardrails is half a risk engine; can't ship one without the other. (Mary)
- **Wash-sale schema → Phase 2.** Phase 3 paper-validation will accumulate 50+ trades that must already have clean wash-sale bookkeeping; doing this retroactively at Phase 3 entry is the wrong order. **Phase 2 designs the schema and records the data. Phase 3 enforces it.** (Winston)
- **Reconciler → Phase 2 (with constraints).** Reconciliation that can autonomously act on positions ships only with: (a) dry-run mode as default, (b) explicit human-confirmation gate before any autonomous action, (c) read-only "drift report" Pushover for the first N runs. (Murat)
- **Broker-side stops → Phase 2 (replaces local-stops-stored-in-JSONL).** Two-step pattern: after entry fill, submit a separate stop-sell order at Alpaca; cancel-and-replace with market SELL at planned exit. NFR5 (failsafe / multi-day VPS outage) is the load-bearing concern. (Murat)

**Non-Functional Requirements — Phase 2 implications:**

- **NFR5 (failsafe)** is the most architecturally load-bearing NFR. **Decision:** broker-side stop orders (Alpaca holds the stop; survives VPS outage) replace local-stop-in-JSONL.
- **NFR2/NFR6 (signal freshness)** drives the MACRO consumer's provenance validation contract.
- **NFR10/NFR12 (fault tolerance)** — Phase 2 MACRO consumer must distinguish stale-but-valid (degrade to neutral regime) from schema-broken (block + alert). Two distinct policies. (Winston)
- NFR1 (<500ms dashboard latency) is Phase 4+; ignore.
- NFR7-9 (security) — Phase 1 already satisfies the local-VPS storage and `.env` credentials posture.

### Scale & Complexity

- **Primary domain:** Python backend service (single-entrypoint batch CLI, scheduled). No UI, no DB, no API publication.
- **Complexity level:** High — regulated finance, multi-signal-source, eventual real capital, full audit-trail requirement, hard immovable constraints.
- **Phase 2 architectural delta estimate:** 3 new modules (`src/risk.py`, `src/macro_consumer.py`, `src/reconciler.py`), one optional `src/config.py` (constants only, no I/O — Amelia), additive schema bump on `trades.jsonl` (no formal versioning yet — Amelia). `run_trading.py` gets ~2 import lines + 1 conditional block; should remain under ~120 lines after Phase 2 (design slipped if it exceeds).
- **Phase 2 graduation criterion (Murat):** 20+ paper trades with ≥2 stop-triggered exits verified against broker fills, ≥1 MACRO-gated size-down observed in logs, zero reconciliation false-positives.

### Technical Constraints & Dependencies

**Hard locked constraints (apply forever, do not re-open):**

| Constraint | Authoritative source | Implication |
|---|---|---|
| **No shorts, ever** | [_bmad-output/project-context.md](../../_bmad-output/project-context.md) "Locked rules" table | Removes pair-trade and short-leg strategies from solution space. *(Mary flagged user-memory-only sourcing; now also documented in project-context.)* |
| **No Python imports across siblings** | All three siblings' CLAUDE.md / project-context | All upstream signal data via filesystem only |
| **Files-on-disk integration only** | MICRO + MACRO + this project's project-context | No shared library, no IPC, no DB, no MQ |
| **Phase 3 live capital is gated** | [TODO.md](../../TODO.md) | Hard floor: 50+ paper trades + rules-of-engagement doc |
| **`paper=True` is the safety pin** | [src/alpaca_connector.py:22](../../src/alpaca_connector.py#L22) | Code-level guarantee against accidental live trading |
| **Audit trail per trade** | PRD success criteria + compliance | Every decision must be reconstructable from `trades.jsonl` |

**PRD-vs-reality mismatches the architecture resolves:**

1. **MICRO contract gap.** PRD assumes MICRO emits `stop_price`, `target_price`, `confidence`, `hold_window_hours`. Reality: MICRO emits only `buy`, `sell`, `spread_pct`, `as_of` (per [MICRO's data-models.md](../../../tactical_markets/docs/data-models.md)). **Resolution:** stops are computed **locally** in this project's `src/risk.py` based on entry fill + per-strategy rule, then **placed broker-side** as separate stop-sell orders. Stops are a risk concern, not a signal concern (Winston). No coupling to MICRO required even if MICRO could provide them.

2. **MACRO contract mismatch.** PRD describes REST `GET /api/current-regime`. Reality: MACRO ships `data/latest.json` (Brief 24, commit `2046161`) with a richer schema documented in [MACRO's integration brief](../../../market_dashboard/_bmad-output/planning-artifacts/integration-brief-for-tactical-bot.md). **Resolution:** `src/macro_consumer.py` reads `../market_dashboard/data/latest.json` with two-tier failure handling:
   - **Stale (run_timestamp > 26h old, file present but old):** degrade gracefully — trade full-size as if regime is neutral. Pushover info notification, not a block. (Winston)
   - **Broken (schema_version mismatch, weights_hash unknown, file unparseable, errors[] non-empty):** block new entries, Pushover alert. Existing positions and exits unaffected. (Winston)
   - Hard-rejection threshold for staleness: **4 hours** (Murat) — not 26h. Daily MACRO regime should be at most one cycle old.

3. **Manual "Execute" UI vs. fully automated.** PRD FR6 has user clicking "Execute" per thesis. [TODO.md](../../TODO.md) locks "automated entries and exits — manual approval reintroduces discretionary contamination." **Resolution:** stay fully automated through Phase 2 and 3. Phase 3 may introduce a **pre-flight confirmation gate** (not a UI — a dry-run flag + Pushover notification posted before fire, with a y/n token-file or short response window). That's a workflow gate, not a dashboard. Phase 4+ revisits the question. (Winston: the real question is "who has authority to veto a trade?")

   *Sourcing note (Mary): the analysis previously inferred this from a TODO lock. The decision is now explicit here in this document; downstream architectural choices reference it.*

### Cross-Cutting Concerns

| Concern | Phase 2 architectural treatment |
|---|---|
| **Audit trail / trade traceability** | Additive schema bump on `trades.jsonl`: new fields `macro_snapshot`, `stop_rule_used`, `sizing_rule_used`, `stop_order_id`, `wash_sale_eligible_lots`. No `schema_version` field yet (Amelia — gold-plating until Phase 3); Phase 2 readers use `.get(key, default)`. |
| **Idempotency** | Preserve Alpaca-as-authoritative pattern. Reconciler ships dry-run-first (read Alpaca state, compare to `trades.jsonl`, write a drift report — do NOT auto-correct until human-gate is added). |
| **Failsafe / graceful degradation (NFR5)** | **Broker-side stop orders** survive VPS outage. MACRO stale → neutral regime; MACRO broken → block. MICRO missing → no new entries, existing exits run on broker-side stops + scheduled time-exit. |
| **Signal freshness validation** | `macro_consumer.validate()` returns `(bool, str)` — boolean ok + reason. Hard-reject staleness ≥4h. |
| **No-shorts hard constraint** | `src/risk.py` only emits long-side sizing primitives. No short-side code paths exist by construction. |
| **Phase-gate discipline** | Phase 2 graduation criterion (Murat) lives in `TODO.md` once this architecture lands. Each new Phase 2 feature must specify its validation criterion before code lands. |
| **Two-repo git workflow** | New modules + configs ship through `_genai_tmp` mirror; tests directory (now appearing in Phase 2) follows the same pattern. |
| **No cross-sibling imports** | `macro_consumer.py` reads a relative path; no Python import. Same as `order_builder.py` reading MICRO. |
| **Clock discipline / startup health check** (Winston, new) | New `src/preflight.py` module runs before any trade logic in both Entry and Exit tasks. Asserts: (a) Alpaca account reachable, (b) Alpaca account `status == "ACTIVE"`, (c) `.env` keys present, (d) MICRO `theses.jsonl` exists and was written today (Entry task only), (e) MACRO `latest.json` validates per `macro_consumer.validate()` (Entry task only — exit can run blind). If any check fails, structured ABORT with reason via Pushover, exit non-zero so Task Scheduler logs it. |
| **First tests** (Murat + Amelia) | `tests/test_risk.py` — sizing math, concentration cap; `tests/test_macro_consumer.py` — stale rejection, schema validation, weights_hash check; `tests/test_preflight.py` — health-check fail conditions. ~8-10 assertions across 3 files. Earns its existence on day one. The "no tests" decision was defensible at Phase 1 scope; Phase 2 ends it. |
| **Future-Rekwa maintainability** (Mary, new) | Every Phase 2 architectural decision in this document includes a one-line **rationale**. Every locked constraint cites its source. Audit trail is for the human who inherits this code, not just for compliance. |

### Open Questions Flagged for Later Steps

- **MVW within Phase 2 (Amelia):** ship `macro_consumer.validate()` + fixed-fraction sizing + broker-side stop + concentration limits as the minimum-viable Phase 2 deployment. Reconciler, kill-switch primitive, and wash-sale schema land in a second Phase 2 sub-release. **Decide sequencing in step 3 or later.**
- **Stop level rule selection:** fixed-percentage drawdown vs. ATR-based vs. recent-low. Phase 2 picks one (probably fixed-percentage to start; ATR is Phase 2.5 or later). **Decide in detailed-design steps.**
- **Phase 3 workflow gate (pre-flight confirmation):** dry-run flag + Pushover y/n token vs. a different mechanism. **Decide at Phase 3 design time, not now.**
- **Tests CI/CD strategy:** does Phase 2 need a GitHub Actions runner for the cross-sibling repo, or is local pre-commit sufficient? **Decide at Phase 3 design time.**

---

## Starter Template Evaluation

### Primary Technology Domain

**Brownfield Python backend service** (single-entrypoint batch CLI, scheduled via Windows Task Scheduler, file-based integration with sibling projects). No starter template applies. Phase 1 baseline is the de facto "starter," and the architectural delta in this document is layered on top.

### Why no starter

The standard starter-template choices (Next.js, NestJS, T3, RedwoodJS, Expo, etc.) target greenfield web / mobile / full-stack projects. This project:

- Publishes no API and serves no UI (Phase 1, Phase 2)
- Has no database
- Has no frontend framework
- Has no web framework
- Has 5 production modules + 1 entrypoint as of Phase 1, all in place

The existing stack — `alpaca-py`, `yfinance`, `pandas-market-calendars`, `python-dotenv`, `requests`, Python 3.14 — is locked and proven through Phase 1. No "initialization command" is needed; the project is initialized.

### One new Phase 2 decision: testing framework

**Decision: `pytest`.**

**Rationale:**

- Phase 2 introduces conditional logic (regime-conditional sizing, stop-rule branches, MACRO validation paths) that the inline-`__main__` smoke-test pattern can no longer cover. Murat (party mode) called the existing "no tests directory" decision "no longer defensible at Phase 2 scope."
- `pytest` is the boring-tech Python default. Stable API, broad ecosystem, no novel semantics to learn. Matches the project's overall "favor boring technology" posture.
- Sibling project MICRO is also testless today and may adopt `pytest` next; consistency across siblings has small but real value.

**First-shipped tests (per party-mode review):**

- `tests/test_risk.py` — sizing math, concentration cap. (Murat: sizing sign-error is the highest P(occurrence) × Impact risk in Phase 2.)
- `tests/test_macro_consumer.py` — stale-timestamp rejection (>4h), schema_version mismatch, unknown weights_hash.
- `tests/test_preflight.py` — health-check fail conditions.

~8-10 assertions across 3 files at Phase 2 first deployment.

**Architectural decisions established by this choice:**

- Test file location: `tests/` at project root (alongside `src/`)
- Test discovery: default `pytest` (file pattern `test_*.py`, class `Test*`, function `test_*`)
- No fixtures framework beyond `pytest` built-in fixtures (no `factory_boy` etc. — gold-plating)
- No mocking framework beyond `unittest.mock` (stdlib)
- No integration-test framework (Phase 1's "run against real Alpaca" smoke pattern stays for production-path verification)

**Phase 2 dev dependency add:**

```bash
pip install pytest
```

No `requirements-dev.txt` or `pyproject.toml` overhaul needed yet — Phase 1 has no `requirements.txt` either. When dependency management becomes a real problem (likely Phase 3 live capital, where reproducibility matters more), formalize it.

---

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (block Phase 2 implementation):**

1. Stop placement mechanism → broker-side stop order
2. Stop level rule → fixed-percentage (Phase 2.0); ATR-based deferred
3. Stop default percentage → 2.5% from entry fill (configurable)
4. Sizing rule → 5% concentration cap binds; risk-based math logged for provenance
5. Concentration limits → 5% per trade, 20% open total, 25% per ticker (PRD FR12, adopt as-is)
6. MACRO size-down policy → band-and-regime tier (specific rule below)
7. MACRO staleness threshold → 4 hours (Murat)
8. MACRO failure recovery → stale = neutral; broken = block (Winston)
9. Kill switch primitive → consecutive-loss counter + drawdown threshold
10. Pre-flight health check scope → 5 explicit checks (below)
11. Reconciler scope → read-only drift report, dry-run forever in Phase 2
12. Wash-sale schema → record-only in Phase 2, fields below
13. Module boundaries → 4 new src/ modules

**Important Decisions (shape architecture but not strictly blocking):**

14. Persistence pattern unchanged (append-only JSONL + in-place close-update)
15. Configuration: inline constants per module; promote to `src/config.py` only when 3+ modules share a constant
16. Logging: stdout + Pushover (no log files, no external sink yet)
17. Testing: pytest in `tests/` (decided in step 3)

**Deferred Decisions:**

- ATR-based stops → Phase 2.5+ (need volatility data per ticker; fixed-pct ships sooner)
- Limit orders → deferred; broker-side stops address the main NFR5 concern that motivated them
- Database / Parquet ledger → Phase 3+ (only if trade volume justifies)
- Pre-flight confirmation gate (dry-run + Pushover y/n) → Phase 3 live-capital design
- `requirements.txt` / `pyproject.toml` formalization → Phase 3+
- Backtest module integration with production code → Phase 4+; research scripts stay off-production-path

---

### Decision 1: Stop Placement Mechanism

**Choice:** Broker-side stop-sell order, submitted after entry fill.

**Flow:**

```
1. run_trading.py submits market BUY (notional=$10k or sized)
2. wait_for_fill → returns fill_price, fill_qty
3. risk.compute_stop_price(fill_price, rule) → stop_price
4. trading_client.submit_order(StopOrderRequest(symbol, qty=fill_qty,
     side=SELL, stop_price=stop_price, time_in_force=GTC))
5. wait briefly to confirm stop order accepted; record stop_order_id
6. trade_logger writes entry record with stop_order_id, stop_price, stop_rule_used
```

**At exit (planned time):**

```
1. exit_manager finds open record past exit_time_planned
2. cancel(stop_order_id) — best-effort; if stop already fired, position is gone
3. if position still open: submit market SELL for fill_qty
4. record exit, including exit_reason: "scheduled" | "stop_fired" | "stop_cancel_failed"
```

**Rationale:** NFR5 (failsafe / multi-day VPS outage). Stops at broker survive scheduler failure, laptop sleep, VPS outage. Local-stop-in-JSONL fails open. (Murat, party mode.) Two-step pattern (not atomic bracket) because Phase 2 may still use notional sizing on first entries; `bracket` orders require qty.

**Affects:** `src/order_builder.py` (add stop submission after entry), `src/exit_manager.py` (cancel stop before SELL), `src/trade_logger.py` (schema fields), `src/risk.py` (new — stop level computation).

### Decision 2: Stop Level Rule

**Choice:** Fixed-percentage drawdown from entry fill. Default 2.5%; configurable per-trade.

**Computation:** `stop_price = round(fill_price * (1 - stop_pct), 2)`. `stop_pct` defaults to 0.025 (2.5%).

**Rationale:** Simplest deterministic rule. Pure function — fully unit-testable (Murat's first-test target). Sector ETFs (XLE/XLK/etc.) have typical 1-month ranges of 4–6%; 2.5% gives wins room to develop, losses room to confirm. ATR-based stops are better matched to asset volatility but require an OHLC fetch + compute step — defer to Phase 2.5 once Phase 2 data shows whether fixed-pct is too tight/loose.

**Affects:** `src/risk.py` — `compute_stop_price(fill_price, stop_pct=0.025) -> float`.

### Decision 3: Sizing Rule

**Choice:** Position size = min(risk-based, 5% concentration cap). At $100k paper, the cap binds for nearly all configurations; risk-based math is logged for provenance.

**Computation:**

```python
def compute_position_size(account_value, entry_price, stop_price,
                          max_position_pct=0.05, max_risk_pct=0.02):
    risk_dollars = account_value * max_risk_pct
    risk_based_qty = risk_dollars / (entry_price - stop_price)
    cap_qty = (account_value * max_position_pct) / entry_price
    chosen_qty = min(risk_based_qty, cap_qty)
    sizing_rule_used = "risk_based" if risk_based_qty < cap_qty else "concentration_cap"
    return chosen_qty, sizing_rule_used
```

**Rationale:** PRD FR11 specifies risk-based math; at $100k paper account, concentration cap (5%) almost always binds. Phase 3 live capital at smaller accounts (PRD says $10k minimum) makes risk-based binding. Logging `sizing_rule_used` per trade preserves audit trail and shows when the math actually mattered.

**Affects:** `src/risk.py`; schema field `sizing_rule_used` in `trades.jsonl`.

### Decision 4: Concentration Limits

**Choice:** PRD FR12 as-is. Three pre-trade checks:

1. Per-trade ≤ 5% of account
2. Total open positions ≤ 20% of account
3. Single ticker ≤ 25% of account (across open positions)

**Pre-trade enforcement:** `run_trading.py` calls `risk.check_concentration(symbol, proposed_qty, current_positions)` before `submit_order()`. If any check fails, log reason, Pushover info, return without trading.

**Rationale:** Mary (party mode): "Sizing without concentration guardrails is half a risk engine." PRD's numbers are reasonable retail-scale defaults.

**Affects:** `src/risk.py` — `check_concentration(...) -> tuple[bool, str]`.

### Decision 5: MACRO Size-Down Policy

**Choice:** Two-tier gating based on `composite_band` and `regime` from MACRO's `data/latest.json`:

| `composite_band` | `regime` | New entry behavior |
|---|---|---|
| `red` | any | **Block**: no new entries today. Existing positions and exits run normally. |
| `orange` | `high` | **Size down 0.5x**: multiply chosen qty by 0.5. |
| any other | any | **Full size**. |

**Provenance:** Every entry trade records `macro_snapshot = {run_timestamp, composite_band, regime, weights_hash}` in `trades.jsonl`.

**Rationale:** Simple two-rule policy. Red regime represents real risk-off; blocking entries is the safer choice over half-sizing. Orange + high VIX regime is the "yellow flag" combination worth de-risking. Anything else gets full Phase 2 sizing.

**Open question (deferred):** Should an `orange` band alone (regime ≠ `high`) also trigger 0.5x? Phase 2 records the data; tune in Phase 2.1 once 10+ live size-downs are observed.

**Affects:** `src/macro_consumer.py`, `src/risk.py` (size multiplier), `trades.jsonl` schema.

### Decision 6: MACRO Staleness + Failure Recovery

**Staleness threshold:** 4 hours since `run_timestamp` (Murat). MACRO runs daily at 7:30 AM ET. Our Entry fires at 08:35 CDT = 9:35 ET = ~2 hours after MACRO; 4h gives margin for MACRO running late, not for skipping a day.

**Failure modes:**

| Condition | Behavior |
|---|---|
| File missing | Block new entries. Pushover "MACRO unavailable". Existing positions/exits unaffected. |
| File present, age > 4h | **Stale** — degrade to neutral regime (full Phase 2 sizing, no size-down). Pushover info. |
| File present, `schema_version != 1` | **Schema broken** — block new entries. Pushover alert. |
| File present, `weights_hash` unknown to allow-list | **Provenance failure** — block new entries. Pushover alert. (Forces human review when MACRO recalibrates weights.) |
| File present, `errors[]` non-empty | Block new entries. Pushover alert with error list. |
| File present, `composite` outside [0, 100] | Block new entries. Pushover alert. |
| All checks pass | Use regime data per Decision 5. |

**Rationale:** Two distinct failure handlings (Winston): stale-but-valid degrades gracefully; broken-or-suspicious blocks. The `weights_hash` allow-list is the explicit human-review gate when MACRO ships a recalibration.

**Affects:** `src/macro_consumer.py` — `validate() -> tuple[ok: bool, reason: str, regime_data: dict | None]`. New file `data/macro_weights_allowlist.json`.

### Decision 7: Kill Switch (Phase 2 primitive)

**Choice:** Two triggers, both checked in pre-flight (so a triggered kill switch blocks new entries; exits and stops continue normally):

1. **Drawdown auto-pause:** account equity from Alpaca, peak high-water-mark stored in `data/account_state.json`. If `(peak - current) / peak > 0.20`, block new entries. Pushover alert. Manual reset (delete state file or set env override flag).
2. **Consecutive-loss counter:** read closed records in `trades.jsonl`; if last 5 consecutive closes all have `pnl_dollars < 0`, block new entries. Pushover alert. Resets automatically on next winning close.

**Rationale:** Phase 2 needs at least a primitive kill switch (Mary). Drawdown is the obvious trigger; consecutive-losses catches a slow-bleed regime before drawdown hits. Both are simple, deterministic, unit-testable. Full PRD FR13 (Sharpe-based, win-rate-based) is Phase 3.

**Affects:** `src/risk.py` — `check_kill_switch(account, trades) -> tuple[bool, str]`. New `data/account_state.json` for high-water-mark.

### Decision 8: Pre-flight Health Check

**Choice:** New `src/preflight.py`. Runs at the top of both Entry and Exit tasks. Five checks, ABORT on any failure:

1. `.env` keys present (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`).
2. Alpaca account reachable + `status == "ACTIVE"` + `trading_blocked == False` + `paper == True`.
3. (Entry only) MICRO `theses.jsonl` exists and was written today (file mtime check).
4. (Entry only) MACRO `latest.json` validates per `macro_consumer.validate()` — a "stale" return is OK (handled by Decision 6); only "broken" / "missing" ABORTs preflight.
5. (Entry only) Kill switch not tripped per Decision 7.

**ABORT behavior:** Pushover `"Tactical Trading ABORT: {reason}"`, exit code 1 (Task Scheduler logs non-zero). No trade attempted.

**Rationale:** Winston's clock-discipline / startup-health concern. Catches state drift / outages before the bot trades on bad assumptions. Cheap to implement; high diagnostic value.

**Affects:** `src/preflight.py` (new); both `run_trading.py` and `src/exit_manager.py` call `preflight.check_entry()` / `preflight.check_exit()` first.

### Decision 9: Reconciler Scope

**Choice:** Read-only drift report. Phase 2 ships dry-run-forever; autonomous correction is Phase 3+ and gated by human-confirmation.

**Runs:** After every Entry and Exit task completion (decision: appended to existing tasks, not a new scheduled task — keeps Task Scheduler at 3 entries).

**Checks:**

1. For every `status == "open"` record in `trades.jsonl`: does Alpaca have a matching open position? Open stop order? If not, drift.
2. For every Alpaca open position: is there a matching `status == "open"` record? If not, drift (orphan position).
3. For every Alpaca open order: is there a matching record? If not, drift (orphan order).

**Output:** When drift is detected, Pushover with a structured summary. Writes to `data/drift_log.jsonl` for audit.

**No autonomous correction.** Phase 3 may add an "auto-close orphan position" capability, but only after Phase 2's dry-run record shows the false-positive rate is acceptable.

**Rationale:** Murat (party mode): reconciliation that autonomously acts on positions needs dry-run + human-confirmation gate. Phase 2 establishes the read-only baseline.

**Affects:** `src/reconciler.py` (new), `data/drift_log.jsonl` (new).

### Decision 10: Wash-Sale Schema (record-only Phase 2)

**Choice:** Record the data; do not enforce in Phase 2 (paper account — wash-sale rules don't legally apply to paper trades). Phase 3 (live) gains enforcement; Phase 2 builds the audit trail.

**Schema additions to closed records:**

```json
{
  "wash_sale": {
    "is_loss": true,
    "loss_amount": -150.50,
    "lots_within_30d": [
      {"trade_id": "...", "entry_time": "...", "fill_qty": 100, "fill_price": 91.30}
    ],
    "potential_wash_sale": false
  }
}
```

**Computation:** At exit time, if `pnl_dollars < 0`, scan `trades.jsonl` for any entries in the same symbol within 30 days of `exit_time_actual`. Record findings.

**Rationale:** Winston: Phase 3 live trading needs clean wash-sale bookkeeping from day one. Phase 2 paper trades that establish the discipline mean Phase 3 doesn't start with retroactive audit.

**Affects:** `src/exit_manager.py` (new computation step), `src/trade_logger.py` (schema), `docs/data-models.md` v2.

### Decision 11: Module Boundaries

**Choice:** 4 new modules in `src/`. `run_trading.py` gains imports but stays orchestrator-shaped (~120 lines max post-Phase-2).

| Module | Purpose | Public API |
|---|---|---|
| `src/risk.py` | Stops, sizing, concentration, kill switch | `compute_stop_price()`, `compute_position_size()`, `check_concentration()`, `check_kill_switch()` |
| `src/macro_consumer.py` | Read + validate MACRO sidecar | `validate() -> (ok, reason, regime_data)`, `size_multiplier(regime_data) -> float` |
| `src/preflight.py` | Health checks before any trade logic | `check_entry()`, `check_exit()` — each returns `(ok, reason)` |
| `src/reconciler.py` | Read-only drift report | `report() -> list[dict]`, `notify_drift(drift)` |

**No `src/kill_switch.py`** — folded into `risk.py` (Amelia: "one boolean function, it belongs in `risk.py`"). **No `src/config.py` yet** — constants stay inline per-module; promote when 3+ modules share the same constant.

**Affects:** New files above; minor edits to `run_trading.py`, `src/exit_manager.py`, `src/trade_logger.py`, `src/order_builder.py`.

### Decision 12: Trade Ledger Schema v2 (additive)

**Choice:** Additive fields only. No `schema_version` field yet (Amelia: gold-plating until Phase 3). Phase 2 readers use `.get(key, default)`.

**New fields on entry record:**

```json
{
  // all Phase 1 fields preserved
  "stop_order_id": "...",
  "stop_price": 89.02,
  "stop_rule_used": "fixed_pct_2.5",
  "sizing_rule_used": "concentration_cap" | "risk_based",
  "macro_snapshot": {
    "run_timestamp": "...",
    "composite_band": "yellow",
    "regime": "mid",
    "weights_hash": "abc1234"
  }
}
```

**New fields on closed record (in addition to Phase 1 exit fields):**

```json
{
  // all Phase 1 close fields preserved
  "exit_reason": "scheduled" | "stop_fired" | "stop_cancel_failed" | "manual",
  "wash_sale": { /* see Decision 10 */ }
}
```

**Document this in `docs/data-models.md` v2 when Phase 2 ships.** The current `data-models.md` describes Phase 1; Phase 2 needs an updated section, not a new file.

### Implementation Sequence (per Amelia)

**MVW Phase 2.0 — ships first:**

1. `src/macro_consumer.py` + `tests/test_macro_consumer.py`
2. `src/risk.py` (stops + sizing + concentration) + `tests/test_risk.py`
3. `src/preflight.py` + `tests/test_preflight.py`
4. `run_trading.py` + `order_builder.py` + `trade_logger.py` updates (stop placement, sizing call, schema)
5. `exit_manager.py` updates (stop cancellation, exit_reason, wash_sale recording)
6. `setup_task.ps1` unchanged

**Phase 2.1 — ships after MVW stabilizes:**

7. `src/reconciler.py` + drift logging
8. Kill switch trigger 2 (consecutive-loss counter)
9. `data/macro_weights_allowlist.json` initial bootstrap

**Phase 2.2 — deferred until Phase 2 data informs:**

10. ATR-based stops
11. Limit orders (if Phase 2 reveals slippage is materially worse than fixed-pct stops anticipate)

### Cross-Component Dependencies

- `preflight.py` depends on `macro_consumer.py` (validation) and `risk.py` (kill switch).
- `macro_consumer.py` depends on the MACRO sidecar file at `../market_dashboard/data/latest.json` — filesystem only.
- `risk.py` is pure (no Alpaca calls); depends on inputs only.
- `reconciler.py` reads Alpaca + reads `trades.jsonl`; never writes either.
- `run_trading.py` orchestrates: `preflight → macro_consumer → risk → order_builder → trade_logger`.
- `exit_manager.py` orchestrates: `preflight → load trades → for each ripe: cancel stop → submit SELL → wait → compute wash_sale → save`.

### Decisions Provided by Phase 1 Baseline (not re-decided)

- Python 3.14, own `.venv/`, `alpaca-py`, `python-dotenv`, `yfinance`, `pandas-market-calendars`, `requests` — locked Phase 1.
- Windows Task Scheduler 3-task layout — locked Phase 1.
- `paper=True` safety pin — locked.
- Append-only JSONL persistence — locked.
- No cross-sibling imports — locked.
- No DB / no API publication / no UI — locked through Phase 3.

---

## Implementation Patterns & Consistency Rules

This section documents rules that prevent AI agents (or future humans) from making divergent choices on details that should be uniform across the codebase. Most are inherited from Phase 1 / [_bmad-output/project-context.md](../../_bmad-output/project-context.md); Phase 2 additions are explicit.

### Naming conventions

| Element | Convention | Examples |
|---|---|---|
| Files (Python) | `snake_case.py` | `alpaca_connector.py`, `macro_consumer.py` |
| Test files | `test_<module>.py` (matches module name under test) | `test_risk.py`, `test_macro_consumer.py` |
| Functions | `snake_case` | `compute_stop_price`, `check_concentration` |
| Module-level constants | `UPPER_SNAKE_CASE` at top of file | `NOTIONAL`, `FILL_POLL_INTERVAL`, `STOP_PCT_DEFAULT` |
| Classes | `PascalCase` | (Rare — mostly Alpaca SDK types) |
| Private helpers | `_leading_underscore` (use sparingly; prefer module-private functions) | `_load_allowlist` |
| Schema field names (JSONL) | `snake_case` | `trade_id`, `fill_price`, `macro_snapshot`, `stop_rule_used` |
| Pushover titles | Title case, `Tactical Trading <ACTION> [STATE]` | `Entered XLE $10,000`, `Tactical Trading ENTRY FAILED` |

### Code style (inherited from project-context.md)

- **No comments** unless the WHY is non-obvious (a hidden constraint, a subtle invariant, a workaround for a specific bug). Don't explain WHAT.
- **No premature abstraction.** Three similar lines beats a helper. Introduce a helper only when the third site appears.
- **No half-finished implementations.** Ship complete or don't ship.
- **No error handling for impossible scenarios.** Trust internal guarantees; validate only at system boundaries.
- **No backwards-compatibility shims** for unused fields or renamed-but-still-exported names. If unused, delete it.

### Error handling pattern

**Three tiers:**

1. **Boundary errors** (Alpaca, yfinance, Pushover, MICRO/MACRO files) — `try/except` at the consumer site. Convert to a `RuntimeError` with diagnostic context if propagating; otherwise log and continue when failure is non-fatal.
2. **Non-fatal failures** — log with `print()` to stdout (Task Scheduler captures), continue. Examples: Pushover not configured, benchmark fetch fails post-SELL.
3. **Fatal failures** — propagate to the entrypoint's top-level `try/except`. Pushover the failure title + message. Re-raise so Task Scheduler logs a non-zero exit.

**Pattern at every entrypoint:**

```python
if __name__ == "__main__":
    load_env()
    try:
        main()
    except Exception as e:
        pushover.send("Tactical Trading <CONTEXT> CRASHED", str(e))
        raise
```

**Pre-flight pattern (Phase 2 new):**

```python
ok, reason = preflight.check_entry()
if not ok:
    pushover.send("Tactical Trading ABORT", reason)
    sys.exit(1)
```

`sys.exit(1)` for clean ABORT (preflight failure); `raise` for crashes (so Task Scheduler distinguishes "we chose to stop" from "we crashed").

### Validation function return shape

Phase 2 validation functions return `tuple[bool, str]` or `tuple[bool, str, T | None]`:

```python
def validate(...) -> tuple[bool, str, dict | None]:
    """Returns (ok, reason, payload). reason is human-readable; payload is None on failure."""
```

- `ok=True, reason="ok"` — success path
- `ok=True, reason="<stale_explanation>"` — degraded but usable (e.g., MACRO stale → trade neutral)
- `ok=False, reason="<failure_explanation>"` — caller blocks

This shape is uniform across `preflight.check_entry`, `preflight.check_exit`, `macro_consumer.validate`, `risk.check_concentration`, `risk.check_kill_switch`. No `Optional[Result]` objects, no exception-as-control-flow, no boolean-only returns (caller always needs `reason` for Pushover).

### Logging & notifications

| Where | Used for | Format |
|---|---|---|
| `print()` to stdout | Diagnostic info, run output (Task Scheduler captures) | Plain text |
| `pushover.send(title, body)` | Trade events, failures, ABORTs | Title ≤ 250 chars, body ≤ 1024 |
| `data/trades.jsonl` | Trade ledger | JSON Lines, one record per line |
| `data/drift_log.jsonl` (Phase 2.1) | Reconciler output | JSON Lines, one event per line |
| `data/account_state.json` (Phase 2) | Drawdown high-water-mark | Single JSON object, rewritten each Entry |
| `data/macro_weights_allowlist.json` (Phase 2) | Provenance allow-list | JSON array of hashes |

**No log files yet.** stdout + Pushover is sufficient through Phase 2. Phase 3 may add structured logging to a file when live capital makes audit forensics matter more.

### Timestamp & datetime conventions

- **New timestamps:** `datetime.now(timezone.utc).isoformat()` — UTC, ISO 8601 with `+00:00` suffix.
- **Phase 1 timestamps:** preserved as-is (mix of `str(datetime)` and `.isoformat()`). Phase 2 readers tolerate both via `datetime.fromisoformat()` which parses both.
- **No naive datetimes** in any new Phase 2 code.
- **Trading-day math:** always via `pandas_market_calendars.get_calendar("NYSE")`. Never roll-your-own business-day arithmetic.

### JSON / JSONL conventions

- **`data/trades.jsonl`** — one JSON object per line. UTF-8. Append-only for entries; in-place rewrite-all for close-updates.
- **Field names:** `snake_case`.
- **Floats:** round dollars to 2 dp (`pnl_dollars`), percentages to 4 dp (`pnl_pct`, `spy_return_pct`).
- **Missing values:** `null`, not `""` or `0`.
- **Booleans:** `true`/`false` (JSON literals), not strings.
- **Optional schema fields** (added Phase 2): readers use `record.get("field", default)`. No `KeyError` from absence.

### Idempotency & dedup

- **Alpaca is authoritative for positions and orders.** `already_traded_today(symbol)` + `at_position_limit()` query Alpaca, not `trades.jsonl`. Same pattern for reconciler.
- **`trades.jsonl` may lag Alpaca** if logging ever fails. Phase 2 reconciler detects drift; never auto-corrects (Phase 2).
- **Entry task is idempotent** — same signal day, same symbol, no double-buy (Alpaca position+order check).
- **Exit task is idempotent** — only processes `status == "open"` records past planned exit; closed records skipped.

### Cross-sibling integration

- **Read by relative path:** `Path(__file__).resolve().parent.parent.parent / "tactical_markets" / "data" / "theses.jsonl"` (and analogous for MACRO).
- **Never `import` from a sibling.** Forbidden. If tempted, surface the design question.
- **Schema dependencies are documented** in [docs/integration-architecture.md](../../docs/integration-architecture.md). If a sibling changes its schema, this project's consumer surfaces the failure at validation time (Decision 6).

### Test patterns (Phase 2)

- **Location:** `tests/` at project root.
- **Discovery:** default `pytest`. File pattern `test_*.py`, function pattern `test_*`.
- **One test file per `src/` module under test.** No nesting unless a single file would exceed ~300 lines.
- **Mocking:** `unittest.mock` (stdlib). No `pytest-mock`, no `responses`, no `factory_boy` — gold-plating until proven needed.
- **No real network calls** in unit tests. Alpaca/yfinance/Pushover are mocked. Integration smoke tests live in `if __name__ == "__main__":` blocks in `src/` modules (Phase 1 pattern continues).
- **Fixtures:** module-level pytest fixtures only. No conftest hierarchies until 3+ test files share fixtures.
- **Test naming:** `test_<behavior_being_tested>` — describe the expected behavior, not the function name. `test_compute_stop_price_default_returns_2_5_pct_below_entry`, not `test_compute_stop_price`.

### Constants vs. config

- **Inline constants** at the top of each module (`NOTIONAL = 10_000` in `order_builder.py`).
- **Promote to `src/config.py`** only when 3+ modules share the same constant. (Phase 2 may or may not cross this threshold; do not pre-create `config.py`.)
- **No YAML / TOML config files** in Phase 2. The constants live in code, version-controlled.
- **Env vars** (`.env`) only for secrets and the rare deployment-varying value (e.g., `ALPACA_BASE_URL`).

### Module entry surface

Each new Phase 2 module has a small public surface (functions only, no classes unless an SDK forces it):

| Module | Public functions |
|---|---|
| `src/risk.py` | `compute_stop_price`, `compute_position_size`, `check_concentration`, `check_kill_switch` |
| `src/macro_consumer.py` | `validate`, `size_multiplier` |
| `src/preflight.py` | `check_entry`, `check_exit` |
| `src/reconciler.py` | `report`, `notify_drift` |

Anything else is module-private (no leading underscore is OK; Python convention is "don't import what isn't documented").

### Repository workflow (already locked)

- **Primary working dir** (`tactical_markets_trading/`) is edit-only.
- **Git repo** lives at `c:\Users\rekwa\ian_projects\_genai_tmp\`.
- **Every commit:** copy to mirror → prefix every `git` command with `cd .../_genai_tmp &&` → HEREDOC commit messages → specific path staging (never `git add .`) → co-author trailer matching running model.
- **Remote** `IanRekward/GenAI_Messing` branch `main`. Push pre-authorized.

---

## Project Structure (Phase 2 target state)

This is the complete tree after Phase 2.0 + 2.1 ship. New files vs. Phase 1 are marked `# NEW`.

```
tactical_markets_trading/
├── run_trading.py                  # Entry task — orchestrates preflight → macro → risk → order → log
├── setup_task.ps1                  # Windows Task Scheduler registration (unchanged from Phase 1)
│
├── src/
│   ├── alpaca_connector.py         # .env loader + TradingClient(paper=True) factory (unchanged)
│   ├── order_builder.py            # Read theses.jsonl, build + submit MarketOrderRequest;
│   │                                 # NEW Phase 2: submit stop-sell after entry fill
│   ├── trade_logger.py             # Wait for fill, write entry record;
│   │                                 # NEW Phase 2: write extended schema (stop_*, macro_snapshot, sizing_rule_used)
│   ├── exit_manager.py             # Find ripe positions, cancel stop, market-sell, log;
│   │                                 # NEW Phase 2: record exit_reason + wash_sale
│   ├── pushover.py                 # Minimal HTTP client (unchanged)
│   ├── risk.py                     # NEW — Stops, sizing, concentration, kill switch
│   ├── macro_consumer.py           # NEW — Read + validate ../market_dashboard/data/latest.json
│   ├── preflight.py                # NEW — Health checks before any trade logic
│   └── reconciler.py               # NEW Phase 2.1 — Read-only drift report
│
├── tests/                          # NEW Phase 2 — pytest
│   ├── test_risk.py                # NEW — sizing math, stop computation, concentration cap, kill switch
│   ├── test_macro_consumer.py      # NEW — staleness, schema_version, weights_hash, file-missing
│   ├── test_preflight.py           # NEW — health check fail conditions
│   └── test_reconciler.py          # NEW Phase 2.1 — drift detection
│
├── research/                       # OFF the production path (unchanged from Phase 1)
│   ├── compare_strategies.py
│   ├── sensitivity.py
│   ├── news_sentiment.py
│   └── data/                       # CSVs + markdown reports
│
├── data/
│   ├── trades.jsonl                # Append-only ledger (schema v2 from Phase 2 onward — additive)
│   ├── drift_log.jsonl             # NEW Phase 2.1 — reconciler output
│   ├── account_state.json          # NEW Phase 2 — drawdown high-water-mark
│   └── macro_weights_allowlist.json # NEW Phase 2 — provenance allow-list for MACRO weights_hash
│
├── _bmad-output/
│   ├── planning-artifacts/
│   │   ├── prd.md                                 # PRD (saas_b2b) — end-state vision
│   │   ├── prd-validation-report.md
│   │   ├── architecture.md                        # THIS DOCUMENT
│   │   ├── FINTECH_TRADING_BOT_REFERENCE_MATERIALS.md
│   │   └── research/
│   │       └── domain-active-trading-bot-regime-strategies-research-2026-05-11.md
│   ├── implementation-artifacts/                  # (placeholder; Phase 2 stories land here)
│   ├── test-artifacts/                            # (placeholder)
│   └── project-context.md                         # Rules for AI agents (Locked rules table)
│
├── docs/                                          # Brownfield doc baseline (generated 2026-05-13)
│   ├── index.md
│   ├── project-overview.md
│   ├── architecture.md                            # PHASE 1 architecture (current state)
│   ├── source-tree-analysis.md
│   ├── data-models.md                             # PHASE 1 trades.jsonl schema — needs v2 update at Phase 2 ship
│   ├── integration-architecture.md
│   ├── development-guide.md
│   └── project-scan-report.json
│
├── TRADING_INTEGRATION_PLAN.md     # Preserved — original integration plan (revised 2026-05-08)
├── ROADMAP_ALPACA_INTEGRATION.md   # Preserved — original Phase 1/2/3 brief
├── TODO.md                          # Source of truth for Phase 1 freeze + Phase 2 lessons
│
└── .venv/                           # Python 3.14 + alpaca-py + yfinance + pandas-market-calendars
                                     # + python-dotenv + requests + pytest (NEW Phase 2)
```

### File-to-decision map

Each Phase 2 file traces to a specific architectural decision:

| File | Decisions it implements |
|---|---|
| `src/risk.py` | D2 (stop level rule), D3 (sizing), D4 (concentration), D7 (kill switch) |
| `src/macro_consumer.py` | D5 (size-down policy), D6 (staleness + failure recovery) |
| `src/preflight.py` | D8 (pre-flight health check) |
| `src/reconciler.py` | D9 (reconciler scope) |
| `src/order_builder.py` (updated) | D1 (stop placement — submit stop after entry fill) |
| `src/exit_manager.py` (updated) | D1 (cancel stop before SELL), D10 (wash-sale recording), D12 (exit_reason field) |
| `src/trade_logger.py` (updated) | D12 (schema v2 — additive fields) |
| `data/account_state.json` | D7 (drawdown high-water-mark persistence) |
| `data/macro_weights_allowlist.json` | D6 (provenance allow-list) |
| `data/drift_log.jsonl` | D9 (reconciler audit trail) |
| `tests/*` | D-style: testing framework (Step 3) — first 3-5 tests per Murat/Amelia |

### Integration boundaries

```
┌───────────────────────────────────────────────────────────────────┐
│                    tactical_markets_trading                       │
│                                                                   │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐        │
│   │ preflight    │───▶│macro_consumer│    │   risk       │        │
│   │              │    │              │    │              │        │
│   │ - .env check │    │ - validate() │    │ - stop_price │        │
│   │ - Alpaca up  │    │ - regime_mult│    │ - position_sz│        │
│   │ - MICRO file │    │              │    │ - concentrat │        │
│   │ - MACRO valid│    │              │    │ - kill_switch│        │
│   │ - kill check │    │              │    │              │        │
│   └──────┬───────┘    └──────┬───────┘    └──────┬───────┘        │
│          │                   │                   │                │
│          └─────────┬─────────┴───────────────────┘                │
│                    │                                              │
│                    ▼                                              │
│              ┌─────────────────┐         ┌─────────────────┐      │
│              │ run_trading.py  │────────▶│ order_builder   │      │
│              │   (orchestrate) │         │ trade_logger    │      │
│              └─────────────────┘         └─────────────────┘      │
│                                                  │                │
│                                                  ▼                │
│                                          data/trades.jsonl        │
└────────────────────┬──────────────────────────────────────────────┘
                     │
   ┌─────────────────┼──────────────────┐
   │                 │                  │
   ▼                 ▼                  ▼
[Alpaca API]   [Pushover API]    [MACRO sidecar file]
                                  [MICRO theses.jsonl]
```

### What lives where — quick reference

| Concern | Lives in |
|---|---|
| Entry orchestration | `run_trading.py` |
| Exit orchestration | `src/exit_manager.py` |
| Health checks | `src/preflight.py` |
| MACRO consumption + regime gating | `src/macro_consumer.py` |
| Stop level computation | `src/risk.py` → `compute_stop_price` |
| Stop order submission to broker | `src/order_builder.py` (after entry fill) |
| Stop order cancellation at exit | `src/exit_manager.py` |
| Position sizing | `src/risk.py` → `compute_position_size` |
| Concentration enforcement | `src/risk.py` → `check_concentration` |
| Kill switch | `src/risk.py` → `check_kill_switch` |
| Trade ledger writes | `src/trade_logger.py` |
| Wash-sale recording | `src/exit_manager.py` (calls into trade history) |
| Drift detection | `src/reconciler.py` |
| Notifications | `src/pushover.py` (called from all entrypoints) |
| State persistence | `data/*.jsonl`, `data/account_state.json`, `data/macro_weights_allowlist.json` |
| Scheduling | `setup_task.ps1` (3 Windows Tasks; unchanged from Phase 1) |

---

## Architecture Validation

### Coherence checks

| Check | Result |
|---|---|
| Tech stack internally consistent? | ✅ Python 3.14 + `alpaca-py` + `pandas-market-calendars` + `yfinance` + `pytest` — no conflicts; all support Python 3.14. |
| Decisions don't contradict each other? | ✅ Verified: broker-side stops (D1) replaces local-stop-in-JSONL (was conflict); MACRO stale=neutral / broken=block (D6) distinct policies; kill switch checks preflight (D7+D8) consistent. |
| Patterns align with module boundaries? | ✅ Validation-function shape `(ok, reason, payload?)` is uniform across `preflight`, `macro_consumer`, `risk`. Error handling tiers map cleanly onto module roles. |
| Project structure supports the decisions? | ✅ Each Phase 2 decision traces to a specific file (see "File-to-decision map"). No orphan decisions. |
| Cross-component dependencies acyclic? | ✅ `preflight → macro_consumer + risk` → `run_trading.py orchestrates`. No cycles. `risk.py` is pure (depends on inputs only). |
| Hard constraints preserved? | ✅ No shorts (long-only by construction in `risk.py`); no cross-sibling imports (MACRO read via filesystem); `paper=True` safety pin retained; audit trail extended not weakened. |

### Requirements coverage

**PRD Functional Requirements — Phase 2 coverage:**

| FR | Title | Phase 2 status | Implementing decision |
|---|---|---|---|
| FR1 | MACRO regime consumption | ✅ Phase 2 | D5, D6 (`src/macro_consumer.py`) |
| FR2 | MICRO theses (limited subset) | ✅ Phase 1 (continues) | Phase 1 `order_builder.py` (PRD richer fields gracefully unhandled — see D-context) |
| FR3 | Signal unavailability → disable new trades | ✅ Phase 2 | D6 (file-missing block), D8 (preflight) |
| FR4 | Regime-based strategy routing | ⚠️ Partial — sizing tier only (D5), full ensemble routing is Phase 4+ | D5 |
| FR5 | Pre-market trade list with thesis details | ⏳ Phase 1 trades via Pushover; full dashboard is Phase 4+ | — |
| FR6 | Manual "Execute" click | ❌ Rejected — kept automated per locked TODO rule. Phase 3 may add pre-flight confirmation gate. | (Decision in context analysis) |
| FR7 | Limit order TTL handling | ⏳ Deferred to Phase 2.2 — Phase 2 uses market orders + broker-side stops | — |
| FR8 | Position tracking + continuous P&L | ✅ Phase 1 (continues) + Phase 2 reconciler | D9 |
| FR9 | Auto-exit on target/stop/timeout | ✅ Phase 2 — broker-side stop (D1) + scheduled timeout (Phase 1) | D1, D12 (`exit_reason`) |
| FR10 | Exit logging | ✅ Phase 2 enriched | D12 schema v2 |
| FR11 | Risk-based position sizing | ✅ Phase 2 (binding when concentration cap doesn't) | D3 |
| FR12 | Pre-trade limit checks | ✅ Phase 2 | D4 |
| FR13 | Kill switch | ⚠️ Phase 2 primitive only (drawdown + consecutive-loss). Sharpe/win-rate triggers are Phase 3. | D7 |
| FR14 | PDT rules | ⏳ Phase 3 (only matters live) | — |
| FR15 | Real-time dashboard | ⏳ Phase 4+ | — |
| FR16 | Daily 5 PM ET report | ⏳ Phase 3+ | — |
| FR17 | Trade CSV export | ⏳ Phase 3 — schema fields exist in Phase 2; CSV export deferred | D10, D12 |
| FR18 | Weekly summary | ⏳ Phase 3+ | — |
| FR19 | Backtesting module (production integration) | ⏳ Phase 4+ — `research/` scripts stay off-production-path | — |
| FR20 | Backtest metrics + sensitivity | ⏳ Phase 4+ (research artifacts already exist) | — |

**PRD Non-Functional Requirements — Phase 2 coverage:**

| NFR | Title | Phase 2 status |
|---|---|---|
| NFR1 | <500ms dashboard latency | ⏳ Phase 4+ (no dashboard) |
| NFR2 | 2s API latency, 5s timeout w/ cache | ⚠️ Partial — MACRO uses cached file (always-on-disk); MICRO read is fast (single-file tail) |
| NFR3 | Backtest <5min for 10y dataset | ⏳ Phase 4+ |
| NFR4 | 99% uptime during market hours | ✅ Phase 2 — preflight catches outages; broker-side stops mean uptime less critical |
| NFR5 | Failsafe / auto-exit during outage | ✅ Phase 2 — broker-side stops (D1) survive multi-day VPS outage |
| NFR6 | Signal freshness <1h / staleness <2h | ✅ Phase 2 with stronger 4h hard reject (D6) |
| NFR7 | Encrypted credentials | ✅ Phase 1 baseline (`.env`, gitignored) |
| NFR8 | Local data storage | ✅ Phase 1 baseline (no cloud) |
| NFR9 | Dashboard local-only | ⏳ Phase 4+ (no dashboard) |
| NFR10 | Cached MACRO regime | ✅ Phase 2 — MACRO sidecar is a file; cache is on-disk by construction |
| NFR11 | Partial order fills | ✅ Phase 1 baseline (`wait_for_fill` terminates only on FILLED) |
| NFR12 | Retry logic on transient errors | ⏳ Phase 2.1 candidate — not in MVW; current `wait_for_fill` is the only retry surface |

**Phase 2 graduation criterion** (Murat, party mode): 20+ paper trades with ≥2 stop-triggered exits, ≥1 MACRO size-down, zero reconciliation false-positives. Recorded for transcription to TODO.md when Phase 2 begins.

### Gap analysis

**Known architectural gaps acknowledged here, addressed at later phases:**

1. **No retry/backoff on transient Alpaca errors** (NFR12). Phase 2.1 can add exponential backoff in `wait_for_fill` if real production firings show transient failures.
2. **No log-file persistence.** stdout + Pushover suffice through Phase 2; Phase 3 may add structured logging when live forensics matter more.
3. **No CI/CD for tests.** Phase 2 tests run locally (`pytest`); Phase 3 may add GitHub Actions for the cross-sibling repo.
4. **No `requirements.txt`** — Phase 1 didn't have one; Phase 2 adds `pytest` ad-hoc. Phase 3 should formalize dependency management before live capital.
5. **No formal schema versioning** — Phase 2 schema bump is additive (`.get(field, default)` pattern). Phase 3 may need real versioning if a breaking change becomes necessary.
6. **Reconciler is read-only.** Detected drift requires manual reconciliation. Autonomous correction is Phase 3+ behind a human-confirmation gate.
7. **Phase 4 question deferred:** how does multi-strategy ensemble (PRD FR4) interact with the single-strategy assumptions baked into Phase 2 (e.g., per-trade sizing assumes one entry per signal)? Phase 4 architecture document re-opens this.

### Decision traceability matrix

Every PRD/locked rule cited in this document traces to an authoritative source:

| Constraint | Source | Where this doc cites it |
|---|---|---|
| No shorts ever | [_bmad-output/project-context.md](../../_bmad-output/project-context.md) Locked rules | Step 2 context analysis, D3 (long-only sizing) |
| paper=True safety pin | [src/alpaca_connector.py:22](../../src/alpaca_connector.py#L22) | Step 2, D8 (preflight check 2) |
| Files-on-disk integration | [docs/integration-architecture.md](../../docs/integration-architecture.md) + MICRO/MACRO docs | Step 2 mismatch resolutions, D5, D6 |
| Phase 3 gate: 50+ paper trades + ROE doc | [TODO.md](../../TODO.md) Locked rules | Phase boundary table at top |
| MACRO sidecar contract | [market_dashboard integration brief](../../../market_dashboard/_bmad-output/planning-artifacts/integration-brief-for-tactical-bot.md) | D5, D6 |
| MICRO theses schema | [tactical_markets data-models.md](../../../tactical_markets/docs/data-models.md) | Step 2 mismatch 1 |
| 2026-05-08 design pass (Phase 1 locks) | [TODO.md](../../TODO.md) Locked Phase 1 design | Phase boundary, Step 2 |

### Readiness for implementation

| Dimension | Status |
|---|---|
| All Phase 2 decisions documented with rationale | ✅ 12 decisions, each with rationale + affected files |
| All decisions traceable to source | ✅ See traceability matrix |
| Module boundaries explicit | ✅ 4 new modules + edits to 4 existing; file-to-decision map provided |
| Schema additions documented | ✅ D12; needs `docs/data-models.md` v2 at ship time |
| Patterns + naming conventions defined | ✅ Section 5 |
| Test plan defined (framework + first tests) | ✅ pytest, first 3 test files specified |
| Open questions explicit | ✅ "Open Questions Flagged for Later Steps" + "Gap analysis" |
| Phase 2 graduation criterion defined | ✅ 20+ trades, 2+ stop exits, 1+ MACRO size-down |
| Hard constraints preserved | ✅ All 6 (no shorts, no cross-sibling imports, files-on-disk, Phase 3 gate, paper=True, audit trail) |

**Implementation can proceed when Phase 1 freeze lifts (≥5 clean Phase 1 trades).**

---

## Completion Summary

This architecture document captures the **Phase 2 forward-looking design** for `tactical_markets_trading`, layered on top of the brownfield Phase 1 baseline in [docs/architecture.md](../../docs/architecture.md). It was produced via the `bmad-create-architecture` workflow over 8 steps, with party-mode stress-testing (Winston, Murat, Mary, Amelia) that reshaped four meaningful decisions before they were locked.

**What's in this document:**

- **Project Context Analysis** — 20 FRs + 12 NFRs categorized by phase; 3 PRD-vs-reality mismatches resolved; cross-cutting concerns enumerated.
- **Starter Evaluation** — brownfield N/A; pytest as the one new framework decision.
- **12 Core Architectural Decisions** — risk primitives (stops, sizing, concentration, kill switch), MACRO integration policy, preflight + reconciler + wash-sale schema, module boundaries.
- **Implementation Patterns** — naming, error handling, validation-function shape, logging, timestamps, JSON conventions, test patterns.
- **Project Structure** — complete Phase 2 target tree with file-to-decision map and integration boundaries.
- **Validation** — coherence checks, full FR/NFR coverage matrix, gap analysis, traceability matrix, implementation-readiness assessment.

**What's NOT in this document (intentionally):**

- Phase 3 live-capital design (PDT enforcement, full Sharpe-based kill switch, wash-sale enforcement logic, pre-flight confirmation gate) — deferred to a Phase 3 architecture pass triggered when Phase 2 graduation criteria are met.
- Phase 4+ end-state (multi-strategy ensemble, dashboard, Tier 2 single stocks) — north star only; not architected here.
- Detailed module implementation (function bodies, line-by-line code). That's the implementation phase's job.

**Hand-off to implementation:**

When Phase 1 unfreezes (≥5 clean Phase 1 trades), the next steps are:

1. **`bmad-create-epics-and-stories`** — break Phase 2 decisions into implementable stories using this document as input. The "Implementation Sequence" section (MVW Phase 2.0 → Phase 2.1 → Phase 2.2) is the natural epic outline.
2. **`bmad-check-implementation-readiness`** — verify PRD + architecture + epics are consistent before any code lands.
3. **`bmad-dev-story`** — execute each story; this architecture document is the authoritative reference.
4. **Update `docs/data-models.md`** to v2 when the Phase 2 schema additions land. Update `docs/architecture.md` to reference both Phase 1 and Phase 2 once Phase 2 is shipping.


