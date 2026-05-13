---
stepsCompleted: ["step-01-init", "step-02-discovery", "step-02b-vision", "step-02c-exec-summary", "step-e-01-discovery", "step-e-02-review", "step-e-03-edit"]
inputDocuments: ["domain-active-trading-bot-regime-strategies-research-2026-05-11.md"]
workflowType: 'prd'
workflow: 'edit'
projectName: 'tactical_markets_trading'
userName: 'Rekwa'
date: '2026-05-11'
lastEdited: '2026-05-13'
classification:
  projectType: "saas_b2b"
  projectTypeDetail: "SaaS platform: Python algorithmic trading bot backend + operator dashboard (monitoring, reporting, controls)"
  domain: "Quantitative finance / retail algo trading"
  complexity: "High (regulated, multi-strategy, microstructure-aware, real capital)"
  projectContext: "Brownfield (integrates with MACRO + MICRO)"
  scopeModel: "Hybrid (upstream-driven + self-sufficient)"
  tierModel: "Tier 1 (70% sector ETFs) + Tier 2 (20% single stocks) in Phase 1; Tier 3 (crypto) deferred to Phase 2"
  riskProfile: "Retail scale ($10-50k), 1-3% position sizing, 20-25% max drawdown, modest leverage"
editHistory:
  - date: '2026-05-13'
    changes: "Complete PRD expansion: added User Journeys, Domain Requirements, Functional Requirements, Non-Functional Requirements, Integration Specs (MACRO/MICRO). Polished Exec Summary. Updated Success Criteria with fintech requirements. Renamed upstream tools to MACRO/MICRO."
  - date: '2026-05-13'
    changes: "Reclassified projectType from 'api_backend' (Python backend service) to 'saas_b2b' to reflect actual full-stack scope: bot backend + operator dashboard, user journeys, and reporting interfaces. Resolves classification conflict flagged in validation report."
---

# Product Requirements Document — tactical_markets_trading

**Author:** Rekwa  
**Date:** 2026-05-11 (updated 2026-05-13)  
**Status:** In Development (Comprehensive Draft Complete)

---

## Document Purpose

This PRD locks in product requirements for an active trading bot based on comprehensive domain research covering 7+ methodology families, adaptability patterns, crypto-specific mechanics, event-driven strategies, classical technical analysis validation, and production infrastructure choices.

---

## Executive Summary

**tactical_markets_trading** is a systematic algorithmic trading bot that fuses real-time market regime signals from MACRO (market stress detection) and tactical sector theses from MICRO (premarket signal generation) with an ensemble of 11+ rule-based trading strategies operating across a tiered universe of liquid assets.

**Problem:** Retail traders face two constraints: cognitive overload from monitoring multiple signal sources in real-time, and limited access to institutional-grade execution infrastructure. This project solves both by building a systematic decision engine that integrates heterogeneous signals, routes strategy allocation by regime, and automates execution for retail accounts ($10–50k scale).

**Approach:** Target a defensible edge (51% win rate) via strict position sizing (1–3% per trade) and proper capital allocation, validated through three sequential layers: (1) historical backtesting with taxes, fees, slippage, and wash-sale adjustments; (2) walk-forward testing to prevent overfitting; (3) paper trading confirmation before deploying live capital.

**Differentiator:** Signal fusion creates structural advantage. The bot consumes real-time regime signals from MACRO (to scale position allocation) and tactical theses from MICRO (to select assets). Hybrid operation: upstream-driven when signals flow, self-sufficient when they don't. Standalone bots lack this multi-signal context.

**Scope (Phase 1):** Tier 1 (70% allocation to 12 sector ETFs + 3 broad indices, regime-aware rotation) + Tier 2 (20% opportunistic single-stock momentum picks within favored sectors flagged by MICRO). Tier 3 (crypto) deferred to Phase 2 pending Phase 1 validation.

**Technical Stack:** Python + modular backtesting framework with tax realism, Alpaca API for live execution, VPS deployment for continuous operation. Retail-scale risk profile: 20–25% max drawdown, 2–5% monthly returns, Sharpe ratio ≥0.5.

---

## Success Criteria

### User Success

