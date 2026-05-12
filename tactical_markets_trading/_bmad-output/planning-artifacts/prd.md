---
stepsCompleted: ["step-01-init", "step-02-discovery", "step-02b-vision", "step-02c-exec-summary"]
inputDocuments: ["domain-active-trading-bot-regime-strategies-research-2026-05-11.md"]
workflowType: 'prd'
projectName: 'tactical_markets_trading'
userName: 'Rekwa'
date: '2026-05-11'
classification:
  projectType: "Algorithmic trading execution bot (Python backend service)"
  domain: "Quantitative finance / retail algo trading"
  complexity: "High (regulated, multi-strategy, microstructure-aware, real capital)"
  projectContext: "Brownfield (integrates with market_health + tactical_markets)"
  scopeModel: "Hybrid (upstream-driven + self-sufficient)"
  tierModel: "Tier 1 (70% sector ETFs) + Tier 2 (20% single stocks) in Phase 1; Tier 3 (crypto) deferred to Phase 2"
  riskProfile: "Retail scale ($10-50k), 1-3% position sizing, 20-25% max drawdown, modest leverage"
---

# Product Requirements Document — tactical_markets_trading

**Author:** Rekwa  
**Date:** 2026-05-11  
**Status:** In Development (Step 2 of 11)

---

## Document Purpose

This PRD locks in product requirements for an active trading bot based on comprehensive domain research covering 7+ methodology families, adaptability patterns, crypto-specific mechanics, event-driven strategies, classical technical analysis validation, and production infrastructure choices.

---

## Executive Summary

**tactical_markets_trading** is a systematic algorithmic trading bot that fuses signals from upstream market intelligence tools (`market_health` stress regime detection and `tactical_markets` premarket sector theses) with an ensemble of 11+ rule-based trading strategies operating across a tiered universe of liquid assets.

**Problem:** Retail traders face two constraints: the cognitive burden of monitoring multiple signal sources in real-time, and the persistent challenge of consistent trade execution without access to institutional infrastructure. This project addresses both by building a systematic decision engine that integrates heterogeneous signals, routes strategy allocation based on regime, and automates execution at scale ($10–50k account).

**Approach:** Rather than chasing high win rates through curve-fitting, the bot targets a modest but defensible edge: 51% win rate with strict position sizing (1–3% per trade) and proper capital allocation. The bot validates this edge through three sequential validation layers: (1) historical backtesting that includes taxes, fees, slippage, and wash-sale adjustments, (2) walk-forward testing to prevent overfitting, and (3) paper trading confirmation before any live capital is deployed.

**Differentiator:** Signal fusion. The bot doesn't operate in isolation; it consumes real-time market regime signals from `market_health` to scale allocation, and tactical sector rotation theses from `tactical_markets` to inform asset selection. This hybrid approach—upstream-driven when signals are available, self-sufficient when they aren't—creates structural advantage over standalone bots.

**Scope (Phase 1):** Tier 1 (70% allocation to sector ETFs with regime-aware rotation) + Tier 2 (20% opportunistic single-stock momentum picks within favored sectors). Tier 3 (crypto) is explicitly deferred to Phase 2 pending Phase 1 validation.

**Technical Stack:** Python + Backtrader for backtesting fidelity and tax realism, Alpaca API for live execution, VPS deployment for continuous operation. Retail-scale risk profile: 20–25% max drawdown, 2–5% monthly return target, Sharpe ratio threshold of 0.5+.

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

- **Trade audit trail:** Every trade logged with: entry timestamp, price, quantity, signal stack reasoning, strategy family, hold logic, exit timestamp, exit price, realized P&L, slippage vs. backtest, tax term flag, wash-sale flag. Format: human-readable logs + CSV for tax/analysis.
- **Dynamic hold windows:** Base hold window per strategy (sector rotation: 3–5 days, mean-reversion: 4–24 hours, etc.) extended by intraday signals (momentum persistent, price running, RSI <70) but capped at 2x base to prevent indefinite holds.
- **Kill switch automation:** Pauses trading and alerts on: single-trade loss >5%, win rate <48%, slippage >50% worse than backtest, signal source unavailability, Sharpe <0.3, hold duration >2x expected.
- **Code quality:** Modular strategy classes, comments explain WHY (not WHAT), no premature abstraction, single responsibility per function. Testable, readable, maintainable.
- **Documentation:** Each strategy family has a playbook (when it works, failure modes, parameters, examples). Signal integration spec covers market_health + tactical_markets freshness and routing. Execution spec defines order types and timing per strategy. Trade log schema fully documented.
- **Backtesting realism:** Includes taxes (short-term capital gains, wash-sale adjustments), fees (Alpaca commissions, bid-ask slippage), time-of-day execution (market vs. limit orders, morning gaps, intraday fills). Walk-forward testing prevents overfitting. Reverse stress-testing validates parameters under opposite market regimes (bull→bear, high vol→low vol).

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

**Discretionary override:** You can manually block certain trades or force execution on high-conviction setups.

**Fully autonomous operation:** Monthly check-ins only. Bot handles all rebalancing, signal routing, execution. You review month-end P&L and metrics.

---
