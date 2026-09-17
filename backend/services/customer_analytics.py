from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime

from config import settings
from utilities.geometry import BBox, center, distance
from utilities.time_utils import seconds_between

ACTIVE_SERVICE_PHASES = {
    "SERVING_AT_COUNTER",
    "FETCHING_MEDICINE",
    "RETURNING_TO_CUSTOMER",
    "COMPLETING_TRANSACTION",
}
MEDICINE_RETRIEVAL_PHASES = {"FETCHING_MEDICINE", "RETURNING_TO_CUSTOMER"}
TERMINAL_PHASES = {"COMPLETED", "ABANDONED", "INTERRUPTED"}
SERVICE_ZONES = {"cashier", "service_position", "register_interaction", "computer", "pos"}
RETRIEVAL_ZONES = {
    "shelf_interaction",
    "medicine",
    "medicine_shelf",
    "storage",
}
TRANSACTION_ZONES = {"register_interaction", "computer", "pos"}


@dataclass
class CustomerObservation:
    track_id: int
    bbox: BBox
    zones: set[str]
    confidence: float = 0.0
    camera_id: int = 0


@dataclass
class WorkerObservation:
    worker_session_id: str
    track_id: int
    bbox: BBox
    zones: set[str]
    confidence: float = 0.0


@dataclass
class ServicePhaseRecord:
    id: str
    phase: str
    started_at: datetime
    ended_at: datetime | None = None
    evidence: dict = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float | None:
        return seconds_between(self.started_at, self.ended_at) if self.ended_at else None


@dataclass
class AssignmentRecord:
    id: str
    worker_session_id: str
    started_at: datetime
    confidence: float
    ended_at: datetime | None = None
    status: str = "active"
    reasons: list[str] = field(default_factory=list)


@dataclass
class AnonymousCustomerSession:
    service_session_id: str
    customer_track_id: int
    camera_id: int
    waiting_started_at: datetime
    worker_session_id: str | None = None
    service_started_at: datetime | None = None
    service_ended_at: datetime | None = None
    waiting_seconds: float | None = None
    service_seconds: float | None = None
    completed: bool = False
    left_without_service: bool = False
    confidence: float = 0
    current_phase: str = "WAITING"
    last_customer_seen_at: datetime | None = None
    last_worker_seen_at: datetime | None = None
    last_direct_interaction_at: datetime | None = None
    medicine_retrieval_started_at: datetime | None = None
    medicine_retrieval_ended_at: datetime | None = None
    medicine_retrieval_seconds: float = 0
    direct_interaction_seconds: float = 0
    transaction_seconds: float = 0
    service_completed_at: datetime | None = None
    outcome: str = "ACTIVE"
    review_status: str = "unreviewed"
    assignment_confidence: float = 0
    trust_classification: str | None = None
    original_track_ids: list[int] = field(default_factory=list)
    limitations: list[str] = field(
        default_factory=lambda: [
            "Anonymous camera-local customer journey; no face or appearance matching is used."
        ]
    )
    last_bbox: BBox | None = None
    customer_missing_since: datetime | None = None
    phase_records: list[ServicePhaseRecord] = field(default_factory=list)
    assignments: list[AssignmentRecord] = field(default_factory=list)

    def phase_seconds(self, phase: str, at: datetime | None = None) -> float:
        total = 0.0
        for record in self.phase_records:
            if record.phase != phase:
                continue
            end = record.ended_at or at
            if end is not None:
                total += seconds_between(record.started_at, end) or 0.0
        return total


