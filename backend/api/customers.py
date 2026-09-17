from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import require_manager
from database import get_db
from db_models.customer_session import CustomerSession
from schemas.customer import (
    CustomerSessionCloseRequest,
    CustomerSessionResponse,
    CustomerSessionReviewRequest,
)
from services.camera_manager import camera_manager
from services.customer_analytics import customer_trust_classification
from utilities.time_utils import day_bounds, seconds_between, utc_now

router = APIRouter(
    prefix="/customer-sessions",
    tags=["customer service"],
    dependencies=[Depends(require_manager)],
)


@router.get("", response_model=list[CustomerSessionResponse])
def list_customer_sessions(
    report_date: date | None = None, db: Session = Depends(get_db)
):
    query = select(CustomerSession).order_by(CustomerSession.waiting_started_at.desc())
    if report_date:
        start, end = day_bounds(report_date)
        query = query.where(
            CustomerSession.waiting_started_at >= start,
            CustomerSession.waiting_started_at <= end,
        )
    return db.scalars(query).all()


@router.get("/{session_id}", response_model=CustomerSessionResponse)
def get_customer_session(session_id: str, db: Session = Depends(get_db)):
    row = db.get(CustomerSession, session_id)
    if not row:
        raise HTTPException(404, "Customer session not found")
    return row


@router.post("/{session_id}/close")
def close_customer_session(
    session_id: str,
    payload: CustomerSessionCloseRequest,
    db: Session = Depends(get_db),
):
    row = db.get(CustomerSession, session_id)
    if not row:
        raise HTTPException(404, "Customer session not found")
    if camera_manager.close_customer_session(row.camera_id, session_id, payload.outcome):
        return {"success": True, "queued": True, "tracking_preserved": True}
    now = utc_now()
    row.current_phase = payload.outcome
    row.outcome = payload.outcome
    row.service_ended_at = row.last_customer_seen_at or now
    row.service_completed_at = row.service_ended_at
    row.completed = payload.outcome == "COMPLETED"
    row.left_without_service = payload.outcome == "ABANDONED"
    if row.service_started_at:
        row.service_seconds = seconds_between(row.service_started_at, row.service_ended_at)
    row.trust_classification = customer_trust_classification(row)
    db.commit()
    return {"success": True, "queued": False, "tracking_preserved": True}


@router.put("/{session_id}/review", response_model=CustomerSessionResponse)
def review_customer_session(
    session_id: str,
    payload: CustomerSessionReviewRequest,
    db: Session = Depends(get_db),
):
    row = db.get(CustomerSession, session_id)
    if not row:
        raise HTTPException(404, "Customer session not found")
    row.review_status = payload.review_status
    if payload.note:
        row.limitations_json = list(row.limitations_json or []) + [
            f"Manager review note: {payload.note}"
        ]
    row.trust_classification = customer_trust_classification(row)
    db.commit()
    db.refresh(row)
    return row
