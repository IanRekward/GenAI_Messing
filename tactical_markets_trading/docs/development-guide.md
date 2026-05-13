# Development Guide

**Generated:** 2026-05-13. How to run, edit, commit, and operate this project.

---

## Prerequisites

- **Windows** (the project uses Windows Task Scheduler for cadence; not portable to Linux/macOS without rework)
- **Python 3.14** (system interpreter or via Microsoft Store)
- **Git** + the two-repo layout already set up at `c:\Users\rekwa\ian_projects\_genai_tmp\`
- **Alpaca paper account** with API keys (free)
- *(Optional)* Pushover account + tokens for notifications

---

## One-time setup

### 1. Create the venv (Phase 1 is already on Python 3.14)

```powershell
cd c:\Users\rekwa\ian_projects\tactical_markets_trading
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

The project has no `requirements.txt` checked in; deps were installed ad-hoc during Phase 1 build. The current set is:

```powershell
pip install alpaca-py python-dotenv yfinance pandas-market-calendars requests
```

(`pandas`, `numpy`, etc. come transitively via the above.)

### 3. Configure `.env`

Create `.env` at the project root (`tactical_markets_trading/.env`). **Never commit.**

```ini
ALPACA_API_KEY=PK_xxx
ALPACA_SECRET_KEY=xxx
ALPACA_BASE_URL=https://paper-api.alpaca.markets
PUSHOVER_TOKEN=axxx
PUSHOVER_USER=uxxx
```

`ALPACA_BASE_URL` is read by some `alpaca-py` integrations but the project uses the SDK's `paper=True` flag in [src/alpaca_connector.py:22](../src/alpaca_connector.py#L22) as the authoritative paper-vs-live switch. Keep them aligned.

`.env` is gitignored at the root `.gitignore`.

### 4. Smoke-test Alpaca auth

```powershell
.\.venv\Scripts\python.exe src\alpaca_connector.py
```

Prints account number, status, cash, buying power. If this fails, fix `.env` before anything else.

### 5. Register the Windows Scheduled Tasks

```powershell
PowerShell -ExecutionPolicy Bypass -File .\setup_task.ps1
```

Registers `Tactical Trading Wake` (08:20), `Tactical Trading Entry` (08:35), `Tactical Trading Exit` (08:40) — all CDT, daily. Safe to re-run (uses `-Force`).

**Battery flags must stay correct.** Verify with:

```powershell
foreach ($name in @("Tactical Trading Wake", "Tactical Trading Entry", "Tactical Trading Exit")) {
    (Get-ScheduledTask -TaskName $name).Settings |
        Select-Object DisallowStartIfOnBatteries, StopIfGoingOnBatteries, StartWhenAvailable, WakeToRun
}
```

Required values:

- `DisallowStartIfOnBatteries = False`
- `StopIfGoingOnBatteries = False`
- `StartWhenAvailable = True`
- `WakeToRun = True` (Wake task only)

If you ever see `DisallowStartIfOnBatteries = True`, the task will silently skip on battery and only `NumberOfMissedRuns` reveals it (not `LastTaskResult`).

---

## Daily run cadence

| Time (CDT) | Trigger | Effect |
|---|---|---|
| 06:30 ET | MICRO writes today's thesis to `../tactical_markets/data/theses.jsonl` (this is upstream — not on this project's schedule) |
| 08:20 CDT | Wake task | Forces laptop awake |
| 08:35 CDT | Entry task | Reads MICRO signal, submits BUY, logs entry, Pushover |
| 08:40 CDT | Exit task | Closes any ripe positions, logs exit + benchmarks, Pushover |

There is **no** intraday execution. The bot is dormant outside the 08:20–08:40 window each weekday.

---

## Running things manually

### Run the entry path manually

```powershell
.\.venv\Scripts\python.exe run_trading.py
```

Same as the scheduled Entry task. Idempotent — if there's already an open position or order in today's signal symbol, it skips. Useful for catching up after a missed scheduled run.

### Run the exit path manually

