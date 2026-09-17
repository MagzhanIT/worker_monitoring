from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from config import settings
from services.activity_engine import ActivityEngine, PhoneTemporalHistory
from services.customer_analytics import (
    ACTIVE_SERVICE_PHASES,
    MEDICINE_RETRIEVAL_PHASES,
    CustomerAnalyticsService,
    CustomerObservation,
    WorkerObservation,
    customer_trust_classification,
)
from services.evidence_service import (
    ActivityEvidence,
    UnknownReason,
    assess_evidence_quality,
    evidence_status,
    normalize_unknown_reason,
)
from services.local_session_stitcher import LocalSessionStitcher
from services.model_registry import model_registry
from services.offline_worker_dataset import OfflineWorkerDatasetExporter
from services.person_detector import PersonDetector
from services.phone_association import associate_phones
from services.phone_detector import PhoneDetector, PhoneSearchScheduler
from services.pose_service import PoseService, pose_inference_due
from services.role_classifier import TemporalRoleClassifier
from services.state_machine import TemporalStateMachine
from services.tracker import Detection, StableTracker
from services.zone_service import ZONE_PRIORITY, TemporalZoneHistory, memberships
from services.work_motion_service import TemporalWorkMotion
from services.worker_session_service import WorkerSessionService
from utilities.geometry import center, distance, foot_point


STATUS_TEXT = {
    "WORK_OBSERVED": "Work observed",
    "REVIEW_NEEDED": "Review needed",
    "CUSTOMER_OBSERVED": "Customer observed",
    "APPROVED_BREAK": "Approved break",
    "INSUFFICIENT_EVIDENCE": "Insufficient evidence",
    "CONFIRMED_IDLE": "Confirmed idle",
}

STATUS_COLORS = {
    "WORK_OBSERVED": (54, 170, 80),
    "REVIEW_NEEDED": (0, 165, 255),
    "CUSTOMER_OBSERVED": (190, 95, 195),
    "APPROVED_BREAK": (220, 145, 45),
    "INSUFFICIENT_EVIDENCE": (150, 150, 150),
    "CONFIRMED_IDLE": (35, 120, 210),
}

ZONE_COLORS = {
    "ignore_area": (80, 80, 80),
    "register_interaction": (20, 150, 255),
    "shelf_interaction": (40, 210, 210),
    "cashier": (80, 200, 80),
    "service_position": (50, 180, 120),
    "waiting": (220, 130, 30),
    "break_area": (220, 90, 170),
    "employee_area": (50, 190, 50),
    "customer_area": (190, 100, 210),
    "entrance": (200, 190, 60),
}


def default_output_path(video_path: Path) -> Path:
    return video_path.with_name(f"{video_path.stem}_backend_test.mp4")


def default_json_path(output_path: Path) -> Path:
    return output_path.with_suffix(".json")


def default_artifact_paths(output_path: Path) -> dict[str, Path]:
    """Keep all validation evidence beside the annotated video."""
    stem = output_path.with_suffix("")
    return {
        "events_csv": Path(f"{stem}_events.csv"),
        "diagnostics_csv": Path(f"{stem}_diagnostics.csv"),
        "customers_csv": Path(f"{stem}_customers.csv"),
        "manager_html": Path(f"{stem}_manager.html"),
    }


def humanize(value: str | None) -> str:
    if not value:
        return "None"
    return value.replace("_", " ").title()


def status_text(value: str) -> str:
    return STATUS_TEXT.get(value, humanize(value))


def format_seconds(value: float) -> str:
    total = max(0, int(round(value)))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def load_camera_zones(camera_id: int | None) -> list[dict[str, Any]]:
    """Read enabled normalized zones. This function never writes to the database."""
    if camera_id is None:
        return []
    from sqlalchemy import select

    from database import SessionLocal
    from db_models.zone import CameraZone

    with SessionLocal() as db:
        rows = db.scalars(
            select(CameraZone).where(
                CameraZone.camera_id == camera_id,
                CameraZone.enabled.is_(True),
            )
        ).all()
        return [
            {
                "display_name": row.display_name,
                "zone_type": row.zone_type,
                "normalized_points": [tuple(point) for point in row.normalized_points],
                "enabled": bool(row.enabled),
            }
            for row in rows
        ]


