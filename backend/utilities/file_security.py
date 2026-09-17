from __future__ import annotations

import base64
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from config import BACKEND_DIR, settings


def _fernet() -> Fernet:
    import hashlib
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.app_secret_key.encode()).digest())
    return Fernet(key)


def protect_source(source: str) -> str:
    return protect_text(source)


def reveal_source(value: str) -> str:
    return reveal_text(value)


def protect_text(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def reveal_text(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        return value


def safe_media_path(root: Path, relative_id: str) -> Path:
    if not relative_id or Path(relative_id).is_absolute() or ".." in Path(relative_id).parts:
        raise ValueError("Invalid media identifier")
    root = root.resolve()
    candidate = (root / relative_id).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Media path escapes approved storage")
    return candidate


MEDIA_ROOTS = {
    "snapshots": BACKEND_DIR / "worker_snapshots",
    "evidence": BACKEND_DIR / "evidence",
}
