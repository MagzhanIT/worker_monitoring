from datetime import UTC, datetime, timedelta

from db_models.worker_session import WorkerSession
from services.event_service import EventService
from services.processing_service import ProcessingService
from services.worker_session_service import WorkerSessionService


def test_worker_session_creation_stability_and_closure():
    service = WorkerSessionService()
    now = datetime(2026, 7, 19, tzinfo=UTC)
    first = service.ensure(7, 1, "CS-1", now)
    again = service.ensure(7, 1, "CS-1", now + timedelta(seconds=2))
    assert first is again
    assert first.display_name == "Worker 1"
    assert first.employee_id is None
    assert service.close(7, now + timedelta(seconds=3)).ended_at is not None


def test_return_creates_new_unmerged_session():
    service = WorkerSessionService()
    now = datetime(2026, 7, 19, tzinfo=UTC)
    old = service.ensure(7, 1, "CS-1", now)
    service.close(7, now + timedelta(seconds=1))
    new = service.ensure(8, 1, "CS-1", now + timedelta(seconds=3))
    assert old.worker_session_id != new.worker_session_id
    assert new.display_name == "Worker 2"


def test_processing_closes_worker_loaded_from_sqlite_with_naive_timestamp(db):
    started = datetime(2026, 7, 19, tzinfo=UTC)
    sessions = WorkerSessionService()
    anonymous = sessions.ensure(7, 1, "CS-1", started)
    db.add(
        WorkerSession(
            id=anonymous.worker_session_id,
            camera_id=1,
            camera_session_id="CS-1",
            track_id=7,
            display_name="Worker 1",
            first_seen=started,
            last_seen=started,
        )
    )
    db.commit()
    db.expire_all()
    assert db.get(WorkerSession, anonymous.worker_session_id).first_seen.tzinfo is None

    service = ProcessingService.__new__(ProcessingService)
    service.worker_sessions = sessions
    service.roles = service.poses = service.phone_history = service.phone_search = _Clearable()
    service.zone_history = service.state_machine = service.work_motion = _Clearable()
    service._last_centers = {}
    service._last_moved_at = {}

    service._close_worker(db, EventService(db), 7, started + timedelta(seconds=5))

    stored = db.get(WorkerSession, anonymous.worker_session_id)
    assert stored.observed_seconds == 5
    assert stored.ended_at == started + timedelta(seconds=5)


class _Clearable:
    def clear(self, _track_id):
        return None
