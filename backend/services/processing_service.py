from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from datetime import UTC, datetime

from sqlalchemy import select

from config import settings
from database import SessionLocal
from db_models.camera_session import CameraSession
from db_models.camera_debug import CameraDebugSetting
from db_models.customer_session import CustomerSession
from db_models.customer_service import (
    CustomerServicePhase,
    WorkerCustomerAssignment,
    WorkerSessionStitch,
)
from db_models.health_event import HealthEvent
from db_models.worker_session import WorkerSession
from db_models.worker_snapshot import WorkerSnapshot
from db_models.zone import CameraZone
from services.activity_engine import ActivityEngine, PhoneTemporalHistory
from services.customer_analytics import (
    ACTIVE_SERVICE_PHASES,
    MEDICINE_RETRIEVAL_PHASES,
    CustomerAnalyticsService,
    CustomerObservation,
    WorkerObservation,
    customer_trust_classification,
)
from services.debug_overlay_service import DebugOverlayRenderer
from services.event_service import EventContext, EventService
from services.evidence_clip_service import EvidenceClipService
from services.evidence_service import (
    ActivityEvidence,
    UnknownReason,
    assess_evidence_quality,
    evidence_status,
    normalize_unknown_reason,
)
from services.frame_buffer import RollingFrameBuffer
from services.global_identity_service import global_worker_identity_service
from services.local_session_stitcher import LocalSessionStitcher
from services.person_detector import PersonDetector
from services.phone_association import associate_phones
from services.phone_detector import PhoneDetector, PhoneSearchScheduler
from services.pose_service import PoseService, pose_inference_due
from services.role_classifier import TemporalRoleClassifier
from services.session_manifest_service import write_manifest
from services.snapshot_service import SnapshotService
from services.source_parser import parse_source
from services.state_machine import TemporalStateMachine
from services.tracker import Detection, StableTracker
from services.worker_session_service import WorkerSessionService
from services.work_motion_service import TemporalWorkMotion
from services.zone_service import ZONE_PRIORITY, TemporalZoneHistory, memberships
from utilities.geometry import center, distance, foot_point
from utilities.time_utils import seconds_between, utc_now

logger = logging.getLogger(__name__)


