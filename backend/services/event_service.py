from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from config import settings
from db_models.activity_event import ActivityEvent
from services.evidence_service import normalize_unknown_reason
from utilities.time_utils import seconds_between


@dataclass
class EventContext:
    worker_session_id: str
    track_id: int
    camera_id: int
    camera_session_id: str


@dataclass
class _EvidenceAccumulator:
    samples: int = 0
    body_total: float = 0.0
    wrist_total: float = 0.0
    elbow_total: float = 0.0
    latest_evidence: dict | None = None
    evidence_quality: str | None = None
    raw_track_ids: set[int] | None = None


class EventService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.active: dict[int, ActivityEvent] = {}
        self._accumulators: dict[int, _EvidenceAccumulator] = {}

    def open(self, context: EventContext, activity: str, presence: str, at: datetime, confidence: float, zone=None, reasons=None, limitations=None, unknown_reason=None, evidence=None) -> ActivityEvent:
        details = dict(evidence or {})
        event = ActivityEvent(
            id=f"EV-{uuid.uuid4().hex[:16]}", worker_session_id=context.worker_session_id,
            track_id=context.track_id, camera_id=context.camera_id, camera_session_id=context.camera_session_id,
            presence=presence, activity=activity, start_time=at, confidence=confidence, zone=zone,
            reasons_json=list(reasons or []), limitations_json=list(limitations or []),
            unknown_reason=normalize_unknown_reason(activity, unknown_reason),
            evidence_json=details,
            raw_track_ids_json=[context.track_id],
            confirmation_seconds=(
                float(details.get("idle_confirmation_seconds", 0))
                if activity == "IDLE"
                else None
            ),
            evidence_quality=details.get("evidence_quality"),
            transition_type="IDLE_STARTED" if activity == "IDLE" else None,
        )
        self.active[context.track_id] = event
        self._accumulators[context.track_id] = _EvidenceAccumulator(
            latest_evidence=details,
            evidence_quality=details.get("evidence_quality"),
            raw_track_ids={context.track_id},
        )
        return event

    def observe(self, track_id: int, evidence: dict | None = None) -> None:
        event = self.active.get(track_id)
        if event is None:
            return
        details = dict(evidence or {})
        raw_track_id = details.get("raw_track_id", track_id)
        accumulator = self._accumulators.setdefault(track_id, _EvidenceAccumulator())
        accumulator.latest_evidence = details
        accumulator.evidence_quality = (
            details.get("evidence_quality") or accumulator.evidence_quality
        )
        if accumulator.raw_track_ids is None:
            accumulator.raw_track_ids = set(event.raw_track_ids_json or [track_id])
        accumulator.raw_track_ids.add(int(raw_track_id))
        accumulator.samples += 1
        accumulator.body_total += float(details.get("body_motion", 0) or 0)
        accumulator.wrist_total += float(details.get("wrist_motion", 0) or 0)
        accumulator.elbow_total += float(details.get("elbow_motion", 0) or 0)

    def close(
        self,
        track_id: int,
        at: datetime,
        ending_reason: str | None = None,
    ) -> ActivityEvent | None:
        event = self.active.pop(track_id, None)
        if not event:
            return None
        accumulator = self._accumulators.pop(track_id, _EvidenceAccumulator())
        event.end_time = at
        event.duration_seconds = seconds_between(event.start_time, at)
        event.ending_reason = ending_reason
        if accumulator.latest_evidence is not None:
            event.evidence_json = accumulator.latest_evidence
        event.evidence_quality = accumulator.evidence_quality or event.evidence_quality
        if accumulator.raw_track_ids:
            event.raw_track_ids_json = sorted(accumulator.raw_track_ids)
        if event.activity == "IDLE":
            event.end_transition_type = "IDLE_ENDED"
        if accumulator.samples:
            event.average_body_movement = accumulator.body_total / accumulator.samples
            event.average_wrist_movement = accumulator.wrist_total / accumulator.samples
            event.average_elbow_movement = accumulator.elbow_total / accumulator.samples
        # A confirmation immediately followed by a camera/track shutdown can
        # create a sub-second interval. Keep it available to the caller for
        # diagnostics, but do not persist it as manager evidence.
        persistable = not (
            event.activity == "IDLE"
            and float(event.duration_seconds or 0) < settings.idle_min_event_seconds
        )
        if persistable:
            self.db.add(event)
            self.db.flush()
        return event

    def transition(self, context: EventContext, activity: str, presence: str, at: datetime, confidence: float, zone=None, reasons=None, limitations=None, unknown_reason=None, evidence=None, ending_reason=None) -> tuple[ActivityEvent | None, ActivityEvent]:
        closed = self.close(context.track_id, at, ending_reason)
        opened = self.open(context, activity, presence, at, confidence, zone, reasons, limitations, unknown_reason, evidence)
        return closed, opened

    def close_all(self, at: datetime) -> list[ActivityEvent]:
        return [event for track_id in list(self.active) if (event := self.close(track_id, at, "camera_processing_ended"))]
