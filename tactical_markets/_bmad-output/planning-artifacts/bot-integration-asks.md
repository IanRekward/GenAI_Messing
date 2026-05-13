---
title: Bot Integration Asks — Phase 2.x → Phase 3 Tasks from tactical_markets_trading
audience: tactical_markets (MICRO) project owner
generated: 2026-05-13
status: draft — submitted for MICRO's post-freeze design pass (~2026-05-19)
source_of_truth: ../tactical_markets_trading/_bmad-output/planning-artifacts/micro-integration-roadmap.md
---

# Bot Integration Asks for MICRO

This is a **request list, not a directive.** MICRO owns its scope and roadmap. These are tasks the downstream trading bot (`tactical_markets_trading`) would value, presented so MICRO's post-freeze design pass has a clear picture of what its only consumer needs.

The bot's Phase 2 architecture is complete and ships with the **current** MICRO schema. None of these asks block the bot. They are quality-of-life and Phase 3 prerequisites.

For full context: see [tactical_markets_trading/_bmad-output/planning-artifacts/micro-integration-roadmap.md](../../../tactical_markets_trading/_bmad-output/planning-artifacts/micro-integration-roadmap.md).

---

## Context

**Who's asking:** The trading bot at `tactical_markets_trading/`, which consumes your `data/theses.jsonl` daily.

**Why now:** Your 14-day freeze ends ~2026-05-19. Your TODO.md branches on Rekwa's read of signal quality into paths (a)/(b)/(c). This doc lives outside that decision — these asks apply regardless of which branch MICRO takes.

**What the bot has been doing meanwhile:** As of 2026-05-13, the bot has executed 1 trade across 5 weekday firings because MICRO's daily signal has been "buy XLK" for 8 days running. The bot's response (commit `50e31d5`) is to allow same-symbol re-entry up to 5 concurrent positions, converting MICRO's persistent signal into rolling-position exposure. It works, but it stacks 5 XLK positions instead of producing diversification. **Item M1 below would resolve this elegantly.**

---

## Task list (priority-ordered)

### M1. Multi-thesis output [HIGH PRIORITY]

**The single highest-leverage thing MICRO could do for the bot.**

**What:** Emit N theses per scheduled run instead of one. Top-N rotation pairs by descending spread.

**Rationale:**
- The bot is designed for 5 overlapping positions in **distinct symbols**. Today's one-thesis-per-day pattern stalls that design: at steady state the bot holds 5 of one symbol.
- Multi-thesis (e.g., top-3 distinct pairs) would let the bot diversify across 3 different sectors per day, hitting the concurrency design as intended.
- Doesn't change MICRO's signal semantics — just exposes more of what MICRO already evaluates internally.

**Proposed schema (envelope):**

```json
{
  "signal": true,
  "as_of": "2026-05-13T11:30:06+00:00",
  "theses": [
    {"buy": "XLK", "sell": "XLE", "spread_pct": 8.94, "buy_momentum_pct": 5.78, "sell_momentum_pct": -3.16, "buy_price": 175.2, "buy_ma": 161.75, "thesis": "..."},
    {"buy": "XLF", "sell": "XLU", "spread_pct": 4.12, "buy_momentum_pct": 2.34, "sell_momentum_pct": -1.78, "buy_price": 38.5, "buy_ma": 37.2, "thesis": "..."},
    {"buy": "XLI", "sell": "XLP", "spread_pct": 3.08, "buy_momentum_pct": 1.85, "sell_momentum_pct": -1.23, "buy_price": 122.4, "buy_ma": 119.6, "thesis": "..."}
  ]
}
```

**Alternative:** write N JSON Lines records per run instead of one envelope. Either format works for the bot.

**MICRO-side cost:** unknown — depends on whether `src/sector_rotation.py` can extend its top-pair computation to top-N. Likely a small refactor.

**Bot-side cost:** ~30 minutes. `run_trading.py:today_signal()` becomes `today_signals()` returning a list; loop calls existing dedup + entry path per thesis.

**Coordination:** When MICRO ships this, bot project bumps `today_signal` consumer and the change lands in a single coordinated commit cycle.

---

### M2. Optional `confidence` field [MEDIUM PRIORITY]

**What:** Add a 0.0-1.0 `confidence` field per thesis. Lower the publish threshold (e.g., `spread_pct ≥ 0.5%`) and let confidence carry the noise filtering.

**Rationale:**
- The bot's Phase 2 sizing already supports multipliers (MACRO `size_multiplier` from architecture D5).
- A per-thesis `confidence` multiplier would let the bot scale position size by signal quality, not just regime quality.
- Useful even if MICRO stays with sector rotation only — confidence varies based on spread magnitude, trend confirmation, and the gap to the next-best pair.

**Proposed schema addition:**

```json
{"buy": "XLK", "sell": "XLE", "spread_pct": 8.94, "confidence": 0.78, "...": "..."}
```

**Suggested mapping in the bot:**
- `confidence ≥ 0.75` → full size
- `0.50 ≤ confidence < 0.75` → 0.75x
- `0.30 ≤ confidence < 0.50` → 0.5x
- `< 0.30` → skip

**MICRO-side cost:** small — define a confidence formula. The published ROADMAP suggested `base_win_rate + adjustment_for_signal_strength`. A reasonable starting point: `confidence = sigmoid((spread_pct - 1.5) / 2.0)` (returns ~0.5 at spread=1.5%, ~0.78 at spread=3.5%, ~0.92 at spread=5.5%).

**Bot-side cost:** small — add a multiplier function in `src/risk.py`; stacks with MACRO multiplier.

**Backward compatibility:** bot uses `.get("confidence", 1.0)` — absence treated as full confidence. No coordination needed.

---