class ProcessingService:
    """Consumes only the newest captured frame and owns track-keyed temporal state."""

    def __init__(self, camera_id: int, source: str, capture) -> None:
        self.camera_id = camera_id
        self.source_type = parse_source(source).kind
        self.capture = capture
        self.detector = PersonDetector()
        self.tracker = StableTracker(id_namespace=camera_id)
        self.roles = TemporalRoleClassifier()
        self.worker_sessions = WorkerSessionService()
        self.customers = CustomerAnalyticsService()
        self.poses = PoseService()
        self.phone_detector = PhoneDetector()
        self.phone_search = PhoneSearchScheduler()
        self.phone_history = PhoneTemporalHistory()
        self.zone_history = TemporalZoneHistory()
        self.activity_engine = ActivityEngine()
        self.state_machine = TemporalStateMachine()
        self.work_motion = TemporalWorkMotion()
        self.session_stitcher = LocalSessionStitcher()
        self.debug_renderer = DebugOverlayRenderer()
        self.snapshots = SnapshotService()
        self.evidence_frames = RollingFrameBuffer(seconds=max(12, settings.event_clip_pre_seconds + settings.event_clip_post_seconds + 2))
        self.clip_service = EvidenceClipService()
        self._pending_clips: deque[tuple[float, object]] = deque(maxlen=64)
        self._customer_commands: deque[tuple[str, str]] = deque(maxlen=128)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._live = {
            "people_visible": 0,
            "workers_visible": 0,
            "customer_count": 0,
            "observed_people": [],
            "worker_states": [],
            "customer_diagnostics": [],
            "camera_diagnostics": {},
            "alerts": [],
        }
        self._processing_times: deque[float] = deque(maxlen=60)
        self._view_lock = threading.Lock()
        self._normal_frame = None
        self._debug_frame = None
        self._debug_settings = {
            "enabled": False,
            "show_pose": settings.debug_default_show_pose,
            "show_zones": settings.debug_default_show_zones,
            "show_phone_boxes": settings.debug_default_show_phone_boxes,
            "show_assignments": settings.debug_default_show_assignments,
            "show_performance": settings.debug_default_show_performance,
        }
        self._last_detection_sequence = -1
        self._last_centers: dict[int, tuple[float, float]] = {}
        self._last_moved_at: dict[int, float] = {}
        self._pending_runtime_expiry: dict[int, float] = {}
        self.camera_session_id = f"CS-{datetime.now(UTC):%Y%m%d}-{uuid.uuid4().hex[:8]}"
        self._active_health_event: HealthEvent | None = None
        self._unavailable_seconds = 0.0

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"camera-processing-{self.camera_id}", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout)

    def live(self) -> dict:
        with self._lock:
            return {
                **self._live,
                "observed_people": list(self._live["observed_people"]),
                "worker_states": list(self._live["worker_states"]),
                "customer_diagnostics": list(
                    self._live.get("customer_diagnostics", [])
                ),
                "camera_diagnostics": dict(
                    self._live.get("camera_diagnostics", {})
                ),
                "alerts": list(self._live["alerts"]),
            }

    def activity_diagnostics(self) -> dict:
        """Return bounded, privacy-safe evidence already computed for this camera."""
        with self._lock:
            return {
                "camera_id": self.camera_id,
                "workers": [dict(value) for value in self._live["worker_states"]],
                "customers": [
                    dict(value)
                    for value in self._live.get("customer_diagnostics", [])
                ],
                "camera": dict(self._live.get("camera_diagnostics", {})),
            }

    def frame(self, view: str = "normal"):
        with self._view_lock:
            use_debug = view == "test" or (
                view == "auto" and self._debug_settings.get("enabled", False)
            )
            selected = self._debug_frame if use_debug else self._normal_frame
            return selected

    def set_debug_settings(self, value: dict) -> None:
        with self._view_lock:
            self._debug_settings.update(
                {key: bool(setting) for key, setting in value.items() if key in self._debug_settings}
            )

    def debug_settings(self) -> dict:
        with self._view_lock:
            return dict(self._debug_settings)

    def request_customer_close(self, session_id: str, outcome: str) -> None:
        with self._lock:
            self._customer_commands.append((session_id, outcome))

    def _load_zones(self, db) -> list[dict]:
        rows = db.scalars(
            select(CameraZone)
            .where(CameraZone.camera_id == self.camera_id, CameraZone.enabled.is_(True))
            .execution_options(populate_existing=True)
        ).all()
        return [{"zone_type": row.zone_type, "normalized_points": [tuple(point) for point in row.normalized_points], "enabled": row.enabled} for row in rows]

    def _run(self) -> None:
        with SessionLocal() as db:
            saved_debug = db.get(CameraDebugSetting, self.camera_id)
            if saved_debug:
                self.set_debug_settings(
                    {
                        "enabled": saved_debug.enabled,
                        "show_pose": saved_debug.show_pose,
                        "show_zones": saved_debug.show_zones,
                        "show_phone_boxes": saved_debug.show_phone_boxes,
                        "show_assignments": saved_debug.show_assignments,
                        "show_performance": saved_debug.show_performance,
                    }
                )
            self._interrupt_orphan_customer_sessions(db)
            camera_session = CameraSession(
                id=self.camera_session_id,
                camera_id=self.camera_id,
                source_type=self.source_type,
                config_json={
                    "face_recognition": False,
                    "face_embeddings": False,
                    "global_anonymous_worker_id": settings.global_worker_id_enabled,
                    "global_worker_id_scope": "calendar_day",
                },
            )
            db.add(camera_session)
            db.commit()
            events = EventService(db)
            zones = self._load_zones(db)
            next_zone_reload = time.monotonic() + settings.zone_reload_seconds
            person_ready = self.detector.load()
            pose_ready = settings.pose_enabled and self.poses.load()
            phone_ready = settings.phone_enabled and self.phone_detector.load()
            self.capture.health.health.person_model_loaded = person_ready
            self.capture.health.health.pose_model_loaded = pose_ready
            self.capture.health.health.phone_model_loaded = phone_ready
            last_sequence = -1
            try:
                while not self._stop.is_set():
                    now_mono = time.monotonic()
                    if now_mono >= next_zone_reload:
                        zones = self._load_zones(db)
                        next_zone_reload = now_mono + settings.zone_reload_seconds
                    packet = self.capture.frames.latest()
                    if packet is None or packet.sequence_id == last_sequence:
                        health_status = self.capture.health.snapshot()["status"]
                        if health_status in {"UNAVAILABLE", "FROZEN", "RECONNECTING"}:
                            self._handle_unavailable(db, events, health_status)
                        self._stop.wait(0.02)
                        continue
                    last_sequence = packet.sequence_id
                    self._close_health_period(db, packet.received_at)
                    started = time.monotonic()
                    try:
                        self._process_packet(db, events, zones, packet, person_ready, pose_ready, phone_ready)
                        db.commit()
                    except Exception as exc:
                        db.rollback()
                        logger.exception("Processing error on camera %s", self.camera_id)
                        self.capture.health.health.last_processing_error = f"{type(exc).__name__}: {exc}"[:200]
                    elapsed = max(0.0001, time.monotonic() - started)
                    self._processing_times.append(elapsed)
                    self.capture.health.health.processing_fps = round(1 / (sum(self._processing_times) / len(self._processing_times)), 2)
            finally:
                now = utc_now()
                events.close_all(now)
                self.customers.interrupt_all(now)
                self._persist_customer_state(db)
                for track_id in list(self.worker_sessions.active):
                    self._close_worker(db, events, track_id, now)
                camera_session.ended_at = now
                camera_session.average_processing_fps = self.capture.health.health.processing_fps
                camera_session.reconnect_count = self.capture.health.health.reconnect_count
                self._close_health_period(db, now)
                camera_session.unavailable_seconds = self._unavailable_seconds
                manifest = write_manifest(self.camera_session_id, {
                    "camera_id": self.camera_id,
                    "source_type": self.source_type,
                    "start_time": camera_session.started_at,
                    "end_time": now,
                    "zone_configuration": zones,
                    "model_status": {
                        "person": person_ready, "pose": pose_ready, "phone": phone_ready,
                    },
                    "processing_fps_summary": camera_session.average_processing_fps,
                    "reconnect_count": camera_session.reconnect_count,
                    "camera_unavailable_time": self._unavailable_seconds,
                    "report_paths": {},
                    "evidence_directory": "evidence",
                    "snapshot_directory": "worker_snapshots",
                })
                camera_session.manifest_path = str(manifest)
                db.commit()

    def _process_packet(self, db, events: EventService, zones: list[dict], packet, person_ready: bool, pose_ready: bool, phone_ready: bool) -> None:
        pipeline_started = time.monotonic()
        now_mono = time.monotonic()
        self._expire_pending_runtime(now_mono)
        now = packet.received_at
        frame = packet.frame
        with self._view_lock:
            self._normal_frame = frame.copy()
        self._apply_customer_commands(now)
        try:
            import cv2
            ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if ok:
                self.evidence_frames.add_jpeg(now_mono, encoded.tobytes())
        except Exception:
            pass
        self._flush_clips(now_mono)
        if not person_ready:
            self._publish([], [], unavailable=True)
            return
        if packet.sequence_id % settings.person_run_every_n_frames != 0:
            return
        person_started = time.monotonic()
        observations = self.detector.detect(frame)
        person_ms = (time.monotonic() - person_started) * 1000
        detections = [Detection(item.bbox, item.confidence, item.class_name) for item in observations]
        tracker_started = time.monotonic()
        tracks, expired = self.tracker.update(detections, now_mono)
        tracker_ms = (time.monotonic() - tracker_started) * 1000
        for track in expired:
            self.session_stitcher.expire(track.track_id)
            self._pending_runtime_expiry[track.track_id] = (
                now_mono
                + min(
                    settings.local_session_stitch_max_gap_seconds,
                    settings.idle_track_gap_grace_seconds,
                )
            )
            self._close_worker(
                db,
                events,
                track.track_id,
                now,
                ending_reason="track_gap",
                preserve_runtime=True,
            )
            self.customers.mark_customer_missing(track.track_id, now)
        height, width = frame.shape[:2]
        classified: list[tuple[object, str, set[str], str | None]] = []
        track_poses: dict[int, object | None] = {}
        track_motion: dict[int, tuple[str, float]] = {}
        track_work_motion: dict[int, object] = {}
        pose_ms = 0.0
        observed_people: list[dict] = []
        interaction_zone_types = {
            "register_interaction",
            "shelf_interaction",
            "medicine_shelf",
            "computer",
            "pos",
        }
        standing_zones = [zone for zone in zones if zone["zone_type"] not in interaction_zone_types]
        interaction_zones = [zone for zone in zones if zone["zone_type"] in interaction_zone_types]
        for track in tracks:
            if not track.directly_observed or not track.confirmed:
                continue
            normalized_foot = (foot_point(track.bbox)[0] / width, foot_point(track.bbox)[1] / height)
            foot_zones, _ = memberships(normalized_foot, standing_zones)
            pose = None
            pose_candidate = bool(
                track.role_hint == "lab_coat"
                or {"employee_area", "cashier", "service_position"} & set(foot_zones)
            )
            if pose_ready and pose_candidate:
                left, top, right, bottom = [max(0, int(value)) for value in track.bbox]
                crop = frame[top:bottom, left:right]
                pose = self.poses.fresh(track.track_id, now_mono)
                if pose_inference_due(
                    packet.sequence_id,
                    settings.pose_run_every_n_frames,
                    pose,
                ):
                    pose_started = time.monotonic()
                    pose = self.poses.infer(track.track_id, packet.sequence_id, track.bbox, crop, now_mono)
                    pose_ms += (time.monotonic() - pose_started) * 1000
            track_poses[track.track_id] = pose
            interaction_hits: set[str] = set()
            if pose and pose.status != "STALE":
                for index in (9, 10):
                    if len(pose.global_keypoints) > index and pose.global_keypoints[index][2] >= settings.pose_keypoint_confidence:
                        wrist = pose.global_keypoints[index]
                        names, _ = memberships((wrist[0] / width, wrist[1] / height), interaction_zones)
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
                track.track_id, pose, track.bbox, now_mono
            )
            track_work_motion[track.track_id] = work_motion
            low_movement = work_motion.low_motion_seconds
            motion = "STATIONARY" if work_motion.low_motion else "RECENT_MOVEMENT"
            track_motion[track.track_id] = (motion, low_movement)
            classified.append((track, role, confirmed_zones, primary))
            role_reasons = []
            if track.role_hint == "lab_coat":
                role_reasons.append("lab coat detected")
            if confirmed_zones:
                role_reasons.append(f"zones: {', '.join(sorted(confirmed_zones))}")
            elif all_zones:
                role_reasons.append(f"candidate zones (confirming): {', '.join(sorted(all_zones))}")
            elif not zones:
                role_reasons.append("no camera zones configured")
            if role == "UNKNOWN":
                role_reasons.append("insufficient evidence for worker/customer role")
                if "shelf_interaction" in all_zones and "employee_area" not in all_zones:
                    role_reasons.append("shelf interaction also needs the person's feet inside employee area")
            observed_people.append({
                "track_id": track.track_id,
                "worker_session_id": None,
                "display_name": f"Person {track.track_id}",
                "role": role,
                "activity": "UNKNOWN",
                "evidence_status": evidence_status(role, "UNKNOWN"),
                "confidence": track.confidence,
                "bbox": track.bbox,
                "zone": primary,
                "motion": motion,
                "stationary_seconds": round(low_movement, 1),
                "reasons": role_reasons,
                "global_worker_id": None,
                "identity_match_status": None,
                "identity_confidence": None,
                "tracker_predicted": track.predicted,
                "tracker_grace_remaining": round(
                    max(0.0, self.tracker.max_missed - track.missed_time), 1
                ),
            })
        customers = [item for item in classified if item[1] == "CUSTOMER"]
        worker_runtime = []
        stitch_debug_by_track: dict[int, dict] = {}
        for track, role, confirmed_zones, primary in classified:
            if role != "WORKER":
                continue
            left, top, right, bottom = [max(0, int(value)) for value in track.bbox]
            crop = frame[top:bottom, left:right]
            anonymous = self.worker_sessions.active.get(track.track_id)
            if anonymous is None:
                stitch = self.session_stitcher.match(track.bbox, crop, now_mono)
                if stitch:
                    anonymous = self.worker_sessions.rebind(track.track_id, stitch.session, now)
                    timers_preserved = bool(
                        stitch.gap_seconds <= settings.idle_track_gap_grace_seconds
                        and self.state_machine.rebind(
                            stitch.previous_track_id, track.track_id
                        )
                    )
                    if timers_preserved:
                        self.work_motion.rebind(
                            stitch.previous_track_id, track.track_id
                        )
                    else:
                        self.state_machine.clear(stitch.previous_track_id)
                        self.work_motion.clear(stitch.previous_track_id)
                    self._pending_runtime_expiry.pop(
                        stitch.previous_track_id, None
                    )
                    stitch_debug_by_track[track.track_id] = {
                        "reason": stitch.reason,
                        "confidence": round(stitch.confidence, 3),
                        "previous_track_id": stitch.previous_track_id,
                        "activity_timers_preserved": timers_preserved,
                    }
                    db.add(
                        self._session_stitch_audit(
                            anonymous.worker_session_id,
                            track.track_id,
                            stitch,
                            now,
                        )
                    )
                else:
                    anonymous = self.worker_sessions.ensure(
                        track.track_id, self.camera_id, self.camera_session_id, now
                    )
            stored = db.get(WorkerSession, anonymous.worker_session_id)
            if stored is None:
                stored = WorkerSession(
                    id=anonymous.worker_session_id, camera_id=self.camera_id, camera_session_id=self.camera_session_id,
                    track_id=track.track_id, employee_id=None, display_name=anonymous.display_name,
                    first_seen=now, last_seen=now, role_confidence=track.confidence,
                    limitations_json=[
                        "Camera-local anonymous session; a separate global ID may be assigned from clothing/body appearance.",
                        "No face recognition is used and cross-camera appearance matches require review.",
                    ],
                )
                db.add(stored)
            else:
                stored.last_seen = now
                stored.observed_seconds = seconds_between(stored.first_seen, now) or 0.0
                stored.ended_at = None
                stored.track_id = track.track_id
            identity = global_worker_identity_service.observe(
                db,
                worker_session_id=anonymous.worker_session_id,
                camera_id=self.camera_id,
                person_crop=crop,
                observed_at=now,
                now_monotonic=now_mono,
            )
            if identity and identity.identity_id:
                anonymous.display_name = identity.display_name
                stored.display_name = identity.display_name
            self.session_stitcher.observe(
                track.track_id, anonymous, track.bbox, crop, now_mono
            )
            worker_runtime.append(
                (track, confirmed_zones, primary, anonymous, stored, identity, crop)
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
                worker_session_id=anonymous.worker_session_id,
                track_id=track.track_id,
                bbox=track.bbox,
                zones=set(confirmed_zones),
                confidence=track.confidence,
            )
            for track, confirmed_zones, _, anonymous, _, _, _ in worker_runtime
        ]
        self.customers.update_scene(
            customer_observations,
            worker_observations,
            now,
            settings.track_max_center_distance,
        )
        self._persist_customer_state(db)
        for person in observed_people:
            session = self.customers.active.get(person["track_id"])
            if session and person["role"] == "CUSTOMER":
                person.update(
                    {
                        "customer_session_id": session.service_session_id,
                        "customer_phase": session.current_phase,
                        "activity": session.current_phase,
                        "waiting_seconds": (
                            seconds_between(session.waiting_started_at, now) or 0.0
                            if session.service_started_at is None
                            else session.waiting_seconds or 0.0
                        ),
                        "service_seconds": (
                            seconds_between(session.service_started_at, now) or 0.0
                            if session.service_started_at
                            else 0.0
                        ),
                        "medicine_retrieval_seconds": session.phase_seconds(
                            "FETCHING_MEDICINE", now
                        )
                        + session.phase_seconds("RETURNING_TO_CUSTOMER", now),
                        "assigned_worker_session_id": session.worker_session_id,
                        "assignment_confidence": session.assignment_confidence,
                        "customer_gap_seconds": (
                            seconds_between(session.customer_missing_since, now)
                            or 0.0
                            if session.customer_missing_since
                            else 0.0
                        ),
                    }
                )

        worker_states = []
        debug_phone_candidates = []
        phone_started = time.monotonic()
        self.phone_search.begin_frame()
        for track, confirmed_zones, primary, anonymous, stored, identity, crop in worker_runtime:
            left, top, right, bottom = [max(0, int(value)) for value in track.bbox]
            pose = track_poses.get(track.track_id)
            wrists = {}
            face = None
            if pose and pose.status != "STALE":
                if len(pose.global_keypoints) > 10:
                    if pose.global_keypoints[9][2] >= settings.pose_keypoint_confidence:
                        wrists["left"] = pose.global_keypoints[9][:2]
                    if pose.global_keypoints[10][2] >= settings.pose_keypoint_confidence:
                        wrists["right"] = pose.global_keypoints[10][:2]
                if pose.global_keypoints and pose.global_keypoints[0][2] >= settings.pose_keypoint_confidence:
                    face = pose.global_keypoints[0][:2]
            phone_hit = False
            phone_like_pose = False
            current_center = center(track.bbox)
            if pose and pose.status != "STALE" and wrists:
                body_height = max(1, bottom - top)
                shoulder_points = [pose.global_keypoints[index][:2] for index in (5, 6) if len(pose.global_keypoints) > index and pose.global_keypoints[index][2] >= settings.pose_keypoint_confidence]
                torso = (
                    (sum(point[0] for point in shoulder_points) / len(shoulder_points), sum(point[1] for point in shoulder_points) / len(shoulder_points))
                    if shoulder_points else current_center
                )
                phone_like_pose = any(
                    distance(wrist, torso) / body_height <= settings.phone_near_hand_distance_ratio
                    or (
                        face is not None
                        and distance(wrist, face) / body_height
                        <= settings.phone_near_head_distance_ratio
                    )
                    for wrist in wrists.values()
                )
                wrist_pose_confidence = max(
                    (
                        pose.global_keypoints[index][2]
                        for index in (9, 10)
                        if len(pose.global_keypoints) > index
                    ),
                    default=0.0,
                )
                phone_like_pose = bool(
                    phone_like_pose
                    and wrist_pose_confidence
                    >= settings.phone_pose_support_confidence
                )
                if phone_like_pose:
                    self.phone_search.trigger_focused(track.track_id, now_mono)
            candidates = []
            debug_crops = {"person_crop": crop}
            phone_box = self._expanded_phone_box(track.bbox, width, height)
            phone_crop = frame[
                phone_box[1] : phone_box[3], phone_box[0] : phone_box[2]
            ]
            if phone_ready and self.phone_search.should_search(track.track_id, packet.sequence_id, "person", now_mono):
                candidates.extend(
                    self.phone_detector.detect_crop(phone_crop, phone_box, "person")
                )
            if phone_ready and self.phone_search.is_focused(track.track_id, now_mono):
                phone_left, phone_top, phone_right, phone_bottom = phone_box
                upper_bottom = phone_top + max(1, int((phone_bottom - phone_top) * 0.68))
                upper_crop = frame[phone_top:upper_bottom, phone_left:phone_right]
                debug_crops["upper_body_crop"] = upper_crop
                if self.phone_search.should_search(track.track_id, packet.sequence_id, "upper_body", now_mono):
                    candidates.extend(
                        self.phone_detector.detect_crop(
                            upper_crop,
                            (phone_left, phone_top, phone_right, upper_bottom),
                            "upper_body",
                        )
                    )
                radius = max(32, int((bottom - top) * 0.16))
                for side, wrist in wrists.items():
                    wx, wy = [int(value) for value in wrist]
                    wrist_box = (max(0, wx - radius), max(0, wy - radius), min(width, wx + radius), min(height, wy + radius))
                    wrist_crop = frame[wrist_box[1]:wrist_box[3], wrist_box[0]:wrist_box[2]]
                    debug_crops[f"{side}_wrist_crop"] = wrist_crop
                    if self.phone_search.should_search(track.track_id, packet.sequence_id, f"{side}_wrist", now_mono):
                        candidates.extend(self.phone_detector.detect_crop(wrist_crop, wrist_box, f"{side}_wrist"))
            associations = []
            if candidates:
                associations = associate_phones(candidates, [{"track_id": track.track_id, "bbox": track.bbox, "wrists": wrists, "face": face}])
                phone_hit = any(item.track_id == track.track_id and item.candidate.physical for item in associations)
            associated_candidates = {
                id(item.candidate)
                for item in associations
                if item.track_id == track.track_id
            }
            debug_phone_candidates.extend(
                {
                    "bbox": item.bbox,
                    "confidence": item.confidence,
                    "source_region": item.source_region,
                    "associated": id(item) in associated_candidates,
                }
                for item in candidates
            )
            behavior_hit = any(
                item.track_id == track.track_id and item.candidate.behavior
                for item in associations
            )
            if phone_like_pose and not phone_hit and phone_ready:
                self.phone_detector.save_debug_miss(track.track_id, debug_crops, {"track_id": track.track_id, "frame_sequence": packet.sequence_id, "pose_status": pose.status if pose else "UNAVAILABLE"})
            physical_object_confidence = max(
                (
                    item.candidate.confidence
                    for item in associations
                    if item.track_id == track.track_id and item.candidate.physical
                ),
                default=0.0,
            )
            pose_support_confidence = max(
                (
                    pose.global_keypoints[index][2]
                    for index in (9, 10)
                    if pose is not None
                    and len(pose.global_keypoints) > index
                ),
                default=0.0,
            )
            context_support_confidence = max(
                (
                    item.association_score
                    for item in associations
                    if item.track_id == track.track_id
                ),
                default=0.0,
            )
            phone_state = self.phone_history.update(track.track_id, phone_hit, now_mono)
            temporal_phone_confidence = self.phone_history.confidence(
                track.track_id, now_mono
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
                anonymous.worker_session_id
            )
            service_phase = customer_service.current_phase if customer_service else None
            fetching_medicine = service_phase in MEDICINE_RETRIEVAL_PHASES
            serving = bool(
                service_phase in ACTIVE_SERVICE_PHASES and not fetching_medicine
            )
            cashier_work = bool(
                "cashier" in confirmed_zones
                and "register_interaction" in confirmed_zones
            )
            computer_work = bool(
                {"register_interaction", "computer", "pos"} & confirmed_zones
            )
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
                zones_configured=bool(zones),
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
            evidence = ActivityEvidence(
                camera_healthy=self.capture.health.snapshot()["status"] in {"HEALTHY", "DEGRADED"},
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
                    f"body_motion={work_motion.body_speed:.4f}",
                    f"bbox_motion={work_motion.bbox_speed:.4f}",
                    f"wrist_motion={work_motion.wrist_speed:.4f}",
                    f"elbow_motion={work_motion.elbow_speed:.4f}",
                ],
                limitations=([] if pose_ready else ["Pose model unavailable; bbox motion is used when reliable"])
                + ([] if zones else ["No activity zones are configured for this camera"]),
            )
            proposed = self.activity_engine.choose(evidence)
            proposed_unknown_reason = normalize_unknown_reason(
                proposed,
                evidence.unknown_reason,
            )
            if proposed_unknown_reason:
                evidence.reasons.append(f"unknown_reason={proposed_unknown_reason}")
            evidence_details = {
                "physical_phone_object_confidence": round(physical_object_confidence, 4),
                "pose_support_confidence": round(pose_support_confidence, 4),
                "context_support_confidence": round(context_support_confidence, 4),
                "temporal_phone_confidence": round(
                    temporal_phone_confidence, 4
                ),
                "final_fused_phone_confidence": round(final_phone_confidence, 4),
                "customer_service_session_id": (
                    customer_service.service_session_id if customer_service else None
                ),
                "customer_service_phase": service_phase,
                "evidence_quality": assessment.quality.value,
                "body_motion": work_motion.body_speed,
                "bbox_motion": work_motion.bbox_speed,
                "wrist_motion": work_motion.wrist_speed,
                "elbow_motion": work_motion.elbow_speed,
                "pose_status": pose_status,
                "pose_confidence": round(pose_support_confidence, 4),
                "track_age_seconds": round(track.age, 3),
                "track_stable": track.confirmed,
                "idle_blocking_reasons": idle_blocking_reasons,
                "idle_confirmation_seconds": settings.idle_confirm_seconds,
                "raw_track_id": track.track_id,
            }
            transition = self.state_machine.update(
                track.track_id,
                proposed,
                now_mono,
                track.confidence,
                evidence.reasons,
                evidence.limitations,
                evidence_quality=assessment.quality.value,
                idle_blocking_reasons=idle_blocking_reasons,
                exit_reason=(idle_blocking_reasons[0] if idle_blocking_reasons else None),
            )
            context = EventContext(anonymous.worker_session_id, track.track_id, self.camera_id, self.camera_session_id)
            current_activity = self.state_machine.states[track.track_id].current_state
            current_unknown_reason = self._current_unknown_reason(
                current_activity, proposed, proposed_unknown_reason
            )
            if current_unknown_reason:
                reason_text = f"unknown_reason={current_unknown_reason}"
                if reason_text not in evidence.reasons:
                    evidence.reasons.append(reason_text)
            if track.track_id not in events.active:
                events.open(context, current_activity, "VISIBLE", now, track.confidence, primary, evidence.reasons, evidence.limitations, current_unknown_reason, evidence_details)
            elif transition:
                closed, _ = events.transition(
                    context,
                    transition.current,
                    "VISIBLE",
                    now,
                    track.confidence,
                    primary,
                    evidence.reasons,
                    evidence.limitations,
                    proposed_unknown_reason if transition.current == "UNKNOWN" else None,
                    evidence_details,
                    transition.reason,
                )
                if (
                    closed
                    and closed.activity in {"ON_PHONE", "POSSIBLE_IDLE", "IDLE"}
                    and (
                        closed.activity != "IDLE"
                        or float(closed.duration_seconds or 0)
                        >= settings.idle_min_event_seconds
                    )
                ):
                    self._pending_clips.append((now_mono + settings.event_clip_post_seconds, closed))
            active_event = events.active.get(track.track_id)
            if active_event:
                active_event.unknown_reason = current_unknown_reason
                events.observe(track.track_id, evidence_details)
            state_diagnostics = self.state_machine.diagnostics(
                track.track_id, now_mono
            )
            if packet.sequence_id % settings.worker_snapshot_run_every_n_frames == 0 and crop.size:
                body_candidate = self.snapshots.consider(worker_session_id=anonymous.worker_session_id, camera_id=self.camera_id, image=crop, kind="body", role="WORKER")
                if body_candidate:
                    db.add(WorkerSnapshot(worker_session_id=anonymous.worker_session_id, kind="body", file_path=body_candidate.path, quality=body_candidate.quality, width=body_candidate.width, height=body_candidate.height))
                for face_crop in self.snapshots.detect_worker_faces(frame, track.bbox)[:1]:
                    face_candidate = self.snapshots.consider(worker_session_id=anonymous.worker_session_id, camera_id=self.camera_id, image=face_crop, kind="face", role="WORKER")
                    if face_candidate:
                        db.add(WorkerSnapshot(worker_session_id=anonymous.worker_session_id, kind="face", file_path=face_candidate.path, quality=face_candidate.quality, width=face_candidate.width, height=face_candidate.height))
            current_evidence_status = evidence_status("WORKER", current_activity)
            worker_states.append({
                "track_id": track.track_id, "worker_session_id": anonymous.worker_session_id,
                "display_name": anonymous.display_name, "presence": "VISIBLE",
                "activity": current_activity, "evidence_status": current_evidence_status,
                "confidence": track.confidence, "zone": primary,
                "motion": motion, "stationary_seconds": round(low_movement, 1),
                "global_worker_id": identity.identity_id if identity else None,
                "identity_match_status": identity.match_status if identity else None,
                "identity_confidence": identity.confidence if identity else None,
                "customer_service_session_id": customer_service.service_session_id if customer_service else None,
                "customer_service_phase": service_phase,
                "unknown_reason": current_unknown_reason,
                "phone_evidence": evidence_details,
                "session_stitch": stitch_debug_by_track.get(track.track_id),
                "track_age_seconds": round(track.age, 3),
                "track_stable": track.confirmed,
                "body_motion": work_motion.body_speed,
                "bbox_motion": work_motion.bbox_speed,
                "wrist_motion": work_motion.wrist_speed,
                "elbow_motion": work_motion.elbow_speed,
                "pose_status": pose_status,
                "pose_confidence": round(pose_support_confidence, 4),
                **state_diagnostics,
            })
            for person in observed_people:
                if person["track_id"] == track.track_id:
                    person.update({
                        "worker_session_id": anonymous.worker_session_id,
                        "display_name": anonymous.display_name,
                        "activity": current_activity,
                        "evidence_status": current_evidence_status,
                        "motion": motion,
                        "stationary_seconds": round(low_movement, 1),
                        "reasons": evidence.reasons + evidence.limitations,
                        "global_worker_id": identity.identity_id if identity else None,
                        "identity_match_status": identity.match_status if identity else None,
                        "identity_confidence": identity.confidence if identity else None,
                        "customer_service_session_id": customer_service.service_session_id if customer_service else None,
                        "customer_service_phase": service_phase,
                        "unknown_reason": current_unknown_reason,
                        "phone_evidence": evidence_details,
                        "session_stitch": stitch_debug_by_track.get(track.track_id),
                        "track_age_seconds": round(track.age, 3),
                        "track_stable": track.confirmed,
                        "body_motion": work_motion.body_speed,
                        "bbox_motion": work_motion.bbox_speed,
                        "wrist_motion": work_motion.wrist_speed,
                        "elbow_motion": work_motion.elbow_speed,
                        "pose_status": pose_status,
                        "pose_confidence": round(pose_support_confidence, 4),
                        **state_diagnostics,
                    })
                    break
        worker_track_by_session = {
            anonymous.worker_session_id: track.track_id
            for track, _, _, anonymous, _, _, _ in worker_runtime
        }
        debug_assignments = [
            {
                "service_session_id": session.service_session_id,
                "phase": session.current_phase,
                "worker_track_id": worker_track_by_session.get(
                    session.worker_session_id or ""
                ),
                "customer_track_id": session.customer_track_id,
            }
            for session in {
                id(value): value for value in self.customers.active.values()
            }.values()
            if session.worker_session_id
        ]
        self._update_debug_frame(
            frame,
            packet.sequence_id,
            zones,
            observed_people,
            track_poses,
            debug_phone_candidates,
            debug_assignments,
            len(worker_runtime),
            len(customers),
            {
                "person_ms": person_ms,
                "tracker_ms": tracker_ms,
                "pose_ms": pose_ms,
                "phone_ms": (time.monotonic() - phone_started) * 1000,
                "total_ms": (time.monotonic() - pipeline_started) * 1000,
                "candidates": len(detections),
            },
        )
        self._publish(worker_states, customers, unavailable=False, people=observed_people)

    def _expanded_phone_box(self, bbox, width: int, height: int) -> tuple[int, int, int, int]:
        left, top, right, bottom = bbox
        box_width = max(1.0, right - left)
        box_height = max(1.0, bottom - top)
        return (
            max(0, int(left - box_width * settings.phone_crop_expansion_x)),
            max(0, int(top - box_height * settings.phone_crop_expansion_y_top)),
            min(width, int(right + box_width * settings.phone_crop_expansion_x)),
            min(height, int(bottom + box_height * settings.phone_crop_expansion_y_bottom)),
        )

    @staticmethod
    def _current_unknown_reason(
        current_activity: str,
        proposed_activity: str,
        proposed_unknown_reason: str | None,
    ) -> str | None:
        if current_activity != "UNKNOWN":
            return None
        if proposed_activity != "UNKNOWN":
            return UnknownReason.INSUFFICIENT_TEMPORAL_EVIDENCE.value
        return normalize_unknown_reason("UNKNOWN", proposed_unknown_reason)

    def _session_stitch_audit(
        self,
        canonical_worker_session_id: str,
        new_track_id: int,
        stitch,
        at: datetime,
    ) -> WorkerSessionStitch:
        """Build the immutable audit row used by every accepted local stitch."""
        run_tag = "".join(
            character for character in self.camera_session_id if character.isalnum()
        )[-6:]
        return WorkerSessionStitch(
            camera_id=self.camera_id,
            canonical_worker_session_id=canonical_worker_session_id,
            original_session_id=(
                f"WS-{at:%Y%m%d}-C{self.camera_id}-{run_tag}-{new_track_id:03d}"
            ),
            previous_track_id=stitch.previous_track_id,
            new_track_id=new_track_id,
            gap_seconds=stitch.gap_seconds,
            appearance_distance=stitch.appearance_distance,
            spatial_distance=stitch.spatial_distance,
            confidence=stitch.confidence,
            reason=stitch.reason,
        )

    @staticmethod
    def _unknown_reason(
        activity: str,
        pose_ready: bool,
        pose,
        confirmed_zones: set[str],
        confidence: float,
        configured_zones: list[dict],
    ) -> str | None:
        if activity != "UNKNOWN":
            return None
        if confidence < 0.35:
            return UnknownReason.LOW_IMAGE_QUALITY.value
        if not configured_zones:
            return UnknownReason.CAMERA_ZONES_NOT_CONFIGURED.value
        if pose is not None and pose.status == "TEMPORARILY_MISSING":
            return UnknownReason.POSE_TEMPORARILY_MISSING.value
        if not pose_ready or pose is None or pose.status == "STALE":
            return UnknownReason.POSE_MISSING.value
        confident_points = sum(
            point[2] >= settings.pose_keypoint_confidence
            for point in pose.global_keypoints
        )
        if confident_points < 5:
            return UnknownReason.POSE_LOW_CONFIDENCE.value
        if not confirmed_zones:
            return UnknownReason.OUTSIDE_CONFIGURED_ZONES.value
        return UnknownReason.INSUFFICIENT_TEMPORAL_EVIDENCE.value

    def _update_debug_frame(
        self,
        frame,
        sequence_id: int,
        zones: list[dict],
        people: list[dict],
        poses: dict,
        phone_candidates: list[dict],
        assignments: list[dict],
        worker_count: int,
        customer_count: int,
        timings: dict,
    ) -> None:
        options = self.debug_settings()
        if not options.get("enabled"):
            with self._view_lock:
                self._debug_frame = None
            return
        pose_points = {
            track_id: value.global_keypoints
            for track_id, value in poses.items()
            if value is not None and value.status != "STALE"
        }
        unique_sessions = {
            id(value): value for value in self.customers.active.values()
        }.values()
        context = {
            "camera_id": self.camera_id,
            "frame_number": sequence_id,
            "zones": zones,
            "people": people,
            "poses": pose_points,
            "phone_candidates": phone_candidates,
            "assignments": assignments,
            "performance": {
                "capture_fps": self.capture.health.health.capture_fps,
                "processing_fps": self.capture.health.health.processing_fps,
                "people": len(people),
                "workers": worker_count,
                "customers": customer_count,
                "active_services": sum(
                    item.current_phase in ACTIVE_SERVICE_PHASES
                    for item in unique_sessions
                ),
                "waiting_customers": sum(
                    item.current_phase == "WAITING" for item in unique_sessions
                ),
                "phone_mode": self.phone_detector.mode,
                **timings,
            },
        }
        rendered = self.debug_renderer.render(frame, context, options)
        with self._view_lock:
            self._debug_frame = rendered

    def _persist_customer_state(self, db) -> None:
        persistence_time = utc_now()
        sessions = list(
            {id(value): value for value in self.customers.active.values()}.values()
        ) + list(self.customers.completed_sessions)
        for session in sessions:
            row = db.get(CustomerSession, session.service_session_id)
            values = {
                "customer_track_id": session.customer_track_id,
                "worker_session_id": session.worker_session_id,
                "camera_id": session.camera_id,
                "waiting_started_at": session.waiting_started_at,
                "service_started_at": session.service_started_at,
                "service_ended_at": session.service_ended_at,
                "waiting_seconds": (
                    session.waiting_seconds
                    if session.service_started_at
                    else seconds_between(session.waiting_started_at, persistence_time)
                ),
                "service_seconds": (
                    session.service_seconds
                    if session.service_ended_at
                    else seconds_between(session.service_started_at, persistence_time)
                    if session.service_started_at
                    else None
                ),
                "completed": session.completed,
                "left_without_service": session.left_without_service,
                "confidence": session.confidence,
                "current_phase": session.current_phase,
                "last_customer_seen_at": session.last_customer_seen_at,
                "last_worker_seen_at": session.last_worker_seen_at,
                "last_direct_interaction_at": session.last_direct_interaction_at,
                "medicine_retrieval_started_at": session.medicine_retrieval_started_at,
                "medicine_retrieval_ended_at": session.medicine_retrieval_ended_at,
                "medicine_retrieval_seconds": session.phase_seconds(
                    "FETCHING_MEDICINE", persistence_time
                )
                + session.phase_seconds(
                    "RETURNING_TO_CUSTOMER", persistence_time
                ),
                "direct_interaction_seconds": sum(
                    session.phase_seconds(phase, persistence_time)
                    for phase in (
                        "SERVING_AT_COUNTER",
                        "COMPLETING_TRANSACTION",
                    )
                ),
                "transaction_seconds": session.phase_seconds(
                    "COMPLETING_TRANSACTION", persistence_time
                ),
                "service_completed_at": session.service_completed_at,
                "outcome": session.outcome,
                "review_status": session.review_status,
                "assignment_confidence": session.assignment_confidence,
                "trust_classification": customer_trust_classification(session),
                "original_track_ids_json": session.original_track_ids,
                "limitations_json": session.limitations,
            }
            if row is None:
                row = CustomerSession(id=session.service_session_id, **values)
                db.add(row)
            else:
                for key, value in values.items():
                    setattr(row, key, value)
            for record in session.phase_records:
                stored_phase = db.get(CustomerServicePhase, record.id)
                phase_values = {
                    "customer_session_id": session.service_session_id,
                    "phase": record.phase,
                    "started_at": record.started_at,
                    "ended_at": record.ended_at,
                    "duration_seconds": record.duration_seconds,
                    "evidence_json": record.evidence,
                }
                if stored_phase is None:
                    db.add(CustomerServicePhase(id=record.id, **phase_values))
                else:
                    for key, value in phase_values.items():
                        setattr(stored_phase, key, value)
            for assignment in session.assignments:
                stored_assignment = db.get(WorkerCustomerAssignment, assignment.id)
                assignment_values = {
                    "customer_session_id": session.service_session_id,
                    "worker_session_id": assignment.worker_session_id,
                    "started_at": assignment.started_at,
                    "ended_at": assignment.ended_at,
                    "confidence": assignment.confidence,
                    "status": assignment.status,
                    "reasons_json": assignment.reasons,
                }
                if stored_assignment is None:
                    db.add(
                        WorkerCustomerAssignment(id=assignment.id, **assignment_values)
                    )
                else:
                    for key, value in assignment_values.items():
                        setattr(stored_assignment, key, value)
        self.customers.completed_sessions.clear()

    def _apply_customer_commands(self, now: datetime) -> None:
        with self._lock:
            commands = list(self._customer_commands)
            self._customer_commands.clear()
        for session_id, outcome in commands:
            self.customers.close_session(session_id, now, outcome)

    def _interrupt_orphan_customer_sessions(self, db) -> None:
        now = utc_now()
        rows = db.scalars(
            select(CustomerSession).where(
                CustomerSession.camera_id == self.camera_id,
                CustomerSession.completed.is_(False),
                CustomerSession.outcome == "ACTIVE",
            )
        ).all()
        for row in rows:
            row.current_phase = "INTERRUPTED"
            row.outcome = "INTERRUPTED"
            row.service_ended_at = row.last_customer_seen_at or now
            row.service_completed_at = row.service_ended_at
            if row.service_started_at:
                row.service_seconds = seconds_between(
                    row.service_started_at, row.service_ended_at
                )
        if rows:
            db.commit()

    def _flush_clips(self, now_mono: float) -> None:
        remaining = []
        for ready_at, event in self._pending_clips:
            if now_mono < ready_at:
                remaining.append((ready_at, event))
                continue
            span = settings.event_clip_pre_seconds + settings.event_clip_post_seconds + 1
            frames = self.evidence_frames.between(ready_at - span, ready_at)
            event.clip_path = self.clip_service.save(event.id, frames)
        self._pending_clips = deque(remaining, maxlen=64)

    def _expire_pending_runtime(self, now_mono: float) -> None:
        for track_id, expires_at in list(self._pending_runtime_expiry.items()):
            if now_mono < expires_at:
                continue
            self.state_machine.clear(track_id)
            self.work_motion.clear(track_id)
            getattr(self, "_pending_runtime_expiry", {}).pop(track_id, None)

    def _close_worker(
        self,
        db,
        events: EventService,
        track_id: int,
        now: datetime,
        *,
        ending_reason: str = "worker_session_closed",
        preserve_runtime: bool = False,
    ) -> None:
        events.close(track_id, now, ending_reason)
        anonymous = self.worker_sessions.close(track_id, now)
        if anonymous:
            global_worker_identity_service.close_session(anonymous.worker_session_id)
            stored = db.get(WorkerSession, anonymous.worker_session_id)
            if stored:
                stored.ended_at = now
                stored.last_seen = now
                stored.observed_seconds = seconds_between(stored.first_seen, now) or 0.0
        self.roles.clear(track_id)
        self.poses.clear(track_id)
        self.phone_history.clear(track_id)
        self.phone_search.clear(track_id)
        self.zone_history.clear(track_id)
        if not preserve_runtime:
            self.state_machine.clear(track_id)
            self.work_motion.clear(track_id)
            getattr(self, "_pending_runtime_expiry", {}).pop(track_id, None)
        self._last_centers.pop(track_id, None)
        self._last_moved_at.pop(track_id, None)

    def _handle_unavailable(self, db, events: EventService, status: str) -> None:
        now = utc_now()
        if self._active_health_event is None:
            self._active_health_event = HealthEvent(camera_id=self.camera_id, status=status, started_at=now, details_json={"presence": "UNKNOWN", "activity": "UNKNOWN"})
            db.add(self._active_health_event)
            for track_id in list(self.worker_sessions.active):
                self.session_stitcher.expire(track_id)
                self._close_worker(db, events, track_id, now)
            for track_id in list(self.customers.active):
                self.customers.mark_customer_missing(track_id, now)
            db.commit()
        self.customers.advance(now)
        self._persist_customer_state(db)
        self._publish([], [], unavailable=True)

    def _close_health_period(self, db, now: datetime) -> None:
        if self._active_health_event is None:
            return
        self._active_health_event.ended_at = now
        self._active_health_event.duration_seconds = seconds_between(self._active_health_event.started_at, now) or 0.0
        self._unavailable_seconds += self._active_health_event.duration_seconds
        self._active_health_event = None
        db.flush()

    def _publish(self, workers: list[dict], customers: list, unavailable: bool, people: list[dict] | None = None) -> None:
        health = self.capture.health.snapshot()
        alerts = []
        if unavailable or health["status"] in {"UNAVAILABLE", "FROZEN", "RECONNECTING"}:
            alerts.append({"type": "camera_unavailable", "severity": "warning"})
        now = utc_now()
        if any((seconds_between(session.waiting_started_at, now) or 0.0) >= settings.customer_wait_threshold_seconds for session in self.customers.active.values() if session.service_started_at is None):
            alerts.append({"type": "customer_waiting_over_threshold", "severity": "warning"})
        if customers and not any(worker["activity"] in {"SERVING_CUSTOMER", "CASHIER_WORK"} for worker in workers):
            alerts.append({"type": "counter_uncovered_while_customer_waits", "severity": "warning"})
        if any(worker["activity"] == "ON_PHONE" for worker in workers):
            alerts.append({"type": "confirmed_phone_event", "severity": "info"})
        if any(worker["activity"] == "POSSIBLE_IDLE" for worker in workers):
            alerts.append({"type": "possible_idle_event", "severity": "info"})
        with self._lock:
            customer_sessions = list(
                {id(value): value for value in self.customers.active.values()}.values()
            )
            customer_diagnostics = []
            for item in customer_sessions:
                service_elapsed = (
                    seconds_between(item.service_started_at, now) or 0.0
                    if item.service_started_at
                    else 0.0
                )
                waiting_elapsed = (
                    seconds_between(item.waiting_started_at, now) or 0.0
                    if item.service_started_at is None
                    else float(item.waiting_seconds or 0)
                )
                retrieval_elapsed = item.phase_seconds(
                    "FETCHING_MEDICINE", now
                ) + item.phase_seconds("RETURNING_TO_CUSTOMER", now)
                customer_gap = (
                    seconds_between(item.customer_missing_since, now) or 0.0
                    if item.customer_missing_since
                    else 0.0
                )
                worker_gap = (
                    seconds_between(item.last_worker_seen_at, now) or 0.0
                    if item.last_worker_seen_at
                    else 0.0
                )
                customer_diagnostics.append(
                    {
                        "customer_session_id": item.service_session_id,
                        "customer_track_id": item.customer_track_id,
                        "waiting_state": item.current_phase == "WAITING",
                        "waiting_seconds": round(waiting_elapsed, 3),
                        "assigned_worker_session_id": item.worker_session_id,
                        "service_phase": item.current_phase,
                        "service_elapsed_seconds": round(service_elapsed, 3),
                        "medicine_retrieval_seconds": round(
                            retrieval_elapsed, 3
                        ),
                        "assignment_confidence": round(
                            float(item.assignment_confidence or 0), 3
                        ),
                        "customer_gap_seconds": round(customer_gap, 3),
                        "customer_end_grace_remaining_seconds": round(
                            max(
                                0.0,
                                max(
                                    settings.customer_lost_timeout_seconds,
                                    settings.service_end_confirm_seconds,
                                )
                                - customer_gap,
                            ),
                            3,
                        ),
                        "worker_return_remaining_seconds": round(
                            max(
                                0.0,
                                settings.worker_return_timeout_seconds
                                - worker_gap,
                            ),
                            3,
                        ),
                    }
                )
            self._live = {
                "people_visible": len(people or []),
                "workers_visible": len(workers),
                "customer_count": len(customers),
                "observed_people": people or [],
                "worker_states": workers,
                "customer_diagnostics": customer_diagnostics,
                "alerts": alerts,
                "active_service_sessions": sum(
                    item.current_phase in ACTIVE_SERVICE_PHASES
                    for item in customer_sessions
                ),
                "active_waiting_customers": sum(
                    item.current_phase == "WAITING" for item in customer_sessions
                ),
                "debug": self.debug_settings(),
                "camera_diagnostics": {
                    "camera_id": self.camera_id,
                    "capture_fps": health.get("capture_fps", 0),
                    "processing_fps": health.get("processing_fps", 0),
                    "current_frame_number": health.get("capture_sequence", 0),
                    "worker_count": len(workers),
                    "customer_count": len(customers),
                    "active_service_sessions": sum(
                        item.current_phase in ACTIVE_SERVICE_PHASES
                        for item in customer_sessions
                    ),
                    "waiting_customers": sum(
                        item.current_phase == "WAITING"
                        for item in customer_sessions
                    ),
                },
            }