def load_zones_json(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    rows = payload.get("zones", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("Zones JSON must be a list or an object containing a zones list.")
    zones: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Zone {index} must be an object.")
        zone_type = str(row.get("zone_type") or "").strip()
        raw_points = row.get("normalized_points") or row.get("points")
        if not zone_type or not isinstance(raw_points, list) or len(raw_points) < 3:
            raise ValueError(f"Zone {index} needs zone_type and at least three points.")
        points = [tuple(float(value) for value in point[:2]) for point in raw_points]
        if any(len(point) != 2 or not all(0 <= value <= 1 for value in point) for point in points):
            raise ValueError(f"Zone {index} points must be normalized x/y values from 0 to 1.")
        zones.append(
            {
                "display_name": row.get("display_name") or humanize(zone_type),
                "zone_type": zone_type,
                "normalized_points": points,
                "enabled": bool(row.get("enabled", True)),
            }
        )
    return [zone for zone in zones if zone["enabled"]]


def _clip_box(box: tuple[float, float, float, float], width: int, height: int) -> tuple[int, int, int, int]:
    left = min(width, max(0, int(box[0])))
    top = min(height, max(0, int(box[1])))
    right = min(width, max(left, int(box[2])))
    bottom = min(height, max(top, int(box[3])))
    return left, top, right, bottom


class OfflineAnalyzer:
    """The live evidence pipeline without cameras, API, reports, or database writes."""

    def __init__(
        self,
        zones: list[dict[str, Any]],
        *,
        enable_pose: bool = True,
        enable_phone: bool = True,
        camera_id: int | None = None,
        session_id: str = "offline-video",
    ) -> None:
        self.zones = zones
        self.camera_id = camera_id or 0
        self.detector = PersonDetector()
        self.tracker = StableTracker(id_namespace=self.camera_id)
        self.roles = TemporalRoleClassifier()
        self.poses = PoseService()
        self.phone_detector = PhoneDetector()
        self.phone_search = PhoneSearchScheduler()
        self.phone_history = PhoneTemporalHistory()
        self.zone_history = TemporalZoneHistory()
        self.activity_engine = ActivityEngine()
        self.state_machine = TemporalStateMachine()
        self.work_motion = TemporalWorkMotion()
        self.customers = CustomerAnalyticsService()
        self.worker_sessions = WorkerSessionService()
        self.session_stitcher = LocalSessionStitcher()
        session_tag = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:6].upper()
        self.camera_session_id = f"OFFLINE-{session_tag}"
        # A fixed origin keeps event/session IDs stable across repeat runs.
        self._time_origin = datetime(2000, 1, 1, tzinfo=UTC)
        self.session_stitches: list[dict[str, Any]] = []
        self.detection_diagnostics: Counter[str] = Counter()
        self._last_centers: dict[int, tuple[float, float]] = {}
        self._last_moved_at: dict[int, float] = {}
        self._pending_runtime_expiry: dict[int, float] = {}
        self.person_ready = False
        self.pose_ready = False
        self.phone_ready = False
        self.enable_pose = enable_pose
        self.enable_phone = enable_phone

    def load_models(self) -> dict[str, bool]:
        self.person_ready = self.detector.load()
        if not self.person_ready:
            raise RuntimeError(
                "The person detector could not load. Check PERSON_MODEL_PATH and the model classes."
            )
        self.pose_ready = bool(self.enable_pose and settings.pose_enabled and self.poses.load())
        self.phone_ready = bool(self.enable_phone and settings.phone_enabled and self.phone_detector.load())
        return {
            "person": self.person_ready,
            "lab_coat_verifier": bool(self.detector.lab_coat_verifier),
            "pose": self.pose_ready,
            "phone": self.phone_ready,
        }

    def _clear_track(self, track_id: int, *, preserve_runtime: bool = False) -> None:
        self.roles.clear(track_id)
        self.poses.clear(track_id)
        self.phone_history.clear(track_id)
        self.phone_search.clear(track_id)
        self.zone_history.clear(track_id)
        if not preserve_runtime:
            self.state_machine.clear(track_id)
            self.work_motion.clear(track_id)
            self._pending_runtime_expiry.pop(track_id, None)
        self._last_centers.pop(track_id, None)
        self._last_moved_at.pop(track_id, None)

    def analyze(self, frame, frame_number: int, video_seconds: float) -> list[dict[str, Any]]:
        for track_id, expires_at in list(self._pending_runtime_expiry.items()):
            if video_seconds >= expires_at:
                self.state_machine.clear(track_id)
                self.work_motion.clear(track_id)
                self._pending_runtime_expiry.pop(track_id, None)
        observations = self.detector.detect(frame)
        self.detection_diagnostics.update(self.detector.last_diagnostics)
        detections = [Detection(item.bbox, item.confidence, item.class_name) for item in observations]
        tracks, expired = self.tracker.update(detections, video_seconds)
        event_time = self._time_origin + timedelta(seconds=video_seconds)
        for track in expired:
            self.session_stitcher.expire(track.track_id)
            self.worker_sessions.close(track.track_id, event_time)
            self.customers.mark_customer_missing(track.track_id, event_time)
            self._pending_runtime_expiry[track.track_id] = (
                video_seconds + settings.idle_track_gap_grace_seconds
            )
            self._clear_track(track.track_id, preserve_runtime=True)

        height, width = frame.shape[:2]
        interaction_zone_types = {
            "register_interaction",
            "shelf_interaction",
            "medicine_shelf",
            "computer",
            "pos",
        }
        standing_zones = [
            zone for zone in self.zones if zone["zone_type"] not in interaction_zone_types
        ]
        interaction_zones = [
            zone for zone in self.zones if zone["zone_type"] in interaction_zone_types
        ]
        classified: list[tuple[Any, str, set[str], str | None]] = []
        track_poses: dict[int, Any] = {}
        track_motion: dict[int, tuple[str, float]] = {}
        track_work_motion: dict[int, Any] = {}
        output: list[dict[str, Any]] = []

        for track in tracks:
            if not track.directly_observed or not track.confirmed:
                continue
            foot = foot_point(track.bbox)
            foot_zones, _ = memberships((foot[0] / width, foot[1] / height), standing_zones)
            pose = None
            pose_candidate = bool(
                track.role_hint == "lab_coat"
                or {"employee_area", "cashier", "service_position"} & set(foot_zones)
            )
            if self.pose_ready and pose_candidate:
                left, top, right, bottom = _clip_box(track.bbox, width, height)
                crop = frame[top:bottom, left:right]
                pose = self.poses.fresh(track.track_id, video_seconds)
                if pose_inference_due(
                    frame_number,
                    settings.pose_run_every_n_frames,
                    pose,
                ):
                    pose = self.poses.infer(
                        track.track_id,
                        frame_number,
                        track.bbox,
                        crop,
                        video_seconds,
                    )
            track_poses[track.track_id] = pose

            interaction_hits: set[str] = set()
            if pose and pose.status != "STALE":
                for index in (9, 10):
                    if (
                        len(pose.global_keypoints) > index
                        and pose.global_keypoints[index][2] >= settings.pose_keypoint_confidence
                    ):
                        wrist = pose.global_keypoints[index]
                        names, _ = memberships(
                            (wrist[0] / width, wrist[1] / height), interaction_zones
                        )
                        interaction_hits.update(names)

            all_zones = sorted(
                set(foot_zones) | interaction_hits,
                key=lambda name: ZONE_PRIORITY.get(name, 0),
                reverse=True,
            )
            primary = all_zones[0] if all_zones else None
            confirmed_zones = self.zone_history.update(track.track_id, set(all_zones))
            role = self.roles.update(
                track.track_id,
                lab_coat_overlap=track.role_hint == "lab_coat",
                employee_zone="employee_area" in confirmed_zones,
                behind_counter=bool({"cashier", "service_position"} & confirmed_zones),
                worker_activity_zone=bool(
                    {
                        "register_interaction",
                        "shelf_interaction",
                        "medicine_shelf",
                        "computer",
                        "pos",
                    }
                    & confirmed_zones
                ),
                customer_zone=bool({"customer_area", "waiting", "entrance"} & confirmed_zones),
            )
            work_motion = self.work_motion.update(
                track.track_id, pose, track.bbox, video_seconds
            )
            track_work_motion[track.track_id] = work_motion
            low_movement = work_motion.low_motion_seconds
            motion = "STATIONARY" if work_motion.low_motion else "RECENT_MOVEMENT"
            track_motion[track.track_id] = (motion, low_movement)
            classified.append((track, role, confirmed_zones, primary))
            reasons: list[str] = []
            if track.role_hint == "lab_coat":
                reasons.append("lab coat detected")
            if confirmed_zones:
                reasons.append(f"zones={sorted(confirmed_zones)}")
            elif all_zones:
                reasons.append(f"candidate zones={sorted(all_zones)}")
            elif not self.zones:
                reasons.append("no camera zones configured")
            if role == "UNKNOWN":
                reasons.append("insufficient evidence for worker/customer role")
            output.append(
                {
                    "track_id": track.track_id,
                    "bbox": tuple(float(value) for value in track.bbox),
                    "role": role,
                    "activity": "UNKNOWN",
                    "evidence_status": evidence_status(role, "UNKNOWN"),
                    "confidence": float(track.confidence),
                    "zone": primary,
                    "motion": motion,
                    "stationary_seconds": round(low_movement, 1),
                    "reasons": reasons,
                    "phone_boxes": [],
                    "phone_evidence": "Not evaluated for this role",
                    "phone_state": "NO_PHONE_EVIDENCE",
                    "physical_phone_hit": False,
                    "physical_phone_confirmed": False,
                    "phone_like_pose": False,
                    "phone_call_behavior": False,
                }
            )

        customers = [item for item in classified if item[1] == "CUSTOMER"]
        by_track = {item["track_id"]: item for item in output}
        worker_runtime: dict[int, tuple[Any, dict | None, Any]] = {}
        for track, role, _, _ in classified:
            if role != "WORKER":
                continue
            left, top, right, bottom = _clip_box(track.bbox, width, height)
            crop = frame[top:bottom, left:right]
            session_stitch = None
            worker_session = self.worker_sessions.active.get(track.track_id)
            if worker_session is None:
                matched = (
                    self.session_stitcher.match(track.bbox, crop, video_seconds)
                    if crop.size
                    else None
                )
                if matched is not None:
                    worker_session = self.worker_sessions.rebind(
                        track.track_id, matched.session, event_time
                    )
                    timers_preserved = bool(
                        matched.gap_seconds <= settings.idle_track_gap_grace_seconds
                        and self.state_machine.rebind(
                            matched.previous_track_id, track.track_id
                        )
                    )
                    if timers_preserved:
                        self.work_motion.rebind(
                            matched.previous_track_id, track.track_id
                        )
                    self._pending_runtime_expiry.pop(matched.previous_track_id, None)
                    session_stitch = {
                        "previous_track_id": matched.previous_track_id,
                        "new_track_id": track.track_id,
                        "gap_seconds": round(matched.gap_seconds, 3),
                        "appearance_distance": round(
                            matched.appearance_distance, 4
                        ),
                        "spatial_distance": round(matched.spatial_distance, 2),
                        "confidence": round(matched.confidence, 4),
                        "reason": matched.reason,
                        "activity_timers_preserved": timers_preserved,
                    }
                    self.session_stitches.append(session_stitch)
                else:
                    worker_session = self.worker_sessions.ensure(
                        track.track_id,
                        self.camera_id,
                        self.camera_session_id,
                        event_time,
                    )
            else:
                worker_session = self.worker_sessions.ensure(
                    track.track_id,
                    self.camera_id,
                    self.camera_session_id,
                    event_time,
                )
            if crop.size:
                self.session_stitcher.observe(
                    track.track_id,
                    worker_session,
                    track.bbox,
                    crop,
                    video_seconds,
                )
            worker_runtime[track.track_id] = (
                worker_session,
                session_stitch,
                crop,
            )

        customer_observations = [
            CustomerObservation(
                track_id=track.track_id,
                bbox=track.bbox,
                zones=set(confirmed_zones),
                confidence=track.confidence,
                camera_id=self.camera_id,
            )
            for track, _, confirmed_zones, _ in customers
            if {"waiting", "customer_area", "service_position", "cashier"}
            & set(confirmed_zones)
        ]
        worker_observations = [
            WorkerObservation(
                worker_session_id=worker_runtime[track.track_id][0].worker_session_id,
                track_id=track.track_id,
                bbox=track.bbox,
                zones=set(confirmed_zones),
                confidence=track.confidence,
            )
            for track, role, confirmed_zones, _ in classified
            if role == "WORKER" and track.track_id in worker_runtime
        ]
        self.customers.update_scene(
            customer_observations,
            worker_observations,
            event_time,
            settings.track_max_center_distance,
        )
        for track, _, _, _ in customers:
            session = self.customers.active.get(track.track_id)
            if session is None:
                continue
            by_track[track.track_id].update(
                {
                    "customer_service_session_id": session.service_session_id,
                    "customer_phase": session.current_phase,
                    "customer_waiting_seconds": round(
                        (
                            session.waiting_seconds
                            if session.waiting_seconds is not None
                            else max(
                                0.0,
                                (event_time - session.waiting_started_at).total_seconds(),
                            )
                        ),
                        3,
                    ),
                    "customer_service_seconds": round(
                        max(
                            0.0,
                            (event_time - session.service_started_at).total_seconds(),
                        )
                        if session.service_started_at
                        else 0.0,
                        3,
                    ),
                    "assigned_worker_session_id": session.worker_session_id,
                    "assignment_confidence": round(session.assignment_confidence, 4),
                }
            )
        self.phone_search.begin_frame()

        for track, role, confirmed_zones, primary in classified:
            if role != "WORKER":
                continue
            left, top, right, bottom = _clip_box(track.bbox, width, height)
            worker_session, session_stitch, crop = worker_runtime[track.track_id]
            pose = track_poses.get(track.track_id)
            wrists: dict[str, tuple[float, float]] = {}
            face = None
            if pose and pose.status != "STALE":
                if len(pose.global_keypoints) > 10:
                    if pose.global_keypoints[9][2] >= settings.pose_keypoint_confidence:
                        wrists["left"] = pose.global_keypoints[9][:2]
                    if pose.global_keypoints[10][2] >= settings.pose_keypoint_confidence:
                        wrists["right"] = pose.global_keypoints[10][:2]
                if (
                    pose.global_keypoints
                    and pose.global_keypoints[0][2] >= settings.pose_keypoint_confidence
                ):
                    face = pose.global_keypoints[0][:2]

            phone_like_pose = False
            current_center = center(track.bbox)
            if pose and pose.status != "STALE" and wrists:
                body_height = max(1, bottom - top)
                shoulder_points = [
                    pose.global_keypoints[index][:2]
                    for index in (5, 6)
                    if len(pose.global_keypoints) > index
                    and pose.global_keypoints[index][2] >= settings.pose_keypoint_confidence
                ]
                torso = (
                    (
                        sum(point[0] for point in shoulder_points) / len(shoulder_points),
                        sum(point[1] for point in shoulder_points) / len(shoulder_points),
                    )
                    if shoulder_points
                    else current_center
                )
                phone_like_pose = any(
                    distance(wrist, torso) / body_height <= 0.28
                    or (face is not None and distance(wrist, face) / body_height <= 0.30)
                    for wrist in wrists.values()
                )
                if phone_like_pose:
                    self.phone_search.trigger_focused(track.track_id, video_seconds)

            candidates = []
            if (
                self.phone_ready
                and crop.size
                and self.phone_search.should_search(
                    track.track_id, frame_number, "person", video_seconds
                )
            ):
                candidates.extend(self.phone_detector.detect_crop(crop, track.bbox, "person"))
            if self.phone_ready and self.phone_search.is_focused(track.track_id, video_seconds):
                upper_bottom = top + max(1, int((bottom - top) * 0.68))
                upper_crop = frame[top:upper_bottom, left:right]
                if (
                    upper_crop.size
                    and self.phone_search.should_search(
                        track.track_id, frame_number, "upper_body", video_seconds
                    )
                ):
                    candidates.extend(
                        self.phone_detector.detect_crop(
                            upper_crop, (left, top, right, upper_bottom), "upper_body"
                        )
                    )
                radius = max(32, int((bottom - top) * 0.16))
                for side, wrist in wrists.items():
                    wx, wy = (int(value) for value in wrist)
                    wrist_box = (
                        max(0, wx - radius),
                        max(0, wy - radius),
                        min(width, wx + radius),
                        min(height, wy + radius),
                    )
                    wrist_crop = frame[
                        wrist_box[1] : wrist_box[3], wrist_box[0] : wrist_box[2]
                    ]
                    if (
                        wrist_crop.size
                        and self.phone_search.should_search(
                            track.track_id,
                            frame_number,
                            f"{side}_wrist",
                            video_seconds,
                        )
                    ):
                        candidates.extend(
                            self.phone_detector.detect_crop(
                                wrist_crop, wrist_box, f"{side}_wrist"
                            )
                        )

            associations = associate_phones(
                candidates,
                [
                    {
                        "track_id": track.track_id,
                        "bbox": track.bbox,
                        "wrists": wrists,
                        "face": face,
                    }
                ],
            ) if candidates else []
            accepted = [item for item in associations if item.track_id == track.track_id]
            phone_hit = any(item.candidate.physical for item in accepted)
            behavior_hit = any(item.candidate.behavior for item in accepted)
            physical_object_confidence = max(
                (
                    item.candidate.confidence
                    for item in accepted
                    if item.candidate.physical
                ),
                default=0.0,
            )
            pose_support_confidence = max(
                (
                    pose.global_keypoints[index][2]
                    for index in (9, 10)
                    if pose is not None and len(pose.global_keypoints) > index
                ),
                default=0.0,
            )
            context_support_confidence = max(
                (item.association_score for item in accepted),
                default=0.0,
            )
            phone_state = self.phone_history.update(
                track.track_id, phone_hit, video_seconds
            )
            temporal_phone_confidence = self.phone_history.confidence(
                track.track_id, video_seconds
            )
            final_phone_confidence = min(
                1.0,
                0.45 * physical_object_confidence
                + 0.15 * pose_support_confidence
                + 0.20 * context_support_confidence
                + 0.20 * temporal_phone_confidence,
            )
            physical_confirmed = phone_state == "ON_PHONE"
            motion, low_movement = track_motion[track.track_id]
            work_motion = track_work_motion[track.track_id]
            customer_service = self.customers.service_for_worker(
                worker_session.worker_session_id
            )
            service_phase = customer_service.current_phase if customer_service else None
            fetching_medicine = service_phase in MEDICINE_RETRIEVAL_PHASES
            serving = bool(service_phase in ACTIVE_SERVICE_PHASES and not fetching_medicine)
            cashier_work = bool(
                "cashier" in confirmed_zones
                and "register_interaction" in confirmed_zones
            )
            computer_work = bool({"computer", "pos"} & confirmed_zones)
            shelf_work = bool(
                {"shelf_interaction", "medicine_shelf", "storage"}
                & confirmed_zones
            )
            other_work = bool(
                work_motion.confirmed
                and "break_area" not in confirmed_zones
                and {"employee_area", "cashier", "service_position"}
                & confirmed_zones
            )
            pose_status = (
                pose.status
                if pose is not None and pose.status != "STALE"
                else "TEMPORARILY_MISSING"
                if work_motion.pose_temporarily_missing
                else "MISSING"
            )
            pose_confident_points = sum(
                point[2] >= settings.pose_keypoint_confidence
                for point in (pose.global_keypoints if pose is not None else [])
            )
            assessment = assess_evidence_quality(
                track_confirmed=track.confirmed,
                track_age_seconds=track.age,
                confidence=track.confidence,
                crop_width=max(0, right - left),
                crop_height=max(0, bottom - top),
                zones_configured=bool(self.zones),
                confirmed_zones=set(confirmed_zones),
                pose_status=pose_status,
                pose_confident_points=pose_confident_points,
                bbox_motion_reliable=work_motion.bbox_reliable,
                minimum_track_age_seconds=settings.idle_min_track_age_seconds,
            )
            idle_blocking_reasons = list(assessment.idle_blocking_reasons)
            if not work_motion.low_motion:
                idle_blocking_reasons.append("meaningful or unstable body movement")
            if fetching_medicine:
                idle_blocking_reasons.append("assigned medicine retrieval is active")
            elif serving:
                idle_blocking_reasons.append("assigned customer service is active")
            if shelf_work:
                idle_blocking_reasons.append("shelf or medicine work is active")
            if cashier_work or computer_work:
                idle_blocking_reasons.append("POS/register work is active")
            if other_work:
                idle_blocking_reasons.append("repeated work-like hand motion")
            if physical_confirmed:
                idle_blocking_reasons.append("confirmed physical-phone evidence")
            elif phone_hit or phone_like_pose or behavior_hit:
                idle_blocking_reasons.append("possible-phone evidence requires review")
            if "break_area" in confirmed_zones:
                idle_blocking_reasons.append("approved break zone")
            limitations = ([] if self.pose_ready else ["Pose model unavailable"]) + (
                [] if self.zones else ["No activity zones are configured"]
            )
            evidence = ActivityEvidence(
                camera_healthy=True,
                physical_phone_confirmed=physical_confirmed,
                physical_phone_hit=phone_hit,
                phone_like_pose=phone_like_pose,
                phone_call_behavior=behavior_hit,
                serving_customer=serving,
                fetching_medicine=fetching_medicine,
                cashier=cashier_work,
                computer_pos=computer_work,
                shelf=shelf_work,
                other_work=other_work,
                approved_break="break_area" in confirmed_zones,
                low_movement_seconds=low_movement,
                low_motion_confirmed=work_motion.low_motion,
                evidence_quality=assessment.quality.value,
                track_age_seconds=track.age,
                track_stable=track.confirmed,
                body_motion=work_motion.body_speed,
                bbox_motion=work_motion.bbox_speed,
                wrist_motion=work_motion.wrist_speed,
                elbow_motion=work_motion.elbow_speed,
                pose_status=pose_status,
                pose_confidence=pose_support_confidence,
                idle_blocking_reasons=idle_blocking_reasons,
                unknown_reason=assessment.unknown_reason,
                confidence=track.confidence,
                zone=primary,
                reasons=[
                    f"zones={sorted(confirmed_zones)}",
                    f"phone_state={phone_state}",
                    f"phone_object_confidence={physical_object_confidence:.3f}",
                    f"phone_pose_support_confidence={pose_support_confidence:.3f}",
                    f"phone_context_support_confidence={context_support_confidence:.3f}",
                    f"phone_temporal_confidence={temporal_phone_confidence:.3f}",
                    f"phone_final_confidence={final_phone_confidence:.3f}",
                    f"customer_service_phase={service_phase or 'none'}",
                    f"work_motion={work_motion.reason}",
                    f"evidence_quality={assessment.quality.value}",
                ],
                limitations=limitations,
            )
            proposed = self.activity_engine.choose(evidence)
            proposed_unknown_reason = normalize_unknown_reason(
                proposed, evidence.unknown_reason
            )
            if proposed_unknown_reason:
                evidence.reasons.append(f"unknown_reason={proposed_unknown_reason}")
            self.state_machine.update(
                track.track_id,
                proposed,
                video_seconds,
                track.confidence,
                evidence.reasons,
                evidence.limitations,
                evidence_quality=assessment.quality.value,
                idle_blocking_reasons=idle_blocking_reasons,
                exit_reason=(idle_blocking_reasons[0] if idle_blocking_reasons else None),
            )
            current_activity = self.state_machine.states[track.track_id].current_state
            unknown_reason = None
            if current_activity == "UNKNOWN":
                unknown_reason = (
                    proposed_unknown_reason
                    if proposed == "UNKNOWN"
                    else UnknownReason.INSUFFICIENT_TEMPORAL_EVIDENCE.value
                )
                unknown_reason = normalize_unknown_reason("UNKNOWN", unknown_reason)
            diagnostics = self.state_machine.diagnostics(track.track_id, video_seconds)
            phone_evidence = (
                "Confirmed physical phone"
                if physical_confirmed
                else "Physical phone candidate"
                if phone_hit
                else "Associated phone-call behavior"
                if behavior_hit
                else "Phone-like pose only"
                if phone_like_pose
                else "No phone evidence"
            )
            item = by_track[track.track_id]
            item.update(
                {
                    "worker_session_id": worker_session.worker_session_id,
                    "worker_label": worker_session.display_name,
                    "session_stitch": session_stitch,
                    "activity": current_activity,
                    "evidence_status": evidence_status("WORKER", current_activity),
                    "reasons": evidence.reasons + evidence.limitations,
                    "unknown_reason": unknown_reason,
                    "candidate_activity": diagnostics.get("candidate_activity"),
                    "candidate_duration_seconds": diagnostics.get(
                        "candidate_duration_seconds", 0.0
                    ),
                    "idle_candidate_seconds": diagnostics.get(
                        "idle_candidate_seconds", 0.0
                    ),
                    "idle_confirmation_seconds": settings.idle_confirm_seconds,
                    "confirmed_idle_seconds": diagnostics.get(
                        "confirmed_idle_seconds", 0.0
                    ),
                    "track_age_seconds": round(track.age, 3),
                    "track_stable": track.confirmed,
                    "evidence_quality": assessment.quality.value,
                    "body_motion": round(work_motion.body_speed, 6),
                    "bbox_motion": round(work_motion.bbox_speed, 6),
                    "wrist_motion": round(work_motion.wrist_speed, 6),
                    "elbow_motion": round(work_motion.elbow_speed, 6),
                    "pose_status": pose_status,
                    "pose_confidence": round(pose_support_confidence, 4),
                    "idle_blocking_reasons": idle_blocking_reasons,
                    "customer_service_session_id": (
                        customer_service.service_session_id if customer_service else None
                    ),
                    "customer_service_phase": service_phase,
                    "phone_evidence": phone_evidence,
                    "phone_state": phone_state,
                    "physical_phone_confidence": round(
                        physical_object_confidence, 4
                    ),
                    "possible_phone_confidence": round(
                        max(pose_support_confidence, context_support_confidence), 4
                    ),
                    "temporal_phone_confidence": round(
                        temporal_phone_confidence, 4
                    ),
                    "final_phone_confidence": round(final_phone_confidence, 4),
                    "physical_phone_hit": phone_hit,
                    "physical_phone_confirmed": physical_confirmed,
                    "phone_like_pose": phone_like_pose,
                    "phone_call_behavior": behavior_hit,
                    "phone_boxes": [
                        {
                            "bbox": tuple(float(value) for value in association.candidate.bbox),
                            "confidence": float(association.candidate.confidence),
                            "class_name": association.candidate.class_name,
                        }
                        for association in accepted
                    ],
                }
            )
        return output


class SummaryCollector:
    def __init__(self) -> None:
        self.tracks: dict[str, dict[str, Any]] = {}
        self.status_seconds: defaultdict[str, float] = defaultdict(float)
        self.activity_seconds: defaultdict[str, float] = defaultdict(float)
        self.phone_evidence_seconds: defaultdict[str, float] = defaultdict(float)
        self.max_visible = 0
        self.events: list[dict[str, Any]] = []
        self._active_events: dict[str, dict[str, Any]] = {}
        self.diagnostics: list[dict[str, Any]] = []
        self._finalized_at: float | None = None

    @staticmethod
    def _entity_key(observation: dict[str, Any]) -> str:
        return str(
            observation.get("worker_session_id")
            or f"TRACK-{observation['track_id']}"
        )

    def _observe_event(
        self, observation: dict[str, Any], timestamp: float, seconds: float
    ) -> None:
        if observation.get("role") != "WORKER":
            return
        entity_key = self._entity_key(observation)
        activity = observation["activity"]
        current = self._active_events.get(entity_key)
        if current is not None and current["activity"] != activity:
            self._close_event(entity_key, timestamp, f"transition_to_{activity.lower()}")
            current = None
        if current is None:
            current = {
                "event_id": f"OFFLINE-E{len(self.events) + len(self._active_events) + 1:06d}",
                "worker_session_id": observation.get("worker_session_id"),
                "worker_label": observation.get("worker_label"),
                "raw_track_ids": {observation["track_id"]},
                "activity": activity,
                "start_seconds": round(timestamp, 3),
                "end_seconds": None,
                "duration_seconds": 0.0,
                "confirmation_seconds": (
                    settings.idle_confirm_seconds if activity == "IDLE" else 0.0
                ),
                "evidence_quality": observation.get("evidence_quality", "LOW"),
                "unknown_reason": observation.get("unknown_reason"),
                "zone": observation.get("zone"),
                "ending_reason": None,
                "transition_type": "IDLE_STARTED" if activity == "IDLE" else "ACTIVITY_STARTED",
                "end_transition_type": None,
                "review_status": "unreviewed",
                "body_motion_total": 0.0,
                "wrist_motion_total": 0.0,
                "elbow_motion_total": 0.0,
                "sample_seconds": 0.0,
            }
            self._active_events[entity_key] = current
        current["raw_track_ids"].add(observation["track_id"])
        current["worker_session_id"] = observation.get("worker_session_id")
        current["worker_label"] = observation.get("worker_label")
        current["evidence_quality"] = observation.get(
            "evidence_quality", current["evidence_quality"]
        )
        current["unknown_reason"] = normalize_unknown_reason(
            activity,
            observation.get("unknown_reason"),
        )
        current["zone"] = observation.get("zone") or current["zone"]
        current["body_motion_total"] += float(observation.get("body_motion", 0.0)) * seconds
        current["wrist_motion_total"] += float(observation.get("wrist_motion", 0.0)) * seconds
        current["elbow_motion_total"] += float(observation.get("elbow_motion", 0.0)) * seconds
        current["sample_seconds"] += seconds

    def _close_event(self, entity_key: str, at: float, reason: str) -> None:
        event = self._active_events.pop(entity_key, None)
        if event is None:
            return
        event["end_seconds"] = round(max(event["start_seconds"], at), 3)
        event["duration_seconds"] = round(
            max(0.0, event["end_seconds"] - event["start_seconds"]), 3
        )
        sample_seconds = max(1e-9, event.pop("sample_seconds"))
        event["average_body_motion"] = round(
            event.pop("body_motion_total") / sample_seconds, 6
        )
        event["average_wrist_motion"] = round(
            event.pop("wrist_motion_total") / sample_seconds, 6
        )
        event["average_elbow_motion"] = round(
            event.pop("elbow_motion_total") / sample_seconds, 6
        )
        event["raw_track_ids"] = sorted(event["raw_track_ids"])
        event["ending_reason"] = reason
        event["end_transition_type"] = (
            "IDLE_ENDED" if event["activity"] == "IDLE" else "ACTIVITY_ENDED"
        )
        self.events.append(event)

    def capture_diagnostics(
        self, observations: list[dict[str, Any]], timestamp: float
    ) -> None:
        for item in observations:
            self.diagnostics.append(
                {
                    "timestamp_seconds": round(timestamp, 3),
                    "worker_session_id": item.get("worker_session_id"),
                    "worker_label": item.get("worker_label"),
                    "raw_track_id": item.get("track_id"),
                    "role": item.get("role"),
                    "final_activity": item.get("activity"),
                    "candidate_activity": item.get("candidate_activity"),
                    "candidate_duration_seconds": item.get(
                        "candidate_duration_seconds", 0.0
                    ),
                    "idle_candidate_seconds": item.get("idle_candidate_seconds", 0.0),
                    "idle_confirmation_seconds": item.get(
                        "idle_confirmation_seconds", settings.idle_confirm_seconds
                    ),
                    "confirmed_idle_seconds": item.get("confirmed_idle_seconds", 0.0),
                    "track_age_seconds": item.get("track_age_seconds", 0.0),
                    "track_stable": item.get("track_stable", False),
                    "evidence_quality": item.get("evidence_quality"),
                    "body_motion": item.get("body_motion", 0.0),
                    "bbox_motion": item.get("bbox_motion", 0.0),
                    "wrist_motion": item.get("wrist_motion", 0.0),
                    "elbow_motion": item.get("elbow_motion", 0.0),
                    "pose_status": item.get("pose_status"),
                    "pose_confidence": item.get("pose_confidence", 0.0),
                    "zone": item.get("zone"),
                    "customer_service_session_id": item.get(
                        "customer_service_session_id"
                    ),
                    "customer_service_phase": item.get("customer_service_phase"),
                    "customer_waiting_seconds": item.get(
                        "customer_waiting_seconds", 0.0
                    ),
                    "customer_service_seconds": item.get(
                        "customer_service_seconds", 0.0
                    ),
                    "physical_phone_confidence": item.get(
                        "physical_phone_confidence", 0.0
                    ),
                    "possible_phone_confidence": item.get(
                        "possible_phone_confidence", 0.0
                    ),
                    "temporal_phone_confidence": item.get(
                        "temporal_phone_confidence", 0.0
                    ),
                    "final_phone_confidence": item.get(
                        "final_phone_confidence", 0.0
                    ),
                    "unknown_reason": item.get("unknown_reason"),
                    "idle_blocking_reasons": " | ".join(
                        item.get("idle_blocking_reasons") or []
                    ),
                }
            )

    def finalize(self, at: float) -> None:
        if self._finalized_at is not None:
            return
        for entity_key in list(self._active_events):
            self._close_event(entity_key, at, "video_processing_ended")
        self._finalized_at = at

    def update(self, observations: list[dict[str, Any]], timestamp: float, seconds: float) -> None:
        self.max_visible = max(self.max_visible, len(observations))
        for observation in observations:
            self._observe_event(observation, timestamp, seconds)
            track_id = observation["track_id"]
            raw_key = f"TRACK-{track_id}"
            worker_session_id = observation.get("worker_session_id")
            entity_key = str(worker_session_id or raw_key)
            if worker_session_id and raw_key in self.tracks and raw_key != entity_key:
                raw = self.tracks.pop(raw_key)
                existing = self.tracks.get(entity_key)
                if existing is None:
                    raw["entity_id"] = entity_key
                    raw["worker_session_id"] = worker_session_id
                    raw["worker_label"] = observation.get("worker_label")
                    self.tracks[entity_key] = raw
                else:
                    existing["first_seen_seconds"] = min(
                        existing["first_seen_seconds"], raw["first_seen_seconds"]
                    )
                    existing["last_seen_seconds"] = max(
                        existing["last_seen_seconds"], raw["last_seen_seconds"]
                    )
                    existing["observed_seconds"] += raw["observed_seconds"]
                    existing["track_ids"].update(raw["track_ids"])
                    for field in (
                        "roles",
                        "activities",
                        "evidence_statuses",
                        "phone_evidence",
                    ):
                        for key, value in raw[field].items():
                            existing[field][key] += value
                    existing["zones"].update(raw["zones"])
                    existing["max_confidence"] = max(
                        existing["max_confidence"], raw["max_confidence"]
                    )
            track = self.tracks.setdefault(
                entity_key,
                {
                    "entity_id": entity_key,
                    "worker_session_id": worker_session_id,
                    "worker_label": observation.get("worker_label"),
                    "track_id": track_id,
                    "track_ids": {track_id},
                    "first_seen_seconds": round(timestamp, 3),
                    "last_seen_seconds": round(timestamp, 3),
                    "observed_seconds": 0.0,
                    "roles": defaultdict(float),
                    "activities": defaultdict(float),
                    "evidence_statuses": defaultdict(float),
                    "phone_evidence": defaultdict(float),
                    "zones": Counter(),
                    "max_confidence": 0.0,
                },
            )
            track["track_id"] = track_id
            track["track_ids"].add(track_id)
            if worker_session_id:
                track["worker_session_id"] = worker_session_id
                track["worker_label"] = observation.get("worker_label")
            track["last_seen_seconds"] = round(timestamp, 3)
            track["observed_seconds"] += seconds
            track["roles"][observation["role"]] += seconds
            track["activities"][observation["activity"]] += seconds
            track["evidence_statuses"][observation["evidence_status"]] += seconds
            track["phone_evidence"][observation["phone_evidence"]] += seconds
            if observation.get("zone"):
                track["zones"][observation["zone"]] += 1
            track["max_confidence"] = max(
                track["max_confidence"], observation["confidence"]
            )
            self.status_seconds[observation["evidence_status"]] += seconds
            self.activity_seconds[observation["activity"]] += seconds
            self.phone_evidence_seconds[observation["phone_evidence"]] += seconds

    @staticmethod
    def _rounded(values: dict[str, float]) -> dict[str, float]:
        return {key: round(value, 2) for key, value in sorted(values.items())}

    def as_dict(self) -> dict[str, Any]:
        tracks = []
        for value in self.tracks.values():
            tracks.append(
                {
                    **value,
                    "track_ids": sorted(value["track_ids"]),
                    "observed_seconds": round(value["observed_seconds"], 2),
                    "roles": self._rounded(value["roles"]),
                    "activities": self._rounded(value["activities"]),
                    "evidence_statuses": self._rounded(value["evidence_statuses"]),
                    "phone_evidence_seconds": self._rounded(value["phone_evidence"]),
                    "zones": dict(value["zones"].most_common()),
                    "max_confidence": round(value["max_confidence"], 4),
                }
            )
        tracks.sort(key=lambda item: (item["first_seen_seconds"], item["entity_id"]))
        unique_track_ids = len(
            {track_id for item in tracks for track_id in item["track_ids"]}
        )
        return {
            "unique_track_ids": unique_track_ids,
            "unique_entities": len(tracks),
            "anonymous_worker_sessions": sum(
                bool(item.get("worker_session_id")) for item in tracks
            ),
            "max_people_visible": self.max_visible,
            "evidence_status_seconds": self._rounded(self.status_seconds),
            "activity_seconds": self._rounded(self.activity_seconds),
            "phone_evidence_seconds": self._rounded(self.phone_evidence_seconds),
            "event_count": len(self.events) + len(self._active_events),
            "tracks": tracks,
        }


SUPPORTED_GROUND_TRUTH = {
    "WORKING",
    "SERVING_CUSTOMER",
    "FETCHING_MEDICINE",
    "SHELF_WORK",
    "POS_WORK",
    "IDLE",
    "PHONE",
    "UNKNOWN",
}


def _validation_activity(activity: str | None) -> str:
    if activity in {
        "SERVING_CUSTOMER",
        "FETCHING_MEDICINE",
        "SHELF_WORK",
        "IDLE",
    }:
        return str(activity)
    if activity == "COMPUTER_POS_WORK" or activity == "CASHIER_WORK":
        return "POS_WORK"
    if activity in {"OTHER_WORK", "RESTOCKING"}:
        return "WORKING"
    if activity == "ON_PHONE":
        return "PHONE"
    return "UNKNOWN"


def load_ground_truth(path: Path) -> list[dict[str, Any]]:
    with path.expanduser().resolve().open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"camera_id", "worker_label", "start_seconds", "end_seconds", "expected_activity"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(
            "Ground-truth CSV requires camera_id, worker_label, start_seconds, "
            "end_seconds, expected_activity, and optional notes."
        )
    result: list[dict[str, Any]] = []
    for number, row in enumerate(rows, start=2):
        expected = str(row["expected_activity"]).strip().upper()
        if expected not in SUPPORTED_GROUND_TRUTH:
            raise ValueError(f"Unsupported expected_activity on CSV line {number}: {expected}")
        start = float(row["start_seconds"])
        end = float(row["end_seconds"])
        if start < 0 or end <= start:
            raise ValueError(f"Invalid time interval on CSV line {number}.")
        result.append(
            {
                "camera_id": int(row["camera_id"]),
                "worker_label": str(row["worker_label"]).strip(),
                "start_seconds": start,
                "end_seconds": end,
                "expected_activity": expected,
                "notes": str(row.get("notes") or "").strip(),
            }
        )
    return result


def _diagnostic_matches_label(row: dict[str, Any], label: str) -> bool:
    if not label:
        return row.get("role") == "WORKER"
    choices = {
        str(row.get("worker_label") or "").casefold(),
        str(row.get("worker_session_id") or "").casefold(),
        str(row.get("raw_track_id") or "").casefold(),
        f"track-{row.get('raw_track_id')}".casefold(),
    }
    return label.casefold() in choices


def evaluate_ground_truth(
    ground_truth: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    pairs: list[tuple[str, str]] = []
    for truth in ground_truth:
        samples = [
            row
            for row in diagnostics
            if truth["start_seconds"] <= float(row["timestamp_seconds"]) < truth["end_seconds"]
            and _diagnostic_matches_label(row, truth["worker_label"])
        ]
        for sample in samples:
            actual = _validation_activity(sample.get("final_activity"))
            expected = truth["expected_activity"]
            if expected == "WORKING" and actual in {
                "SERVING_CUSTOMER",
                "FETCHING_MEDICINE",
                "SHELF_WORK",
                "POS_WORK",
                "WORKING",
            }:
                actual = "WORKING"
            pairs.append((expected, actual))

    labels = sorted(SUPPORTED_GROUND_TRUTH | {value for pair in pairs for value in pair})
    matrix = {
        expected: {actual: 0 for actual in labels}
        for expected in labels
    }
    for expected, actual in pairs:
        matrix[expected][actual] += 1
    per_class: dict[str, dict[str, float | int]] = {}
    for label in labels:
        true_positive = matrix[label][label]
        false_positive = sum(matrix[expected][label] for expected in labels if expected != label)
        false_negative = sum(matrix[label][actual] for actual in labels if actual != label)
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {
            "support": sum(matrix[label].values()),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    truth_idle = [row for row in ground_truth if row["expected_activity"] == "IDLE"]
    predicted_idle = [row for row in events if row["activity"] == "IDLE"]
    start_errors: list[float] = []
    end_errors: list[float] = []
    matched_predictions: set[str] = set()
    missed_idle = 0
    for truth in truth_idle:
        candidates = []
        for event in predicted_idle:
            label_match = not truth["worker_label"] or truth["worker_label"].casefold() in {
                str(event.get("worker_label") or "").casefold(),
                str(event.get("worker_session_id") or "").casefold(),
            }
            overlap = max(
                0.0,
                min(truth["end_seconds"], event["end_seconds"])
                - max(truth["start_seconds"], event["start_seconds"]),
            )
            if label_match and overlap > 0:
                candidates.append((overlap, event))
        if not candidates:
            missed_idle += 1
            continue
        event = max(candidates, key=lambda item: item[0])[1]
        matched_predictions.add(event["event_id"])
        start_errors.append(event["start_seconds"] - truth["start_seconds"])
        end_errors.append(event["end_seconds"] - truth["end_seconds"])

    total_truth_idle = sum(row["end_seconds"] - row["start_seconds"] for row in truth_idle)
    total_predicted_idle = sum(float(row["duration_seconds"]) for row in predicted_idle)
    total_samples = len(pairs)
    unknown_samples = sum(actual == "UNKNOWN" for _, actual in pairs)
    coverage = (total_samples - unknown_samples) / total_samples if total_samples else 0.0
    return {
        "sample_count": total_samples,
        "confusion_matrix": matrix,
        "per_class": per_class,
        "idle_precision": per_class["IDLE"]["precision"],
        "idle_recall": per_class["IDLE"]["recall"],
        "idle_f1": per_class["IDLE"]["f1"],
        "mean_idle_start_error_seconds": round(statistics.fmean(start_errors), 3) if start_errors else None,
        "mean_idle_end_error_seconds": round(statistics.fmean(end_errors), 3) if end_errors else None,
        "total_idle_duration_error_seconds": round(total_predicted_idle - total_truth_idle, 3),
        "false_idle_count": sum(event["event_id"] not in matched_predictions for event in predicted_idle),
        "missed_idle_count": missed_idle,
        "unknown_percentage": round(100 * unknown_samples / total_samples, 2) if total_samples else 0.0,
        "reliable_classification_coverage": round(coverage, 4),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def customer_rows(
    analyzer: OfflineAnalyzer, end_time: datetime
) -> list[dict[str, Any]]:
    sessions = list(analyzer.customers.completed_sessions) + list(analyzer.customers.active.values())
    unique = {session.service_session_id: session for session in sessions}
    rows: list[dict[str, Any]] = []
    for session in sorted(unique.values(), key=lambda item: item.waiting_started_at):
        service_seconds = session.service_seconds
        if service_seconds is None and session.service_started_at:
            service_seconds = max(0.0, (end_time - session.service_started_at).total_seconds())
        waiting_seconds = session.waiting_seconds
        if waiting_seconds is None:
            waiting_seconds = max(0.0, (end_time - session.waiting_started_at).total_seconds())
        rows.append(
            {
                "service_session_id": session.service_session_id,
                "camera_id": session.camera_id,
                "anonymous_customer_track_ids": "|".join(map(str, session.original_track_ids)),
                "arrival_timestamp": session.waiting_started_at.isoformat(),
                "waiting_seconds": round(waiting_seconds, 3),
                "service_started_at": session.service_started_at.isoformat() if session.service_started_at else None,
                "service_completed_at": session.service_completed_at.isoformat() if session.service_completed_at else None,
                "total_service_seconds": round(service_seconds or 0.0, 3),
                "direct_interaction_seconds": round(session.direct_interaction_seconds, 3),
                "medicine_retrieval_seconds": round(session.medicine_retrieval_seconds, 3),
                "transaction_seconds": round(session.transaction_seconds, 3),
                "assigned_worker_session_id": session.worker_session_id,
                "assignment_confidence": round(session.assignment_confidence, 4),
                "current_phase": session.current_phase,
                "outcome": session.outcome,
                "trust_classification": customer_trust_classification(session),
                "review_status": session.review_status,
            }
        )
    return rows


def write_manager_html(
    path: Path,
    result: dict[str, Any],
    events: list[dict[str, Any]],
    customers: list[dict[str, Any]],
) -> None:
    activities = result["summary"]["activity_seconds"]
    work_seconds = sum(
        activities.get(name, 0.0)
        for name in {
            "SERVING_CUSTOMER",
            "FETCHING_MEDICINE",
            "SHELF_WORK",
            "CASHIER_WORK",
            "COMPUTER_POS_WORK",
            "OTHER_WORK",
        }
    )
    idle_events = [event for event in events if event["activity"] == "IDLE"]
    idle_durations = [float(event["duration_seconds"]) for event in idle_events]
    idle_seconds = sum(idle_durations)
    phone_seconds = activities.get("ON_PHONE", 0.0)
    possible_phone_seconds = activities.get("POSSIBLE_PHONE", 0.0)
    unknown_seconds = activities.get("UNKNOWN", 0.0)
    reliable_total = work_seconds + idle_seconds + phone_seconds
    observed_total = reliable_total + possible_phone_seconds + unknown_seconds
    trusted = sum(row["trust_classification"] == "trusted_completed" for row in customers)
    review = sum(row["trust_classification"] == "completed_needs_review" for row in customers)
    active = sum(row["trust_classification"] == "active" for row in customers)
    unknown_events = [event for event in events if event["activity"] == "UNKNOWN"]
    reason_coverage = (
        sum(bool(event.get("unknown_reason")) for event in unknown_events) / len(unknown_events)
        if unknown_events
        else 1.0
    )

    def metric(label: str, value: str) -> str:
        return f'<div class="metric"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>'

    metrics = "".join(
        [
            metric("Cameras processed", "1"),
            metric("Anonymous worker sessions", str(result["summary"]["anonymous_worker_sessions"])),
            metric("Trusted completed services", str(trusted)),
            metric("Completed services requiring review", str(review)),
            metric("Currently waiting customers", str(active)),
            metric("Confirmed work", format_seconds(work_seconds)),
            metric("Confirmed idle", format_seconds(idle_seconds)),
            metric("Idle event count", str(len(idle_events))),
            metric("Average idle interval", format_seconds(statistics.fmean(idle_durations) if idle_durations else 0)),
            metric("Median idle interval", format_seconds(statistics.median(idle_durations) if idle_durations else 0)),
            metric("Longest idle interval", format_seconds(max(idle_durations, default=0))),
            metric("Confirmed phone", format_seconds(phone_seconds)),
            metric("Possible phone", format_seconds(possible_phone_seconds)),
            metric("Unknown", format_seconds(unknown_seconds)),
            metric("Reliable classification coverage", f"{(100 * reliable_total / observed_total if observed_total else 0):.1f}%"),
            metric("UNKNOWN intervals with reason", f"{100 * reason_coverage:.1f}%"),
        ]
    )
    worker_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('worker_label') or row['entity_id']))}</td>"
        f"<td>{html.escape(', '.join(map(str, row['track_ids'])))}</td>"
        f"<td>{format_seconds(row['observed_seconds'])}</td>"
        f"<td>{html.escape(str(max(row['activities'], key=row['activities'].get) if row['activities'] else 'None'))}</td>"
        "</tr>"
        for row in result["summary"]["tracks"]
        if row.get("worker_session_id")
    ) or '<tr><td colspan="4">No trusted worker session was observed.</td></tr>'
    idle_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(event.get('worker_label') or event.get('worker_session_id')))}</td>"
        f"<td>{format_seconds(event['start_seconds'])}</td>"
        f"<td>{format_seconds(event['end_seconds'])}</td>"
        f"<td>{format_seconds(event['duration_seconds'])}</td>"
        f"<td>{html.escape(str(event.get('evidence_quality') or 'Unknown'))}</td>"
        f"<td>{html.escape(str(event.get('ending_reason') or 'Unknown'))}</td>"
        "</tr>"
        for event in idle_events
    ) or '<tr><td colspan="6">No confirmed idle interval was recorded.</td></tr>'
    customer_table = "".join(
        "<tr>"
        f"<td>{html.escape(row['service_session_id'])}</td>"
        f"<td>{format_seconds(row['waiting_seconds'])}</td>"
        f"<td>{format_seconds(row['total_service_seconds'])}</td>"
        f"<td>{format_seconds(row['medicine_retrieval_seconds'])}</td>"
        f"<td>{html.escape(str(row.get('assigned_worker_session_id') or 'Unassigned'))}</td>"
        f"<td>{html.escape(row['outcome'])}</td>"
        f"<td>{html.escape(row['trust_classification'])}</td>"
        "</tr>"
        for row in customers
    ) or '<tr><td colspan="7">No customer journey was observed.</td></tr>'
    evaluation = result.get("ground_truth_evaluation")
    evaluation_html = (
        f"<h2>Ground-truth validation</h2><pre>{html.escape(json.dumps(evaluation, indent=2))}</pre>"
        if evaluation
        else "<h2>Ground-truth validation</h2><p>No ground-truth CSV was supplied.</p>"
    )
    document = f"""<!doctype html><html><head><meta charset="utf-8"><title>Offline pharmacy validation</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:32px;color:#17332b;background:#f7faf8}}h1,h2{{color:#0c6b50}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}}.metric{{background:white;border:1px solid #dbe7e1;border-radius:9px;padding:12px}}.metric span{{display:block;color:#52665f;font-size:13px}}.metric strong{{font-size:20px}}table{{width:100%;border-collapse:collapse;background:white}}th,td{{padding:8px;border:1px solid #dbe7e1;text-align:left}}th{{background:#e9f5f0}}.warning{{background:#fff7df;border-left:5px solid #d29b20;padding:12px}}pre{{white-space:pre-wrap;background:white;padding:12px}}</style></head><body>
<h1>Pharmacy Worker Monitor V2 — offline validation</h1><p>Input: {html.escape(result['input_video'])}</p><div class="grid">{metrics}</div>
<div class="warning"><p><b>Evidence limits:</b> UNKNOWN does not mean inactive. Possible phone and possible idle require review. Anonymous appearance matching is not confirmed identity. CCTV evidence is not payroll or disciplinary proof.</p></div>
<h2>Anonymous worker summary</h2><table><tr><th>Worker</th><th>Raw tracks</th><th>Observed</th><th>Dominant activity</th></tr>{worker_rows}</table>
<h2>Confirmed idle timeline</h2><table><tr><th>Worker</th><th>Start</th><th>End</th><th>Duration</th><th>Evidence</th><th>Ending reason</th></tr>{idle_rows}</table>
<h2>Customer journeys</h2><table><tr><th>Session</th><th>Wait</th><th>Total service</th><th>Medicine retrieval</th><th>Worker</th><th>Outcome</th><th>Trust</th></tr>{customer_table}</table>{evaluation_html}</body></html>"""
    path.write_text(document, encoding="utf-8")


