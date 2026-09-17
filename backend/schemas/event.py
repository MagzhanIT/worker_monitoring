from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.evidence_service import normalize_unknown_reason


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    worker_session_id: str
    track_id: int
    camera_id: int
    camera_session_id: str
    presence: str
    activity: str
    start_time: datetime
    end_time: datetime | None
    duration_seconds: float | None
    confidence: float
    zone: str | None
    reasons_json: list
    limitations_json: list
    unknown_reason: str | None = None
    evidence_json: dict = Field(default_factory=dict)
    raw_track_ids_json: list = Field(default_factory=list)
    confirmation_seconds: float | None = None
    evidence_quality: str | None = None
    average_body_movement: float | None = None
    average_wrist_movement: float | None = None
    average_elbow_movement: float | None = None
    ending_reason: str | None = None
    transition_type: str | None = None
    end_transition_type: str | None = None
    review_status: str

    @field_validator("unknown_reason", mode="before")
    @classmethod
    def legacy_unknown_reason(cls, value, info):
        activity = info.data.get("activity")
        return normalize_unknown_reason(activity, value, legacy=True)
