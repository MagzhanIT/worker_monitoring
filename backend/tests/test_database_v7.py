from sqlalchemy import create_engine, text

import database
from db_models.customer_service import TrackIdMigration


def test_v7_keeps_track_mapping_without_camera_foreign_key(tmp_path, monkeypatch):
    assert not TrackIdMigration.__table__.c.camera_id.foreign_keys
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))
        connection.execute(text("CREATE TABLE cameras (id INTEGER PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE track_id_migrations ("
                "id INTEGER PRIMARY KEY, camera_id INTEGER NOT NULL "
                "REFERENCES cameras(id), legacy_track_id INTEGER NOT NULL, "
                "namespaced_track_id INTEGER NOT NULL, migration_version VARCHAR, "
                "created_at DATETIME, UNIQUE(camera_id, legacy_track_id))"
            )
        )
        connection.execute(text("INSERT INTO cameras VALUES (4)"))
        connection.execute(
            text(
                "INSERT INTO track_id_migrations VALUES "
                "(1, 4, 7, 40000007, 'v6', CURRENT_TIMESTAMP)"
            )
        )
    monkeypatch.setattr(database, "engine", engine)

    database._apply_additive_v7_upgrade()
    database._apply_additive_v7_upgrade()

    with engine.begin() as connection:
        assert connection.execute(
            text("PRAGMA foreign_key_list('track_id_migrations')")
        ).all() == []
        assert connection.execute(
            text(
                "SELECT camera_id, legacy_track_id, namespaced_track_id "
                "FROM track_id_migrations"
            )
        ).one() == (4, 7, 40_000_007)
        connection.execute(text("DELETE FROM cameras WHERE id = 4"))
        assert connection.execute(
            text("SELECT count(*) FROM track_id_migrations")
        ).scalar_one() == 1
