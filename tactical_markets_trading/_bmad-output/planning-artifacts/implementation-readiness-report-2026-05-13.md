---
stepsCompleted: [1, 2, 3, 4, 5, 6]
date: '2026-05-13'
project: 'tactical_markets_trading'
scope: 'phase-2-implementation'
inputDocuments:
  - "_bmad-output/planning-artifacts/prd.md"
  - "_bmad-output/planning-artifacts/architecture.md"
  - "_bmad-output/planning-artifacts/epics.md"
  - "_bmad-output/planning-artifacts/prd-validation-report.md (supplementary)"
  - "_bmad-output/project-context.md (supplementary)"
  - "docs/architecture.md, data-models.md, integration-architecture.md (Phase 1 baseline)"
verdict: 'READY (Phase 2 implementation may begin when Phase 1 freeze lifts)'
status: 'complete'
---

# Implementation Readiness Assessment Report

**Date:** 2026-05-13
**Project:** tactical_markets_trading
**Scope:** Phase 2 implementation readiness (post-Phase-1-freeze)
**Verdict:** ✅ **READY** — Phase 2 implementation may begin once Phase 1 freeze lifts (≥10 clean Phase 1 trades).

---

## Step 1: Document Discovery

### Documents Found

**Core artifacts** (all present in `_bmad-output/planning-artifacts/`):

| Document | File | Status |
|---|---|---|
| PRD | `prd.md` | ✅ Present (saas_b2b classification, end-state vision) |
| Architecture | `architecture.md` | ✅ Present (Phase 2 forward-looking design, 953 lines) |
| Epics & Stories | `epics.md` | ✅ Present (5 epics, 24 stories, 833 lines) |
| PRD Validation | `prd-validation-report.md` | ✅ Present (PASS, 4/5 GOOD — supplementary) |
| Reference Materials | `FINTECH_TRADING_BOT_REFERENCE_MATERIALS.md` | ✅ Present (regulatory/technical reference) |
| Domain Research | `research/domain-active-trading-bot-regime-strategies-research-2026-05-11.md` | ✅ Present |

**Brownfield supporting docs** (in `docs/`):

| Document | Status |
|---|---|
| `index.md`, `project-overview.md` | ✅ Present (Phase 1 entry points) |
| `architecture.md` | ✅ Present (Phase 1 baseline) |
| `data-models.md` | ✅ Present (Phase 1 trades.jsonl schema) |
| `integration-architecture.md` | ✅ Present (sibling-project + external service contracts) |
| `development-guide.md`, `source-tree-analysis.md` | ✅ Present |
| `_bmad-output/project-context.md` | ✅ Present (locked rules for AI agents) |

**UX Design:** ❌ Not present. **Not a gap** — PRD's UX requirements (FR15-16 dashboard, FR6 manual Execute UI) are Phase 4+ / rejected; Phase 2 stays headless with stdout + Pushover only. No UX spec needed for Phase 2 scope.

### Duplicates

None. Each document type has exactly one canonical version.

### Missing Documents

None for Phase 2 scope.

---

## Step 2: PRD Analysis

### Vision and Scope Alignment

**PRD vision:** End-state algorithmic trading bot consuming MACRO + MICRO signals, with 11+ strategy ensemble, full dashboard, kill switch, tax export, and regime-routed strategy allocation across Tiers 1/2/3.

**Reality check:** PRD describes the Phase 4+ end-state. The Phase 2 architecture document explicitly narrows this to a validated next increment (stops, MACRO size-down, risk-aware sizing, drift detection). The PRD's full vision is the **north star**; Phase 2 is the **starting point**.

**Alignment status:** ✅ Architecture and Epics both correctly anchor to Phase 2 scope and explicitly defer Phase 3+/Phase 4+ requirements. No scope creep.

### PRD Quality (from validation report)

- **Holistic quality rating:** 4/5 GOOD (PASS)
- **SMART score:** 4.88/5.0 (95% of FRs scored ≥4)
- **Traceability:** Fully intact — all FRs map to user needs/business objectives
- **Compliance:** Strong fintech domain coverage (regulatory, audit, risk governance)
- **Classification:** saas_b2b (full-stack scope including operator dashboard)

### Three resolved PRD-vs-reality mismatches (carried into architecture)

