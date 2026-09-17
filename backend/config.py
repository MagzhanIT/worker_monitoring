from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Pharmacy Worker Monitor V2"
    app_env: str = "development"
    app_reload: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_secret_key: str = "change-me"
    database_url: str = "sqlite:///./storage/worker_monitor.db"
    # NoDecode lets the before-validator accept the documented comma-separated
    # .env value instead of requiring a JSON array.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:8080"])
    default_admin_username: str = "admin"
    default_admin_password: str = ""
    access_token_minutes: int = 480

    person_model_path: str = "models/employee_customer.pt"
    lab_coat_verifier_enabled: bool = True
    lab_coat_verifier_model_path: str = "models/labcoat.pt"
    lab_coat_verifier_confidence: float = Field(default=0.20, ge=0, le=1)
    lab_coat_verifier_every_n_frames: int = Field(default=3, ge=1)
    lab_coat_min_person_overlap: float = Field(default=0.35, ge=0, le=1)
    phone_model_path: str = "models/phone_yolo.pt"
    pose_model_path: str = "models/yolo11n-pose.pt"
    worker_detection_mode: Literal["person", "lab_coat", "person_or_lab_coat"] = "person_or_lab_coat"
    person_confidence: float = 0.25
    lab_coat_confidence: float = 0.25
    person_min_box_area_ratio: float = Field(default=0.0004, ge=0, le=1)
    person_min_box_height_pixels: int = Field(default=24, ge=1)
    person_run_every_n_frames: int = Field(default=1, ge=1)
    track_iou_threshold: float = 0.25
    track_max_center_distance: float = 180.0
    track_max_missed_seconds: float = 5.0
    tracker_velocity_smoothing_alpha: float = Field(default=0.65, ge=0, le=1)
    tracker_max_prediction_seconds: float = Field(default=3.0, ge=0)
    track_min_confirmation_hits: int = Field(default=2, ge=1)
    role_confirmation_window: int = Field(default=7, ge=2)
    role_customer_minimum_votes: int = Field(default=4, ge=1)
    role_worker_promotion_hits: int = Field(default=2, ge=1)

    pose_enabled: bool = True
    pose_run_every_n_frames: int = 1
    pose_imgsz: int = 640
    pose_person_confidence: float = 0.15
    pose_keypoint_confidence: float = 0.20
    pose_max_stale_seconds: float = 2.50
    pose_hold_missing_updates: int = 3
    pose_confidence_decay: float = 0.85
    pose_smoothing_alpha: float = 0.65

    phone_enabled: bool = True
    phone_run_every_n_frames: int = 4
    phone_focused_run_every_n_frames: int = 1
    phone_focused_search_seconds: float = 2.5
    # The generic COCO phone model produces very low scores for tiny CCTV
    # phones. This is only a proposal threshold; strict pose/geometry gates in
    # phone_association.py decide whether a proposal can count as evidence.
    phone_object_confidence: float = 0.002
    phone_wrist_candidate_confidence: float = 0.002
    phone_person_candidate_confidence: float = 0.01
    phone_no_pose_fallback_confidence: float = 0.25
    phone_behavior_fallback_confidence: float = 0.60
    phone_max_wrist_distance: float = 0.22
    phone_max_face_distance: float = 0.30
    phone_behavior_max_hand_to_face_distance: float = 0.22
    phone_person_crop_imgsz: int = 640
    phone_wrist_crop_imgsz: int = 640
    phone_crop_expansion_x: float = 0.25
    phone_crop_expansion_y_top: float = 0.15
    phone_crop_expansion_y_bottom: float = 0.10
    phone_confirm_window: int = 5
    phone_min_confirm_hits: int = 2
    phone_release_misses: int = 3
    phone_memory_seconds: float = 2.5
    phone_pose_support_confidence: float = Field(default=0.35, ge=0, le=1)
    phone_temporal_window: int = Field(default=5, ge=2)
    phone_min_positive_checks: int = Field(default=2, ge=2)
    phone_confirm_seconds: float = Field(default=0.6, ge=0)
    phone_hold_seconds: float = Field(default=1.5, ge=0)
    phone_near_hand_distance_ratio: float = Field(default=0.22, gt=0, le=1)
    phone_near_head_distance_ratio: float = Field(default=0.30, gt=0, le=1)

    zone_confirm_window: int = 5
    zone_min_confirm_hits: int = 3
    zone_memory_seconds: float = 0.75
    zone_reload_seconds: float = Field(default=2.0, gt=0)
    zone_min_area_ratio: float = 0.002
    zone_max_area_ratio: float = 0.90
    state_switch_confirm_seconds: float = 1.5
    state_min_duration_seconds: float = 2.0
    possible_idle_threshold_seconds: float = 90.0
    idle_confirm_seconds: float = Field(default=15.0, gt=0)
    idle_exit_confirm_seconds: float = Field(default=1.5, ge=0)
    idle_min_track_age_seconds: float = Field(default=5.0, ge=0)
    idle_pose_grace_seconds: float = Field(default=3.0, ge=0)
    idle_track_gap_grace_seconds: float = Field(default=5.0, ge=0)
    idle_body_motion_threshold: float = Field(default=0.035, gt=0)
    idle_wrist_motion_threshold: float = Field(default=0.025, gt=0)
    idle_elbow_motion_threshold: float = Field(default=0.025, gt=0)
    idle_min_evidence_quality: Literal["HIGH", "MEDIUM"] = "MEDIUM"
    movement_smoothing_window: int = Field(default=5, ge=2)
    pose_smoothing_window: int = Field(default=5, ge=2)
    idle_min_event_seconds: float = Field(default=2.0, ge=0)
    idle_hold_seconds: float = Field(default=2.5, ge=0)
    absence_threshold_seconds: float = 60.0
    work_motion_enabled: bool = True
    work_motion_min_wrist_speed: float = Field(default=0.035, gt=0)
    work_motion_max_body_speed: float = Field(default=0.35, gt=0)
    work_motion_reach_ratio: float = Field(default=0.18, gt=0, le=1)
    work_motion_confirm_window: int = Field(default=5, ge=2)
    work_motion_min_confirm_hits: int = Field(default=3, ge=2)

    event_clip_enabled: bool = True
    event_clip_pre_seconds: float = 5.0
    event_clip_post_seconds: float = 5.0
    worker_snapshot_enabled: bool = True
    worker_snapshot_run_every_n_frames: int = 10
    worker_snapshot_min_interval_seconds: float = 1.0
    worker_snapshot_max_face_images: int = 3
    worker_snapshot_max_body_images: int = 2
    worker_snapshot_min_face_size: int = 40
    worker_snapshot_min_quality: float = 0.55

    customer_analytics_enabled: bool = True
    customer_wait_threshold_seconds: float = 180.0
    customer_service_min_seconds: float = 10.0
    service_start_confirm_seconds: float = Field(default=1.5, ge=0)
    service_lost_grace_seconds: float = Field(default=4.0, ge=0)
    medicine_retrieval_timeout_seconds: float = Field(default=180.0, gt=0)
    customer_lost_timeout_seconds: float = Field(default=8.0, gt=0)
    worker_return_timeout_seconds: float = Field(default=120.0, gt=0)
    service_end_confirm_seconds: float = Field(default=2.0, ge=0)
    service_max_seconds: float = Field(default=1800.0, gt=0)
    customer_short_gap_relink_seconds: float = Field(default=6.0, ge=0)
    customer_relink_max_center_distance: float = Field(default=140.0, gt=0)
    customer_trusted_assignment_confidence: float = Field(
        default=0.55, ge=0, le=1
    )
    local_session_stitch_enabled: bool = True
    local_session_stitch_max_gap_seconds: float = Field(default=12.0, gt=0)
    local_session_stitch_max_center_distance: float = Field(default=220.0, gt=0)
    local_session_stitch_appearance_threshold: float = Field(default=0.16, gt=0, le=1)
    local_session_stitch_min_margin: float = Field(default=0.035, ge=0, le=1)
    local_session_stitch_min_confidence: float = Field(default=0.72, ge=0, le=1)
    debug_default_show_pose: bool = True
    debug_default_show_zones: bool = True
    debug_default_show_phone_boxes: bool = True
    debug_default_show_assignments: bool = True
    debug_default_show_performance: bool = True
    frozen_frame_seconds: float = 5.0
    camera_reconnect_seconds: float = 3.0
    local_video_realtime: bool = True
    local_video_loop: bool = True
    worker_snapshot_retention_days: int = 30
    evidence_clip_retention_days: int = 30
    debug_image_retention_days: int = 7

    # Anonymous, worker-only, day-scoped cross-camera appearance association.
    # It intentionally uses clothing/body appearance rather than face recognition.
    global_worker_id_enabled: bool = True
    global_worker_id_min_observations: int = Field(default=3, ge=2)
    global_worker_id_observation_interval_seconds: float = Field(default=0.8, gt=0)
    global_worker_id_match_threshold: float = Field(default=0.20, gt=0, le=1)
    global_worker_id_min_margin: float = Field(default=0.04, ge=0, le=1)
    global_worker_id_min_crop_width: int = Field(default=28, ge=12)
    global_worker_id_min_crop_height: int = Field(default=72, ge=24)
    global_worker_id_min_quality: float = Field(default=0.30, ge=0, le=1)
    global_worker_id_max_signatures: int = Field(default=6, ge=1, le=30)
    global_worker_id_active_conflict_seconds: float = Field(default=5.0, ge=0)
    global_worker_id_signature_retention_days: int = Field(default=2, ge=1)

    google_sheets_enabled: bool = False
    google_sheets_credentials_file: str = ""
    google_sheets_spreadsheet_id: str = ""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def backend_path(self, value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else BACKEND_DIR / path

    @property
    def cors_origin_regex(self) -> str | None:
        """Allow browser dev servers to choose any loopback port locally."""
        if self.app_env != "development":
            return None
        return r"https?://(localhost|127[.]0[.]0[.]1)(:[0-9]+)?$"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
