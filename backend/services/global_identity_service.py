from __future__ import annotations

import json
import math
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Iterable

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from config import settings
from db_models.worker_identity import (
    WorkerAppearanceSignature,
    WorkerIdentity,
    WorkerIdentityLink,
)
from db_models.worker_session import WorkerSession
from utilities.file_security import protect_text, reveal_text
from utilities.image_quality import image_quality


DESCRIPTOR_VERSION = "clothing-v1"
IDENTITY_LIMITATIONS = [
    "Anonymous day-scoped appearance ID; not a legal or payroll identity.",
    "Uses clothing and body appearance only; no face recognition or face embedding.",
    "Similar uniforms, occlusion, lighting, or clothing changes can create a wrong or duplicate match.",
    "Managers must review uncertain or operationally important cross-camera associations.",
]


def normalize(vector: np.ndarray) -> np.ndarray:
    value = np.asarray(vector, dtype=np.float32).reshape(-1)
    length = float(np.linalg.norm(value))
    return value / length if length > 1e-8 else value


def cosine_distance(first: np.ndarray, second: np.ndarray) -> float:
    if np.asarray(first).size != np.asarray(second).size:
        return 2.0
    return float(
        np.clip(1.0 - np.dot(normalize(first), normalize(second)), 0.0, 2.0)
    )


def _region_descriptor(region: np.ndarray) -> np.ndarray:
    """Colour plus coarse texture descriptor adapted from the supplied prototype."""
    import cv2

    if region.size == 0:
        return np.zeros(211, dtype=np.float32)
    resized = cv2.resize(region, (48, 64), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 25, 20), (179, 255, 255))
    colour = cv2.calcHist(
        [hsv], [0, 1], mask, [16, 8], [0, 180, 0, 256]
    ).reshape(-1)
    colour = normalize(colour)
    value = cv2.calcHist([hsv], [2], None, [16], [0, 256]).reshape(-1)
    value = normalize(value)
    coarse = cv2.resize(hsv[:, :, :2], (4, 4), interpolation=cv2.INTER_AREA).astype(
        np.float32
    )
    coarse[:, :, 0] /= 180.0
    coarse[:, :, 1] /= 255.0
    coarse = normalize(coarse.reshape(-1))
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    texture = normalize(cv2.dct(gray)[:6, :6].reshape(-1)[1:])
    return np.concatenate((colour, value, coarse, texture)).astype(np.float32)


def clothing_descriptor(person_crop: np.ndarray) -> np.ndarray | None:
    """Describe full-body clothing while retaining torso/leg layout."""
    if person_crop is None or getattr(person_crop, "size", 0) == 0:
        return None
    height, width = person_crop.shape[:2]
    if height < settings.global_worker_id_min_crop_height or width < settings.global_worker_id_min_crop_width:
        return None
    left, right = int(width * 0.12), max(int(width * 0.88), 1)
    torso = person_crop[int(height * 0.16) : int(height * 0.58), left:right]
    legs = person_crop[int(height * 0.55) : int(height * 0.94), left:right]
    if torso.size == 0 or legs.size == 0:
        return None
    descriptor = np.concatenate(
        (
            0.55 * _region_descriptor(person_crop),
            0.30 * _region_descriptor(torso),
            0.15 * _region_descriptor(legs),
        )
    )
    return normalize(descriptor)


def encode_descriptor(descriptor: np.ndarray) -> str:
    payload = json.dumps(normalize(descriptor).round(7).tolist(), separators=(",", ":"))
    return protect_text(payload)


def decode_descriptor(ciphertext: str) -> np.ndarray | None:
    try:
        value = np.asarray(json.loads(reveal_text(ciphertext)), dtype=np.float32)
        return normalize(value) if value.size else None
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def ranked_identity_matches(
    descriptor: np.ndarray,
    profiles: Iterable[tuple[str, list[np.ndarray]]],
) -> list[tuple[str, float]]:
    scores: list[tuple[str, float]] = []
    for identity_id, signatures in profiles:
        distances = sorted(cosine_distance(descriptor, value) for value in signatures)
        if not distances:
            continue
        score = distances[0]
        if len(distances) > 1:
            score = 0.85 * distances[0] + 0.15 * distances[1]
        scores.append((identity_id, float(score)))
    return sorted(scores, key=lambda item: item[1])


