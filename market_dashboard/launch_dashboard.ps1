# Market Stress Dashboard — launcher script
# Runs the dashboard refresh then opens the HTML in the default browser.
# To pin to the taskbar: right-click the shortcut (launch_dashboard.lnk) -> Pin to taskbar.

$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python     = "C:\Users\rekwa\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$script     = Join-Path $projectDir "run_dashboard.py"
$output     = Join-Path $projectDir "output\dashboard.html"

Set-Location $projectDir

# Run the dashboard refresh (shows a brief console window with progress)
& $python $script --no-alerts
if ($LASTEXITCODE -ne 0) {
    Write-Host "Dashboard run failed (exit code $LASTEXITCODE)" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit $LASTEXITCODE
}

# Open the generated HTML in the default browser
Start-Process $output
