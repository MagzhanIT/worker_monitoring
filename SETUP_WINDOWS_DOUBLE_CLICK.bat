@echo off
setlocal
cd /d "%~dp0"

if exist backend\.venv\Scripts\python.exe goto INSTALL
if exist backend\.venv rmdir /s /q backend\.venv
if exist backend\venv rmdir /s /q backend\venv

py -3.11 -c "import sys" >nul 2>&1
if errorlevel 1 (
  py -3.12 -c "import sys" >nul 2>&1
  if errorlevel 1 (
    echo Python 3.11 or 3.12 is required. Install it from python.org.
    pause
    exit /b 1
  )
  py -3.12 -m venv backend\.venv
) else (
  py -3.11 -m venv backend\.venv
)

:INSTALL
if not exist .env copy .env.example .env >nul
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto ERROR
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if errorlevel 1 goto TORCH_HELP
cd backend
.venv\Scripts\python.exe -c "from database import init_db; init_db(); print('Database schema ready')"
if errorlevel 1 goto ERROR
.venv\Scripts\python.exe -c "import fastapi, sqlalchemy, cv2, ultralytics, torch; print('Backend imports verified')"
if errorlevel 1 goto ERROR
cd ..\mobile_app
call flutter pub get
if errorlevel 1 goto ERROR
cd ..
echo Setup complete. Edit .env before real use and place licensed weights in backend\models.
pause
exit /b 0

:TORCH_HELP
echo AI dependencies did not install. Run FIX_WINDOWS_AI_TORCH.bat.
goto ERROR

:ERROR
echo Setup stopped because a command failed. Review the message above.
pause
exit /b 1
