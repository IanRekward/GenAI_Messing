---
title: MICRO ↔ Bot Integration Roadmap (Phase 2.x → Phase 3)
audience: tactical_markets (MICRO) project owner; trading bot architects
generated: 2026-05-13
status: draft
inputDocuments:
  - "_bmad-output/planning-artifacts/architecture.md (Phase 2 forward-looking)"
  - "_bmad-output/planning-artifacts/epics.md (Phase 2 stories)"
  - "../tactical_markets/docs/data-models.md (MICRO theses.jsonl schema)"
  - "../tactical_markets/docs/integration-architecture.md (cross-project contracts)"
  - "../tactical_markets/TODO.md (MICRO post-freeze design fork)"
---

# MICRO ↔ Bot Integration Roadmap

What `tactical_markets_trading` (the bot) would like `tactical_markets` (MICRO) to emit in Phase 2.x → Phase 3, what it explicitly does NOT want, and the coordination protocol when MICRO evolves.

This is a **planning doc, not a request**. MICRO owns its scope. This articulates the downstream consumer perspective so MICRO's post-freeze design (decision fork around 2026-05-19) has a clear picture of what its only consumer needs.

---

## 1. Current state (2026-05-13)

### What MICRO emits

One JSON Lines record per scheduled run (~6:30 AM ET weekdays). On a `signal: true` day:

```json
{
  "signal": true,
  "buy": "XLK",
  "sell": "XLE",
  "buy_momentum_pct": 5.78,
  "sell_momentum_pct": -3.16,
  "spread_pct": 8.94,
  "buy_price": 175.2,
  "buy_ma": 161.75,
  "thesis": "XLK (Technology) +5.8% vs XLE (Energy) -3.2% over 5 days. Spread: 8.9%. Signal: rotate 5-10% from XLE -> XLK. Hold 5-7 days. XLK above 20d MA ($175.20 vs $161.75), trend confirmed.",
  "as_of": "2026-05-13T11:30:06.186935+00:00"
}
```

No-signal day: `{"signal": false, ..., "as_of": ...}`. Error day: `{"signal": false, "error": "<reason>", ...}`.

### What the bot consumes today

Of the 9 fields:

| Field | Used | How |
|---|---|---|
| `signal` | Yes | Filter to `true` records |
| `as_of` | Yes | Filter to today's UTC date |
| `buy` | Yes | Submit as long-leg BUY ticker |
| `sell` | Yes (preserved only) | Recorded as `sell_leg` for benchmark capture at exit. **Not traded** — the bot is long-only per durable user preference (no shorts, ever). |
| `spread_pct` | Yes (display only) | Pushover message body |
| `buy_momentum_pct` | No | Available for inspection |
| `sell_momentum_pct` | No | Available for inspection |
| `buy_price` | No | Bot uses Alpaca fill price |
| `buy_ma` | No | Available for inspection |
| `thesis` | No | Human-readable Pushover prose, not parsed |

### Observed dynamic: dominant-signal stalling

From 2026-05-06 to 2026-05-13, MICRO has emitted **identical buy:XLK theses 8 days in a row** (with spread_pct varying from 5.4% to 13.8%). XLK has been the dominant momentum leader for the entire window. This is empirically correct — MICRO's signal is doing what it was designed to do, identifying the persistent winner — but it produces low trading-bot cadence because each day's signal is for the same symbol the bot already holds.

The bot's response (commit `50e31d5`) is to allow same-symbol re-entry up to 5 concurrent positions, aligning with the locked "5 overlapping positions" design. This converts MICRO's persistent signal into rolling-position exposure to the same symbol. It works but it's a workaround for a signal-emission convention, not a signal-quality issue.

---

## 2. Phase 2.x: what would help the bot

In priority order. Each is independent — MICRO can pick zero, one, or several. None block the bot.

### 2.1. Multi-thesis output (highest value)

**Current:** one signal per scheduled run.
**Proposed:** N signals per scheduled run, ordered by descending spread, top-N rotation pairs.

**Why this matters most:**

With one-per-day, the bot at steady state holds 5 rolling positions of the **same** symbol. That's 5x notional exposure to whatever the current top sector is — fine for signal-validation, but a contradiction of the diversification intent baked into the "5 overlapping positions" design.

With multi-thesis (e.g., top-3 distinct pairs per day), the bot enters 3 distinct symbols per day. At hold=2 (Phase 2 setting), steady state is ~3 open positions across 3 different sectors at any time. The "rolling 5-position" design now produces **diversified** exposure as originally intended.

**Concrete signal cadence comparison:**

| MICRO output | Bot daily entries | Steady-state open positions |
|---|---|---|
| 1 thesis/day (today) | 1 (same symbol stacks) | 5 of one symbol |
| 3 distinct theses/day | 3 (3 different symbols, until cap binds) | 3-5 of distinct symbols |

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

**Alternative schema (separate records):** MICRO could write N JSON Lines records per scheduled run instead of one envelope. Either format works for the bot; the envelope is slightly cleaner because the `as_of` is naturally shared.

