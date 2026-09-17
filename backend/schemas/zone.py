from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ZoneType = Literal[
    "employee_area", "customer_area", "cashier", "register_interaction",
    "shelf_interaction", "service_position", "waiting", "entrance",
    "medicine_shelf", "storage", "computer", "pos",
    "authorized_out_of_zone", "break_area", "ignore_area",
]


class ZoneInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    zone_type: ZoneType
    normalized_points: list[tuple[float, float]]
    reference_width: int | None = Field(default=None, gt=0)
    reference_height: int | None = Field(default=None, gt=0)
    enabled: bool = True


class ZoneResponse(ZoneInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    camera_id: int
    camera_config_version: int
    created_at: datetime
    updated_at: datetime


class ZoneValidationResponse(BaseModel):
    valid: bool
    errors: list[str]
    area_ratio: float | None = None
