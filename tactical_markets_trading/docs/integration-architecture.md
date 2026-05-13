# Integration Architecture

**Generated:** 2026-05-13. Documents this project's boundaries — sibling projects + external services.

`tactical_markets_trading` sits **downstream** of two sibling projects and **outbound** to four external services. There are five distinct contracts, all asymmetric: this project consumes more than it produces.

---

## Sibling projects

```
c:\Users\rekwa\ian_projects\
├── market_dashboard\           MACRO — strategic stress dashboard (11-bucket composite)
├── tactical_markets\           MICRO — premarket tactical signal generator
└── tactical_markets_trading\   THIS — Alpaca paper-trading execution layer
```

| Project | Owns | Status | This project's relationship |
|---|---|---|---|
| `market_dashboard` (MACRO) | Strategic regime call; 10y+ context | Production, daily 7:30 AM | **Not consumed in Phase 1.** Phase 2+ candidate input. |
| `tactical_markets` (MICRO) | Daily premarket tactical thesis | Week-1 live, daily 6:30 AM ET | **Consumed every Entry run** via `data/theses.jsonl`. |
| `tactical_markets_trading` (this) | Execution against MICRO theses | Phase 1 live, daily 8:35/8:40 AM CDT | — |

---

## Hard rule — no Python imports across sibling projects

This is the load-bearing architectural constraint that all three siblings enforce. Restated from MICRO's [project-context.md](../../tactical_markets/_bmad-output/project-context.md):

> No shared imports across the three sibling projects. `tactical_markets`, `market_dashboard`, and `tactical_markets_trading` integrate via files-on-disk, not Python imports. If you find yourself wanting `from market_dashboard.foo import bar`, stop and surface the design question.

Each project:
- Owns its own `.venv/`
- Owns its own dependencies (each `requirements.txt` / installed packages independent)
- Ships independently
- Integrates with siblings **only** through filesystem reads/writes

There is no shared library, no message queue, no DB, no IPC. The filesystem is the contract.

---

## Inbound contract — from MICRO (`tactical_markets`)

### Channel

**File-based, pull-mode.** This project reads `c:\Users\rekwa\ian_projects\tactical_markets\data\theses.jsonl` at every Entry run.

