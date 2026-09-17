from datetime import date, datetime, time, UTC

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import require_manager
from database import get_db
from db_models.activity_event import ActivityEvent
from schemas.event import EventResponse

router = APIRouter(prefix="/events", tags=["events"], dependencies=[Depends(require_manager)])


@router.get("", response_model=list[EventResponse])
def list_events(activity: str | None = None, review_status: str | None = None, event_date: date | None = None, db: Session = Depends(get_db)):
    query = select(ActivityEvent).order_by(ActivityEvent.start_time.desc())
    if activity:
        query = query.where(ActivityEvent.activity == activity)
    if review_status:
        query = query.where(ActivityEvent.review_status == review_status)
    if event_date:
        start = datetime.combine(event_date, time.min, tzinfo=UTC)
        end = datetime.combine(event_date, time.max, tzinfo=UTC)
        query = query.where(ActivityEvent.start_time >= start, ActivityEvent.start_time <= end)
    return db.scalars(query).all()


@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: str, db: Session = Depends(get_db)):
    value = db.get(ActivityEvent, event_id)
    if not value:
        raise HTTPException(404, "Event not found")
    return value

