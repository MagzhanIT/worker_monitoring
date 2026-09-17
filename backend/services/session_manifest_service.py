from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

from config import BACKEND_DIR, settings


def _git(command: list[str]) -> str | None:
    try:
        return subprocess.run(command, cwd=BACKEND_DIR.parent, capture_output=True, text=True, timeout=2, check=True).stdout.strip()
    except Exception:
        return None


def write_manifest(session_id: str, payload: dict) -> Path:
    folder = BACKEND_DIR / "storage" / "manifests"
    folder.mkdir(parents=True, exist_ok=True)
    document = {
        "session_uuid": session_id,
        "generated_at": datetime.now().astimezone().isoformat(),
        "git_commit": _git(["git", "rev-parse", "HEAD"]),
        "dirty_tree": bool(_git(["git", "status", "--porcelain"])),
        "configuration": settings.model_dump(exclude={"app_secret_key", "default_admin_password"}),
        **payload,
    }
    path = folder / f"{session_id}.json"
    path.write_text(json.dumps(document, indent=2, default=str), encoding="utf-8")
    return path

