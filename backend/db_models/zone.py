from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class CameraZone(Base):
    __tablename__ = "camera_zones"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    zone_type: Mapped[str] = mapped_column(String(40), index=True)
    normalized_points: Mapped[list] = mapped_column(JSON)
    reference_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    camera_config_version: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