```powershell
.\.venv\Scripts\python.exe src\exit_manager.py
```

Closes any open positions past `exit_time_planned`. Also idempotent — already-closed records are skipped.

### Verify account state

```powershell
.\.venv\Scripts\python.exe src\alpaca_connector.py
```

Prints account summary.

### Check the trade ledger

```powershell
Get-Content data\trades.jsonl
```

Each line is one trade record. See [data-models.md](./data-models.md) for the schema.

---

## Two-repo git workflow

This is the load-bearing, easy-to-get-wrong workflow shared with MICRO and MACRO.

**The primary working directory (`tactical_markets_trading/`) is edit-only.** The git repo lives at `c:\Users\rekwa\ian_projects\_genai_tmp\`, which contains all three siblings as subdirectories.

Every commit sequence:

1. Edit files in the primary directory.
2. **Copy changed files into the git mirror:**
   ```powershell
   Copy-Item tactical_markets_trading\<path> ..\_genai_tmp\tactical_markets_trading\<path>
   ```
3. **Prefix every git command** with the `_genai_tmp` cwd:
   ```bash
   cd /c/Users/rekwa/ian_projects/_genai_tmp && git status
   cd /c/Users/rekwa/ian_projects/_genai_tmp && git add tactical_markets_trading/src/foo.py
   cd /c/Users/rekwa/ian_projects/_genai_tmp && git commit -m "..."
   ```
   Bash tool cwd does **not** persist between calls — prefix every time.
4. **Use HEREDOC commit messages** with the running model's co-author trailer:
   ```
   Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
   Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
   ```
5. **Stage with specific paths.** Never `git add .` or `git add -A` — the repo contains MICRO + MACRO + this project. Blanket adds pull in unrelated work.
6. `warning: LF will be replaced by CRLF` is harmless Windows line-ending noise. Don't touch `.gitattributes`.
7. **Remote:** `https://github.com/IanRekward/GenAI_Messing.git`, branch `main`. Push is **pre-authorized** for this repo.

---

## Coding style (mirrors MICRO + MACRO)

- **No comments** unless the WHY is non-obvious (a hidden constraint, a subtle invariant, a workaround for a specific bug). Don't explain WHAT the code does.
- **No extra abstractions** beyond what the task requires. Three similar lines beats a premature helper.
- **No half-finished implementations.** Ship complete or don't ship.
- **No error handling for impossible scenarios.** Trust internal guarantees. Validate only at system boundaries: Alpaca, yfinance, Pushover, MICRO's `theses.jsonl`.
- **No backwards-compatibility shims** for unused fields, renamed-but-still-exported names, etc. If something's unused, delete it.
- **Security:** no command injection, no hardcoded secrets. All secrets via `.env`. Push is pre-authorized but force-push still requires user sign-off.

---

## Project-specific don't-miss rules

