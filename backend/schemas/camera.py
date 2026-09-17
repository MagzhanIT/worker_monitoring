from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CameraBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source: str
    enabled: bool = True
    reference_width: int | None = Field(default=None, gt=0)
    reference_height: int | None = Field(default=None, gt=0)
    rotation: int = 0
    mirror: bool = False


class CameraCreate(CameraBase):
    pass


class CameraUpdate(CameraBase):
    pass


class CameraResponse(CameraBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    config_version: int
    created_at: datetime
    updated_at: datetime


class CameraDebugSettings(BaseModel):
    enabled: bool = False
    show_pose: bool = True
    show_zones: bool = True
    show_phone_boxes: bool = True
    show_assignments: bool = True
    show_performance: bool = True


class CameraDebugResponse(CameraDebugSettings):
    camera_id: int
    tracking_preserved: bool = True
