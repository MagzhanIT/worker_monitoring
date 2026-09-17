from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class CustomerServicePhase(Base):
    """Auditable interval inside one customer journey."""

    __tablename__ = "customer_service_phases"

    id: Mapped[str] = mapped_column(String(140), primary_key=True)
    customer_session_id: Mapped[str] = mapped_column(
        ForeignKey("customer_sessions.id"), index=True
    )
    phase: Mapped[str] = mapped_column(String(40), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)


class WorkerCustomerAssignment(Base):
    """One-to-one primary worker assignment with its evidence and review trail."""

    __tablename__ = "worker_customer_assignments"

    id: Mapped[str] = mapped_column(String(140), primary_key=True)
    customer_session_id: Mapped[str] = mapped_column(
        ForeignKey("customer_sessions.id"), index=True
    )
    worker_session_id: Mapped[str] = mapped_column(
        ForeignKey("worker_sessions.id"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    reasons_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkerSessionStitch(Base):
    """Audit record for a conservative camera-local short-gap re-link."""

    __tablename__ = "worker_session_stitches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id"), index=True)
    canonical_worker_session_id: Mapped[str] = mapped_column(
        ForeignKey("worker_sessions.id"), index=True
    )
    original_session_id: Mapped[str] = mapped_column(String(120))
    previous_track_id: Mapped[int] = mapped_column(Integer)
    new_track_id: Mapped[int] = mapped_column(Integer)
    gap_seconds: Mapped[float] = mapped_column(Float)
    appearance_distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    spatial_distance: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="automatic_conservative")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrackIdMigration(Base):
    """Immutable map from a legacy camera-local ID to its global numeric namespace."""

    __tablename__ = "track_id_migrations"
    __table_args__ = (
        UniqueConstraint(
            "camera_id", "legacy_track_id", name="uq_track_id_migration_camera_legacy"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Deliberately not a foreign key: historical camera rows may be removed while
    # this migration audit must remain immutable and queryable.
    camera_id: Mapped[int] = mapped_column(Integer, index=True)
    legacy_track_id: Mapped[int] = mapped_column(Integer)
    namespaced_track_id: Mapped[int] = mapped_column(Integer, index=True)
    migration_version: Mapped[str] = mapped_column(String(20), default="v6")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
