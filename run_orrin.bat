@echo off
REM run_orrin.bat - start Orrin with auto-restart (Windows)
REM Usage:  run_orrin.bat
REM Stop:   Ctrl-C
REM (Windows equivalent of run_orrin.sh; no caffeinate - see notes below.)

setlocal enabledelayedexpansion
set "REPO=%~dp0"
cd /d "%REPO%"
set "LOG=%REPO%brain\data\run_log.txt"
if "%ORRIN_CYCLE_SLEEP%"=="" set "ORRIN_CYCLE_SLEEP=1"

if exist "%REPO%.venv\Scripts\python.exe" (
    set "PYTHON=%REPO%.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

echo [run] Starting Orrin - press Ctrl-C to stop
echo [run] Python: !PYTHON!
echo [run] Log:    %LOG%
echo [run] Cycle sleep: %ORRIN_CYCLE_SLEEP%s

REM To keep Windows awake while Orrin runs, you can run (in another window):
REM   powercfg /change standby-timeout-ac 0

set /a RESTART_COUNT=0
:loop
echo [run] %date% %time% - launch #!RESTART_COUNT!>> "%LOG%"
echo [run] %date% %time% - launch #!RESTART_COUNT!
"!PYTHON!" main.py
set "EXIT_CODE=!errorlevel!"
set /a RESTART_COUNT+=1
if "!EXIT_CODE!"=="0" (
    echo [run] clean exit - not restarting.
    goto :end
)
echo [run] crashed (exit !EXIT_CODE!) - restarting in 10s...
timeout /t 10 /nobreak >nul
goto :loop

:end
endlocal