You can deploy the bot with confidence knowing that:
- **Full trade traceability:** Every executed trade has a complete audit trail: entry signal stack (which strategies + signals triggered the buy), reasoning (plain English), execution details, hold logic, exit reasoning, and P&L. If a trade looks off, you can instantly see why it happened.
- **Phase 1 validation complete:** Tier 1 + Tier 2 model has proven viable across backtest, paper trading (3 months with regime diversity), and live trading with metrics (Sharpe, win rate, drawdown) aligned across all three.
- **Confident operational transition:** The bot can transition from daily monitoring (paper phase) → weekly monitoring → eventual autonomous operation with monthly check-ins.
- **Understanding edge:** You understand precisely how the bot wins: signal fusion (market_health + tactical_markets) gives regime context, opportunistic strategy selection (routing by regime) maximizes payoff per trade, and 51% win rate + proper sizing compounds into positive returns.

### Business / Investor Success

- **Sharpe ≥ 0.5:** Maintained consistently across backtest, paper trading, and live trading (within 0.1 tolerance). If live Sharpe drops <0.3, bot auto-pauses and alerts.
- **Win rate ≥ 51%:** Realized in live trading. Tracked over rolling windows (10 trades, 30 trades, 90 trades). If drops <48% (2 std dev below baseline), bot alerts and pauses.
- **Returns: 2–5% monthly** on retail scale ($10–50k account). Compounded.
- **Drawdown contained:** Max drawdown 20–25%; single-trade loss never >5% of account (kill switch); hold duration never >2x expected window without manual override (safety valve).
- **Tax-efficient:** Trade log includes short-term vs. long-term designation, wash-sale flags, and is exportable to accountant/tax software. Realized P&L includes tax impact modeling from backtests.

### Technical Success

- **Trade audit trail:** Every trade logged with entry timestamp, price, quantity, signal stack reasoning, strategy family, hold logic, exit timestamp, exit price, realized P&L, slippage vs. backtest, tax term flag, and wash-sale flag. Format: human-readable logs + CSV for analysis and tax reporting.
- **Dynamic hold windows:** Base hold window per strategy (sector rotation: 3–5 days, mean-reversion: 4–24 hours, etc.) extended by intraday signals but capped at 2x base to prevent indefinite holds.
- **Kill switch automation:** Pauses trading and alerts on: single-trade loss >5% of account, win rate <48%, slippage >50% worse than backtest, signal source unavailability, Sharpe <0.3, hold duration >2x expected.
- **Code quality:** Modular strategy classes, comments explain WHY (not WHAT), no premature abstraction, single responsibility per function. Testable, readable, maintainable.
- **Documentation:** Each strategy family has a playbook (when it works, failure modes, parameters, examples). Signal integration spec covers MACRO + MICRO freshness and routing. Execution spec defines order types and timing per strategy. Trade log schema fully documented.
- **Backtesting realism:** Includes taxes (short-term capital gains, wash-sale adjustments), fees (Alpaca commissions, bid-ask slippage), time-of-day execution (market vs. limit orders, morning gaps, intraday fills). Walk-forward testing prevents overfitting. Reverse stress-testing validates parameters under opposite market regimes (bull→bear, high vol→low vol).

### Compliance & Risk Success

- **Trade compliance:** 100% of trades logged with complete reasoning chain traceable back to signal source. No trade executed without documented entry reason, hold window, and exit trigger.
- **Regulatory alignment:** Pattern day trader rules enforced (max 3 round trips per 5-day window for accounts <$25k; auto-enforced for accounts <$25k). Position limits enforced (max 5% per trade, max 20% open positions, max 25% single ticker).
- **Tax reporting ready:** Short-term vs. long-term designation tracked per trade. Wash-sale detection and flagging implemented. CSV export format validated against accountant workflow.
- **Risk guardrails:** Drawdown monitoring with alerts at 15% (warning) and 20% (escalation review). Auto-pause at 25% max drawdown. Single-trade loss >5% triggers immediate kill switch.
- **Signal source SLA:** Bot degrades gracefully if MACRO or MICRO signals unavailable. Manual kill switch available at any time. No trades executed without explicit signal source confirmation.

### Measurable Outcomes

