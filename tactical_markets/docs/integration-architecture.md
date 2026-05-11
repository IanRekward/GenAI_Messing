# Integration Architecture

`tactical_markets` is a monolith, but it sits between two sibling projects in `c:\Users\rekwa\ian_projects\`. This document covers those cross-project boundaries.

## Sibling projects

```
c:\Users\rekwa\ian_projects\
├── market_dashboard\           strategic early-warning (10y+ context, 11 buckets, composite score)
├── tactical_markets\           THIS PROJECT — tactical signals (24–48h horizon, sector rotation)
└── tactical_markets_trading\   Alpaca-based execution layer (planned; consumes this project's output)
```

| Project | Owns | Status |
|---|---|---|
| `market_dashboard` | Strategic regime call; "Is the system in stress?" | Shipping; not yet consumed here |
| `tactical_markets` (this) | Daily premarket signal; "What's the 24–48h trade?" | Week-1 live |
| `tactical_markets_trading` | Trade execution against signals | Not built yet |

## Hard rule — no Python imports across sibling projects

From [CLAUDE.md](../CLAUDE.md):

> No shared imports across the three sibling projects. `tactical_markets`, `market_dashboard`, and `tactical_markets_trading` integrate via files-on-disk, not Python imports. If you find yourself wanting `from market_dashboard.foo import bar`, stop and surface the design question.

Each project owns its own venv (when it has one). Each project owns its own dependencies. Each project ships independently. Integration happens through filesystem contracts.

## Outbound contract — to `tactical_markets_trading`

### Channel

**File-based, pull-mode.** The trading bot reads `c:\Users\rekwa\ian_projects\tactical_markets\data\theses.jsonl`.

There is **no** push, no IPC, no shared database, no message queue. The bot polls/tails the file.

### Schema

Documented in [data-models.md](./data-models.md). Three record shapes: signal, no-signal, error. JSON Lines, UTF-8, append-only.

### Cadence

One new line per scheduled run (~daily, 6:30 AM ET on weekdays). The bot should:

- Run after 6:30 AM ET (or tail continuously).
- Process new records (those with `as_of` > last-seen).
- Be tolerant of weekend/holiday gaps.

### What the trading bot must do that this project does not

The signal is intentionally minimal. The execution layer owns:

| Responsibility | Why it sits in the trading bot, not here |
|---|---|
| Position sizing | Risk is portfolio-level; depends on existing positions. |
| Stop-loss levels | Depends on bot's per-trade risk budget; not part of signal edge. |
| Profit targets | Same. |
| Exit timer | Read `config/thresholds.yaml` `hold_days` if needed. |
| Order routing (limit vs market) | Slippage policy is execution-layer. |
| Fill confirmation / partial-fill handling | Pure execution concern. |
| Live P&L tracking | Goes in the trading bot's own logs, not here. |
| Discretionary override | Ian reads the Pushover; the bot trades. Sequence may differ. |

### What this project would need to surface for richer integration (deferred)

Per the v2 ROADMAP (see [ROADMAP_SIGNAL_GENERATION.md](../ROADMAP_SIGNAL_GENERATION.md)), the trading bot might eventually want:

- `id` per thesis (stable key beyond timestamp)
- `confidence` score
- `stop` and `target` price levels
- `hold_window_hours` as a structured field
- `signal_type` discriminator (once a second signal type exists)
- `macro_context` block (VIX, credit spreads, regime call)
- `theses` array envelope (multiple plays per run)

**None are surfaced in week 1.** They are deferred until lived exposure validates that sector rotation alone is useful. Re-opening requires explicit user sign-off (see [architecture.md](./architecture.md#scope-boundaries--locked)).

## Inbound contract — from `market_dashboard`

**Currently: none.** Week-1 is standalone. The strategic composite score is *not* read.

Per [TODO.md](../TODO.md):

> Week 3+ may consume it as macro context, but week 1 is fully standalone.

When that integration lands, the expected shape is also files-on-disk: `tactical_markets` would read a file (probably JSON or YAML) emitted by `market_dashboard`'s daily run. The mechanism is not yet designed.

## Outbound contract — to Pushover (external)

- Endpoint: `https://api.pushover.net/1/messages.json`
- Auth: `PUSHOVER_TOKEN` + `PUSHOVER_USER` from `.env`.
- Payload: `title="Tactical Premarket"`, `message=<thesis text>`.
- Failure mode: returns `False` from `pushover.send`. The run still completes; the JSONL record is still written.

Pushover is **delivery**, not **contract**. A failed Pushover does not break any downstream contract — `theses.jsonl` is the canonical record.

## Inbound contract — from Yahoo Finance (external, free)

- Library: `yfinance`
- Tickers: 12 (9 SPDR sector ETFs + IWM, QQQ, SPY).
- Cadence: once per scheduled run.
- Failure mode: any `yfinance` exception is caught at the entrypoint boundary and produces an `error` JSONL record. No retry.

No SLA. Yahoo Finance has historically had occasional outages — the 2026-05-06 record in `theses.jsonl` shows one was captured cleanly.

## Data flow diagram

```
                            yfinance (Yahoo Finance, free)
                                       |
                                       v
   .env  +  config/*.yaml  -->  run_tactical.py
                                       |
                          +------------+------------+
                          |                         |
                          v                         v
                     Pushover API           data/theses.jsonl
                          |                         |
                          v                         v
                    Ian's phone           tactical_markets_trading
                                          (not built; will tail file)
```

Future (week 3+):

```
   market_dashboard/<composite-output>  -->  run_tactical.py  (macro context)
```

## Gaps between design (README/ROADMAP) and current reality

The [README](../README.md) and [ROADMAP](../ROADMAP_SIGNAL_GENERATION.md) describe a richer system than what week 1 ships. A trading-bot author reading those docs would expect features that don't exist. Specifically:

| Designed | Built | Status |
|---|---|---|
| 3–5 theses per run | 0 or 1 thesis per run | Cut. Multi-thesis envelope deferred. |
| Sector rotation **+** VIX slope **+** gaps **+** credit spreads | Sector rotation only | Cut. Other signals deferred to weeks 3+ pending lived exposure. |
| HTML dashboard tiles + Pushover | Pushover only | Cut. Plain-text thesis is the entire delivery. |
| Confidence scoring (1–100%) with publish/hold/skip tiers | Binary publish gate (spread >= 1.5%) | Cut. |
| Per-thesis `stop`, `target`, `qty`, `hold_window_hours`, `historical_win_rate`, `id` | None of these | Cut. |
| `macro_context` block (VIX, credit spreads, regime call) | Not collected | Cut. |
| Backtest framework + tests directory | Neither | Cut. Published Sharpe 0.92 treated as starting hypothesis. |
| Integration with strategic dashboard for regime context | Standalone | Deferred to week 3+. |
| 4-week parallel rollout | 5 working days, single signal end-to-end | Revised by 2026-05-05 design pass. |

**None of these are bugs.** They are deliberate scope cuts to ship something Ian can evaluate on his phone. The trading bot's author should plan against the schema in [data-models.md](./data-models.md), not against the v2 ROADMAP.

## README is stale

The [README](../README.md) currently says:

> ## Status
> Early-stage ideation. TBD: architecture, data sources, update cadence, display format.

All four — architecture, data sources, cadence, format — are now locked. The README has not been updated to reflect the 2026-05-05 design pass or the week-1 implementation. **Recommend updating the README** to point to [docs/index.md](./index.md) and to note current status before the trading-bot author reads it.

## Summary for the trading-bot author

You need three things:

1. **Read `data/theses.jsonl`** (tail or poll). Schema in [data-models.md](./data-models.md).
2. **Branch on record type** (signal / no-signal / error). Treat error and no-signal differently.
3. **Implement your own sizing, stops, targets, exits.** This project deliberately doesn't compute them.

You should **not** rely on:

- Multiple theses per run (max 1 today).
- Confidence scores (none today).
- A `signal_type` field (implicit: always sector rotation today).
- Macro context, VIX, credit spreads (not collected today).
- An `id` field, a `theses` array envelope, or a schema version field (none of these exist today).

Plan for schema additions — but not against a specific timeline. They land when (and if) lived exposure justifies them.