| Mismatch | Resolution in Phase 2 architecture |
|---|---|
| MICRO doesn't emit `stop_price`/`target_price`/`confidence`/`hold_window_hours` | Phase 2 computes stops locally per AR6; PRD FR2 marked partial |
| PRD describes MACRO as REST API; reality is `data/latest.json` sidecar | Phase 2 reads file with validation per AR10-AR12; PRD Integration Spec is wrong on channel |
| PRD FR6 wants manual "Execute" UI; TODO.md locks automated | Phase 2 stays automated; Phase 3 may add pre-flight confirmation gate; FR6 rejected |

### Quality concerns flagged for Phase 3+

- **FR17 wash-sale enforcement** (vs. recording-only in Phase 2): the schema lands in Epic 2 Story 2.5, but enforcement is Phase 3. Phase 3 design must produce the actual blocking logic.
- **FR14 PDT rules:** only matters at live capital (Phase 3). Architecturally noted but not designed.
- **NFR12 retry/backoff:** Phase 2.2 candidate; not blocking Phase 2 graduation.

**Verdict:** PRD provides solid foundation. Phase 2 architecture correctly maps PRD vision to a validated next increment. No PRD-side blockers for Phase 2 implementation.

---

## Step 3: Epic Coverage Validation

### FR Coverage Map

All in-scope FRs covered by ≥1 story:

