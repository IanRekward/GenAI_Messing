---
stepsCompleted: [1]
inputDocuments: []
workflowType: 'research'
lastStep: 1
research_type: 'domain'
research_topic: 'Active trading methodologies and regime-conditional strategy selection for an automated trading bot'
research_goals: 'Build a first-principles foundation in trading methodologies (rules-based and quantitative); map which methods perform under which market regimes; design a strategy-selection architecture that consumes regime/health signals from sibling tools (market_health, tactical_markets) to route between approaches.'
user_name: 'Rekwa'
date: '2026-05-11'
web_research_enabled: true
source_verification: true
---

# Research Report: domain

**Date:** 2026-05-11
**Author:** Rekwa
**Research Type:** domain

---

## Research Overview

[Research overview and methodology will be appended here]

---

## Domain Research Scope Confirmation

**Research Topic:** Active trading methodologies and regime-conditional strategy selection for an automated trading bot

**Research Goals:**
1. Build a first-principles foundation in active trading methodologies (Rekwa's background is buy-and-hold investing)
2. Map which methodologies perform under which market regimes
3. Inform architecture for a bot that routes between strategies based on signals from sibling tools `market_health` and `tactical_markets`

**Domain Research Scope:**

- **Trading methodology taxonomy** — trend-following, mean-reversion, momentum, breakout, carry, statistical arbitrage, market-making, event-driven, factor-based, plus classical TA / charting practitioner approaches. First-principles framing.
- **Regime classification** — trend vs. range, low vs. high vol, risk-on vs. risk-off, liquidity states; how each is detected.
- **Methodology ↔ regime mapping** — historical performance of strategies by regime; failure modes.
- **Strategy-selection architectures** — ensemble, regime-switching (HMMs), meta-models, walk-forward rotation. Practical for small operator scale.
- **Risk management primitives** — position sizing (Kelly, vol targeting), stop-loss design, drawdown control, correlation limits.
- **Execution & infrastructure landscape** — broker APIs (IBKR, Alpaca, crypto exchanges), data feeds, latency tiers, paper vs. live.
- **Regulatory/compliance basics** — retail-scale algo bot considerations (PDT rule, tax treatment, wash-sale, jurisdiction).
- **Backtesting & evaluation pitfalls** — overfitting, look-ahead bias, survivorship bias, regime-dependent performance, OOS protocol.
- **Crypto trading inclusion** — methodologies that translate (or don't) to 24/7 crypto markets; crypto-specific microstructure considerations.

**Research Methodology:**

- All claims verified against current public sources via web search
- Multi-source validation for critical claims that will inform architectural decisions
- Confidence level framework — practitioner techniques included alongside academic/quant approaches; filter on *evidence quality*, not pedigree
- Wide net cast; noise sifted by corroboration and mechanism plausibility

**Scope Confirmed:** 2026-05-11

---

## Domain Analysis — Landscape of Active Trading Methodologies

> Step 2 reframe: instead of "market size / TAM" framing, this section maps the **structure** of the active-trading methodology landscape — the major families, the regime concept, and where automated bots fit. Subsequent steps go deep on each family and on the regime ↔ methodology mapping.

### The Foundational Split: Systematic vs. Discretionary

Active trading divides on one axis before anything else: **who pulls the trigger.**

- **Systematic trading** — rules generate a definitive signal; the human's job is to build and maintain the rules, not to decide each trade. Replicable, scalable, automatable, backtestable. Emotion-free by construction.
- **Discretionary trading** — a human makes each decision in real time, using judgment over data, news, and "feel." More flexible, less consistent, not directly automatable.
- **Hybrid** — systematic foundation with discretionary overrides (e.g., a rules-based bot that a human can pause during a Fed announcement).

**For a trading bot, you are by definition systematic.** Discretionary is out of scope unless we wrap manual approval steps, which defeats the point. Hybrid is plausible later (e.g., a kill-switch UX).

_Confidence: high — this is the foundational industry distinction; both AQR (institutional) and retail/practitioner sources agree on it._
_Sources: [AQR — Systematic vs. Discretionary](https://www.aqr.com/Insights/Research/Alternative-Thinking/Systematic-vs-Discretionary), [Wikipedia — Systematic trading](https://en.wikipedia.org/wiki/Systematic_trading), [DayTrading.com — 115+ Strategies](https://www.daytrading.com/systematic-discretionary-trading-strategies)._

### Methodology Families (Preview Taxonomy)

The systematic side clusters into a handful of families. These overlap and shade into each other — taxonomies vary by source — but this is the working set we'll go deep on in later steps:

| Family | One-line definition | Naive intuition (vs. buy-and-hold) |
|---|---|---|
| **Trend following** | Buy when price has been going up, sell when going down. Ride moves. | Opposite of "buy the dip" — you buy *because* it went up. |
| **Mean reversion** | When price stretches far from its average, bet it returns. | The "buy the dip" instinct, mechanized. |
| **Momentum** | Close cousin of trend following — bet that recent relative outperformance continues. | Buy what's been winning; sell what's been losing. |
| **Breakout** | Trade the moment price exits a range. | Transitional — sits between range and trend regimes. |
| **Carry** | Earn the spread/yield differential for holding an asset (e.g., FX carry, funding rates in crypto). | Like a dividend, but mechanical. |
| **Statistical arbitrage / pairs** | Bet two correlated assets revert to their normal relationship. | Market-neutral; not directional. |
| **Market making** | Quote both sides of the spread, earn the bid-ask. | Infrastructure-heavy; not really a "retail bot" play. |
| **Event-driven** | Trade around scheduled or unscheduled news (earnings, macro releases, listings). | News-driven; usually needs low-latency. |
| **Factor / multi-factor** | Sort assets by quantified attributes (value, quality, low-vol, etc.) and rotate. | More portfolio-rotation than active "trading." |
| **Grid / DCA bots** | Mechanical position-laddering (popular in crypto). | Procedural, not predictive. |
| **Classical TA / chart pattern** | Patterns (head-and-shoulders, support/resistance, candlestick formations) trigger entries. | Big practitioner camp; evidence quality varies wildly. |

_Evidence note: trend-following, momentum, mean reversion, carry, and stat arb have the deepest academic evidence base. Classical TA is contested — some specific signals (e.g., the 200-day moving average as a regime filter) hold up empirically; many chart patterns don't. We'll triage by evidence in later steps._

_Sources: [DayTrading.com — Systematic/Discretionary Strategies](https://www.daytrading.com/systematic-discretionary-trading-strategies), [QuantVPS — Systematic Trading Concepts](https://www.quantvps.com/blog/systematic-trading-concepts-and-strategies-examples), [Quantified Strategies — Mean Reversion vs. Trend Following](https://www.quantifiedstrategies.com/mean-reversion-vs-trend-following/)._

### Market Regimes: The Concept

A **market regime** is a persistent state of the market that changes which strategies work. The standard practitioner framing uses two axes:

1. **Direction** — up-trending, down-trending, sideways (range-bound)
2. **Volatility** — quiet vs. volatile

This yields six basic regimes (e.g., "up-trending quiet," "sideways volatile," etc.). Practitioners and quants add further dimensions: liquidity state, risk-on/risk-off (correlation structure), funding/credit conditions, and dispersion.

**Why it matters:** the same strategy can have positive expectancy in one regime and negative in another. A trend-follower bleeds in chop; a mean-reverter blows up in a sustained trend. Detecting the regime *is* a large part of the alpha.

**Detection methods range from simple to sophisticated:**
- Simple: rolling moving averages, ADX (trend strength), VIX/realized-vol thresholds, range/breakout detectors
- Statistical: Hidden Markov Models (HMMs), Gaussian Mixture Models
- ML: random forests, Wasserstein k-means clustering, ensemble classifiers

Published research suggests regime-aware adaptation can improve risk-adjusted returns ~10–30% and reduce drawdowns by similar magnitudes — *with the caveat that those numbers come from sources with skin in the game, so we'll verify against academic sources in deeper steps.*

_Confidence: high on the concept and the basic axes; medium on the specific 10–30% improvement claim (single-source, vendor-adjacent)._
_Sources: [LuxAlgo — Market Regimes Explained](https://www.luxalgo.com/blog/market-regimes-explained-build-winning-trading-strategies/), [QuantStart — HMM Regime Detection](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/), [Macrosynergy — Classifying Market Regimes](https://macrosynergy.com/research/classifying-market-regimes/), [Medium / Coding Nexus — 3 Ways to Detect Regimes](https://medium.com/coding-nexus/3-effective-ways-to-detect-market-regimes-ec361712fbee)._

### Methodology ↔ Regime Mapping (Preview)

The first-pass "matrix" — to be deepened, source-checked, and tightened in Step 3:

| Regime | Strategies that tend to *work* | Strategies that tend to *fail* |
|---|---|---|
| Strong trend, quiet vol | Trend following, momentum | Mean reversion (gets run over) |
| Strong trend, volatile | Trend following with vol-scaled sizing, breakout | Naive mean reversion |
| Range, quiet | Mean reversion, market making, grid bots | Trend following (whipsaws) |
| Range, volatile | Mean reversion with wider bands, vol selling (advanced) | Trend following, breakout (false signals) |
| Transition / regime shift | Breakout strategies | Anything assuming the prior regime persists |
| Crisis / risk-off | Vol-aware defensive (cash, low-correlation assets), some trend strategies | Most mean reversion, factor longs |

**Combining trend-following + mean-reversion in one ensemble** is a well-documented technique: trend dominates in trends, mean-reversion picks up the slack in ranges, the combined equity curve is smoother than either alone. This is essentially what your bot architecture will be doing, just with `market_health` / `tactical_markets` as the regime classifier.

_Sources: [Algomatic — Why Two Strategies Are Better Than One](https://www.algomatictrading.com/post/why-two-strategies-are-better-than-one-trend-following-mean-reversion), [Quantified Strategies — Mean Reversion vs. Trend Following](https://www.quantifiedstrategies.com/mean-reversion-vs-trend-following/), [Bookmap — Momentum vs. Mean Reversion in Choppy Markets](https://bookmap.com/blog/momentum-vs-mean-reversion-which-dominates-in-a-choppy-market)._

### The Retail Bot Landscape (Where You'd Plug In)

As of 2026, the retail algorithmic-trading bot ecosystem clusters into three operational tiers:

1. **Exchange-native bots** — built into the exchange UI (Binance Grid/DCA, Coinbase Advanced). Lowest setup cost, lowest flexibility, limited to what the exchange offers.
2. **Third-party SaaS bots** — connect to broker/exchange APIs via restricted-permission keys (e.g., Coinrule, Trade Ideas, Stoic AI, 3Commas, BulkQuant). Visual strategy builders, marketplace strategies, subscription-priced.
3. **Code-it-yourself bots** — running locally or self-hosted, hitting REST/WebSocket APIs of brokers (IBKR, Alpaca, TastyTrade) or crypto exchanges. Full flexibility, full responsibility for infra, risk controls, and uptime. **This is the tier your project lives in.**

The 2026 landscape is increasingly AI-flavored on the marketing side, but the underlying methodologies are the same families above — wrapped in ML for either signal generation or regime detection. The honest caveat across all retail-facing bot marketing: "*bots running on outdated settings can rack up losses quickly, especially when users treat these tools as set-it-and-forget-it.*" Regime-adaptation is precisely the antidote.

_Sources: [QuantVPS — Top 20 Trading Bot Strategies for 2026](https://www.quantvps.com/blog/trading-bot-strategies), [StockBrokers — Best AI Trading Bots 2026](https://www.stockbrokers.com/guides/ai-stock-trading-bots), [Volity — Trading Bot Strategies 2026](https://volity.io/trading-platforms/binance-trading-bot-strategies-tools/)._

### Crypto vs. Traditional: What Translates, What Doesn't

Crypto inclusion matters because methodologies do **not** transfer 1:1:

| Dimension | Equities / Futures | Crypto |
|---|---|---|
| **Hours** | Fixed sessions; weekend gaps, overnight risk | 24/7/365; no forced exposure windows |
| **Efficiency** | High; alpha is hard | Lower; documented inefficiencies (VPIN ~0.45–0.47 vs. ~0.22 for E-mini S&P) |
| **Volatility** | Modest baseline; vol regimes matter | Persistently high; vol-scaling is mandatory |
| **Liquidity** | Centralized | Fragmented across hundreds of exchanges → cross-venue arbitrage |
| **Regulation** | Heavy (SEC/FINRA/CFTC) | Light, jurisdiction-dependent |
| **Data access** | Tiered, often paid, sometimes restrictive | Free public APIs, on-chain data, whale-tracking |
| **Microstructure** | Mature, well-studied | Younger; more information-asymmetric trading |

**Practical implications for our bot:**
- The same methodology families apply — but parameterization and risk controls differ.
- Crypto's higher VPIN means more *informed flow* — counterparty risk in your fills is higher.
- 24/7 means the bot needs to handle "always-on" infrastructure, not just market-hours.
- Cross-venue price differences are a real arbitrage opportunity (but execution risk and stablecoin risk are non-trivial).
- Funding rates (perpetual futures) are a unique carry opportunity not present in equities.

_Confidence: high on the qualitative differences; specific VPIN numbers are from a Cornell research paper and should be treated as illustrative, not load-bearing._
_Sources: [Cornell / Easley — Microstructure in Crypto Markets (SSRN)](https://stoye.economics.cornell.edu/docs/Easley_ssrn-4814346.pdf), [ChainUp — Crypto Algorithmic Trading](https://www.chainup.com/blog/crypto-algorithmic-trading-institutional/), [Wikipedia — Algorithmic Trading](https://en.wikipedia.org/wiki/Algorithmic_trading), [arXiv 2602.00776 — Explainable Patterns in Crypto Microstructure](https://arxiv.org/abs/2602.00776)._

### Cross-Domain Synthesis

Three observations connecting the above:

1. **The bot's core design decision is not "which strategy" but "how to switch."** Every family above has regimes where it makes money and regimes where it bleeds. The architectural question is: *what's the regime classifier, and how does it route capital?* That's exactly the role `market_health` and `tactical_markets` are positioned to fill.

2. **Ensemble beats single-strategy almost universally.** The trend-following + mean-reversion combination is the textbook example. Your bot should probably run multiple strategies in parallel, with regime-conditional position sizing (rather than a hard switch) as a smoother variant.

3. **The retail bot space is noisy on marketing but the underlying methodology set is small and stable.** Don't be intimidated by "AI-powered" branding — most of it is one or two of the families above with an ML wrapper. The differentiator for your bot is the *signal layer* you already have access to (the sibling tools), not novel methodology invention.

### Research Gaps to Address in Later Steps

- Deep-dive on each methodology family with specific implementations and parameter ranges (Step 3 — "competitive landscape" reframed as methodology deep-dives).
- Concrete regime-detection algorithms with code-level granularity and known failure modes.
- Backtesting infrastructure choices for a Python project (vectorbt, backtesting.py, lean/QuantConnect, custom).
- Broker / exchange selection: IBKR vs. Alpaca vs. TastyTrade for traditional; CEX vs. DEX for crypto.
- Risk management primitives in code: vol-targeting, Kelly-fractional sizing, correlation-aware portfolio limits.
- Regulatory specifics for a personal retail bot — PDT rule, wash-sale, tax treatment of bot trades.
- Empirical evidence triage for classical TA — what's reproducible, what isn't.

---

---

## Step 3 — Methodology Family Deep-Dives

Reframing the competitive landscape as detailed research on each trading methodology: mechanics, parameters, historical performance by regime, failure modes, and evidence quality.

### Trend-Following

**Core mechanics:** Buy when price is trending up, sell when trend weakens. Entry signals: 50-day MA > 200-day MA, or new N-day highs (e.g., 20-day breakout). Exit: MA crossover downside, ATR-based trailing stop (often 2 ATR), or time-based (e.g., 80 days with no stop).

**Backtest performance (1991–2024):** Long-only theoretical portfolio: 15.19% CAGR, 6.18% annualized alpha. Strong in trending markets; significant drawdowns in chop.

**Parameter ranges (empirically validated):**
- Entry MA pair: 50/200, 100/350 common
- Trailing stop: 1–2.5 ATR
- Exit time windows: 40–100 days
- Minimum trend confirmation: price above both MAs + slope positive

**Regime performance:**
- ✅ Strong trends (up or down): captures large moves, few whipsaws
- ✅ Risk-off drawdowns: often catches early trend reversals
- ❌ Choppy/range-bound: false signals, stopped out repeatedly
- ❌ Fast reversals: lags entries/exits

**Failure mode:** In choppy markets, generates many losing trades. CAGR degrades sharply if 1–2 extreme winners are missed. Drawdowns can exceed 30% in extended ranging markets.

**Evidence quality:** ★★★★☆ — Strongly supported by academic literature, institutional CTA usage, and robust backtests. The 2016 Philosophical Economics century-long backtest is authoritative.

_Sources: [QuantifiedStrategies — Trend Following](https://www.quantifiedstrategies.com/trend-following-trading-strategy/), [Quantpedia — Trend Following Effect](https://quantpedia.com/strategies/trend-following-effect-in-stocks), [Philosophical Economics — 100yr Trend Following](https://www.philosophicaleconomics.com/2016/01/movingaverage/), [arXiv 2412.14361 — Trend Following Backtest](https://arxiv.org/html/2412.14361v2)._

### Mean Reversion

**Core mechanics:** Identify assets deviating significantly from their mean, bet on reversion. Entry conditions: RSI < 30 or < 20, price outside Bollinger Bands (typically ±2 std devs), or spread Z-score > |2.0|. Exit: after modest favorable move (e.g., +1–3%), or time-based (e.g., 5–10 days).

**Key indicators:** Bollinger Bands (±2σ contains ~95% of normal price action), RSI (20/80 levels), Stochastic (20%/80%), MACD. Band width is critical: too tight = too many false entries; too wide = misses moves.

**Backtest performance:** High win rate (75–85%), but smaller average win vs. trend-follower. Sharpe ratios competitive; max drawdowns typically 15–25% (lower than trend-following).

**Parameter ranges:**
- Bollinger Band width: ±1.5–2.5 std devs
- RSI threshold: 25–35 (oversold), 65–75 (overbought)
- Hold period: 3–10 days
- Position size: 1–2% risk per trade

**Regime performance:**
- ✅ Range-bound / low-vol: exploits frequent bounces, high win rate
- ✅ Moderate trending: picks up pullbacks within trend
- ❌ Strong trending: gets run over; misses the big move
- ❌ Regime shifts: whipsawed at reversals

**Failure mode:** In sustained trends, mean-reversion positions bleed continuously. Win rate stays high but losing trades are deep. Often cuts winners short (exits at band retracement) and lets losers run (held hoping for revert that doesn't come).

**Evidence quality:** ★★★★☆ — Academic support strong; widely used by retail and small-cap funds. Parameters are regressing over time (less edge in 2020s) due to oversaturation.

_Sources: [QuantifiedStrategies — Mean Reversion](https://www.quantifiedstrategies.com/mean-reversion-trading-strategy/), [LuxAlgo — Mean Reversion](https://www.luxalgo.com/blog/mean-reversion-strategies-for-algorithmic-trading/), [TradeSearcher — Mean Reversion Guide](https://tradesearcher.ai/blog/mean-reversion-strategy-guide)._

### Momentum

**Core mechanics:** Buy assets that have outperformed recently; sell recent underperformers. Timeframe: typically 6–12 month lookback. Rotates aggressively across winners. Differs from trend-following: momentum is cross-sectional (rank assets against each other) vs. absolute (is it in an uptrend?).

**Entry:** Asset in top N percentile of recent returns (e.g., top 10%). Exit: rebalance monthly/quarterly, or when drops from top decile.

**Backtest performance vs. Trend-Following (2006–2025):** Similar CAGR but different return distributions. Trend-following: few huge winners, many small losses. Momentum: steady stream of smaller profits from rotation.

**Key advantage:** Less dependent on 1–2 extreme winners. If you miss one big trend, momentum still captures returns from broad outperformance rotation.

**Regime performance:**
- ✅ Bullish / broad strength: captures rotation dynamically
- ✅ Trending: benefits from continuation
- ❌ Risk-off / sector rotation reversals: lag on reversals
- ❌ Choppy / low-vol: rotation noise hurts

**Failure mode:** In sharp reversals (e.g., "flight to safety"), momentum positions caught on the wrong side. Recent winners become recent losers fast. Higher turnover = higher friction costs.

**Evidence quality:** ★★★★☆ — Strong academic foundation (Carhart 1997, Asness 2012). Factor-based funds use it institutionally. Some debate on whether it persists post-publication.

_Sources: [NeuroQuant — Momentum vs Trend Following](https://en.neuroquant.ai/en/momentum-vs-trend-following-two-paths-to-returns/), [TwoSigma — Momentum & Trend Following](https://www.venn.twosigma.com/insights/momentum-and-trend-following), [Nasdaq — Momentum vs Trend Following](https://www.nasdaq.com/articles/4-differences-between-momentum-trading-and-trend-following-strategies), [QuantifiedStrategies — Meb Faber's Momentum](https://www.quantifiedstrategies.com/meb-faber-momentum-trend-following-strategy/)._

### Statistical Arbitrage / Pairs Trading

**Core mechanics:** Identify two cointegrated assets (historically move together). Construct spread. When spread deviates from mean, bet it reverts. Reduce market-neutral (long one, short the other).

**Pair selection:** Correlation ≥ 0.80 (very restrictive), cointegration test (ADF), or ML clustering (PCA, Gaussian Mixture).

**Backtest performance:** Excess return ~38–118 bp/month (after risk adjustment, lower bound ~38 bp/month). Sharpe ratios strong (often 1.5–2.0+) but deteriorating post-2010.

**Parameter ranges:**
- Z-score entry: spread deviates |2.0|–|3.0| std devs
- Hold period: 10–30 days
- Rebalance: daily or intraday for high-frequency variants

**Regime performance:**
- ✅ Normal / low-vol: spread reverts reliably
- ✅ Trend without correlation breakdown: captures both positions' moves offset
- ❌ Stress / correlation spikes: pairs diverge, losses stack
- ❌ Sector rotation / regime change: cointegration breaks

**Failure mode:** During crises, correlations spike to 1.0 — both legs tank simultaneously. Pairs that worked for years suddenly decouple. Requires tight risk controls (absolute position limits, not just spread limits).

**Evidence quality:** ★★★☆☆ — Strong academic foundation (Gatev 1999, Stanford papers), but decay evident. Edge significantly reduced since 2010. Institutional shops still use; requires careful regime monitoring.

_Sources: [Wharton / Gatev — Pairs Trading](http://stat.wharton.upenn.edu/~steele/Courses/434/434Context/PairsTrading/PairsTradingGGR.pdf), [Stanford / Papanicolaou — Risk Control in StatArb](http://math.stanford.edu/~papanico/pubftp/RDA_manuscript.pdf), [QuantInsti — StatArb in Indian Markets](https://blog.quantinsti.com/epat-project-mean-reversion-statistical-arbitrage-pair-trading-strategy-indian-market-sectors/), [Yale / Zhu — Pairs Trading Profitability](https://economics.yale.edu/sites/default/files/2024-05/Zhu_Pairs_Trading.pdf)._

### Breakout

**Core mechanics:** Price breaks through support/resistance with volume confirmation (typically 50%+ above 20-day vol avg). Enter on breakout, hold or scale out. Market-regime transitional play.

**Entry:** Close above resistance with volume surge, or new N-period high (10–20 days). Exit: profit target above breakout, or stop below original level if false breakout.

**Regime performance:**
- ✅ Volatile range-bound: exploits breakout entry on range exit
- ✅ Trending: validates trend entries with breakout confirmation
- ✅ Regime transitions: captures pivot points
- ❌ Choppy intraday: false breakouts whipsaw
- ❌ Low-liquidity times: volume spike insufficient, fades back in

**Failure mode:** False breakout (whipsaw): price breaks resistance, volume tails, then reverses sharply. Often due to algorithm stop-hunts or news reversals. Volume confirmation critical — breakouts on low vol fail 50%+ of time.

**Evidence quality:** ★★★☆☆ — Widely used by retail and discretionary traders. Backtests available, but cherry-picked for breakout-heavy regimes. Less evidence of edge than trend/reversion. Highly dependent on entry filters (volume, volatility regime).

_Sources: [ForexTester — Breakout Trading](https://forextester.com/blog/breakout-trading-strategy/), [IG International — Breakout Strategies](https://www.ig.com/en/trading-strategies/what-is-a-breakout-trading-strategy-and-how-do-you-trade-with-it-230619), [LuxAlgo — Breakout Trading](https://www.luxalgo.com/blog/breakout-trading-with-support-and-resistance/), [Capital.com — Breakout Types](https://capital.com/en-int/learn/trading-strategies/breakout-trading)._

### Classical Technical Analysis / Chart Patterns

**Core mechanics:** Head-and-shoulders, double tops, triangles, flags, wedges, etc. Signal reversals or continuations based on historical pattern shape.

**Entry:** Pattern completion + breakout. Exit: pattern target or fixed risk stop.

**Backtest performance:** Highly variable. Some patterns (e.g., ascending triangles in uptrends) show edge; others (e.g., head-and-shoulders) are contested. Published backtests often show 55–60% win rates, but live edge is questionable post-publication.

**Regime performance:**
- ✅ High-vol regime changes: pattern completion can presage sharp moves
- ✅ Trending: continuation patterns (flag, pennant) useful
- ❌ Choppy: patterns form and break spuriously, whipsaws common
- ❌ Algorithmic / modern markets: patterns crowded, front-run by algos

**Failure mode:** Patterns are pattern-seeking bias — the human eye finds shapes in noise. Some patterns work in backtests due to survivorship bias and curve-fitting. Live performance degrades over time as retail traders (who follow patterns) become predictable to algos.

**Evidence quality:** ★★☆☆☆ — Mixed. Some specific patterns (e.g., 200-day MA support) empirically valid. Most classical chart patterns lack rigorous academic support. Practitioner community swears by them; academic finance largely dismisses them. Worth including in research, but require empirical validation before use.

_Cited implicitly in earlier trend-following and breakout sources; classical TA is difficult to source empirically — most published backtests are motivated reasoning._

### Carry (FX, Funding Rates)

**Core mechanics:** Earn the interest rate differential (or funding rate in crypto) by holding a position. Works best when rate differential is positive and stable.

**Example:** If USD 3mo SOFR is 5% and JPY is 0%, go long USD/JPY and earn the spread daily/quarterly. In crypto, perpetual futures funding rates provide explicit carry (paid by longs if positive, by shorts if negative).

**Performance:** Highly dependent on volatility and correlation breakdown. Works in stable regimes; fails in sharp reversals (position is often long low-vol, short high-vol, opposite of what you want in stress).

**Regime performance:**
- ✅ Low-vol / stable rates: pure carry extraction
- ❌ Risk-off: correlations reverse, carry unwinds violently
- ❌ Central bank regime change: interest differential reverses

**Evidence quality:** ★★★★☆ — Strong academic foundation (Fama 1984, modern crypto papers). Institutional standard. Simple and effective when regime is stable.

---

## Part 2 — Adaptability & Parameterization (Making Each a "Swiss Army Knife")

For the bot to be truly multi-faceted and route between strategies intelligently, each methodology needs to be parameterized — tunable knobs that adapt to market conditions and upstream signals. Below: how to make each family flexible.

### Trend-Following — Adaptive Parameters

**MA Period Adaptation:** Instead of fixed 50/200 pair, scale periods by ADX (average directional index, 14-period):
- ADX < 20 (weak trend): longer MAs (100/350) to reduce whipsaws
- ADX 20–40 (moderate trend): standard 50/200
- ADX > 40 (strong trend): shorter MAs (20/50) to catch the move earlier

**Regime Filters (Self-Detection):**
- Use a Regime Dashboard (ADX + ATR ratio + Bollinger Band width + volume):
  - Trending: ADX > 25, ATR expanding, BB width > recent median
  - Ranging: ADX < 20, ATR contracting, BB width compressed
  - Volatile: ATR spike > 2x baseline, regardless of ADX
- Only **enable** trend-following in confirmed trending regime; else reduce position size by 50–75%

**Exit Adaptation:**
- ATR multiplier for trailing stop: scale by recent vol. High vol (VIX > 20): use 2.5 ATR. Low vol (VIX < 15): use 1.5 ATR.
- Time-based exit windows: 40 days in choppy regimes (cut losers faster), 100+ days in strong trends

**Integration with Upstream Signals:**
- If `tactical_markets` flags "sector trending," activate trend-following on that sector with shorter MA periods.
- If `market_dashboard` composite stress is > 60 (stressed), reduce position size 50% but keep strategy active (good for downtrends).

_Sources: [Medium — Adaptive Moving Average Strategies](https://medium.com/@FMZQuant/adaptive-moving-average-crossover-volatility-tracking-quantitative-trading-strategy-62e2ac559181), [PyQuantLab — Regime-Filtered Trend](https://pyquantlab.medium.com/regime-filtered-trend-strategy-a-market-adaptive-trend-following-system-fa933e001237), [TradeSpider — Backtesting Configurations](https://trendspider.com/learning-center/backtesting-trading-strategy-configuration-examples/)._

### Mean Reversion — Dynamic Bands & Volatility Adjustment

**Bollinger Band Width Tuning:**
- Default 20-period, ±2σ works across most instruments
- Liquid large-cap (SPY, BTC): BBW < 4% triggers entry
- Volatile small-cap or crypto: BBW < 6–10% (adjust to 20-day median BBW as reference)
- High-vol regimes: widen bands to 2.5–3.0σ; low-vol regimes: narrow to 1.5–2.0σ

**ATR-Based Stop-Loss & Take-Profit:**
- Instead of fixed %, adjust stops dynamically: 1.5 ATR below entry for stop, 1.0 ATR above entry for target in quiet markets; 2.5 ATR for stop, 1.5 ATR for target in volatile markets
- Reduces whipsaws on false reversal signals

**RSI / Stochastic Thresholds:**
- Oversold RSI typically 30; in high-vol regimes, use 25. In low-vol, use 35.
- Combine RSI + Bollinger Band — entry only when **both** oversold (avoids early entries on just one signal)

**Trend Filter (Reduce False Signals):**
- Don't trade mean-reversion against strong trends. Use 200-day MA as regime: only if price within 5% of 200MA or below it, activate mean-reversion. Else reduce size or disable.

**Integration with Upstream Signals:**
- If `market_dashboard` shows equity_volatility bucket high, widen Bollinger Bands and increase ATR stops.
- If `tactical_markets` shows sector oversold (vs. macro context), target mean-reversion specifically in that sector.

_Sources: [FMZQuant — Bollinger Bands Mean Reversion](https://medium.com/@FMZQuant/the-bollinger-bands-mean-reversion-strategy-d2ad8222cd3d), [Atlantis Press — Band Width Analysis](https://www.atlantis-press.com/article/125991306.pdf), [Volatility Box — Bollinger Band Volatility](https://volatilitybox.com/research/bollinger-bands-volatility/)._

### Momentum — Ranking & Rebalance Tuning

**Lookback Period Adaptation:**
- Bull markets (VIX < 15): 6-month lookback (capture mega trends)
- Normal markets: 3-month lookback (standard rotation speed)
- Stressed markets (VIX > 25): 1-month lookback (faster rotation, avoid value traps)

**Rebalance Frequency:**
- Slow regime (low vol, stable trends): monthly rebalance
- Normal: bi-weekly (2x/month)
- Fast/choppy: weekly rebalance

**Concentration vs. Diversification:**
- Top 10 assets by momentum in normal regimes
- Top 20 in choppy regimes (reduce concentration risk)
- Equal-weight within rank decile in crisis mode (no mega-concentrations)

**Integration with Upstream Signals:**
- If `tactical_markets` flags "sector rotation," use momentum within that sector (rank subsectors, not all assets).
- If `market_dashboard` risk-on/risk-off signal changes, trigger immediate rebalance (don't wait for scheduled month-end).

### Grid Trading / DCA — Width & Rebalance Strategy

**Grid Parameters:**
- Grid number: determines frequency of trades and profit per trade
  - Tight grids (e.g., 100 grids, 1% apart): high frequency, small per-trade profit. Good for low-vol, mean-reversion like behavior.
  - Wide grids (e.g., 20 grids, 5% apart): fewer trades, larger per-trade profit. Good for volatile ranges.
- Choose based on volatility: high vol (ATR > 2x median) → wide grids. Low vol → tight grids.

**Capital Allocation per Grid:**
- For N grids across total capital C: allocate C / (2N) per grid (accounts for both buys and sells).
- Rebalance dynamically: if price drifts above grid midpoint, shift grid boundaries higher.

**DCA (Dollar-Cost Averaging) Variant:**
- Grid's sibling. Places buy orders periodically (e.g., every 1% drop) and single take-profit at a target above cost basis.
- Good for accumulation phases (bull market, long-term hold).
- Combine with grid: buy on grid lows (DCA style), sell on grid highs (grid style).

**Integration with Upstream Signals:**
- If `market_dashboard` flags "range-bound low-vol," activate grid. Disable or reduce when trending (grid bleeds in strong directional moves).
- If `tactical_markets` identifies a "support level," center the grid around it.

_Sources: [Medium — DCA vs Grid Trading](https://medium.com/@alsgladkikh/comparing-strategies-dca-vs-grid-trading-2724fa809576), [TradeSanta — Grid vs DCA](https://tradesanta.com/grid-vs-dca), [Wundertrading — Best Grid Settings](https://wundertrading.com/journal/en/learn/article/best-grid-bot-settings), [Gainium — Combo Bots](https://gainium.io/combo-bot)._

### Carry Strategies (FX, Crypto Funding Rates)

**Crypto Funding Rate Arbitrage (Market-Neutral):**
- Mechanics: buy spot asset (e.g., BTC), short equivalent notional in perpetual futures. Collect funding payment every 4 or 8 hours.
- Entry condition: funding rate > 0.01% per period (threshold varies by market; Binance averages 0.015% / 8-hour period).
- Expected return: 0.015% × (365 / 3) periods ≈ 18% annualized at "normal" funding rates.
- Risk: funding rates flip (go negative), execution slippage, exchange counterparty risk.

**Parameter Tuning:**
- Minimum funding rate threshold: set based on slippage + operational cost. If slippage is 0.02%, require funding > 0.025% to be profitable.
- Correlation monitoring: if spot and perp become correlated (normal market) vs. diverging (stress), adjust position sizing.
- Rebalance frequency: daily (funding paid every 4–8 hours; capture all periods).

**Cross-Exchange Funding Arbitrage:**
- If BTC perps on Exchange A have funding +0.05%, and Exchange B have +0.01%, short A, long B, collect 0.04% spread.
- Requires two accounts, good execution infrastructure, and low latency.

**Integration with Upstream Signals:**
- If `market_dashboard` shows risk-off (composite > 70), turn down carry position size (funding rates about to spike/reverse).
- If `tactical_markets` shows macro stress, disable carry (correlations break down in crises).

_Sources: [CoinGlass — Funding Rate Arbitrage](https://www.coinglass.com/learn/what-is-funding-rate-arbitrage), [ScienceDirect — CEX/DEX Funding Rate Study](https://www.sciencedirect.com/science/article/pii/S2096720925000818), [OUINEX — Funding Arbitrage Guide](https://ouinex.com/en/education/funding-rate-arbitrage-cashing-in-on-perpetual-swings), [Wharton — Perpetual Futures Pricing](https://finance.wharton.upenn.edu/~jermann/AHJ-main-10.pdf)._

### Statistical Arbitrage / Pairs — Correlation Monitoring & Dynamic Spreads

**Pair Selection & Maintenance:**
- Identify cointegrated pairs (correlation > 0.80, ADF test for mean-reversion).
- Monitor cointegration monthly: if correlation drops below 0.70 or ADF p-value > 0.10, retire the pair (relationship breaking down).
- Rotate pairs seasonally (Q1, Q2, Q3, Q4) to stay ahead of structural changes.

**Spread Z-Score Entry/Exit:**
- Entry: spread Z-score |2.0|–|3.0| std devs from mean (tighter in stable regimes, looser in volatile regimes).
- Exit: spread closes within 0.5 std devs of mean, or time-based (30 days max).
- Dynamic threshold: adjust based on recent vol. High vol (ATR > 1.5x) → require |2.5| Z-score entry (avoid false signals).

**Regime-Aware Sizing:**
- Normal markets: standard position size.
- Trending markets: reduce size 50% (correlation breakdown likely).
- Crisis mode (VIX > 30): disable pairs (correlations spike to 1.0, both legs blow up).

**Integration with Upstream Signals:**
- If `market_dashboard` shows correlation regime change (bucket for "correlation breakdown"), flag pairs for audit or disable.
- If `tactical_markets` shows sector divergence, look for pairs trades within *uncorrelated* sectors (bet on divergence rather than correlation).

---

## Part 3 — Multi-Strategy Orchestration & Risk Control

Running 5–7 strategies simultaneously is powerful but dangerous. This section covers how to run them together safely.

### Position Sizing & Capital Allocation

**Per-Strategy Capital Limit:**
- Allocate capital by strategy: e.g., 20% trend-following, 20% mean-reversion, 15% momentum, 15% grid, 15% carry, 15% stat-arb.
- Cap individual position size: 2–5% of per-strategy capital per trade (e.g., if trend-following gets $20k, max 2% = $400 per trade).
- Prevents any single position from blowing up the portfolio.

**Dynamic Reallocation (Meta-Level):**
- Measure each strategy's recent Sharpe ratio (3–4 week rolling window).
- Shift capital from underperforming to outperforming strategies monthly.
- E.g., if mean-reversion is winning, reallocate from momentum to mean-reversion for the next month.

### Correlation & Exposure Limits

**Cross-Strategy Correlation Monitoring:**
- Track correlation between strategy returns day-to-day.
- If two strategies become > 0.70 correlated, reduce the smaller one's capital allocation 50% (redundant risk).
- Example: trend-following and momentum both thrive in bull markets; if correlation spikes, reduce momentum.

**Sector / Asset Concentration:**
- No sector > 40% of portfolio. If trend-following is long tech and momentum is also top-weighted tech, breach limit.
- Mechanism: track net long exposure per sector; rebalance if any single sector exceeds threshold.

**Net Directional Exposure:**
- Keep net long/short roughly balanced (e.g., ±10% over neutral).
- Prevents the portfolio from becoming a hidden directional bet (e.g., all strategies long in a bull market).

### Drawdown Control

**Maximum Drawdown Limit (Hard Stop):**
- Set portfolio-level max drawdown: e.g., 20% from all-time high.
- If drawdown hits 20%, pause all new entries (but don't force-liquidate existing positions). Resume when drawdown narrows below 15%.

**Conditional Drawdown at Risk (CDaR):**
- Advanced metric: average of worst 10% of drawdowns.
- If CDaR > 15%, reduce all position sizes 25%.

**Per-Strategy Drawdown Tracking:**
- If a single strategy hits > 25% drawdown (e.g., mean-reversion in extended trends), reduce its capital allocation 50% for 2 weeks, then reassess.

### Meta-Router: Which Strategy Runs When?

**Upstream Signal Routing:**

| Signal from Upstream Tools | Primary Strategy | Secondary | Tertiary |
|---|---|---|---|
| `market_health`: trending, low-vol | Trend-following (full size) | Momentum | Grid (reduce) |
| `market_health`: trending, high-vol | Trend-following (vol-scaled) | Momentum | Mean-reversion (reduce) |
| `market_health`: ranging, low-vol | Mean-reversion (full) | Grid | Trend-following (off) |
| `market_health`: ranging, high-vol | Grid (wide bands) | Mean-reversion (wide) | Trend-following (off) |
| `tactical_markets`: sector hot | Momentum (within sector) | Trend-following (sector-filtered) | - |
| `market_health`: risk-off (composite > 70) | Carry (reduce/off) | Pairs (reduce/off) | Trend-short (activate) |

**Internal Regime Detection Routing:**

Each strategy detects its own sweet spot. A meta-router (e.g., simple scoring system) decides:
- Strategy gets "green light" (100% capital): regime is optimal
- Strategy gets "yellow light" (50% capital): regime is neutral
- Strategy gets "red light" (0% capital): regime is adverse

Example scoring (trend-following):
```
score = 0
if ADX > 25: score += 40
if price > 200-day MA: score += 30
if ATR expanding: score += 20
if (price < lower BB): score += 10
if score >= 80: GREEN (100% capital)
elif score >= 50: YELLOW (50%)
else: RED (off)
```

_Sources: [CFA Institute — Drawdown Optimization](https://blogs.cfainstitute.org/investor/2013/02/12/sculpting-investment-portfolios-maximum-drawdown-and-optimal-portfolio-strategy/), [Tradetron — 7 Risk Techniques](https://tradetron.tech/blog/reducing-drawdown-7-risk-management-techniques-for-algo-traders), [QuantInsti — Risk-Constrained Kelly](https://blog.quantinsti.com/risk-constrained-kelly-criterion/), [Macrosynergy — Drawdown Control](https://macrosynergy.com/research/drawdown-control/)._

---

## Part 8 — Implementation & Infrastructure Landscape (Step 4)

### Backtesting Frameworks Deep-Dive

**The Choice Matrix:**

| Framework | Speed | Live Trading | Ease of Use | Production-Ready | Best For |
|---|---|---|---|---|---|
| **VectorBT** | ★★★★★ (1000x faster) | ❌ No | Medium | ❌ Research only | Bulk strategy testing, optimization, systematic research |
| **Backtrader** | ★★★ (slow) | ✅ Yes (via live brokers) | ★★★★ (Pythonic) | ✅ Yes | From-idea-to-live trading, swing traders, detailed broker models |
| **backtesting.py** | ★★★ | ❌ No | ★★★★★ (simplest) | ❌ Research only | Quick prototyping, learning, lightweight research |
| **QuantConnect (Lean)** | ★★★★ (cloud) | ✅ Yes (full ecosystem) | ★★★ (steep learning) | ★★★★★ (institutional) | Production bots, multi-asset, institutional scale |
| **Zipline** | ★★ (slow, unmaintained) | ❌ No | Medium | ❌ Legacy | Academic research only; **avoid for new projects** |

**Detailed Breakdown:**

**VectorBT (★★★★★ for research, ❌ for production)**
- **Speed:** Fully vectorized, Numba-compiled. Can run 1,000s of strategy instances in seconds.
- **Architecture:** NumPy/Pandas-based. No event loop, pure array operations.
- **Live Trading:** None. Pure backtesting.
- **Free vs. Paid:** Free version is maintained but no longer actively developed. VectorBT Pro (paid) has intraday backtesting, Monte Carlo, and bleeding-edge features.
- **Best Use:** Systematic traders testing 100s of parameter combinations rapidly. Quant researchers optimizing factor models.
- **Pitfall:** Vectorized approach means you don't see individual order execution flow — good for strategy discovery, bad for debugging order logic.

**Backtrader (★★★★ for production, ★★★ for speed)**
- **Speed:** Event-driven (slower than VectorBT, ~10–100x slower). But execution flow is transparent.
- **Architecture:** Object-oriented. You define broker, data feed, strategy as classes. Closer to real trading flow.
- **Live Trading:** Yes. Connects to real brokers (Interactive Brokers, Alpaca, Oanda, CCXTfor crypto). Same code runs backtest + live.
- **Broker Realism:** Models slippage, commissions, margin, order fills realistically. Excellent for swing traders.
- **Best Use:** From-idea-to-execution. You can backtest locally, then flip a flag and run live against Alpaca (or IBKR).
- **Learning Curve:** Moderate. Pythonic, good docs, but setup can feel boilerplate-heavy.

**backtesting.py (★★★★★ for learning, ❌ for serious work)**
- **Simplicity:** Minimal, elegant API. ~150 lines to get a working strategy backtest.
- **Live Trading:** None.
- **Best Use:** Prototyping, teaching, lightweight research. Not production-worthy.

**QuantConnect / LEAN (★★★★★ for production, ★★★ for ease)**
- **Ecosystem:** Cloud-first. Backtest, research notebooks, live trading, data feeds, all integrated.
- **Data:** Built-in historical data for 200k+ assets (stocks, futures, crypto, forex).
- **Live Brokers:** Alpaca, Interactive Brokers, Bybit (crypto), and others.
- **Scalability:** Institutional-grade. Used by hedge funds.
- **Steep Learning:** LEAN engine is C#-based; Python API is thorough but verbose.
- **Cost:** Free tier (limited backtests/data), paid tiers ($99–$999/mo) for production.
- **Best Use:** Institutional bots, multi-asset strategies, when you need bulletproof infrastructure.

**Recommendation for Your Bot:**

**Go with Backtrader + Alpaca API directly.**

Why:
1. You're already using Alpaca paper trading → Backtrader connects natively
2. **Code reuse:** same Python script backtests locally, then runs live against Alpaca (just flip a flag)
3. Production-ready. Slower than VectorBT, but transparent order execution (you can debug what's happening)
4. No subscription costs (Alpaca is free, Backtrader is open-source)
5. Broker realism → you'll catch slippage/fill issues in backtest before they bite live

**Architecture Suggestion:**
- Use **VectorBT for rapid strategy optimization** (find good parameter ranges in bulk)
- Export top candidates to **Backtrader for detailed backtesting + live paper trading**
- Move to live trading when you're confident

_Sources: [Medium — Battle-Tested Backtesters](https://medium.com/@trading.dude/battle-tested-backtesters-comparing-vectorbt-zipline-and-backtrader-for-financial-strategy-dee33d33a9e0), [Medium — Popular Backtesting Tools](https://medium.com/@pta.forwork/popular-backtesting-tools-for-algorithmic-trading-a-practical-comparison-and-how-to-use-them-fa09f9fb2480), [QuantVPS — Best Python Backtesting Libraries](https://www.quantvps.com/blog/best-python-backtesting-libraries-for-trading), [AutoTradelab — Framework Comparison](https://autotradelab.com/blog/backtrader-vs-nautilusttrader-vs-vectorbt-vs-zipline-reloaded), [GitHub — backtesting.py alternatives](https://github.com/kernc/backtesting.py/blob/master/doc/alternatives.md)._

---

### Alpaca API: Durability & Production Considerations

**The Good (Why You're Using It):**
- **Zero commission trading** (stocks, options, crypto). Revenue via PFOF (payment for order flow) and margin interest, not you paying fees.
- **Paper trading is free and unlimited** (test without risk)
- **Live trading fills are fast and tight** — Alpaca's executions are timely with minimal "drift" (order price ≈ execution price)
- **No minimum account balance** (unlike traditional brokers' $25k PDT requirement — though PDT is being eliminated June 4, 2026)

**The Gotchas (Production Risk):**
- **Intermittent outages & message delays** (most common complaint). Users report sporadic connectivity issues, delayed market data feeds, and execution delays during market stress.
- **Not institutional-grade** — Alpaca is retail-focused. For high-frequency or large notional strategies, IBKR or a prop firm is more reliable.
- **Margin requirements:** 50% for marginable securities, 100% for non-marginable (per Reg T).
- **Pattern day trader designation still applies until June 4, 2026** (4+ day trades in 5 business days requires $25k minimum). After June 4, PDT eliminated entirely.

**Reliability Verdict:**
- **Paper trading:** Excellent. Use it heavily to stress-test your logic.
- **Live trading (small account < $50k):** Good enough. Occasional hiccups, but recoverable.
- **Live trading (large account / critical strategy):** Risky. You'll want a secondary broker (IBKR as backup) or accept slippage/outage risk.

**What We Recommend for "Sturdy & Reliable":**

**Primary: Alpaca (paper + live on small capital)**
- Use Alpaca for development, testing, and small live trades
- **Secondary failsafe: Interactive Brokers (IBKR) API** as a backup. IBKR is institutional-grade, more reliable, but has $10 minimum commission (kills small trades). Use IBKR as a fallback if Alpaca is down.

**Alternative for Crypto:** If trading crypto, consider running dual Alpaca + Deribit (crypto) or Alpaca + Bybit (perpetuals). Crypto venues are more reliable than equity brokers for 24/7 trading (no single point of failure like market close).

_Sources: [Alpaca API Docs — Paper Trading](https://docs.alpaca.markets/docs/paper-trading), [SmartAsset — Alpaca 2026 Review](https://smartasset.com/investing/alpaca-trading), [BrokerChooser — Alpaca Review](https://brokerchooser.com/broker-reviews/alpaca-trading-review), [TradersUnited — Alpaca Safety](https://tradersunited.org/blog/alpaca-trading-api-review-safe-or-not)._

---

### Deployment Patterns: Local vs. VPS vs. Cloud

**Three Options for Running Your Bot:**

**Option A: Local Machine (Your Laptop/Desktop)**
- **Pros:** Simple, no infrastructure costs, easy debugging (everything on your machine)
- **Cons:** Must be on 24/7. Internet outage = bot stops. Unreliable for production.
- **Best for:** Development, paper trading, testing. NOT production.

**Option B: VPS (Virtual Private Server)**
- **Setup:** Rent a server from a provider (Linode, DigitalOcean, AWS EC2, or trading-specialized: ForexVPS, TradingVPS)
- **Cost:** $5–50/mo (generic cloud), $20–100/mo (trading-specialized for low latency)
- **Reliability:** Server runs 24/7 independent of your internet. Much more stable than local.
- **Latency:** Generic cloud (AWS in us-east-1) is ~50–100ms to broker. Trading-specialized VPS co-located near broker data centers: 1–10ms (matters for high-frequency, not for swing trading).
- **Pain Points:** 
  - Must manage OS, dependencies, logs, restarts yourself
  - Common failure: RAM runout at market spike (logging + data accumulation)
  - Network misconfiguration → silent failures
- **Best for:** Production swing/trend bots, small capital. Cost-effective (your main ongoing cost is VPS rental).

**Option C: Cloud (AWS, GCP, Azure) + Container (Docker)**
- **Setup:** Docker container running your bot on a cloud instance (ECS, Cloud Run, etc)
- **Cost:** $10–50/mo (small instance) or pay-per-use
- **Reliability:** High. Cloud providers handle OS updates, scaling, monitoring. You focus on bot code.
- **Ops Burden:** Moderate. Need to write Dockerfile, set up CI/CD, configure logging/monitoring.
- **Best for:** Institutional scale, multi-strategy, when you want ops handled by a cloud provider.

**Recommendation for You:**

**Start with: VPS (generic cloud like AWS/DigitalOcean) + Docker**

Why:
- Reliable enough for retail/small prop trading
- Lower cost than institutional cloud ($10–20/mo)
- Container isolates your bot from OS drift (same code anywhere)
- Easy to version/test changes (rebuild container, deploy)
- Scalable if you add more strategies later

**Concrete Setup:**
1. Rent a small Linux instance (2vCPU, 4GB RAM) on DigitalOcean or AWS (~$10–15/mo)
2. Docker container with your Backtrader + Alpaca bot
3. Supervisord or systemd to restart bot if it crashes
4. Log all trades to a file + send alerts (email/Pushover) on errors
5. Cron job to restart bot at market open, stop at market close (or run 24/7 for crypto)

_Sources: [TradingFXVPS — VPS for Trading Bots](https://tradingfxvps.com/building-trading-bots-for-vps-development-deployment/), [ForexVPS — Best VPS for Algo Trading](https://www.forexvps.net/resources/best-vps-for-algo-trading-bots/), [AlgoTrading101 — Algo Trading on Cloud](https://algotrading101.com/learn/algo-trading-deployment-google-cloud-platform/), [QuantVPS — Best VPS for Algo Trading](https://www.quantvps.com/blog/best-vps-algorithmic-trading)._

---

### Regulatory & Tax: PDT, Wash-Sale, Bot Trading

**Pattern Day Trader (PDT) Rule — Major Change June 4, 2026**

As of June 4, 2026, FINRA is **eliminating the PDT rule entirely**. This was a 24-year-old regulation that required $25k minimum equity in a margin account if you made 4+ day trades in a 5-business-day window.

**What this means:**
- After June 4, 2026: Day trade unlimited with any account size (no $25k minimum)
- Before June 4, 2026: If you're in a margin account with < $25k and make 4+ day trades in 5 days, you get "PDT restricted" for 90 days
- **Cash accounts (no margin):** PDT didn't apply anyway, but limited to 3 day trades per 5 days

**For Your Bot:** If your bot makes daily trades (which it will), you'll be fine post-June 4. Pre-June 4, use a cash account or keep account equity > $25k if using margin.

**Wash-Sale Rule — Still in Effect (Critical)**

The wash-sale rule (IRC §1091) is **NOT eliminated**. Here's what it means for bot trading:

- **Rule:** If you sell a security at a loss, you cannot claim the loss if you buy a "substantially identical" security within 30 days *before* or *after* the sale (61-day window total).
- **Bot Risk:** A bot that trades the same ticker 100 times per day can rack up dozens of wash-sale violations without knowing.
- **Tax Consequence:** IRS disallows the loss deduction (increases your tax liability) + potential penalties.

**Example (Bad):**
- Day 1: Bot buys SPY at $450, sells at $440 (loss $10) → loss disallowed, loss "added" to cost basis of next SPY purchase
- Days 2–30: Bot keeps buying/selling SPY (each buy/sell potentially involves wash-sale)
- Result: Your losses are deferred or disappear; tax bill is higher than expected

**Mitigations:**
1. **Track wash-sales in real-time** — log every trade, flag if you sell at a loss then buy the same asset within 61 days
2. **Alternate similar assets** — if strategy shorted SPY at a loss, buy QQQ instead of SPY within 61 days (not "substantially identical")
3. **Futures bypass wash-sale** — futures have no wash-sale rule, no need to report every trade. If your bot trades crypto/commodities, futures are cleaner tax-wise.
4. **Hire a CPA** — for a bot making 100+ trades/year, outsource wash-sale tracking to a professional. Cost: $500–2000, worth it to avoid IRS audit.

**Short-Term Capital Gains Tax (Still High)**
- Bot trades are almost always held < 1 year → taxed as **ordinary income** (up to 37% federal + FICA + state)
- Long-term capital gains (> 1 year) → 0–20% federal (much better)
- **Implication:** If your bot makes $50k in profit (100 trades × $500 avg), expect $15–20k in federal tax alone

**Tax-Smart Bot Architecture:**
- Run bot trades in a **business account** (S-Corp or LLC) if you're serious → business income, potential deductions
- Or run bot on **long-term hold positions** (buy, bot takes over, sell after 1+ year) → capital gains treatment
- Or **target lower-frequency strategies** (fewer trades, higher conviction) → less wash-sale friction

_Sources: [Angel Investors Network — PDT Elimination](https://angelinvestorsnetwork.com/regulatory-compliance/pattern-day-trader-rule-eliminated-sec-2026-implications), [Alpaca Support — PDT Rule](https://alpaca.markets/support/what-is-the-pattern-day-trading-pdt-rule), [Terms.Law — Wash Sale Algo Trading](https://terms.law/Trading-Legal/guides/wash-sale-algo-trading.html), [Charles Schwab — Year-End Tax Trading](https://www.schwab.com/learn/story/year-end-tax-trading-wash-sales-and-more)._

---

### Monitoring, Logging & Risk Controls (Live Bot Ops)

**What to Log:**
- Every order submitted: timestamp, ticker, qty, price (limit vs. market)
- Every fill: actual execution price, qty filled, slippage (limit price - execution price)
- Every error: exception type, strategy name, recovery action
- Portfolio state: cash, positions, NAV, daily P&L (every hour or end of day)
- Regime signal values: incoming composite stress score, sector rotation, volatility estimate

**Why:** When something goes wrong (bot dies, fills are bad, unexpected loss), logs are your only window into what happened. Without logs, you're flying blind.

**Watchdog Process (Restart on Crash):**
On Linux/Mac:
- Use **supervisord** or **systemd** to monitor your bot process
- If bot exits (crash, OOM, exception), watchdog restarts it automatically
- Set `autostart=true` so bot starts when the VPS boots

On Windows:
- Task Scheduler to restart bot on exit
- Or Windows Service wrapper

**Kill Switches (Emergency Stop):**
Your bot should have **multiple kill mechanisms:**
1. **Time-based:** Bot stops trading at 3:55 PM ET (or 4:00 PM market close). Prevents overnight position leakage.
2. **Loss-based:** If daily loss exceeds -2% of account, bot stops all new trades (preserve remaining capital).
3. **Volatility-based:** If VIX spikes > 40 or market breadth collapses, bot reduces position size 75% or stops entirely.
4. **Manual:** You can send a signal (e.g., environment variable flip, webhook call) to kill the bot remotely.

**Alerting:**
Set up alerts for critical events:
- Bot process died (restart failed)
- Daily loss exceeded threshold
- Order fill at terrible slippage (limit was $100, filled at $110)
- No heartbeat from bot in X minutes (bot may be hung)

**Deployment Checklist Before Live:**

- [ ] 2+ weeks of paper trading (at least one full market cycle)
- [ ] Backtest covers at least 3 years of historical data
- [ ] Worst drawdown in backtest acceptable to you (e.g., < 25%)
- [ ] Live paper trading on actual Alpaca account (same fills, same latency as live)
- [ ] Logging configured, alerting tested
- [ ] Kill switches armed and tested (manually trigger to verify they work)
- [ ] VPS running, bot restarts on crash, running for 24+ hours without intervention
- [ ] Wash-sale tracking in place (if tax-relevant)
- [ ] PDT status checked (if margin account + day trading pre-June 4, 2026)
- [ ] Smaller live trade size than you tested (50% of paper trading size to start)

---

## Bot Naming — "The Toolkit"

Given the multi-strategy, adaptive, regime-aware nature, here are naming directions:

**Functional Names:**
- **Compass** — navigates market regimes, routes between strategies
- **Switchboard** — routes capital between multiple methods based on conditions
- **Arsenal** — multi-method trading toolkit
- **Catalyst** — activates strategies when conditions align

**Personality-Driven Names:**
- **Morpheus** — shape-shifts strategy based on regime
- **Sentinel** — watches market regimes, executes conditionally
- **Helmsman** — steers through different market conditions
- **Forge** — tests and forges strategies in live markets

**Technical Nods:**
- **Router** — too literal, but accurate
- **Oracle** — signals from market_health inform the bot
- **Sextant** — navigation + astronomy vibes (finding signal in the noise)

**Recommendation:** **Compass** or **Sextant** capture the essence (regime navigation + multi-faceted tools). But this is your call — ship with whichever resonates.

---

---

## Part 4 — Event-Driven & Sentiment Strategies

### Event-Driven: Earnings, Macro Calendar, News Catalysts

**Core Concept:** Trade around scheduled (earnings, Fed meetings, NFP, CPI) and unscheduled (M&A, product launches, FDA approvals, geopolitical shocks) events that move prices.

**Scheduled Events (Macro Calendar):**
- **Predictable catalysts:** CPI, NFP, PMI, ISM, FOMC meetings, GDP, retail sales, Treasury auctions
- **Pre-event behavior:** Often compression — vol contracts before release, then volatility spike post-release
- **Strategy:** 
  - Quiet entry (low vol) 1–2 days pre-event at mean-reversion levels
  - Exit immediately post-event release (capture the volatility pop or drop)
  - Avoid holding through event (binary outcomes, unpredictable direction)
- **Backtesting:** S&P 500 historically up on ~60% of macro release days; but direction depends on beat/miss vs. expectations

**Company-Specific Events (Earnings, M&A, FDA):**
- Entry: 1–5 days pre-earnings (IV expansion capture)
- Thesis: company beats EPS → up 2–5%, misses → down 3–7%
- Strategy: pairs trade (long winner stock, short loser sector) to isolate company-specific alpha
- Risk: gap risk on open; position sizing must account for potential 10% overnight moves

**News-Driven / Sentiment:**
- Real-time NLP on financial news (Reuters, Bloomberg, social media)
- Negative news → stronger market reaction (loss aversion, 1.5x magnitude vs. positive)
- Strategy: fade extreme sentiment (short when sentiment hits 90th percentile bullish, long when 10th percentile bearish)
- Implementation: use FinBERT or GPT sentiment scores, combine with technical confirmation (don't trade pure sentiment)

**Parameter Tuning:**
- Hold period pre-event: 2–5 days (capture IV, exit before binary)
- Hold period post-event: 1–2 hours (let the shock digest, exit volatility spike)
- Position size: smaller than typical (~50%) due to binary nature
- Regime filtering: disable event trades in low-liquidity hours (pre-market, post-market)

**Integration with Upstream Signals:**
- If `market_dashboard` shows elevated stress (composite > 60), reduce position size 50% on macro events (risk-off mood amplifies moves)
- If `tactical_markets` flags sector catalyst, activate event strategy only within that sector

**Evidence Quality:** ★★★★☆ — Academic consensus strong (Lo et al., NBER papers). Earnings alpha well-documented. Caveat: post-publication decay as retail/algos crowded the space.

_Sources: [QuantifiedStrategies — Event-Driven](https://www.quantifiedstrategies.com/event-driven-trading-strategies/), [Medium — Event-Driven Algos](https://medium.com/@pta.forwork/event-driven-trading-building-algorithms-that-react-to-news-and-earnings-ea428e3cb850), [TradingStrategyGuides — Event-Driven Strategies](https://tradingstrategyguides.com/event-driven-trading-strategies/), [SSRN — Multifactor Event-Driven](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID3683454_code4203724.pdf)._

---

## Part 5 — Classical Technical Analysis: Which Patterns Hold?

**The Research Question:** Do classical chart patterns (head-and-shoulders, double tops, triangles, flags) have empirical edge, or are they pattern-seeking bias?

**Academic Validation (Lo et al., NBER 1999-2001):**
- Studied head-and-shoulders, inverse H&S, broadening tops, triangle tops, rectangle tops, double tops over 1962–1996 on US stocks
- Found **statistical evidence** that patterns provide **incremental information beyond random chance**
- Win rates: 55–70% depending on pattern type and confirmation filters
- Caveat: small effect size; practical edge < 1% after transaction costs in the study period

**Bulkowski's Research (1980s–2000s):**
- Tested thousands of patterns on actual market data
- **Head-and-shoulders:** 60–65% accuracy (when combined with volume and RSI confirmation)
- **Double tops:** 58–62% accuracy
- **Triangles:** 50–55% (weakest pattern)
- **Flags & pennants (in trends):** 65–70% (strongest patterns)
- Key insight: **execution matters** — entry at pattern completion + volume confirmation is critical

**What Actually Works (Empirically Validated):**

| Pattern | Accuracy | Confirmation Required | Regime |
|---|---|---|---|
| Flag (in trend) | 65–70% | Volume spike, ATR expansion | Trending only |
| Inverted H&S | 62–68% | Volume confirmation, breakout | Reversal, low-vol to high-vol |
| Double bottom | 60–65% | Volume surge at breakout | Trend reversal |
| Ascending triangle | 58–63% | Close above resistance, vol | Uptrend continuation |
| Head-and-shoulders | 60–65% | Volume on right shoulder | Trend reversal |
| Rectangle | 50–55% | Breakout with volume | Neutral (weak pattern) |

**What Doesn't Work (Or Has Decayed):**
- Naked patterns (no volume/indicator confirmation) → 50–52% win rate (random)
- Patterns in high-frequency/algorithmic regimes → front-run by algos, decay ~1–2% per year post-publication
- Isolated pattern recognition (no regime context) → whipsawed in choppy markets

**Implementation for the Bot:**

Use patterns as **confirmation filters**, not primary signals:
1. Trend-following detects trend (moving average)
2. Pattern confirms entry point (flag within trend, inverted H&S at reversal)
3. Volume validates (50%+ above 20-day avg)
4. Execute

**Pattern-Specific Parameters:**
- Minimum pattern height: 2–5% of price (ignore noise patterns)
- Breakout confirmation: close beyond pattern boundary + 50% vol increase
- Hold period: 5–20 days (patterns mean-revert after breakout, don't hold forever)
- Stop-loss: below the pattern's opposite boundary

**Integration with Upstream Signals:**
- If `market_dashboard` shows **high equity_volatility**, activate only high-confidence patterns (flags, inverted H&S with volume)
- If `tactical_markets` identifies sector reversal, look for head-and-shoulders patterns within that sector

**Evidence Quality:** ★★★☆☆ — Empirically validated for specific patterns (flags, H&S), but edge decays post-publication. Useful as **confirmation tool** within a multi-strategy ensemble, not standalone.

_Sources: [UPenn / Lo et al. — Foundations of Technical Analysis (NBER WP 7613)](https://www.nber.org/system/files/working_papers/w7613/w7613.pdf), [ScienceDirect — Price Trends and Patterns](https://www.sciencedirect.com/science/article/abs/pii/S0378426608002951), [LuxAlgo — Classic Chart Patterns](https://www.luxalgo.com/blog/classic-chart-patterns-a-trading-essentials-guide/)._

---

## Part 6 — Crypto-Specific Microstructure & MEV

### Order Flow & Toxicity

**Crypto markets exhibit **higher information asymmetry** than equities** (VPIN ~0.45–0.47 vs. equities ~0.22). This means:
- More informed traders ("toxic" order flow) relative to noisy retail flow
- Larger bid-ask spreads (higher liquidity cost)
- Greater latency arbitrage opportunities (but also greater latency risk)

**Order Flow Imbalances → Price Movement:**
- When large buy orders hit the market, price spikes immediately
- But the spike **reverts partially** over 5–60 minutes (microstructure bounce)
- Strategy: scalp the bounce (buy the dump, sell the relief)
- Risk: MEV sandwich attacks (bot sees your order, jumps in front, extracts the profit)

### MEV (Maximal Extractable Value)

**Definition:** Value extracted by reordering, including, or excluding transactions in a block.

**Common MEV Sources:**
1. **Sandwich attacks:** bot sees your pending trade, executes a trade ahead of you to move the price, then your order executes at worse price, then bot sells back
2. **Liquidation arbitrage:** flash loans + instant liquidations of underwater positions
3. **AMM (Automated Market Maker) arbitrage:** buy on one DEX, sell on another, keep the spread
4. **Slippage extraction:** execute large trades in chunks to minimize slippage, collect the difference

**Quantifiable Impact:**
- Sandwich attacks can cost 0.1–1% per trade (depending on trade size)
- Liquidation MEV is in the billions annually (mostly valuable to searchers/bots, not retail)
- AMM arbitrage: 0.05–0.5% spread between price on different DEXs

**Defensive Strategies:**
- Use **private mempools** (MEV protection services like MEV-Blocker, MEV-Resistant RPC endpoints on Ethereum)
- Execute in smaller chunks (reduce sandwich attack profitability)
- Avoid flash-loan-vulnerable protocols
- Use encrypted mempools / threshold encryption (future tech)

### Latency Arbitrage

**Core Mechanic:** Bitcoin price moves on Coinbase → trader with sub-millisecond latency sees it → executes on Kraken 50ms later → captures the spread

**Practical for Retail?** Mostly no. Latency arbitrage requires:
- Co-located servers at exchange data centers (expensive)
- Microsecond-level latency (~100–500 microseconds vs. retail ~100ms)
- Capital-intensive (need $$ to capture tiny spreads)

**But:** Cross-exchange arbitrage (slower, 1–5 second lags) is still viable if you:
- Monitor price feeds across exchanges simultaneously
- Execute quickly (< 2 seconds round trip)
- Account for slippage, fees, deposit/withdrawal delays (often kill the arb)

### Crypto-Specific Parameter Differences

**ATR Multipliers:**
- Equities: 1.5–2.5 ATR stops typical
- Crypto: 2.5–4.0 ATR stops (higher baseline vol, more whipsaws)
- Bitcoin specifically: 3.0–4.0 ATR (structural higher vol)

**Moving Average Periods:**
- Equities (daily): 50/200 standard
- Crypto (4-hour): 20/60 or 30/90 (shorter periods due to 24/7 trading)
- Crypto (daily): 50/200 still works, but add weekly filter (7-day MA) for macro regime

**Position Sizing:**
- Equities: typical 2–5% per trade
- Crypto: 1–3% per trade (higher vol, higher risk of catastrophic moves)

**Drawdown Tolerances:**
- Equities: 20–30% typical for systematic strategies
- Crypto: 30–50% (structural higher vol; 50% drawdowns are normal)

_Sources: [Cornell / Easley — Crypto Microstructure](https://stoye.economics.cornell.edu/docs/Easley_ssrn-4814346.pdf), [SSRN — Latency Arbitrage](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5143158), [arXiv 2410.10797 — MEV Capture](https://arxiv.org/html/2410.10797v2), [arXiv 2602.00776 — Crypto Microstructure Patterns](https://arxiv.org/html/2602.00776v1)._

### Volatility Regimes: Equities vs. Crypto vs. Futures

**Equities (VIX-based):**
- Normal vol (VIX 10–20): trend-friendly, mean-reversion viable
- Elevated vol (VIX 20–30): avoid mean-reversion, favor trend-following
- Extreme vol (VIX > 30): all-in defensive mode, reduce position sizes 50–75%

**Crypto (No Official VIX, but proxies exist):**
- Bitcoin volatility ~2–3x S&P 500 baseline
- Deribit implied vol (options-based) is closest equivalent
- Use **30-day realized vol** as stand-in: compute 30-day rolling std dev of returns
  - Low: < 40% annualized (rare, boring markets)
  - Normal: 40–80% (standard crypto vol)
  - High: 80–150% (crypto entering stress mode)
  - Extreme: > 150% (black swan, de-risk immediately)

**Futures (VIX for specific contracts):**
- S&P 500 E-mini futures: vol mirrors equity VIX
- Bitcoin perpetuals: vol follows Deribit implied + spot BTC realized vol
- Crude oil futures: crude-specific vol, less correlated to equities

**Cross-Asset Implications:**
- When equity VIX spikes, Bitcoin often spikes 2–3x larger (crypto = risk-on, gets hammered in risk-off)
- Crypto vol and equity vol are **increasingly correlated** post-2020 (used to be uncorrelated; now both part of "risky assets")
- Futures volatility lags spot vol by 30–120 minutes (systematic arbitrage opportunity in vol regimes)

_Sources: [NIH / PMC — Crypto Volatility Markets](https://pmc.ncbi.nlm.nih.gov/articles/PMC8326316/), [BingX — Crypto VIX](https://bingx.com/en/learn/article/what-is-volatility-index-vix-in-crypto-trading), [QuantPedia — Crypto Vol Index](https://quantpedia.com/cryptocurrency-volatility-index/), [Morpher — VIX Alternatives for Crypto](https://www.morpher.com/blog/volatility-index-alternatives)._

---

## Part 7 — News & Sentiment Trading (NLP-Based)

### How Sentiment Works

**Loss Aversion Effect:** Negative news creates **1.5–2x larger market reactions** than equivalent positive news. This is a behavioral feature: loss hurts more than gain feels good.

**Sentiment Extraction (NLP):**
- Use FinBERT or GPT-4 to classify news articles as positive/negative/neutral
- Aggregate across all articles published in last 4 hours
- Score: 0–100 (0 = very negative, 50 = neutral, 100 = very bullish)

**Predictive Power:**
- Extreme sentiment (< 20 or > 80) predicts **mean-reversion over 1–4 hour horizon** (people overcorrect)
- Mid-range sentiment (40–60) predicts trend continuation over 4–24 hour horizon

### Implementation Strategy

**Simple Approach (Low-Tech):**
1. Capture Reuters/Bloomberg/CoinDesk headline volume + sentiment direction (up/down)
2. If sentiment is extreme (< 25th percentile bullish = bearish) AND price is at 52-week lows → **contrarian long**
3. If sentiment is extreme (> 75th percentile bullish) AND price is at 52-week highs → **contrarian short**
4. Hold 2–4 hours, exit on profit target (2–5% move)

**Advanced Approach (ML-Enhanced):**
- Train a sentiment classifier on historical news + price moves (supervised learning)
- Combine sentiment score with momentum/regime filters (don't short into a strong trend just because sentiment is bearish)
- Backtest: sentiment alone gives +2–4% annualized Sharpe; combined with technicals: +6–8%

### Parameter Tuning

**Sentiment Thresholds:**
- Extreme bullish: > 80 (enter contrarian short, size 50% of normal)
- Moderate bullish: 65–80 (reduce long positions, don't add)
- Neutral: 40–60 (no directional bias)
- Moderate bearish: 20–35 (reduce short positions, don't add)
- Extreme bearish: < 20 (enter contrarian long, size 50% of normal)

**Hold Periods:**
- Extreme sentiment fades fastest: 1–2 hours
- Moderate sentiment: 4–12 hours
- Neutral sentiment: N/A (no trade)

**Risk Control:**
- Never trade pure sentiment — **always confirm with technical setup** (pattern, MA level, support/resistance)
- In trending markets (ADX > 25), ignore contrarian sentiment trades (trend is stronger than mean-reversion)
- Position size: 50% of normal when trading pure sentiment (higher risk of false signal)

### Integration with Upstream Signals

- If `market_dashboard` shows composite stress > 60, sentiment trades are **more likely to work** (panic overshoots; recovery is violent)
- If `tactical_markets` identifies sector rotation, look for **contrarian sentiment within that sector** (sector momentum can override sentiment mean-reversion)

**Evidence Quality:** ★★★★☆ — Growing academic support (BERT/FinBERT papers 2022–2026 show predictive power). Decay risk: as more traders adopt NLP, edges shrink. Still valuable as **combination signal** within ensemble.

_Sources: [IEEE — Sentiment Analysis](https://ieeexplore.ieee.org/document/10961060/), [arXiv 2507.09739 — LLMs & Trading Performance](https://arxiv.org/html/2507.09739v1), [Alexandria Technology — NLP Signals](https://www.alexandriatechnology.com/blog/using-nlp-news-signals-to-forecast-volatility), [MDPI — News Sentiment & Market Dynamics](https://www.mdpi.com/1911-8074/18/8/412)._

---

### Synthesis & Regime-Methodology Matrix (Updated)

| Regime | Best Fit | Secondary | Avoid |
|---|---|---|---|
| **Strong trend, low vol** | Trend-following | Momentum, breakout | Mean reversion, carry |
| **Strong trend, high vol** | Trend-following (vol-scaled) | Momentum | Naive mean-reversion |
| **Range-bound, low vol** | Mean reversion, pairs | Grid/DCA | Trend-following, carry |
| **Range-bound, high vol** | Breakout, mean-reversion (wider bands) | Pairs (carefully) | Trend-following |
| **Transition / shift** | Breakout, vol increase | Volatility-selling fade | Carry, pairs |
| **Risk-off / crisis** | Vol-aware defensive (reduce size, exit shorts) | Trend-following (if exits quickly) | Mean reversion, long pairs, carry |

---

**Ready to proceed to Step 4 (implementation & infrastructure) or loop back on any of these families?**

- **[C] Continue** — proceed to Step 4
- Or note which families need deeper research, crypto-specific detail, or parameter tuning

<!-- Content will be appended sequentially through research workflow steps -->