| Metric | Target | Measurement |
|---|---|---|
| Win rate (live) | ≥51% | % of closed trades with positive P&L |
| Sharpe ratio (live) | ≥0.5 | Daily returns, rolling 30-day calculation |
| Monthly return | 2–5% | Ending balance / starting balance per calendar month |
| Max drawdown | 20–25% | Peak-to-trough from account high-water mark |
| Single-trade loss | <5% of account | Maximum per-trade loss (kill switch: pause if exceeded) |
| Win rate (paper) | ≥51% | Over full 3-month paper trading period |
| Sharpe (paper) | ≥0.5 | Over full 3-month paper trading period |
| Signal freshness | <1 hour staleness | tactical_markets update frequency (see Phase 1B enhancement) |
| Slippage realization | ≤150% of backtest | Realized slippage / modeled slippage |
| Code review | 100% | All strategy families and core execution reviewed for correctness |
| Tax log accuracy | 100% | CSV export matches realized trades; accountant validation |

---

## Product Scope

### MVP — Minimum Viable Product (Phase 1A: First 30 Days Paper Trading)

**What's in:**
- **Tier 1 (70% allocation):** Sector ETFs (9 SPDR + 3 broad: SPY, QQQ, IWM) with regime-aware rotation. Regimes: bull (growth tilt), bear (defensive tilt), stress (cash/hedge).
- **Strategy families (5–7 core):** Momentum, mean-reversion, carry, breakout, statistical arbitrage. Minimum for multi-regime opportunism.
- **Signal fusion:** market_health composite score → allocation sizing; tactical_markets sector theses → asset selection within Tier 1.
- **Execution:** Market orders at 6:35 AM ET (post-open chaos), limit orders for mean-reversion confirmation intraday.
- **Backtesting:** Backtrader with taxes, fees, slippage, walk-forward testing.
- **Trade logging:** Audit trail with signal stack, reasoning, P&L. CSV for analysis.
- **Reporting:** Daily reports to you (signal count, executed trades, +/- P&L, Sharpe snapshot).
- **Kill switch logic:** Pauses on loss >5%, win rate <48%, slippage >50% deviation, signal source down.

**What's not:**
- Tier 2 or Tier 3
- Advanced execution (adaptive order sizing, intraday signal extensions)
- ML-based stock picking
- Discretionary override interface
- Sentiment/NLP integration
- Monthly automation (still daily check-ins)

### Growth — Competitive Maturity (Phase 1B: Months 2–3 Paper, Then Live)

**What's added:**
- **Tier 2 (20% allocation):** Single-stock momentum picks within favored sectors (flagged by tactical_markets), filtered by event catalysts and divergence checks.
- **Full strategy ensemble:** All 11+ methodology families, with explicit regime routing.
- **Dynamic hold windows:** Intraday signals extend hold duration; momentum persistence, price breakouts, volatility normalization.
- **Advanced execution:** Adaptive order routing (limit vs. market per strategy family), spread-aware sizing (reduce position if spread >0.1%).
- **Quarterly deep dives:** Parameter stress-testing, regime analysis, strategy family performance dashboards.
- **Reporting transition:** Weekly summaries (instead of daily), alerts only on kill switches.
- **Tax workflow integration:** Wash-sale flagging, short-term vs. long-term tracking, CSV export validated against accountant workflow.

**What's still not:**
- Tier 3 (crypto)
- ML-based universe selection
- Sentiment integration
- Fully autonomous (still weekly check-ins)

### Vision — Future Roadmap (Phase 2+)

**Tier 3 (crypto):** 10% allocation to BTC/ETH with 24/7 operation during equity market closure. Correlation <0.3 to equities. Sharpe ≥0.3 (volatile asset class).

**Smarter asset selection:** ML-based ranking of single stocks (not just momentum) informed by historical buy/sell patterns. Tier 2 expands from 20 stocks to 50+.

**Macro context enrichment:** VIX tracking, credit spread monitoring (HY OAS), regime probability estimates feed strategy weighting.

**Sentiment and event detection:** NLP on financial news to detect catalysts; event-triggered strategy activation.

**Discretionary override:** Manual trade blocking and forced execution for high-conviction setups.

**Fully autonomous operation:** Monthly check-ins only. Bot handles all rebalancing, signal routing, execution. You review month-end P&L and metrics.

---

## User Journeys

### Journey 1: Daily Monitoring & Trade Execution (Phase 1A MVP)

**Actor:** Retail trader (you)

