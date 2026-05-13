---
title: Bot Integration Asks — Coordination Tasks from tactical_markets_trading
audience: market_dashboard (MACRO) project owner
generated: 2026-05-13
status: draft
related_doc: integration-brief-for-tactical-bot.md (your existing brief)
---

# Bot Integration Asks for MACRO

This is a **short, coordination-focused** doc. MACRO has already done most of the heavy lift on this integration via its [integration-brief-for-tactical-bot.md](./integration-brief-for-tactical-bot.md) (the JSON sidecar contract). The bot is consuming MACRO's `data/latest.json` as designed.

These are the remaining coordination items that affect the trading bot, in priority order.

---

## Context

**Who's asking:** The trading bot at `tactical_markets_trading/`, currently in Phase 1 paper-trading validation (graduation projected ~2026-05-21). Phase 2 wires in MACRO consumption per the bot's architecture decisions D5/D6.

**Where the bot uses MACRO:** 
- `src/macro_consumer.py` reads `../market_dashboard/data/latest.json` daily before each entry decision.
- Validates: `schema_version == 1`, `errors[]` empty, `composite ∈ [0,100]`, `run_timestamp` ≤ 4h old, `weights_hash` in bot's allow-list.
- On red `composite_band` → blocks new entries. On orange + high regime → 0.5x size. Otherwise full size.

