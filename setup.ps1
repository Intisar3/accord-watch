# One-time setup for accord-watch on Windows. Run from this folder:
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
Set-Location $PSScriptRoot

# 1. Python (skip the Microsoft Store stub that answers to python3)
$py = "python"
& $py -c "import sys" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Error "Python not found"; exit 1 }

& $py -m pip install -r requirements.txt
& $py tools\trust_workspace.py
& $py tools\db.py init

# 2. Browser tool for the Scout
$c = (Get-Command claude -ErrorAction SilentlyContinue).Source
if (-not $c) { $c = Get-ChildItem "$env:USERPROFILE\.vscode\extensions" -Recurse -Filter claude.exe -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName }
& $c mcp add playwright -- npx @playwright/mcp@latest

# 3. Daily run at 7:00 every morning
$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$PSScriptRoot\run_daily.ps1`""
$trigger = New-ScheduledTaskTrigger -Daily -At 7:00am
Register-ScheduledTask -TaskName "accord-watch daily" -Action $action -Trigger $trigger -Description "Daily Honda Accord watch" -Force

Write-Host "Setup done. Run the first cycle now with:  claude  then type  /daily-run"
