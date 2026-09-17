import json

from sqlalchemy import create_engine, text

import database


def test_v6_namespaces_legacy_track_ids_and_preserves_audit_map(
    tmp_path, monkeypatch
):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE worker_sessions "
                "(id VARCHAR PRIMARY KEY, camera_id INTEGER, track_id INTEGER)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE activity_events (id VARCHAR PRIMARY KEY, "
                "camera_id INTEGER, track_id INTEGER, raw_track_ids_json JSON)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE customer_sessions (id VARCHAR PRIMARY KEY, "
                "camera_id INTEGER, customer_track_id INTEGER, "
                "original_track_ids_json JSON)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE worker_session_stitches (id INTEGER PRIMARY KEY, "
                "camera_id INTEGER, previous_track_id INTEGER, new_track_id INTEGER)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE track_id_migrations (id INTEGER PRIMARY KEY, "
                "camera_id INTEGER, legacy_track_id INTEGER, "
                "namespaced_track_id INTEGER, migration_version VARCHAR)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO worker_sessions VALUES "
                "('W1', 1, 7), ('W2', 2, 7), ('W3', 2, 20000008)"
            )
        )
        connection.execute(
            text("INSERT INTO activity_events VALUES ('E1', 1, 7, '[7, 9]')")
        )
        connection.execute(
            text("INSERT INTO customer_sessions VALUES ('C1', 2, 7, '[7, 12]')")
        )
        connection.execute(
            text("INSERT INTO worker_session_stitches VALUES (1, 1, 7, 9)")
        )
    monkeypatch.setattr(database, "engine", engine)

    database._apply_additive_v6_upgrade()
    database._apply_additive_v6_upgrade()

    with engine.connect() as connection:
        worker_rows = connection.execute(
            text("SELECT id, track_id FROM worker_sessions ORDER BY id")
        ).all()
        event = connection.execute(
            text(
                "SELECT track_id, raw_track_ids_json FROM activity_events "
                "WHERE id = 'E1'"
            )
        ).one()
        customer = connection.execute(
            text(
                "SELECT customer_track_id, original_track_ids_json "
                "FROM customer_sessions WHERE id = 'C1'"
            )
        ).one()
        stitch = connection.execute(
            text(
                "SELECT previous_track_id, new_track_id "
                "FROM worker_session_stitches WHERE id = 1"
            )
        ).one()
        mappings = connection.execute(
            text(
                "SELECT camera_id, legacy_track_id, namespaced_track_id "
                "FROM track_id_migrations ORDER BY camera_id, legacy_track_id"
            )
        ).all()

    assert worker_rows == [
        ("W1", 10_000_007),
        ("W2", 20_000_007),
        ("W3", 20_000_008),
    ]
    assert event[0] == 10_000_007
    assert json.loads(event[1]) == [10_000_007, 10_000_009]
    assert customer[0] == 20_000_007
    assert json.loads(customer[1]) == [20_000_007, 20_000_012]
    assert stitch == (10_000_007, 10_000_009)
    assert (1, 7, 10_000_007) in mappings
    assert (1, 9, 10_000_009) in mappings
    assert (2, 7, 20_000_007) in mappings
    assert (2, 12, 20_000_012) in mappings
    assert len(mappings) == len(set(mappings))
