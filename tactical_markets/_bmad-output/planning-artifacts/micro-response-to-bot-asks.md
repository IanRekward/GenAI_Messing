---
title: MICRO Response — Bot Integration Asks (M1–M5)
audience: tactical_markets_trading (bot project)
generated: 2026-05-13
status: draft — confirmed at post-freeze design pass (~2026-05-19)
responds_to: bot-integration-asks.md
---

# MICRO Response to Bot Integration Asks

This document closes the loop on [bot-integration-asks.md](bot-integration-asks.md). Decisions below are provisional — subject to Ian's post-freeze read — but the replay evidence is solid enough to draft against.

---

## Replay findings (M1 evidence)

A historical replay was run on 2026-05-13 against the last 10 trading days using the existing
sector rotation logic extended to top-N. Full script: [replay_topn.py](replay_topn.py).

**Result: M1 would produce real diversification in 8 of 10 days.**

Avg distinct buy-side tickers per day (target=3): **2.70**.
Days with full 3-way diversification: **8/10**.
Days with partial (gate filtered): 2 (2026-05-01: 1 pair; 2026-05-04: 2 pairs — spread gate
working as designed; bot would open fewer positions, correct behavior).

Recent buy-side variety observed: XLE, XLK, IWM, QQQ, XLRE, SPY — six distinct tickers.

**Caveat flagged:** XLK + QQQ + SPY are correlated (all tech-heavy). The bot would hold 3
*symbols* but not 3 *uncorrelated bets*. Better than 5× the same ticker, but real risk reduction
requires a sector-class constraint. See open design questions below.

---

## Decisions by item

### M1 — Multi-thesis output [ACCEPTED, post-freeze]

**Decision:** Accept. Confirmed leverage. Implementation held until freeze ends (~2026-05-19).

**Proposed approach:** emit all pairs above the spread gate per run, not a fixed top-N.
Rationale: on quiet days only 1 pair passes — forcing N=3 would either pad with weak signals
or require special-casing. "All above gate" is simpler and self-regulating.

**Open design question before implementation:**
- Ticker-distinct vs sector-class-distinct? Two options:
  - **(A) Distinct ticker only** (current replay logic): XLK + QQQ both allowed. Simple,
    matches current data. Bot gets 3 positions but they may correlate.
  - **(B) Distinct sector class** (e.g., "tech" = XLK + QQQ + SPY all map to same class):
    stricter, requires a sector-class mapping in universe.yaml, guarantees uncorrelated bets.
  - **Recommendation:** start with (A) now; add (B) as a follow-on if bot telemetry shows
    correlated drawdowns. Don't over-engineer before the first live multi-thesis week.

**Schema:** N JSONL records per run (not an envelope). Keeps backward compat simple — the bot
reads today's lines as a list; old single-line days remain valid.

```jsonl
{"signal": true, "buy": "XLK", "sell": "XLE", "spread_pct": 10.3, ...}
{"signal": true, "buy": "IWM", "sell": "XLF", "spread_pct": 5.56, ...}
{"signal": true, "buy": "QQQ", "sell": "XLU", "spread_pct": 5.10, ...}
```

Bot consumer change: `today_signal()` → `today_signals()` returning a list.

---

### M2 — Optional `confidence` field [DEFERRED — decide post-freeze]

**Decision:** Defer. The post-freeze failure mode determines priority:
- Path (a) "I'd act on these" — M2 becomes medium-priority (size scaling would add value).
- Path (b) "Feels like noise" — M2 is low-priority (fix the signal first, then layer confidence).
- Path (c) "Wrong delivery" — M2 not relevant.

The sigmoid formula suggested in the asks doc is reasonable as a starting point when we get here.

---

### M3 — Optional `signal_type` discriminator [CONDITIONAL — triggers if path (a)]

**Decision:** Conditional. Only implement if post-freeze direction is path (a) "expand to VIX
slope." At that point, M3 is mandatory (different strategies need different stop rules).
If MICRO stays sector-rotation-only (path b or c), M3 can wait indefinitely.

When implemented, absence defaults to `"sector_rotation"` per the asks doc.

---

### M4 — Guardrail: don't add stop/target/hold/qty [ACKNOWLEDGED]

**Decision:** Confirmed. MICRO will not emit stop_price, target_price, hold_window_hours, qty,
or position_size. These are bot territory. The ROADMAP fields are retired.

---

### M5 — Phase 3 prerequisites [NOTED, not yet actioned]

**Decision:** Logged for lead time. Will action before live capital. `schema_version`,
`code_sha`, `config_hash`, and freshness SLA are all small adds when the time comes.
Currently tracking in this document — no separate ticket needed until bot approaches Phase 3.

---

## Open design questions for the 2026-05-19 design pass

| # | Question | Options | Recommendation |
|---|---|---|---|
| Q1 | Multi-thesis schema: N JSONL lines vs envelope? | JSONL lines (simpler, backward compat) vs `{"theses": [...]}` | JSONL lines |
| Q2 | Distinct ticker vs distinct sector class? | (A) ticker only; (B) add sector-class mapping | Start with (A), revisit if bot shows correlated drawdowns |
| Q3 | Fixed top-N or all-above-gate? | Fixed N=3 or emit all passing pairs | All-above-gate |
| Q4 | M2 priority post-freeze? | Determined by failure mode (a/b/c) | Decide on 5/19 |
| Q5 | M3 trigger? | Path (a) only | Confirmed conditional |

---

## Coordination notes

- MICRO will send a one-line heads-up in the commit message if the publish gate threshold
  changes (lower or higher), so the bot doesn't attribute volume shifts to a bug.
- Bot uses `.get(key, default)` everywhere for optional fields — MICRO can ship M2/M3 fields
  without coordination.
- Breaking changes to existing field semantics (e.g. redefining `spread_pct`) will bump
  `schema_version` when M5 is implemented. Until then, treat existing fields as stable.
- Both projects share `_genai_tmp/` repo — cross-project commits should reference each other's
  hash.
