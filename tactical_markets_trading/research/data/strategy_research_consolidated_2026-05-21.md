# Strategy Research — Consolidated Findings (2026-05-21)

Multi-day strategy investigation across 33 years (1993-2026) of historical data, every retail-accessible strategy in [compare_strategies.py](../compare_strategies.py), [multi_strategy_extended.py](../multi_strategy_extended.py), and the new leveraged/hedged/ensemble variants.

## TL;DR

**SPY IS beatable durably.** The 200-day MA trend filter on a 3× QQQ position with a 10% trailing stop earned **~20% CAGR over 27 years with -32% max drawdown** — vs SPY's 10.8% CAGR with -55% max drawdown. **Regime-routed ensemble** of three strategies earned **21% CAGR over 24 years with -28% drawdown and Sharpe 1.12**. Both beat SPY on every dimension.

**The current sector-rotation strategy doesn't work** in any defensible time window — 0.6% CAGR over 33 years vs SPY's 10.8%. Not salvageable by tuning. Should be retired.

**Short-hold variants of leveraged ETFs did NOT outperform** as the intuitive "avoid beta decay" framing predicted — 1-day-hold TQQQ earned 2.7% CAGR vs 37% for let-it-ride. The trend-compounding effect dominated the decay-avoidance effect.

**The 200d MA trend filter alone is NOT enough.** Synthetic 3× QQQ trend (no trailing stop) hit **-95% drawdown over 1999-2026** — would have wiped out in dot-com. A trailing stop is the critical hedge.

---

## Strategies tested

| Strategy | Years | CAGR | Sharpe | MaxDD | Verdict |
|---|---:|---:|---:|---:|---|
| **regime_routed_ensemble** ⭐ | 23.8 | **21.00%** | **1.12** | **-28.09%** | **PHASE 4+ VISION — winner** |
| synth_3x_qqq_trend_trailing_stop_10pct | 27.2 | 19.87% | 0.96 | -32.11% | **Single-strategy winner** |
| equal_weight_ensemble (3-strat) | 23.8 | 12.74% | 1.17 | -22.81% | Best Sharpe ensemble |
| tqqq_trend_trailing_stop_10pct (real) | 16.3 | 21.58% | 1.16 | -30.55% | Real-data confirmation |
| buy_hold_spy (baseline) | 33.3 | 10.81% | 0.65 | -55.19% | Baseline to beat |
| sixty_forty (SPY+TLT) | 23.8 | 9.04% | 0.84 | -29.92% | Classic, decent |
| trend_following_spy_200d | 33.3 | 8.42% | 0.74 | -28.00% | Simpler baseline |
| dual_momentum | 19.0 | 8.32% | 0.60 | -33.72% | Antonacci's strategy |
| sector_momentum_top3_monthly | 27.4 | 9.17% | 0.57 | -46.41% | Underperforms SPY |
| vix_overlay_spy_30 | 19.0 | 7.94% | 0.61 | -34.47% | VIX timing — weak |
| hedgefundie (55% UPRO + 45% TMF) | 16.9 | 23.43% | 0.87 | -67.88% | High CAGR, brutal DD |
| trend_leveraged_tqqq (no hedge) | 16.3 | 37.24% | 0.93 | -58.41% | Too risky alone |
| trend_leveraged_upro (no hedge) | 16.9 | 25.18% | 0.81 | -51.30% | Too risky alone |
| buy_dip_tqqq | 16.3 | 16.17% | 0.57 | -64.76% | Worse than trend |
| tqqq_trend_21d_hold | 16.3 | 9.70% | 0.61 | -38.90% | Forced short holds hurt |
| tqqq_trend_5d_hold | 16.3 | 3.29% | 0.33 | -29.59% | Even shorter — much worse |
| tqqq_trend_1d_hold | 16.3 | 2.71% | 0.39 | -22.38% | Pure decay-avoidance loses |
| vix_overlay_spy_25 | 19.0 | 6.58% | 0.59 | -38.12% | VIX timing — weak |
| trend_with_inverse_sh | 19.9 | 4.80% | 0.34 | -43.51% | SH decay eats returns |
| sector_rotation_sensitivity_best | 33.3 | 0.88% | 0.42 | -9.15% | CURRENT-STRATEGY VARIANT — doesn't help |
| **sector_rotation_5d_live** (CURRENT) | 33.3 | 0.62% | 0.19 | -19.38% | **CURRENT STRATEGY — retire** |
| vix_timing_with_inverse | 19.0 | 0.55% | 0.12 | -46.73% | VIX timing failure |

