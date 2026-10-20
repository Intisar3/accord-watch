# Headless daily run for Windows (Task Scheduler).
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"
New-Item -ItemType Directory -Force -Path logs | Out-Null
$log = "logs\$(Get-Date -Format yyyy-MM-dd).log"
$claude = (Get-Command claude -ErrorAction SilentlyContinue).Source
if (-not $claude) { $claude = Get-ChildItem "$env:USERPROFILE\.vscode\extensions" -Recurse -Filter claude.exe -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName }
if (-not $claude) { "claude not found" | Out-File $log -Append; exit 1 }
& $claude -p "/daily-run" --permission-mode acceptEdits *>> $log
