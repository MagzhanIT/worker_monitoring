from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from config import settings


@dataclass
class WorkMotionSignal:
    confirmed: bool = False
    reaching: bool = False
    wrist_speed: float = 0.0
    elbow_speed: float = 0.0
    body_speed: float = 0.0
    bbox_speed: float = 0.0
    pose_reliable: bool = False
    bbox_reliable: bool = False
    low_motion: bool = False
    low_motion_seconds: float = 0.0
    pose_temporarily_missing: bool = False
    reason: str = "pose evidence unavailable"


class TemporalWorkMotion:
    """Conservative worker-only hand-motion evidence adapted from pose_activity.py."""

    def __init__(self) -> None:
        self.previous: dict[int, tuple[float, np.ndarray]] = {}
        self.previous_bbox: dict[int, tuple[float, np.ndarray]] = {}
        self.votes: dict[int, deque[bool]] = {}
        self.motion_history: dict[int, dict[str, deque[float]]] = {}
        self.low_motion_started_at: dict[int, float] = {}
        self.last_reliable_pose_at: dict[int, float] = {}

    def _smooth(self, track_id: int, name: str, value: float) -> float:
        histories = self.motion_history.setdefault(track_id, {})
        values = histories.setdefault(
            name,
            deque(
                maxlen=(
                    settings.movement_smoothing_window
                    if name == "bbox"
                    else settings.pose_smoothing_window
                )
            ),
        )
        values.append(max(0.0, float(value)))
        return float(np.median(np.asarray(values, dtype=np.float32)))

    def update(self, track_id: int, pose, bbox, now: float) -> WorkMotionSignal:
        height = max(1.0, float(bbox[3] - bbox[1]))
        bbox_center = np.asarray(
            ((bbox[0] + bbox[2]) * 0.5, (bbox[1] + bbox[3]) * 0.5),
            dtype=np.float32,
        )
        previous_bbox = self.previous_bbox.get(track_id)
        bbox_reliable = previous_bbox is not None
        bbox_speed = 0.0
        if previous_bbox is not None:
            previous_at, previous_center = previous_bbox
            elapsed = max(0.05, now - previous_at)
            bbox_speed = float(np.linalg.norm(bbox_center - previous_center) / height / elapsed)
        self.previous_bbox[track_id] = (now, bbox_center)
        bbox_speed = self._smooth(track_id, "bbox", bbox_speed)

        pose_reliable = bool(
            settings.work_motion_enabled
            and pose is not None
            and pose.status != "STALE"
        )
        points = (
            np.asarray(pose.global_keypoints, dtype=np.float32)
            if pose_reliable
            else np.empty((0, 3), dtype=np.float32)
        )
        if points.ndim != 2 or points.shape[0] < 13 or points.shape[1] < 3:
            pose_reliable = False
        valid = (
            points[:, 2] >= settings.pose_keypoint_confidence
            if pose_reliable
            else np.zeros(0, dtype=bool)
        )
        wrists = [index for index in (9, 10) if pose_reliable and valid[index]]
        elbows = [index for index in (7, 8) if pose_reliable and valid[index]]
        shoulders = [index for index in (5, 6) if pose_reliable and valid[index]]
        hips = [index for index in (11, 12) if pose_reliable and valid[index]]
        pose_reliable = bool(pose_reliable and wrists and elbows)
        if pose_reliable:
            self.last_reliable_pose_at[track_id] = now
        pose_temporarily_missing = bool(
            not pose_reliable
            and track_id in self.last_reliable_pose_at
            and now - self.last_reliable_pose_at[track_id]
            <= settings.idle_pose_grace_seconds
        )

        reaching = False
        if pose_reliable and shoulders:
            shoulder_center = np.mean(points[shoulders, :2], axis=0)
            reaching = any(
                np.linalg.norm(points[index, :2] - shoulder_center) / height
                >= settings.work_motion_reach_ratio
                for index in wrists
            )
        if hips:
            hip_y = float(np.mean(points[hips, 1]))
            reaching = reaching and any(points[index, 1] <= hip_y + 0.05 * height for index in wrists)

        wrist_speed = 0.0
        elbow_speed = 0.0
        body_speed = 0.0
        previous = self.previous.get(track_id)
        if pose_reliable and previous is not None:
            previous_at, previous_points = previous
            elapsed = max(0.05, now - previous_at)
            valid_previous = previous_points[:, 2] >= settings.pose_keypoint_confidence

            def speed(indices: list[int]) -> float:
                shared = [index for index in indices if valid[index] and valid_previous[index]]
                if not shared:
                    return 0.0
                movement = np.linalg.norm(
                    points[shared, :2] - previous_points[shared, :2], axis=1
                )
                return float(np.median(movement) / height / elapsed)

            wrist_speed = speed([9, 10])
            elbow_speed = speed([7, 8])
            body_speed = speed([5, 6, 7, 8, 11, 12])
        if pose_reliable:
            self.previous[track_id] = (now, points.copy())
            wrist_speed = self._smooth(track_id, "wrist", wrist_speed)
            elbow_speed = self._smooth(track_id, "elbow", elbow_speed)
            body_speed = self._smooth(track_id, "body", body_speed)

        raw = bool(
            pose_reliable
            and
            reaching
            and wrist_speed >= settings.work_motion_min_wrist_speed
            and body_speed <= settings.work_motion_max_body_speed
        )
        history = self.votes.setdefault(
            track_id, deque(maxlen=settings.work_motion_confirm_window)
        )
        history.append(raw)
        confirmed = sum(history) >= settings.work_motion_min_confirm_hits
        effective_body_speed = max(bbox_speed, body_speed if pose_reliable else 0.0)
        low_motion = bool(
            bbox_reliable
            and effective_body_speed <= settings.idle_body_motion_threshold
            and (
                not pose_reliable
                or (
                    wrist_speed <= settings.idle_wrist_motion_threshold
                    and elbow_speed <= settings.idle_elbow_motion_threshold
                )
            )
        )
        if low_motion:
            self.low_motion_started_at.setdefault(track_id, now)
        else:
            self.low_motion_started_at.pop(track_id, None)
        low_motion_seconds = (
            max(0.0, now - self.low_motion_started_at[track_id])
            if track_id in self.low_motion_started_at
            else 0.0
        )
        reason = (
            "repeated reaching hand movement in employee area"
            if confirmed
            else "work-like hand movement is still confirming"
            if raw
            else "no repeated reaching hand movement"
        )
        return WorkMotionSignal(
            confirmed=confirmed,
            reaching=reaching,
            wrist_speed=round(wrist_speed, 4),
            elbow_speed=round(elbow_speed, 4),
            body_speed=round(effective_body_speed, 4),
            bbox_speed=round(bbox_speed, 4),
            pose_reliable=pose_reliable,
            bbox_reliable=bbox_reliable,
            low_motion=low_motion,
            low_motion_seconds=round(low_motion_seconds, 3),
            pose_temporarily_missing=pose_temporarily_missing,
            reason=reason,
        )

    def clear(self, track_id: int) -> None:
        self.previous.pop(track_id, None)
        self.previous_bbox.pop(track_id, None)
        self.votes.pop(track_id, None)
        self.motion_history.pop(track_id, None)
        self.low_motion_started_at.pop(track_id, None)
        self.last_reliable_pose_at.pop(track_id, None)

    def rebind(self, previous_track_id: int, new_track_id: int) -> bool:
        moved = False
        for values in (
            self.previous,
            self.previous_bbox,
            self.votes,
            self.motion_history,
            self.low_motion_started_at,
            self.last_reliable_pose_at,
        ):
            if previous_track_id in values:
                values.pop(new_track_id, None)
                values[new_track_id] = values.pop(previous_track_id)
                moved = True
        return moved