| FR | Epic.Story | Phase | Coverage Status |
|---|---|---|---|
| FR1 (MACRO consumption) | 1b.6 | 2.0 | ✅ Complete |
| FR2 (MICRO theses) | Phase 1 baseline | 1 | ✅ Continues (subset only — PRD's richer fields rejected per architecture) |
| FR3 (signal unavailability disables entries) | 1b.5 | 2.0 | ✅ Complete (preflight ABORT) |
| FR4 (regime-based strategy routing) | 1b.3 | 2.0 partial | ⚠️ Partial — coarse size multiplier only; full 11+ ensemble routing Phase 4+ |
| FR5 (pre-market trade list display) | — | 4+ | ⏳ Deferred |
| FR6 (manual Execute UI) | — | REJECTED | ❌ Rejected per locked TODO rule |
| FR7 (limit orders with TTL) | — | 2.2+ | ⏳ Deferred to Phase 2.2 |
| FR8 (position tracking + continuous P&L) | Phase 1 baseline | 1 | ✅ Continues |
| FR9 (auto-exit on stop/timeout) | 1a.4, 1a.5 | 2.0 | ✅ Complete |
| FR10 (exit logging) | 1a.5 | 2.0 | ✅ Complete |
| FR11 (risk-based sizing) | 1c.1, 1c.3 | 2.0 | ✅ Complete |
| FR12 (concentration limits) | 1c.2, 1c.3 | 2.0 | ✅ Complete |
| FR13 (kill switch — drawdown) | 1c.5 | 2.0 | ✅ Primitive (drawdown only) |
| FR13 (kill switch — consecutive-loss) | 2.4 | 2.1 | ✅ |
| FR13 (kill switch — Sharpe/win-rate) | — | 3+ | ⏳ Deferred to Phase 3 |
| FR14 (PDT rules) | — | 3 | ⏳ Deferred to Phase 3 (live capital only) |
| FR15 (real-time dashboard) | — | 4+ | ⏳ Deferred |
| FR16 (5 PM daily report) | — | 3+ | ⏳ Deferred |
| FR17 (trade log fields) | 1a.3, 2.5 | 2.0, 2.1 | ✅ Schema recorded in Phase 2; CSV export Phase 3+ |
| FR18 (weekly summary) | — | 3+ | ⏳ Deferred |
| FR19 (backtesting module) | — | 4+ | ⏳ Deferred |
| FR20 (backtest metrics) | — | 4+ | ⏳ Deferred |

**NFRs:**

| NFR | Epic.Story | Status |
|---|---|---|
| NFR1 (dashboard latency) | — | ⏳ 4+ |
| NFR2 (API latency w/ cache) | 1b.1 | ✅ Satisfied — MACRO read from file is on-disk, MICRO read is fast tail |
| NFR3 (backtest perf) | — | ⏳ 4+ |
| NFR4 (99% uptime market hours) | Cross-epic | ✅ Preserved — preflight + reconciler catch outages |
| NFR5 (failsafe / multi-day outage) | Epic 1a | ✅ **Critical satisfied** — broker-side stops survive VPS outage |
| NFR6 (signal freshness) | 1b.2 | ✅ Satisfied — 4h hard reject |
| NFR7 (encrypted creds) | Phase 1 baseline | ✅ Continues |
| NFR8 (local storage) | Phase 1 baseline | ✅ Continues |
| NFR9 (dashboard local-only) | — | ⏳ 4+ (no dashboard) |
| NFR10 (cached MACRO) | 1b.2 | ✅ Satisfied — file on disk = cache |
| NFR11 (partial fills) | Phase 1 baseline | ✅ Continues — `wait_for_fill` terminates only on FILLED |
| NFR12 (retry/backoff) | — | ⏳ Deferred to Phase 2.2 candidate |

**ARs (architecture requirements AR1-AR20):**

| AR | Epic.Story | Status |
|---|---|---|
| AR1-AR4 (hard constraints) | All epics (cross-cutting) | ✅ Applied per-story |
| AR5 (broker-side stops) | 1a.2 | ✅ |
| AR6 (fixed-pct stop rule) | 1a.1 | ✅ |
| AR7 (sizing rule min(risk, cap)) | 1c.1 | ✅ |
| AR8 (concentration limits) | 1c.2 | ✅ |
| AR9 (MACRO size-down policy) | 1b.3 | ✅ |
| AR10 (4h staleness) | 1b.2 | ✅ |
| AR11 (two-tier failure recovery) | 1b.1, 1b.2 | ✅ |
| AR12 (provenance allow-list) | 1b.2 | ✅ |
| AR13 (kill switch primitive) | 1c.5 (drawdown), 2.4 (consec) | ✅ |
| AR14 (preflight 5-check) | 1b.4, 1b.5 | ✅ |
| AR15 (reconciler dry-run) | 2.1, 2.2, 2.3 | ✅ |
| AR16 (wash-sale recording) | 2.5 | ✅ |
| AR17 (module boundaries) | All epics (distributed) | ✅ — risk.py, macro_consumer.py, preflight.py, reconciler.py defined |
| AR18 (schema v2 additive) | 1a.3, 1a.5, 1b.6, 1c.3, 2.5 | ✅ — all new fields land in specific stories |
| AR19 (pytest + first tests) | 1a.1, 1b.3, 1b.4, 1c.1, 2.1 | ✅ — first 5 test files mapped to specific stories |
| AR20 (Phase 2 graduation) | Epic 3 (all 3 stories) | ✅ |

### Gaps

**No coverage gaps** within Phase 2 scope. Every in-scope requirement has at least one story.

**Explicit Phase 3+ deferrals** (acknowledged, not gaps):
- FR14, FR13 (full Sharpe/win-rate), FR16, FR17 (CSV export), FR18 → Phase 3
- FR4 (11+ strategies), FR5, FR15, FR19, FR20, NFR1, NFR3, NFR9 → Phase 4+
- NFR12, FR7 → Phase 2.2 (within Phase 2 itself, just sequenced later)

**Verdict:** Coverage is complete for the declared scope. No silent omissions.

---

## Step 4: UX Alignment

**Not applicable.** No UX specification exists. UX is Phase 4+ scope per the architecture's phase plan. Phase 2 is headless (stdout + Pushover only); no dashboard, no operator UI, no manual approval flow. This is a deliberate scope decision, not a gap.

The PRD's manual Execute UI (FR6) is REJECTED per the TODO.md locked rule "automated entries and exits — manual approval reintroduces discretionary contamination." The architecture documents this rejection explicitly.

**Verdict:** ✅ No UX work required. No gap.

---

## Step 5: Epic Quality Review

### Story Independence

**Within-epic forward-dependency check:** Each story within an epic was reviewed for forward dependencies on future stories.

| Epic | Story flow | Independence |
|---|---|---|
| 1a (5 stories) | 1→2→3→4→5 (compute → submit → persist → cancel → record reason) | ✅ Each story buildable from prior stories only |
| 1b (6 stories) | 1→2 (validation cascade), 3 uses 1+2, 4 (preflight skeleton, independent), 5 wires 4, 6 wires 3+5 | ✅ |
| 1c (5 stories) | 1, 2 are pure functions (independent); 3 wires 1+2; 4 independent; 5 uses 4 | ✅ |
| 2 (5 stories) | 1→2 (detect→persist), 3 wires 1+2; 4, 5 independent | ✅ |
| 3 (3 stories) | 1→2→3 | ✅ |

**Cross-epic dependency check:**
- Epic 1a → standalone (depends on Phase 1 baseline only)
- Epic 1b → standalone (parallel to 1a; can ship in either order)
- Epic 1c → depends on 1a (uses stop_price for risk math) and 1b (uses size_multiplier)
- Epic 2 → depends on 1a (reconciler checks stop orders)
- Epic 3 → depends on 1a, 1b, 1c, 2 (counts events from all)

Cross-epic graph is acyclic. ✅

### Story Sizing

All 24 stories scoped for single dev-agent session (≤3 hours of focused work). Largest stories (1c.3 wiring sizing+concentration into orchestration; 1b.6 wiring MACRO multiplier) include explicit transitional behavior to avoid forcing simultaneous sibling-story landings. ✅

### Acceptance Criteria Quality

- 100% of stories use Given/When/Then format ✅
- Average 3-5 ACs per story
- Edge cases and error conditions explicit (e.g., 1a.4 covers stop already filled, cancel race; 1b.2 covers missing allow-list, unknown hash)
- Story 1a.2 explicitly handles broker-rejection failure mode (Pushover + null stop_order_id, do NOT auto-close)
- Story 1c.2 includes corrected example (early draft had a misnumbered calculation; verified in final text)

### File Churn Assessment

Multiple epics touch:
- `src/risk.py` (Epics 1a, 1b, 1c, 2 — each adds a distinct function)
- `run_trading.py` (Epics 1b, 1c, 2 — orchestrator adds steps)
- `src/exit_manager.py` (Epics 1a, 2, 3 — distinct concerns: stop cancel, wash-sale, graduation hook)
- `src/trade_logger.py` (Epic 1a only)

**Assessment:** Overlap is meaningful (same component end-to-end), not unnecessary churn. Each touch adds a distinct user-observable value chunk. Consolidation considered (could collapse Epic 1a+1b+1c into one "Phase 2.0 MVW" epic) but **rejected** because per-epic Pushover-visible value boundaries enable Rekwa to validate each chunk separately before shipping the next. Justified split.

### Database/Entity Creation

N/A — no database. New `data/*.json` files (`account_state.json`, `macro_weights_allowlist.json`, `drift_log.jsonl`, `graduation_state.json`) are each created **only by the story that needs them**, not upfront. ✅

### Test Strategy

- pytest selected (Architecture step 3); `tests/` directory introduced in Epic 1a
- First 5 test files scoped to specific stories (Murat's party-mode recommendation: target highest-P×Impact risks first)
- Pure functions (1a.1, 1b.3, 1c.1, 1c.2) prioritized for unit tests; integration paths via `__main__` smoke runs continue from Phase 1

### Quality Issues

**Two minor observations** (non-blocking):

1. **Story 1c.2 examples:** The first example in the acceptance criteria walks through concentration math that initially had a value error (check_c text says fails but $25,500 > $25,000 — actually the example does fail correctly because it's checking if the total would exceed the 25% cap). Re-read: this is correct as written. No fix needed.

2. **Story 1b.6 transitional state:** The story includes a "transitional" sizing rule (`phase1_fixed_x_macro_mult`) for when 1b.6 lands before 1c.3. Worth noting in the implementation order: ideally 1c.3 lands in the same release as 1b.6 to avoid the transitional state ever appearing in trades.jsonl. But the story is structurally correct.

**Verdict:** ✅ Story quality is high. No blockers.

---

## Step 6: Final Assessment

### Readiness Verdict: ✅ **READY**

Phase 2 implementation may begin when Phase 1 freeze lifts (≥10 clean Phase 1 trades).

### Decision matrix

| Dimension | Status | Notes |
|---|---|---|
| PRD complete and approved | ✅ | 4/5 GOOD, PASS validation |
| Architecture complete and approved | ✅ | 12 decisions, party-mode-stress-tested, 8-step bmad workflow |
| Epics decomposed with stories | ✅ | 5 epics, 24 stories, single-dev-session sized |
| All FRs covered (in-scope) | ✅ | Per FR coverage map above |
| All NFRs covered (in-scope) | ✅ | NFR5 (failsafe) is critical and satisfied by broker-side stops |
| All ARs covered | ✅ | AR1-AR20, including hard constraints |
| Cross-epic dependencies acyclic | ✅ | Per dependency graph |
| Within-epic stories independent | ✅ | No forward references |
| Hard constraints preserved | ✅ | No shorts, no cross-sibling imports, paper=True, files-on-disk, audit trail |
| Phase boundaries explicit | ✅ | Phase 2 / Phase 3 / Phase 4+ scope clearly demarcated |
| Test strategy defined | ✅ | pytest + first 5 test files mapped |
| Phase 2 graduation criterion defined | ✅ | 20+ trades, 2+ stop exits, 1+ MACRO size-down, zero drift |

### Pre-implementation prerequisites (NOT scope of this report, but blocking)

1. **Phase 1 freeze must lift** before any Phase 2 code lands. Status as of 2026-05-13: per TODO.md, "First scheduled fires today" was 2026-05-08. Whether the freeze has actually accumulated ≥10 clean trades by 2026-05-13 is a separate operational question being investigated.
2. **MACRO `weights_hash` allow-list bootstrap** — Story 1b.2 requires `data/macro_weights_allowlist.json` to exist with at least the current MACRO weights_hash. This is a one-time manual step before Phase 2 entries can run; document this as a Phase 2 launch checklist item.

### Recommended next actions

1. **Resolve Phase 1 trade-count concern** (operational, not planning) — investigate why only ~1 trade has accumulated after 5 days; may indicate a scheduler/MICRO-signal/execution issue that needs to be addressed before Phase 2 even makes sense.
2. **Once Phase 1 freeze lifts** (10+ clean trades or operational issues resolved), use `/bmad-create-story` to produce dev-ready story files starting with **Epic 1a Story 1a.1** (pure-function `compute_stop_price` — lowest-risk first commit to validate the new dev flow).
3. **MVW Phase 2.0 ship order** (per architecture and party-mode recommendation):
   - 1a.1 → 1a.2 → 1a.3 → 1a.4 → 1a.5 (broker stops shipped end-to-end first; validate via paper trading)
   - 1b.1 → 1b.2 → 1b.3 (MACRO consumer in place, no wiring yet)
   - 1b.4 → 1b.5 (preflight wired)
   - 1b.6 + 1c.1 + 1c.2 + 1c.3 + 1c.4 + 1c.5 (sizing + MACRO multiplier wired together to avoid transitional state)
4. **Phase 2.1 ship**: Epic 2 (drift, consecutive-loss, wash-sale)
5. **Phase 2.2 stays deferred** until Phase 2.0 + 2.1 data informs (limit orders, ATR stops, retry/backoff)
6. **Epic 3 (graduation tracking) ships last** since it depends on all prior epics emitting events to count

### Top 3 risks remaining

1. **MACRO contract drift** (medium probability, high impact). MACRO is a sibling project under active development. Its `data/latest.json` schema or `weights_hash` may change without coordination. **Mitigation:** AR12 (provenance allow-list) forces explicit human review on hash changes. **Residual risk:** the allow-list could be bypassed by an operator under pressure; document the discipline in Phase 2 launch.
2. **Stop-order rejection by Alpaca** (low-medium probability, medium impact). Some Alpaca paper-account symbols may not support GTC stop orders (e.g., during halts, after-hours). **Mitigation:** Story 1a.2 handles broker-rejection with Pushover + null stop_order_id (position stays open, surfaces to human). **Residual risk:** if rejection is silent or delayed, position is unprotected until exit task fires.
3. **Phase 1 → Phase 2 schema migration** (low probability, low impact). Old Phase 1 rows in `trades.jsonl` lack new fields. Phase 2 readers use `.get(field, default)` per AR18. **Mitigation:** documented in stories 1a.3, 1a.5, 2.5. **Residual risk:** if Phase 1 generates many close records with `exit_reason: null` (because no stop was placed), Epic 3's graduation count for "stop_fired exits" only includes Phase-2-era stops — must ensure the criterion counts Phase 2 trades only.

### Summary

The planning chain (PRD → Architecture → Epics → Stories) is **complete, internally consistent, and ready for implementation**. The four party-mode-stress-tested architectural choices (broker-side stops, Phase 2 concentration limits, Phase 2 wash-sale schema, dry-run reconciler) flow through cleanly to specific stories with testable acceptance criteria. Hard constraints (no shorts, no cross-sibling imports, paper=True, files-on-disk, audit trail) are preserved end-to-end.

**Recommended action:** Resolve the Phase 1 trade-count concern first (operational issue, possibly blocking Phase 1 graduation). Once that's clarified — either Phase 1 has actually graduated, or there's a fixable bug that's been preventing trades — move to `/bmad-create-story` for Epic 1a Story 1a.1 as the first Phase 2 implementation.
