@echo off
setlocal
cd /d "%~dp0"
echo ========================================
echo          LUSHORA ONE-CLICK LAUNCH
echo ========================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1"
if errorlevel 1 (
  echo.
  echo Setup failed. Read the error above, fix the missing prerequisite, and rerun.
  pause
  exit /b 1
)
start "LUSHORA API" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%~dp0backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
start "LUSHORA WEB" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%~dp0frontend'; npm run dev"
timeout /t 4 /nobreak >nul
start "" http://127.0.0.1:5173
echo LUSHORA is starting. Keep both terminal windows open while using the app.
endlocal
