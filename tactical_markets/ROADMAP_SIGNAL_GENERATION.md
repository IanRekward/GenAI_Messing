# ROADMAP Brief 1: Tactical Markets Signal Generation

**Overnight repricing + sector rotation signals for 24–48h tactical decisions.**

## Problem

The strategic Market Stress Dashboard answers: *"Is the system in stress?"* (10y+ context, macro regime). It doesn't answer: *"What's moving right now, and where's the 24–48h trade within that regime?"*

Gap: A retail investor reads "composite orange, dollar/global shock" but doesn't know whether to rotate from XLK→XLE, flatten duration via IEF, or wait. The macro signal is there; the *actionable* signal isn't.

## Solution: Overnight Repricing Dashboard

Run at **6:30 AM ET** (premarket, before open) to surface **3–5 live theses** from overnight market repricing. Each thesis is:
- **Specific** (ticker/ETF, not abstract sectors)
- **Actionable** (entry price, stop, target, hold window)
- **Time-bounded** (24–48 hour window, not "wait and see")
- **Grounded in edge** (empirically backed strategies from 2000–2026 research)

Output: Dashboard tiles + Pushover alert ("3 tactical plays overnight: sector rotation, duration repricing, gap fill…")

## Design Decisions

### Signal Categories (Grounded in Research)

