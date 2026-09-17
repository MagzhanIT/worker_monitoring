#!/bin/zsh
set -e

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR/backend"

if [[ ! -x .venv/bin/python ]]; then
  echo "Backend environment is missing. Run SETUP_MAC.command first."
  read -k 1 "?Press any key to close..."
  exit 1
fi

exec .venv/bin/python run_backend.py

