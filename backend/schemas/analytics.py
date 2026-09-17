from pydantic import BaseModel, Field


class DailyAnalytics(BaseModel):
    report_date: str
    camera_observed_seconds: float = 0
    confirmed_productive_seconds: float = 0
    serving_customer_seconds: float = 0
    fetching_medicine_seconds: float = 0
    cashier_work_seconds: float = 0
    computer_pos_seconds: float = 0
    shelf_work_seconds: float = 0
    other_work_seconds: float = 0
    confirmed_phone_seconds: float = 0
    possible_phone_seconds: float = 0
    possible_idle_seconds: float = 0
    unknown_activity_seconds: float = 0
    out_of_zone_seconds: float = 0
    absent_seconds: float = 0
    approved_break_seconds: float = 0
    camera_unavailable_seconds: float = 0
    report_quality: dict = Field(default_factory=dict)