### M3. Optional `signal_type` discriminator [MEDIUM PRIORITY — HIGH if MICRO adds new signal types]

**What:** Tag each thesis with its signal origin. Today everything is implicit "sector_rotation."

**Rationale:**
- If MICRO grows beyond sector rotation per its [ROADMAP_SIGNAL_GENERATION.md](../../ROADMAP_SIGNAL_GENERATION.md) (VIX slope, gap fills, credit-spread context), the bot needs to route different strategies to different stop rules.
- Sector rotation: 2-3% drawdown stops, 2-day hold.
- VIX slope: 4-5% stops, 3-5 day hold.
- Gap fill: 0.5% stops, intraday hold.

**Proposed schema:**

```json
{"buy": "SPY", "sell": "VXX", "signal_type": "vix_slope", "...": "..."}
{"buy": "QQQ", "sell": null, "signal_type": "gap_fill", "...": "..."}
```

**Trigger condition:** Only needed if MICRO ships path (a) "expand to VIX slope signal type" post-freeze. If MICRO stays with sector rotation (path b), this can wait.

**MICRO-side cost:** trivial when adding a new signal type anyway.

**Bot-side cost:** small — `compute_stop_price()` already accepts a `stop_pct` parameter. Router in `run_trading.py` maps `signal_type` to default stop_pct.

**Backward compatibility:** absence → `"sector_rotation"`.

---

### M4. NOT desired — please don't add these [GUARDRAIL]

The bot **explicitly does not want** MICRO to emit:

- `stop_price` per thesis
- `target_price` per thesis
- `hold_window_hours` per thesis
- `qty` or `position_size`
- Auto-execute flag

**Rationale:** these are risk-management concerns (bot territory) and require account state (equity, current positions) that MICRO doesn't have. The bot computes them locally so it can audit *which rule was used per trade* (architecture AR4: full audit trail). MICRO-supplied hints would confuse provenance.

The original [ROADMAP_SIGNAL_GENERATION.md](../../ROADMAP_SIGNAL_GENERATION.md) described these fields — please consider them retired. The bot's Phase 2 architecture explicitly rejected them after party-mode review (Winston: "stops are a risk-management concern, not a signal concern; coupling stop calculation to MICRO would be the wrong abstraction even if MICRO could provide them").

---

### M5. Phase 3 (live capital) prerequisites — defer until then [LOW PRIORITY, HIGH at Phase 3 entry]

When the trading bot graduates to live capital (gated on 50+ paper trades + ROE doc), the bot will need:

- **`schema_version` field** (MACRO already has this — same pattern)
- **`code_sha` field** (commit SHA of the MICRO build that produced this signal — same pattern as MACRO)
- **`config_hash` field** (hash of MICRO's config files at run time)
- **Documented freshness SLA** (e.g., "MICRO writes by 7:00 AM ET on every NYSE trading day; absence after 8:00 AM = explicit signal")

None of these are needed for Phase 2 paper trading. Listed here so MICRO has lead time before they become blocking.

---

## Coordination protocol

### When MICRO adds new optional fields

The bot uses `.get(key, default)` everywhere. **No coordination needed.** Ship freely.

### When MICRO changes existing field semantics

This is where coordination matters. Example: if `spread_pct` semantics change from "% spread of 5-day momentum" to "z-score of spread," the bot's interpretation breaks silently with no error.

**Proposed protocol:** any breaking change to existing field semantics bumps `schema_version` (Phase 3+ requirement, item M5). The bot's allow-list check then fails on the new version until manually reviewed and approved. Same provenance-gate pattern the bot uses with MACRO.

### When MICRO changes the publish gate

Today `spread_pct >= 1.5` publishes. If this lowers (more signals) or raises (fewer signals), the bot's trading volume changes. **Not a breaking change** — but worth a one-line heads-up in the commit message so we don't attribute a cadence shift to a bot bug.

### Cross-project change discipline

Both projects use the same `_genai_tmp/` shared repo. Commits touching both should reference each other's commit hashes.

---

## Mapping to MICRO's post-freeze design fork

Per your [TODO.md](../../TODO.md), the post-freeze decision branches on Rekwa's read of signal quality:

| If MICRO chooses | The bot's priority asks |
|---|---|
| **(a)** "I'd act on these" → expand to VIX slope | **M1 (multi-thesis)** + **M3 (signal_type)** — both essential to handle the expanded signal universe cleanly. |
| **(b)** "Feels like noise" → fix sector rotation | **M1 (multi-thesis)** stays highest-value. M2 (confidence) would help while fixing. |
| **(c)** "Never read at 6:30 AM" → fix delivery | No bot impact. |

**M1 (multi-thesis output) is the single most valuable ask regardless of which branch MICRO chooses.**

---

## Summary

| # | Ask | Priority | MICRO cost | Bot cost | When |
|---|---|---|---|---|---|
| M1 | Multi-thesis output | HIGH | medium | small (~30min) | post-freeze (~5/19+) |
| M2 | Optional `confidence` field | MEDIUM | small | small | Phase 2.x, any time |
| M3 | Optional `signal_type` discriminator | MEDIUM / HIGH | small | small | when MICRO adds new types |
| M4 | (Guardrail: don't add stop/target/hold/qty) | — | — | — | always |
| M5 | Phase 3 prerequisites (schema_version, code_sha, config_hash, freshness SLA) | LOW today, HIGH at Phase 3 | small each | small each | before live capital |

**Bot status:** Phase 2 architecture is shipping with current MICRO schema. The bot's `src/risk.py` and `src/macro_consumer.py` pure-function layer is already committed and tested (31/31 passing). Post-Phase-1-graduation (~5/21), bot wires these into the entry/exit flow. None of M1-M5 block that work; they enhance it.