class CustomerAnalyticsService:
    """Camera-local, one-to-one customer journey and service state machine."""

    def __init__(
        self,
        *,
        start_confirm_seconds: float | None = None,
        customer_lost_seconds: float | None = None,
        worker_return_seconds: float | None = None,
        retrieval_timeout_seconds: float | None = None,
        service_max_seconds: float | None = None,
        service_lost_grace_seconds: float | None = None,
        service_end_confirm_seconds: float | None = None,
    ) -> None:
        self.active: dict[int, AnonymousCustomerSession] = {}
        self.completed_sessions: list[AnonymousCustomerSession] = []
        self._counter = 0
        self._assignment_candidates: dict[tuple[str, str], datetime] = {}
        self.start_confirm_seconds = (
            settings.service_start_confirm_seconds
            if start_confirm_seconds is None
            else start_confirm_seconds
        )
        self.customer_lost_seconds = (
            settings.customer_lost_timeout_seconds
            if customer_lost_seconds is None
            else customer_lost_seconds
        )
        self.worker_return_seconds = (
            settings.worker_return_timeout_seconds
            if worker_return_seconds is None
            else worker_return_seconds
        )
        self.retrieval_timeout_seconds = (
            settings.medicine_retrieval_timeout_seconds
            if retrieval_timeout_seconds is None
            else retrieval_timeout_seconds
        )
        self.service_max_seconds = (
            settings.service_max_seconds
            if service_max_seconds is None
            else service_max_seconds
        )
        self.service_lost_grace_seconds = (
            settings.service_lost_grace_seconds
            if service_lost_grace_seconds is None
            else service_lost_grace_seconds
        )
        self.service_end_confirm_seconds = (
            settings.service_end_confirm_seconds
            if service_end_confirm_seconds is None
            else service_end_confirm_seconds
        )

    def waiting(
        self, track_id: int, camera_id: int, now: datetime
    ) -> AnonymousCustomerSession:
        return self.observe_customer(track_id, camera_id, now, None, {"waiting"}, 0)

    def observe_customer(
        self,
        track_id: int,
        camera_id: int,
        now: datetime,
        bbox: BBox | None,
        zones: set[str],
        confidence: float,
    ) -> AnonymousCustomerSession:
        current = self.active.get(track_id)
        if current is None:
            current = self._short_gap_relink(track_id, camera_id, now, bbox)
        if current is None:
            self._counter += 1
            current = AnonymousCustomerSession(
                service_session_id=f"CSVC-{now:%Y%m%d}-C{camera_id}-{self._counter:04d}",
                customer_track_id=track_id,
                camera_id=camera_id,
                waiting_started_at=now,
                last_customer_seen_at=now,
                original_track_ids=[track_id],
                last_bbox=bbox,
            )
            current.phase_records.append(
                ServicePhaseRecord(f"{current.service_session_id}-P001", "WAITING", now)
            )
            self.active[track_id] = current
        current.last_customer_seen_at = now
        current.customer_missing_since = None
        current.last_bbox = bbox or current.last_bbox
        current.confidence = max(current.confidence, confidence)
        return current

    def _short_gap_relink(
        self, track_id: int, camera_id: int, now: datetime, bbox: BBox | None
    ) -> AnonymousCustomerSession | None:
        if bbox is None or settings.customer_short_gap_relink_seconds <= 0:
            return None
        matches: list[tuple[float, int, AnonymousCustomerSession]] = []
        for old_track_id, session in self.active.items():
            if (
                session.camera_id != camera_id
                or session.customer_missing_since is None
                or session.last_bbox is None
            ):
                continue
            gap = seconds_between(session.customer_missing_since, now) or 0.0
            spatial = distance(center(session.last_bbox), center(bbox))
            if (
                gap <= settings.customer_short_gap_relink_seconds
                and spatial <= settings.customer_relink_max_center_distance
            ):
                matches.append((spatial, old_track_id, session))
        if len(matches) != 1:
            return None
        _, old_track_id, session = matches[0]
        self.active.pop(old_track_id, None)
        session.customer_track_id = track_id
        session.original_track_ids.append(track_id)
        session.customer_missing_since = None
        self.active[track_id] = session
        return session

    def mark_customer_missing(self, track_id: int, now: datetime) -> None:
        session = self.active.get(track_id)
        if session and session.customer_missing_since is None:
            session.customer_missing_since = now

    def begin_service(
        self,
        track_id: int,
        worker_session_id: str | None,
        now: datetime,
        confidence: float,
    ) -> AnonymousCustomerSession | None:
        session = self.active.get(track_id)
        if not session or not worker_session_id or session.service_started_at:
            return session
        if worker_session_id in self.assigned_worker_ids:
            return session
        self._assign(session, worker_session_id, now, confidence, ["confirmed direct interaction"])
        return session

    @property
    def assigned_worker_ids(self) -> set[str]:
        return {
            session.worker_session_id
            for session in self.active.values()
            if session.worker_session_id and session.current_phase not in TERMINAL_PHASES
        }

    def service_for_worker(self, worker_session_id: str) -> AnonymousCustomerSession | None:
        return next(
            (
                session
                for session in self.active.values()
                if session.worker_session_id == worker_session_id
                and session.current_phase in ACTIVE_SERVICE_PHASES
            ),
            None,
        )

    def update_scene(
        self,
        customers: list[CustomerObservation],
        workers: list[WorkerObservation],
        now: datetime,
        max_interaction_distance: float,
    ) -> None:
        visible_customer_ids = {item.track_id for item in customers}
        for item in customers:
            self.observe_customer(
                item.track_id,
                item.camera_id or self._camera_id_for(item.track_id),
                now,
                item.bbox,
                item.zones,
                item.confidence,
            )
        for track_id, session in list(self.active.items()):
            if track_id not in visible_customer_ids and session.customer_missing_since is None:
                session.customer_missing_since = now

        customer_by_track = {item.track_id: item for item in customers}
        worker_by_session = {item.worker_session_id: item for item in workers}

        for session in list({id(value): value for value in self.active.values()}.values()):
            customer = customer_by_track.get(session.customer_track_id)
            worker = worker_by_session.get(session.worker_session_id or "")
            if session.worker_session_id:
                self._update_assigned(session, customer, worker, now, max_interaction_distance)
            self._apply_timeouts(session, now)

        available_workers = {
            item.worker_session_id: item
            for item in workers
            if item.worker_session_id not in self.assigned_worker_ids
        }
        unassigned = [
            session
            for session in {id(value): value for value in self.active.values()}.values()
            if session.worker_session_id is None and session.current_phase == "WAITING"
        ]
        candidates: list[tuple[float, AnonymousCustomerSession, WorkerObservation]] = []
        for session in unassigned:
            customer = customer_by_track.get(session.customer_track_id)
            if customer is None:
                continue
            for worker in available_workers.values():
                if not self._direct_interaction(customer, worker, max_interaction_distance):
                    continue
                candidates.append(
                    (distance(center(customer.bbox), center(worker.bbox)), session, worker)
                )
        used_customers: set[str] = set()
        used_workers: set[str] = set()
        live_candidate_keys: set[tuple[str, str]] = set()
        for _, session, worker in sorted(candidates, key=lambda item: item[0]):
            if session.service_session_id in used_customers or worker.worker_session_id in used_workers:
                continue
            key = (session.service_session_id, worker.worker_session_id)
            live_candidate_keys.add(key)
            started = self._assignment_candidates.setdefault(key, now)
            if (seconds_between(started, now) or 0.0) >= self.start_confirm_seconds:
                self._assign(
                    session,
                    worker.worker_session_id,
                    now,
                    worker.confidence,
                    ["one-to-one direct interaction persisted through confirmation window"],
                )
                used_customers.add(session.service_session_id)
                used_workers.add(worker.worker_session_id)
        self._assignment_candidates = {
            key: value
            for key, value in self._assignment_candidates.items()
            if key in live_candidate_keys
        }

    def _camera_id_for(self, track_id: int) -> int:
        current = self.active.get(track_id)
        if current:
            return current.camera_id
        existing = next(iter(self.active.values()), None)
        return existing.camera_id if existing else 0

    @staticmethod
    def _direct_interaction(
        customer: CustomerObservation,
        worker: WorkerObservation,
        maximum_distance: float,
    ) -> bool:
        service_context = bool((customer.zones | worker.zones) & SERVICE_ZONES)
        return service_context and distance(center(customer.bbox), center(worker.bbox)) <= maximum_distance

    def _assign(
        self,
        session: AnonymousCustomerSession,
        worker_session_id: str,
        now: datetime,
        confidence: float,
        reasons: list[str],
    ) -> None:
        session.worker_session_id = worker_session_id
        session.service_started_at = now
        session.waiting_seconds = seconds_between(session.waiting_started_at, now)
        session.assignment_confidence = confidence
        session.last_worker_seen_at = now
        session.last_direct_interaction_at = now
        assignment = AssignmentRecord(
            id=f"{session.service_session_id}-A{len(session.assignments) + 1:03d}",
            worker_session_id=worker_session_id,
            started_at=now,
            confidence=confidence,
            reasons=reasons,
        )
        session.assignments.append(assignment)
        self._transition(session, "SERVING_AT_COUNTER", now, {"assignment": reasons})

    def _update_assigned(
        self,
        session: AnonymousCustomerSession,
        customer: CustomerObservation | None,
        worker: WorkerObservation | None,
        now: datetime,
        maximum_distance: float,
    ) -> None:
        if worker is not None:
            session.last_worker_seen_at = now
        if customer is None or worker is None:
            return
        if self._direct_interaction(customer, worker, maximum_distance):
            session.last_direct_interaction_at = now
            phase = (
                "COMPLETING_TRANSACTION"
                if worker.zones & TRANSACTION_ZONES
                else "SERVING_AT_COUNTER"
            )
            self._transition(session, phase, now, {"direct_interaction": True})
            return
        if worker.zones & RETRIEVAL_ZONES:
            self._transition(
                session,
                "FETCHING_MEDICINE",
                now,
                {"worker_zones": sorted(worker.zones), "customer_present": True},
            )
            return
        if session.current_phase == "FETCHING_MEDICINE":
            self._transition(
                session,
                "RETURNING_TO_CUSTOMER",
                now,
                {"customer_present": True},
            )

    def _transition(
        self,
        session: AnonymousCustomerSession,
        phase: str,
        now: datetime,
        evidence: dict | None = None,
    ) -> None:
        if session.current_phase == phase:
            return
        if session.phase_records and session.phase_records[-1].ended_at is None:
            previous = session.phase_records[-1]
            previous.ended_at = now
            duration = previous.duration_seconds or 0.0
            if previous.phase == "SERVING_AT_COUNTER":
                session.direct_interaction_seconds += duration
            elif previous.phase in MEDICINE_RETRIEVAL_PHASES:
                session.medicine_retrieval_seconds += duration
            elif previous.phase == "COMPLETING_TRANSACTION":
                session.transaction_seconds += duration
                session.direct_interaction_seconds += duration
        if (
            phase == "FETCHING_MEDICINE"
            and session.current_phase not in MEDICINE_RETRIEVAL_PHASES
        ):
            session.medicine_retrieval_started_at = now
            session.medicine_retrieval_ended_at = None
        if (
            session.current_phase in MEDICINE_RETRIEVAL_PHASES
            and phase not in MEDICINE_RETRIEVAL_PHASES
        ):
            session.medicine_retrieval_ended_at = now
        session.current_phase = phase
        session.phase_records.append(
            ServicePhaseRecord(
                f"{session.service_session_id}-P{len(session.phase_records) + 1:03d}",
                phase,
                now,
                evidence=evidence or {},
            )
        )

    def _apply_timeouts(self, session: AnonymousCustomerSession, now: datetime) -> None:
        if session.current_phase in TERMINAL_PHASES:
            return
        if session.customer_missing_since is not None:
            # Require a short continuous absence before the lost timeout begins;
            # a one-frame detector miss must not close the customer journey.
            missing = seconds_between(session.customer_missing_since, now) or 0.0
            if (
                missing >= self.service_end_confirm_seconds
                and missing >= self.customer_lost_seconds
            ):
                effective_end = session.last_customer_seen_at or now
                outcome = "COMPLETED" if session.service_started_at else "ABANDONED"
                self._finish(session, effective_end, outcome)
                return
        if session.service_started_at:
            service_age = seconds_between(session.service_started_at, now) or 0.0
            worker_missing = (
                seconds_between(session.last_worker_seen_at, now)
                if session.last_worker_seen_at
                else service_age
            ) or 0.0
            retrieval_age = (
                seconds_between(session.medicine_retrieval_started_at, now)
                if session.current_phase in MEDICINE_RETRIEVAL_PHASES
                and session.medicine_retrieval_started_at
                else 0.0
            ) or 0.0
            if (
                worker_missing >= self.service_lost_grace_seconds
                and worker_missing >= self.worker_return_seconds
            ):
                self._finish(session, now, "INTERRUPTED")
            elif retrieval_age >= self.retrieval_timeout_seconds:
                self._finish(session, now, "INTERRUPTED")
            elif service_age >= self.service_max_seconds:
                self._finish(session, now, "INTERRUPTED")

    def advance(self, now: datetime) -> None:
        for session in list({id(value): value for value in self.active.values()}.values()):
            self._apply_timeouts(session, now)

    def leave(self, track_id: int, now: datetime) -> AnonymousCustomerSession | None:
        session = self.active.get(track_id)
        if not session:
            return None
        self._finish(session, now, "COMPLETED" if session.service_started_at else "ABANDONED")
        return session

    def interrupt_all(self, now: datetime) -> list[AnonymousCustomerSession]:
        sessions = list({id(value): value for value in self.active.values()}.values())
        for session in sessions:
            self._finish(session, now, "INTERRUPTED")
        return sessions

    def close_session(
        self, session_id: str, now: datetime, outcome: str = "INTERRUPTED"
    ) -> AnonymousCustomerSession | None:
        session = next(
            (
                value
                for value in {id(item): item for item in self.active.values()}.values()
                if value.service_session_id == session_id
            ),
            None,
        )
        if session:
            self._finish(session, now, outcome)
        return session

    def _finish(
        self, session: AnonymousCustomerSession, effective_end: datetime, outcome: str
    ) -> None:
        if session.current_phase in TERMINAL_PHASES:
            return
        self._transition(session, outcome, effective_end, {"outcome": outcome})
        if session.phase_records and session.phase_records[-1].ended_at is None:
            session.phase_records[-1].ended_at = effective_end
        session.service_ended_at = effective_end
        session.service_completed_at = effective_end
        session.outcome = outcome
        session.completed = outcome == "COMPLETED"
        session.left_without_service = outcome == "ABANDONED"
        if session.service_started_at:
            session.service_seconds = seconds_between(
                session.service_started_at, effective_end
            )
        else:
            session.waiting_seconds = seconds_between(
                session.waiting_started_at, effective_end
            )
        if session.assignments:
            assignment = session.assignments[-1]
            assignment.ended_at = effective_end
            assignment.status = "completed" if outcome == "COMPLETED" else "interrupted"
        self.active.pop(session.customer_track_id, None)
        self.completed_sessions.append(session)