**Bot-side cost:** moderate. `run_trading.py:today_signal()` becomes `today_signals()` returning a list. The dedup logic (`already_traded_today` + `at_position_limit`) already handles per-symbol decisions, so processing multiple theses is just a loop. Estimate: ~30-min change after MICRO ships.

**MICRO-side cost:** unknown. Depends on how `tactical_markets/src/sector_rotation.py` computes the top pair today and whether it can extend to top-N.

### 2.2. Optional `confidence` field per thesis

**Current:** binary publish gate (spread ≥ 1.5%).
**Proposed:** publish all spreads ≥ 0.5% (lower bar) with a `confidence` score 0.0-1.0.

**Why:** the bot's Phase 2 sizing rule already supports a multiplier (the MACRO `size_multiplier` from architecture D5). Adding a per-thesis confidence multiplier would let the bot scale position size by signal quality, not just regime quality.

**Proposed schema addition:**

```json
{
  "buy": "XLK",
  "sell": "XLE",
  "spread_pct": 8.94,
  "confidence": 0.78,
  "...": "..."
}
```

**Mapping in the bot (Phase 2.x):**

- `confidence ≥ 0.75` → full size
- `0.50 ≤ confidence < 0.75` → 0.75x size
- `0.30 ≤ confidence < 0.50` → 0.5x size
- `confidence < 0.30` → skip (would have been filtered today)

**Bot-side cost:** small. Add a `confidence_multiplier()` function in `src/risk.py`. Stack with MACRO multiplier.

**Backward compatibility:** bot uses `.get("confidence", 1.0)` — absence treated as full confidence. No coordination needed when MICRO adds it.

### 2.3. Optional `signal_type` discriminator

**Current:** every signal is implicitly sector rotation.
**Proposed:** when MICRO grows beyond sector rotation (per its [ROADMAP](../../tactical_markets/ROADMAP_SIGNAL_GENERATION.md): VIX slope, gap fills, credit-spread context), tag each thesis with its origin.

```json
{"buy": "SPY", "sell": "VXX", "signal_type": "vix_slope", "...": "..."}
{"buy": "QQQ", "sell": null, "signal_type": "gap_fill", "...": "..."}
```

**Why:** the bot's Phase 2 stop rule is a fixed 2.5% for sector-rotation 2-day holds. Different signal types want different stops:
- Sector rotation (multi-day): 2-3% drawdown stops
- VIX slope (3-5d mean reversion): wider stops, maybe 4%
- Gap fill (intraday): tight stops, maybe 0.5%

**Bot-side cost:** small. `compute_stop_price` already accepts a `stop_pct` parameter. A small router in `run_trading.py` selects pct based on `signal_type`.

**Backward compatibility:** absence treated as `"sector_rotation"`. Bot infers historical default for old records.

### 2.4. NOT desired (do not add)

The bot **does not want** MICRO to emit any of the following:

| Field | Why not |
|---|---|
| `stop_price` per thesis | Stops are a risk-management concern (bot territory), not a signal concern (MICRO territory). Bot computes locally from entry fill + per-strategy rule. (Architecture D1, D2; Winston party-mode review.) |
| `target_price` per thesis | Same as above — exit logic is bot-owned. |
| `hold_window_hours` per thesis | Same. Bot's HOLD_DAYS is a per-deployment constant. Future: per-`signal_type` defaults are bot-side mapping. |
| `qty` or `position_size` | Position sizing requires account state (equity, current positions) that MICRO doesn't have. Bot territory. |
| Auto-execute flag | Manual approval / dry-run gates belong in the bot's workflow layer, not the signal. Phase 3 will discuss. |

If MICRO is tempted to emit these (because the original ROADMAP_SIGNAL_GENERATION.md described them), please don't. Even as "hints." The bot needs to compute these locally so it can audit *which rule was used per trade* (architecture AR4). MICRO-supplied hints would confuse provenance.

---

## 3. Phase 3 (live capital): what becomes important

When the bot graduates to live capital (gated on 50+ paper trades + ROE doc, no earlier), additional integration concerns appear:

### 3.1. Schema versioning

Today MICRO has no `schema_version` field. MACRO does (per its integration brief). When live, the bot needs to refuse to act on an unrecognized schema. Suggest:

```json
{"schema_version": 1, "as_of": "...", "theses": [...]}
```

Bot will allow-list known schema versions, same pattern as MACRO weights_hash.

### 3.2. Provenance / signal lineage

When a trade goes wrong in live, regulators (and Rekwa) want to audit *which version of the signal generator produced this thesis*. Suggest:

```json
{
  "schema_version": 1,
  "code_sha": "abc1234",
  "config_hash": "def5678",
  "as_of": "...",
  "theses": [...]
}
```

Bot records `code_sha` and `config_hash` in `trades.jsonl` per architecture AR4 audit trail.

### 3.3. Freshness contract

