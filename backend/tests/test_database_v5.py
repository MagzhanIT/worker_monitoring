from sqlalchemy import create_engine, text

import database


def test_v5_labels_blank_historical_unknown_without_reclassifying(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE activity_events ("
                "id VARCHAR PRIMARY KEY, activity VARCHAR, unknown_reason VARCHAR)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO activity_events VALUES "
                "('blank-null', 'UNKNOWN', NULL), "
                "('blank-text', 'UNKNOWN', ''), "
                "('old-label', 'UNKNOWN', 'Reason Not Recorded'), "
                "('specific', 'UNKNOWN', 'pose_missing'), "
                "('work', 'SHELF_WORK', NULL)"
            )
        )
    monkeypatch.setattr(database, "engine", engine)

    database._apply_additive_v5_upgrade()

    with engine.connect() as connection:
        rows = dict(
            connection.execute(
                text("SELECT id, unknown_reason FROM activity_events")
            ).all()
        )
        activities = dict(
            connection.execute(text("SELECT id, activity FROM activity_events")).all()
        )
    assert rows["blank-null"] == "legacy_record_missing_reason"
    assert rows["blank-text"] == "legacy_record_missing_reason"
    assert rows["old-label"] == "legacy_record_missing_reason"
    assert rows["specific"] == "pose_missing"
    assert rows["work"] is None
    assert activities["blank-null"] == "UNKNOWN"
