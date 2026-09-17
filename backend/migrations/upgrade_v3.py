"""Safe additive schema upgrade for customer journeys, TEST mode, and audit data."""

import sys
from pathlib import Path

# Allow this file to be run directly from either the project or backend folder.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import init_db


if __name__ == "__main__":
    init_db()
    print("Schema v3 is installed. Existing rows were preserved.")