def customer_trust_classification(session) -> str:
    """Classify records without promoting incomplete legacy rows to trusted data."""
    outcome = getattr(session, "outcome", "ACTIVE") or "ACTIVE"
    completed = bool(getattr(session, "completed", False)) or outcome == "COMPLETED"
    if not completed:
        if outcome == "INTERRUPTED":
            return "interrupted"
        if outcome == "ABANDONED" or bool(
            getattr(session, "left_without_service", False)
        ):
            return "abandoned"
        return "active"
    service_started_at = getattr(session, "service_started_at", None)
    service_completed_at = getattr(session, "service_completed_at", None)
    chronological = bool(
        service_started_at
        and service_completed_at
        and (seconds_between(service_started_at, service_completed_at) or 0) >= 0
    )
    required = bool(
        service_started_at
        and service_completed_at
        and chronological
        and float(getattr(session, "service_seconds", 0) or 0) > 0
        and getattr(session, "worker_session_id", None)
        and getattr(session, "current_phase", None) == "COMPLETED"
        and outcome == "COMPLETED"
    )
    if not required:
        return "legacy_incomplete"
    review_status = getattr(session, "review_status", "unreviewed")
    assignment_confidence = float(
        getattr(session, "assignment_confidence", 0) or 0
    )
    if review_status == "confirmed" or (
        assignment_confidence >= settings.customer_trusted_assignment_confidence
        and review_status not in {"needs_review", "corrected", "false_alarm"}
    ):
        return "trusted_completed"
    return "completed_needs_review"