MACRO has a 4-hour staleness threshold in the bot (architecture D6). MICRO doesn't yet. Today the bot just checks "is the file mtime from today." For live, suggest a documented freshness SLA from MICRO (e.g., "MICRO writes by 7:00 AM ET on every NYSE trading day; bot may treat absence after 8:00 AM as an explicit ABORT").

### 3.4. Error semantics

MICRO already emits `{"signal": false, "error": "..."}` on yfinance failures. Good. Suggest documenting the error vocabulary so the bot can map specific errors to specific Pushover messages (e.g., `"yfinance down"` → "MICRO yfinance outage, expect signal delay" vs. `"calendar mismatch"` → "MICRO calendar bug, flag for review").

---

## 4. Coordination protocol

### When MICRO adds fields

The bot uses `.get(key, default)` everywhere, so additive changes are safe. MICRO can ship new optional fields without coordinating.

### When MICRO changes existing field semantics

This is where coordination matters. Example: if `spread_pct` semantics change (e.g., from "% spread of 5-day momentum" to "z-score of 5-day momentum spread"), the bot's interpretation breaks silently.

**Proposed protocol:** any breaking change to existing field semantics bumps `schema_version` (Phase 3+ requirement, listed in §3.1). The bot's allow-list check then fails on the new version until manually reviewed and approved. Same provenance gate pattern as MACRO `weights_hash`.

### When MICRO changes the publish gate

Today `spread_pct >= 1.5` publishes. If this lowers (more signals) or raises (fewer signals), the bot's trading volume changes meaningfully. **Not a breaking change** — but worth a heads-up so we don't attribute a cadence shift to a bot bug.

### Cross-project change discipline

Both projects use the same `_genai_tmp/` shared repo. Commits touching both projects should reference each other's commit hashes in the message. Example: if MICRO ships multi-thesis output and bot ships consumption, both commits should cross-reference.

---

## 5. MICRO's post-freeze design fork (per its [TODO.md](../../tactical_markets/TODO.md))

MICRO's freeze ends ~2026-05-19. The post-freeze decision branches per its three documented failure modes:

| MICRO observes | MICRO's planned response | Bot implication |
|---|---|---|
| (a) "I'd act on these" | Expand to VIX slope signal type | Bot wants §2.3 `signal_type` discriminator + per-type stop rules. Coordination point. |
| (b) "Feels like noise" | Fix sector rotation before adding anything | Bot is fine with current schema. No coordination needed during fix. Maybe `confidence` (§2.2) helps. |
| (c) "Never read at 6:30 AM" | Delivery is wrong, not signal | Affects MICRO's Pushover, not bot integration. Bot unaffected. |

**This roadmap is intentionally agnostic to the branch.** Sections 2.1 (multi-thesis), 2.2 (confidence), and 2.3 (signal_type) are useful regardless of which path MICRO takes.

The bot's single highest-value ask is **§2.1 multi-thesis output.** If MICRO does one thing post-freeze that helps the bot most, it's that. (Combined with the diversification benefit, it would let Phase 1 graduate in fewer days even than the current 5/21 projection.)

---

## 6. Summary of asks (priority-ordered)

| # | Ask | Priority | MICRO cost | Bot cost | When |
|---|---|---|---|---|---|
| 1 | Multi-thesis output (envelope or N records) | HIGH | medium | small (~30min) | post-freeze (~5/19+) |
| 2 | Optional `confidence` field | MEDIUM | small | small | Phase 2.x |
| 3 | Optional `signal_type` discriminator | MEDIUM (becomes high if MICRO adds VIX slope) | small | small | when MICRO grows signal types |
| 4 | `schema_version` field | LOW today, REQUIRED at Phase 3 | small | small | Phase 3 (live capital) |
| 5 | `code_sha` / `config_hash` provenance | LOW today, REQUIRED at Phase 3 | small | small | Phase 3 |
| 6 | Documented freshness SLA | LOW today, REQUIRED at Phase 3 | small | small | Phase 3 |

None of #1-6 block the bot. The bot's Phase 2 architecture is complete and ships with the current MICRO schema. These are quality-of-life and Phase 3 prerequisites.

---

## 7. What this document is NOT

- **Not a roadmap for MICRO's strategy logic.** That's MICRO's territory. The bot has no opinion on VIX slope vs. gap fills vs. sector rotation. Whatever MICRO emits, the bot consumes.
- **Not a promise.** MICRO's freeze still has a week left. MICRO's post-freeze decision branches on Rekwa's read of the signal quality, which the bot can't predict.
- **Not a hard constraint.** MICRO can ignore everything here. The bot survives.
- **Not Phase 4+ scope.** The PRD's end-state vision (11+ strategy ensemble, Tier 2 single stocks, Tier 3 crypto) involves changes both upstream and downstream. This doc covers the next 2-3 phases of MICRO integration only.

---

**Recommended next step:** when MICRO's freeze ends ~5/19, share this doc with the MICRO project as input to its post-freeze design pass. If MICRO chooses (a) "expand to new signal types," items §2.1 + §2.3 are the bot's specific asks. If MICRO chooses (b) "fix sector rotation," item §2.1 is still highly valuable as an orthogonal improvement.
