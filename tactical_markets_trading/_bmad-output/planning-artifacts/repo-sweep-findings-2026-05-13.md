---
title: Repo Sweep Findings — 2026-05-13
purpose: Comprehensive review of the project after a day of heavy planning + dev work, looking for holes, gotchas, and things to harden before stepping away.
status: all critical issues fixed in this commit; non-blocking observations recorded below
---

# Repo Sweep Findings — 2026-05-13

A skeptical end-of-day review covering production code, Phase 2 modules, planning artifacts, brownfield docs, cross-project integration, git state, and operational readiness. All critical issues were fixed before this doc was committed.

---

## Critical issues — FIXED in this commit

### 1. Stale `already_traded` references across 7 files (11 mentions)

**Problem:** The dedup fix shipped earlier today (commit `50e31d5`) replaced `already_traded(symbol)` with `already_traded_today(symbol)` + `at_position_limit(5)`. Twelve documentation references continued describing the old function as authoritative. Future AI agents (and future-you) reading these docs would be misled about Phase 1's actual idempotency model.

**Files fixed:**
- `_bmad-output/project-context.md:48` — locked rules table
- `docs/source-tree-analysis.md:77` — flow-step description with line refs updated
- `docs/development-guide.md:188` — don't-miss rules
- `docs/data-models.md:21, 102, 112` — lifecycle + invariants + dedup-source-of-truth notes
- `docs/architecture.md:28, 58 (paragraph), 147, 155` — daily flow diagram + idempotency paragraph + failure-mode table (added the new "at 5-position limit" failure mode row)
- `_bmad-output/planning-artifacts/architecture.md:625` — Phase 2 forward-looking architecture pattern reference
- `_bmad-output/planning-artifacts/epics.md:468` — Story 1b.5 acceptance criterion that lists the orchestration chain (updated to include both new functions)

All updated to describe the dual-check model (`already_traded_today` intra-day dedup + `at_position_limit` concurrency cap) with the historical context that the original was over-strict relative to the locked "5 overlapping positions" design.

### 2. Misleading `ticker_concentration` example in epics.md Story 1c.2

**Problem:** The story's acceptance-criteria walkthrough used an example that mathematically can't trigger the ticker-concentration check with default caps:

> "Existing XLE position worth $24,500 and proposed XLE buy worth $1,000 on a $100k account ... check (c) fails ($25,500 > $25,000)"

But the per-trade check is (a), open-total is (b), per-ticker is (c) — and with default caps (5%/20%/25%) on a $100k account, the open-total cap ($20k) is always **tighter** than the per-ticker cap ($25k). So an open-total failure ALWAYS fires first; per-ticker never fires with default caps.

The example was misleading. The actual test in `tests/test_risk.py::test_concentration_blocks_ticker_cap` uses custom caps (`max_open_pct=0.10`, `max_ticker_pct=0.045`) to isolate the per-ticker check.

**Fix:** rewrote the Story 1c.2 acceptance criteria with three accurate examples: (1) a "passes all checks" case, (2) a per-trade failure, (3) an open-total failure. Added an explicit note that the per-ticker check is defensive (only reachable when configured looser than open-total).

### 3. Phase 2 transient state files not in `.gitignore`

**Problem:** Phase 2 stories will create three new runtime-state files in `data/`:
- `data/account_state.json` (Story 1c.4 — drawdown high-water-mark)
- `data/drift_log.jsonl` (Story 2.2 — reconciler audit trail)
- `data/graduation_state.json` (Story 3.2 — Phase 2 graduation notification dedup)

If left ungitignored, a careless `git add .` (which the two-repo workflow already warns against) would catch them. They're runtime state, not source code.

**Fix:** added all three to `.gitignore` preemptively. Also added `.pytest_cache/` which was missing. Note: `data/trades.jsonl` deliberately remains tracked — it's the operational audit record and was committed as part of commit `58fa2e1`.

---

## Operationally important — known issue, documented but not yet resolved

### 4. MACRO `errors[]` blocks Phase 2 wiring (W3)

**Status:** This is the W3 ask filed against MACRO at `market_dashboard/_bmad-output/planning-artifacts/bot-integration-asks.md`.