def customer_metrics(sessions: list) -> dict:
    waits = [float(s.waiting_seconds) for s in sessions if s.waiting_seconds is not None]
    classifications = {
        id(session): customer_trust_classification(session) for session in sessions
    }
    trusted = [
        session
        for session in sessions
        if classifications[id(session)] == "trusted_completed"
    ]
    services = [
        float(s.service_seconds) for s in trusted if s.service_seconds is not None
    ]
    retrieval = [
        float(getattr(s, "medicine_retrieval_seconds", 0) or 0)
        for s in trusted
    ]
    now = datetime.now(UTC)
    active_waiting = sum(
        getattr(s, "current_phase", None) == "WAITING"
        and getattr(s, "outcome", "ACTIVE") == "ACTIVE"
        and not bool(getattr(s, "completed", False))
        and getattr(s, "last_customer_seen_at", None) is not None
        and (seconds_between(getattr(s, "last_customer_seen_at"), now) or 0)
        <= settings.customer_lost_timeout_seconds
        for s in sessions
    )
    return {
        "customers_detected": len(sessions),
        "completed_service_sessions": sum(bool(s.completed) for s in sessions),
        "customers_served": sum(bool(s.completed) for s in sessions),
        "trusted_completed_services": len(trusted),
        "completed_services_requiring_review": sum(
            classifications[id(session)] == "completed_needs_review"
            for session in sessions
        ),
        "legacy_incomplete_services": sum(
            classifications[id(session)] == "legacy_incomplete"
            for session in sessions
        ),
        "customers_currently_waiting": active_waiting,
        "average_wait_seconds": statistics.fmean(waits) if waits else None,
        "median_wait_seconds": statistics.median(waits) if waits else None,
        "longest_wait_seconds": max(waits) if waits else None,
        "average_service_seconds": statistics.fmean(services) if services else None,
        "median_service_seconds": statistics.median(services) if services else None,
        "longest_service_seconds": max(services) if services else None,
        "average_medicine_retrieval_seconds": (
            statistics.fmean(retrieval) if retrieval else None
        ),
        "customers_left_without_service": sum(bool(s.left_without_service) for s in sessions),
        "abandoned_customers": sum(
            getattr(s, "outcome", None) == "ABANDONED"
            or bool(getattr(s, "left_without_service", False))
            for s in sessions
        ),
        "interrupted_service_sessions": sum(
            getattr(s, "outcome", None) == "INTERRUPTED" for s in sessions
        ),
    }
