#!/bin/zsh
set -e

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

if command -v python3.11 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.11)"
elif command -v python3.12 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.12)"
else
  echo "Python 3.11 or 3.12 is required. Install it, then run this setup again."
  read -k 1 "?Press any key to close..."
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env. Set APP_SECRET_KEY and optionally DEFAULT_ADMIN_PASSWORD before real use."
fi

cd backend
"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
mkdir -p storage/manifests reports evidence worker_snapshots debug_phone_misses
.venv/bin/python -c "from database import init_db; init_db(); print('Database schema ready')"
.venv/bin/python -c "from config import settings; from pathlib import Path; [(print(('FOUND   ' if settings.backend_path(p).is_file() else 'MISSING ') + str(settings.backend_path(p)))) for p in (settings.person_model_path, settings.phone_model_path, settings.pose_model_path)]"
.venv/bin/python -c "import fastapi, sqlalchemy, cv2, ultralytics, torch; print('Backend imports verified')"

cd ../mobile_app
flutter pub get

echo "Setup complete. Missing model files are allowed; perception will be marked unavailable until licensed weights are added."
read -k 1 "?Press any key to close..."

