# Tactical Markets — Task Scheduler setup
# Run once to register (or re-register) both tasks.
# No admin required — tasks run as current user.

$python  = "C:\Users\rekwa\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$workDir = "C:\Users\rekwa\ian_projects\tactical_markets"

# --- Wake task (wakes the computer 10 min before main task) ---
$wakeAction   = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c exit"
$wakeTrigger  = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "06:20AM"
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

Write-Host "Wake task registered."

# --- Main task ---
$mainAction   = New-ScheduledTaskAction `
    -Execute          $python `
    -Argument         "run_tactical.py" `
    -WorkingDirectory $workDir

$mainTrigger  = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "06:30AM"
$mainSettings = New-ScheduledTaskSettingsSet `
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

Write-Host "Main task registered."

# --- Verify ---
Write-Host ""
Write-Host "--- Verification ---"
foreach ($name in @("Tactical Markets Wake", "Tactical Markets")) {
    $t = Get-ScheduledTask -TaskName $name
    Write-Host "${name}:"
    $t.Triggers | Select-Object StartBoundary | Format-List
    $t.Settings | Select-Object DisallowStartIfOnBatteries, StopIfGoingOnBatteries, StartWhenAvailable, WakeToRun | Format-List
}
