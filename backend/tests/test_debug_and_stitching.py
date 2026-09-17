from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select

from api.cameras import get_debug_settings, update_debug_settings
from db_models.camera import Camera
from db_models.camera_session import CameraSession
from db_models.customer_service import WorkerSessionStitch
from db_models.worker_session import WorkerSession
from schemas.camera import CameraDebugSettings
from services.debug_overlay_service import DebugOverlayRenderer
from services.local_session_stitcher import LocalSessionStitcher
from services.processing_service import ProcessingService
from services.tracker import Detection
from services.worker_session_service import AnonymousWorkerSession


def anonymous(identifier: str, track_id: int):
    now = datetime(2026, 7, 25, tzinfo=UTC)
    return AnonymousWorkerSession(
        identifier, "CS-1", 1, track_id, None, "Worker", now, now
    )


def test_debug_renderer_draws_on_copy_and_keeps_clean_inference_frame():
    clean = np.zeros((240, 320, 3), dtype=np.uint8)
    before = clean.copy()
    rendered = DebugOverlayRenderer.render(
        clean,
        {
            "camera_id": 1,
            "frame_number": 7,
            "people": [
                {
                    "track_id": 1,
                    "bbox": (20, 30, 100, 200),
                    "role": "WORKER",
                    "activity": "UNKNOWN",
                    "confidence": 0.8,
                }
            ],
            "performance": {},
        },
        {"show_performance": True},
    )
    assert np.array_equal(clean, before)
    assert not np.array_equal(rendered, clean)


def test_test_mode_toggle_does_not_reset_tracker():
    service = ProcessingService(1, "demo://sample", object())
    tracks, _ = service.tracker.update([Detection((0, 0, 50, 100), 0.9)], 0)
    tracker_identity = id(service.tracker)
    service.set_debug_settings({"enabled": True})
    assert id(service.tracker) == tracker_identity
    assert tracks[0].track_id in service.tracker.tracks


def test_each_camera_processing_service_has_independent_state():
    first = ProcessingService(1, "demo://sample", object())
    second = ProcessingService(2, "demo://sample", object())
    assert first.tracker is not second.tracker
    assert first.state_machine is not second.state_machine
    assert first.customers is not second.customers
    first_tracks, _ = first.tracker.update([Detection((0, 0, 50, 100), 0.9)], 0)
    second_tracks, _ = second.tracker.update([Detection((0, 0, 50, 100), 0.9)], 0)
    assert first.tracker.tracks and second.tracker.tracks
    assert first_tracks[0].track_id != second_tracks[0].track_id
    assert first_tracks[0].track_id // 10_000_000 == 1
    assert second_tracks[0].track_id // 10_000_000 == 2


def test_normal_auto_and_test_views_keep_separate_frame_buffers():
    service = ProcessingService(1, "demo://sample", object())
    clean = np.zeros((40, 60, 3), dtype=np.uint8)
    debug = np.full((40, 60, 3), 255, dtype=np.uint8)
    service._normal_frame = clean.copy()
    service._debug_frame = debug.copy()

    service.set_debug_settings({"enabled": False})
    assert np.array_equal(service.frame("normal"), clean)
    assert np.array_equal(service.frame("auto"), clean)
    service.set_debug_settings({"enabled": True})
    assert np.array_equal(service.frame("test"), debug)
    assert np.array_equal(service.frame("auto"), debug)
    assert np.array_equal(service.frame("normal"), clean)


def test_temporal_candidate_explains_current_unknown_state():
    assert (
        ProcessingService._current_unknown_reason(
            "UNKNOWN", "SERVING_CUSTOMER", None
        )
        == "insufficient_temporal_evidence"
    )
    assert (
        ProcessingService._current_unknown_reason(
            "UNKNOWN", "UNKNOWN", "pose_missing"
        )
        == "pose_missing"
    )
    assert (
        ProcessingService._current_unknown_reason(
            "SERVING_CUSTOMER", "UNKNOWN", "pose_missing"
        )
        is None
    )


def test_missing_camera_zones_are_reported_before_missing_pose():
    assert (
        ProcessingService._unknown_reason(
            "UNKNOWN", True, None, set(), 0.9, []
        )
        == "camera_zones_not_configured"
    )


def test_debug_configuration_is_persisted_per_camera(db):
    db.add(Camera(id=1, name="Counter", source="demo://sample"))
    db.commit()
    response = update_debug_settings(
        1,
        CameraDebugSettings(enabled=True, show_pose=False),
        db,
    )
    assert response.enabled and not response.show_pose and response.tracking_preserved
    assert get_debug_settings(1, db).enabled


def test_short_gap_session_relinks_only_with_strong_unambiguous_evidence(monkeypatch):
    monkeypatch.setattr(
        "services.local_session_stitcher.settings.local_session_stitch_min_confidence", 0.5
    )
    stitcher = LocalSessionStitcher()
    crop = np.full((120, 60, 3), (20, 80, 180), dtype=np.uint8)
    session = anonymous("WS-1", 1)
    stitcher.observe(1, session, (0, 0, 60, 120), crop, 0)
    stitcher.expire(1)
    match = stitcher.match((5, 0, 65, 120), crop.copy(), 1)
    assert match is not None and match.session.worker_session_id == "WS-1"

    ambiguous = LocalSessionStitcher()
    ambiguous.observe(1, anonymous("WS-A", 1), (0, 0, 60, 120), crop, 0)
    ambiguous.observe(2, anonymous("WS-B", 2), (2, 0, 62, 120), crop, 0)
    ambiguous.expire(1)
    ambiguous.expire(2)
    assert ambiguous.match((4, 0, 64, 120), crop.copy(), 1) is None


def test_accepted_session_stitch_keeps_persistent_audit_history(db, monkeypatch):
    monkeypatch.setattr(
        "services.local_session_stitcher.settings.local_session_stitch_min_confidence", 0.5
    )
    now = datetime(2026, 8, 3, tzinfo=UTC)
    db.add(Camera(id=1, name="Counter", source="demo://sample"))
    db.add(CameraSession(id="CS-1", camera_id=1, source_type="demo"))
    db.add(
        WorkerSession(
            id="WS-1",
            camera_id=1,
            camera_session_id="CS-1",
            track_id=10_000_001,
            display_name="Worker 1",
            first_seen=now,
            last_seen=now,
        )
    )
    db.commit()
    crop = np.full((120, 60, 3), (20, 80, 180), dtype=np.uint8)
    stitcher = LocalSessionStitcher()
    stitcher.observe(
        10_000_001,
        anonymous("WS-1", 10_000_001),
        (0, 0, 60, 120),
        crop,
        0,
    )
    stitcher.expire(10_000_001)
    match = stitcher.match((5, 0, 65, 120), crop.copy(), 1)
    assert match is not None
    service = ProcessingService(1, "demo://sample", object())
    db.add(service._session_stitch_audit("WS-1", 10_000_002, match, now))
    db.commit()

    rows = db.scalars(select(WorkerSessionStitch)).all()
    assert len(rows) == 1
    assert rows[0].canonical_worker_session_id == "WS-1"
    assert rows[0].previous_track_id == 10_000_001
    assert rows[0].new_track_id == 10_000_002
    assert rows[0].reason == "short_gap_spatial_appearance_match"
    assert rows[0].confidence == match.confidence