def draw_zones(frame, zones: list[dict[str, Any]]) -> None:
    import cv2
    import numpy as np

    height, width = frame.shape[:2]
    overlay = frame.copy()
    for zone in zones:
        points = np.array(
            [
                [int(point[0] * width), int(point[1] * height)]
                for point in zone["normalized_points"]
            ],
            dtype=np.int32,
        )
        if len(points) < 3:
            continue
        color = ZONE_COLORS.get(zone["zone_type"], (120, 120, 120))
        cv2.fillPoly(overlay, [points], color)
        cv2.polylines(frame, [points], True, color, 2, cv2.LINE_AA)
        label = zone.get("display_name") or humanize(zone["zone_type"])
        cv2.putText(
            frame,
            label,
            tuple(points[0]),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            color,
            2,
            cv2.LINE_AA,
        )
    cv2.addWeighted(overlay, 0.12, frame, 0.88, 0, frame)


def _draw_label(frame, lines: list[str], x: int, y: int, color: tuple[int, int, int]) -> None:
    import cv2

    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.5
    thickness = 1
    line_height = 19
    widths = [cv2.getTextSize(line, font, scale, thickness)[0][0] for line in lines]
    box_width = max(widths, default=100) + 12
    box_height = len(lines) * line_height + 8
    y = max(box_height + 2, y)
    right = min(frame.shape[1] - 1, x + box_width)
    cv2.rectangle(frame, (x, y - box_height), (right, y), color, -1)
    for index, line in enumerate(lines):
        cv2.putText(
            frame,
            line,
            (x + 6, y - box_height + 17 + index * line_height),
            font,
            scale,
            (255, 255, 255),
            thickness,
            cv2.LINE_AA,
        )


