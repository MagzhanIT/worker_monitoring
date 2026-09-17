from datetime import UTC, datetime, timedelta

from db_models.activity_event import ActivityEvent
from db_models.camera import Camera
from db_models.camera_session import CameraSession
from db_models.worker_session import WorkerSession
from services.event_service import EventContext, EventService


def seed_context(db):
    now = datetime(2026, 7, 19, tzinfo=UTC)
    db.add(Camera(id=1, name="Counter", source="demo://sample"))
    db.add(CameraSession(id="CS-1", camera_id=1, source_type="demo"))
    db.add(WorkerSession(id="WS-1", camera_id=1, camera_session_id="CS-1", track_id=7, display_name="Worker 1", first_seen=now, last_seen=now))
    db.flush()
    return EventContext("WS-1", 7, 1, "CS-1"), now


def test_event_open_close_and_correct_duration(db):
    context, now = seed_context(db)
    service = EventService(db)
    service.open(context, "CASHIER_WORK", "VISIBLE", now, 0.8)
    closed = service.close(7, now + timedelta(seconds=5))
    assert closed.duration_seconds == 5
    assert db.get(ActivityEvent, closed.id).activity == "CASHIER_WORK"


def test_transition_closes_before_opening_without_double_count(db):
    context, now = seed_context(db)
    service = EventService(db)
    first = service.open(context, "CASHIER_WORK", "VISIBLE", now, 0.8)
    closed, second = service.transition(context, "ON_PHONE", "VISIBLE", now + timedelta(seconds=10), 0.9)
    assert closed.id == first.id and closed.end_time == second.start_time