1. **Pre-market (6:15 AM ET):** Open dashboard, review overnight MACRO regime shift + MICRO theses (updated 6:30 AM)
2. **Decision point:** Review proposed trades (entry price, stop, target, hold window) + rationale
3. **Execution choice:** Click "Execute" on thesis card or skip
4. **Intraday (9:35 AM–4 PM ET):** Monitor position P&L on dashboard; system auto-exits on target/stop/hold-window-timeout
5. **End of day (5 PM ET):** Review daily P&L, signal execution rate, trades logged to history
6. **Exit:** Dashboard shows cumulative Sharpe, win rate, drawdown vs. target

**Frequency:** Daily 6:30–11:00 AM, then check intraday 1-2x.

---

### Journey 2: Weekly Reporting & Strategy Review (Phase 1B+)

**Actor:** Retail trader + optional advisor

1. **Weekly (Monday AM):** Open dashboard, view rolling metrics (win rate over 30 trades, Sharpe 30-day, drawdown trend)
2. **Review:** Compare realized returns vs. backtest; identify underperforming strategies
3. **Analysis:** Pull CSV export; load into spreadsheet or send to accountant for tax impact review
4. **Action:** Adjust strategy confidence weights or pause underperformer
5. **Documentation:** Notes logged to trade history for future reference

**Frequency:** Once per week, ~15 min.

---

### Journey 3: Tax & Accountant Workflow

**Actor:** You + accountant

1. **End of month/quarter:** Export trade CSV from dashboard
2. **Accountant receives:** Symbol, quantity, entry date/price, exit date/price, P&L, short-term flag, wash-sale flag
3. **Validation:** Accountant reconciles CSV against portfolio system; asks clarifications if needed
4. **Tax filing:** Incorporates data into tax return; flags any special adjustments

**Frequency:** Monthly during active trading, quarterly review.

---

### Journey 4: Paper to Live Transition (Phase 1A→1B)

**Actor:** You (with oversight)

1. **Trigger:** After 30+ days paper trading, metrics align (Sharpe >0.5, win rate >51%, max drawdown <20%)
2. **Pre-live:** Create live account on Alpaca, fund with initial capital ($10k min)
3. **Go-live:** Toggle bot from paper → live. Position sizes auto-adjust to account value. Kill switches armed.
4. **Daily monitoring:** Watch for slippage divergence vs. paper; verify fills match expectations
5. **Escalation:** If slippage >150% of backtest assumption, pause and debug

**Frequency:** One-time transition; ongoing live monitoring.

---

### Journey 5: Kill Switch & Emergency Response

**Actor:** You

**Trigger scenarios:**
- Single trade loss >5% of account → Immediate pause
- Win rate drops below 48% over 10 trades → Pause + alert
- Sharpe <0.3 (rolling 30-day) → Pause + review
- MACRO/MICRO signal unavailable >1 hour → Pause + alert
- Unexpected slippage (>50% worse than backtest) → Pause + debug

**Response:**
1. Dashboard displays alert + reason
2. All trading paused immediately
3. You review trade log for context
4. Manual resume or fix + re-enable

**Frequency:** As-needed; expect ~1-2/month in early phases.

---

## Domain Requirements

**Retail Algorithmic Trading / Quantitative Finance**

### Regulatory Compliance

- **Pattern Day Trading (PDT) Rules:** For accounts <$25k, enforce max 3 round-trip trades per 5-day rolling window. Bot must respect this with auto-checks before order submission. Alert if at risk of violation.
- **Order Routing & Best Execution:** Trades routed through Alpaca (Nasdaq member). Document execution venue and time; log best-bid/ask at order submission time.
- **Position Limits & Concentration Risk:** Max 5% of account per single trade; max 20% in open positions simultaneously; no single ticker >25% of account. Alerts if approaching limits.

### Tax Compliance

- **Trade Term Classification:** Mark each trade as short-term (<365 days) or long-term (≥365 days) at execution. Update if holding period changes.
- **Wash-Sale Detection:** Track all sales. Flag sales within 30 days of matching purchase. Preventive alerts before execution if wash-sale risk exists.
- **Tax Report Export:** CSV format compatible with accountant workflows + tax software (IB Flex, E*TRADE downloads, etc.). Include: symbol, qty, entry date/price, exit date/price, P&L, term, wash-sale flag.

### Financial Audit Trail

