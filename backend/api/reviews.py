from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.auth import require_manager
from database import get_db
from db_models.activity_event import ActivityEvent
from db_models.event_review import EventReview
from db_models.user import User
from schemas.review import ReviewCreate, ReviewResponse

router = APIRouter(tags=["manager review"])


@router.post("/events/{event_id}/review", response_model=ReviewResponse)
def review_event(
    event_id: str,
    payload: ReviewCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    event = db.get(ActivityEvent, event_id)
    if not event:
        raise HTTPException(404, "Event not found")
    review = EventReview(
        event_id=event.id,
        original_activity=event.activity,
        original_confidence=event.confidence,
        manager_status=payload.manager_status,
        manager_note=payload.manager_note,
        reviewer_user_id=user.id,
    )
    event.review_status = payload.manager_status
    db.add(review)
    db.commit()
    db.refresh(review)
    return review

