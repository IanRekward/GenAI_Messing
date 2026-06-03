# Market Dashboard — Task Scheduler setup
# Run once to register (or re-register) both tasks.
# No admin required — tasks run as current user.
#
# All times are local machine time (CDT = UTC-5 during DST).
# 07:20 AM CDT = 12:20 UTC = 08:20 AM ET
# 07:30 AM CDT = 12:30 UTC = 08:30 AM ET
#
# WakeToRun on BOTH tasks: the wake task fires first and may complete before
# the machine fully settles; WakeToRun on the main task is the belt-and-suspenders
# guarantee that the machine wakes at 07:30 even if it dozed off after 07:20.

$python  = "C:\Users\rekwa\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$workDir = "C:\Users\rekwa\ian_projects\market_dashboard"

# --- Wake task (wakes the machine 10 min before run) ---
$wakeAction   = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c exit"
$wakeTrigger  = New-ScheduledTaskTrigger -Daily -At "07:20AM"
# ExecutionTimeLimit PT20M: the pipeline finishes in ~1 min. A hard 20-min cap
# guarantees a hung run (e.g. a stalled network fetch) self-terminates so the
# NEXT day's trigger starts clean. The old PT72H default + MultipleInstances
# IgnoreNew meant one hung run could silently skip up to 3 days of runs.
$wakeSettings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

Register-ScheduledTask `
    -TaskName "Market Dashboard Wake" `
    -Action   $wakeAction `
    -Trigger  $wakeTrigger `
    -Settings $wakeSettings `
    -RunLevel Limited `
    -Force | Out-Null

Write-Host "Wake task registered."

# --- Main run task ---
$runAction   = New-ScheduledTaskAction `
    -Execute          $python `
    -Argument         "run_dashboard.py --publish --heartbeat --quiet" `
    -WorkingDirectory $workDir

$runTrigger  = New-ScheduledTaskTrigger -Daily -At "07:30AM"
$runSettings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

Register-ScheduledTask `
    -TaskName "Market Stress Dashboard" `
    -Action   $runAction `
    -Trigger  $runTrigger `
    -Settings $runSettings `
    -RunLevel Limited `
    -Force | Out-Null

Write-Host "Main run task registered."

# --- Verify ---
Write-Host ""
Write-Host "--- Verification ---"
foreach ($name in @("Market Dashboard Wake", "Market Stress Dashboard")) {
    $t = Get-ScheduledTask -TaskName $name
    Write-Host "${name}:"
    $t.Triggers | Select-Object StartBoundary | Format-List
    $t.Settings | Select-Object DisallowStartIfOnBatteries, StopIfGoingOnBatteries, StartWhenAvailable, WakeToRun | Format-List
}
