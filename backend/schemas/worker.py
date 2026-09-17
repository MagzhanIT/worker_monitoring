from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WorkerSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    camera_id: int
    camera_session_id: str
    track_id: int
    employee_id: int | None
    display_name: str
    first_seen: datetime
    last_seen: datetime
    ended_at: datetime | None
    observed_seconds: float
    role_confidence: float
    limitations_json: list
    global_worker_id: str | None = None
    identity_match_status: str | None = None
    identity_confidence: float | None = None


class SnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    worker_session_id: str
    kind: str
    quality: float
    width: int
    height: int
    media_id: str
