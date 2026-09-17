import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path

from db_models.activity_event import ActivityEvent
from db_models.camera import Camera
from db_models.camera_session import CameraSession
from db_models.customer_session import CustomerSession
from db_models.worker_session import WorkerSession
from db_models.worker_identity import WorkerIdentity, WorkerIdentityLink
from db_models.worker_snapshot import WorkerSnapshot
from services import report_service


def seed(db):
    now = datetime(2026, 7, 19, 9, 0, tzinfo=UTC)
    db.add(Camera(id=1, name="Counter", source="demo://sample"))
    db.add(CameraSession(id="CS-1", camera_id=1, source_type="demo"))
    db.add(WorkerSession(id="WS-1", camera_id=1, camera_session_id="CS-1", track_id=7, display_name="Worker 1", first_seen=now, last_seen=now + timedelta(minutes=1)))
    db.add(ActivityEvent(id="EV-1", worker_session_id="WS-1", track_id=7, camera_id=1, camera_session_id="CS-1", presence="VISIBLE", activity="ON_PHONE", start_time=now, end_time=now + timedelta(seconds=10), duration_seconds=10, confidence=0.9))
    db.add(ActivityEvent(id="EV-2", worker_session_id="WS-1", track_id=7, camera_id=1, camera_session_id="CS-1", presence="VISIBLE", activity="POSSIBLE_PHONE", start_time=now + timedelta(seconds=10), end_time=now + timedelta(seconds=20), duration_seconds=10, confidence=0.5))
    db.add(ActivityEvent(id="EV-3", worker_session_id="WS-1", track_id=7, camera_id=1, camera_session_id="CS-1", presence="VISIBLE", activity="SHELF_WORK", start_time=now + timedelta(seconds=20), end_time=now + timedelta(seconds=50), duration_seconds=30, confidence=0.8))
    db.add(ActivityEvent(id="EV-4", worker_session_id="WS-1", track_id=7, camera_id=1, camera_session_id="CS-1", presence="VISIBLE", activity="IDLE", start_time=now + timedelta(seconds=50), end_time=now + timedelta(seconds=60), duration_seconds=10, confidence=0.8, evidence_quality="MEDIUM", confirmation_seconds=15, ending_reason="confirmed work resumed", transition_type="IDLE_STARTED", end_transition_type="IDLE_ENDED"))
    db.add(WorkerSnapshot(worker_session_id="WS-1", kind="face", file_path=r"2026-07-19\camera_1\session_WS-1\face_1.jpg", quality=0.9, width=80, height=100))
    db.add(CustomerSession(id="CUSTOMER-PRIVATE", customer_track_id=99, worker_session_id="WS-1", camera_id=1, waiting_started_at=now, completed=True, confidence=0.9))
    db.commit()
    return now.date()


