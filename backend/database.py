from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import DateTime, Integer, String, create_engine, func, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from config import BACKEND_DIR, settings


class Base(DeclarativeBase):
    pass


class SchemaVersion(Base):
    __tablename__ = "schema_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    applied_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


def _database_url() -> str:
    url = settings.database_url
    prefix = "sqlite:///./"
    if url.startswith(prefix):
        path = BACKEND_DIR / url.removeprefix(prefix)
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"
    return url


engine = create_engine(
    _database_url(),
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    with SessionLocal() as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


def init_db() -> None:
    import db_models  # noqa: F401

    Base.metadata.create_all(engine)
    _apply_additive_v3_upgrade()
    _apply_additive_v4_upgrade()
    _apply_additive_v5_upgrade()
    _apply_additive_v6_upgrade()
    _apply_additive_v7_upgrade()
    with session_scope() as db:
        if not db.scalar(select(SchemaVersion).where(SchemaVersion.version == "1")):
            db.add(SchemaVersion(version="1"))
        if not db.scalar(select(SchemaVersion).where(SchemaVersion.version == "2")):
            db.add(SchemaVersion(version="2"))
        if not db.scalar(select(SchemaVersion).where(SchemaVersion.version == "3")):
            db.add(SchemaVersion(version="3"))
        if not db.scalar(select(SchemaVersion).where(SchemaVersion.version == "4")):
            db.add(SchemaVersion(version="4"))
        if not db.scalar(select(SchemaVersion).where(SchemaVersion.version == "5")):
            db.add(SchemaVersion(version="5"))
        if not db.scalar(select(SchemaVersion).where(SchemaVersion.version == "6")):
            db.add(SchemaVersion(version="6"))
        if not db.scalar(select(SchemaVersion).where(SchemaVersion.version == "7")):
            db.add(SchemaVersion(version="7"))


def _apply_additive_v3_upgrade() -> None:
    """Add v3 columns to an existing database without rewriting or deleting rows."""
    required = {
        "customer_sessions": {
            "current_phase": "VARCHAR(40) NOT NULL DEFAULT 'WAITING'",
            "last_customer_seen_at": "DATETIME",
            "last_worker_seen_at": "DATETIME",
            "last_direct_interaction_at": "DATETIME",
            "medicine_retrieval_started_at": "DATETIME",
            "medicine_retrieval_ended_at": "DATETIME",
            "medicine_retrieval_seconds": "FLOAT NOT NULL DEFAULT 0",
            "direct_interaction_seconds": "FLOAT NOT NULL DEFAULT 0",
            "transaction_seconds": "FLOAT NOT NULL DEFAULT 0",
            "service_completed_at": "DATETIME",
            "outcome": "VARCHAR(40) NOT NULL DEFAULT 'ACTIVE'",
            "review_status": "VARCHAR(30) NOT NULL DEFAULT 'unreviewed'",
            "assignment_confidence": "FLOAT NOT NULL DEFAULT 0",
            "original_track_ids_json": "JSON NOT NULL DEFAULT '[]'",
            "limitations_json": "JSON NOT NULL DEFAULT '[]'",
        },
        "activity_events": {
            "unknown_reason": "VARCHAR(60)",
            "evidence_json": "JSON NOT NULL DEFAULT '{}'",
        },
    }
    with engine.begin() as connection:
        schema = inspect(connection)
        tables = set(schema.get_table_names())
        for table_name, columns in required.items():
            if table_name not in tables:
                continue
            existing = {column["name"] for column in schema.get_columns(table_name)}
            for column_name, declaration in columns.items():
                if column_name not in existing:
                    connection.execute(
                        text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {declaration}')
                    )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_customer_sessions_current_phase "
                "ON customer_sessions (current_phase)"
            )
        )