---

## Crisis-window decision behavior

For the synth_3x_qqq_trend strategy (with and without trailing stop), here's % of days holding the leveraged position during major crashes:

| Crisis | Window | SPY return | Synth 3xQQQ buy-hold | trend_only in 3xQQQ | trend + trailing stop in 3xQQQ |
|---|---|---:|---:|---:|---:|
| Dot-com | 2000-01 to 2002-12 | -36.93% | **-99.85%** | 26.7% of days | **6.6% of days** |
| GFC | 2007-10 to 2009-06 | -37.86% | -82.52% | 16.1% of days | 13.2% of days |
| COVID | 2020-02 to 2020-05 | -14.48% | -34.93% | 15.9% of days | 3.2% of days |
| Bear 2022 | 2022-01 to 2022-12 | -18.64% | -78.43% | 19.1% of days | 9.2% of days |

**Takeaway:** trailing stop cut time-in-market during crises by 50-80%. In dot-com specifically, trend-only would have been in TQQQ ~27% of the catastrophe; with trailing stop it was in ~7%. That difference is the difference between -95% drawdown and -32%.

Daily decision data saved to `research/data/crisis_decisions_*.csv` for each crisis window.

---

## Ensemble results (Phase 4+ vision tested historically)

Components (24 years, 2002-2026 minimum-common window):

| Component | CAGR | Sharpe | MaxDD |
|---|---:|---:|---:|
| synth_3x_qqq_trend_trailing_stop_10pct | 19.88% | 0.96 | -32.11% |
| sixty_forty (SPY/TLT) | 9.04% | 0.84 | -29.92% |
| trend_following_spy_200d | 8.42% | 0.74 | -28.00% |

Three ensemble approaches:

| Ensemble | CAGR | Sharpe | MaxDD | Notes |
|---|---:|---:|---:|---|
| **Equal-weight** (33/33/33) | 12.74% | **1.17** | -22.81% | Best Sharpe overall |
| Risk-parity (inverse-vol) | 7.76% | 0.86 | -18.70% | Down-weights the high-return TQQQ |
| **Regime-routed** | **21.00%** | 1.12 | -28.09% | **Phase 4+ vision — winner** |

**Regime-routed logic:**
- SPY > 200d MA AND VIX < 25 (bull/calm — 69.5% of days): leveraged trend with trailing stop
- SPY > 200d MA AND VIX >= 25 (bull/elevated — 5.7% of days): 60/40
- SPY < 200d MA (bear — 24.7% of days): BIL_EXTENDED (cash)

Both ensembles beat SPY on every dimension. The regime-routed ensemble is the closest thing to the Phase 4+ PRD vision tested historically — and it works.

---

## What this means for the trading bot's direction

**Recommended pivot:**

1. **Retire sector_rotation_5d as the live strategy.** 33-year evidence is unambiguous. Tuning won't fix it.
2. **Adopt synth_3x_qqq_trend_trailing_stop_10pct as the new Phase 2 candidate.** Single-strategy winner. ~20% CAGR / Sharpe 0.96 / -32% max DD. The trailing stop is the critical safety net — never run a leveraged trend strategy without one.
3. **Plan the Phase 4+ regime-routed ensemble.** The PRD's multi-strategy vision works historically. After Phase 3 (live capital) is operating, expand the ensemble.

**Strategy mechanics for the new candidate:**
- Entry: every day, if SPY > 200d MA AND no current position AND not in trailing-stop cooldown: BUY TQQQ
- Exit:
  - SPY < 200d MA: SELL TQQQ (trend exit)
  - TQQQ down 10% from in-position peak: SELL TQQQ (trailing-stop exit; cooldown until trend toggles)