def test_local_csv_html_and_phone_separation(db, monkeypatch, tmp_path):
    day = seed(db)
    monkeypatch.setattr(report_service, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(report_service, "upload_aggregates", lambda rows: (False, "network unavailable"))
    (tmp_path / "latest_report_20260719_090000.csv").write_text("old")
    (tmp_path / "latest_events_20260719_090000.csv").write_text("old")
    (tmp_path / "latest_customer_report.csv").write_text("old customer export")
    (tmp_path / "latest_customer_report_20260719_090000.csv").write_text("old")
    (tmp_path / "latest_manager_report_20260719_090000.html").write_text("old")
    (tmp_path / ".gitkeep").write_text("")

    result = report_service.generate_reports(db, day)

    assert result["success"] and result["local_reports_created"]
    assert result["google_sheets_error"] == "network unavailable"
    assert (tmp_path / "latest_report.csv").is_file()
    assert (tmp_path / "latest_events.csv").is_file()
    assert (tmp_path / "latest_manager_report.html").is_file()
    assert (tmp_path / ".gitkeep").is_file()
    assert sorted(path.name for path in tmp_path.glob("latest_*")) == [
        "latest_customer_report.csv",
        "latest_events.csv",
        "latest_manager_report.html",
        "latest_report.csv",
    ]

    html = (tmp_path / "latest_manager_report.html").read_text(encoding="utf-8")
    assert "Worker Activity Report" in html
    assert "WS-1" in html and "00:01:00" in html
    assert "Captured face" in html and "face_1.jpg" in html
    assert "Shelf work" in html and "00:00:30" in html
    assert "Confirmed idle time" in html and "00:00:10" in html
    assert "idle timeline" in html and "confirmed work resumed" in html
    assert "No face recognition or embeddings" in html
    assert "Customer-service journeys" in html
    assert "CUSTOMER-PRIVATE" in html
    assert "Report quality" not in html
    assert html.index("Business summary") < html.index("Customer-service journeys")
    assert html.index("Customer-service journeys") < html.index("Worker overview")
    assert "Observed time not requiring review" in html

    csv_text = (tmp_path / "latest_report.csv").read_text(encoding="utf-8-sig")
    assert "confirmed_phone_seconds" in csv_text and "possible_phone_seconds" in csv_text
    assert "worker_session_id" in csv_text and "WS-1" in csv_text
    assert "confirmed_work_time" in csv_text and "00:00:30" in csv_text
    with (tmp_path / "latest_report.csv").open(encoding="utf-8-sig") as stream:
        worker_rows = list(csv.DictReader(stream))
    assert float(worker_rows[0]["confirmed_idle_seconds"]) == 10.0
    with (tmp_path / "latest_events.csv").open(encoding="utf-8-sig") as stream:
        event_rows = list(csv.DictReader(stream))
    idle_rows = [row for row in event_rows if row["activity"] == "IDLE"]
    assert len(idle_rows) == 1 and float(idle_rows[0]["duration_seconds"]) == 10.0
    assert "CUSTOMER-PRIVATE" not in csv_text
    assert "customer_csv" in result["files"]
    customer_csv = (tmp_path / "latest_customer_report.csv").read_text(
        encoding="utf-8-sig"
    )
    assert "CUSTOMER-PRIVATE" in customer_csv
    assert "medicine_retrieval_seconds" in customer_csv


def test_multicamera_report_groups_one_global_worker_without_overlap_double_count(db, monkeypatch, tmp_path):
    day = seed(db)
    start = datetime(2026, 7, 19, 9, 0, 30, tzinfo=UTC)
    db.add(Camera(id=2, name="Second camera", source="demo://second"))
    db.add(CameraSession(id="CS-2", camera_id=2, source_type="demo"))
    db.add(
        WorkerSession(
            id="WS-2",
            camera_id=2,
            camera_session_id="CS-2",
            track_id=9,
            display_name="Worker ABC123",
            first_seen=start,
            last_seen=start + timedelta(minutes=1),
        )
    )
    identity = WorkerIdentity(
        id="GW-20260719-ABC123",
        display_name="Worker ABC123",
        scope_date=day,
        status="provisional",
        last_seen_at=start + timedelta(minutes=1),
        last_camera_id=2,
    )
    db.add(identity)
    db.add_all(
        [
            WorkerIdentityLink(
                worker_session_id="WS-1",
                worker_identity_id=identity.id,
                match_method="conservative_new_identity",
                match_status="new_identity",
                confidence=0.5,
            ),
            WorkerIdentityLink(
                worker_session_id="WS-2",
                worker_identity_id=identity.id,
                match_method="encrypted_clothing_descriptor",
                match_status="appearance_matched",
                confidence=0.8,
                distance=0.08,
                margin=0.12,
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr(report_service, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(report_service, "upload_aggregates", lambda rows: (False, None))

    report_service.generate_reports(db, day)

    with (tmp_path / "latest_report.csv").open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]["global_worker_id"] == identity.id
    assert rows[0]["camera_ids"] == "1,2"
    assert rows[0]["session_count"] == "2"
    assert float(rows[0]["observed_seconds"]) == 90.0
    html = (tmp_path / "latest_manager_report.html").read_text(encoding="utf-8")
    assert "Observed time (camera overlap removed)" in html
    assert "Workers seen on multiple cameras</span><strong>1" in html
