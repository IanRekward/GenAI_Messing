# Data Models — `theses.jsonl` schema

**This is the cross-project consumption contract.** `tactical_markets_trading` (and any other downstream tool) reads `data/theses.jsonl` and must handle every record shape documented below.

## Storage

- Path: `data/theses.jsonl`
- Format: JSON Lines (one JSON object per line, trailing newline after each).
- Encoding: UTF-8.
- Append-only. Records are never rewritten. Historical no-signal days are part of the calibration record.
- Writer: exactly one process at a time (the daily 6:30 AM scheduled run). No concurrent-writer concerns.
- Retention: indefinite. No rotation policy. Expect file size to grow ~1 KB/day.

## Record types

There are **three** record shapes. A consumer must branch on `signal` first, then on `error`.

### 1. Signal record (`signal == true`)

```json
{
  "signal": true,
  "buy": "XLK",
  "sell": "XLE",
  "buy_momentum_pct": 8.43,
  "sell_momentum_pct": -5.35,
  "spread_pct": 13.79,
  "buy_price": 175.52,
  "buy_ma": 158.77,
  "thesis": "XLK (Technology) +8.4% vs XLE (Energy) -5.4% over 5 days. Spread: 13.8%. Signal: rotate 5-10% from XLE -> XLK. Hold 5-7 days. XLK above 20d MA ($175.52 vs $158.77), trend confirmed.",
  "as_of": "2026-05-11T11:30:10.514070+00:00"
}
```

| Field | Type | Meaning |
|---|---|---|
| `signal` | `bool` (always `true`) | Discriminator. |
| `buy` | `str` | Ticker to add exposure to. One of the 12 universe tickers (`XLK XLF XLE XLI XLV XLY XLC XLU XLRE IWM QQQ SPY`). |
| `sell` | `str` | Ticker to reduce exposure on. Same universe. |
| `buy_momentum_pct` | `float` (percentage, e.g. 8.43 means +8.43%) | Top-of-rank momentum over `momentum_window` (currently 5) trading days. |
| `sell_momentum_pct` | `float` | Bottom-of-rank momentum, same window. May be negative. |
| `spread_pct` | `float` | `buy_momentum_pct - sell_momentum_pct`. Always >= the configured `spread_pct` gate (currently 1.5). |
| `buy_price` | `float` | Most recent close for `buy`, USD. |
| `buy_ma` | `float` | `ma_window`-day (currently 20) trailing mean close for `buy`, USD. Always less than `buy_price` (trend gate). |
| `thesis` | `str` | Human-readable summary. **Display only.** Do not parse to recover structured fields — use the structured columns. |
| `as_of` | `str` (ISO 8601 with `+00:00` offset) | UTC timestamp when the record was generated. Microsecond precision. |

**Implicit hold window:** The text says "Hold 5-7 days" — this comes from `thresholds.yaml` (`hold_days: 5`, upper bound = `hold_days + 2`). Not in the structured fields. A consumer needing it should read `config/thresholds.yaml` directly.

**Implicit suggested size:** The text says "rotate 5-10%" — currently a static phrase, **not** a per-record computation. Do not parse it for size.

### 2. No-signal record (`signal == false`, no `error`)

```json
{
  "signal": false,
  "as_of": "2026-05-12T11:30:00.000000+00:00"
}
```

Emitted when either the spread gate or the trend gate fails. Consumer action: **no rotation**. The day was scanned cleanly.

**Caveat:** The current code in [run_tactical.py:39](../run_tactical.py#L39) only writes this exact shape when `generate` returns `None` *and* the result variable is reassigned — verify behavior matches before relying on field absence.

### 3. Error record (`signal == false`, `error` present)

```json
{
  "signal": false,
  "error": "yfinance down",
  "as_of": "2026-05-06T12:22:58.091098+00:00"
}
```

Emitted when `sector_rotation.generate` raised an exception (yfinance failure, insufficient data, network outage, etc.). Consumer action: **no rotation, no inference**. The day's data is missing, not "no signal".

**Important distinction for the trading bot:** An error record is *not* the same as a no-signal record. A no-signal record means "the system looked and saw nothing actionable". An error record means "the system could not look". Treating them as equivalent would silently swallow data outages.

### Record-type decision tree for consumers

```
record = json.loads(line)
if record["signal"] is True:
    rotate(buy=record["buy"], sell=record["sell"], ...)
elif "error" in record:
    skip_and_alert(record["error"], record["as_of"])
else:
    skip_silently(record["as_of"])
```

## What the schema deliberately does **not** include

Items the v2 ROADMAP envisioned but week-1 deliberately omits (per the 2026-05-05 design pass — see [architecture.md](./architecture.md#scope-boundaries--locked)):

- `id` — no per-thesis identifier. Use `as_of` if you need a key.
- `signal_type` — only sector rotation exists; this field is implicit. Will be needed when a second signal type lands.
- `confidence` — replaced by binary publish gate.
- `entry_logic`, `historical_win_rate` — not surfaced.
- `stop`, `target` — not computed. Trading bot must derive these from its own risk policy.
- `hold_window_hours` — only in the `thesis` string, not structured.
- `qty`, `position_size` — not computed. "Rotate 5–10%" is display text, not a number.
- `macro_context` block (VIX, credit spreads) — not collected in week 1.
- `id` per thesis or `theses` array — schema is one-thesis-per-line, not an envelope.

A future schema migration is expected (likely when the second signal type lands). The migration path is: introduce `signal_type` (default `"sector_rotation"` for backfill), introduce a `theses` array envelope, add `id` per thesis. Until that happens, downstream consumers should treat the current schema as authoritative and not pre-implement v2 fields.

## Schema versioning

There is **no schema version field** in the current records. Consumers must inspect record shape directly.

When migration happens, the new format will likely include a `schema_version` field. Until then, the absence of `schema_version` itself implicitly identifies v1.

## Cadence

- Expected: 1 new line per weekday at ~11:30 UTC (EST) or ~10:30 UTC (EDT).
- Weekends/US holidays: no run (Windows scheduler still fires, but `yfinance` returns stale data; the trend gate or spread gate may still produce a signal — currently the code does **not** check for trading-day membership).
- Empirical: review `theses.jsonl` for actual cadence. As of 2026-05-11, ~5 consecutive daily records, with one error record captured on 2026-05-06.

## What a downstream consumer (e.g., `tactical_markets_trading`) needs

Minimum viable consumer logic:

1. **Tail the file.** Read new lines as they appear. Do not re-process old ones — `as_of` uniquely identifies a record.
2. **Branch on record type.** Use the decision tree above.
3. **Apply own risk policy.** The thesis does not include stop, target, or position size. The trading layer owns sizing (per [RESEARCH_SUMMARY.md](../RESEARCH_SUMMARY.md): fixed 2% risk per trade, max 5% per position, max 20% open).
4. **Derive hold window from config.** Read `config/thresholds.yaml` if the bot needs the exit timer. Currently `hold_days: 5` so exit after ~5–7 trading days.
5. **Treat `thesis` as display only.** Render it to the user, but compute trades from structured fields.
6. **Differentiate error from no-signal.** Alert on `error`; quietly skip on `signal: false` without `error`.

See [integration-architecture.md](./integration-architecture.md) for full integration contract.