There is no push, no IPC, no streaming. We poll/tail the file via Windows Task Scheduler firing at 08:35 AM CDT (which is **after** MICRO's 6:30 AM ET signal generation has completed — MICRO writes between 6:30 and ~6:32 AM ET).

### Schema dependency

This project depends on a **subset** of MICRO's `theses.jsonl` schema:

| Field | Required | Behavior if missing |
|---|---|---|
| `signal` (bool) | Yes | Records without `signal: true` are skipped by `today_signal()`. |
| `as_of` (ISO 8601) | Yes | Used to filter to today's signal. Records with malformed `as_of` would crash `datetime.fromisoformat`. |
| `buy` (ticker string) | Yes for `signal: true` records | Submitted as the BUY ticker. |
| `sell` (ticker string) | Yes for `signal: true` records | Preserved for benchmark capture at exit. Not traded. |
| `spread_pct` (float) | Yes for `signal: true` records | Displayed in entry Pushover. Read at [run_trading.py:52,61](../run_trading.py#L52). |

**Fields this project does NOT depend on** (per MICRO's [integration-architecture.md](../../tactical_markets/docs/integration-architecture.md)):

- `id`, `confidence`, `signal_type`, `stop`, `target`, `hold_window_hours`, `historical_win_rate`, `theses` array envelope, `macro_context`, `schema_version`

If any of these are added in future, this project will silently ignore them.

### Cadence + freshness

- MICRO writes one new line per scheduled run (~daily, 6:30 AM ET, weekdays).
- Entry task reads at 08:35 AM CDT (= 9:35 AM ET) — comfortably after MICRO's write.
- `today_signal()` filters to records whose `as_of` UTC-date matches today's UTC date. If MICRO didn't run, no record matches → exit clean.
- The bot is tolerant of weekend/holiday gaps (no signal = no trade).

### Failure modes

| Failure | Detection | Handling |
|---|---|---|
| File missing | `open()` raises `FileNotFoundError` | Propagates up; Pushover "ENTRY FAILED". |
| File empty | `today_signal()` returns `None` | Exit clean, no order. |
| No `signal: true` line for today | `today_signal()` returns `None` | Exit clean, no order. |
| Malformed JSON line | `json.loads` raises | Propagates up; Pushover "ENTRY FAILED". |
| Missing required field on a signal-true line | `KeyError` | Propagates up; Pushover "ENTRY FAILED". |

---

## Inbound contract — from MACRO (`market_dashboard`) — **not consumed in Phase 1**

MACRO ships `data/latest.json` (Brief 24, commit `2046161`) as a stable downstream contract. Phase 1 does not read it. Phase 2 will, for regime size-down logic (e.g., halve `notional` when `regime == "high"` or `composite_band == "red"`).

When Phase 2 wires it up, the contract is documented in [MACRO's integration brief](../../market_dashboard/_bmad-output/planning-artifacts/integration-brief-for-tactical-bot.md). Highlights worth carrying forward:

### Stable surfaces (safe to bet on)

- `composite` in [0, 100]
- `composite_band` ∈ {`green`, `yellow`, `orange`, `red`}, thresholds 30/50/70
- `regime` ∈ {`low`, `mid`, `high`} (VIX-tercile classifier with hysteresis)
- `shock_type` ∈ {`fast_shock`, `slow_burn`, `recovery`, `calm`, `insufficient`}
- 11 buckets, bucket count locked
- `schema_version`, `weights_hash`, `code_sha` for provenance

### Validate-per-read (per MACRO's brief)

- `run_timestamp` < 26h old (else degrade safely).
- `weights_hash` matches a known-good list this project keeps. New hash → don't trade on bucket-weighted signals until reviewed.
- `stale_indicators` is empty or known-tolerable.
- `errors` is empty.
- `composite` in [0, 100].

### Drift-prone surfaces (don't hardcode; read from the sidecar)

- Bucket weights (recalibration pipeline exists; regime weighting may toggle after 2026-05-30 review).
- Indicator keys within a bucket (new ones get added; old ones can be dropped).
- `composite_regime_adj` formula caps.

---

## Outbound — Alpaca paper-trading API

### Channel

REST via `alpaca-py` Python SDK. Authenticated with `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` from `.env`. **`paper=True`** flag in `TradingClient` is the safety pin against accidental live trading.

### Surfaces used

| Operation | Module | Method |
|---|---|---|
| Auth (account verification, smoke test) | [src/alpaca_connector.py:25-37](../src/alpaca_connector.py#L25-L37) | `client.get_account()` |
| Submit entry order | [src/order_builder.py:34](../src/order_builder.py#L34) | `client.submit_order(MarketOrderRequest)` |
| Submit exit order | [src/exit_manager.py:45-50](../src/exit_manager.py#L45-L50) | `client.submit_order(MarketOrderRequest)` |
| Poll fill | [src/trade_logger.py:42](../src/trade_logger.py#L42) | `client.get_order_by_id(order_id)` |
| Idempotency check (positions) | [run_trading.py:32](../run_trading.py#L32) | `client.get_all_positions()` |
| Idempotency check (open orders) | [run_trading.py:35](../run_trading.py#L35) | `client.get_orders(GetOrdersRequest(status=OPEN))` |

### Failure modes

- Order REJECTED / CANCELED / EXPIRED → `wait_for_fill` raises `RuntimeError`. Caught at entrypoint, Pushover "ENTRY FAILED" / "EXIT FAILED".
- Network timeout → `requests`-level exception propagates up. Caught at entrypoint.
- API rate limiting → not observed; daily-frequency calls are well under any plausible limit.
- Symbol halted or otherwise unfillable → manifests as a non-FILLED terminal status; handled by the same rejection path.
- Insufficient buying power → REJECTED status; same handling.

---

## Outbound — Pushover

### Channel

HTTPS POST to `https://api.pushover.net/1/messages.json` with form-encoded `{token, user, title, message}`. 10s timeout.

### When fired

See the notification matrix in [data-models.md](./data-models.md#outbound--pushover-messages). Every entry, exit, and failure path notifies.

### Failure mode

Non-fatal by design. If `PUSHOVER_TOKEN` or `PUSHOVER_USER` is unset → prints `[pushover not configured]` and returns `False`. The trade still executes. This mirrors MICRO's pattern.

---

## Outbound — yfinance (benchmark capture)

### Channel

`yfinance.download(ticker, start, end, ...)` — Yahoo Finance free API, no auth.

### When called

At exit time only, **after** the SELL has filled. For SPY and the sell-leg ticker, over `[entry_time, exit_time_actual]`. [src/exit_manager.py:18-26](../src/exit_manager.py#L18-L26).

### Failure mode

`try/except Exception` in [src/exit_manager.py:68-74](../src/exit_manager.py#L68-L74). Any yfinance error (empty response, network failure, ticker change) leaves `spy_return_pct` / `sell_leg_return_pct` as `null` in the closed record. **The close itself still persists.** This is the non-raising close path designed in the 2026-05-08 hardening.

---

## Outbound — Windows Task Scheduler

Not a network contract, but a system-level integration. Three tasks registered via [setup_task.ps1](../setup_task.ps1):

| Task | Trigger | Action | Critical settings |
|---|---|---|---|
| Tactical Trading Wake | Daily 08:20 AM | `cmd.exe /c exit` | `-WakeToRun` (forces laptop wake), `-AllowStartIfOnBatteries`, `-DontStopIfGoingOnBatteries` |
| Tactical Trading Entry | Daily 08:35 AM | `.venv\Scripts\python.exe run_trading.py` | `-AllowStartIfOnBatteries`, `-DontStopIfGoingOnBatteries`, `-StartWhenAvailable` |
| Tactical Trading Exit | Daily 08:40 AM | `.venv\Scripts\python.exe src\exit_manager.py` | Same battery flags as Entry |

Battery flags **must be correct from the start** — a past session lost a fire on default battery behavior. Same gotcha was hit by MICRO and is now in their CLAUDE.md.

---

## Data flow diagram

```
                            ../tactical_markets/data/theses.jsonl       (MICRO produces)
                                       │
                                       ▼
   .env  ─►  run_trading.py  ─►  Alpaca paper API  ◄────────┐
                  │                                          │  poll fills
                  ├──────────► Pushover (entry / failure)    │  (alpaca-py)
                  │                                          │
                  └──────────► data/trades.jsonl             │
                                       │                    │
                                       ▼                    │
                   src/exit_manager.py ◄────────────────────┘
                                       │
                                       ├──► Alpaca paper API (SELL + fill poll)
                                       ├──► yfinance (SPY, sell_leg benchmarks)
                                       ├──► data/trades.jsonl (in-place close update)
                                       └──► Pushover (exit / failure)

Future (Phase 2+):

   ../market_dashboard/data/latest.json  ──►  run_trading.py  (size-down on red regime)
```

---

## What this project deliberately does **not** integrate with (Phase 1)

| Not integrated | Why |
|---|---|
| MACRO `data/latest.json` | Phase 1 stands alone. Phase 2 candidate (size-down logic). |
| Any of MICRO's other outputs (only `theses.jsonl` is consumed; MICRO doesn't have other outputs anyway) | n/a |
| Email, SMS, Slack | Pushover only. |
| Live (non-paper) Alpaca | Hard gate: 50+ paper trades + rules-of-engagement doc required before live. |
| Tax-reporting service | Out of scope Phase 1. PRD describes a CSV export feature for Phase 2+. |
| Portfolio analytics dashboards | Out of scope. Phase 2+ may add a status read-only HTML. |
| GitHub Actions / CI | This project doesn't have its own CI; the cross-sibling repo at `_genai_tmp/` may have shared CI. |

---

## Cross-project repo layout

All three siblings live under one git repo at `c:\Users\rekwa\ian_projects\_genai_tmp\` (the "two-repo workflow"). Their primary editing directories (`market_dashboard/`, `tactical_markets/`, `tactical_markets_trading/`) are **edit-only mirrors**. See [development-guide.md](./development-guide.md) for the commit dance.

This matters for integration because:
- A commit can touch multiple siblings in one operation (e.g., MICRO publishes a new field + this project reads it).
- `git log --oneline -- tactical_markets_trading/` lets you see all this project's commits across the shared repo.
- The remote is `https://github.com/IanRekward/GenAI_Messing.git`, branch `main`.

---

## Summary

| Direction | Partner | Channel | Stability |
|---|---|---|---|
| Inbound | MICRO `theses.jsonl` | Filesystem, JSONL append | Schema today is minimal; richer fields may land per MICRO's roadmap |
| Inbound | MACRO `data/latest.json` | Filesystem, JSON | Stable contract (Brief 24); **not yet consumed** |
| Outbound | Alpaca paper API | REST via `alpaca-py` | SDK-stable; depend on it |
| Outbound | Pushover | HTTPS form POST | Non-fatal; trade succeeds even if Pushover doesn't |
| Outbound | yfinance | yfinance library | Non-fatal at exit; can leave benchmarks null |
| Outbound | Windows Task Scheduler | OS-level tasks | Stable; battery flags must remain correct |
