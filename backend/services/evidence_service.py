from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from config import settings


class EvidenceQuality(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class UnknownReason(StrEnum):
    INITIAL_TEMPORAL_WARMUP = "initial_temporal_warmup"
    INSUFFICIENT_TEMPORAL_EVIDENCE = "insufficient_temporal_evidence"
    UNSTABLE_TRACK = "unstable_track"
    SHORT_TRACK = "short_track"
    TRACK_GAP = "track_gap"
    POSE_MISSING = "pose_missing"
    POSE_TEMPORARILY_MISSING = "pose_temporarily_missing"
    POSE_LOW_CONFIDENCE = "pose_low_confidence"
    WORKER_PARTIALLY_OCCLUDED = "worker_partially_occluded"
    LOW_IMAGE_QUALITY = "low_image_quality"
    PERSON_CROP_TOO_SMALL = "person_crop_too_small"
    OUTSIDE_CONFIGURED_ZONES = "outside_configured_zones"
    CAMERA_ZONES_NOT_CONFIGURED = "camera_zones_not_configured"
    CONFLICTING_ACTIVITY_SIGNALS = "conflicting_activity_signals"
    NO_RELIABLE_MOTION_SIGNAL = "no_reliable_motion_signal"
    CUSTOMER_ASSIGNMENT_UNCERTAIN = "customer_assignment_uncertain"
    SERVICE_SESSION_UNCERTAIN = "service_session_uncertain"
    PHONE_EVIDENCE_UNCERTAIN = "phone_evidence_uncertain"
    DETECTOR_MISSING = "detector_missing"
    LEGACY_RECORD_MISSING_REASON = "legacy_record_missing_reason"
    INTERNAL_STATE_INCONSISTENCY = "internal_state_inconsistency"


UNKNOWN_REASON_VALUES = frozenset(item.value for item in UnknownReason)


def normalize_unknown_reason(
    activity: str,
    reason: str | UnknownReason | None,
    *,
    legacy: bool = False,
) -> str | None:
    """Guarantee a controlled reason for UNKNOWN without rewriting legacy evidence."""
    if activity != "UNKNOWN":
        return None
    value = str(reason or "").strip()
    if value in UNKNOWN_REASON_VALUES:
        return value
    if not value:
        return (
            UnknownReason.LEGACY_RECORD_MISSING_REASON.value
            if legacy
            else UnknownReason.INSUFFICIENT_TEMPORAL_EVIDENCE.value
        )
    return UnknownReason.INTERNAL_STATE_INCONSISTENCY.value


@dataclass(frozen=True)
class EvidenceAssessment:
    quality: EvidenceQuality
    unknown_reason: str | None
    idle_blocking_reasons: list[str]


def assess_evidence_quality(
    *,
    track_confirmed: bool,
    track_age_seconds: float,
    confidence: float,
    crop_width: int,
    crop_height: int,
    zones_configured: bool,
    confirmed_zones: set[str],
    pose_status: str,
    pose_confident_points: int,
    bbox_motion_reliable: bool,
    minimum_track_age_seconds: float,
) -> EvidenceAssessment:
    if not track_confirmed:
        return EvidenceAssessment(
            EvidenceQuality.LOW,
            UnknownReason.UNSTABLE_TRACK.value,
            ["track is not temporally stable"],
        )
    if track_age_seconds < minimum_track_age_seconds:
        return EvidenceAssessment(
            EvidenceQuality.LOW,
            UnknownReason.SHORT_TRACK.value,
            [
                f"track age {track_age_seconds:.1f}s is below "
                f"{minimum_track_age_seconds:.1f}s"
            ],
        )
    if confidence < 0.35:
        return EvidenceAssessment(
            EvidenceQuality.LOW,
            UnknownReason.LOW_IMAGE_QUALITY.value,
            ["person detection confidence is too low"],
        )
    if crop_width < 20 or crop_height < 48:
        return EvidenceAssessment(
            EvidenceQuality.LOW,
            UnknownReason.PERSON_CROP_TOO_SMALL.value,
            ["person crop is too small for reliable activity evidence"],
        )
    if not zones_configured:
        return EvidenceAssessment(
            EvidenceQuality.LOW,
            UnknownReason.CAMERA_ZONES_NOT_CONFIGURED.value,
            ["camera activity zones are not configured"],
        )
    if not confirmed_zones:
        return EvidenceAssessment(
            EvidenceQuality.LOW,
            UnknownReason.OUTSIDE_CONFIGURED_ZONES.value,
            ["worker is outside confirmed activity zones"],
        )
    if not bbox_motion_reliable:
        return EvidenceAssessment(
            EvidenceQuality.LOW,
            UnknownReason.NO_RELIABLE_MOTION_SIGNAL.value,
            ["bbox movement history is still warming up"],
        )
    if pose_status == "VALID" and pose_confident_points >= 5:
        return EvidenceAssessment(EvidenceQuality.HIGH, None, [])
    if pose_status == "TEMPORARILY_MISSING":
        return EvidenceAssessment(
            EvidenceQuality.MEDIUM,
            UnknownReason.POSE_TEMPORARILY_MISSING.value,
            [],
        )
    if pose_status == "VALID" and pose_confident_points < 5:
        return EvidenceAssessment(
            EvidenceQuality.MEDIUM,
            UnknownReason.POSE_LOW_CONFIDENCE.value,
            [],
        )
    return EvidenceAssessment(
        EvidenceQuality.MEDIUM,
        UnknownReason.POSE_MISSING.value,
        [],
    )


@dataclass
class ActivityEvidence:
    camera_healthy: bool
    presence: str = "VISIBLE"
    physical_phone_confirmed: bool = False
    physical_phone_hit: bool = False
    phone_like_pose: bool = False
    phone_call_behavior: bool = False
    serving_customer: bool = False
    fetching_medicine: bool = False
    cashier: bool = False
    computer_pos: bool = False
    shelf: bool = False
    other_work: bool = False
    approved_break: bool = False
    low_movement_seconds: float = 0
    low_motion_confirmed: bool = False
    evidence_quality: str = EvidenceQuality.LOW.value
    track_age_seconds: float = 0.0
    track_stable: bool = False
    body_motion: float = 0.0
    bbox_motion: float = 0.0
    wrist_motion: float = 0.0
    elbow_motion: float = 0.0
    pose_status: str = "MISSING"
    pose_confidence: float = 0.0
    idle_blocking_reasons: list[str] = field(default_factory=list)
    unknown_reason: str | None = None
    reasons: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    confidence: float = 0.0
    zone: str | None = None


WORK_ACTIVITIES = {
    "SHELF_WORK",
    "CASHIER_WORK",
    "SERVING_CUSTOMER",
    "FETCHING_MEDICINE",
    "COMPUTER_POS_WORK",
    "OTHER_WORK",
}

def evidence_status(role: str, activity: str) -> str:
    """Return a manager-facing observation label, never an employment judgment."""
    if role == "CUSTOMER":
        return "CUSTOMER_OBSERVED"
    if role != "WORKER":
        return "INSUFFICIENT_EVIDENCE"
    if activity in WORK_ACTIVITIES:
        return "WORK_OBSERVED"
    if activity == "APPROVED_BREAK":
        return "APPROVED_BREAK"
    if activity == "IDLE":
        return "CONFIRMED_IDLE"
    if activity in {"ON_PHONE", "POSSIBLE_PHONE", "POSSIBLE_IDLE"}:
        return "REVIEW_NEEDED"
    return "INSUFFICIENT_EVIDENCE"


def official_activity(evidence: ActivityEvidence, idle_threshold: float) -> str:
    if not evidence.camera_healthy or evidence.presence == "UNKNOWN":
        return "UNKNOWN"
    # Active pharmacy service/work wins over device evidence so medicine
    # retrieval never resets service classification.
    if evidence.fetching_medicine:
        return "FETCHING_MEDICINE"
    if evidence.serving_customer:
        return "SERVING_CUSTOMER"
    if evidence.evidence_quality == EvidenceQuality.LOW.value:
        return "UNKNOWN"
    if evidence.computer_pos:
        return "COMPUTER_POS_WORK"
    if evidence.cashier:
        return "CASHIER_WORK"
    if evidence.shelf:
        return "SHELF_WORK"
    if evidence.other_work:
        return "OTHER_WORK"
    if evidence.physical_phone_confirmed:
        return "ON_PHONE"
    if evidence.approved_break:
        return "APPROVED_BREAK"
    if evidence.phone_like_pose or evidence.phone_call_behavior or evidence.physical_phone_hit:
        return "POSSIBLE_PHONE"
    if (
        evidence.low_motion_confirmed
        and (
            evidence.evidence_quality == EvidenceQuality.HIGH.value
            or (
                settings.idle_min_evidence_quality == EvidenceQuality.MEDIUM.value
                and evidence.evidence_quality == EvidenceQuality.MEDIUM.value
            )
        )
        and not evidence.idle_blocking_reasons
    ):
        return "IDLE_CANDIDATE"
    return "UNKNOWN"
