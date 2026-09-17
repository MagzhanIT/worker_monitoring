from __future__ import annotations

import argparse
from datetime import datetime, timedelta

from config import BACKEND_DIR, settings


def cleanup(dry_run: bool = False, now: datetime | None = None) -> list[str]:
    now = now or datetime.now()
    policies = {
        BACKEND_DIR / "worker_snapshots": settings.worker_snapshot_retention_days,
        BACKEND_DIR / "evidence": settings.evidence_clip_retention_days,
        BACKEND_DIR / "debug_phone_misses": settings.debug_image_retention_days,
    }
    removed = []
    for root, days in policies.items():
        if not root.exists():
            continue
        cutoff = now - timedelta(days=days)
        for path in root.rglob("*"):
            if not path.is_file() or path.name == ".active":
                continue
            if any(parent.joinpath(".active").exists() for parent in [path.parent, *path.parents] if root == parent or root in parent.parents):
                continue
            if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
                removed.append(str(path))
                if not dry_run:
                    path.unlink()
    return removed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean expired local monitoring media")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    for item in cleanup(args.dry_run):
        print(("Would remove " if args.dry_run else "Removed ") + item)

