# Development Guide — tactical_markets

## Prerequisites

- **Windows** (host OS — scheduler is Windows-specific).
- **Python 3.14** at `C:\Users\rekwa\AppData\Local\Python\pythoncore-3.14-64\python.exe` (path is hardcoded in `setup_task.ps1`). System install, not a venv.
- System-wide packages: `yfinance`, `pandas`, `pyyaml`, `requests`, `python-dotenv`.
- **Pushover credentials** in `.env` at the project root:
  ```
  PUSHOVER_TOKEN=...
  PUSHOVER_USER=...
  ```

No virtual environment in week 1 (per CLAUDE.md). When week-2+ work demands it, create `tactical_markets/.venv/`. Do not reuse `market_dashboard`'s venv.

## Run it manually

```powershell
cd C:\Users\rekwa\ian_projects\tactical_markets
python run_tactical.py
```

Smoke-only:

```powershell
python -m src.sector_rotation
```

The latter prints the thesis (or "No sector rotation signal today...") and exits without writing to `theses.jsonl` or sending Pushover.

## Install the daily scheduler

One-time, no admin required:

```powershell
.\setup_task.ps1
```

Re-running is idempotent (`-Force` on `Register-ScheduledTask`). Two tasks are registered:

- `Tactical Markets Wake` at 06:20 ET (wakes laptop)
- `Tactical Markets` at 06:30 ET (runs the script)

Verify:

```powershell
Get-ScheduledTask -TaskName "Tactical Markets"
Get-ScheduledTaskInfo -TaskName "Tactical Markets"   # last/next run
```

`theses.jsonl` is the live indicator that the schedule is firing. Expected cadence: one new line per weekday at ~11:30 UTC (EST) or ~10:30 UTC (EDT).

## Edit / commit — two-repo workflow

**Critical.** The primary working dir (`tactical_markets/`) is **edit-only**. The git repo lives at `c:\Users\rekwa\ian_projects\_genai_tmp\`. Every commit follows this sequence (per [CLAUDE.md](../CLAUDE.md)):

```bash
# 1. Edit in primary
# 2. Copy changed files
cp tactical_markets/<path> _genai_tmp/tactical_markets/<path>

# 3. Prefix every git command (Bash cwd does not persist between calls)
cd /c/Users/rekwa/ian_projects/_genai_tmp && git status

# 4. Stage specific paths (NEVER git add . — the repo contains other projects)
cd /c/Users/rekwa/ian_projects/_genai_tmp && git add tactical_markets/<path>

# 5. HEREDOC commit message with model co-author trailer
cd /c/Users/rekwa/ian_projects/_genai_tmp && git commit -m "$(cat <<'EOF'
tactical_markets: day N short description

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"

# 6. Push (pre-authorized)
cd /c/Users/rekwa/ian_projects/_genai_tmp && git push origin main
```

Remote: `https://github.com/IanRekward/GenAI_Messing.git`, branch `main`.

`LF will be replaced by CRLF` warnings are harmless Windows noise. Do not touch `.gitattributes`.

Co-author trailer must match the running model:
- Sonnet 4.6: `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`
- Opus 4.7: `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`

## Model selection

- **Design questions / DESIGNER_PROMPT.md work** — Opus 4.7+
- **Locked-brief execution** — Sonnet 4.6+

## Style rules

From CLAUDE.md (project-specific):

- No comments unless the **why** is non-obvious. Code already says what.
- No extra abstractions. Three similar lines beats a premature helper.
- No half-finished implementations.
- No error handling for impossible scenarios. Validate only at boundaries (yfinance, FRED, Pushover).
- All secrets via `.env`. Never hardcoded.
- **No cross-project Python imports.** `tactical_markets`, `market_dashboard`, `tactical_markets_trading` integrate via files-on-disk. If you find yourself wanting `from market_dashboard.foo import bar`, stop and surface the design question.

## Two-week freeze rule

After the week-1 ship, **no changes for 14 days** while Ian reads theses. The frozen state is the calibration substrate — modifying it mid-window invalidates the read. Bug fixes only with explicit user sign-off.

The freeze ends when one of three failure modes shows up (per [TODO.md](../TODO.md)):

- (a) "Sometimes I'd act on these" → expand to VIX slope.
- (b) "Feels like noise" → fix sector rotation before adding anything.
- (c) "Never read them at 6:30 AM" → delivery is wrong, not signal.

## Before any work

```bash
cd /c/Users/rekwa/ian_projects/_genai_tmp && git log --oneline -5
```

Then re-read [TODO.md](../TODO.md). If the decision isn't covered there, **stop and surface it** rather than guessing.

## After any work

1. Smoke-test (`python run_tactical.py` or `python -m src.sector_rotation`).
2. Commit with a message that names the day/phase (e.g., `tactical_markets: day 1 sector rotation thesis generator`).
3. Push to `origin main`.

## Common tasks

| Task | Command |
|---|---|
| Tune publish threshold | Edit `config/thresholds.yaml`, smoke-test |
| Add/remove a ticker | Edit `config/universe.yaml`, smoke-test |
| Force a Pushover test | `python -c "from src.pushover import send; send('test', 'hello')"` |
| Inspect today's run | `tail -1 data/theses.jsonl` |
| Inspect last week | `tail -5 data/theses.jsonl` |
| Re-register scheduler | `.\setup_task.ps1` |
| Disable scheduler temporarily | `Disable-ScheduledTask -TaskName "Tactical Markets"` |
