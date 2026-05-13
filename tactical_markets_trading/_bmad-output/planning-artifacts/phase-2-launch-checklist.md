---
title: Phase 2 Launch Checklist
generated: 2026-05-13
status: ready to use when Phase 1 graduates
---

# Phase 2 Launch Checklist

Run through this before starting the first Phase 2 **wiring** story (Story 1a.2 — submit broker-side stop after entry fill). The pure-function layer (Stories 1a.1, 1b.1-3, 1c.1-2) already shipped on 2026-05-13.

---

## Hard gates (must all be ✅ before Story 1a.2 lands)

### Phase 1 graduation

- [ ] ≥5 clean Phase 1 trades closed in `data/trades.jsonl` with `status: "closed"`
- [ ] Zero stranded `status: "open"` records older than their `exit_time_planned`
- [ ] Pushover history confirms no unhandled crashes (search "Tactical Trading ENTRY FAILED" / "EXIT FAILED" / "CRASHED" — incidents should have post-mortems or be clean recoveries)
- [ ] Mark Phase 1 graduated in `TODO.md` "Status" block (date the graduation)

### Sibling project coordination

- [ ] **MACRO W3 (errors-vs-warnings) resolved** OR bot-side workaround documented
  - As of 2026-05-13, MACRO's `latest.json` has `STALE: stlfsi` and `STALE: jobless_claims` in `errors[]`. The bot's `src/macro_consumer.py` `validate()` will block on any non-empty `errors[]` (architecture D6, strict).
  - **Option A:** MACRO ships W3 — moves STALE warnings to a new `warnings[]` field. Bot uses `.get("warnings", [])` — no change needed.
  - **Option B:** Bot side workaround — `src/macro_consumer.py` filters `errors[]` to only block on entries NOT prefixed with `STALE:`. Add this in Story 1b.1 or a follow-up.
  - Decide which path before Story 1b.5 (preflight wiring) lands.

- [ ] **MACRO weights_hash allow-list current**
  - Check current hash in `../market_dashboard/data/latest.json` against `data/macro_weights_allowlist.json`
  - If mismatch, MACRO has recalibrated since 2026-05-13. Review what changed (bucket weights, regime weighting flip from 5/30 review, etc.) and add new hash to allow-list with reviewer + date + summary.

### Pre-implementation verification

- [ ] All 31 existing Phase 2 unit tests still pass: `.venv/Scripts/python.exe -m pytest tests/ -v`
- [ ] Phase 1 modules syntactically valid (sanity): `.venv/Scripts/python.exe -c "import alpaca_connector, order_builder, trade_logger, exit_manager, pushover"` from `src/`
- [ ] No uncommitted changes in primary or mirror (`git status` clean in `_genai_tmp`)
- [ ] Most recent push to `origin/main` confirmed via `git log origin/main` matches local

---

## Soft prerequisites (recommended but not blocking)

### Configuration sanity

- [ ] `.env` keys present: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `PUSHOVER_TOKEN`, `PUSHOVER_USER`
- [ ] Alpaca account smoke test: `.venv/Scripts/python.exe src/alpaca_connector.py` returns active paper account
- [ ] Windows Task Scheduler tasks healthy: all three show `LastTaskResult: 0` and `NumberOfMissedRuns: 0`

### Phase 1 retrospective

- [ ] Review the 5+ closed trades: any patterns worth feeding into Phase 2 design?
  - Did stops would have fired on any of them? (Phase 1 had no stops; reconstruct retroactively at 2.5% — would Phase 2's stop rule have triggered too tight, too loose, or just right?)
  - Did 2-day holds capture momentum or exit too early? (Compare actual exit price to price 5 days post-entry to see what hold=5 would have produced.)
  - SPY benchmark vs trades: did the bot outperform passive SPY on the 2-day hold window?
- [ ] If retrospective surfaces a strong "stop should be X%" or "hold should be Y days" — update Phase 2 defaults in `src/risk.py` (`STOP_PCT_DEFAULT`) and `src/trade_logger.py` (`HOLD_DAYS`) BEFORE wiring lands, while it's still a one-line change.

### Story ordering decision

- [ ] Confirm MVW Phase 2.0 ship order per architecture (commit `d6e6958` — Implementation Sequence section):
  1. 1a.2 → 1a.3 → 1a.4 → 1a.5 (broker-stop wiring — ship together as one coherent path)
  2. 1b.4 → 1b.5 (preflight skeleton + wire)
  3. 1b.6 + 1c.3 + 1c.4 + 1c.5 (MACRO multiplier + sizing wiring + kill switch — ship together to avoid transitional `phase1_fixed_x_macro_mult` state in `trades.jsonl`)
- [ ] Decide between `/bmad-create-story` (full story file with implementation context) vs. just implementing from `epics.md` directly. Either is fine; story files add ceremony but help when context is thin.

---

## Day-of-Story-1a.2 actions

When you actually start implementation:

1. Read `epics.md` Story 1a.2 acceptance criteria one more time
2. Run `pytest tests/` to confirm green baseline
3. Implement the Alpaca stop-order submission in `src/order_builder.py` after `submit_order` returns
4. Write `tests/test_order_builder.py` mocking Alpaca to verify the stop submission shape (per AC: `StopOrderRequest(symbol, qty=fill_qty, side=SELL, stop_price=computed_stop, time_in_force=GTC)`)
5. Verify `pytest tests/` is still green
6. Smoke-test against real paper Alpaca (manual `run_trading.py` run or wait for tomorrow's 8:35 fire)
7. Commit per two-repo workflow + push

If the first wiring story exposes a real bug in the pure-function layer, ROLL BACK the wiring (revert the commit) before fixing the pure-function — keeping `src/risk.py` and `src/macro_consumer.py` clean during the wiring phase is what made parallel work safe.

---

## Operational state to monitor during Phase 2 buildout

These don't block any story but watching them prevents surprises:

- **MICRO post-freeze design pass** (~2026-05-19): does Rekwa choose path (a), (b), or (c)? See [bot-integration-asks](../../../tactical_markets/_bmad-output/planning-artifacts/bot-integration-asks.md). If (a), Story M3 priority rises (signal_type discriminator).
- **MACRO 2026-05-30 regime-weights review**: if MACRO flips `regime_weights.enabled: true`, expect `weights_hash` to change. W1 coordination should pre-add the new hash to allow-list — but if it doesn't, the bot will block. Watch Pushover.
- **Phase 2 graduation criterion** (architecture AR20): 20+ paper trades, ≥2 stop-triggered exits, ≥1 MACRO size-down, zero reconciliation false-positives. Update `TODO.md` Status block when met to gate Phase 3 design.

---

## Definition of "Phase 2 launched"

- Story 1a.2 commit landed and pushed
- Next Entry task fire (08:35 AM CDT) places a broker-side stop after the entry fill
- Stop visible in Alpaca paper account UI
- `trades.jsonl` entry record has `stop_order_id`, `stop_price`, `stop_rule_used` populated
- Pushover entry message mentions the stop (e.g., `"Entered XLK $10,000. Filled @ $X. Stop at $Y. Exit: ZZZ"`)

After that, the remaining 14 stories follow per the architecture's Implementation Sequence section.
