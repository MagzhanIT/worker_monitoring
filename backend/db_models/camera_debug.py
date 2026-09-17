from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class CameraDebugSetting(Base):
    __tablename__ = "camera_debug_settings"

    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    show_pose: Mapped[bool] = mapped_column(Boolean, default=True)
    show_zones: Mapped[bool] = mapped_column(Boolean, default=True)
    show_phone_boxes: Mapped[bool] = mapped_column(Boolean, default=True)
    show_assignments: Mapped[bool] = mapped_column(Boolean, default=True)
    show_performance: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

