from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from config import settings
from services.global_identity_service import clothing_descriptor, cosine_distance
from services.worker_session_service import AnonymousWorkerSession
from utilities.geometry import BBox, center, distance


@dataclass
class _ObservedSession:
    session: AnonymousWorkerSession
    track_id: int
    bbox: BBox
    descriptor: np.ndarray | None
    last_seen: float
    velocity: tuple[float, float] = (0.0, 0.0)


@dataclass
class LocalStitchMatch:
    session: AnonymousWorkerSession
    previous_track_id: int
    gap_seconds: float
    appearance_distance: float
    spatial_distance: float
    confidence: float
    reason: str = "short_gap_spatial_appearance_match"


class LocalSessionStitcher:
    """Conservative same-camera re-linking after a tracker ID is lost."""

    def __init__(self) -> None:
        self.observed: dict[int, _ObservedSession] = {}
        self.recently_lost: dict[int, _ObservedSession] = {}

    def observe(
        self,
        track_id: int,
        session: AnonymousWorkerSession,
        bbox: BBox,
        crop,
        now: float,
    ) -> None:
        previous = self.observed.get(track_id)
        descriptor = clothing_descriptor(crop)
        velocity = (0.0, 0.0)
        if previous and now > previous.last_seen:
            old_center = center(previous.bbox)
            new_center = center(bbox)
            elapsed = now - previous.last_seen
            velocity = (
                (new_center[0] - old_center[0]) / elapsed,
                (new_center[1] - old_center[1]) / elapsed,
            )
            if descriptor is None:
                descriptor = previous.descriptor
        self.observed[track_id] = _ObservedSession(
            session, track_id, bbox, descriptor, now, velocity
        )

    def expire(self, track_id: int) -> None:
        value = self.observed.pop(track_id, None)
        if value:
            self.recently_lost[track_id] = value

    def match(self, bbox: BBox, crop, now: float) -> LocalStitchMatch | None:
        if not settings.local_session_stitch_enabled:
            return None
        descriptor = clothing_descriptor(crop)
        if descriptor is None:
            return None
        candidates: list[tuple[float, float, float, _ObservedSession]] = []
        for track_id, candidate in list(self.recently_lost.items()):
            gap = now - candidate.last_seen
            if gap > settings.local_session_stitch_max_gap_seconds:
                self.recently_lost.pop(track_id, None)
                continue
            if gap < 0 or candidate.descriptor is None:
                continue
            old_center = center(candidate.bbox)
            predicted = (
                old_center[0] + candidate.velocity[0] * gap,
                old_center[1] + candidate.velocity[1] * gap,
            )
            spatial = distance(predicted, center(bbox))
            appearance = cosine_distance(descriptor, candidate.descriptor)
            if (
                spatial <= settings.local_session_stitch_max_center_distance
                and appearance <= settings.local_session_stitch_appearance_threshold
            ):
                candidates.append((appearance, spatial, gap, candidate))
        candidates.sort(key=lambda item: (item[0], item[1]))
        if not candidates:
            return None
        best = candidates[0]
        if len(candidates) > 1 and candidates[1][0] - best[0] < settings.local_session_stitch_min_margin:
            return None
        appearance, spatial, gap, candidate = best
        appearance_score = max(
            0.0, 1.0 - appearance / settings.local_session_stitch_appearance_threshold
        )
        spatial_score = max(
            0.0, 1.0 - spatial / settings.local_session_stitch_max_center_distance
        )
        time_score = max(
            0.0, 1.0 - gap / settings.local_session_stitch_max_gap_seconds
        )
        confidence = 0.60 * appearance_score + 0.25 * spatial_score + 0.15 * time_score
        if confidence < settings.local_session_stitch_min_confidence:
            return None
        self.recently_lost.pop(candidate.track_id, None)
        return LocalStitchMatch(
            session=candidate.session,
            previous_track_id=candidate.track_id,
            gap_seconds=gap,
            appearance_distance=appearance,
            spatial_distance=spatial,
            confidence=confidence,
        )

    def clear(self) -> None:
        self.observed.clear()
        self.recently_lost.clear()