- **Complete Trade Log:** Every trade logged with: timestamp (entry + exit), venue, fill price, quantity, signal reasoning (plain English), strategy family, hold window, exit trigger, P&L dollars/%, slippage (actual vs. backtest).
- **Signal Source Documentation:** Every trade tied to signal stack: which MACRO regime triggered sizing? Which MICRO thesis triggered entry? Include confidence scores if present.
- **Manual Override Logging:** If you override bot decision (cancel order, force execution), log reason + timestamp.

### Risk Governance

- **Drawdown Monitoring & Escalation:** Continuous tracking of peak-to-trough drawdown. Alerts at 15% (warning), 20% (escalation review), 25% (auto-pause). Resume requires manual confirmation.
- **Position Sizing Hard Limits:** Kill switch if single trade loss >5% of account. Kill switch if open positions >20% of account. Kill switch if any single position >25% of account value.
- **Performance Breakers:** Auto-pause if win rate <48% over 10 trades. Auto-pause if Sharpe <0.3 (rolling 30-day). Resume requires manual review + confirmation.

### Account & Portfolio Management

- **Account Minimum:** Phase 1A paper (unlimited practice); Phase 1B live minimum $10k. If account drops <$5k, auto-pause trading to preserve margin.
- **Leverage:** Phase 1A no margin. Phase 1B max 1:1 (no actual margin borrowing; margin account for buying power cushion only).
- **Idle Cash:** Maintain min 5% cash buffer. Alert if cash <5% or if no trades possible due to buying power constraints.

---

## Functional Requirements

### Signal Consumption & Routing

**FR1:** Bot consumes market regime signals from MACRO API on every pre-market run (6:30 AM ET). Regime values: "bull" (growth), "bear" (defensive), "stress" (cash). Used to scale position allocation (Tier 1 only in Phase 1A; Tier 1 + Tier 2 in Phase 1B).

**FR2:** Bot consumes tactical sector theses from MICRO API on every pre-market run. Each thesis includes: symbol, direction (buy/sell), entry price, stop, target, hold window, confidence score. Theses expire after hold window elapses.

**FR3:** If MACRO or MICRO unavailable (>1 hour staleness or API error), bot logs alert and disables new trade execution. Outstanding positions remain open; exits execute on pre-programmed rules (target/stop/hold-window-timeout).

**FR4:** Bot auto-routes strategy allocation based on regime. Specific allocation per regime: bull regime → 60% momentum + 40% breakout; bear regime → 70% mean-reversion + 30% defensive sectors; stress regime → 80% cash + hedges + 20% carry. Routing logic documented per strategy family.

### Trade Execution & Management

**FR5:** Bot generates pre-market trade list (3–5 theses max) showing: symbol, entry price, quantity (calculated via position sizing rules), stop, target, expected hold window, confidence score, signal reasoning.

**FR6:** User reviews dashboard and clicks "Execute" to submit orders. Orders submitted as limit orders within 5 bps of market (ask + 5 bps for buys, bid − 5 bps for sells) with 60-second time-to-live window.

**FR7:** If limit order fills, position is logged to active positions with entry details. If limit order expires unfilled, order is canceled and logged as "unfilled"; no position opened.

**FR8:** For each open position, bot tracks: entry price, quantity, entry time, target price, stop price, hold window expiry time. Updates P&L continuously during market hours.

**FR9:** Position exits automatically on (first trigger wins): (a) target price hit → log as "target exit"; (b) stop price hit → log as "stop exit"; (c) hold window expiry → log as "hold window timeout exit"; (d) manual kill switch → log as "manual pause exit".

**FR10:** On exit, bot logs: exit timestamp, exit price, exit reason, P&L dollars, P&L %, slippage (actual - backtest expected), tax term (ST/LT), wash-sale flag (Y/N).

### Position Sizing & Risk Controls

**FR11:** Position size calculated via: risk = account_value × 2%; position_size = risk / (entry_price − stop_price); capped at 5% of account and adjusted for spread if >0.1%.

**FR12:** Before order submission, bot checks: (a) account has sufficient buying power; (b) position doesn't exceed 5% of account; (c) total open positions don't exceed 20% of account; (d) no single ticker already >25% of account. If any check fails, order canceled with reason logged.

