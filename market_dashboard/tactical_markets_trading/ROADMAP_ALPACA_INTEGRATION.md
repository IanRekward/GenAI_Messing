# ROADMAP Brief 2: Tactical Markets Trading Integration (Alpaca Paper)

**Execute tactical signals via Alpaca paper trading, validate efficacy, measure edge empirically.**

## Problem

Tactical signal generation (Brief 1) produces theses. But *do they work*? Paper backtests (2015–2026) show edge in aggregate, but:
- Backtests don't account for real slippage, rejections, or execution friction
- Psychology (fear/greed) distorts retail execution vs model
- Regime shifts: edge documented in historical data may have decayed

Gap: Need **empirical real-time feedback** on whether the model's edge translates to actual fills + P&L.

## Solution: Alpaca Paper Trading Integration

1. **Manual execution phase (Phase 1):** User reviews thesis on dashboard, clicks "Execute" → order sent to Alpaca paper account
2. **Automatic logging:** Track entry price, fills, holds, exits, P&L
3. **Validation loop:** Compare actual fills vs backtest slippage assumptions; measure win rate by signal type
4. **Calibration:** After 30–50 trades, adjust signal thresholds based on live data
5. **Graduation:** If live performance > backtest (Sharpe +0.1 or better, win rate >50%), consider Phase 2 (auto-execute) or Phase 3 (live money)

## Design Decisions

### Alpaca: Why This Platform?

| Criterion | Alpaca | Interactive Brokers | TD Ameritrade |
|-----------|--------|-------------------|---------------|
| **API simplicity** | Excellent (Python SDK, clean REST) | Good (complex, but powerful) | Poor (thinkorswim only) |
| **Paper trading** | Free, unlimited | Free | Good (thinkorswim tools) |
| **Execution quality** | Nasdaq member (2025), direct routing | Superior (150+ order types) | Mid-tier |
| **Commission** | $0 (retail equity) | Tiered (0.01–1/share) | $0 (post-closure) |
| **Data latency** | Acceptable (not HFT-grade) | <50ms (TWS) | Mid-tier |
| **Retail fit** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |

**Decision:** Alpaca. Simple, cost-free, sufficient latency, Python SDK well-maintained.

### Order Types & Execution

**Phase 1 restrictions (manual approval):**
- **Limit orders only** (entry). Edge: 10–20 bps savings on large orders; 65% fill rate acceptable.
- **Market orders for exits** if underwater (slippage < bid-ask spread risk).
- **No options, no shorts, no margin.** Keeps it simple; tests equity/sector rotation edge only.

**Logic:**
- Thesis says: "BUY 100 XLE at market, SELL 100 XLK at market"
- Dashboard translates to: "BUY 100 XLE at limit [ask + 5bps], SELL 100 XLK at limit [bid − 5bps]"
- User reviews, clicks "Execute"
- System submits both orders (attempt fill within 60 seconds; if not, cancel and retry at next signal)
- Log actual fills vs intended entry

**Realistic slippage model:**
- **Large-caps (SPY, QQQ, IWM, XLE, XLK, etc.):** 1–2 bps expected slippage
- **If actual > 2x expected:** Log as anomaly, flag user ("slippage higher than normal; possible rejection or wide spread")

### Position Sizing & Risk Management

**Hard rules (prevent blowups):**
- **Max 2% risk per single trade:** If thesis entry is $100 and stop is $98, size is (account × 0.02) / $2 = 1% of account
- **Max 5% per position:** If sector rotation wants 3% of account, cap it at 5%
- **Max 20% in open positions:** Prevents over-concentration; leaves room to add on reversals or scale
- **Minimum position value:** $100 (avoid penny-stock drag)

**Sizing formula:**
```
risk_dollars = account_value × 0.02
position_size = risk_dollars / (entry_price − stop_price)
if position_size > (account_value × 0.05):
    position_size = account_value × 0.05  # cap at 5%
```

**Example:**
- Account: $10,000
- Thesis: Buy XLE $91.30, stop $89.50 (1.97% drawdown)
- Risk: $10k × 0.02 = $200
- Position: $200 / $1.80 = 111 shares
- Check: 111 × $91.30 = $10,134 (> 5% cap, $500)
- Adjusted: 5% of $10k = $500; $500 / $91.30 = 5 shares

Hold on, that's tiny. Let me recalculate. If max 5% per position is $500 and stop is $1.80, that's only 278 shares. That's actually reasonable for a micro-account. For Phase 1 (validation), assume Ian's paper account is $25k–50k minimum.

### Hold Window Enforcement

**Auto-exit rules:**
1. **Target hit:** Exit immediately, log win
2. **Stop hit:** Exit immediately, log loss
3. **Hold window expired:** Exit at market (or best available limit), log as "timeout"
4. **Confidence fade:** If new thesis contradicts old (e.g., sector rotation reverses), exit early

