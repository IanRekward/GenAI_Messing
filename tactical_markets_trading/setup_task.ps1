# Tactical Trading — Task Scheduler setup
# Run once to register (or re-register) all three tasks.
# No admin required — tasks run as current user.

$python  = "C:\Users\rekwa\ian_projects\tactical_markets_trading\.venv\Scripts\python.exe"
$workDir = "C:\Users\rekwa\ian_projects\tactical_markets_trading"

# --- Wake task (wakes the computer 15 min before entry) ---
$wakeAction   = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c exit"
$wakeTrigger  = New-ScheduledTaskTrigger -Daily -At "08:20AM"
$wakeSettings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries

Register-ScheduledTask `
    -TaskName "Tactical Trading Wake" `
    -Action   $wakeAction `
    -Trigger  $wakeTrigger `
    -Settings $wakeSettings `
    -RunLevel Limited `
    -Force | Out-Null

Write-Host "Wake task registered."

# --- Entry task (Phase 3.1 ensemble orchestrator) ---
# Changed 2026-05-21: was run_trading.py (sector_rotation_5d), now run_ensemble.py
# (multi-strategy ensemble — currently only trend_leveraged_tqqq active).
# run_ensemble.py handles BOTH entries and the software-managed trailing stop,
# and now all exits — the legacy Exit task (exit_manager.py) was retired
# 2026-06-08 and is intentionally no longer registered (see below).
$entryAction   = New-ScheduledTaskAction `
    -Execute          $python `
    -Argument         "run_ensemble.py" `
    -WorkingDirectory $workDir

$entryTrigger  = New-ScheduledTaskTrigger -Daily -At "08:35AM"
# WakeToRun added 2026-05-27 — the 08:20 Wake task alone wasn't reliably waking
# the laptop (likely lid-closed/battery), so StartWhenAvailable was firing this
# task hours late and Pushovering reconcile alerts at odd times. Also requires
# "Allow wake timers" enabled in Windows power settings.
$entrySettings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries

Register-ScheduledTask `
    -TaskName "Tactical Trading Entry" `
    -Action   $entryAction `
    -Trigger  $entryTrigger `
    -Settings $entrySettings `
    -RunLevel Limited `
    -Force | Out-Null

Write-Host "Entry task registered."

# --- Exit task (legacy exit_manager.py) — INTENTIONALLY NOT REGISTERED ---
# Disabled 2026-06-08. run_ensemble.py now handles ALL exits and the software-
# managed trailing stop directly; the legacy exit_manager.py skips every ensemble
# record and never trades, but still fired daily emitting reconcile/drift Pushover
# noise. This block is left here (commented) for history — DO NOT re-enable it
# without re-confirming exit_manager is needed, or it will resume the noise.
# If a stale "Tactical Trading Exit" task already exists, remove it once with:
#   Unregister-ScheduledTask -TaskName "Tactical Trading Exit" -Confirm:$false
Write-Host "Exit task intentionally NOT registered (legacy exit_manager retired)."

# --- Benchmark backfill task (runs after close to fill null spy/sell-leg returns) ---
# 03:45 PM CDT = 04:45 PM ET (45 min after 4:00 PM close; EOD bars need ~15-30 min to materialize)
$backfillAction   = New-ScheduledTaskAction `
    -Execute          $python `
    -Argument         "src\backfill_benchmarks.py" `
    -WorkingDirectory $workDir

$backfillTrigger  = New-ScheduledTaskTrigger -Daily -At "03:45PM"
$backfillSettings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries

Register-ScheduledTask `
    -TaskName "Tactical Trading Backfill Benchmarks" `
    -Action   $backfillAction `
    -Trigger  $backfillTrigger `
    -Settings $backfillSettings `
    -RunLevel Limited `
    -Force | Out-Null

Write-Host "Backfill benchmarks task registered."

# --- Verify ---
Write-Host ""
Write-Host "--- Verification ---"
foreach ($name in @("Tactical Trading Wake", "Tactical Trading Entry", "Tactical Trading Backfill Benchmarks")) {
    $t = Get-ScheduledTask -TaskName $name
    Write-Host "${name}:"
    $t.Triggers | Select-Object StartBoundary | Format-List
    $t.Settings | Select-Object DisallowStartIfOnBatteries, StopIfGoingOnBatteries, StartWhenAvailable, WakeToRun | Format-List
}
