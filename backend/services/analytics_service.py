from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from db_models.activity_event import ActivityEvent
from db_models.customer_session import CustomerSession
from db_models.health_event import HealthEvent
from db_models.worker_identity import WorkerIdentityLink
from db_models.worker_session import WorkerSession
from services.customer_analytics import customer_metrics
from services.evidence_service import normalize_unknown_reason
from utilities.time_utils import day_bounds

ACTIVITY_FIELDS = {
    "SERVING_CUSTOMER": "serving_customer_seconds", "FETCHING_MEDICINE": "fetching_medicine_seconds",
    "CASHIER_WORK": "cashier_work_seconds", "COMPUTER_POS_WORK": "computer_pos_seconds",
    "SHELF_WORK": "shelf_work_seconds", "OTHER_WORK": "other_work_seconds",
    "ON_PHONE": "confirmed_phone_seconds", "POSSIBLE_PHONE": "possible_phone_seconds",
    "POSSIBLE_IDLE": "possible_idle_seconds", "UNKNOWN": "unknown_activity_seconds",
    "IDLE": "confirmed_idle_seconds",
    "APPROVED_BREAK": "approved_break_seconds",
}
PRODUCTIVE = {"SERVING_CUSTOMER", "FETCHING_MEDICINE", "CASHIER_WORK", "COMPUTER_POS_WORK", "SHELF_WORK", "OTHER_WORK"}


def daily_analytics(db: Session, report_date: date) -> dict:
    start, end = day_bounds(report_date)
    events = db.scalars(select(ActivityEvent).where(ActivityEvent.start_time >= start, ActivityEvent.start_time <= end, ActivityEvent.end_time.is_not(None))).all()
    metrics = defaultdict(float)
    sessions: set[str] = set()
    for event in events:
        duration = float(event.duration_seconds or 0)
        sessions.add(event.worker_session_id)
        if event.presence == "OUT_OF_ZONE":
            metrics["out_of_zone_seconds"] += duration
        elif event.presence == "ABSENT":
            metrics["absent_seconds"] += duration
        if event.review_status == "false_alarm":
            continue
        field = ACTIVITY_FIELDS.get(event.activity)
        if field:
            metrics[field] += duration
        if event.activity in PRODUCTIVE:
            metrics["confirmed_productive_seconds"] += duration
    health = db.scalars(select(HealthEvent).where(HealthEvent.started_at >= start, HealthEvent.started_at <= end)).all()
    unavailable = sum(float(item.duration_seconds or 0) for item in health if item.status in {"UNAVAILABLE", "FROZEN", "RECONNECTING"})
    metrics["camera_unavailable_seconds"] = unavailable
    total = sum(float(event.duration_seconds or 0) for event in events)
    unknown = metrics["unknown_activity_seconds"]
    observed = max(0.0, total - unavailable)
    metrics["camera_observed_seconds"] = observed
    unknown_reasons: defaultdict[str, float] = defaultdict(float)
    for event in events:
        if event.activity == "UNKNOWN" and event.review_status != "false_alarm":
            unknown_reasons[
                normalize_unknown_reason(
                    "UNKNOWN", event.unknown_reason, legacy=True
                )
            ] += float(event.duration_seconds or 0)
    worker_sessions = db.scalars(
        select(WorkerSession).where(
            WorkerSession.first_seen >= start, WorkerSession.first_seen <= end
        )
    ).all()
    session_ids = [session.id for session in worker_sessions]
    identity_links = (
        db.scalars(
            select(WorkerIdentityLink).where(
                WorkerIdentityLink.worker_session_id.in_(session_ids)
            )
        ).all()
        if session_ids
        else []
    )
    global_ids = {link.worker_identity_id for link in identity_links}
    cameras_by_identity: dict[str, set[int]] = {}
    camera_by_session = {session.id: session.camera_id for session in worker_sessions}
    for link in identity_links:
        cameras_by_identity.setdefault(link.worker_identity_id, set()).add(
            camera_by_session[link.worker_session_id]
        )
    metrics["global_anonymous_worker_count"] = len(global_ids)
    metrics["multi_camera_worker_count"] = sum(
        len(camera_ids) > 1 for camera_ids in cameras_by_identity.values()
    )
    quality = {
        "camera_availability_percent": round(100 * observed / total, 2) if total else None,
        "observation_coverage_percent": round(100 * observed / total, 2) if total else None,
        "tracking_coverage_percent": None,
        "pose_availability_percent": None,
        "phone_model_availability_percent": None,
        "average_processing_fps": None,
        "p95_processing_latency_ms": None,
        "unknown_activity_percent": round(100 * unknown / total, 2) if total else None,
        "unassigned_global_id_session_count": len(session_ids) - len(identity_links),
        "identity_review_required_count": sum(
            link.match_status in {"appearance_matched", "ambiguous_separate"}
            for link in identity_links
        ),
        "sessions_without_face_preview": None,
        "camera_unavailable_seconds": unavailable,
    }
    return {
        "report_date": report_date.isoformat(),
        **{key: round(value, 3) for key, value in metrics.items()},
        "unknown_seconds_by_reason": {
            key: round(value, 3) for key, value in unknown_reasons.items()
        },
        "report_quality": quality,
    }


def customer_daily_analytics(db: Session, report_date: date) -> dict:
    start, end = day_bounds(report_date)
    sessions = db.scalars(select(CustomerSession).where(CustomerSession.waiting_started_at >= start, CustomerSession.waiting_started_at <= end)).all()
    metrics = customer_metrics(sessions)
    metrics["customers_waiting_over_threshold"] = sum(
        float(session.waiting_seconds or 0) >= settings.customer_wait_threshold_seconds
        for session in sessions
    )
    metrics["counter_uncovered_while_customers_waited_seconds"] = None
    return metrics
