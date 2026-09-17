from __future__ import annotations

from dataclasses import dataclass

from config import settings
from services.model_registry import model_registry
from utilities.geometry import distance

COCO_BONES = ((5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12), (11, 12))


@dataclass
class PoseObservation:
    track_id: int
    frame_sequence: int
    crop_box: tuple[float, float, float, float]
    global_keypoints: list[tuple[float, float, float]]
    timestamp: float
    status: str = "VALID"
    missing_updates: int = 0


def pose_inference_due(
    frame_sequence: int,
    every_n_frames: int,
    cached_pose: PoseObservation | None,
) -> bool:
    """Refresh missing/stale evidence even when captured frame numbers are skipped."""
    cadence = max(1, every_n_frames)
    return cached_pose is None or frame_sequence % cadence == 0


class PoseService:
    def __init__(self) -> None:
        self.history: dict[int, PoseObservation] = {}
        self.model = None

    def load(self) -> bool:
        self.model = model_registry.load("pose", settings.pose_model_path, settings.pose_person_confidence, settings.pose_imgsz)
        return self.model is not None

    @staticmethod
    def to_global(points: list[tuple[float, float, float]], crop_box: tuple[float, float, float, float]) -> list[tuple[float, float, float]]:
        left, top, _, _ = crop_box
        return [(x + left, y + top, confidence) for x, y, confidence in points]

    def store(self, track_id: int, frame_sequence: int, crop_box, crop_points, timestamp: float) -> PoseObservation:
        global_points = self.to_global(crop_points, crop_box)
        previous = self.history.get(track_id)
        left, top, right, bottom = crop_box
        span = max(1.0, right - left, bottom - top)
        validated = []
        for index, (x, y, confidence) in enumerate(global_points):
            outside = not (left - 0.15 * span <= x <= right + 0.15 * span and top - 0.15 * span <= y <= bottom + 0.15 * span)
            jumped = bool(previous and index < len(previous.global_keypoints) and distance((x, y), previous.global_keypoints[index][:2]) > 0.6 * span)
            validated.append((x, y, 0.0 if outside or jumped else confidence))
        global_points = validated
        for first, second in COCO_BONES:
            if first < len(global_points) and second < len(global_points):
                if distance(global_points[first][:2], global_points[second][:2]) > 0.75 * span:
                    point = global_points[second]
                    global_points[second] = (point[0], point[1], 0.0)
        if previous and len(previous.global_keypoints) == len(global_points):
            alpha = settings.pose_smoothing_alpha
            smoothed = []
            for old, new in zip(previous.global_keypoints, global_points):
                if new[2] >= settings.pose_keypoint_confidence:
                    smoothed.append((alpha * new[0] + (1 - alpha) * old[0], alpha * new[1] + (1 - alpha) * old[1], new[2]))
                else:
                    smoothed.append(new)
            global_points = smoothed
        value = PoseObservation(track_id, frame_sequence, tuple(crop_box), global_points, timestamp)
        self.history[track_id] = value
        return value

    def infer(self, track_id: int, frame_sequence: int, crop_box, crop, timestamp: float) -> PoseObservation | None:
        if self.model is None or crop is None or getattr(crop, "size", 0) == 0:
            return None
        try:
            result = model_registry.predict(
                "pose",
                self.model,
                crop,
                imgsz=settings.pose_imgsz,
                conf=settings.pose_person_confidence,
                verbose=False,
            )[0]
            if result.keypoints is None or len(result.keypoints) == 0:
                return self.missing(track_id, timestamp)
            xy = result.keypoints.xy[0].tolist()
            confidences = result.keypoints.conf[0].tolist() if result.keypoints.conf is not None else [1.0] * len(xy)
            points = [(float(point[0]), float(point[1]), float(confidence)) for point, confidence in zip(xy, confidences)]
            return self.store(track_id, frame_sequence, crop_box, points, timestamp)
        except Exception:
            return self.missing(track_id, timestamp)

    def missing(self, track_id: int, now: float) -> PoseObservation | None:
        value = self.history.get(track_id)
        if not value:
            return None
        value.missing_updates += 1
        age = now - value.timestamp
        if age > settings.pose_max_stale_seconds:
            value.status = "STALE"
        elif value.missing_updates <= settings.pose_hold_missing_updates:
            value.status = "TEMPORARILY_MISSING"
            value.global_keypoints = [(x, y, confidence * settings.pose_confidence_decay) for x, y, confidence in value.global_keypoints]
        else:
            value.status = "STALE"
        return value

    def fresh(self, track_id: int, now: float) -> PoseObservation | None:
        value = self.history.get(track_id)
        if value and now - value.timestamp <= settings.pose_max_stale_seconds:
            return value
        return None

    def clear(self, track_id: int) -> None:
        self.history.pop(track_id, None)