@dataclass
class IdentityResolution:
    identity_id: str | None
    display_name: str
    match_status: str
    confidence: float
    distance: float | None = None
    margin: float | None = None
    reason: str = ""


@dataclass
class _IdentityProfile:
    identity_id: str
    display_name: str
    scope_date: date
    signatures: list[np.ndarray] = field(default_factory=list)


@dataclass
class _ActiveIdentity:
    worker_session_id: str
    camera_id: int
    last_seen_monotonic: float


class GlobalWorkerIdentityService:
    """Thread-safe conservative association across camera-local worker sessions."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._buffers: dict[str, deque[np.ndarray]] = {}
        self._last_sample: dict[str, float] = {}
        self._assignments: dict[str, IdentityResolution] = {}
        self._active: dict[str, _ActiveIdentity] = {}
        self._profiles: dict[tuple[date, str], _IdentityProfile] = {}
        self._loaded_scopes: set[date] = set()

    def reset_runtime_cache(self) -> None:
        with self._lock:
            self._buffers.clear()
            self._last_sample.clear()
            self._assignments.clear()
            self._active.clear()
            self._profiles.clear()
            self._loaded_scopes.clear()

    @staticmethod
    def _scope(observed_at: datetime) -> date:
        return observed_at.date()

    def _load_scope(self, db: Session, scope: date) -> None:
        if scope in self._loaded_scopes:
            return
        identities = db.scalars(
            select(WorkerIdentity).where(WorkerIdentity.scope_date == scope)
        ).all()
        by_id = {
            item.id: _IdentityProfile(item.id, item.display_name, scope)
            for item in identities
        }
        if by_id:
            signatures = db.scalars(
                select(WorkerAppearanceSignature).where(
                    WorkerAppearanceSignature.worker_identity_id.in_(list(by_id))
                )
            ).all()
            for signature in signatures:
                descriptor = decode_descriptor(signature.descriptor_ciphertext)
                if descriptor is not None:
                    by_id[signature.worker_identity_id].signatures.append(descriptor)
        for identity_id, profile in by_id.items():
            self._profiles[(scope, identity_id)] = profile
        self._loaded_scopes.add(scope)

    @staticmethod
    def _new_identity(scope: date, observed_at: datetime, camera_id: int, status: str) -> WorkerIdentity:
        suffix = uuid.uuid4().hex[:6].upper()
        identity_id = f"GW-{scope:%Y%m%d}-{suffix}"
        return WorkerIdentity(
            id=identity_id,
            display_name=f"Worker {suffix}",
            scope_date=scope,
            status=status,
            last_seen_at=observed_at,
            last_camera_id=camera_id,
            limitations_json=list(IDENTITY_LIMITATIONS),
        )

    def _active_conflict(
        self, identity_id: str, worker_session_id: str, now_monotonic: float
    ) -> bool:
        current = self._active.get(identity_id)
        return bool(
            current
            and current.worker_session_id != worker_session_id
            and now_monotonic - current.last_seen_monotonic
            <= settings.global_worker_id_active_conflict_seconds
        )

    @staticmethod
    def _confidence(distance: float, margin: float) -> float:
        threshold = settings.global_worker_id_match_threshold
        distance_score = max(0.0, min(1.0, 1.0 - distance / max(threshold, 1e-6)))
        margin_score = max(
            0.0,
            min(1.0, margin / max(settings.global_worker_id_min_margin * 2.0, 1e-6)),
        )
        return round(0.7 * distance_score + 0.3 * margin_score, 3)

    def _existing_link(
        self, db: Session, worker_session_id: str
    ) -> IdentityResolution | None:
        link = db.get(WorkerIdentityLink, worker_session_id)
        if not link:
            return None
        identity = db.get(WorkerIdentity, link.worker_identity_id)
        if not identity:
            return None
        return IdentityResolution(
            identity.id,
            identity.display_name,
            link.match_status,
            float(link.confidence or 0),
            link.distance,
            link.margin,
            "Loaded existing global worker assignment",
        )

    def observe(
        self,
        db: Session,
        *,
        worker_session_id: str,
        camera_id: int,
        person_crop,
        observed_at: datetime,
        now_monotonic: float,
    ) -> IdentityResolution | None:
        if not settings.global_worker_id_enabled:
            return None
        with self._lock:
            resolution = self._assignments.get(worker_session_id)
            if resolution and resolution.identity_id:
                self._active[resolution.identity_id] = _ActiveIdentity(
                    worker_session_id, camera_id, now_monotonic
                )
                return resolution
            existing = self._existing_link(db, worker_session_id)
            if existing:
                self._assignments[worker_session_id] = existing
                self._active[existing.identity_id] = _ActiveIdentity(
                    worker_session_id, camera_id, now_monotonic
                )
                return existing
            if (
                now_monotonic - self._last_sample.get(worker_session_id, -math.inf)
                < settings.global_worker_id_observation_interval_seconds
            ):
                return resolution

            quality = image_quality(person_crop)
            descriptor = (
                clothing_descriptor(person_crop)
                if quality >= settings.global_worker_id_min_quality
                else None
            )
            self._last_sample[worker_session_id] = now_monotonic
            if descriptor is None:
                return IdentityResolution(
                    None,
                    "Anonymous worker",
                    "pending_low_quality",
                    0,
                    reason="Waiting for a sufficiently clear full-body crop",
                )
            values = self._buffers.setdefault(
                worker_session_id,
                deque(maxlen=settings.global_worker_id_min_observations),
            )
            values.append(descriptor)
            if len(values) < settings.global_worker_id_min_observations:
                return IdentityResolution(
                    None,
                    "Anonymous worker",
                    "collecting_evidence",
                    len(values) / settings.global_worker_id_min_observations,
                    reason=(
                        f"Collecting clothing observations {len(values)}/"
                        f"{settings.global_worker_id_min_observations}"
                    ),
                )

            aggregate = normalize(np.median(np.stack(list(values)), axis=0))
            scope = self._scope(observed_at)
            self._load_scope(db, scope)
            profiles = [
                (profile.identity_id, profile.signatures)
                for (profile_scope, _), profile in self._profiles.items()
                if profile_scope == scope and profile.signatures
            ]
            ranked = ranked_identity_matches(aggregate, profiles)
            best_id, best_distance = ranked[0] if ranked else (None, math.inf)
            second_distance = ranked[1][1] if len(ranked) > 1 else math.inf
            margin = second_distance - best_distance

            if (
                best_id is not None
                and best_distance <= settings.global_worker_id_match_threshold
                and self._active_conflict(best_id, worker_session_id, now_monotonic)
            ):
                return IdentityResolution(
                    None,
                    "Anonymous worker",
                    "pending_active_conflict",
                    0,
                    best_distance,
                    margin if math.isfinite(margin) else None,
                    "Best appearance ID is still active on another camera; waiting instead of merging",
                )

            safe_match = bool(
                best_id is not None
                and best_distance <= settings.global_worker_id_match_threshold
                and margin >= settings.global_worker_id_min_margin
            )
            if safe_match:
                identity = db.get(WorkerIdentity, best_id)
                if identity is None:
                    safe_match = False

            if safe_match:
                confidence = self._confidence(best_distance, margin)
                match_status = "appearance_matched"
                match_method = "encrypted_clothing_descriptor"
                reason = "Matched by clothing/body appearance with threshold and second-best margin"
                identity.last_seen_at = observed_at
                identity.last_camera_id = camera_id
            else:
                ambiguous = bool(
                    best_id is not None
                    and best_distance <= settings.global_worker_id_match_threshold
                    and margin < settings.global_worker_id_min_margin
                )
                identity = self._new_identity(
                    scope,
                    observed_at,
                    camera_id,
                    "review_required" if ambiguous else "provisional",
                )
                db.add(identity)
                confidence = 0.25 if ambiguous else 0.5
                match_status = "ambiguous_separate" if ambiguous else "new_identity"
                match_method = "conservative_new_identity"
                reason = (
                    "Similar candidates were ambiguous; kept separate to avoid a false merge"
                    if ambiguous
                    else "No safe day-scoped appearance match; created a new anonymous ID"
                )
                best_distance = best_distance if math.isfinite(best_distance) else None
                margin = margin if math.isfinite(margin) else None
                self._profiles[(scope, identity.id)] = _IdentityProfile(
                    identity.id, identity.display_name, scope
                )

            link = WorkerIdentityLink(
                worker_session_id=worker_session_id,
                worker_identity_id=identity.id,
                match_method=match_method,
                match_status=match_status,
                confidence=confidence,
                distance=best_distance,
                margin=margin,
                notes_json=[reason],
            )
            signature = WorkerAppearanceSignature(
                worker_identity_id=identity.id,
                source_session_id=worker_session_id,
                camera_id=camera_id,
                descriptor_version=DESCRIPTOR_VERSION,
                descriptor_ciphertext=encode_descriptor(aggregate),
                quality=quality,
            )
            db.add_all((link, signature))
            session = db.get(WorkerSession, worker_session_id)
            if session:
                session.display_name = identity.display_name
                session.limitations_json = list(
                    dict.fromkeys(list(session.limitations_json or []) + IDENTITY_LIMITATIONS)
                )
            db.flush()

            profile = self._profiles.setdefault(
                (scope, identity.id),
                _IdentityProfile(identity.id, identity.display_name, scope),
            )
            if len(profile.signatures) < settings.global_worker_id_max_signatures:
                profile.signatures.append(aggregate)
            resolution = IdentityResolution(
                identity.id,
                identity.display_name,
                match_status,
                confidence,
                best_distance,
                margin,
                reason,
            )
            self._assignments[worker_session_id] = resolution
            self._active[identity.id] = _ActiveIdentity(
                worker_session_id, camera_id, now_monotonic
            )
            return resolution

    def close_session(self, worker_session_id: str) -> None:
        with self._lock:
            resolution = self._assignments.pop(worker_session_id, None)
            self._buffers.pop(worker_session_id, None)
            self._last_sample.pop(worker_session_id, None)
            if resolution and resolution.identity_id:
                active = self._active.get(resolution.identity_id)
                if active and active.worker_session_id == worker_session_id:
                    self._active.pop(resolution.identity_id, None)

    def manager_assignment_updated(self, worker_session_id: str, scope: date) -> None:
        """Invalidate only affected runtime state after an audited manager correction."""
        with self._lock:
            previous = self._assignments.pop(worker_session_id, None)
            self._buffers.pop(worker_session_id, None)
            self._last_sample.pop(worker_session_id, None)
            if previous and previous.identity_id:
                active = self._active.get(previous.identity_id)
                if active and active.worker_session_id == worker_session_id:
                    self._active.pop(previous.identity_id, None)
            for key in [key for key in self._profiles if key[0] == scope]:
                self._profiles.pop(key, None)
            self._loaded_scopes.discard(scope)


def purge_expired_signatures(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=settings.global_worker_id_signature_retention_days)
    result = db.execute(
        delete(WorkerAppearanceSignature).where(
            WorkerAppearanceSignature.created_at < cutoff
        )
    )
    return int(result.rowcount or 0)


global_worker_identity_service = GlobalWorkerIdentityService()
