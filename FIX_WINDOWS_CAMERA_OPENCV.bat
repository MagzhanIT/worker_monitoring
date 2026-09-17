@echo off
setlocal
cd /d "%~dp0"
if not exist backend\.venv\Scripts\python.exe (
  echo Run SETUP_WINDOWS_DOUBLE_CLICK.bat first.
  pause
  exit /b 1
)
backend\.venv\Scripts\python.exe -m pip uninstall -y opencv-python opencv-python-headless
backend\.venv\Scripts\python.exe -m pip install opencv-python==4.10.0.84
backend\.venv\Scripts\python.exe -c "import cv2; print('OpenCV ready:', cv2.__version__)"
pause

