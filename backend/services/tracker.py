from __future__ import annotations

from dataclasses import dataclass

from config import settings
from utilities.geometry import BBox, center, distance, iou


@dataclass
class Detection:
    bbox: BBox
    confidence: float
    role_hint: str = "UNKNOWN"


@dataclass
class Track:
    track_id: int
    bbox: BBox
    confidence: float
    first_seen: float
    last_seen: float
    age: float = 0
    missed_time: float = 0
    directly_observed: bool = True
    predicted: bool = False
    role_hint: str = "UNKNOWN"
    velocity: tuple[float, float] = (0.0, 0.0)
    last_observed_bbox: BBox | None = None
    hits: int = 1
    consecutive_hits: int = 1
    confirmed: bool = False


class StableTracker:
    """Small deterministic IoU/centre tracker keyed only by stable track IDs."""

    def __init__(
        self,
        iou_threshold: float | None = None,
        max_distance: float | None = None,
        max_missed: float | None = None,
        *,
        id_namespace: int = 0,
    ) -> None:
        self.iou_threshold = iou_threshold or settings.track_iou_threshold
        self.max_distance = max_distance or settings.track_max_center_distance
        self.max_missed = max_missed or settings.track_max_missed_seconds
        self.tracks: dict[int, Track] = {}
        if id_namespace < 0:
            raise ValueError("track ID namespace must be non-negative")
        # New live tracks are numerically unique across cameras while the
        # tracker and all continuity state remain camera-local. The default
        # namespace preserves compact IDs for isolated unit tests.
        self._next_id = id_namespace * 10_000_000 + 1

    def update(self, detections: list[Detection], timestamp: float) -> tuple[list[Track], list[Track]]:
        available = set(self.tracks)
        matched: set[int] = set()
        output: list[Track] = []
        for detection in sorted(detections, key=lambda item: item.confidence, reverse=True):
            candidates = []
            for track_id in available:
                track = self.tracks[track_id]
                overlap = iou(track.bbox, detection.bbox)
                centre_distance = distance(center(track.bbox), center(detection.bbox))
                if overlap >= self.iou_threshold or centre_distance <= self.max_distance:
                    candidates.append((overlap, -centre_distance, track_id))
            if candidates:
                _, _, track_id = max(candidates)
                track = self.tracks[track_id]
                elapsed = max(0.0001, timestamp - track.last_seen)
                previous_box = track.last_observed_bbox or track.bbox
                previous_center = center(previous_box)
                observed_center = center(detection.bbox)
                measured_velocity = (
                    (observed_center[0] - previous_center[0]) / elapsed,
                    (observed_center[1] - previous_center[1]) / elapsed,
                )
                alpha = settings.tracker_velocity_smoothing_alpha
                track.velocity = (
                    alpha * measured_velocity[0] + (1 - alpha) * track.velocity[0],
                    alpha * measured_velocity[1] + (1 - alpha) * track.velocity[1],
                )
                track.bbox = detection.bbox
                track.last_observed_bbox = detection.bbox
                track.confidence = detection.confidence
                track.age = timestamp - track.first_seen
                track.missed_time = 0
                track.last_seen = timestamp
                track.directly_observed = True
                track.predicted = False
                track.role_hint = detection.role_hint
                track.hits += 1
                track.consecutive_hits += 1
                if track.consecutive_hits >= settings.track_min_confirmation_hits:
                    track.confirmed = True
                available.remove(track_id)
                matched.add(track_id)
                output.append(track)
            else:
                track = Track(
                    self._next_id,
                    detection.bbox,
                    detection.confidence,
                    timestamp,
                    timestamp,
                    role_hint=detection.role_hint,
                    confirmed=settings.track_min_confirmation_hits <= 1,
                )
                track.last_observed_bbox = detection.bbox
                self.tracks[track.track_id] = track
                self._next_id += 1
                matched.add(track.track_id)
                output.append(track)

        expired: list[Track] = []
        for track_id in list(self.tracks):
            if track_id not in matched:
                track = self.tracks[track_id]
                track.missed_time = timestamp - track.last_seen
                track.age = timestamp - track.first_seen
                track.directly_observed = False
                track.consecutive_hits = 0
                track.predicted = track.missed_time <= self.max_missed
                if track.predicted and track.last_observed_bbox is not None:
                    prediction_seconds = min(
                        track.missed_time, settings.tracker_max_prediction_seconds
                    )
                    dx = track.velocity[0] * prediction_seconds
                    dy = track.velocity[1] * prediction_seconds
                    left, top, right, bottom = track.last_observed_bbox
                    track.bbox = (
                        left + dx,
                        top + dy,
                        right + dx,
                        bottom + dy,
                    )
                if track.missed_time > self.max_missed:
                    expired.append(self.tracks.pop(track_id))
                else:
                    output.append(track)
        return sorted(output, key=lambda track: track.track_id), expired

    def clear(self) -> list[Track]:
        values = list(self.tracks.values())
        self.tracks.clear()
        return values
