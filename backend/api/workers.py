from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import require_manager
from database import get_db
from db_models.activity_event import ActivityEvent
from db_models.worker_session import WorkerSession
from db_models.worker_identity import WorkerIdentityLink
from db_models.worker_snapshot import WorkerSnapshot
from schemas.event import EventResponse
from schemas.worker import SnapshotResponse, WorkerSessionResponse

router = APIRouter(prefix="/worker-sessions", tags=["worker sessions"], dependencies=[Depends(require_manager)])


def _worker_response(session: WorkerSession, link: WorkerIdentityLink | None) -> WorkerSessionResponse:
    return WorkerSessionResponse(
        id=session.id,
        camera_id=session.camera_id,
        camera_session_id=session.camera_session_id,
        track_id=session.track_id,
        employee_id=session.employee_id,
        display_name=session.display_name,
        first_seen=session.first_seen,
        last_seen=session.last_seen,
        ended_at=session.ended_at,
        observed_seconds=session.observed_seconds,
        role_confidence=session.role_confidence,
        limitations_json=session.limitations_json or [],
        global_worker_id=link.worker_identity_id if link else None,
        identity_match_status=link.match_status if link else None,
        identity_confidence=link.confidence if link else None,
    )


@router.get("", response_model=list[WorkerSessionResponse])
def list_worker_sessions(camera_id: int | None = None, db: Session = Depends(get_db)):
    query = (
        select(WorkerSession, WorkerIdentityLink)
        .outerjoin(WorkerIdentityLink, WorkerIdentityLink.worker_session_id == WorkerSession.id)
        .order_by(WorkerSession.first_seen.desc())
    )
    if camera_id is not None:
        query = query.where(WorkerSession.camera_id == camera_id)
    return [_worker_response(session, link) for session, link in db.execute(query).all()]


@router.get("/{worker_session_id}", response_model=WorkerSessionResponse)
def get_worker_session(worker_session_id: str, db: Session = Depends(get_db)):
    value = db.get(WorkerSession, worker_session_id)
    if not value:
        raise HTTPException(404, "Worker session not found")
    return _worker_response(value, db.get(WorkerIdentityLink, worker_session_id))


@router.get("/{worker_session_id}/events", response_model=list[EventResponse])
def worker_events(worker_session_id: str, db: Session = Depends(get_db)):
    if not db.get(WorkerSession, worker_session_id):
        raise HTTPException(404, "Worker session not found")
    return db.scalars(select(ActivityEvent).where(ActivityEvent.worker_session_id == worker_session_id).order_by(ActivityEvent.start_time)).all()


@router.get("/{worker_session_id}/snapshots", response_model=list[SnapshotResponse])
def worker_snapshots(worker_session_id: str, db: Session = Depends(get_db)):
    if not db.get(WorkerSession, worker_session_id):
        raise HTTPException(404, "Worker session not found")
    values = db.scalars(select(WorkerSnapshot).where(WorkerSnapshot.worker_session_id == worker_session_id).order_by(WorkerSnapshot.quality.desc())).all()
    return [SnapshotResponse(id=item.id, worker_session_id=item.worker_session_id, kind=item.kind, quality=item.quality, width=item.width, height=item.height, media_id=item.file_path) for item in values]