**Current bot allow-list state:** `data/macro_weights_allowlist.json` contains hash `2532e380` (read from MACRO's `latest.json` at 2026-05-13T07:45:02 UTC). When MACRO changes this hash, the bot blocks trading until the new hash is manually added.

---

## Task list

### W1. Pre-coordinate `weights_hash` changes [HIGH PRIORITY — context-sensitive]

**What:** When MACRO ships a recalibration that bumps `weights_hash`, send the bot project a heads-up so the allow-list can be updated before the next bot run.

**Why:**
- The bot's allow-list is the explicit human-review gate per architecture decision AR12 ("forces human review when MACRO recalibrates weights").
- Without pre-coordination, the bot will silently block new entries on the day MACRO ships a recalibration, until someone notices and adds the new hash.
- With pre-coordination, the bot project can review the recalibration's bucket-weight deltas, confirm semantics haven't drifted, and add the new hash with reviewer + date + summary recorded in the allow-list file.

**Specific upcoming event:** Your [TODO.md](../../TODO.md#L141) has a "**Regime-weights review checkpoint** due 2026-05-30" — running `python -m src.recalibrate --regime` and possibly flipping `regime_weights.enabled: true` in `config/weights.yaml`. If that ships, it will produce a new `weights_hash` and the bot will block.

**Proposed protocol:** Before pushing any commit that changes `config/weights.yaml`:
1. Run `python -m src.recalibrate --regime` (or whatever) to see the new hash
2. Open a coordination note in the shared repo: a one-line entry in `tactical_markets_trading/data/macro_weights_allowlist.json` adding the new hash with reviewer name + date + summary of weight changes
3. Push both commits (yours + bot's allow-list update) together or close in sequence

The bot's allow-list file already has structured `_comment` and `_bootstrap_*` fields ready for this convention.

**MACRO-side cost:** trivial — one additional file edit per recalibration commit.

---

### W2. Populate `code_sha` field [MEDIUM PRIORITY]

**What:** Your `data/latest.json` currently emits `"code_sha": ""` (empty string). Populate it with the commit SHA of the MACRO build that produced this run.

**Why:** Phase 3 live-capital audit trail per the bot's architecture AR4. The bot records per-trade `macro_snapshot` including `weights_hash` and `code_sha`. When investigating a trade's reasoning months later, the code SHA tells us exactly which MACRO build produced the regime call.

**Proposed implementation:** In `run_dashboard.py` (or wherever `latest.json` gets emitted), populate `code_sha` via:

```python
import subprocess
try:
    code_sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, check=True
    ).stdout.strip()
except Exception:
    code_sha = "unknown"
```

In the cross-sibling repo at `_genai_tmp/`, this returns the latest commit SHA. Good enough for audit.

**Bot-side use:** Phase 2 records this in `trades.jsonl`. Phase 3 may add a known-good-builds allow-list (parallel to weights_hash) for very paranoid audit; today the bot just records it.

**Backward compatibility:** bot uses `.get("code_sha", "unknown")`. No coordination needed when MACRO adds it.

---

### W3. Document the `errors[]` policy for downstream consumers [LOW PRIORITY]

**What:** Your `latest.json` `errors[]` field sometimes contains STALE warnings for individual indicators (e.g., `"STALE: stlfsi — last observation 12d ago"`). Document whether the bot should block on these or treat them as benign.

**Current bot behavior:** The bot blocks on **any** non-empty `errors[]` per architecture D6 (strict interpretation). This means a stale `stlfsi` indicator (which MACRO's integration brief explicitly calls benign) blocks new entries.

**Concrete consequence today:** MACRO's `latest.json` at 2026-05-13 contains:

```json
"errors": [
  "STALE: stlfsi — last observation 12d ago (expected ≤10d for weekly series)",
  "STALE: jobless_claims — last observation 11d ago (expected ≤10d for weekly series)"
]
```

When the bot wires up MACRO consumption post-Phase-1-graduation, it will block on this state. We need to either:
- (a) Distinguish blocking vs. non-blocking errors at MACRO's source (e.g., `errors[]` for hard errors, `warnings[]` for STALE-style soft conditions).
- (b) Document a per-error-prefix policy the bot can apply (e.g., `STALE:` is non-blocking, anything else is blocking).
- (c) Document that bot is too strict — refine in bot side to ignore `STALE:` lines.

**Recommendation:** option (a) — split `errors[]` (real failures) from `warnings[]` (informational). Cleanest contract going forward. Backward compat: bot uses `.get("warnings", [])` for the new field.

**MACRO-side cost:** small — categorize the existing error emissions.

**Trigger:** before bot's Phase 2 MACRO consumption ships (post-2026-05-21). If not addressed, bot will need a workaround (option c).

---

### W4. Acknowledgments — already shipped, no action needed

These are NOT asks; they're acknowledgments of what MACRO has already shipped that the bot relies on:

- ✅ `data/latest.json` sidecar (Brief 24, commit `2046161`) — bot consumes it
- ✅ `schema_version` field — bot validates it
- ✅ `weights_hash` field — bot allow-list checks it
- ✅ `run_timestamp` field — bot staleness checks it
- ✅ `composite`, `composite_band`, `regime` fields — bot reads them
- ✅ Stable band thresholds (30/50/70 → green/yellow/orange/red) — bot uses default
- ✅ Stable bucket count (11) — bot doesn't enumerate buckets
- ✅ `regime` enum (`low`/`mid`/`high`) — bot uses for sizing policy
- ✅ Integration brief at `_bmad-output/planning-artifacts/integration-brief-for-tactical-bot.md` — bot's source of truth for the contract

---

## Summary

| # | Ask | Priority | MACRO cost | Trigger |
|---|---|---|---|---|
| W1 | Pre-coordinate `weights_hash` changes | HIGH | trivial | Every recalibration; first event ~2026-05-30 |
| W2 | Populate `code_sha` field | MEDIUM | small | Any time; useful from Phase 2 wiring onward |
| W3 | Distinguish `errors[]` (blocking) from `warnings[]` (non-blocking) | MEDIUM | small | Before bot's Phase 2 MACRO consumption ships (~2026-05-25) |

**Bot status:** `src/macro_consumer.py` is committed and tested (commit `7f8fbb2`) but **not yet wired** into the entry flow. Wiring lands as Story 1b.5/1b.6 after Phase 1 graduation (~2026-05-21). At that point, W3 (errors vs warnings) becomes blocking for the bot.

---

## Coordination protocol summary

| MACRO change | Action |
|---|---|
| Bug fix or refactor (no `weights.yaml` or schema change) | Just push. No coordination needed. |
| Add an optional field to `latest.json` | Just push. Bot uses `.get(key, default)`. |
| Change `weights_hash` (recalibration) | Pre-coordinate per W1 — update bot's allow-list in a paired commit. |
| Change `schema_version` (breaking schema change) | Hard-coordinate — bot blocks until manually approved. Discuss before. |
| Change `composite_band` thresholds (30/50/70) | Discuss before — bot policy depends on these. |
| Add `warnings[]` field (per W3) | Just push. Bot uses `.get("warnings", [])`. |
| Remove `STALE:` entries from `errors[]` (move to `warnings[]`) | This IS the W3 change — coordinate. |
