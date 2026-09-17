from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class EventReview(Base):
    __tablename__ = "event_reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("activity_events.id"), index=True)
    original_activity: Mapped[str] = mapped_column(String(40))
    original_confidence: Mapped[float] = mapped_column(Float)
    manager_status: Mapped[str] = mapped_column(String(30))
    manager_note: Mapped[str] = mapped_column(Text, default="")
    reviewer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

