from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CustomerSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_track_id: int
    worker_session_id: str | None
    camera_id: int
    waiting_started_at: datetime
    service_started_at: datetime | None
    service_ended_at: datetime | None
    waiting_seconds: float | None
    service_seconds: float | None
    current_phase: str
    medicine_retrieval_seconds: float
    direct_interaction_seconds: float
    transaction_seconds: float
    outcome: str
    review_status: str
    assignment_confidence: float
    trust_classification: str | None = None
    original_track_ids_json: list = Field(default_factory=list)


class CustomerSessionCloseRequest(BaseModel):
    outcome: Literal["COMPLETED", "ABANDONED", "INTERRUPTED"] = "INTERRUPTED"


class CustomerSessionReviewRequest(BaseModel):
    review_status: Literal["confirmed", "corrected", "needs_review", "false_alarm"]
    note: str = Field(default="", max_length=500)
