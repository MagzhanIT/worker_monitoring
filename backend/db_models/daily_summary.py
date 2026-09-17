from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, JSON, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class DailySummary(Base):
    __tablename__ = "daily_summaries"
    __table_args__ = (UniqueConstraint("summary_date", "camera_id", name="uq_summary_date_camera"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    summary_date: Mapped[date] = mapped_column(Date, index=True)
    camera_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    camera_availability_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    observation_coverage_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

