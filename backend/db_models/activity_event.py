from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    worker_session_id: Mapped[str] = mapped_column(ForeignKey("worker_sessions.id"), index=True)
    track_id: Mapped[int] = mapped_column(Integer, index=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id"), index=True)
    camera_session_id: Mapped[str] = mapped_column(ForeignKey("camera_sessions.id"), index=True)
    presence: Mapped[str] = mapped_column(String(30))
    activity: Mapped[str] = mapped_column(String(40), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    zone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reasons_json: Mapped[list] = mapped_column(JSON, default=list)
    limitations_json: Mapped[list] = mapped_column(JSON, default=list)
    unknown_reason: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_track_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    confirmation_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_quality: Mapped[str | None] = mapped_column(String(20), nullable=True)
    average_body_movement: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_wrist_movement: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_elbow_movement: Mapped[float | None] = mapped_column(Float, nullable=True)
    ending_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    transition_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    end_transition_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    clip_path: Mapped[str | None] = mapped_column(String(600), nullable=True)
    review_status: Mapped[str] = mapped_column(String(30), default="unreviewed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