def _apply_additive_v4_upgrade() -> None:
    """Add auditable idle and customer-trust fields without rewriting old rows."""
    required = {
        "activity_events": {
            "raw_track_ids_json": "JSON NOT NULL DEFAULT '[]'",
            "confirmation_seconds": "FLOAT",
            "evidence_quality": "VARCHAR(20)",
            "average_body_movement": "FLOAT",
            "average_wrist_movement": "FLOAT",
            "average_elbow_movement": "FLOAT",
            "ending_reason": "VARCHAR(120)",
            "transition_type": "VARCHAR(50)",
            "end_transition_type": "VARCHAR(50)",
        },
        "customer_sessions": {
            "trust_classification": "VARCHAR(40)",
        },
    }
    with engine.begin() as connection:
        schema = inspect(connection)
        tables = set(schema.get_table_names())
        for table_name, columns in required.items():
            if table_name not in tables:
                continue
            existing = {column["name"] for column in schema.get_columns(table_name)}
            for column_name, declaration in columns.items():
                if column_name not in existing:
                    connection.execute(
                        text(
                            f'ALTER TABLE "{table_name}" ADD COLUMN '
                            f'"{column_name}" {declaration}'
                        )
                    )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_customer_sessions_trust_classification "
                "ON customer_sessions (trust_classification)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_customer_sessions_outcome "
                "ON customer_sessions (outcome)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_activity_events_unknown_reason "
                "ON activity_events (unknown_reason)"
            )
        )


def _apply_additive_v5_upgrade() -> None:
    """Label blank historical UNKNOWN reasons without reclassifying activity."""
    with engine.begin() as connection:
        schema = inspect(connection)
        if "activity_events" not in set(schema.get_table_names()):
            return
        columns = {column["name"] for column in schema.get_columns("activity_events")}
        if "unknown_reason" not in columns:
            return
        connection.execute(
            text(
                "UPDATE activity_events "
                "SET unknown_reason = 'legacy_record_missing_reason' "
                "WHERE activity = 'UNKNOWN' AND ("
                "unknown_reason IS NULL OR trim(unknown_reason) = '' OR "
                "lower(trim(unknown_reason)) = 'reason not recorded'"
                ")"
            )
        )


def _apply_additive_v6_upgrade() -> None:
    """Namespace legacy numeric track IDs by camera and retain an audit map."""
    namespace_size = 10_000_000
    scalar_columns = {
        "worker_sessions": ("track_id",),
        "activity_events": ("track_id",),
        "customer_sessions": ("customer_track_id",),
        "worker_session_stitches": ("previous_track_id", "new_track_id"),
    }
    json_columns = {
        "activity_events": ("id", "raw_track_ids_json"),
        "customer_sessions": ("id", "original_track_ids_json"),
    }
    with engine.begin() as connection:
        schema = inspect(connection)
        tables = set(schema.get_table_names())
        if "track_id_migrations" not in tables:
            return

        existing_mappings = {
            (int(camera_id), int(legacy_track_id))
            for camera_id, legacy_track_id in connection.execute(
                text("SELECT camera_id, legacy_track_id FROM track_id_migrations")
            )
        }
        discovered: set[tuple[int, int]] = set()
        for table_name, columns in scalar_columns.items():
            if table_name not in tables:
                continue
            available = {
                column["name"] for column in schema.get_columns(table_name)
            }
            if "camera_id" not in available:
                continue
            for column_name in columns:
                if column_name not in available:
                    continue
                rows = connection.execute(
                    text(
                        f'SELECT DISTINCT camera_id, "{column_name}" '
                        f'FROM "{table_name}" WHERE "{column_name}" >= 0 '
                        f'AND "{column_name}" < :namespace_size'
                    ),
                    {"namespace_size": namespace_size},
                )
                discovered.update((int(camera), int(track)) for camera, track in rows)

        # Some relinked IDs exist only inside the JSON audit arrays. Include them
        # in the immutable mapping before rewriting those arrays.
        for table_name, (id_column, json_column) in json_columns.items():
            if table_name not in tables:
                continue
            available = {
                column["name"] for column in schema.get_columns(table_name)
            }
            if not {"camera_id", id_column, json_column}.issubset(available):
                continue
            rows = connection.execute(
                text(
                    f'SELECT camera_id, "{json_column}" FROM "{table_name}" '
                    f'WHERE "{json_column}" IS NOT NULL'
                )
            ).all()
            for camera_id, serialized in rows:
                try:
                    values = (
                        serialized
                        if isinstance(serialized, list)
                        else json.loads(serialized)
                    )
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if isinstance(values, list):
                    discovered.update(
                        (int(camera_id), int(value))
                        for value in values
                        if isinstance(value, int) and 0 <= value < namespace_size
                    )

        for camera_id, legacy_track_id in sorted(discovered - existing_mappings):
            connection.execute(
                text(
                    "INSERT INTO track_id_migrations "
                    "(camera_id, legacy_track_id, namespaced_track_id, migration_version) "
                    "VALUES (:camera_id, :legacy_track_id, :namespaced_track_id, 'v6')"
                ),
                {
                    "camera_id": camera_id,
                    "legacy_track_id": legacy_track_id,
                    "namespaced_track_id": camera_id * namespace_size
                    + legacy_track_id,
                },
            )

        # Update scalar references consistently. Already-namespaced IDs are untouched,
        # which makes this migration safe to run at every startup.
        for table_name, columns in scalar_columns.items():
            if table_name not in tables:
                continue
            available = {
                column["name"] for column in schema.get_columns(table_name)
            }
            if "camera_id" not in available:
                continue
            for column_name in columns:
                if column_name not in available:
                    continue
                connection.execute(
                    text(
                        f'UPDATE "{table_name}" SET "{column_name}" = '
                        f'camera_id * :namespace_size + "{column_name}" '
                        f'WHERE "{column_name}" >= 0 AND "{column_name}" < :namespace_size'
                    ),
                    {"namespace_size": namespace_size},
                )

        # The arrays are report/audit fields, so migrate them as well instead of
        # leaving camera-local numbers visible beside the new scalar IDs.
        for table_name, (id_column, json_column) in json_columns.items():
            if table_name not in tables:
                continue
            available = {
                column["name"] for column in schema.get_columns(table_name)
            }
            if not {"camera_id", id_column, json_column}.issubset(available):
                continue
            rows = connection.execute(
                text(
                    f'SELECT "{id_column}", camera_id, "{json_column}" '
                    f'FROM "{table_name}" WHERE "{json_column}" IS NOT NULL'
                )
            ).all()
            for row_id, camera_id, serialized in rows:
                try:
                    values = (
                        serialized
                        if isinstance(serialized, list)
                        else json.loads(serialized)
                    )
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if not isinstance(values, list):
                    continue
                migrated = [
                    int(camera_id) * namespace_size + int(value)
                    if isinstance(value, int) and 0 <= value < namespace_size
                    else value
                    for value in values
                ]
                if migrated != values:
                    connection.execute(
                        text(
                            f'UPDATE "{table_name}" SET "{json_column}" = :value '
                            f'WHERE "{id_column}" = :row_id'
                        ),
                        {"value": json.dumps(migrated), "row_id": row_id},
                    )


