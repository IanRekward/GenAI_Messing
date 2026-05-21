# tactical_markets — TODO

Companion to the strategic [market_dashboard](../market_dashboard/) early-warning system. Focuses on shorter-term tactical signals (overnight repricing, sector rotation, premarket positioning).

## Status

**Freeze ended 2026-05-20. Post-freeze enhancements shipped.**

- **M1 (multi-thesis output):** `sector_rotation.py` returns `list[dict]`; greedy top-vs-bottom pairing; `run_tactical.py` emits one JSONL line per thesis pair. Bot now reads all today's signals via `today_signals()`.
- **M2 (confidence field):** `sigmoid((spread_pct - 1.5) / 2.0)` per thesis; `confidence` field in every JSONL record.
- **M3 (signal_type field):** `"sector_rotation"` tag per thesis for future routing.
- **Scheduler fixed:** triggers shifted from 6:30 AM / 7:00 AM CT to 5:30 AM / 7:00 AM CT (machine is on CDT = UTC-5; was firing at 7:30 ET instead of 6:30 ET).
- **Watchdog task:** `watch_tactical.py` fires at 7:00 AM CT; Pushover-alerts "Tactical Markets MISSED" if no thesis recorded for today.
- **Freeze retired:** replaced with production-path vs research-path policy (see bot TODO.md). No action needed until 2026-06-10 review.

**Next action: 2026-06-10 review.** Let M1 multi-thesis data accumulate ~3 weeks across diverse sector pairs, then decide whether to add variant-B (21-day hold) or re-param. See bot-integration-asks-variant-b-2026-05-20.md (HELD).

## Source documents

- [ROADMAP_SIGNAL_GENERATION.md](ROADMAP_SIGNAL_GENERATION.md) — full implementation brief: overnight repricing + sector rotation dashboard, 6:30 AM premarket signals
- [RESEARCH_SUMMARY.md](RESEARCH_SUMMARY.md) — empirical findings (2000–2026) that grounded the signal design
- [README.md](README.md) — project framing and design principles
- [_bmad-output/planning-artifacts/bot-integration-asks.md](_bmad-output/planning-artifacts/bot-integration-asks.md) — priority-ordered tasks (M1-M5) the downstream `tactical_markets_trading` bot would like MICRO to consider in the post-freeze design pass. **Read before deciding path (a)/(b)/(c)** — M1 (multi-thesis output) is the highest-leverage ask regardless of which branch you choose.
- [_bmad-output/planning-artifacts/bot-integration-asks-variant-b-2026-05-20.md](_bmad-output/planning-artifacts/bot-integration-asks-variant-b-2026-05-20.md) — **HELD (2026-05-20):** variant-B signal ask is on ice. Rekwa picked Option D first: let M1 multi-thesis data accumulate ~3 weeks, review 2026-06-10, then decide whether variant-B (Option C) or re-param (Option B) is needed. **No MICRO action requested until 2026-06-10.**

## Locked week-1 design (2026-05-05 design session, Opus 4.7)

Design pass run with [DESIGNER_PROMPT.md](DESIGNER_PROMPT.md). Outcome: the [ROADMAP_SIGNAL_GENERATION.md](ROADMAP_SIGNAL_GENERATION.md) 4-week parallel rollout is **revised**. Week 1 ships a single signal end-to-end via Pushover only; HTML, confidence scoring, additional signals, and the backtest framework are deferred until two weeks of lived exposure surface what's actually wrong.

**Week 1 slice (4–5 working days):**

```
tactical_markets/
  run_tactical.py             single entrypoint, ~50 lines
  src/
    sector_rotation.py        yfinance → 5d momentum rank → spread check → thesis text
    pushover.py               minimal client (copy market_dashboard's pattern)
  config/
    universe.yaml             9 sectors + 3 broad indices
    thresholds.yaml           spread_pct: 1.5, hold_days: 5
  data/
    theses.jsonl              one line per run (including no-thesis days)
  .env                        PUSHOVER_TOKEN, PUSHOVER_USER
```

- Day 1–2: `sector_rotation.py` end-to-end, output to stdout.
- Day 3: Pushover + `theses.jsonl` logging. Verify message on phone.
- Day 4: Windows Task Scheduler at 6:30 AM, reusing market_dashboard's wake pattern **with battery flags correct from the start** (`DisallowStartIfOnBatteries=false`, `StopIfGoingOnBatteries=false`, `StartWhenAvailable=true`).
- Day 5: Two consecutive smoke runs.

**Cut from the ROADMAP's week-1 scope:** VIX slope, gap detection, credit-spread context, HTML tiles, confidence formula, 3-tier publish/hold thresholds, backtest framework, economic-calendar signal, tests directory. Preserved: 9-sector universe, 5d momentum + 1.5% spread rule, hold-window text, output phrasing.

**Then freeze for two weeks.** Ian reads the daily thesis on his phone. Week-3 direction is decided by which of three failure modes shows up:
- (a) "Sometimes I'd act on these" → expand to VIX slope.
- (b) "Feels like noise" → fix sector rotation before adding anything.
- (c) "Never read them at 6:30 AM" → delivery is wrong, not signal.

**Trade-offs accepted:** no quantitative evidence in weeks 1–2 (only Ian's gut); less context per thesis than HTML tiles would provide; no confidence number; no integration with the trading layer (which doesn't exist yet).

**Hard dependency:** none. The strategic [market_dashboard](../market_dashboard/) composite score is *not* read in week 1. Week 3+ may consume it as macro context, but week 1 is fully standalone.

## Execution handoff

When the hopper opens, switch to Sonnet 4.6+ for execution. The brief is locked above; no further design pass needed unless something fails on contact with reality.

## Integration with the other two projects

- **Strategic dashboard** (`market_dashboard/`) — eventually consume its composite score / band as a tactical-context input.
- **Trading layer** (`tactical_markets_trading/`) — emit theses as structured records (e.g. JSON) for the Alpaca executor to consume. Keep the contract explicit — no shared imports across projects.

Three-way integration is on the long-term roadmap, not now.
