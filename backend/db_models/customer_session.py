from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class CustomerSession(Base):
    __tablename__ = "customer_sessions"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    customer_track_id: Mapped[int] = mapped_column(Integer, index=True)
    worker_session_id: Mapped[str | None] = mapped_column(ForeignKey("worker_sessions.id"), nullable=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id"), index=True)
    waiting_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    service_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    service_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    waiting_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    service_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    left_without_service: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    current_phase: Mapped[str] = mapped_column(String(40), default="WAITING", index=True)
    last_customer_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_worker_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_direct_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    medicine_retrieval_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    medicine_retrieval_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    medicine_retrieval_seconds: Mapped[float] = mapped_column(Float, default=0)
    direct_interaction_seconds: Mapped[float] = mapped_column(Float, default=0)
    transaction_seconds: Mapped[float] = mapped_column(Float, default=0)
    service_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str] = mapped_column(String(40), default="ACTIVE", index=True)
    review_status: Mapped[str] = mapped_column(String(30), default="unreviewed", index=True)
    assignment_confidence: Mapped[float] = mapped_column(Float, default=0)
    trust_classification: Mapped[str | None] = mapped_column(
        String(40), nullable=True, index=True
    )
    original_track_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    limitations_json: Mapped[list] = mapped_column(JSON, default=list)
