from __future__ import annotations

from datetime import date

from config import BACKEND_DIR, settings


class EvidenceClipService:
    def save(self, event_id: str, frames: list[tuple[float, bytes]], fps: float = 8.0, day: date | None = None) -> str | None:
        if not settings.event_clip_enabled or not frames:
            return None
        output = BACKEND_DIR / "evidence" / str(day or date.today()) / f"{event_id}.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            import cv2
            import numpy as np
            first = cv2.imdecode(np.frombuffer(frames[0][1], dtype=np.uint8), cv2.IMREAD_COLOR)
            if first is None:
                return None
            height, width = first.shape[:2]
            writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
            for _, encoded in frames:
                frame = cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    writer.write(frame)
            writer.release()
            return str(output.relative_to(BACKEND_DIR / "evidence")) if output.exists() else None
        except Exception:
            return None

