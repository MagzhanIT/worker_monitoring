from __future__ import annotations

import threading

from services.capture_service import CaptureService
from services.processing_service import ProcessingService


class CameraRuntime:
    def __init__(self, camera_id: int, source: str) -> None:
        self.capture = CaptureService(source)
        self.processing = ProcessingService(camera_id, source, self.capture)

    @property
    def frames(self):
        return self.capture.frames

    @property
    def health(self):
        return self.capture.health

    @property
    def running(self) -> bool:
        return self.capture.running

    def start(self) -> bool:
        started = self.capture.start()
        self.processing.start()
        return started

    def stop(self) -> None:
        self.processing.stop()
        self.capture.stop()

    def live(self) -> dict:
        return self.processing.live()

    def frame(self, view: str = "normal"):
        return self.processing.frame(view)

    def set_debug_settings(self, value: dict) -> None:
        self.processing.set_debug_settings(value)

    def close_customer_session(self, session_id: str, outcome: str) -> None:
        self.processing.request_customer_close(session_id, outcome)


class CameraManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._services: dict[int, CameraRuntime] = {}

    def start(self, camera_id: int, source: str) -> dict:
        with self._lock:
            current = self._services.get(camera_id)
            if current and current.running:
                return {"started": False, "reason": "already_running", "status": current.health.snapshot()}
            service = CameraRuntime(camera_id, source)
            self._services[camera_id] = service
            service.start()
            return {"started": True, "status": service.health.snapshot()}

    def stop(self, camera_id: int) -> dict:
        with self._lock:
            service = self._services.get(camera_id)
        if not service:
            return {"stopped": False, "reason": "not_running"}
        service.stop()
        return {"stopped": True, "status": service.health.snapshot()}

    def restart(self, camera_id: int, source: str) -> dict:
        self.stop(camera_id)
        return self.start(camera_id, source)

    def get(self, camera_id: int) -> CameraRuntime | None:
        return self._services.get(camera_id)

    def status(self, camera_id: int) -> dict:
        service = self.get(camera_id)
        return service.health.snapshot() if service else HealthMonitor().snapshot()

    def live(self, camera_id: int) -> dict:
        service = self.get(camera_id)
        return service.live() if service else {
            "people_visible": 0,
            "workers_visible": 0,
            "customer_count": 0,
            "observed_people": [],
            "worker_states": [],
            "alerts": [],
        }

    def diagnostics(self, camera_id: int) -> dict:
        service = self.get(camera_id)
        return service.processing.activity_diagnostics() if service else {
            "camera_id": camera_id,
            "workers": [],
            "customers": [],
            "camera": {},
        }

    def set_debug_settings(self, camera_id: int, value: dict) -> None:
        service = self.get(camera_id)
        if service:
            service.set_debug_settings(value)

    def close_customer_session(
        self, camera_id: int, session_id: str, outcome: str
    ) -> bool:
        service = self.get(camera_id)
        if not service:
            return False
        service.close_customer_session(session_id, outcome)
        return True

    def stop_all(self) -> None:
        for camera_id in list(self._services):
            self.stop(camera_id)


from services.health_service import HealthMonitor

camera_manager = CameraManager()