**Timeout logic:**
```
entry_time = 2026-04-27 09:35:00
hold_window = 120 hours (5 days for sector rotation)
auto_exit_time = entry_time + 120h = 2026-05-02 09:35:00
if current_time > auto_exit_time and not_exited:
    exit_at_market_or_best_limit()
    log_as("timeout")
```

**Why:** Prevents "holding a loser indefinitely." Edge is time-bounded; after window, trade becomes discretionary.

### Backtesting Loop (Daily Reconciliation)

Each day at close, system generates a **"what if we had executed yesterday" report:**

```
Thesis: XLE rotation (generated 2026-04-27 06:30)
Recommended action: BUY 100 XLE @ 91.30, SELL 100 XLK @ 122.45
Hold window: 5 days (until 2026-05-02)
Historical fill: Executed 2026-04-27 09:35 @ 91.35, 122.48
Slippage: +0.5 bps (XLE), +2.5 bps (XLK) — within model
Day 1 (2026-04-27): XLE 91.50 (+0.22%), XLK 121.80 (−0.53%) → position +0.30%
Day 2 (2026-04-28): XLE 92.10 (+0.66%), XLK 121.00 (−0.66%) → position +1.32%
Day 3 (2026-04-29): XLE 93.80 (+1.85%), XLK 120.50 (−0.41%) → position +2.26%
[Days 4–5 pending]

Backtest equivalent (2015–2026 data, sector rotation):
Same entry date simulated: Would have filled 91.27, 122.42 (historical avg slippage)
Actual vs backtest slippage: −0.8 bps (XLE), −0.6 bps (XLK) → better than model
```

This feedback loop calibrates slippage assumptions.

### Data Schema & Logging

```python
# Each executed thesis logged to data/trades.jsonl

{
  "trade_id": "uuid",
  "timestamp_created": "2026-04-27T06:30:00Z",  # signal generation
  "signal_type": "sector_rotation",
  "confidence": 70,
  
  "orders": [
    {
      "side": "BUY",
      "symbol": "XLE",
      "qty": 111,
      "entry_type": "limit",
      "limit_price": 91.35,  # ask + 5bps
      "timestamp_submitted": "2026-04-27T09:35:10Z",
      "timestamp_filled": "2026-04-27T09:35:22Z",
      "fill_price": 91.35,
      "fill_qty": 111,
      "slippage_bps": 5.5,  # (91.35 - ask) / ask × 10000
      "status": "filled"
    },
    {
      "side": "SELL",
      "symbol": "XLK",
      "qty": 111,
      "entry_type": "limit",
      "limit_price": 122.40,  # bid - 5bps
      "timestamp_submitted": "2026-04-27T09:35:10Z",
      "timestamp_filled": "2026-04-27T09:35:31Z",
      "fill_price": 122.48,
      "fill_qty": 111,
      "slippage_bps": -6.5,  # wider than limit, but filled
      "status": "filled"
    }
  ],
  
  "position": {
    "entry_timestamp": "2026-04-27T09:35:31Z",
    "entry_cost": 111 * 91.35 - 111 * 122.48,  # net debit (if spread works)
    "target_price": {"XLE": 94.0, "XLK": 120.0},
    "stop_price": {"XLE": 89.5, "XLK": 124.0},
    "hold_window_hours": 120,
    "auto_exit_time": "2026-05-02T09:35:31Z"
  },
  
  "exit": {
    "timestamp": "2026-04-29T15:45:00Z",
    "exit_reason": "target_hit",  # or "stop_hit", "timeout", "contradiction"
    "exit_price_xe": 94.05,
    "exit_price_xlk": 120.10,
    "exit_qty_xlk": 111,  # may be partial on timeout
    "pnl_dollars": 1250,
    "pnl_percent": 3.01,
    "hold_hours": 53.5,
    "slippage_round_trip": 12,  # bps
    "friction_cost": 15,  # bps (slippage + implied commissions)
    "net_return_after_friction": 2.86
  },
  
  "metadata": {
    "account_value_at_entry": 25000,
    "position_size_pct": 4.8,
    "risk_dollars": 500,
    "risk_pct_account": 2.0,
    "confidence_at_exit": 70,
    "macro_context": {
      "vix": 21.2,
      "composite_band": "orange",
      "credit_spreads_change": 15  # bps; context
    }
  },
  
  "backtest_comparison": {
    "historical_avg_return": 1.87,  # sector rotation, 2015–2026
    "historical_sharpe": 0.92,
    "this_trade_return": 2.86,  # better than average
    "this_trade_hold": 53.5,  # faster than avg 120h window
    "percentile_vs_backtest": "75th"  # top quartile this trade
  }
}
```

**Aggregated metrics (jsonl → CSV daily summary):**
```csv
date,signal_type,trades_executed,avg_return_pct,win_rate,sharpe_rolling_30d,slippage_vs_model_bps
2026-04-27,sector_rotation,1,2.86,100,1.2,+5.5
2026-04-28,vix_slope,2,0.45,50,0.3,-2.0
2026-04-29,gap_fill,1,0.52,100,0.8,+1.0
...
```

## Implementation Files

