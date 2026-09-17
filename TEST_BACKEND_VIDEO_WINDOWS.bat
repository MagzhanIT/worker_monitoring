@echo off
setlocal
cd /d "%~dp0\backend"
if not exist .venv\Scripts\python.exe (
  echo Backend environment is missing. Run SETUP_WINDOWS_DOUBLE_CLICK.bat first.
  pause
  exit /b 1
)
echo Pharmacy Worker Monitor V2 - safe offline backend test
echo.
echo This test does not start the API, cameras, or app UI and never edits the input.
echo It creates an annotated MP4, event/diagnostic/customer CSV files,
echo a repeatable JSON summary, and a manager-facing HTML report.
echo Included worker-tracking functions:
echo   - stable worker role after coat evidence is confirmed
echo   - short tracker-loss recovery and anonymous worker session labels
echo   - optional Codea employee/lab-coat model profile
echo   - optional WORKER-ONLY crop dataset with review CSV
echo   - live annotated preview; press Q or Esc in the video window to stop
echo   - the same evidence quality, idle hysteresis, phone temporal logic,
echo     and customer service/retrieval state machine used by the live backend
echo   - optional ground-truth scoring with confusion matrix, precision, recall, and F1
echo.
echo Double-click: answer the prompts below.
echo Command line example:
echo   TEST_BACKEND_VIDEO_WINDOWS.bat "C:\video.mp4" --codea-models --dataset-dir "C:\worker_review"
echo Validation example:
echo   TEST_BACKEND_VIDEO_WINDOWS.bat "C:\video.mp4" --camera-id 4 --ground-truth "C:\truth.csv"
echo Add --no-preview when running from Command Prompt to disable the window.
echo.
.venv\Scripts\python.exe offline_video_test.py --preview %*
if errorlevel 1 (
  echo.
  echo The offline test stopped with an error. Read the message above.
)
pause