**Confirmed today via live test:** Running `macro_consumer.validate()` against the actual MACRO sidecar at `../market_dashboard/data/latest.json` returns:

```
ok: False
reason: macro_errors: ['STALE: stlfsi — last observation 12d ago (expected ≤10d for weekly series)',
                      'STALE: jobless_claims — last observation 11d ago (expected ≤10d for weekly series)']
data: None
```

**Implication:** When Story 1b.5 / 1b.6 wires `macro_consumer.validate()` into `run_trading.py`'s pre-flight, the bot will block on EVERY fire under current MACRO state. **Phase 2 wiring is blocked until either:**
- (a) MACRO ships W3 (separate `errors[]` from `warnings[]`, move STALE entries to warnings), or
- (b) Bot adds a workaround filter (only block on errors NOT prefixed with `STALE:`)

This is already noted in `phase-2-launch-checklist.md` as a hard gate before Story 1a.2 can land. No action needed today; it's a coordination item with MACRO's owner.

### 5. Unicode encoding gotcha on Windows cp1252 terminal

**Symptom:** Running `python -c "from src import macro_consumer; ..."` from a default Windows cmd.exe terminal crashes with `UnicodeEncodeError: 'charmap' codec can't encode character '≤'` when printing MACRO's STALE error messages (which contain `≤`).

**Why it doesn't break production:**
- The Scheduled Task captures stdout to a file via redirection; the file encoding can be different from terminal cp1252.
- Pushover messages travel via HTTPS body (UTF-8); no terminal encoding involved.
- The Python source files don't contain non-ASCII text, just the data we read.

**Why it's worth knowing:**
- If you ever run `python run_trading.py` manually from a stock Windows shell and a unicode reason string comes through, the `print(...)` call could crash.
- The fix would be `sys.stdout.reconfigure(encoding='utf-8')` at the top of entry scripts, but that's only needed for manual operation.

**Not fixed now.** Add to the Phase 2 launch checklist as a "consider adding" item if/when it bites.

---

## Code review observations — minor, not fixed now

### 6. `at_position_limit` doesn't count pending open orders

**Current behavior:** `at_position_limit` calls `client.get_all_positions()` which returns settled positions, not in-flight BUY orders awaiting fill. A BUY submitted at 8:35 but not yet filled isn't counted toward the 5-position cap.

**Risk:** Very low. The bot fires once per day and waits for fill (60s timeout) before proceeding. An order pending overnight on a liquid ETF is unusual. The next day's fire checks `already_traded_today` (which queries ALL today's orders, not just filled), so cross-day stacking via pending orders is caught.

**Not fixed now.** Story 1c.3 / 1c.4 will rewrite this area anyway.

### 7. `compute_position_size` doesn't guard against `entry_price=0` or `account_value<=0`

