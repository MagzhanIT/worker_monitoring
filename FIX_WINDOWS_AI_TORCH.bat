@echo off
setlocal
cd /d "%~dp0"
if not exist backend\.venv\Scripts\python.exe (
  echo Run SETUP_WINDOWS_DOUBLE_CLICK.bat first.
  pause
  exit /b 1
)
backend\.venv\Scripts\python.exe -m pip uninstall -y torch torchvision
backend\.venv\Scripts\python.exe -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
backend\.venv\Scripts\python.exe -c "import torch; print('Torch ready:', torch.__version__)"
if errorlevel 1 (
  echo If c10.dll is mentioned, install the latest Microsoft Visual C++ 2015-2022 Redistributable x64, restart Windows, and run this file again.
)
pause

