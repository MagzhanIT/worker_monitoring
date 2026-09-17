from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class WorkerIdentity(Base):
    """Day-scoped anonymous worker identity shared by multiple camera sessions."""

    __tablename__ = "worker_identities"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80), index=True)
    scope_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(30), default="provisional", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_camera_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limitations_json: Mapped[list] = mapped_column(JSON, default=list)


class WorkerIdentityLink(Base):
    """Auditable assignment of one camera-local session to a global worker ID."""

    __tablename__ = "worker_identity_links"

    worker_session_id: Mapped[str] = mapped_column(
        ForeignKey("worker_sessions.id"), primary_key=True
    )
    worker_identity_id: Mapped[str] = mapped_column(
        ForeignKey("worker_identities.id"), index=True
    )
    match_method: Mapped[str] = mapped_column(String(40))
    match_status: Mapped[str] = mapped_column(String(40), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes_json: Mapped[list] = mapped_column(JSON, default=list)


class WorkerAppearanceSignature(Base):
    """Encrypted clothing/body-appearance descriptor; never a face embedding."""

    __tablename__ = "worker_appearance_signatures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    worker_identity_id: Mapped[str] = mapped_column(
        ForeignKey("worker_identities.id"), index=True
    )
    source_session_id: Mapped[str] = mapped_column(
        ForeignKey("worker_sessions.id"), index=True
    )
    camera_id: Mapped[int] = mapped_column(Integer, index=True)
    descriptor_version: Mapped[str] = mapped_column(String(30), default="clothing-v1")
    descriptor_ciphertext: Mapped[str] = mapped_column(Text)
    quality: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