**FR13:** Kill switch pauses all trading if: single trade loss >5% of account realized, OR win rate <48% over rolling 10 trades, OR max drawdown >25%, OR account equity <$5k (Phase 1B). Manual intervention required to resume.

**FR14:** Position limits enforced for Pattern Day Trading: for accounts <$25k, max 3 round-trip trades per 5-day rolling window. Bot counts open + closed positions; alerts if approaching limit before order submission.

### Reporting & Logging

**FR15:** Dashboard displays real-time: current date/time, account equity, cash, buying power, open positions (symbol, entry price, current P&L %), running win rate (trades closed this week), Sharpe ratio (rolling 30-day), max drawdown (peak-to-trough).

**FR16:** Daily report (5 PM ET) shows: trades executed today, filled qty/price, exits (target/stop/timeout), daily P&L, cumulative P&L this month, signal execution rate (theses executed / theses generated).

**FR17:** Trade log persisted to CSV: symbol, entry date/time, entry price, quantity, exit date/time, exit price, exit reason, P&L $, P&L %, slippage bps, tax term, wash-sale flag, strategy family, signal stack reasoning. CSV exportable for analysis + tax workflow.

**FR18:** Weekly summary (Monday AM): rolling win rate (10-trade, 30-trade, 90-trade windows), Sharpe ratio (rolling 30-day), max drawdown, largest winner, largest loser, strategy family breakdown (which strategies contributed most to P&L).

### Backtesting & Validation

**FR19:** Bot includes backtesting module capable of running historical scenarios (2015–2026 data) with: entry/exit logic identical to live, taxes modeled (short-term cap gains rate), fees modeled (Alpaca commissions + slippage assumptions), wash-sale adjustments applied, walk-forward testing (train on 80%, test on 20%).

**FR20:** Backtest output includes: Sharpe ratio, win rate, max drawdown, monthly returns, strategy family performance breakdown, parameter sensitivity analysis. Compares to live metrics for calibration.

---

## Non-Functional Requirements

### Performance

**NFR1:** Dashboard refreshes real-time position P&L with <500 ms latency during market hours (9:30 AM–4 PM ET). End-of-day reporting completes within 5 minutes of market close (by 4:05 PM ET).

**NFR2:** API calls to MACRO and MICRO complete within 2 seconds (95th percentile). If latency >5 seconds, log warning and use most recent cached signal.

**NFR3:** Backtesting runs complete within 5 minutes for 10-year historical dataset (2015–2026). Walk-forward tests complete within 10 minutes.

### Reliability & Uptime

**NFR4:** Bot achieves 99% uptime during market hours (9:30 AM–4 PM ET). Maintenance windows (updates, restarts) occur outside market hours. Any unplanned outage >5 minutes triggers alert.

**NFR5:** If VPS/deployment connection drops during market hours, positions remain open and auto-exit rules (target/stop/hold-window) execute regardless (failsafe mode).

**NFR6:** Daily signal freshness from MACRO: update frequency <1 hour old. From MICRO: update frequency <1 hour old. If staleness >2 hours, bot logs alert and disables new trade execution until signal refreshed.

### Security & Data Protection

**NFR7:** API keys stored in encrypted environment, not in code. Credentials not logged or transmitted in plaintext. Storage mechanism is implementation detail.

**NFR8:** Trade logs and P&L data stored on the bot's deployment VPS, not in cloud storage, unless explicitly exported. No third-party telemetry without explicit user consent.

**NFR9:** Dashboard accessible only locally (restricted to localhost or VPS-bound private network). No public-facing endpoints. VPS access requires cryptographic key authentication (public-key infrastructure or equivalent).

### Fault Tolerance

**NFR10:** If MACRO signal unavailable, bot continues operating with last-known regime (caches regime for 2 hours). If MICRO signal unavailable, bot executes only open positions; no new theses generated.

**NFR11:** Partial order fills handled gracefully: if limit order partially fills, position opened with actual fill quantity; exit rules scale to actual quantity (stop/target adjusted proportionally).

**NFR12:** Network retry logic: transient API errors (timeouts, 5xx responses) retried up to 3 times with exponential backoff (1s, 2s, 4s). Permanent errors (401, 403, 404) logged and escalated to manual review.

---

## Integration Specifications

### MACRO (Market Stress Dashboard) → Bot Integration

#### Data Contract