def _apply_additive_v7_upgrade() -> None:
    """Keep the track migration audit after historical camera deletion."""
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if "track_id_migrations" not in tables:
            return
        foreign_keys = connection.execute(
            text("PRAGMA foreign_key_list('track_id_migrations')")
        ).all()
        if not foreign_keys:
            return
        connection.execute(
            text(
                "CREATE TABLE track_id_migrations_v7 ("
                "id INTEGER PRIMARY KEY, camera_id INTEGER NOT NULL, "
                "legacy_track_id INTEGER NOT NULL, namespaced_track_id INTEGER NOT NULL, "
                "migration_version VARCHAR(20) NOT NULL DEFAULT 'v6', "
                "created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
                "CONSTRAINT uq_track_id_migration_camera_legacy "
                "UNIQUE (camera_id, legacy_track_id))"
            )
        )
        connection.execute(
            text(
                "INSERT INTO track_id_migrations_v7 "
                "(id, camera_id, legacy_track_id, namespaced_track_id, "
                "migration_version, created_at) "
                "SELECT id, camera_id, legacy_track_id, namespaced_track_id, "
                "migration_version, created_at FROM track_id_migrations"
            )
        )
        connection.execute(text("DROP TABLE track_id_migrations"))
        connection.execute(
            text("ALTER TABLE track_id_migrations_v7 RENAME TO track_id_migrations")
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_track_id_migrations_camera_id "
                "ON track_id_migrations (camera_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_track_id_migrations_namespaced_track_id "
                "ON track_id_migrations (namespaced_track_id)"
            )
        )


def database_file() -> Path | None:
    url = _database_url()
    return Path(url.removeprefix("sqlite:///")) if url.startswith("sqlite:///") else None