- **`paper=True` is the safety pin.** Do NOT remove it from [src/alpaca_connector.py:22](../src/alpaca_connector.py#L22) without explicit user sign-off. Phase 3 (live capital) is gated on 50+ paper trades + a written rules-of-engagement document — code change alone is not sufficient.
- **No cross-sibling Python imports.** `from market_dashboard.foo import bar` or `from tactical_markets.signal import ...` is forbidden. Use files-on-disk integration. See [integration-architecture.md](./integration-architecture.md).
- **No shorts, ever.** Long-only or cash only. Durable user preference. Any pair-trade or short-leg reference in the PRD is non-viable.
- **Phase 1 is frozen** until 5+ trades execute cleanly (lowered from 10 on 2026-05-13). No code changes during freeze. The TODO.md "Locked rules" table is the source of truth.
- **Don't silently downgrade Alpaca errors.** They're a boundary — catch at the entrypoint ([run_trading.py:68-71](../run_trading.py#L68-L71), [src/exit_manager.py:115-119](../src/exit_manager.py#L115-L119)), Pushover the failure, and re-raise so Task Scheduler logs a non-zero exit.
- **Don't delete or rewrite past `data/trades.jsonl` rows.** Append-only for entries; in-place update only to flip `status: "open" → "closed"`. Historical rows are the validation record.
- **Authoritative dedup is Alpaca, not the local file.** `already_traded_today` (intra-day) + `at_position_limit` (5-position cap) in [run_trading.py:28-53](../run_trading.py#L28-L53) both query Alpaca. Don't shortcut to reading `trades.jsonl` — it lags if logging ever fails. *(Original `already_traded(symbol)` was replaced 2026-05-13 — was over-strict relative to original 5-overlapping-positions design.)*

---

## Common development tasks

### Adding a new dependency

```powershell
.\.venv\Scripts\Activate.ps1
pip install <package>
```

There's no `requirements.txt` to update. If we ever add one, also document it here.

### Re-registering the scheduled tasks (after editing `setup_task.ps1`)

```powershell
PowerShell -ExecutionPolicy Bypass -File .\setup_task.ps1
```

Safe — uses `-Force`. Re-verify battery flags afterward.

### Checking scheduled task fire history

```powershell
Get-WinEvent -LogName Microsoft-Windows-TaskScheduler/Operational `
    -MaxEvents 50 |
    Where-Object { $_.Message -match "Tactical Trading" }
```

### Inspecting recent Alpaca activity

```powershell
.\.venv\Scripts\python.exe -c "from src.alpaca_connector import trading_client; c = trading_client(); print(c.get_account()); print([str(p) for p in c.get_all_positions()])"
```

### Smoke-testing a single module

Most modules have an `if __name__ == "__main__":` block:

- [src/alpaca_connector.py](../src/alpaca_connector.py) — prints account summary
- [src/order_builder.py](../src/order_builder.py) — reads latest signal, submits order (THIS WILL TRADE — use with care)
- [src/exit_manager.py](../src/exit_manager.py) — same as the scheduled Exit task

`trade_logger.py` had a stale `__main__` block removed in the 2026-05-08 hardening pass — don't reintroduce it.

---

## Testing strategy (Phase 1)

Phase 1 deliberately ships **no tests directory**. The justifications:

- Surface area is small (5 modules + 1 entrypoint).
- The genuine risk is Alpaca API behavior on production firings, not unit-test-able branches. The 2026-05-08 partial-fill bug (`wait_for_fill` returning on `filled_at != None` instead of `status == FILLED`) was only discoverable by running against the real API.
- Inline `__main__` smoke runs cover the high-value paths.

**Phase 2 should add tests** once the surface area justifies them — particularly around stops, sizing rules, and the eventual MACRO consumption logic.

---

## Mid-task handoffs

If a session ends mid-implementation (context limit, interruption), before the last message append a `## Mid-task handoff` section to [TODO.md](../TODO.md) with:

1. Which task/brief you were on.
2. What's done (file list + behavior shipped).
3. What's next — the literal next step in concrete terms.
4. Any gotchas you hit but didn't write up yet.

Delete the section when the next session picks up and completes the work.

---

## Where to look when something breaks

| Symptom | First look |
|---|---|
| No entry fired today | Windows Task Scheduler "Last Run Result" for `Tactical Trading Entry`; battery flag check |
| Entry fired but failed | Pushover for "ENTRY FAILED" + stderr; check `.env`; check Alpaca account status |
| Exit didn't fire | Same — Task Scheduler check, then read `data/trades.jsonl` for stranded open records |
| `data/trades.jsonl` out of sync with Alpaca | Truth is Alpaca. Run `src/alpaca_connector.py` to see positions; manually reconcile or restart from scratch (paper account; can be wiped) |
| Pushover stopped working | Pushover token validity; rate limits (Pushover has a 10k/month free tier) |
| `theses.jsonl` not updating | Check MICRO's status — it's a separate scheduled task on the same machine |
| `pandas_market_calendars` missing dates | NYSE holiday calendar may need a library update; verify `mcal.get_calendar("NYSE").valid_days(...)` returns the expected dates |