def annotate_frame(
    frame,
    observations: list[dict[str, Any]],
    zones: list[dict[str, Any]],
    timestamp: float,
    analysis_every: int,
) -> Any:
    import cv2

    annotated = frame.copy()
    draw_zones(annotated, zones)
    for observation in observations:
        left, top, right, bottom = _clip_box(
            observation["bbox"], annotated.shape[1], annotated.shape[0]
        )
        status = observation["evidence_status"]
        color = STATUS_COLORS.get(status, (150, 150, 150))
        cv2.rectangle(annotated, (left, top), (right, bottom), color, 3)
        identity = observation.get("worker_label") or f"Track {observation['track_id']}"
        if observation.get("worker_session_id"):
            identity = f"{identity} / T{observation['track_id']}"
        _draw_label(
            annotated,
            [
                f"{identity} {humanize(observation['role'])} | {status_text(status)}"
            ],
            left,
            top,
            color,
        )
        for phone in observation.get("phone_boxes", []):
            px1, py1, px2, py2 = _clip_box(
                phone["bbox"], annotated.shape[1], annotated.shape[0]
            )
            cv2.rectangle(annotated, (px1, py1), (px2, py2), (20, 20, 240), 2)
            cv2.putText(
                annotated,
                f"PHONE {phone['confidence']:.3f}",
                (px1, max(15, py1 - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (20, 20, 240),
                2,
                cv2.LINE_AA,
            )

    counts = Counter(item["evidence_status"] for item in observations)
    cv2.rectangle(annotated, (0, 0), (annotated.shape[1], 66), (20, 25, 25), -1)
    cv2.putText(
        annotated,
        f"Backend video test  |  {format_seconds(timestamp)}  |  People: {len(observations)}  |  Analyze every {analysis_every} frame(s)",
        (16, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (245, 245, 245),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        annotated,
        "Work: {}  Idle: {}  Review: {}  Customer: {}  Break: {}  Insufficient: {}".format(
            counts["WORK_OBSERVED"],
            counts["CONFIRMED_IDLE"],
            counts["REVIEW_NEEDED"],
            counts["CUSTOMER_OBSERVED"],
            counts["APPROVED_BREAK"],
            counts["INSUFFICIENT_EVIDENCE"],
        ),
        (16, 52),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (220, 230, 230),
        1,
        cv2.LINE_AA,
    )

    if observations:
        panel_width = min(370, max(300, annotated.shape[1] // 3))
        panel_x = annotated.shape[1] - panel_width - 10
        panel_top = 76
        row_height = 154
        max_rows = max(1, (annotated.shape[0] - panel_top - 10) // row_height)
        shown = observations[:max_rows]
        panel_bottom = panel_top + len(shown) * row_height
        overlay = annotated.copy()
        cv2.rectangle(
            overlay,
            (panel_x, panel_top),
            (annotated.shape[1] - 10, panel_bottom),
            (18, 23, 23),
            -1,
        )
        cv2.addWeighted(overlay, 0.78, annotated, 0.22, 0, annotated)
        for index, observation in enumerate(shown):
            row_top = panel_top + index * row_height
            status = observation["evidence_status"]
            color = STATUS_COLORS.get(status, (150, 150, 150))
            cv2.rectangle(
                annotated,
                (panel_x, row_top),
                (panel_x + 6, row_top + row_height - 1),
                color,
                -1,
            )
            zone = (
                humanize(observation.get("zone"))
                if observation.get("zone")
                else "No zone"
            )
            detail_lines = [
                f"{observation.get('worker_label') or 'Track ' + str(observation['track_id'])} | {humanize(observation['role'])} | {observation['confidence']:.2f}",
                f"{status_text(status)} | {humanize(observation['activity'])}",
                f"Candidate: {humanize(observation.get('candidate_activity'))} {observation.get('candidate_duration_seconds', 0):.1f}s",
                f"Idle: {observation.get('idle_candidate_seconds', 0):.1f}/{observation.get('idle_confirmation_seconds', settings.idle_confirm_seconds):.1f}s | Q={observation.get('evidence_quality') or '-'}",
                f"Motion B/W/E: {observation.get('body_motion', 0):.3f}/{observation.get('wrist_motion', 0):.3f}/{observation.get('elbow_motion', 0):.3f}",
                f"{zone} | Pose {observation.get('pose_status') or '-'} | Track {observation.get('track_age_seconds', 0):.1f}s",
                f"Phone: {observation['phone_evidence']} | Service: {humanize(observation.get('customer_service_phase'))}",
            ]
            for line_index, line in enumerate(detail_lines):
                cv2.putText(
                    annotated,
                    line,
                    (panel_x + 14, row_top + 19 + line_index * 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.42,
                    (245, 245, 245) if line_index != 1 else color,
                    1 if line_index != 1 else 2,
                    cv2.LINE_AA,
                )
    return annotated


def run_video_test(
    video_path: Path,
    output_path: Path,
    json_path: Path,
    *,
    camera_id: int | None,
    analysis_every: int,
    max_seconds: float | None,
    enable_pose: bool,
    enable_phone: bool,
    dataset_dir: Path | None = None,
    dataset_every: int = 25,
    dataset_max_per_worker: int = 100,
    person_model_path: Path | None = None,
    labcoat_model_path: Path | None = None,
    preview: bool = False,
    zones_path: Path | None = None,
    ground_truth_path: Path | None = None,
) -> dict[str, Any]:
    import cv2

    video_path = video_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    json_path = json_path.expanduser().resolve()
    if not video_path.is_file():
        raise FileNotFoundError(f"Input video does not exist: {video_path}")
    if output_path == video_path:
        raise ValueError("Output path must be different from the input video path.")
    if person_model_path is not None:
        person_model_path = person_model_path.expanduser().resolve()
        if not person_model_path.is_file():
            raise FileNotFoundError(
                f"Person/worker model does not exist: {person_model_path}"
            )
        settings.person_model_path = str(person_model_path)
        model_registry.models.pop("person", None)
        model_registry.metadata.pop("person", None)
    if labcoat_model_path is not None:
        labcoat_model_path = labcoat_model_path.expanduser().resolve()
        if not labcoat_model_path.is_file():
            raise FileNotFoundError(
                f"Lab-coat verifier model does not exist: {labcoat_model_path}"
            )
        settings.lab_coat_verifier_enabled = True
        settings.lab_coat_verifier_model_path = str(labcoat_model_path)
        model_registry.models.pop("lab_coat_verifier", None)
        model_registry.metadata.pop("lab_coat_verifier", None)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    artifacts = default_artifact_paths(output_path)

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"OpenCV could not open the input video: {video_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    if not fps or fps <= 0:
        fps = 25.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    source_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    requested_frames = (
        min(source_frames, max(1, int(max_seconds * fps)))
        if max_seconds is not None and source_frames > 0
        else max(1, int(max_seconds * fps))
        if max_seconds is not None
        else source_frames
    )
    writer = cv2.VideoWriter(
        str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError(f"OpenCV could not create the output video: {output_path}")

    zones = (
        load_zones_json(zones_path)
        if zones_path is not None
        else load_camera_zones(camera_id)
    )
    stable_source = f"{video_path}|camera={camera_id or 0}|zones={json.dumps(zones, sort_keys=True)}"
    session_id = f"{video_path.stem}-{hashlib.sha256(stable_source.encode('utf-8')).hexdigest()[:12]}"
    analyzer = OfflineAnalyzer(
        zones,
        enable_pose=enable_pose,
        enable_phone=enable_phone,
        camera_id=camera_id,
        session_id=session_id,
    )
    print("Loading the backend AI models...")
    model_status = analyzer.load_models()
    print(
        "Models: "
        + ", ".join(f"{name}={'ready' if ready else 'unavailable'}" for name, ready in model_status.items())
    )
    if camera_id is not None:
        print(f"Loaded {len(zones)} enabled zone(s) for camera {camera_id}.")
    else:
        print("No camera ID supplied; worker/customer and work evidence may be limited without zones.")

    collector = SummaryCollector()
    dataset = (
        OfflineWorkerDatasetExporter(
            dataset_dir,
            session_id,
            every_frames=dataset_every,
            max_per_worker=dataset_max_per_worker,
        )
        if dataset_dir is not None
        else None
    )
    latest_observations: list[dict[str, Any]] = []
    analyzed_frames = 0
    written_frames = 0
    started = time.monotonic()
    preview_started = started
    preview_active = bool(preview)
    stopped_by_user = False
    preview_window = "Pharmacy Worker Monitor V2 - Q or Esc to stop"
    next_progress = 0
    try:
        frame_number = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            timestamp = frame_number / fps
            if max_seconds is not None and timestamp >= max_seconds:
                break
            if frame_number % analysis_every == 0:
                latest_observations = analyzer.analyze(frame, frame_number, timestamp)
                collector.capture_diagnostics(latest_observations, timestamp)
                if dataset is not None:
                    dataset.export(
                        frame,
                        frame_number,
                        timestamp,
                        latest_observations,
                    )
                analyzed_frames += 1
            annotated = annotate_frame(
                frame, latest_observations, zones, timestamp, analysis_every
            )
            writer.write(annotated)
            collector.update(latest_observations, timestamp, 1.0 / fps)
            written_frames += 1
            frame_number += 1

            if preview_active:
                try:
                    preview_frame = annotated
                    scale = min(
                        1.0,
                        1280 / max(1, annotated.shape[1]),
                        820 / max(1, annotated.shape[0]),
                    )
                    if scale < 1.0:
                        preview_frame = cv2.resize(
                            annotated,
                            (
                                max(1, int(annotated.shape[1] * scale)),
                                max(1, int(annotated.shape[0] * scale)),
                            ),
                            interpolation=cv2.INTER_AREA,
                        )
                    cv2.imshow(preview_window, preview_frame)
                    remaining = timestamp - (time.monotonic() - preview_started)
                    delay_ms = max(1, min(100, int(max(0.0, remaining) * 1000)))
                    key = cv2.waitKey(delay_ms) & 0xFF
                    if key in (ord("q"), ord("Q"), 27):
                        stopped_by_user = True
                        print("Preview stopped by the user; finalizing current outputs...")
                        break
                except cv2.error as exc:
                    preview_active = False
                    print(
                        "WARNING: OpenCV preview is unavailable; continuing without "
                        f"a window ({exc}).",
                        flush=True,
                    )

            if requested_frames > 0:
                progress = int((written_frames / requested_frames) * 100)
                if progress >= next_progress:
                    elapsed = time.monotonic() - started
                    print(
                        f"Progress {min(progress, 100):3d}% | frame {written_frames}/{requested_frames} | elapsed {format_seconds(elapsed)}",
                        flush=True,
                    )
                    next_progress += 10
    finally:
        capture.release()
        writer.release()
        if preview:
            try:
                cv2.destroyAllWindows()
            except cv2.error:
                pass

    elapsed = time.monotonic() - started
    duration_seconds = round(written_frames / fps, 3)
    collector.finalize(duration_seconds)
    end_time = analyzer._time_origin + timedelta(seconds=duration_seconds)
    customers = customer_rows(analyzer, end_time)
    ground_truth = (
        load_ground_truth(ground_truth_path) if ground_truth_path is not None else None
    )
    evaluation = (
        evaluate_ground_truth(ground_truth, collector.diagnostics, collector.events)
        if ground_truth is not None
        else None
    )
    result = {
        "tool": "Pharmacy Worker Monitor V2 offline backend video test",
        "input_video": str(video_path),
        "output_video": str(output_path),
        "summary_json": str(json_path),
        "event_csv": str(artifacts["events_csv"]),
        "diagnostics_csv": str(artifacts["diagnostics_csv"]),
        "customer_journey_csv": str(artifacts["customers_csv"]),
        "manager_html": str(artifacts["manager_html"]),
        "camera_id": camera_id,
        "read_only_zone_load": camera_id is not None,
        "video": {
            "width": width,
            "height": height,
            "fps": round(fps, 4),
            "source_frames": source_frames,
            "written_frames": written_frames,
            "analyzed_frames": analyzed_frames,
            "duration_seconds": duration_seconds,
            "analysis_every_n_frames": analysis_every,
            "wall_time_seconds": round(elapsed, 3),
            "audio_copied": False,
            "stopped_by_user": stopped_by_user,
        },
        "preview": {
            "requested": bool(preview),
            "displayed": bool(preview and preview_active),
            "controls": "Press Q or Esc in the preview window to stop safely.",
        },
        "models": model_status,
        "model_metadata": model_registry.status(),
        "detection_diagnostics": dict(sorted(analyzer.detection_diagnostics.items())),
        "zones": zones,
        "semantics": {
            "WORK_OBSERVED": "Positive observed work evidence; not a complete productivity judgment.",
            "REVIEW_NEEDED": "Possible phone or idle evidence that needs human review.",
            "CUSTOMER_OBSERVED": "A customer was observed; this is not a work-status label.",
            "INSUFFICIENT_EVIDENCE": "The system does not have enough evidence for a stronger label.",
            "APPROVED_BREAK": "A worker was observed in the configured break area.",
        },
        "identity": {
            "scope": "anonymous, camera-local, and limited to this video run",
            "short_loss_recovery": "velocity prediction plus conservative clothing/spatial stitching",
            "session_stitches": analyzer.session_stitches,
            "limitations": (
                "Worker labels are not real employee identities. Clothing similarity can "
                "confuse workers in the same uniform, and there is no face recognition or "
                "cross-video identity matching in this test."
            ),
        },
        "dataset_export": dataset.summary() if dataset is not None else None,
        "summary": collector.as_dict(),
        "ground_truth_csv": str(ground_truth_path.resolve()) if ground_truth_path else None,
        "ground_truth_evaluation": evaluation,
        "repeatability": {
            "deterministic_session_id": session_id,
            "signature": hashlib.sha256(
                json.dumps(
                    {
                        "session_id": session_id,
                        "video": {
                            "frames": written_frames,
                            "fps": round(fps, 4),
                            "analysis_every": analysis_every,
                        },
                        "summary": collector.as_dict(),
                        "events": collector.events,
                        "customers": customers,
                        "evaluation": evaluation,
                    },
                    sort_keys=True,
                    default=str,
                ).encode("utf-8")
            ).hexdigest(),
        },
    }
    event_fields = [
        "event_id", "worker_session_id", "worker_label", "raw_track_ids",
        "activity", "start_seconds", "end_seconds", "duration_seconds",
        "confirmation_seconds", "evidence_quality", "unknown_reason", "zone",
        "average_body_motion", "average_wrist_motion", "average_elbow_motion",
        "ending_reason", "transition_type", "end_transition_type", "review_status",
    ]
    _write_csv(
        artifacts["events_csv"],
        [
            {
                **event,
                "raw_track_ids": "|".join(map(str, event["raw_track_ids"])),
            }
            for event in collector.events
        ],
        event_fields,
    )
    diagnostic_fields = list(collector.diagnostics[0]) if collector.diagnostics else [
        "timestamp_seconds", "worker_session_id", "raw_track_id", "role",
        "final_activity", "candidate_activity", "unknown_reason",
    ]
    _write_csv(artifacts["diagnostics_csv"], collector.diagnostics, diagnostic_fields)
    customer_fields = list(customers[0]) if customers else [
        "service_session_id", "camera_id", "anonymous_customer_track_ids",
        "arrival_timestamp", "waiting_seconds", "service_started_at",
        "service_completed_at", "total_service_seconds", "direct_interaction_seconds",
        "medicine_retrieval_seconds", "transaction_seconds",
        "assigned_worker_session_id", "assignment_confidence", "current_phase",
        "outcome", "trust_classification", "review_status",
    ]
    _write_csv(artifacts["customers_csv"], customers, customer_fields)
    write_manager_html(artifacts["manager_html"], result, collector.events, customers)
    json_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Pharmacy Worker Monitor backend against a local video without "
            "starting the API or UI, then write video, CSV, JSON, and HTML evidence."
        )
    )
    parser.add_argument("video", nargs="?", help="Input video path")
    parser.add_argument("--output", help="Annotated MP4 path")
    parser.add_argument("--json-output", help="JSON evidence summary path")
    parser.add_argument(
        "--camera-id",
        type=int,
        help="Read this camera's saved zones (read-only; no database changes)",
    )
    parser.add_argument(
        "--zones-json",
        help="Optional normalized zone configuration JSON; overrides saved camera zones",
    )
    parser.add_argument(
        "--ground-truth",
        help=(
            "Optional ground-truth CSV with camera_id, worker_label, start_seconds, "
            "end_seconds, expected_activity, and notes"
        ),
    )
    parser.add_argument(
        "--analysis-every",
        type=_positive_int,
        default=1,
        help="Analyze every Nth frame while writing every frame (default: 1)",
    )
    parser.add_argument(
        "--max-seconds", type=float, help="Only process the first N seconds"
    )
    parser.add_argument("--no-pose", action="store_true", help="Disable pose inference")
    parser.add_argument("--no-phone", action="store_true", help="Disable phone inference")
    parser.add_argument(
        "--dataset-dir",
        help=(
            "Optional directory for worker-only identity crops and a review CSV; "
            "customers are never exported"
        ),
    )
    parser.add_argument(
        "--dataset-every",
        type=_positive_int,
        default=25,
        help="Save an eligible worker crop every N source frames (default: 25)",
    )
    parser.add_argument(
        "--dataset-max-per-worker",
        type=_positive_int,
        default=100,
        help="Maximum exported crops per anonymous worker session (default: 100)",
    )
    parser.add_argument("--person-model", help="Override the person/worker YOLO model")
    parser.add_argument("--labcoat-model", help="Override the lab-coat verifier model")
    parser.add_argument(
        "--codea-models",
        action="store_true",
        help=(
            "Use E:/model/employee_customer1.pt and E:/model/labcoat.pt from the "
            "Codea experiment"
        ),
    )
    parser.add_argument(
        "--preview",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Display the annotated video while processing (Q/Esc stops safely)",
    )
    return parser


def _strip_wrapping_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def interactive_values(args: argparse.Namespace) -> argparse.Namespace:
    if args.video:
        return args
    print("Pharmacy Worker Monitor V2 - offline backend video test")
    args.video = _strip_wrapping_quotes(input("Video path: "))
    output = _strip_wrapping_quotes(
        input("Output MP4 path (press Enter for automatic name): ")
    )
    if output:
        args.output = output
    camera = input("Camera ID for saved zones (press Enter for none): ").strip()
    if camera:
        args.camera_id = int(camera)
    stride = input(
        "Analyze every N frames (1 = best detail, 5 = faster; press Enter for 1): "
    ).strip()
    if stride:
        args.analysis_every = _positive_int(stride)
    maximum = input(
        "Maximum seconds to process (press Enter for the whole video): "
    ).strip()
    if maximum:
        args.max_seconds = float(maximum)
    codea = input(
        "Use the Codea employee + lab-coat model profile from E:\\model? [y/N]: "
    ).strip()
    if codea.lower() in {"y", "yes"}:
        args.codea_models = True
    export = input(
        "Export worker-only tracking crops for human review? [y/N]: "
    ).strip()
    if export.lower() in {"y", "yes"}:
        destination = _strip_wrapping_quotes(
            input(
                "Dataset directory (press Enter for backend/offline_datasets): "
            )
        )
        args.dataset_dir = destination or "offline_datasets"
    return args


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = interactive_values(parser.parse_args(argv))
    if not args.video:
        parser.error("an input video path is required")
    if args.max_seconds is not None and args.max_seconds <= 0:
        parser.error("--max-seconds must be greater than zero")
    video_path = Path(_strip_wrapping_quotes(args.video))
    output_path = (
        Path(_strip_wrapping_quotes(args.output))
        if args.output
        else default_output_path(video_path)
    )
    json_path = (
        Path(_strip_wrapping_quotes(args.json_output))
        if args.json_output
        else default_json_path(output_path)
    )
    person_model = args.person_model
    labcoat_model = args.labcoat_model
    if args.codea_models:
        person_model = person_model or "E:/model/employee_customer1.pt"
        labcoat_model = labcoat_model or "E:/model/labcoat.pt"
    try:
        result = run_video_test(
            video_path,
            output_path,
            json_path,
            camera_id=args.camera_id,
            analysis_every=args.analysis_every,
            max_seconds=args.max_seconds,
            enable_pose=not args.no_pose,
            enable_phone=not args.no_phone,
            dataset_dir=(
                Path(_strip_wrapping_quotes(args.dataset_dir))
                if args.dataset_dir
                else None
            ),
            dataset_every=args.dataset_every,
            dataset_max_per_worker=args.dataset_max_per_worker,
            person_model_path=(
                Path(_strip_wrapping_quotes(person_model)) if person_model else None
            ),
            labcoat_model_path=(
                Path(_strip_wrapping_quotes(labcoat_model)) if labcoat_model else None
            ),
            preview=args.preview,
            zones_path=(
                Path(_strip_wrapping_quotes(args.zones_json))
                if args.zones_json
                else None
            ),
            ground_truth_path=(
                Path(_strip_wrapping_quotes(args.ground_truth))
                if args.ground_truth
                else None
            ),
        )
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print("\nCompleted successfully.")
    print(f"Annotated video: {result['output_video']}")
    print(f"JSON summary:    {result['summary_json']}")
    if result["dataset_export"] is not None:
        print(
            "Worker dataset:  "
            f"{result['dataset_export']['session_directory']} "
            f"({result['dataset_export']['saved_worker_crops']} crop(s))"
        )
    print(
        "Reminder: worker labels are anonymous video-local sessions, and status labels "
        "describe observed evidence, not a final employment judgment."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