**Signal Name:** `macro_regime`

**API Endpoint:** `GET /api/current-regime` (or equivalent)

**Response Schema:**
```json
{
  "timestamp": "2026-05-13T10:30:00Z",
  "regime": "bull" | "bear" | "stress",
  "composite_score": 0-100,
  "sub_scores": {
    "equity_momentum": 0-100,
    "credit_spreads": 0-100,
    "volatility": 0-100,
    "liquidity": 0-100,
    "flow": 0-100
  }
}
```

**Update Frequency:** Daily at 6:30 AM ET (premarket). Intraday updates if regime shifts >10 points.

**Freshness SLA:** Data no older than 1 hour at time of consumption. If stale >2 hours, bot logs alert and disables new trade execution.

**Failure Mode:** If endpoint unavailable >1 hour, bot uses last-known regime (cached for 2 hours). If cache expires, defaults to "neutral" allocation (equal split across strategy families).

#### Integration Points

- **Allocation Scaling (Phase 1A+):** MACRO regime directly scales Tier 1 position sizes: bull → 100% target allocation, bear → 75% allocation (shift to defensive sectors), stress → 50% allocation (favor cash/hedges).
- **Strategy Routing (Phase 1B+):** MACRO regime weights strategy families: bull → favor momentum/breakout, bear → favor mean-reversion/defensive, stress → favor carry/hedges.
- **Reporting (Phase 1A+):** Dashboard displays current MACRO regime + sub-scores as context for daily decisions. Trade log includes MACRO regime at entry time for backtesting correlation.

#### Implementation Notes

- Bot caches last 48 hours of regime history for walk-forward testing and regime shift analysis
- A regime shift (e.g., bull → bear) triggers alert on dashboard; manual review recommended before next batch of trades
- MACRO unavailability does NOT pause live trading; outstanding positions continue to managed per their rules

---

### MICRO (Tactical Signal Generator) → Bot Integration

#### Data Contract

**Signal Name:** `micro_theses`

**API Endpoint:** `GET /api/theses` or `GET /api/theses?limit=10&min_confidence=60`

**Response Schema:**
```json
{
  "timestamp": "2026-05-13T06:30:00Z",
  "theses": [
    {
      "thesis_id": "uuid",
      "symbol": "XLE",
      "direction": "BUY",
      "entry_price": 91.30,
      "stop_price": 89.50,
      "target_price": 94.00,
      "hold_window_hours": 48,
      "confidence": 75,
      "reasoning": "Sector rotation: relative strength XLE vs XLK 3.9%. Hold 48h within quarter.",
      "strategy_family": "sector_rotation",
      "backtest_sharpe": 0.92,
      "backtest_win_rate": 0.58
    },
    ... (3-5 theses per premarket run)
  ]
}
```

**Update Frequency:** Daily at 6:30 AM ET (premarket). No intraday updates in Phase 1A; optional intraday refresh in Phase 1B.

**Freshness SLA:** Data no older than 1 hour at time of consumption. If stale >2 hours, no new theses consumed; existing positions managed per rules.

**Failure Mode:** If endpoint unavailable, bot continues managing outstanding positions. No new theses generated until MICRO endpoint restored.

#### Integration Points

- **Thesis Display (Phase 1A+):** Dashboard displays top 3–5 theses with entry/stop/target and reasoning. User clicks to execute or skip.
- **Position Sizing (Phase 1A+):** Confidence score from MICRO feeds into position size scaling (high confidence → larger position within limits, low confidence → minimum position).
- **Hold Window Enforcement (Phase 1A+):** `hold_window_hours` from MICRO defines auto-exit time. Position exits at market if still open when window expires.
- **Strategy Routing (Phase 1B+):** `strategy_family` from MICRO helps route Tier 2 single-stock picks and intraday signal processing.
- **Backtesting (Phase 1A+):** Historical backtest metrics (Sharpe, win rate) from MICRO included in daily reporting for live vs. backtest comparison.

#### Implementation Notes

- Bot validates all MICRO theses for: (a) symbol liquidity (min daily volume 1M shares), (b) entry/stop/target spreads are reasonable, (c) hold window <5 days (Phase 1A limit). Theses outside parameters logged as "filtered" and not displayed.
- Duplicate symbols across multiple theses in same run: bot keeps highest confidence thesis; others logged as "filtered".
- MICRO unavailability does NOT pause bot; existing positions managed per rules. However, without MICRO theses, new trade opportunities cannot be generated.

