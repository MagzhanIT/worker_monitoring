from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class WorkerSession(Base):
    __tablename__ = "worker_sessions"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id"), index=True)
    camera_session_id: Mapped[str] = mapped_column(ForeignKey("camera_sessions.id"), index=True)
    track_id: Mapped[int] = mapped_column(Integer, index=True)
    employee_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    display_name: Mapped[str] = mapped_column(String(50))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_seconds: Mapped[float] = mapped_column(Float, default=0)
    role_confidence: Mapped[float] = mapped_column(Float, default=0)
    limitations_json: Mapped[list] = mapped_column(JSON, default=list)

