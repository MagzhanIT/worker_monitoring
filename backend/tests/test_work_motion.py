from types import SimpleNamespace

from config import settings
from services.work_motion_service import TemporalWorkMotion


def _pose(wrist_x: float):
    points = [(50.0, 50.0, 0.9)] * 17
    points[5] = (40.0, 55.0, 0.9)
    points[6] = (60.0, 55.0, 0.9)
    points[9] = (wrist_x, 70.0, 0.9)
    points[10] = (70.0, 70.0, 0.9)
    points[11] = (45.0, 110.0, 0.9)
    points[12] = (55.0, 110.0, 0.9)
    return SimpleNamespace(global_keypoints=points, status="VALID")


def test_repeated_reaching_wrist_motion_becomes_other_work_evidence(monkeypatch):
    monkeypatch.setattr(settings, "work_motion_min_wrist_speed", 0.01)
    service = TemporalWorkMotion()
    box = (0, 0, 100, 160)
    signals = [
        service.update(1, _pose(5 + index * 4), box, float(index))
        for index in range(5)
    ]
    assert signals[-1].confirmed
    assert signals[-1].reaching


def test_body_translation_is_not_mislabeled_as_hand_work(monkeypatch):
    monkeypatch.setattr(settings, "work_motion_max_body_speed", 0.01)
    service = TemporalWorkMotion()
    first = _pose(20)
    service.update(1, first, (0, 0, 100, 160), 0.0)
    moved = _pose(30)
    moved.global_keypoints = [
        (x + 30, y + 30, confidence)
        for x, y, confidence in moved.global_keypoints
    ]
    result = service.update(1, moved, (30, 30, 130, 190), 1.0)
    assert not result.confirmed
