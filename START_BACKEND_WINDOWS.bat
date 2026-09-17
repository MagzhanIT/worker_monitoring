@echo off
setlocal
cd /d "%~dp0\backend"
if not exist .venv\Scripts\python.exe (
  echo Backend environment is missing. Run SETUP_WINDOWS_DOUBLE_CLICK.bat first.
  pause
  exit /b 1
)
for /f %%P in ('.venv\Scripts\python.exe -c "from config import settings; print(settings.app_port)"') do set "BACKEND_PORT=%%P"
if not defined BACKEND_PORT set "BACKEND_PORT=8000"
powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:%BACKEND_PORT%/health' -TimeoutSec 2; if ($r.app -eq 'Pharmacy Worker Monitor V2') { exit 0 }; exit 2 } catch { exit 1 }"
if errorlevel 2 goto PORT_BUSY
if errorlevel 1 goto START_BACKEND
echo Pharmacy Worker Monitor V2 is already running at http://localhost:%BACKEND_PORT%.
echo No second backend is needed. You can keep using the app.
powershell -NoProfile -Command "Start-Sleep -Seconds 4"
exit /b 0

:PORT_BUSY
echo Port %BACKEND_PORT% is already used by another application.
echo Stop that application or change APP_PORT in .env.
pause
exit /b 1

:START_BACKEND
.venv\Scripts\python.exe run_backend.py
if errorlevel 1 (
  echo Backend stopped with an error. Check .env, model paths and the message above.
  pause
)
