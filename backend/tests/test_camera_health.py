import time

from services.health_service import HealthMonitor


def test_advancing_static_video_is_not_frozen():
    monitor = HealthMonitor(frozen_seconds=0.01)
    monitor.connected()
    monitor.frame_received(1)
    time.sleep(0.02)
    monitor.frame_received(2)  # image content can be identical; sequence advancement matters
    assert monitor.snapshot()["status"] == "HEALTHY"


def test_stalled_sequence_becomes_frozen(monkeypatch):
    monitor = HealthMonitor(frozen_seconds=0)
    monitor.connected(); monitor.frame_received(1)
    assert monitor.snapshot()["status"] == "FROZEN"
    assert monitor.snapshot()["system_status"] == "CAMERA_UNAVAILABLE"


def test_reconnect_and_decode_counts():
    monitor = HealthMonitor()
    monitor.read_failed(); monitor.reconnecting()
    health = monitor.snapshot()
    assert health["decode_error_count"] == 1 and health["reconnect_count"] == 1