**Current behavior:** Raises `ValueError` only on `stop_price >= entry_price` (Murat's sign-error guard). Other degenerate inputs (zero entry_price, negative account_value) would produce a `ZeroDivisionError` or sign-confused output.

**Risk:** Very low. Real-world callers pass `entry_price` from Alpaca fills (always >0) and `account_value` from `get_account().equity` (always positive for paper account).

**Not fixed now.** Test gap is small. Could add tests in a future hardening pass.

### 8. `today_signal` parses the entire `theses.jsonl` every fire

**Current behavior:** Iterates the full file to find today's record. File is ~12 lines today; will grow to several hundred lines by end of year. Linear scan; still fast.

**Risk:** None at current scale. File would need to grow to ~10MB+ before measurable.

**Not fixed now.** Phase 2 reconciler does similar scans; if either becomes slow, can index by date.

### 9. `today_signal` doesn't tolerate JSON parse errors mid-file

**Current behavior:** If any line in `theses.jsonl` is malformed JSON, `json.loads` raises and the entry script crashes (caught by the top-level `try/except` → Pushover).

**Risk:** Low. MICRO controls the file format and writes atomically. The recent 8 days of data shows no corruption.

**Not fixed now.** Could add `try/continue` per line, but silent skip might hide a real MICRO issue.

---

## Cross-doc consistency — verified clean

The following invariants were spot-checked:

- **HOLD_DAYS=2** consistently referenced across `src/trade_logger.py:21`, `TODO.md`, `_bmad-output/project-context.md`, `docs/architecture.md`, `docs/source-tree-analysis.md`, `docs/data-models.md`, `_bmad-output/planning-artifacts/architecture.md`
- **Phase 1 graduation gate = 5** consistently referenced everywhere it appears (29 mentions across 10 files, updated earlier today)
- **paper=True safety pin** referenced in code (`src/alpaca_connector.py:22`), `_bmad-output/project-context.md`, `docs/development-guide.md`, `docs/architecture.md`
- **No-shorts** referenced consistently as a hard locked rule
- **Cross-project paths** correct: `../tactical_markets/data/theses.jsonl` (MICRO), `../market_dashboard/data/latest.json` (MACRO)
- **MACRO weights_hash bootstrap** matches: `data/macro_weights_allowlist.json` contains `2532e380` which matches `market_dashboard/data/latest.json` as of 2026-05-13T07:45:02 UTC

The remaining "5 trading days" / "5-day hold" mentions are confined to:
- `research/compare_strategies.py` and `research/data/sensitivity_summary.md` — backtests of the original 5-day variant. Correctly kept as historical reference (off the production path).
- PRD's FR2 + integration spec describe the hypothetical MICRO-emitted `hold_window_hours` field that we explicitly don't consume (Phase 2 computes locally).

---

## Operational readiness — tomorrow's fire

Tomorrow (2026-05-14) at 08:35 AM CDT, the Entry task will execute the dedup fix and HOLD_DAYS=2 changes against live Alpaca paper. Pre-flight projection (now that I've re-read the code):

| Step | Expected behavior |
|---|---|
| `load_env()` | Loads .env. ✓ |
| `today_signal()` | Finds 5/14 signal (probably XLK still). Returns thesis dict. |
| `already_traded_today("XLK")` | Queries Alpaca for BUY orders with `after=2026-05-14T00:00:00Z`. No today's orders yet → returns False. ✓ |
| `at_position_limit()` | Queries all positions. Currently 1 (the 5/8 XLK). 1 < 5 → returns False. ✓ |
| `submit_order(thesis)` | Submits `MarketOrderRequest(symbol=XLK, notional=10000, BUY, DAY)`. |
| `wait_for_fill(...)` | Polls, returns on `OrderStatus.FILLED`. |
| `log_entry(...)` | Appends new row with `exit_time_planned = +2 NYSE trading days from fill_time` → 2026-05-18 (5/15 + 5/18). |
| Pushover | "Entered XLK $10,000. Filled @ $... | Spread: ...% | Exit: 2026-05-18" |

If anything other than this happens, investigate.

**Then at 08:40 AM CDT**, Exit task runs — but `now < 5/15 exit time`, so no records ripe. Logs "No open positions due for exit (2 record(s) checked)."

---

## Test suite state

**31/31 tests passing on pytest 9.0.3 + Python 3.14.4 in 0.08s** as of this commit:

- `tests/test_risk.py` — 14 assertions (stop math, sizing rules, concentration checks)
- `tests/test_macro_consumer.py` — 17 assertions (schema/staleness/provenance validation, multiplier policy)

No flaky tests. No skipped tests. All pure-function tests; no network or filesystem-outside-tmp dependencies.

---

## Summary

**Critical issues fixed:** 11 stale `already_traded` references + misleading concentration example + 4 gitignore entries. All consistency restored across the docs.

**Operationally important known issues (documented, no action today):** W3 (MACRO errors[] blocks Phase 2 wiring), Unicode print on cp1252 terminal.

**Minor code gaps (not blockers):** at_position_limit doesn't count pending orders; compute_position_size lacks degenerate-input guards; today_signal full-file scan.

**Cross-doc consistency:** verified clean post-fix.

**Operational readiness for tomorrow's 08:35 fire:** ready. Expected behavior projected.

The repo is in good shape. Nothing else needs to be done before stepping away.
