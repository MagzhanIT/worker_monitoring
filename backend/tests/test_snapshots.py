import sys
from types import SimpleNamespace

from services import snapshot_service as module


class Image:
    shape = (100, 80, 3)
    size = 24000


def test_worker_only_face_capture_and_customer_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "BACKEND_DIR", tmp_path)
    monkeypatch.setattr(module, "image_quality", lambda image: 0.9)
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(imwrite=lambda path, image: True))
    service = module.SnapshotService()
    assert service.consider(worker_session_id="WS-1", camera_id=1, image=Image(), kind="face", role="CUSTOMER") is None
    assert service.consider(worker_session_id="WS-1", camera_id=1, image=Image(), kind="face", role="WORKER", face_size=80)


def test_ambiguous_and_small_face_rejected(monkeypatch):
    service = module.SnapshotService()
    assert service.consider(worker_session_id="WS-1", camera_id=1, image=Image(), kind="face", role="WORKER", ambiguous=True) is None
    assert service.consider(worker_session_id="WS-1", camera_id=1, image=Image(), kind="face", role="WORKER", face_size=10) is None


def test_snapshot_write_failure_does_not_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "BACKEND_DIR", tmp_path)
    monkeypatch.setattr(module, "image_quality", lambda image: 0.9)
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(imwrite=lambda path, image: False))
    result = module.SnapshotService().consider(worker_session_id="WS-1", camera_id=1, image=Image(), kind="body", role="WORKER")
    assert result is None


def test_better_body_replaces_weaker_best(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "BACKEND_DIR", tmp_path)
    scores = iter([0.6, 0.9])
    monkeypatch.setattr(module, "image_quality", lambda image: next(scores))
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(imwrite=lambda path, image: True))
    service = module.SnapshotService()
    service.consider(worker_session_id="WS-1", camera_id=1, image=Image(), kind="body", role="WORKER")
    better = service.consider(worker_session_id="WS-1", camera_id=1, image=Image(), kind="body", role="WORKER")
    assert better.path.endswith("best_body.jpg")
    assert service.best["WS-1:body"][0].quality == 0.9
