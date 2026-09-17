from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import date

from config import BACKEND_DIR, settings
from utilities.image_quality import image_quality


@dataclass
class SnapshotCandidate:
    kind: str
    quality: float
    path: str
    width: int
    height: int


class SnapshotService:
    """Worker-only visual references; deliberately contains no identity comparison."""

    def __init__(self) -> None:
        self.best: dict[str, list[SnapshotCandidate]] = {}
        self._face_net = None

    def detect_worker_faces(self, frame, worker_box) -> list:
        """Return face crops only; never descriptors, embeddings or comparisons."""
        model_path = BACKEND_DIR / "models" / "optional_face_detector.onnx"
        if not model_path.is_file() or frame is None:
            return []
        try:
            import cv2
            if self._face_net is None:
                self._face_net = cv2.FaceDetectorYN.create(str(model_path), "", (320, 320), 0.75, 0.3, 5000)
            left, top, right, bottom = [int(value) for value in worker_box]
            crop = frame[max(0, top):max(0, bottom), max(0, left):max(0, right)]
            if crop.size == 0:
                return []
            self._face_net.setInputSize((crop.shape[1], crop.shape[0]))
            _, faces = self._face_net.detect(crop)
            if faces is None:
                return []
            output = []
            for face in faces:
                x, y, width, height = [int(value) for value in face[:4]]
                if width >= settings.worker_snapshot_min_face_size and height >= settings.worker_snapshot_min_face_size:
                    output.append(crop[max(0, y):y + height, max(0, x):x + width])
            return output
        except Exception:
            return []

    def consider(
        self, *, worker_session_id: str, camera_id: int, image, kind: str,
        role: str, ambiguous: bool = False, face_size: int | None = None, day: date | None = None,
    ) -> SnapshotCandidate | None:
        if role != "WORKER" or ambiguous or kind not in {"face", "body"}:
            return None
        height, width = image.shape[:2] if image is not None and getattr(image, "size", 0) else (0, 0)
        if kind == "face" and (face_size or min(width, height)) < settings.worker_snapshot_min_face_size:
            return None
        quality = image_quality(image)
        if quality < settings.worker_snapshot_min_quality:
            return None
        folder = BACKEND_DIR / "worker_snapshots" / str(day or date.today()) / f"camera_{camera_id}" / f"session_{worker_session_id}"
        folder.mkdir(parents=True, exist_ok=True)
        values = self.best.setdefault(worker_session_id + ":" + kind, [])
        limit = settings.worker_snapshot_max_face_images if kind == "face" else settings.worker_snapshot_max_body_images
        rank = len(values)
        best_name = "best_face.jpg" if kind == "face" else "best_body.jpg"
        is_best = not values or quality > values[0].quality
        if is_best and values:
            previous = values.pop(0)
            previous_best = folder / best_name
            alternative_name = f"alternative_{kind}_{rank}.jpg"
            alternative_path = folder / alternative_name
            if previous_best.is_file():
                shutil.copy2(previous_best, alternative_path)
                previous.path = str(alternative_path.relative_to(BACKEND_DIR / "worker_snapshots"))
                values.append(previous)
        filename = best_name if is_best else f"alternative_{kind}_{rank}.jpg"
        path = folder / filename
        try:
            import cv2
            if not cv2.imwrite(str(path), image):
                return None
        except Exception:
            return None
        candidate = SnapshotCandidate(kind, quality, str(path.relative_to(BACKEND_DIR / "worker_snapshots")), width, height)
        values.append(candidate)
        values.sort(key=lambda item: item.quality, reverse=True)
        del values[limit:]
        (folder / "metadata.json").write_text(
            json.dumps(
                {
                    "face_recognition": False,
                    "face_embeddings": False,
                    "global_worker_appearance_association": settings.global_worker_id_enabled,
                    "global_worker_appearance_scope": "same calendar day only",
                    "snapshots": [asdict(item) for item in values],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return candidate
