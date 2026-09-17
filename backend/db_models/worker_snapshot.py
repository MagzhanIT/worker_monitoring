from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class WorkerSnapshot(Base):
    __tablename__ = "worker_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    worker_session_id: Mapped[str] = mapped_column(ForeignKey("worker_sessions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    file_path: Mapped[str] = mapped_column(String(600))
    quality: Mapped[float] = mapped_column(Float)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

