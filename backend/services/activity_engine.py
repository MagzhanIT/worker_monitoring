from __future__ import annotations

from collections import deque

from config import settings
from services.evidence_service import ActivityEvidence, official_activity


class PhoneTemporalHistory:
    def __init__(self, window: int | None = None, min_hits: int | None = None, release_misses: int | None = None) -> None:
        self.window = window or settings.phone_temporal_window
        self.min_hits = min_hits or settings.phone_min_positive_checks
        self.release_misses = release_misses or settings.phone_release_misses
        self.hits: dict[int, deque[bool]] = {}
        self.misses: dict[int, int] = {}
        self.confirmed: set[int] = set()
        self.first_positive_at: dict[int, float] = {}
        self.last_positive_at: dict[int, float] = {}

    def update(
        self,
        track_id: int,
        associated_physical_phone: bool,
        timestamp: float | None = None,
    ) -> str:
        history = self.hits.setdefault(track_id, deque(maxlen=self.window))
        history.append(associated_physical_phone)
        if associated_physical_phone:
            self.misses[track_id] = 0
            if timestamp is not None:
                self.first_positive_at.setdefault(track_id, timestamp)
                self.last_positive_at[track_id] = timestamp
            confirmed_long_enough = (
                timestamp is None
                or timestamp - self.first_positive_at.get(track_id, timestamp)
                >= settings.phone_confirm_seconds
            )
            if sum(history) >= self.min_hits and confirmed_long_enough:
                self.confirmed.add(track_id)
        else:
            self.misses[track_id] = self.misses.get(track_id, 0) + 1
            held = bool(
                timestamp is not None
                and track_id in self.confirmed
                and timestamp - self.last_positive_at.get(track_id, timestamp)
                < settings.phone_hold_seconds
            )
            if self.misses[track_id] >= self.release_misses and not held:
                self.confirmed.discard(track_id)
                self.first_positive_at.pop(track_id, None)
        if track_id in self.confirmed:
            return "ON_PHONE"
        return "POSSIBLE_PHONE" if any(history) else "NO_PHONE_EVIDENCE"

    def clear(self, track_id: int) -> None:
        self.hits.pop(track_id, None)
        self.misses.pop(track_id, None)
        self.confirmed.discard(track_id)
        self.first_positive_at.pop(track_id, None)
        self.last_positive_at.pop(track_id, None)

    def confidence(self, track_id: int, timestamp: float | None = None) -> float:
        history = self.hits.get(track_id)
        if not history:
            return 0.0
        ratio = sum(history) / len(history)
        duration_score = 1.0
        if timestamp is not None and track_id in self.first_positive_at:
            duration_score = min(
                1.0,
                max(
                    0.0,
                    (timestamp - self.first_positive_at[track_id])
                    / max(settings.phone_confirm_seconds, 1e-6),
                ),
            )
        return round(0.65 * ratio + 0.35 * duration_score, 4)


class ActivityEngine:
    def choose(self, evidence: ActivityEvidence) -> str:
        return official_activity(evidence, settings.possible_idle_threshold_seconds)
