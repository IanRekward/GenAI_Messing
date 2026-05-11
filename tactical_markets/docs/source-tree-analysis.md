# Source Tree Analysis — tactical_markets

```
c:\Users\rekwa\ian_projects\tactical_markets\
├── run_tactical.py                  # entrypoint (47 LOC)
├── setup_task.ps1                   # Windows Task Scheduler registration
├── CLAUDE.md                        # persistent agent instructions (canonical)
├── TODO.md                          # locked week-1 design + status (canonical)
├── ROADMAP_SIGNAL_GENERATION.md     # preserved v2 spec context (superseded)
├── RESEARCH_SUMMARY.md              # empirical research grounding signal design
├── DESIGNER_PROMPT.md               # designer-mode prompt for Opus design passes
├── README.md                        # outdated framing (see Project Overview)
├── src/
│   ├── sector_rotation.py           # pure-function signal generator (100 LOC)
│   └── pushover.py                  # minimal Pushover client (20 LOC)
├── config/
│   ├── universe.yaml                # 9 SPDR sectors + 3 broad indices
│   └── thresholds.yaml              # spread_pct, momentum_window, ma_window, hold_days
├── data/
│   └── theses.jsonl                 # append-only run log (signal + no-signal + errors)
├── docs/                            # this directory (generated documentation)
├── .env                             # PUSHOVER_TOKEN, PUSHOVER_USER (gitignored)
├── _bmad/                           # BMad skill installation
├── _bmad-output/                    # BMad workflow outputs (separate from docs/)
└── .claude/                         # Claude Code skill installs
```

## File-by-file

### `run_tactical.py` — entry point

47 lines. Loads `.env`, calls `sector_rotation.generate`, handles the boundary (yfinance failures), prints to stdout, calls Pushover, appends to JSONL.

Key lines:
- [run_tactical.py:21-31](../run_tactical.py#L21-L31) — yfinance boundary: catch any exception from `generate`, log error record, return cleanly.
- [run_tactical.py:33-39](../run_tactical.py#L33-L39) — signal path: print + Pushover + record.
- [run_tactical.py:41-42](../run_tactical.py#L41-L42) — every run (including no-signal and error days) writes one JSONL line.

### `src/sector_rotation.py` — signal generator

100 lines, one public function. Returns `dict` on signal or `None` on no-signal.

Key lines:
- [src/sector_rotation.py:10-15](../src/sector_rotation.py#L10-L15) — `_NAMES` ticker → display name map.
- [src/sector_rotation.py:18-86](../src/sector_rotation.py#L18-L86) — `generate(universe_path, thresholds_path)`.
- [src/sector_rotation.py:29-30](../src/sector_rotation.py#L29-L30) — yfinance fetch with lookback derived from `ma_window` (~42 calendar days for 20 trading days).
- [src/sector_rotation.py:43-49](../src/sector_rotation.py#L43-L49) — momentum rank + spread.
- [src/sector_rotation.py:51-52](../src/sector_rotation.py#L51-L52) — **spread gate** (returns None if below threshold).
- [src/sector_rotation.py:54-58](../src/sector_rotation.py#L54-L58) — **trend gate**: buy-side must be above 20d MA. The comment here explains why (don't trade against longer trend); this is the kind of "why is non-obvious" comment CLAUDE.md endorses.
- [src/sector_rotation.py:66-73](../src/sector_rotation.py#L66-L73) — `thesis` string assembly (free-form, human-readable; the trading bot should treat the structured fields as authoritative and the `thesis` string as display-only).
- [src/sector_rotation.py:75-86](../src/sector_rotation.py#L75-L86) — return dict; see [data-models.md](./data-models.md) for field-by-field.
- [src/sector_rotation.py:89-99](../src/sector_rotation.py#L89-L99) — inline `__main__` smoke run (CLAUDE.md: "inline `__main__` smoke run is sufficient" in week 1).

### `src/pushover.py` — delivery

20 lines. POST to Pushover API. Returns `bool`. Never raises.

Key lines:
- [src/pushover.py:7-9](../src/pushover.py#L7-L9) — missing env vars return False silently. **Note:** this is the correct boundary behavior, but the run still proceeds — see `run_tactical.py:36` for how the failure is surfaced.
- [src/pushover.py:12-18](../src/pushover.py#L12-L18) — 10 s timeout, broad exception → False.

### `config/universe.yaml`

```yaml
sectors:  [XLK, XLF, XLE, XLI, XLV, XLY, XLC, XLU, XLRE]
broad:    [IWM, QQQ, SPY]
```

12 tickers total. Adding or removing a ticker is a pure-config change — no code edit required.

### `config/thresholds.yaml`

```yaml
spread_pct: 1.5       # publish gate
momentum_window: 5    # trading days
ma_window: 20         # trading days
hold_days: 5          # lower bound; upper bound = hold_days + 2 in thesis text
```

Two-week freeze rule applies here. Don't tune mid-window.

### `data/theses.jsonl`

Sample contents (live as of 2026-05-11):

```jsonl
{"signal": true, "buy": "XLK", "sell": "XLE", "buy_momentum_pct": 8.43, "sell_momentum_pct": -5.35, "spread_pct": 13.79, "buy_price": 175.52, "buy_ma": 158.77, "thesis": "XLK (Technology) +8.4% vs XLE (Energy) -5.4% over 5 days...", "as_of": "2026-05-11T11:30:10.514070+00:00"}
{"signal": false, "error": "yfinance down", "as_of": "2026-05-06T12:22:58.091098+00:00"}
```

Empirically: signal has fired ~daily for the past 5 days, mostly `XLK > XLE` rotation, with one captured yfinance failure on 2026-05-06.

### `setup_task.ps1`

Registers two Windows scheduled tasks:

1. **Tactical Markets Wake** at 06:20 — wakes the laptop 10 minutes before the main task. Action is `cmd.exe /c exit` (no-op; the side effect is the wake).
2. **Tactical Markets** at 06:30 — runs `python run_tactical.py` in the project working dir.

Both use `-StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries`. CLAUDE.md refers to these by their underlying property names (`DisallowStartIfOnBatteries=false`, `StopIfGoingOnBatteries=false`, `StartWhenAvailable=true`) — same settings, different surface. The wake task adds `-WakeToRun`.

Battery flags are correct on first registration — important because CLAUDE.md flags this as easy to get wrong.
