from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class CameraSession(Base):
    __tablename__ = "camera_sessions"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    average_processing_fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    reconnect_count: Mapped[int] = mapped_column(Integer, default=0)
    unavailable_seconds: Mapped[float] = mapped_column(Float, default=0)
    manifest_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)

