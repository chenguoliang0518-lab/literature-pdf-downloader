@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  py -3 run.py --mode search
) else (
  python run.py --mode search
)
pause
