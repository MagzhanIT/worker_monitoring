from __future__ import annotations

import logging
import platform
import threading
import time
from collections.abc import Callable

from config import settings
from logging_config import redact_source
from services.frame_buffer import LatestFrameBuffer
from services.health_service import HealthMonitor
from services.source_parser import ParsedSource, parse_source

logger = logging.getLogger(__name__)


class CaptureService:
    def __init__(self, source: str, on_frame: Callable | None = None) -> None:
        self.source = source
        self.parsed: ParsedSource = parse_source(source)
        self.frames = LatestFrameBuffer()
        self.health = HealthMonitor(settings.frozen_frame_seconds)
        self.on_frame = on_frame
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._capture = None

    @staticmethod
    def _playback_interval(kind: str, realtime: bool, fps: float) -> float | None:
        if kind not in {"file", "demo"} or not realtime or fps <= 0:
            return None
        return 1.0 / min(fps, 240.0)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> bool:
        if self.running:
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._reader, name="camera-capture", daemon=True)
        self._thread.start()
        return True

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        capture = self._capture
        if capture is not None:
            capture.release()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout)
        self.health.stopped()

    def restart(self) -> None:
        self.stop()
        self.start()

    def _open(self):
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("OpenCV is not installed") from exc
        backend = cv2.CAP_DSHOW if platform.system() == "Windows" and self.parsed.kind == "webcam" else cv2.CAP_ANY
        capture = cv2.VideoCapture(self.parsed.capture_value, backend)
        if not capture.isOpened():
            capture.release()
            raise RuntimeError("Camera source could not be opened")
        return capture

    def _reader(self) -> None:
        end_of_file = False
        while not self._stop.is_set():
            try:
                self._capture = self._open()
                self.health.connected()
                try:
                    import cv2
                    fps = float(self._capture.get(cv2.CAP_PROP_FPS))
                except Exception:
                    fps = 0.0
                interval = self._playback_interval(self.parsed.kind, self.parsed.realtime, fps)
                next_frame_at = time.monotonic()
                while not self._stop.is_set():
                    if interval is not None:
                        remaining = next_frame_at - time.monotonic()
                        if remaining > 0 and self._stop.wait(remaining):
                            break
                    ok, frame = self._capture.read()
                    if not ok:
                        if self.parsed.loop:
                            self._capture.set(1, 0)
                            next_frame_at = time.monotonic()
                            continue
                        if self.parsed.kind in {"file", "demo"}:
                            end_of_file = True
                            self.health.end_of_file()
                            break
                        self.health.read_failed()
                        break
                    packet = self.frames.put(frame)
                    self.health.frame_received(packet.sequence_id)
                    if self.on_frame:
                        self.on_frame(packet)
                    if interval is not None:
                        next_frame_at += interval
                        if next_frame_at < time.monotonic() - interval:
                            next_frame_at = time.monotonic()
            except Exception as exc:
                logger.warning("Capture unavailable for %s: %s", redact_source(self.source), type(exc).__name__)
                self.health.health.last_processing_error = str(exc)[:200]
            finally:
                if self._capture is not None:
                    self._capture.release()
                    self._capture = None
            if end_of_file:
                break
            if not self._stop.is_set():
                self.health.reconnecting()
                self._stop.wait(settings.camera_reconnect_seconds)
