from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict, dataclass


@dataclass
class CameraHealth:
    status: str = "UNAVAILABLE"
    camera_connected: bool = False
    receiving_frames: bool = False
    stream_frozen: bool = False
    last_frame_age_seconds: float | None = None
    capture_sequence: int = 0
    capture_fps: float = 0.0
    processing_fps: float = 0.0
    reconnect_count: int = 0
    decode_error_count: int = 0
    person_model_loaded: bool = False
    pose_model_loaded: bool = False
    phone_model_loaded: bool = False
    last_processing_error: str | None = None
    system_status: str = "CAMERA_UNAVAILABLE"

    def public(self) -> dict:
        return asdict(self)


class HealthMonitor:
    def __init__(self, frozen_seconds: float = 5.0) -> None:
        self.health = CameraHealth()
        self.frozen_seconds = frozen_seconds
        self._frame_times: deque[float] = deque(maxlen=60)
        self._last_frame_monotonic: float | None = None
        self._last_sequence_change: float | None = None

    def connected(self) -> None:
        self.health.camera_connected = True
        self.health.status = "DEGRADED"

    def frame_received(self, sequence_id: int) -> None:
        now = time.monotonic()
        if sequence_id > self.health.capture_sequence:
            self._last_sequence_change = now
        self.health.capture_sequence = sequence_id
        self._last_frame_monotonic = now
        self._frame_times.append(now)
        self.health.receiving_frames = True
        self.health.stream_frozen = False
        self.health.status = "HEALTHY"
        self.health.system_status = "RUNNING"
        if len(self._frame_times) > 1:
            span = self._frame_times[-1] - self._frame_times[0]
            self.health.capture_fps = (len(self._frame_times) - 1) / span if span else 0.0

    def read_failed(self) -> None:
        self.health.decode_error_count += 1
        self.health.receiving_frames = False
        self.health.status = "RECONNECTING"
        self.health.system_status = "CAMERA_UNAVAILABLE"

    def end_of_file(self) -> None:
        self.health.camera_connected = False
        self.health.receiving_frames = False
        self.health.status = "END_OF_FILE"
        self.health.system_status = "STOPPED"

    def reconnecting(self) -> None:
        self.health.reconnect_count += 1
        self.health.camera_connected = False
        self.health.status = "RECONNECTING"
        self.health.system_status = "CAMERA_UNAVAILABLE"

    def stopped(self) -> None:
        self.health.camera_connected = False
        self.health.receiving_frames = False
        self.health.status = "UNAVAILABLE"
        self.health.system_status = "CAMERA_UNAVAILABLE"

    def snapshot(self) -> dict:
        now = time.monotonic()
        if self._last_frame_monotonic is not None:
            self.health.last_frame_age_seconds = round(now - self._last_frame_monotonic, 3)
        if self.health.camera_connected and self._last_sequence_change is not None:
            stalled = now - self._last_sequence_change >= self.frozen_seconds
            if stalled:
                self.health.stream_frozen = True
                self.health.receiving_frames = False
                self.health.status = "FROZEN"
                self.health.system_status = "CAMERA_UNAVAILABLE"
        return self.health.public()
