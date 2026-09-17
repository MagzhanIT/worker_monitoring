from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from utilities.time_utils import utc_now


@dataclass
class AnonymousWorkerSession:
    worker_session_id: str
    camera_session_id: str
    camera_id: int
    track_id: int
    employee_id: None
    display_name: str
    first_seen: datetime
    last_seen: datetime
    ended_at: datetime | None = None


class WorkerSessionService:
    def __init__(self) -> None:
        self.active: dict[int, AnonymousWorkerSession] = {}
        self._display_counter = 0

    def ensure(self, track_id: int, camera_id: int, camera_session_id: str, now: datetime | None = None) -> AnonymousWorkerSession:
        now = now or utc_now()
        current = self.active.get(track_id)
        if current:
            current.last_seen = now
            return current
        self._display_counter += 1
        run_tag = "".join(character for character in camera_session_id if character.isalnum())[-6:]
        identifier = f"WS-{now:%Y%m%d}-C{camera_id}-{run_tag}-{track_id:03d}"
        session = AnonymousWorkerSession(identifier, camera_session_id, camera_id, track_id, None, f"Worker {self._display_counter}", now, now)
        self.active[track_id] = session
        return session

    def close(self, track_id: int, now: datetime | None = None) -> AnonymousWorkerSession | None:
        session = self.active.pop(track_id, None)
        if session:
            session.ended_at = now or utc_now()
            session.last_seen = session.ended_at
        return session

    def rebind(
        self,
        track_id: int,
        session: AnonymousWorkerSession,
        now: datetime | None = None,
    ) -> AnonymousWorkerSession:
        """Continue a conservatively stitched camera-local session on a new track ID."""
        now = now or utc_now()
        self.active.pop(session.track_id, None)
        session.track_id = track_id
        session.last_seen = now
        session.ended_at = None
        self.active[track_id] = session
        return session

    def clear(self, now: datetime | None = None) -> list[AnonymousWorkerSession]:
        return [self.close(track_id, now) for track_id in list(self.active) if track_id in self.active]