---

### Parallel Work Gates & Dependencies

**Gate 1 (Phase 1A MVP): MACRO & MICRO Operational**
- ✅ MACRO endpoint stable, regime classification working
- ✅ MICRO endpoint stable, thesis generation working
- ✅ Both endpoints return valid data by 6:30 AM ET daily
- **Impact on Bot:** Without this gate, bot cannot execute Phase 1A (manual execution requires MICRO theses + MACRO regime context). Recommend: parallel development of bot + signal sources; gate approval 1-2 weeks before Phase 1A paper trading launch.

**Gate 2 (Phase 1B Growth): Intraday Signal Support**
- ✅ MICRO supports intraday thesis refresh (optional; enhances Tier 2 single-stock picking)
- ✅ MACRO supports mid-day regime shift alerts (optional; enhances strategy routing)
- **Impact on Bot:** Phase 1A functions without this gate. Phase 1B (dynamic hold windows + advanced execution) requires intraday signal support for edge. Recommend: implement after Phase 1A validates signal quality (30+ trades).

**Gate 3 (Phase 1B→Live): Backtesting Validation**
- ✅ Bot backtesting module completed and validated against 2015–2026 data
- ✅ Walk-forward testing run; Sharpe ≥0.5, win rate ≥51%, max drawdown ≤25%
- ✅ Live metrics (30 days paper trading) align with backtest metrics within 10% tolerance
- **Impact on Bot:** Paper trading (Phase 1A) can start without this gate (exploratory). Transition to live (Phase 1B) requires this gate (confidence in edge).

**Work Parallelization:**
- MACRO development: Independent of bot development. Can proceed in parallel.
- MICRO development: Partially independent. Signal generation logic can proceed in parallel; but integration with bot requires data contract finalization (Gate 1). Recommend finalizing contract early (week 1) to unblock parallel work.
- Bot development: Can proceed with mock MACRO/MICRO endpoints (hardcoded test data) while upstream projects finalize. Integration testing (bot + real endpoints) occurs in weeks 3–4.

---

## Implementation Priority & Sequencing

### Phase 1A (MVP: 30 Days Paper Trading)

**Weeks 1–2: Setup & Core Development**
- Bot scaffold + Alpaca API integration (order submission, position tracking)
- MACRO/MICRO API consumption (polling, error handling, caching)
- Position sizing + risk controls (kill switches, PDT rules)
- Backtesting framework (tax realism, fees, slippage)

**Weeks 3–4: Integration & Testing**
- Dashboard (pre-market thesis display, position P&L, daily reporting)
- Manual execution (user clicks "Execute" on thesis)
- Trade logging (CSV export, signal stack documentation)
- Paper trading launch (target 20+ theses executed)

**Success Metrics:**
- 20+ trades executed without system errors
- Win rate ≥51%, Sharpe ≥0.5 (paper)
- Max drawdown <20%
- All trades logged with complete audit trail

### Phase 1B (Growth: Months 2–3 Paper, Then Live)

**Weeks 5–8: Enhancement & Validation**
- Tier 2 single-stock integration (if MICRO supports; else defer to Phase 2)
- Intraday signal processing (hold window extensions, momentum persistence)
- Weekly reporting + strategy performance dashboards
- Tax workflow integration (CSV validation with accountant)

**Weeks 9–10: Live Transition Prep**
- Create live Alpaca account, validate funding workflow
- Slippage calibration (compare paper fills vs. backtest assumptions)
- Kill switch testing (verify pause/resume behavior)
- Live trading launch (target $10k+ initial capital)

**Success Metrics:**
- 50+ total trades (paper + live), Sharpe ≥0.5, win rate ≥51%
- Slippage within 150% of backtest assumptions
- Drawdown <20%, no account blowups
- Tax CSV validated by accountant

---

**Next Steps:**
1. ✅ PRD finalization (this document)
2. → UX Design review with Sally (dashboard wireframes, thesis display)
3. → Architecture review with Winston (MACRO/MICRO API contracts, deployment model, database schema)
4. → Epic/Story breakdown for Phase 1A implementation
5. → Integrate MACRO & MICRO requirement docs into respective repos

---
