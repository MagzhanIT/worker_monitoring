# Windows setup

Status: setup and repair scripts are **implemented** for Python 3.11/3.12 and an installed Flutter SDK.

Never copy a macOS virtual environment. Copy `.env.example` to `.env`, set secrets, add licensed weights, then double-click `SETUP_WINDOWS_DOUBLE_CLICK.bat`. It creates `backend\.venv` and invokes its Python directly. Use `FIX_WINDOWS_AI_TORCH.bat` for PyTorch installation issues and `FIX_WINDOWS_CAMERA_OPENCV.bat` for camera/OpenCV repair. A missing `c10.dll` commonly requires the current Microsoft Visual C++ Redistributable.

