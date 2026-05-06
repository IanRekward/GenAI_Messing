# Tactical Markets Trading Integration

Alpaca paper trading integration to validate tactical signal efficacy. Separate from signal generation; integrates *with* `tactical_markets/` signal output.

## Purpose

- Execute theses suggested by the tactical dashboard
- Test via **paper trading first** (no real money risk)
- Track: win rate, avg return per signal type, slippage vs. model
- After 50+ validated theses → consider live trading with rules

## Architecture

```
tactical_markets/ (signal generation)
    ↓ (generates theses)
tactical_markets_trading/ (execution + P&L tracking)
    ↓ (receives "BUY 100 XLE, stop $85" etc)
    ├─ Alpaca API (paper account)
    ├─ Order execution + fills
    └─ Position tracking & historical logging
```

## Platform: Alpaca

- REST API + Python SDK
- Paper trading account (free, no commission)
- Real-time websocket data
- Position tracking, fills, P&L
- Active community, well-maintained

## Workflow

1. **Signal generation** produces thesis card: "Buy XLE, sell XLK, stop at $X, target $Y"
2. **Dashboard displays** the suggested order with entry/stop/target
3. **User reviews** on dashboard + clicks "Execute"
4. **Order sent to Alpaca** paper account via API
5. **Dashboard polls Alpaca** for:
   - Actual fill price (vs. estimated)
   - Current position P&L
   - When target/stop hit
6. **Position closes** → logged to history with metadata (signal type, thesis, actual return)
7. **Backtesting loop**: Run yesterday's signals through same rules, see what would have hit/missed

## Phases

### Phase 1: Manual Execution (MVP)
- Connect to Alpaca paper account
- Dashboard displays: "Execute order?" button
- User clicks → order goes to Alpaca
- Track fills + P&L on dashboard
- **Duration**: 20–30 live tests
- **Metric**: Win rate, avg return, which signal categories work

### Phase 2: Confidence Scoring (after Phase 1 validation)
- Each thesis gets a confidence score (e.g., 0–100%)
- Only auto-execute if confidence > threshold
- Reduces whipsaw trades, keeps manual control where it matters

### Phase 3: Live Trading (only after 50+ validated theses with edge)
- Position sizing rules: max 5% per trade, max 20% portfolio in open positions
- Real-money account
- Requires approval + risk guardrails

## Key Design Decisions

### Approval model
- **Phase 1**: Manual click to execute (user sees order, approves)
- **Rationale**: Keeps feedback loop tight; user learns what's actually tradeable vs. theoretical

### Slippage & fill modeling
- Paper trading doesn't model real slippage (no commission, no friction)
- Dashboard should show: "estimated fill" vs "actual fill" vs "real market price at time of order"
- After Phase 1, build a slippage model to adjust signal thresholds

### Position sizing
- Max 5% of account per single trade
- Max 20% of account in open positions simultaneously
- Prevents over-concentration, keeps paper account alive for 50+ tests

### Hold window enforcement
- Each thesis has a target hold window (24–48h typically)
- Dashboard auto-closes position at window end if target not hit
- Prevents "bag holding" thesis that didn't work
- Logs as: "closed by timeout, actual return: X%"

### Backtesting loop
- Each day, run yesterday's signal theses through same execution rules
- Compare: "if we had executed yesterday, would this have hit?"
- Useful for: identifying which signal categories have false positive rates

## Data to log

For each executed thesis:

```json
{
  "thesis_id": "uuid",
  "timestamp_created": "2026-04-27T06:30:00Z",
  "signal_type": "sector_rotation",
  "thesis": "XLK weakness, XLE strength",
  "action": "SELL 100 XLK @ market, BUY 100 XLE @ market",
  "entry_time": "2026-04-27T09:30:15Z",
  "entry_price_est": {"XLK": 122.50, "XLE": 91.30},
  "entry_price_actual": {"XLK": 122.48, "XLE": 91.35},
  "slippage_bps": {"XLK": 1.6, "XLE": -5.5},
  "target_price": {"XLE": 94.0},
  "stop_price": {"XLE": 89.5},
  "hold_window_hours": 48,
  "exit_time": "2026-04-27T15:45:30Z",
  "exit_reason": "target_hit",
  "exit_price": {"XLE": 94.05},
  "return_pct": 3.01,
  "closed": true
}
```

## Success Criteria (Phase 1)

- [ ] Alpaca API integration working (auth, order submission, fills)
- [ ] 20+ live executed theses without errors
- [ ] Win rate > 40% (better than coin flip)
- [ ] Avg return per winning trade > avg loss per losing trade
- [ ] No blown-up paper account (position sizing rules work)
- [ ] Slippage model built (estimated vs actual quantified)

## Dependencies

- Alpaca account + API keys
- Python Alpaca SDK (`pip install alpaca-trade-api`)
- Tactical markets signal generation (Phase 1 signal output format locked)

## Out of scope (Phase 1)

- Options strategies (start with equities/ETFs only)
- Short selling (long only to start)
- Leverage / margin (keep it simple)
- Live trading (paper only)
- Auto-execution (manual approval)

## Status

Early-stage planning. Awaiting:
1. Tactical markets signal generation design (locked)
2. Go/no-go decision on integration scope
3. Alpaca account setup confirmation
