# tactical_markets_trading — TODO

Alpaca paper-trading layer that validates [tactical_markets](../tactical_markets/) signal efficacy. Separate from signal generation; integrates *with* it.

## Status

**Planning, in hopper.** Specs are locked in. Hard dependency: [tactical_markets](../tactical_markets/) must emit structured theses before this layer has anything to execute. Earliest meaningful start: after `tactical_markets` Brief 1 produces a thesis output.

## Source documents

- [ROADMAP_ALPACA_INTEGRATION.md](ROADMAP_ALPACA_INTEGRATION.md) — full implementation brief: Phase 1–3 paper-trading integration + validation loop
- [TRADING_INTEGRATION_PLAN.md](TRADING_INTEGRATION_PLAN.md) — architecture, platform choice (Alpaca), data flow

## Next concrete step (when the hopper opens)

Phase 1 in [ROADMAP_ALPACA_INTEGRATION.md](ROADMAP_ALPACA_INTEGRATION.md) — open an Alpaca paper account, store keys in `.env`, and hand-execute one round-trip via the SDK to confirm auth and order/fill semantics before any automation.

## Validation gate before live trading

50+ paper theses tracked end-to-end. Required metrics: win rate, average return per signal type, slippage vs. model price. No live capital until the gate is passed and the rules-of-engagement document is written.

## Integration with the other two projects

- **`tactical_markets/`** — consumes thesis records (e.g. "BUY 100 XLE, stop $85"); never imports from there. Contract lives on disk or via a defined schema.
- **`market_dashboard/`** — read-only consumer of the composite stress score for position-sizing rules (e.g. cut size when band is red). No reverse coupling.
