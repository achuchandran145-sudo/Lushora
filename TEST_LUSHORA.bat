@echo off
cd /d "%~dp0backend"
if not exist .venv\Scripts\python.exe (
  echo Run RUN_LUSHORA.bat first to install dependencies.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pytest -q
pause