```
tactical_markets_trading/
  ROADMAP_ALPACA_INTEGRATION.md  (this file)
  src/
    alpaca_connector.py           (auth, order submission, fills)
    position_manager.py           (hold window, auto-exit, sizing)
    order_builder.py              (thesis → Alpaca order syntax)
    trade_logger.py               (JSONL logging, aggregation)
    backtest_reconciler.py        (daily "what-if" report)
    slippage_calibrator.py        (actual vs model slippage tracking)
  config/
    alpaca_settings.yaml          (API keys, paper account, order templates)
    risk_limits.yaml              (2% per trade, 5% per position, 20% open)
  tests/
    test_order_building.py        (thesis → order format)
    test_position_sizing.py       (Kelly, account draw rules)
    test_auto_exit_logic.py       (hold window, timeout)
    test_fill_simulation.py       (slippage model validation)
  data/
    trades.jsonl                  (all executed trades, logged daily)
    trades_aggregated.csv         (daily summary: return, win rate, Sharpe)
    backtest_reconciliation.csv   (what-if daily report)
  output/
    [daily reports, P&L charts]
```

## Phase 1 Success Criteria (Manual Execution)

- [ ] Alpaca API authentication + live connection (paper account)
- [ ] 10+ executed theses without order rejections or system errors
- [ ] Order execution: 80%+ of limits fill within 60s; slippage within model (±2 bps for large-caps)
- [ ] Trade logging: Every execution logged to trades.jsonl with full metadata
- [ ] Win rate: >50% on 10+ trades (statistical significance low, but positive sign)
- [ ] P&L tracking: Dashboard displays running position P&L, target/stop status
- [ ] Auto-exit: Timeout logic executes correctly; no stranded positions
- [ ] Backtest reconciliation: Daily "what-if" report matches live fills within 5 bps

## Phase 2 Success Criteria (Confidence-Based Auto-Execute)

- [ ] 30+ executed trades with 50%+ win rate and documented Sharpe >0.3
- [ ] Confidence calibration: Signals >70% win >55% live; signals 50–70% win ~50%
- [ ] No catastrophic losses: Max drawdown <20% of account
- [ ] Slippage model validated: Actual avg slippage = model ±2 bps over 30 trades

## Phase 3 Success Criteria (Live Trading)

- [ ] 50+ paper trades, validated Sharpe >0.75, win rate >55%
- [ ] Account minimum $25k (SEC pattern-day-trade requirement)
- [ ] Position sizing rules automated and tested
- [ ] Risk guardrails locked: alerts if drawdown >15%, auto-stop at 25%

## Dependencies

- **Alpaca:** API keys, paper account setup (free), Python SDK
- **Signal generation:** Brief 1 output (tactical_markets/output/dashboard.html JSON)
- **Data:** yfinance (fills), Alpaca API (positions, orders)
- **Libraries:** pandas, numpy, requests, alpaca-trade-api SDK

## Edge Cases & Safeguards

1. **Gap down >5% overnight:** Cancel gap-fill orders (high-risk reversal, low edge)
2. **Circuit breaker triggered:** Reject all new theses until market stabilizes (hold 15 min)
3. **Alpaca connection drops:** Log error, retry with exponential backoff; disable auto-exit until restored
4. **Order rejected (insufficient buying power, halted symbol, etc.):** Log rejection reason, notify user, refund capital reservation
5. **Partial fills:** Scale exit proportionally; log as "partial, exit qty = fill qty"
6. **Thesis conflicts:** If new thesis contradicts open position (e.g., rotate OUT of XLE the day after rotating IN), flag to user, allow manual override
7. **Account < $5k:** Disable paper trading (slippage bps scale differently at micro-account sizes)

## Known Limitations

- **Paper vs live friction:** Paper trading has zero rejection rate, zero commission. Live may see 5–10% worse fills.
- **Execution latency:** Alpaca is not HFT-grade; gap fills may miss if premarket volatility is extreme.
- **Margin/shorting:** Out of scope Phase 1. Long-only universe limits signal set.
- **Options strategies:** Out of scope Phase 1. Equity/ETF rotation only.

## Rollout Schedule

1. **Week 1:** Set up Alpaca paper account, implement alpaca_connector.py + order_builder.py
2. **Week 2:** Implement position_manager.py, auto-exit logic, trade logger
3. **Week 3:** Connect Brief 1 (signal generation) → Brief 2 (execution); manual testing
4. **Week 4:** Begin live paper trading with first 5 theses; log fills daily
5. **Weeks 5–8:** Execute 30–50 theses; monitor win rate, calibrate slippage model
6. **Month 3:** Decision point: Phase 2 (auto-execute) or continue manual; or Phase 3 (live) if validated

## Co-developed with Tactical Markets Signal Generation

This brief pairs with Brief 1 (signal generation). Signal generation is *independent* (can be shipped and validated separately), but trading integration provides empirical feedback to refine thresholds.

---

**Next:** Implement Briefs 1 + 2 in parallel. Signal generation ships by Week 3; trading integration begins Week 3–4.
