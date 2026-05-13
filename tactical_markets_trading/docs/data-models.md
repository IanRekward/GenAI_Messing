# Data Models

**Generated:** 2026-05-13 (deep scan). Schema derived from [src/trade_logger.py](../src/trade_logger.py) and [src/exit_manager.py](../src/exit_manager.py).

This project owns one stateful artifact: `data/trades.jsonl`. It's an append-only JSONL ledger of every entry, with each row updated in place when the position closes. There is no database, no other persistence.

---

## `data/trades.jsonl` — The trade ledger

### Lifecycle

```
Entry task writes:                  Exit task updates (in place):
─────────────────                    ────────────────────────────
status: "open"                       status: "closed"
+ entry fields                       + exit fields
                                     + benchmarks (may be null)
```

The Entry task **appends** a new line per signal day (skipped if `already_traded`). The Exit task **rewrites** the file with all records — open ones untouched, ripe ones flipped to `closed` with exit fields merged in. The file is always small (target ~5 open positions max + accumulating closed history), so full-file rewrites are fine.

### Schema — entry (when written by Entry task)

```json
{
  "trade_id": "550e8400-e29b-41d4-a716-446655440000",
  "order_id": "c0a80101-1234-1234-1234-123456789abc",
  "symbol": "XLE",
  "sell_leg": "XLK",
  "notional": 10000,
  "thesis_as_of": "2026-05-13T06:30:00+00:00",
  "entry_time": "2026-05-13T13:35:22.123456+00:00",
  "fill_price": 91.35,
  "fill_qty": 109.4807,
  "exit_time_planned": "2026-05-20 13:35:22.123456+00:00",
  "status": "open"
}
```