**1. Sector Rotation (Quarterly Mean Reversion)**
- **Edge:** Sharpe 0.92 across TSX 60, 2000–2025
- **Hold window:** 3–7 days (within quarter)
- **Trigger:** Prior day close, relative strength between 9 sectors + broad indices
- **Data:** yfinance OHLC for XLK, XLF, XLE, XLI, XLV, XLY, XLC, XLU, XLRE + IWM, QQQ, SPY
- **Logic:** 
  - Rank sectors by 5-day momentum
  - If top/bottom relative strength >1.5% apart, signal: "rotate from bottom quartile → top quartile"
  - Verify with 20-day MA (don't trade against longer trend)
- **Example:** "XLE up 2.8%, XLK down 1.1%. Relative spread: 3.9% (top 10%). Signal: rotate 5–10% from XLK → XLE. Hold 5–7 days."

**2. Volatility Term Structure (VIX Slope)**
- **Edge:** 16.3% annual, Sharpe 1.0, 15% SPX correlation. Inverted slope predicts equity upside
- **Hold window:** 3–5 days (vol mean reverts)
- **Trigger:** VIX front month vs 3M/6M; current vs prior close
- **Data:** yfinance ^VIX, ^VIXV (3M), ^VIXT (6M implied, or use CBOE website scrape)
- **Logic:**
  - VIX slope = (VIX3M − VIX) / VIX (simplified; deeper: futures term structure)
  - If slope inverts (VIX > VIX3M) AND inverted >2 days, signal long equity or short VXX
  - If slope steep (VIX3M − VIX > 3), signal short vol or reduce equity volatility hedges
- **Example:** "VIX 22, 3M 19 (inverted 3 pts, 2nd day). Signal: VIX reversal + equity upside within 5 days. Consider: short VXX or buy SPY calls (low lever­age)."

**3. Overnight Gap Trading (Large-Caps Only)**
- **Edge:** 0.48% avg gain on 0.0–0.19% gaps, profit factor 1.8. Only on large-caps (IWM, SPY, QQQ, major tickers)
- **Hold window:** <1 day (next close or reversion within hours)
- **Constraint:** Gaps >0.7% down have negative expectancy (−0.11%); skip those. Only signal 0–0.19% gaps.
- **Data:** Prior close vs futures open gap (ES, NQ, YM via yfinance future contracts or CBOE data)
- **Logic:**
  - Gap = (futures open − prior close) / prior close
  - If 0.0% < gap < 0.19%, signal: "gap likely to fill; trade reversion"
  - If gap < −0.7%, skip (high-risk reversal, negative expectancy)
- **Example:** "SPY gap +0.12% overnight. Signal: 89% probability fill by next close. Entry: at open on reversion, size 2–3% risk."

**4. Credit Spreads as Macro Timing (Not Trading)**
- **Edge:** Leads equity crashes by 2–8 weeks; free from FRED
- **Hold window:** N/A (macro context, not trade)
- **Data:** FRED ICE BofA IG OAS (BAMLC0A4CBBB), HY OAS (BAMLH0A0HYM2)
- **Logic:** 
  - Flag if spreads spike >2σ overnight (unusual repricing)
  - If spike + negative news + VIX>20: risk-off context, lower sector rotation conviction
  - If spreads narrow >50bps overnight: risk-on context, favor equity rotation
- **Example:** "IG OAS widened 25bps overnight (unusual, +1.2σ). Combined with Fed speaker hawkish stance: reduce equity long conviction, wait for reversal."

**5. Economic Calendar Triggers (Optional, if new data overnight)**
- **Hold window:** Same as macro catalyst (hours to days depending on data type)
- **Trigger:** Pre-market data releases (China PMI, ECB, BoJ decisions, initial jobless claims)
- **Data:** Retrieve from FRED, trading calendars (Investing.com API or manual check)
- **Logic:**
  - If Asia/Europe releases surprise >1σ, assess which U.S. assets are repricing in premarket
  - Signal: "Asia PMI beat, ASX rally +1.2%. Expect U.S. growth rotation at open; favors XLI, XLC."

### Thresholds & Confidence

Each signal gets a **confidence score** (1–100%):
- **70%+:** Publish (enough edge to act)
- **50–70%:** Publish as "lower conviction" (informational only)
- **<50%:** Don't publish (noise)

**Confidence formula (simplified):**
```
base_confidence = historical_win_rate_for_signal_type
adjustment = (signal_strength_vs_baseline) × calibration_factor
final_confidence = min(base_confidence + adjustment, 100)
```

Example:
- Sector rotation base = 55% (mean reversion, quarterly Sharpe 0.92)
- Spread is 3.9% (top 10% historical), adjustment = +15%
- Final confidence = 70%

### Data Sources & Refresh

| Signal | Source | Refresh | Latency |
|--------|--------|---------|---------|
| Sector OHLC | yfinance | Daily open, premarket | <2s |
| VIX term structure | yfinance + scrape ^VIX(3M/6M) | Daily premarket | <5s |
| Gap analysis | yfinance futures (ES, NQ, YM) | At open | <1s |
| Credit spreads | FRED API (cached 1hr) | Daily premarket | <5s |
| Economic calendar | Investing.com API (free tier limited) | 1x daily premarket | <10s |

**Caching:** All FRED data cached 1h (avoid rate limits). Gap data fresh at open. OHLC pulled fresh at 6:25 AM.

## Outputs

### Dashboard

HTML tile deck (lightweight, <500KB):
```
┌─────────────────────────────────┐
│ OVERNIGHT REPRICING (6:30 AM ET)│  
│ Updated: 2026-04-27 06:32       │
└─────────────────────────────────┘

┌─ SECTOR ROTATION (70% conf) ────┐
│ XLE +2.8% vs XLK −1.1%          │
│ Action: Rotate 5% XLK → XLE     │
│ Entry: Market at open           │
│ Stop: YTD low (or −2%)          │
│ Hold: 5–7 days                  │
│ Thesis: Post-OPEC strength...   │
└─────────────────────────────────┘

┌─ VIX SLOPE (65% conf) ──────────┐
│ Slope inverted 3 pts (2nd day)  │
│ Action: Short vol (VXX) or long │
│ Entry: Premarket              │
│ Target: Spread mean revert (−2) │
│ Hold: 3–5 days                  │
│ Risk: Fed pivot reverses slope  │
└─────────────────────────────────┘

[More tiles...]
```

### Pushover Alert

```
📊 Tactical Overnight (6:30 AM):
3 live plays: XLE rotation, VIX slope short, 
SPY +0.12% gap fill. Full dashboard: [link]
```

### Data Logged (JSON)

```json
{
  "run_timestamp": "2026-04-27T06:30:00Z",
  "theses": [
    {
      "id": "rotation_20260427_0",
      "signal_type": "sector_rotation",
      "confidence": 70,
      "assets": {
        "sell": {"ticker": "XLK", "price": 122.45, "qty": 100},
        "buy": {"ticker": "XLE", "price": 91.30, "qty": 100}
      },
      "entry_logic": "5-day momentum rank + 20d MA confirmation",
      "stop": {"level": 89.50, "pct": −1.97},
      "target": {"level": 94.00, "pct": 3.01},
      "hold_window_hours": 120,
      "historical_win_rate": 0.55,
      "thesis": "Post-OPEC production cut hawkishness, energy near 200d MA inflection..."
    },
    ...
  ],
  "macro_context": {
    "vix": 21.2,
    "vix_slope": −2.8,
    "credit_spreads": {
      "ig_oas": 112,
      "ig_oas_change_bps": 15,
      "interpretation": "Unusual tightening overnight; risk-on bias"
    }
  }
}
```

## Implementation Files

```
tactical_markets/
  ROADMAP_SIGNAL_GENERATION.md  (this file)
  src/
    overnight_signals.py         (main signal generation)
    sector_rotation.py           (sector rotation logic + backtester)
    vix_slope.py                 (VIX term structure analysis)
    gaps.py                       (gap detection + filter)
    credit_context.py            (FRED OAS context + macro timing)
    confidence.py                (confidence scoring)
    dashboard_renderer.py        (HTML tile generation)
  config/
    signal_thresholds.yaml       (confidence levels, hold windows, slippage models)
    assets.yaml                  (universe: 9 sectors + 3 indices + gap tickers)
  tests/
    test_sector_rotation.py      (backtest 2015–2026, Sharpe validation)
    test_vix_slope.py            (VIX term structure edge)
    test_gaps.py                 (0–0.19% gap filter, fill rate)
    test_confidence.py           (confidence score calibration)
  data/
    overnight_runs.jsonl         (log of each 6:30 AM run + final outcomes)
    backtest_results.csv         (historical performance by signal type)
  output/
    dashboard.html               (rendered tiles for 6:30 AM push)
    [daily snapshots archived]
```

## Success Criteria

- [ ] 6:30 AM daily run produces 3–5 theses without errors
- [ ] Sector rotation: backtest Sharpe 0.92 or better (2015–2026) with realistic slippage (1–2 bps)
- [ ] VIX slope: positive correlation with next 3–5d SPX returns documented
- [ ] Gap signals: 80%+ fill rate for 0–0.19% gaps on large-caps
- [ ] Live validation: 30+ executed theses (via trading integration, Phase 1), win rate >50%
- [ ] Confidence calibration: signals >70% win >55% in live tests; signals 50–70% win ~50%
- [ ] No false alerts: macro context (credit spreads) correctly filters risk-off days

## Dependencies

- **Data:** yfinance (free), FRED API (free, rate-limited), optional Investing.com calendar API
- **Libraries:** pandas, numpy, scipy (backtest), requests, Jinja2 (HTML rendering)
- **External:** Market open time (9:30 AM ET), timezone handling (UTC, EST)
- **Reference:** Strategic dashboard (Market Stress) for macro regime context (optional confidence adjustment)

## Edge Cases

1. **Gap analysis on holidays:** No futures contract open; skip gap signal
2. **Circuit breaker triggered previous day:** Extra caution on gap signals (high volatility regime)
3. **Fed speaker/data release premarket:** Credit spreads may spike artificially; require 2–3h confirmation
4. **VIX term structure data stale:** Fall back to VIX level alone (backup signal)
5. **Sector ETF halted:** Skip rotation signal, use broad indices (SPY, QQQ, IWM) instead

## Known Limitations

- **Paper trading vs live:** Slippage modeled at 1–2 bps; actual may be 2–5 bps in stress. Monitor Phase 1 live fills vs backtest.
- **Overnight windows:** Only covers 4 PM–9:30 AM. Intraday repricings not captured (intentional; too high friction for retail).
- **News/sentiment not included:** Hard edge not documented. Can be added as confidence *modifier* after confidence is validated.
- **Regime shifts:** Sector rotation edge may fade within 12 months as market adapts. Monitor live Sharpe quarterly.

## Rollout

1. **Week 1:** Implement sector rotation + VIX slope, backtest 2015–2026
2. **Week 2:** Add gap detection, credit spreads context, confidence scoring
3. **Week 3:** Dashboard HTML + Pushover integration, manual test runs
4. **Week 4:** Begin live paper trading (Phase 2 project), log outcomes daily
5. **Month 2+:** Monitor live performance, calibrate thresholds based on actual fills + P&L

## Co-developed with Alpaca Paper Trading

This brief is designed *in concert with* `tactical_markets_trading/` (Alpaca integration). Signal generation is decoupled from execution—can ship the dashboard independently—but the trading layer validates edge empirically.

---

**Next:** Draft Alpaca trading integration (Brief 2), then lock both and begin implementation.
