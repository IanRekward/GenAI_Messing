# Tactical Markets — Task Scheduler setup
# Run once to register (or re-register) both tasks.
# No admin required — tasks run as current user.
#
# Trigger times are in LOCAL MACHINE TIME. This machine is on Central Time,
# so 05:30 local = 06:30 ET (the documented target). If you move the machine
# to a different time zone, recompute the offset. Both ET and CT observe the
# same DST schedule, so the 1-hour offset holds year-round.

$python  = "C:\Users\rekwa\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$workDir = "C:\Users\rekwa\ian_projects\tactical_markets"

# --- Wake task (wakes the computer 10 min before main task) ---
$wakeAction   = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c exit"
$wakeTrigger  = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "05:20AM"
$wakeSettings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries

Register-ScheduledTask `
    -TaskName "Tactical Markets Wake" `
    -Action   $wakeAction `
    -Trigger  $wakeTrigger `
    -Settings $wakeSettings `
    -RunLevel Limited `
    -Force | Out-Null

Write-Host "Wake task registered (05:20 CT = 06:20 ET)."

# --- Main task ---
$mainAction   = New-ScheduledTaskAction `
    -Execute          $python `
    -Argument         "run_tactical.py" `
    -WorkingDirectory $workDir

$mainTrigger  = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "05:30AM"
$mainSettings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries

Register-ScheduledTask `
    -TaskName "Tactical Markets" `
    -Action   $mainAction `
    -Trigger  $mainTrigger `
    -Settings $mainSettings `
    -RunLevel Limited `
    -Force | Out-Null

Write-Host "Main task registered (05:30 CT = 06:30 ET, with -WakeToRun as backup)."

# --- Watchdog task (fires 90 min after main; alerts if no thesis written today) ---
$watchdogAction   = New-ScheduledTaskAction `
    -Execute          $python `
    -Argument         "watch_tactical.py" `
    -WorkingDirectory $workDir

$watchdogTrigger  = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "07:00AM"
$watchdogSettings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries

Register-ScheduledTask `
    -TaskName "Tactical Markets Watchdog" `
    -Action   $watchdogAction `
    -Trigger  $watchdogTrigger `
    -Settings $watchdogSettings `
    -RunLevel Limited `
    -Force | Out-Null

Write-Host "Watchdog task registered (07:00 CT = 08:00 ET)."

# --- Verify ---
Write-Host ""
Write-Host "--- Verification ---"
foreach ($name in @("Tactical Markets Wake", "Tactical Markets", "Tactical Markets Watchdog")) {
    $t = Get-ScheduledTask -TaskName $name
    Write-Host "${name}:"
    $t.Triggers | Select-Object StartBoundary | Format-List
    $t.Settings | Select-Object DisallowStartIfOnBatteries, StopIfGoingOnBatteries, StartWhenAvailable, WakeToRun | Format-List
}
