from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReviewCreate(BaseModel):
    manager_status: Literal["confirmed", "false_alarm", "approved_activity", "unclear"]
    manager_note: str = Field(default="", max_length=2000)


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_id: str
    original_activity: str
    original_confidence: float
    manager_status: str
    manager_note: str
    reviewer_user_id: int
    reviewed_at: datetime

