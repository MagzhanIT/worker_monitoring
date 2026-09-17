from services.pose_service import PoseService, pose_inference_due


def test_exact_inference_box_mapping_and_global_storage():
    service = PoseService()
    value = service.store(7, 12, (100, 200, 300, 500), [(10, 20, 0.9)], 1.0)
    assert value.frame_sequence == 12
    assert value.crop_box == (100, 200, 300, 500)
    assert value.global_keypoints[0][:2] == (110, 220)


def test_skipped_and_one_missing_frame_retain_fresh_pose(monkeypatch):
    service = PoseService()
    service.store(7, 1, (0, 0, 100, 100), [(10, 20, 0.9)], 1.0)
    value = service.missing(7, 1.1)
    assert value.status == "TEMPORARILY_MISSING"
    assert service.fresh(7, 1.2) is value


def test_stale_pose_expires_and_track_clear():
    service = PoseService()
    service.store(7, 1, (0, 0, 100, 100), [(10, 20, 0.9)], 1.0)
    assert service.missing(7, 10).status == "STALE"
    service.clear(7)
    assert 7 not in service.history


def test_implausible_bone_is_rejected():
    service = PoseService()
    points = [(10.0, 10.0, 0.9)] * 17
    points[5] = (5.0, 5.0, 0.9)
    points[7] = (500.0, 500.0, 0.9)
    value = service.store(7, 1, (0, 0, 100, 100), points, 1.0)
    assert value.global_keypoints[7][2] == 0


def test_pose_schedule_refreshes_missing_evidence_even_between_cadence_frames():
    assert pose_inference_due(8, 3, None)


def test_pose_schedule_reuses_fresh_evidence_between_cadence_frames():
    service = PoseService()
    cached = service.store(7, 1, (0, 0, 100, 100), [(10, 20, 0.9)], 1.0)
    assert not pose_inference_due(8, 3, cached)
    assert pose_inference_due(9, 3, cached)
