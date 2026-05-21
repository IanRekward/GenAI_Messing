---
title: Pivot note from tactical_markets_trading (bot) → MICRO project
date: 2026-05-21
from: tactical_markets_trading bot project
to: tactical_markets (MICRO) project owner
---

# Bot is pivoting away from sector-rotation execution

## Short version

The bot project ran extensive backtest research over 2026-05-20 to 2026-05-21 covering every retail-accessible strategy on 33 years of historical data (1993-2026). Conclusion: the 5-day sector-rotation signal MICRO emits does not have edge sufficient to beat passive benchmarks. The bot is pivoting to a multi-strategy regime-routed ensemble that does NOT consume MICRO signals.

**This is not a MICRO criticism.** MICRO produces what it was designed to produce — a daily sector-rotation thesis based on 5-day momentum. The bot's research found that this signal type (5-day cross-sectional sector momentum with 1.5% spread threshold) doesn't generate alpha over long historical windows. That's a finding about the underlying empirical question, not a defect in MICRO's implementation.

## What the bot will and won't do going forward

**Stopped (today):**
- `run_trading.py` Entry path now short-circuits via `SECTOR_ROTATION_5D_RETIRED = True` flag
- Bot no longer reads `theses.jsonl` for trading decisions
- The variant-B ask filed 2026-05-20 (request for 21-day-hold output) is CANCELLED — see updated status in [bot-integration-asks-variant-b-2026-05-20.md](bot-integration-asks-variant-b-2026-05-20.md)

**Continuing:**
- The bot's Exit task still runs daily to manage any remaining open positions until they close out
- MICRO project continues to operate independently — daily Pushover notifications still go to Rekwa
- The existing M1 (multi-thesis), M2 (confidence), M3 (signal_type) outputs MICRO ships are useful as personal-awareness data even though the bot doesn't trade them
- MACRO project (market_dashboard) gets PROMOTED in the new design — it becomes the regime safety layer for the bot

**New direction (bot side):**
- Phase 3 design: 3-component regime-routed ensemble
  - `trend_leveraged_tqqq` (TQQQ + 50d MA + 5% trailing stop)
  - `sector_momentum_top3_monthly` (different mechanics from the 5d signal — monthly cadence, 3-month lookback)
  - `trend_following_spy_200d` (simple SPY + 200d MA)
- Regime router uses MACRO + SPY 200d MA + VIX
- Implementation begins after Rekwa reviews the design doc

## Research that drove the pivot

For full context, see:
- `tactical_markets_trading/research/data/strategy_research_consolidated_2026-05-21.md` — headline findings + every strategy tested
- `tactical_markets_trading/research/data/extended_report.md` — 33-year backtest details
- `tactical_markets_trading/research/data/trailing_stop_walk_forward_report.md` — walk-forward validation showing 98% Sharpe retention OOS for the new candidate strategy
- `tactical_markets_trading/_bmad-output/planning-artifacts/phase-3-ensemble-design.md` — the new architecture

Key data points:
- sector_rotation_5d (live signal): 0.62% CAGR over 33 years, Sharpe 0.19
- Best alternative tuned to similar mechanics: still <1% CAGR — not salvageable by re-paramming
- Best historical sector-momentum variant (monthly cadence, 3-month lookback): 9.17% CAGR (vs SPY 10.81%) — usable as ensemble component but not as standalone
- TQQQ + 200d MA + 10% trailing stop: 19.87% CAGR with Sharpe 0.96 over 27-year synthetic window
- TQQQ + 50d MA + 5% trailing stop: 49% CAGR with Sharpe 1.86 — walk-forward confirmed (TEST=1.83 vs TRAIN=1.87, 98% retention)

## What this means for MICRO going forward

**Nothing has to change in MICRO.** The project keeps running as-is. Its daily output remains useful for personal awareness and continues to ship via Pushover.

If MICRO project owner wants to:
- Continue evolving the sector-rotation methodology — totally fine, it's just no longer feeding the trading bot
- Pivot MICRO to something else — also fine, but no urgency from the bot side
- Pause/freeze MICRO — also fine; the bot doesn't need anything from MICRO

The cross-project relationship simplifies: MICRO produces personal-awareness data for Rekwa's phone. Bot is fully self-sufficient for its own decisions.

## Questions or pushback

If MICRO owner wants to discuss the research findings or push back on the pivot, raise it in MICRO's TODO.md and Rekwa will see it. The bot's pivot is intentional and based on multi-day research, but the door is open if there's an argument I haven't seen.

— from the bot project, 2026-05-21
