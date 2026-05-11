# Architecture — tactical_markets

## Architecture pattern

**Single-entrypoint batch CLI.** No daemon, no API, no event loop. The Windows scheduler invokes `python run_tactical.py` once a day; the process pulls data, computes one signal, logs it, optionally sends one Pushover message, and exits.

## Daily flow

```
06:20 ET   Tactical Markets Wake task          -> wakes laptop
06:30 ET   Tactical Markets task               -> launches python run_tactical.py
           run_tactical.main()
             load_dotenv(.env)
             sector_rotation.generate(universe.yaml, thresholds.yaml)
               yf.download(12 tickers, lookback=~42 calendar days)
               pandas: closes, 5d momentum, 20d MA
               rank, spread check (>= 1.5%), trend confirmation
               -> dict (signal) OR None (no signal)
             if dict:
               print(thesis); pushover.send(title, thesis)
             append one JSON line to data/theses.jsonl
           process exits
```

The whole pipeline runs in a few seconds on a warm network.

## Components

### Entry point — `run_tactical.py`

50 lines. Three responsibilities:

1. Load `.env`, resolve config paths.
2. Call `sector_rotation.generate`. On exception, log `{"signal": false, "error": str(exc), ...}` and return — this is the **boundary** for yfinance failures (CLAUDE.md: "validate only at boundaries"). See `theses.jsonl` line 4 for the live `"yfinance down"` example.
3. On signal: print to stdout, call `pushover.send`. Always: append the result (signal or no-signal record) to `data/theses.jsonl`.

Pushover failure does **not** abort the run — `pushover.send` returns `bool` and the result is reported in stdout, but the JSONL record is still written.

### Signal generator — `src/sector_rotation.py`

Pure function `generate(universe_path, thresholds_path) -> dict | None`. No I/O side effects beyond `yfinance.download`. Returns `None` to mean "no signal today"; returns a dict when both gates pass.

**Two gates:**
1. **Spread gate** — top vs bottom 5-day momentum must exceed `spread_pct` (1.5%).
2. **Trend gate** — buy-side ticker must be above its 20-day moving average. Don't trade against the longer trend.

**Why this shape:** Both gates derive from the published mean-reversion edge (Sharpe 0.92, TSX 60, 2000–2025; see [RESEARCH_SUMMARY.md](../RESEARCH_SUMMARY.md)). The 1.5% spread is a starting hypothesis, not a fitted parameter — it is treated as frozen for the calibration window.

### Pushover client — `src/pushover.py`

20 lines. POSTs to `https://api.pushover.net/1/messages.json`. Returns `True` on HTTP 200, `False` otherwise — including missing env vars or exception. Never raises into the caller.

### Configuration — `config/*.yaml`

- `universe.yaml`: 9 SPDR sector ETFs (XLK, XLF, XLE, XLI, XLV, XLY, XLC, XLU, XLRE) + 3 broad indices (IWM, QQQ, SPY). Total 12 tickers.
- `thresholds.yaml`: `spread_pct: 1.5`, `momentum_window: 5`, `ma_window: 20`, `hold_days: 5`.

**Rule:** Publish gates and time windows are config-driven. Never hardcode these inside `src/`. The whole point of two-week freezes is that thresholds remain visible and adjustable as data.

### Persistence — `data/theses.jsonl`

Append-only. One JSON object per line, one record per run, including no-signal days and error days. Records are never rewritten — historical no-signal days are part of the calibration record Ian is reading.

See [data-models.md](./data-models.md) for the record schema (this is the trading-bot consumption contract).

## Scope boundaries — locked

Cut from week 1 (per [TODO.md](../TODO.md), 2026-05-05 design pass):

| Item | Status | Why deferred |
|---|---|---|
| VIX slope signal | Cut | Adds a second signal before the first is validated by lived exposure |
| Overnight gap detection | Cut | Same |
| Credit-spread macro context | Cut | Same; also adds FRED dependency |
| Confidence scoring formula | Cut | Replaced by binary publish gate (spread >= 1.5%) |
| HTML dashboard | Cut | Pushover-only is enough to evaluate signal quality on phone |
| Multi-thesis JSON envelope | Cut | One thesis per day max; current schema is per-record |
| Backtest framework | Cut | Published Sharpe 0.92 is treated as starting hypothesis, not re-derived |
| Tests directory | Cut | Inline `__main__` smoke run sufficient at this surface area |
| `market_dashboard` composite consumption | Cut | Standalone in week 1; week-3+ may consume composite as macro context |

Re-opening any of these requires explicit user sign-off per CLAUDE.md.

## Dependencies

Runtime, all system-installed:
- `yfinance` (Yahoo Finance scrape, free)
- `pandas`
- `pyyaml`
- `requests`
- `python-dotenv`

Standard library: `datetime`, `pathlib`, `json`, `os`, `__future__.annotations`.

External services:
- **Yahoo Finance** — primary market data. Unmonitored, free, no SLA. Failure mode handled at boundary in `run_tactical.py`.
- **Pushover** — delivery. Failure is logged in stdout but does not abort.

No database. No HTTP server. No queue. No secrets manager (only `.env`).

## Architectural decisions that look surprising but are deliberate

1. **No venv.** Week-1 toolchain is small enough that system Python is fine. Per CLAUDE.md: "Day 1–2 can use system Python (yfinance is already installed system-wide)." A `.venv/` will be added when surface area justifies it.
2. **No tests directory.** Same reason. `sector_rotation.py` has an inline `__main__` smoke run. Adding `tests/` now would be premature ceremony.
3. **No error retries on yfinance.** A daily premarket run can miss one day cleanly — the JSONL records the error and Ian sees no notification. Better than partial-data signals.
4. **Pushover failure is non-fatal.** The signal still ran successfully; the delivery layer failed. Stdout surfaces the failure; the next run is fresh.
5. **Append-only JSONL, not SQLite.** The trading bot will read this file; a plain JSONL is the simplest cross-project contract (no migrations, no concurrent-writer concerns since exactly one process writes per day).
6. **Module structure is files-on-disk only.** No Python imports across `tactical_markets`, `market_dashboard`, `tactical_markets_trading`. See [integration-architecture.md](./integration-architecture.md).
