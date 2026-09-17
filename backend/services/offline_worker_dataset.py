from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any


def _safe_name(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in value
    )[:120]


class OfflineWorkerDatasetExporter:
    """Export reviewed worker crops without storing customer identity crops.

    These are pseudo-labelled tracking samples, not ground truth. A human must
    review them before they are used to tune ReID thresholds or train a model.
    """

    def __init__(
        self,
        root: Path,
        session_id: str,
        *,
        every_frames: int = 25,
        max_per_worker: int = 100,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.session_id = _safe_name(session_id) or "offline_video"
        self.every_frames = max(1, int(every_frames))
        self.max_per_worker = max(1, int(max_per_worker))
        self.session_dir = self.root / self.session_id
        self.crop_dir = self.session_dir / "worker_identity_crops"
        self.manifest_path = self.session_dir / "worker_crops.csv"
        self.counts: defaultdict[str, int] = defaultdict(int)
        self.saved_crops = 0
        self.session_dir.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            with self.manifest_path.open("w", newline="", encoding="utf-8") as stream:
                csv.writer(stream).writerow(
                    [
                        "frame",
                        "video_seconds",
                        "anonymous_worker_session_id",
                        "local_track_id",
                        "confidence",
                        "role_evidence",
                        "stitch_status",
                        "crop_path",
                    ]
                )

    def export(
        self,
        frame,
        frame_number: int,
        video_seconds: float,
        observations: list[dict[str, Any]],
    ) -> int:
        if frame_number % self.every_frames != 0:
            return 0
        import cv2

        height, width = frame.shape[:2]
        saved = 0
        for observation in observations:
            if observation.get("role") != "WORKER":
                continue
            worker_id = str(observation.get("worker_session_id") or "")
            if not worker_id or self.counts[worker_id] >= self.max_per_worker:
                continue
            left, top, right, bottom = observation["bbox"]
            left = max(0, min(width, int(left)))
            top = max(0, min(height, int(top)))
            right = max(left, min(width, int(right)))
            bottom = max(top, min(height, int(bottom)))
            crop = frame[top:bottom, left:right]
            if crop.size == 0 or crop.shape[0] < 48 or crop.shape[1] < 20:
                continue
            worker_folder = self.crop_dir / _safe_name(worker_id)
            worker_folder.mkdir(parents=True, exist_ok=True)
            filename = f"frame_{frame_number:08d}_{self.counts[worker_id] + 1:04d}.jpg"
            path = worker_folder / filename
            if not cv2.imwrite(str(path), crop):
                continue
            relative_path = path.relative_to(self.session_dir).as_posix()
            stitch = observation.get("session_stitch") or {}
            with self.manifest_path.open("a", newline="", encoding="utf-8") as stream:
                csv.writer(stream).writerow(
                    [
                        frame_number,
                        f"{video_seconds:.3f}",
                        worker_id,
                        observation.get("track_id"),
                        f"{float(observation.get('confidence', 0)):.4f}",
                        "; ".join(observation.get("reasons") or []),
                        stitch.get("reason", "not_stitched"),
                        relative_path,
                    ]
                )
            self.counts[worker_id] += 1
            self.saved_crops += 1
            saved += 1
        return saved

    def summary(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "session_directory": str(self.session_dir),
            "manifest": str(self.manifest_path),
            "saved_worker_crops": self.saved_crops,
            "workers": dict(sorted(self.counts.items())),
            "customers_exported": 0,
            "review_required": True,
            "purpose": (
                "Human-reviewed worker tracking/ReID evaluation; pseudo-labels are not "
                "ground truth and must not be trained without review."
            ),
        }
