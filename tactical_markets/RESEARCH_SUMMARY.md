# Tactical Markets: Research Summary & Design Rationale

**How empirical research (2000–2026) informed the signal selection and execution strategy.**

---

## Signal Selection: What Actually Works

### 1. Sector Rotation (Quarterly Mean Reversion)

**Research finding:** Sector rotation with quarterly rebalancing achieves **Sharpe 0.92** across TSX 60 (2000–2025), significantly outperforming equal-weight buy-and-hold (Sharpe 0.62).

**Why it works:**
- Sectors mean-revert within a 3-month window due to cyclical earnings, commodity exposure, and relative valuation
- Quarterly rebalancing rhythm aligns with earnings season
- Historical win rate: ~55% (better than coin flip; real edge)

**Design decision — Hold window:** 3–7 days within a quarter-long thesis
- Supports the empirical finding that mean reversion works at the 2–10 day horizon
- Avoids holding into the next quarter where new mean reversions begin
- Reduces transaction friction vs. daily rebalancing

**Design decision — Confidence scoring:** Base confidence = 55% for sector rotation
- Conservative (published research shows 55% win rate)
- Can be adjusted up if signal strength is top-quartile relative strength

---

### 2. Volatility Term Structure (VIX Slope)

**Research finding:** An inverted VIX term structure (front month > 3M) predicts equity upside over 3–5 days. A dynamic short-volatility strategy targeting VIX slope inversion compounds at **16.3% annually (Sharpe 1.0)** with **15% correlation to SPX** (2008–2025, across crisis periods).

**Why it works:**
- Inverted term structure signals fear premium (traders overpaying for near-term protection)
- Reversion happens within 3–5 days as fear fades
- 15% SPX correlation means signal is diversifying (not just equity beta)

**Design decision — Hold window:** 3–5 days
- Matches the documented mean-reversion horizon for VIX slope
- Shorter than sector rotation to capture rapid vol decay

**Design decision — No leverage:** Avoid margin/options
- VIX term structure is accessible via short VXX (inverse vol ETF), but retail leverage has high friction
- Instead: flag as "signal to reduce equity volatility hedges" or add SPY calls (defined risk)

**Design decision — Confidence scoring:** Base confidence = 65% for VIX slope
- Slightly higher than sector rotation (stronger historical Sharpe)
- Only signal if inverted 2+ days (confirm signal persistence)

---

### 3. Overnight Gap Trading (Large-Caps Only)

**Research finding:** Overnight gaps in the 0.0–0.19% range fill 89–93% of the time, with **0.48% average gain** and **profit factor 1.8** (realistic slippage included). Gaps >0.7% down have **negative expectancy (−0.11%)**; skip these.

**Why it works:**
- Small gaps are often mechanical (futures imbalances, Asia closes) and don't reflect new information
- Larger gaps (>0.2%) are real price discovery; reversal odds drop sharply
- Large-cap liquidity ensures fills; small-caps experience too much slippage

**Design decision — Filter:** Only 0–0.19% gaps, only large-caps (SPY, QQQ, IWM, major sector ETFs)
- Matches the documented edge exactly
- Avoids negative-expectancy large gaps

**Design decision — Hold window:** <1 day (next close or reversion within hours)
- Gap fills typically happen within first 30 min to 4 hours of market open
- Don't hold overnight after fill; new gaps kill the thesis

**Design decision — Confidence scoring:** Base confidence = 60% for gap fills
- Win rate ~89–93% on 0–0.19% gaps (excellent), but profit factor 1.8 means some wins are small
- Only signal if gap is within tight range; avoid edge cases

---

### 4. Credit Spreads as Macro Timing (Not Trading)

**Research finding:** Credit spreads (IG OAS, HY OAS) lead equity crashes by **2–8 weeks**. A 1.2σ overnight spike in spreads is an unusual repricing event correlated with risk-off sentiment.

**Why it works:**
- Credit spreads are forward-looking (incorporates default risk expectations)
- Equities react slower due to retail/momentum dynamics
- FRED data is free; historical leads are empirically documented

**Design decision — Not a standalone signal:** Use only as macro *context* to adjust confidence on other signals
- Don't trade credit spreads directly (retail derivatives access limited; wrong timezone for international spreads)
- Instead: "IG OAS +25bps overnight → risk-off regime → lower sector rotation confidence"

