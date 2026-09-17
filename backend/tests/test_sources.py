from pathlib import Path, PureWindowsPath

import pytest

from services.source_parser import parse_source
from services.capture_service import CaptureService
from services import camera_manager as manager_module
from utilities.validation import validate_camera_source


def test_rtsp_validation_and_credentials_remain_in_capture_value():
    parsed = parse_source("rtsp://user:password@10.0.0.2/live")
    assert parsed.kind == "rtsp"
    assert parsed.capture_value.startswith("rtsp://")


def test_invalid_rtsp_has_useful_error():
    assert validate_camera_source("rtsp:///missing-host")


def test_posix_file_url():
    parsed = parse_source("file:///Users/example/video.mp4")
    assert parsed.kind == "file"
    assert parsed.capture_value == "/Users/example/video.mp4"


def test_windows_file_url():
    parsed = parse_source("file:///C:/Users/BORAS/Videos/test.mp4")
    assert PureWindowsPath(parsed.capture_value).drive == "C:"


def test_local_file_defaults_to_realtime_looping():
    parsed = parse_source("file:///C:/Videos/test.mp4")
    assert parsed.realtime is True
    assert parsed.loop is True


def test_local_file_playback_options_can_be_disabled():
    parsed = parse_source("file:///C:/Videos/test.mp4?loop=false&realtime=false")
    assert parsed.loop is False
    assert parsed.realtime is False


def test_recorded_fps_controls_local_playback_interval():
    assert CaptureService._playback_interval("file", True, 25.0) == pytest.approx(0.04)
    assert CaptureService._playback_interval("rtsp", True, 25.0) is None
    assert CaptureService._playback_interval("file", False, 25.0) is None


def test_webcam_source():
    assert parse_source("webcam://0").capture_value == 0
    with pytest.raises(ValueError):
        parse_source("webcam://front")


def test_demo_source_resolution():
    parsed = parse_source("demo://sample")
    assert Path(parsed.capture_value).name == "demo_source.mp4"
    assert parsed.loop is True


def test_duplicate_camera_start_protection_and_clean_stop(monkeypatch):
    class FakeHealth:
        def snapshot(self):
            return {"status": "HEALTHY"}

    class FakeRuntime:
        def __init__(self, camera_id, source):
            self.running = False
            self.health = FakeHealth()

        def start(self):
            self.running = True
            return True

        def stop(self):
            self.running = False

    monkeypatch.setattr(manager_module, "CameraRuntime", FakeRuntime)
    manager = manager_module.CameraManager()
    assert manager.start(1, "demo://sample")["started"]
    assert manager.start(1, "demo://sample")["reason"] == "already_running"
    assert manager.stop(1)["stopped"]
