from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime

from utilities.time_utils import utc_now


@dataclass(frozen=True)
class FramePacket:
    frame: object
    capture_timestamp: float
    sequence_id: int
    received_at: datetime


class LatestFrameBuffer:
    """Exactly one newest frame slot. Old frames are overwritten, never queued."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._packet: FramePacket | None = None
        self._sequence = 0

    def put(self, frame: object, capture_timestamp: float | None = None) -> FramePacket:
        with self._lock:
            self._sequence += 1
            packet = FramePacket(frame, capture_timestamp or time.monotonic(), self._sequence, utc_now())
            self._packet = packet
            return packet

    def latest(self) -> FramePacket | None:
        with self._lock:
            return self._packet

    @property
    def sequence_id(self) -> int:
        with self._lock:
            return self._sequence


class RollingFrameBuffer:
    """Time-bounded compressed JPEG evidence buffer."""

    def __init__(self, seconds: float = 8.0, max_fps: float = 8.0) -> None:
        from collections import deque
        self.max_frames = max(1, int(seconds * max_fps))
        self._frames = deque(maxlen=self.max_frames)

    def add_jpeg(self, timestamp: float, jpeg: bytes) -> None:
        self._frames.append((timestamp, jpeg))

    def between(self, start: float, end: float) -> list[tuple[float, bytes]]:
        return [(timestamp, frame) for timestamp, frame in self._frames if start <= timestamp <= end]