| Field | Type | Source | Notes |
|---|---|---|---|
| `trade_id` | UUID4 string | Generated locally | Internal identifier; not visible to Alpaca. |
| `order_id` | string | Alpaca | The entry order's Alpaca ID. Used to poll fill status. |
| `symbol` | string | MICRO thesis `buy` field | The long-leg ticker we buy. |
| `sell_leg` | string | MICRO thesis `sell` field | The thesis's loser-leg ticker. **We don't trade it** — it's preserved for the exit-time benchmark capture (lets us reconstruct pair-trade Sharpe post-hoc without shorting). |
| `notional` | int | constant `NOTIONAL = 10_000` | Phase 1 fixed sizing. |
| `thesis_as_of` | ISO 8601 timestamp | MICRO thesis `as_of` field | Pass-through from MICRO. Used for traceability (which thesis fired this trade). |
| `entry_time` | ISO 8601 timestamp | Alpaca `order.filled_at` | The fill time, not the submission time. |
| `fill_price` | float | Alpaca `order.filled_avg_price` | The average fill price (notional sizing → fractional shares → there's only one fill). |
| `fill_qty` | float | Alpaca `order.filled_qty` | Fractional. Computed by Alpaca from `notional / fill_price`. |
| `exit_time_planned` | string (datetime repr) | `add_trading_days(entry_time, HOLD_DAYS)` (HOLD_DAYS=2 as of 2026-05-13) | NYSE-aware. Note: written via `str(datetime)`, not `.isoformat()`. Parses cleanly with `datetime.fromisoformat()`. |
| `status` | enum `"open"` \| `"closed"` | constant `"open"` at entry | Flipped to `"closed"` by Exit task. |

### Schema — closed (after Exit task processes)

The entry row above is **merged** with the exit fields below (Python `{**record, ...exit_fields}` pattern in [src/exit_manager.py:56-67](../src/exit_manager.py#L56-L67)):

```json
{
  "trade_id": "550e8400-e29b-41d4-a716-446655440000",
  "order_id": "c0a80101-1234-1234-1234-123456789abc",
  "symbol": "XLE",
  "sell_leg": "XLK",
  "notional": 10000,
  "thesis_as_of": "2026-05-13T06:30:00+00:00",
  "entry_time": "2026-05-13T13:35:22.123456+00:00",
  "fill_price": 91.35,
  "fill_qty": 109.4807,
  "exit_time_planned": "2026-05-20 13:35:22.123456+00:00",

  "exit_order_id": "c0a80101-9999-9999-9999-987654321cba",
  "exit_time_actual": "2026-05-20T13:40:15.654321+00:00",
  "exit_fill_price": 94.10,
  "exit_fill_qty": 109.4807,
  "pnl_dollars": 301.07,
  "pnl_pct": 3.01,
  "spy_return_pct": 0.85,
  "sell_leg_return_pct": -1.22,
  "status": "closed"
}
```

Additional fields:

| Field | Type | Source | Notes |
|---|---|---|---|
| `exit_order_id` | string | Alpaca | The exit order's ID. |
| `exit_time_actual` | ISO 8601 timestamp | Alpaca `order.filled_at` of the SELL | The actual exit time. Likely a few seconds after the planned time (Exit task fires at 08:40 CDT and processes ripe trades). |
| `exit_fill_price` | float | Alpaca | Avg fill price on the SELL. |
| `exit_fill_qty` | float | Alpaca | Should equal `fill_qty` (we sell what we bought). |
| `pnl_dollars` | float, rounded to 2 dp | computed | `(exit_fill_price * exit_fill_qty) - (fill_price * fill_qty)`. |
| `pnl_pct` | float, rounded to 4 dp | computed | `(exit_proceeds - entry_cost) / entry_cost * 100`. |
| `spy_return_pct` | float \| null | yfinance | SPY pct return over `[entry_time, exit_time_actual]`. **null** if yfinance fetch fails. Captured **after** the SELL fills, so a failure here doesn't lose the trade record. |
| `sell_leg_return_pct` | float \| null | yfinance | Same window, applied to `sell_leg`. Lets us reconstruct pair-trade Sharpe. **null** if yfinance fails. |
| `status` | enum value `"closed"` | constant | Replaces `"open"`. |

### Invariants

- **`trade_id` is unique** (UUID4).
- **`order_id` is unique** within the project's lifetime (Alpaca guarantees).
- **One record per executed signal day.** The Entry task's `already_traded(symbol)` query is the dedup guard; it queries Alpaca (positions + open orders), not this file. If the file is out of sync with Alpaca, Alpaca wins.
- **Append-only at entry, in-place update at exit.** No deletes. No reorders.
- **`status` transitions: only `"open" → "closed"`.** No reverse, no other states.
- **`fill_qty` is fractional.** Notional sizing produces fractional shares; Alpaca supports them.
- **`exit_fill_qty == fill_qty`** (we sell exactly what we bought; no partial exits in Phase 1).
- **Benchmarks can be null;** the close record still persists. This is the non-raising close path.

### What this schema is **not**

- **Not a stable downstream contract.** No external consumer reads this file today. There is no schema versioning, no provenance hashes, no `schema_version` field. If a Phase 2 feature adds fields, existing rows won't have them — be defensive when reading old rows.
- **Not the dedup source of truth.** Alpaca is. See `already_traded` in [run_trading.py:28-38](../run_trading.py#L28-L38).
- **Not transactional.** A crash between writing the entry record and the next Pushover send leaves the record intact (entry succeeded); a crash before the SELL fills leaves the record at `status: "open"` (Exit task will retry on the next firing).

---

## Inbound — MICRO thesis schema (read-only)

This project reads `../tactical_markets/data/theses.jsonl` for entry signals. MICRO owns this contract; see [MICRO's docs/data-models.md](../../tactical_markets/docs/data-models.md) for the canonical schema. Summary of what this project actually depends on:

| Field | Type | Used by | Notes |
|---|---|---|---|
| `signal` | bool | `today_signal` in [run_trading.py:17-25](../run_trading.py#L17-L25) | Only records with `signal: true` are considered. |
| `as_of` | ISO 8601 string | `today_signal` (date filter), `submit_order` (passed through to `thesis_as_of`) | Used to filter to today's signal (UTC date). |
| `buy` | ticker string | `submit_order` | The long-leg ticker → submitted as Alpaca BUY. |
| `sell` | ticker string | `submit_order` | The thesis's short-leg. **Not traded** — preserved as `sell_leg` for benchmark capture. |
| `spread_pct` | float | Pushover message only | Display in the notification body. |

Fields the schema may include but **this project does not depend on**: any future `confidence`, `id`, `stop`, `target`, `hold_window_hours`, `signal_type`, `macro_context`. Per MICRO's integration-architecture doc, these are not surfaced today and may or may not land in future. Plan against today's schema.

---

## Inbound — MACRO `data/latest.json` (not consumed in Phase 1)

MACRO shipped a stable JSON sidecar (Brief 24, commit `2046161`). Contract documented in MACRO's [integration brief](../../market_dashboard/_bmad-output/planning-artifacts/integration-brief-for-tactical-bot.md). Phase 2 may read it for size-down logic when the regime band is red. Phase 1 does not.

Stable surfaces (per MACRO's brief):

- Band thresholds: 30/50/70 (green/yellow/orange/red)
- 11-bucket count
- 0–100 score scale
- `regime` enum: `low` / `mid` / `high` (VIX tercile, with hysteresis)
- `shock_type` enum: `fast_shock` / `slow_burn` / `recovery` / `calm` / `insufficient`
- `schema_version`, `weights_hash`, `code_sha` (use for provenance / refusal-to-trade guards)

Drift-prone surfaces (read from the sidecar, never hardcode):

- Bucket weights
- Per-indicator keys within a bucket
- `composite_regime_adj` formula caps

---

## Outbound — Alpaca order requests (write-only)

The bot does not publish APIs. Its outbound API calls to Alpaca use these `alpaca-py` request shapes:

### `MarketOrderRequest` (entry)

```python
MarketOrderRequest(
    symbol="XLE",
    notional=10_000,       # NOTIONAL constant; fractional shares via Alpaca
    side=OrderSide.BUY,
    time_in_force=TimeInForce.DAY,
)
```

[src/order_builder.py:27-33](../src/order_builder.py#L27-L33)

### `MarketOrderRequest` (exit)

```python
MarketOrderRequest(
    symbol=record["symbol"],
    qty=record["fill_qty"],    # exact share count from the entry fill
    side=OrderSide.SELL,
    time_in_force=TimeInForce.DAY,
)
```

[src/exit_manager.py:46-50](../src/exit_manager.py#L46-L50)

### `GetOrdersRequest` (idempotency check)

```python
GetOrdersRequest(status=QueryOrderStatus.OPEN)
```

[run_trading.py:35](../run_trading.py#L35)

---

## Outbound — Pushover messages

Two field POST: `title`, `message`. Recipients: `PUSHOVER_TOKEN` + `PUSHOVER_USER` from `.env`. No structured schema; plain-text strings only.

Notification matrix:

| Trigger | Title | Body |
|---|---|---|
| Entry success | `Entered <SYMBOL> $10,000` | `Filled <qty> @ $<price> \| Spread: <pct>% \| Exit: <YYYY-MM-DD>` |
| Entry failure | `Tactical Trading ENTRY FAILED` | `<exception message>` |
| Exit success | `Exited <SYMBOL> <±pct>%` | `P&L: $<dollars> \| SPY <pct>% \| <sell_leg> <pct>%` (benchmarks shown as `n/a` if null) |
| Exit per-trade failure | `Tactical Trading EXIT FAILED` | `<symbol> (trade <id_prefix>): <exception>` |
| Exit top-level crash | `Tactical Trading EXIT CRASHED` | `<exception message>` |

---

## Implicit constants

These live inline in modules; Phase 2 may externalize to a `config/` directory.

| Constant | Value | Module | Purpose |
|---|---|---|---|
| `NOTIONAL` | `10_000` | [src/order_builder.py:13](../src/order_builder.py#L13) | Per-trade dollar size. |
| `HOLD_DAYS` | `2` (lowered from 5 on 2026-05-13) | [src/trade_logger.py:21](../src/trade_logger.py#L21) — explicit module constant; used in `log_entry` via `add_trading_days(entry_time, HOLD_DAYS)` | NYSE trading days held. |
| `FILL_POLL_INTERVAL` | `2` (seconds) | [src/trade_logger.py:19](../src/trade_logger.py#L19) | Polling frequency on `wait_for_fill`. |
| `FILL_POLL_TIMEOUT` | `60` (seconds) | [src/trade_logger.py:20](../src/trade_logger.py#L20) | Max wait before raising. |
| `TERMINAL_FAILED` | `{REJECTED, CANCELED, EXPIRED}` | [src/trade_logger.py:16](../src/trade_logger.py#L16) | Fail-fast states in `wait_for_fill`. |
