# tactical_markets_trading — TODO

Alpaca paper-trading layer that validates [tactical_markets](../tactical_markets/) signal efficacy. Separate from signal generation; integrates *with* it via files-on-disk (`tactical_markets/data/theses.jsonl`). No imports across projects.

## Status

**Phase 1 Day 1 complete (2026-05-08).** Alpaca paper account active (`PA3SOYDP6IP5`, $100k), [src/alpaca_connector.py](src/alpaca_connector.py) confirmed auth + account fetch. Day 2 onward is locked-brief execution; switch to Sonnet 4.6+ for it.

## Source documents

- [ROADMAP_ALPACA_INTEGRATION.md](ROADMAP_ALPACA_INTEGRATION.md) — original implementation brief, **revised by the 2026-05-08 design pass**. Preserved as Phase 2/3 spec context.
- [TRADING_INTEGRATION_PLAN.md](TRADING_INTEGRATION_PLAN.md) — architecture, platform choice (Alpaca), data flow.

## Locked Phase 1 design (2026-05-08 design pass, Opus 4.7)

Design pass run after `tactical_markets` week-1 ship. The ROADMAP's pair-trade hypothesis cannot be tested under Ian's durable "no shorts, ever" rule (infinite-downside risk preference). Phase 1 tests a *related* long-only momentum hypothesis instead.

**Hypothesis:** Long-only momentum on sector winners outperforms buy-and-hold SPY.

**Mechanic:**
- Account: Alpaca paper, $100k. `paper=True` flag in `TradingClient` is the safety pin.
- Trigger: each trading day, if `tactical_markets/data/theses.jsonl` has a `signal: true` line for that day, buy the `buy` ticker only (ignore the `sell` leg).
- Sizing: fixed **$10k per trade** (10% of account, fractional shares via Alpaca `notional` field). No risk-based sizing in Phase 1.
- Order type: **market order** at entry, **market order** at exit. Slippage optimization deferred.
- Exit: market order, **5 trading days after entry**. No stop, no target.
- Concurrency: up to 5 overlapping positions. Steady state ~50% deployed, ~50% cash.
- Per-trade logging: entry, fills, exit, P&L — plus two benchmarks at exit time:
  - (a) SPY's return over the same window
  - (b) The loser-leg ticker's return over the same window
  - (b) lets us reconstruct the pair-trade Sharpe post-hoc, even though we never short.

**Why no stops in Phase 1:** characterizing the signal, not managing risk. Stops introduce a confound (where did you set it?) that contaminates validation. After ~10 trades we'll see the drawdown distribution and can size stops based on real data instead of guesses.

**Why fixed dollar sizing:** risk-based sizing needs a stop, which we don't have. Fixed dollar makes per-trade P&L directly comparable across trades.

**What this revises from ROADMAP_ALPACA_INTEGRATION.md:**
- Pair trade → long-only winner + counterfactual loser-leg tracking.
- Limit orders w/ ask + 5bps → market orders.
- 2% risk / 5% position / 20% open caps → deferred to Phase 2 (after drawdown distribution is known).
- Confidence-based sizing → fixed sizing.
- "Manual approval, user clicks Execute" → fully automated; we want to test the signal, not Ian's discretionary judgment.
- Phase 1 success criteria → simplified (see below).

**Trade-offs accepted:**
- Long-only ≠ pair-trade hypothesis, so we're testing a related but not identical edge.
- Market orders sacrifice slippage optimization for execution simplicity.
- Full automation contaminates "would Ian have actually placed this trade?" but cleanly tests the signal.

## Phase 1 day-by-day

- **Day 1 (2026-05-08, complete):** [src/alpaca_connector.py](src/alpaca_connector.py) — `load_env()`, `trading_client()`, `__main__` prints account info. Smoke-tested against paper account.
- **Day 2:** read most-recent `signal: true` line from `../tactical_markets/data/theses.jsonl`, build a market buy order for `buy` ticker with `notional=10000`, submit, print fill. File: `src/order_builder.py` with inline `__main__` smoke run. Manual trigger only.
- **Day 3:** trade logging — on entry, append a record to `data/trades.jsonl` with order id, fill price/qty, entry timestamp, intended exit timestamp (entry + 5 trading days using a US market calendar — `pandas_market_calendars` or hand-rolled). File: `src/trade_logger.py`.
- **Day 4:** exit logic — script reads `data/trades.jsonl`, finds open positions whose exit time has passed, submits market sell for the held qty, appends exit record. File: `src/exit_manager.py`. Manual trigger.
- **Day 5:** benchmark capture — at exit time, fetch SPY return + loser-leg return over the same window via yfinance, append to exit record. Trade-record schema is now complete.
- **Day 6:** scheduling — Windows Task Scheduler. Two tasks: entry runs at 9:35 AM ET (5 min after open), exit runs at 9:40 AM ET. Mirror `tactical_markets/setup_task.ps1` battery flags. Holiday handling: skip if no thesis file written that morning.
- **Day 7:** two consecutive clean scheduler fires (entry + exit). Then freeze.

After Day 7, **no new code.** Accumulate paper trades passively. Phase 1 success gate: 10+ trades executed end-to-end without rejections or stranded positions.

## Validation gates

- **Phase 1 → Phase 2:** 10+ clean executions, no system errors, positions exit on schedule. ~2–3 weeks at 1 signal/day.
- **Phase 2 → Phase 3 (live capital):** 50+ trades, win rate vs SPY > 50%, alpha statistically positive. ~10+ weeks.
- **Hard floor:** no live capital until Ian writes a one-page rules-of-engagement document and the validation gate is passed.

## Design fork points (hand back to Opus 4.7)

- **End of Phase 1 (~10 trades):** review trade distribution, decide whether to add stops, change sizing, or move to Phase 2 (refined risk management).
- **Surprise in results:** if win rate is dramatically above or below expectation, the hypothesis or the signal might need revisiting.
- **Trading-day calendar edge cases:** long weekends, early closes, halts, ETF rebalances. If 5-trading-day exit math gets weird in practice.
- **Phase 2 → Phase 3:** writing the rules-of-engagement document, picking the live-capital amount, deciding what (if anything) gets sized differently.

## Locked rules — do not re-open without explicit user sign-off

| Topic | Decision |
|---|---|
| Shorts | Never. Durable preference (memory: feedback_no_shorts.md). Long-only or cash only. |
| Real money | Not until 50+ paper trades validate edge AND rules-of-engagement doc is written. |
| Cross-project imports | Forbidden. Read `theses.jsonl` from disk. |
| Account size | $100k paper. Don't change without re-deriving sizing. |
| Trade size | Fixed $10k per trade. Phase 1 only; Phase 2 may reintroduce risk-based sizing. |
| Stops/targets | None in Phase 1. Add in Phase 2 after seeing real drawdown distribution. |
| Manual vs automated | Automated entries and exits. Manual approval reintroduces discretionary contamination. |

## Cross-project integration

- **`tactical_markets/`** — read-only consumer of `data/theses.jsonl`. No imports.
- **`market_dashboard/`** — not consumed in Phase 1. May read composite stress score in Phase 2 for size-down logic when band is red.

## Environment

- Own venv at `tactical_markets_trading/.venv/`. Created Day 1 with Python 3.14 (system).
- Dependencies installed: `alpaca-py`, `python-dotenv`. Add `yfinance`, `pandas-market-calendars` (or equivalent) on Days 4–5.
- `.env` keys: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_BASE_URL` (the URL is informational only — `paper=True` in code is the actual safety pin). Gitignored via root `.gitignore`.
