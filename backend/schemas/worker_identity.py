from datetime import date, datetime

from pydantic import BaseModel, Field


class WorkerIdentityResponse(BaseModel):
    id: str
    display_name: str
    scope_date: date
    status: str
    created_at: datetime
    last_seen_at: datetime
    last_camera_id: int | None
    session_count: int = 0
    camera_ids: list[int] = Field(default_factory=list)
    limitations_json: list = Field(default_factory=list)


class IdentitySessionResponse(BaseModel):
    worker_session_id: str
    camera_id: int
    display_name: str
    first_seen: datetime
    last_seen: datetime
    match_method: str
    match_status: str
    confidence: float
    distance: float | None
    margin: float | None


class IdentityAssignmentRequest(BaseModel):
    note: str = Field(default="Manager confirmed this cross-camera association", max_length=500)