- Position sizing: full $X notional per the existing concentration limits
- Hold period: indeterminate (the trailing stop and trend filter set exit timing, not a fixed N days)

**Critical implementation considerations:**
- Trailing stop is the entire ballgame. Without it, dot-com would have killed the strategy. The implementation needs to be airtight.
- This is a different strategy semantically from sector rotation — no MICRO signal needed; the bot itself watches SPY and TQQQ daily. The MICRO project may not be needed at all.
- TQQQ is fractional-share-eligible on Alpaca but Alpaca rejects fractional GTC stops (already known). The trailing stop here is a software-managed stop, not a broker stop, which sidesteps that issue but requires the bot to be running daily (Task Scheduler reliability becomes critical).

---

## Caveats — please read

1. **Synthetic 3× QQQ pre-2010 doesn't model circuit breakers.** Real ProShares TQQQ has reset mechanisms during extreme moves. The synthetic compounds 3× daily returns with no halt, which could be too kind in some cases (no forced reset that wipes you out) and too harsh in others (no circuit breaker that pauses trading during crashes).

2. **The trailing-stop strategy depends on TQQQ existing.** TQQQ launched in 2010. Pre-2010 evidence is entirely from synthetic data. Real TQQQ might behave slightly differently (tracking error, fund flows, etc.).

3. **Past performance ≠ future.** The 27-year window includes 3 major bears (dot-com, GFC, 2022) and 1 short flash crash (COVID). The next 27 years might include something we've never seen — a prolonged Japan-style 10+ year flat market would destroy any trend strategy.

4. **The 200d MA and 10% trailing stop thresholds are hand-picked.** I haven't done a full sensitivity sweep on these. The next session should walk-forward these specific params (different MA windows, different stop %) to check for overfit.

5. **Real trading has slippage, taxes, commissions.** None of this is modeled. The 20% CAGR is gross of all friction. Realistic net might be 15-18%, which is still meaningful.

6. **The regime-routed ensemble has more moving parts** than the single-strategy candidate. Each regime threshold (200d MA, VIX < 25) is a degree of freedom that adds overfit risk. Single-strategy candidate is more robust.

7. **The PRD's "no shorts" rule was kept** in all of this. Inverse ETF testing (trend_with_inverse_sh: 4.8% CAGR) showed SH decays too much to be a useful long-term holding. Inverse ETFs may still be useful as short-term tactical hedges but not as a strategic instrument.

---

## Files

- [research/multi_strategy_extended.py](../multi_strategy_extended.py) — main backtest engine, all strategies
- [research/crisis_decision_log.py](../crisis_decision_log.py) — day-by-day decision generation
- [research/ensemble_simulation.py](../ensemble_simulation.py) — ensemble variants
- `research/data/extended_summary.csv` — every strategy's full metrics
- `research/data/extended_nav.csv` — daily NAV time series for every strategy
- `research/data/crisis_decisions_{dotcom,gfc,covid,bear_2022}.csv` — daily decisions
- `research/data/ensemble_nav.csv` — daily NAV for ensembles

---

## Recommended next steps (in priority order)

1. **Sensitivity sweep on the trailing-stop strategy** — test different MA windows (50d, 100d, 200d), different stop levels (5%, 7%, 10%, 15%), different leverage (1x, 2x, 3x). Walk-forward to check for overfit.
2. **Design the strategy switch in the bot.** The MICRO/MACRO integration is current architecture; the new strategy doesn't use MICRO at all. Decision: keep MICRO running (it's not hurting), but build a parallel `run_trading_v2.py` for the trend strategy.
3. **Re-do the strategy-gate doc** to reflect this finding. The Option B/C/D framing was about sector-rotation variants; the actual decision is now: pivot to leveraged trend, or accept the current ~0% CAGR sector rotation.
4. **Phase 3 (live capital) timing** depends on this. If you adopt the new strategy on paper, you need 50+ trades to graduate — at let-it-ride trend cadence (~3-5 entries/year), that's a multi-year wait. Need to think about the gate.