**Design decision — Confidence adjustment:**
```
if credit_spreads_change_bps > 1.5_sigma:
    confidence_adjustment = −10%  # reduce all equity signal confidence
```

---

## What Doesn't Work (And Why We Excluded It)

### News & Sentiment-Based Signals

**Research finding:** Sentiment alone (Reddit volume, FinBERT news scores) **lacks robust predictive power**. Hybrid approaches (sentiment + technical oversold + stable fundamentals) sometimes work, but edge is **inconsistent and hard to defend empirically**.

**Why excluded:**
- False positive rate too high (90% of viral news doesn't move markets; 10% of quiet news does)
- Requires interpretation (which model? which sentiment threshold?)
- Overfitting risk: easily look good in backtest, fail in live
- Sentiment changes hourly; thesis hold windows are hours to days (mismatch)

**How to use sentiment:** As a *confirmation* layer, not a signal
- If sector rotation says "buy XLE" AND energy news volume is elevated AND not already priced in (XLE up 3%+ already) → increase confidence
- But never rely on sentiment alone

### Technical Analysis Alone

**Research:** TA indicators (MACD, RSI, Bollinger Bands) lack documented edge without additional context.

**Design decision:** Use technical as *confirmation* of mean reversion, not signal
- RSI < 30 + sector rotation thesis = higher confidence
- RSI > 70 + sector rotation thesis = lower confidence (already ran, less edge)

### High-Frequency / Intraday Strategies

**Research:** Transaction costs (0.025% per round-trip on liquid assets) destroy retail edges on hold periods <1 day.

**Design decision:** Minimum hold 1 day (gaps) to 3 weeks (momentum)
- Gaps are exception (fill quickly, end within hours)
- Everything else must justify friction costs via 2%+ per-trade expected return

---

## Slippage & Friction: Realistic Modeling

**Research finding:** 
- **Large-caps:** 1–2 bps slippage typical
- **Small-caps / illiquid ETFs:** 75–100+ bps slippage
- **Round-trip friction (commissions + slippage):** ~0.025% on liquid assets
- **Retail limit orders:** 10–20 bps savings vs market orders; 65% fill rate

**Design decisions:**
- Backtest all signals with 1–2 bps slippage (large-cap universe)
- Only trade large-cap ETFs/indices (avoid micro-cap slippage hell)
- Default to limit orders (Phase 1 manual, Phase 2 auto-execute rules favor limits)
- Paper-to-live gap expected: ~30% performance degradation if backtest assumes zero friction

**Validation step:** Phase 1 paper trading monitors actual fills vs model. If live slippage > 2x model → re-fit thresholds.

---

## Position Sizing: Kelly Criterion & Drawdown Control

**Research finding:** Full Kelly criterion maximizes growth but accepts 50–70% drawdowns; practitioners typically use **Half Kelly or Quarter Kelly** (6–7% or 3–4% per trade).

**Design decisions:**
- **Fixed 2% risk per trade:** Most reliable for retail; 40% better completion rate than aggressive sizing
- **Max 5% per position:** Prevents over-concentration; leaves room for scaling
- **Max 20% in open positions:** Keeps firepower to add on reversals, reduces blowup risk
- **Only valid with 50+ historical trades:** Until then, Kelly is noise-driven

**Validation:** Phase 1 paper trading will confirm sizing doesn't produce >25% peak drawdown. If it does, scale back to 1% per trade.

---

## Hold Windows & Regime Detection

**Research finding:**
- **Mean reversion:** 2–10 days optimal Sharpe; beyond 15 days degrades
- **Momentum:** 3 weeks to 3 months optimal
- **Regime shifts:** Edge documented in 2000–2026 data may have decayed by 2026 (market adaptation)

**Design decisions:**
- **Sector rotation:** 5–7 days within a quarter (mean reversion window)
- **VIX slope:** 3–5 days (vol mean reversion)
- **Gaps:** <1 day (fill within hours)
- **Auto-exit on timeout:** Don't hold past window; trade becomes discretionary after edge expires

**Validation step:** Phase 1 will measure actual hold times and returns by window length. If 90% of wins happen within 2 days, tighten timeout to 48h.

---

## Confidence Scoring Calibration

**Research finding:** Backtests with Sharpe >2.5 are suspicious (overfitting). Real retail edge produces Sharpe 0.75–1.0 after friction.

**Design decisions:**
- **Base confidences:**
  - Sector rotation: 55% (mean reversion, quarterly, Sharpe 0.92)
  - VIX slope: 65% (stronger historical Sharpe 1.0)
  - Gaps: 60% (high win rate, low avg win)
- **Confidence is *not* win rate.** It's "I'm >70% sure this edge is real right now"
- **Publish threshold:** 70% confidence (real edge, low false-positive rate)
- **Hold threshold:** 50–70% (informational; user decides)
- **Don't publish:** <50% (pure noise)

**Validation:** Phase 1 will compare confidence to actual wins. If 70% confidence signals win only 40%, lower thresholds or fix signal logic.

---

## Why We're Starting with These 4 Signals (Not 10+)

**Philosophy:** Ship the edges we *know work*, validate empirically, then add more.

**Risk of overcomplexity:**
- Each signal adds maintenance burden (monitoring live performance, regime detection, etc.)
- Correlation between signals increases as universe expands (harder to size, higher whip-saw risk)
- Overfitting risk: more signals = more parameter tuning = more curve-fitting

**4 signals are:**
- Well-researched (2000–2026 historical data backing each)
- Uncorrelated (sector rotation is micro, VIX slope is macro hedging, gaps are technical, spreads are context)
- Retail-accessible (no exotic derivatives, no negative-expectancy trades)
- Time-bounded (24–48h window, not "hold forever")

**Expansion path:**
- After Phase 1 validation (30+ trades), add **relative strength pairs** (long breadth, short narrow concentration)
- After Phase 2 (50+ trades), consider **earnings surprises** (but only on large-caps with clear edges)
- Never add: sentiment alone, indicator cocktails, ML black boxes without interpreted features

---

## Known Failure Modes (We're Watching For)

### 1. Overfitting to Backtest Data

**Mitigation:**
- 30%+ out-of-sample test during development
- Paper trading Phase 1 as external validation
- Quarterly recalibration of thresholds (don't trust 2000–2026 fit blindly; markets evolve)

### 2. Survivorship Bias

**Example:** SPX backtest with survivors-only can overstate returns by 1.6% annually.

**Mitigation:**
- All sector rotations include delisted/de-indexed companies (handle separately)
- Gap signals limited to highly-liquid tickers (no micro-caps with survivorship distortion)

### 3. Look-Ahead Bias

**Example:** Using close data to generate overnight signals (wrong; signals must use prior-close + pre-market data).

**Mitigation:**
- Signals generated strictly before market open (6:30 AM, using prior close)
- Gap analysis uses futures open (available before 9:30 AM ET)
- No intraday price data in signal logic

### 4. Regime Shift / Edge Decay

**Risk:** Sector rotation worked 2000–2026; but markets change. Edge could degrade within 6–12 months of this build.

**Mitigation:**
- Monitor rolling Sharpe quarterly (target >0.75 in live trading)
- If rolling Sharpe falls below 0.50 for 4+ weeks, flag as "edge decay" and re-optimize
- Phase 3 (live trading) only approved if Phase 1+2 validates Sharpe >0.75 after friction

---

## Research Sources

All findings grounded in:
- Academic: Oxford, Berkeley, MDPI, arXiv (2024–2025 papers)
- Practitioner: QuantifiedStrategies, State Street, Zerodha, Macrosynergy, Alpaca white papers
- Empirical: 2000–2026 historical backtest data (FRED, yfinance)

See `RESEARCH_SUMMARY.md#Sources` in the Agent research output for full citations.

---

## Next: Execution Roadmaps

**Brief 1 (Signal Generation):** Implements these 4 signals + confidence scoring + daily 6:30 AM run + dashboard rendering

**Brief 2 (Trading Integration):** Validates edge empirically via Phase 1 (manual execution, 30+ trades) → Phase 2 (auto-execute) → Phase 3 (live)

Both briefs are **designed for iterative validation**, not blind optimization.
