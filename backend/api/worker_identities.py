from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from api.auth import require_manager
from database import get_db
from db_models.worker_identity import WorkerAppearanceSignature, WorkerIdentity, WorkerIdentityLink
from db_models.worker_session import WorkerSession
from schemas.worker_identity import (
    IdentityAssignmentRequest,
    IdentitySessionResponse,
    WorkerIdentityResponse,
)
from services.global_identity_service import global_worker_identity_service

router = APIRouter(
    prefix="/worker-identities",
    tags=["global worker identities"],
    dependencies=[Depends(require_manager)],
)


@router.get("", response_model=list[WorkerIdentityResponse])
def list_worker_identities(
    report_date: date | None = None, db: Session = Depends(get_db)
):
    query = select(WorkerIdentity).order_by(WorkerIdentity.last_seen_at.desc())
    if report_date is not None:
        query = query.where(WorkerIdentity.scope_date == report_date)
    identities = db.scalars(query).all()
    if not identities:
        return []
    links = db.execute(
        select(
            WorkerIdentityLink.worker_identity_id,
            func.count(WorkerIdentityLink.worker_session_id),
        )
        .where(WorkerIdentityLink.worker_identity_id.in_([item.id for item in identities]))
        .group_by(WorkerIdentityLink.worker_identity_id)
    ).all()
    counts = dict(links)
    cameras = db.execute(
        select(WorkerIdentityLink.worker_identity_id, WorkerSession.camera_id)
        .join(WorkerSession, WorkerSession.id == WorkerIdentityLink.worker_session_id)
        .where(WorkerIdentityLink.worker_identity_id.in_([item.id for item in identities]))
        .distinct()
    ).all()
    cameras_by_identity: dict[str, set[int]] = {}
    for identity_id, camera_id in cameras:
        cameras_by_identity.setdefault(identity_id, set()).add(camera_id)
    return [
        WorkerIdentityResponse(
            id=item.id,
            display_name=item.display_name,
            scope_date=item.scope_date,
            status=item.status,
            created_at=item.created_at,
            last_seen_at=item.last_seen_at,
            last_camera_id=item.last_camera_id,
            session_count=int(counts.get(item.id, 0)),
            camera_ids=sorted(cameras_by_identity.get(item.id, set())),
            limitations_json=item.limitations_json or [],
        )
        for item in identities
    ]


@router.get("/{identity_id}/sessions", response_model=list[IdentitySessionResponse])
def identity_sessions(identity_id: str, db: Session = Depends(get_db)):
    if not db.get(WorkerIdentity, identity_id):
        raise HTTPException(404, "Global worker identity not found")
    rows = db.execute(
        select(WorkerIdentityLink, WorkerSession)
        .join(WorkerSession, WorkerSession.id == WorkerIdentityLink.worker_session_id)
        .where(WorkerIdentityLink.worker_identity_id == identity_id)
        .order_by(WorkerSession.first_seen)
    ).all()
    return [
        IdentitySessionResponse(
            worker_session_id=session.id,
            camera_id=session.camera_id,
            display_name=session.display_name,
            first_seen=session.first_seen,
            last_seen=session.last_seen,
            match_method=link.match_method,
            match_status=link.match_status,
            confidence=link.confidence,
            distance=link.distance,
            margin=link.margin,
        )
        for link, session in rows
    ]


@router.post("/{identity_id}/assign-session/{worker_session_id}")
def assign_session(
    identity_id: str,
    worker_session_id: str,
    payload: IdentityAssignmentRequest,
    db: Session = Depends(get_db),
):
    identity = db.get(WorkerIdentity, identity_id)
    session = db.get(WorkerSession, worker_session_id)
    if not identity:
        raise HTTPException(404, "Global worker identity not found")
    if not session:
        raise HTTPException(404, "Worker session not found")
    if session.first_seen.date() != identity.scope_date:
        raise HTTPException(
            409,
            "Global appearance IDs are day-scoped; the identity and session dates must match",
        )
    link = db.get(WorkerIdentityLink, worker_session_id)
    previous_identity = link.worker_identity_id if link else None
    now = datetime.now(UTC)
    if link is None:
        link = WorkerIdentityLink(
            worker_session_id=worker_session_id,
            worker_identity_id=identity_id,
            match_method="manager_assignment",
            match_status="manager_confirmed",
            confidence=1.0,
            reviewed_at=now,
            notes_json=[payload.note],
        )
        db.add(link)
    else:
        link.worker_identity_id = identity_id
        link.match_method = "manager_assignment"
        link.match_status = "manager_confirmed"
        link.confidence = 1.0
        link.reviewed_at = now
        link.notes_json = list(link.notes_json or []) + [payload.note]
    session.display_name = identity.display_name
    identity.status = "manager_confirmed"
    db.execute(
        update(WorkerAppearanceSignature)
        .where(WorkerAppearanceSignature.source_session_id == worker_session_id)
        .values(worker_identity_id=identity_id)
    )
    db.commit()
    global_worker_identity_service.manager_assignment_updated(
        worker_session_id, identity.scope_date
    )
    return {
        "success": True,
        "worker_session_id": worker_session_id,
        "global_worker_id": identity_id,
        "previous_global_worker_id": previous_identity,
        "match_status": "manager_confirmed",
    }
