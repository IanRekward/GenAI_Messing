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

# --- Entry task (submit order + log trade) ---
$entryAction   = New-ScheduledTaskAction `
    -Execute          $python `
    -Argument         "run_trading.py" `
    -WorkingDirectory $workDir

$entryTrigger  = New-ScheduledTaskTrigger -Daily -At "08:35AM"
$entrySettings = New-ScheduledTaskSettingsSet `
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

# --- Exit task (close positions past hold window) ---
$exitAction   = New-ScheduledTaskAction `
    -Execute          $python `
    -Argument         "src\exit_manager.py" `
    -WorkingDirectory $workDir

$exitTrigger  = New-ScheduledTaskTrigger -Daily -At "08:40AM"
$exitSettings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries

Register-ScheduledTask `
    -TaskName "Tactical Trading Exit" `
    -Action   $exitAction `
    -Trigger  $exitTrigger `
    -Settings $exitSettings `
    -RunLevel Limited `
    -Force | Out-Null

Write-Host "Exit task registered."

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
foreach ($name in @("Tactical Trading Wake", "Tactical Trading Entry", "Tactical Trading Exit", "Tactical Trading Backfill Benchmarks")) {
    $t = Get-ScheduledTask -TaskName $name
    Write-Host "${name}:"
    $t.Triggers | Select-Object StartBoundary | Format-List
    $t.Settings | Select-Object DisallowStartIfOnBatteries, StopIfGoingOnBatteries, StartWhenAvailable, WakeToRun | Format-List
}
