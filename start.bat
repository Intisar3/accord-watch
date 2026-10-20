@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set LOG=logs\first_run.log
echo accord-watch setup started %date% %time% > %LOG%
set CLAUDE=
for /f "delims=" %%F in ('where claude 2^>nul') do if not defined CLAUDE set "CLAUDE=%%F"
if not defined CLAUDE for /f "delims=" %%F in ('dir /b /s "%USERPROFILE%\.vscode\extensions\claude.exe" 2^>nul') do set "CLAUDE=%%F"
if not defined CLAUDE (echo CLAUDE_NOT_FOUND >> %LOG% & echo Claude Code was not found. & pause & exit /b 1)
echo CLAUDE=%CLAUDE% >> %LOG%
echo %CLAUDE%> logs\claude_path.txt
for %%D in ("%CLAUDE%") do set "PATH=%%~dpD;%PATH%"

where python >> %LOG% 2>&1
"%CLAUDE%" --version >> %LOG% 2>&1
echo Step 1 of 2: setup... please wait
powershell -ExecutionPolicy Bypass -File setup.ps1 >> %LOG% 2>&1
echo SETUP_EXIT %errorlevel% >> %LOG%
echo Step 2 of 2: first daily run... this can take 30-60 minutes. PLEASE KEEP THIS WINDOW OPEN.
"%CLAUDE%" -p "/daily-run" --permission-mode acceptEdits --verbose --output-format stream-json > logs\run2_stream.jsonl 2>&1
echo RUN_EXIT %errorlevel% >> %LOG%
if exist reports\latest.html start "" reports\latest.html
echo Done. You can close this window.
pause
